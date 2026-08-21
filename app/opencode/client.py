import asyncio
import inspect
import os
from pathlib import Path
from typing import Any
from app.config.settings import BASE_DIR
from acp import RequestError, spawn_agent_process
from acp.schema import (
    AgentMessageChunk, ToolCallStart, ToolCallProgress,
    PermissionOption, AllowedOutcome, DeniedOutcome, RequestPermissionResponse,
    ReadTextFileResponse,
    CreateTerminalResponse, TerminalOutputResponse,
    ReleaseTerminalResponse, WaitForTerminalExitResponse,
    KillTerminalResponse, WriteTextFileResponse,
    TextContentBlock, ToolCallUpdate,
)


class VaronikaClient:
    """
    Implements the ACP Client protocol: handles callbacks FROM OpenCode.
    The Agent (connection) is used to SEND requests TO OpenCode.
    """

    def __init__(self):
        self.connection = None  # Will be set to the Agent-side connection
        self.session_id = None
        self.on_text_chunk = None       # callback(str)
        self.on_tool_start = None       # callback(title, tool_call_id, *, kind, raw_input)
        self.on_tool_update = None      # callback(tool_call_id, *, title, kind, raw_input, locations, status)
        self._accumulated_text = ""

    def on_connect(self, conn) -> None:
        """Called when the connection is established."""
        self.connection = conn

    async def session_update(
        self, session_id: str, update, **kwargs: Any
    ) -> None:
        """Called when OpenCode sends a session notification (streamed chunks)."""
        if session_id != self.session_id:
            return
        if isinstance(update, AgentMessageChunk):
            if update.content and hasattr(update.content, 'text') and update.content.text:
                self._accumulated_text += update.content.text
                if self.on_text_chunk:
                    self.on_text_chunk(update.content.text)

        elif isinstance(update, ToolCallStart):
            if self.on_tool_start:
                self.on_tool_start(
                    update.title or "Tool",
                    update.tool_call_id,
                    kind=update.kind,
                    raw_input=update.raw_input,
                )

        elif isinstance(update, ToolCallProgress):
            if self.on_tool_update:
                self.on_tool_update(
                    update.tool_call_id,
                    title=update.title,
                    kind=update.kind,
                    raw_input=update.raw_input,
                    locations=update.locations,
                    status=update.status,
                )

    async def request_permission(
        self, options: list[PermissionOption], session_id: str, tool_call: ToolCallUpdate, **kwargs: Any
    ) -> RequestPermissionResponse:
        """Always approve: permissions are auto-approved by OpenCode."""
        if not options:
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        # Pick the first allow-kind option. If OpenCode offered only deny
        # options, approving is wrong: deny explicitly instead of blindly
        # selecting the first (which could be a deny the agent never asked for).
        allow_id = next(
            (o.option_id for o in options if str(getattr(o, "kind", "")).startswith("allow")),
            None,
        )
        if allow_id is None:
            title = getattr(tool_call, "title", None) or "unknown tool"
            print(f"Permission request denied: no allow option offered for {title}")
            return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))
        return RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", option_id=allow_id))

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        """Read a file slice. ACP `line` is 1-based; `limit` is a line count, not bytes."""
        try:
            start = line if (line is not None and line > 0) else 1
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                if start == 1 and limit is None:
                    content = f.read()
                else:
                    rows = []
                    for i, row in enumerate(f, start=1):
                        if i < start:
                            continue
                        rows.append(row)
                        if limit is not None and len(rows) >= limit:
                            break
                    content = "".join(rows)
            return ReadTextFileResponse(content=content)
        except Exception as e:
            return ReadTextFileResponse(content=f"Error reading file: {e}")

    async def write_text_file(self, content: str, path: str, session_id: str, **kwargs: Any) -> WriteTextFileResponse | None:
        try:
            dirname = os.path.dirname(path)
            if dirname:
                os.makedirs(dirname, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            return WriteTextFileResponse()
        except Exception as e:
            raise Exception(f"Failed to write file: {e}")

    async def create_terminal(self, command: str, session_id: str, **kwargs: Any) -> CreateTerminalResponse:
        # Terminals are not supported: tell the agent with a proper JSON-RPC
        # error instead of a fake success it could wait on forever.
        raise RequestError.method_not_found("terminal/create")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        raise RequestError.method_not_found("terminal/output")

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> ReleaseTerminalResponse | None:
        raise RequestError.method_not_found("terminal/release")

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> WaitForTerminalExitResponse:
        raise RequestError.method_not_found("terminal/wait_for_exit")

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        raise RequestError.method_not_found("terminal/kill")

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        pass


class OpenCodeClient:
    # Hard cap on a single prompt (including long tool runs). A wedged or
    # silently dead connection must never leave the user waiting forever;
    # on timeout the connection is reset and the next prompt reconnects.
    PROMPT_TIMEOUT = 900.0
    # Liveness probe: any response (even an error) within this window proves
    # the receive loop is still alive.
    PROBE_TIMEOUT = 5.0
    # Auto-reconnect backoff: 1s, then doubling up to 60s per attempt.
    RECONNECT_BASE_DELAY = 1.0
    RECONNECT_MAX_DELAY = 60.0
    # How often the background heartbeat probes a quiet connection. It
    # detects a silently broken pipe (see _watch) while the user is idle,
    # so the UI "connected" message is revoked and the reconnect happens
    # before the next prompt.
    HEARTBEAT_INTERVAL = 20.0
    # One response line may legitimately be huge (a long file read). The
    # default 32MB limit made a single oversized message kill the receive
    # loop permanently; 256MB is effectively unlimited for real traffic.
    TRANSPORT_LIMIT = 256 * 1024 * 1024
    # Hard cap for establishing a session (spawn to new_session). A server
    # that never answers session/new would otherwise block every prompt,
    # the reset path, and the reconnect loop forever, with no watcher or
    # heartbeat armed yet. 60s covers slow cold starts while still
    # bounding the wait.
    CONNECT_TIMEOUT = 60.0

    def __init__(self, opencode_cmd: list[str] | None = None):
        self.varonika_client = VaronikaClient()
        self.connection = None  # Agent-side connection for sending requests
        self._cm = None
        self._process = None
        self._stderr_task = None
        self._watcher_task = None
        self._reconnect_task = None
        self._heartbeat_task = None
        self._stopping = False
        # True once the connection is known to be dead (teardown done). The
        # background loop keeps retrying until the agent is back or the app
        # stops.
        self._disconnected = False
        # Monotonic connect generation. Watchers capture the generation they
        # watch; a stale watcher from a previous connection can never tear
        # down a newer one.
        self._epoch = 0
        self._cwd = None
        self._connect_lock = asyncio.Lock()
        # callback(message: str, connected: bool): fired on every connect,
        # disconnect and reconnect so the UI message is never stale.
        self.on_status_change = None
        # Overridable for tests; defaults to the real opencode CLI.
        if opencode_cmd is not None:
            self._opencode_cmd = list(opencode_cmd)
            self._exe_resolved = True
        else:
            import shutil
            exe = shutil.which("opencode")
            self._opencode_cmd = ([exe, "acp"] if exe else ["opencode", "acp"])
            self._exe_resolved = exe is not None
        self.session_id = None
        self._model = None
        # Serializes prompts/resets: two concurrent requests on one session
        # would corrupt the accumulated stream and confuse the agent.
        self._prompt_lock = asyncio.Lock()
        # Sequence of the request whose prompt is currently streaming. Set
        # right before a prompt is sent; streamed chunks that arrive while a
        # NEWER request has already started belong to a cancelled answer
        # (the ACP server keeps streaming until the old prompt completes),
        # and the manager uses this to drop them.
        self._stream_seq = None

    async def get_current_model(self) -> str:
        """Fetches the currently configured OpenCode model (cached after first lookup)."""
        if self._model:
            return self._model
        import json, shutil
        opencode_exe = shutil.which("opencode") or "opencode"
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                opencode_exe, "debug", "config",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            # A wedged opencode CLI must not stall startup (or the model line
            # after a session reset) forever: give it 10 seconds, then kill
            # it and report the model as unknown.
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode == 0:
                config = json.loads(stdout.decode('utf-8'))
                self._model = config.get("model", "default")
                return self._model
            return "unknown"
        except Exception as e:
            print(f"Warning: Failed to get current model: {e}")
            return "unknown"
        finally:
            if proc is not None and proc.returncode is None:
                try:
                    proc.kill()
                    # Process the exit event (and pipe cleanup) while the
                    # loop is alive, instead of leaving it to transport
                    # finalizers that can run after the loop is closed.
                    await proc.wait()
                except Exception:
                    pass

    async def start(self, cwd: str | None = None):
        """Starts the OpenCode ACP process and connects to it via stdio.

        The working directory is anchored to the project root (where
        AGENTS.md lives): OpenCode loads it from there. A relative cwd
        like "." would resolve against wherever the app happened to be
        launched from (e.g. a desktop shortcut), silently losing the
        agent instructions.
        """
        self._cwd = str(Path(cwd).resolve()) if cwd else str(BASE_DIR)
        if self.is_connected():
            return
        if not self._exe_resolved:
            raise RuntimeError(
                "opencode not found on PATH. Install it with 'npm install -g opencode-ai', "
                "then close and reopen the terminal before starting Varonika."
            )
        async with self._connect_lock:
            if self.is_connected():
                return
            try:
                await self._connect_once()
            except Exception as e:
                print(f"Failed to start OpenCode ACP server: {e}")
                raise

    async def ensure_connected(self) -> bool:
        """Makes sure a live connection with a session exists; connects if not.

        Returns False (without raising) when the agent cannot be reached.
        Concurrent callers share one connect attempt through _connect_lock,
        and a failed attempt hands retrying over to the background loop.
        """
        if self.is_connected():
            return True
        async with self._connect_lock:
            if self.is_connected():
                return True
            try:
                await self._connect_once()
                return True
            except Exception as e:
                print(f"OpenCode connect failed: {e}")
                self._disconnected = True
                self._schedule_reconnect()
                return False

    def is_connected(self) -> bool:
        """True while a live connection with a session exists."""
        return (self.connection is not None and self.session_id is not None
                and not self._disconnected)

    def is_disconnected(self) -> bool:
        """True after a connection loss, until a reconnect succeeds."""
        return self._disconnected

    async def _connect_once(self):
        """Spawn the ACP process, create a session, arm the watcher, report status."""
        await self._spawn_and_connect()
        self._disconnected = False
        self._watcher_task = asyncio.ensure_future(self._watch())
        if self._heartbeat_task is None or self._heartbeat_task.done():
            self._heartbeat_task = asyncio.ensure_future(self._heartbeat_loop())
        model = await self.get_current_model()
        if model in ("unknown", "default", "", None):
            message = (
                "OpenCode connected, but no model is configured.\n"
                "Run 'opencode' in a terminal and use /connect to add a model."
            )
        else:
            message = f"OpenCode connected.\nSession: {self.session_id}\nModel: {model}"
        print(f"OpenCode session created: {self.session_id} (Model: {model})")
        self._emit_status(message, connected=True)

    async def _spawn_and_connect(self):
        """Start the ACP subprocess and the agent-side connection, then create a session."""
        # ensure_connected() can legally run before start() (the manager
        # gate may fire while the app is still starting): anchor to the
        # project root instead of crashing on a None cwd.
        cwd = self._cwd or str(BASE_DIR)
        cm = None
        try:
            cm = spawn_agent_process(
                self.varonika_client, *self._opencode_cmd, "--cwd", cwd,
                transport_kwargs={"limit": self.TRANSPORT_LIMIT},
            )
            connection, process = await cm.__aenter__()
        except Exception:
            # Never leave a half-started process behind after a failed start.
            if cm is not None:
                try:
                    await asyncio.wait_for(cm.__aexit__(None, None, None), timeout=5)
                except Exception:
                    pass
            raise
        self._cm = cm
        self._process = process
        self.connection = connection
        self.varonika_client.connection = connection
        # A chatty agent must never fill the stderr pipe and wedge itself.
        self._stderr_task = asyncio.ensure_future(self._drain_stderr(process.stderr))
        try:
            # A server that never answers session/new must not block the
            # connect path forever: no watcher or heartbeat is armed yet.
            resp = await asyncio.wait_for(
                connection.new_session(cwd=cwd), timeout=self.CONNECT_TIMEOUT
            )
            self.session_id = resp.session_id
            self.varonika_client.session_id = resp.session_id
        except Exception:
            await self._teardown_current()
            raise

    async def _drain_stderr(self, stderr):
        """Drain the agent's stderr so it can never block on a full pipe. Logged for diagnostics."""
        try:
            while True:
                line = await stderr.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(f"[opencode] {text}")
        except (asyncio.CancelledError, Exception):
            pass

    async def _watch(self):
        """Monitors the OpenCode process.

        When the process dies (crash, kill, system sleep), the connection
        is torn down and a reconnect is scheduled. This is the detection
        half of the fix for prompts that used to hang forever with no
        answer and a stale "connected" message.

        A pipe closed while the process stays alive is NOT detected here:
        on Windows the Proactor loop never delivers EOF for a broken
        subprocess pipe (readline hangs, at_eof() never flips), so that
        case is caught by the probe in prompt() and by the background
        heartbeat instead.
        """
        process = self._process
        epoch = self._epoch
        if process is None:
            return
        try:
            code = await process.wait()
        except (asyncio.CancelledError, Exception):
            return
        if not self._stopping:
            await self._handle_disconnect(f"OpenCode process exited (code {code}).", epoch)

    async def _heartbeat_loop(self):
        """Periodically probes a quiet connection.

        A connection whose pipe broke while idle would otherwise sit with
        a stale "connected" message until the next prompt. The heartbeat
        detects it within HEARTBEAT_INTERVAL and hands it to the
        reconnect machinery before the user speaks.
        """
        while not self._stopping:
            await asyncio.sleep(self.HEARTBEAT_INTERVAL)
            if self._stopping or not self.is_connected():
                continue
            if not await self._probe():
                await self._handle_disconnect("OpenCode heartbeat probe failed.")

    async def _handle_disconnect(self, reason: str, epoch: int | None = None):
        """Idempotent teardown after a connection loss; schedules a reconnect.

        Rejects every in-flight request (prompts fail fast instead of
        hanging) and reports the loss so the stale "connected" UI message
        is revoked immediately.
        """
        if self._stopping or self._disconnected:
            return
        if epoch is not None and epoch != self._epoch:
            return
        self._disconnected = True
        self._epoch += 1
        print(f"OpenCode disconnected: {reason}")
        self._emit_status("OpenCode lost its connection. Reconnecting...", connected=False)
        await self._teardown_current()
        self._schedule_reconnect()

    def _schedule_reconnect(self):
        if self._reconnect_task is not None and not self._reconnect_task.done():
            return
        self._reconnect_task = asyncio.ensure_future(self._reconnect_loop())

    async def _reconnect_loop(self):
        """Keep retrying with backoff until the agent is back or the app stops."""
        delay = self.RECONNECT_BASE_DELAY
        while not self._stopping and self._disconnected:
            await asyncio.sleep(delay)
            if self._stopping or not self._disconnected:
                return
            async with self._connect_lock:
                if self.is_connected() or not self._disconnected:
                    return
                try:
                    await self._connect_once()
                    print("OpenCode reconnected.")
                    return
                except Exception as e:
                    print(f"OpenCode reconnect attempt failed: {e}")
            delay = min(delay * 2, self.RECONNECT_MAX_DELAY)

    async def reset_session(self, cwd: str | None = None):
        """Creates a new fresh session and swaps the current context."""
        if not await self.ensure_connected():
            raise RuntimeError("OpenCode not connected")
        cwd = str(Path(cwd).resolve()) if cwd else str(BASE_DIR)
        async with self._prompt_lock:
            if not self.is_connected():
                raise RuntimeError("OpenCode not connected")
            # Try to close old session gracefully if possible
            if self.session_id:
                try:
                    await asyncio.wait_for(
                        self.connection.close_session(session_id=self.session_id),
                        timeout=self.PROBE_TIMEOUT,
                    )
                except Exception:
                    pass

            try:
                resp = await asyncio.wait_for(
                    self.connection.new_session(cwd=cwd),
                    timeout=self.CONNECT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                # The session request never came back: the connection is
                # wedged. Reset it; the next prompt reconnects automatically.
                await self._handle_disconnect("OpenCode did not respond in time.")
                raise RuntimeError("OpenCode did not respond in time; the connection was reset.")
            self.session_id = resp.session_id
            self.varonika_client.session_id = self.session_id
        model = await self.get_current_model()
        print(f"OpenCode session reset. New ID: {self.session_id} (Model: {model})")

    async def prompt(self, text: str, stream_seq=None) -> str:
        """Send a prompt and wait for completion. Streamed chunks arrive via session_update."""
        if not await self.ensure_connected():
            raise RuntimeError("OpenCode not connected")

        async with self._prompt_lock:
            if not self.is_connected():
                raise RuntimeError("OpenCode not connected")
            # Pre-flight liveness probe: a pipe that broke while idle (or a
            # receive loop that died) must be caught BEFORE the prompt is
            # sent, or the prompt would hang until PROMPT_TIMEOUT.
            if not await self._probe():
                await self._handle_disconnect("OpenCode heartbeat probe failed.")
                raise RuntimeError("OpenCode connection lost; the connection was reset.")
            self.varonika_client._accumulated_text = ""
            # Chunks that arrive from this point on belong to this request.
            self._stream_seq = stream_seq
            content = [TextContentBlock(type="text", text=text)]

            try:
                await asyncio.wait_for(
                    self.connection.prompt(
                        prompt=content, session_id=self.session_id
                    ),
                    timeout=self.PROMPT_TIMEOUT,
                )
                return self.varonika_client._accumulated_text
            except asyncio.TimeoutError:
                # The agent stopped answering (dead receive loop, wedged
                # process). Never leave the caller waiting forever: reset
                # the connection; the next prompt reconnects automatically.
                await self._handle_disconnect("OpenCode did not respond in time.")
                raise RuntimeError("OpenCode did not respond in time; the connection was reset.")
            except Exception as e:
                if not await self._probe():
                    await self._handle_disconnect(f"OpenCode request failed: {e}")
                    raise RuntimeError(f"OpenCode connection lost: {e}") from e
                raise

    async def _probe(self) -> bool:
        """Cheap liveness probe: any response (even an error) within a few
        seconds proves the receive loop is alive."""
        if self.connection is None or self._disconnected or not self.session_id:
            return False
        try:
            await asyncio.wait_for(
                self.connection.list_sessions(),
                timeout=self.PROBE_TIMEOUT,
            )
        except asyncio.TimeoutError:
            return False
        except Exception:
            pass  # an error response still means the loop answered
        return self.is_connected()

    def _emit_status(self, message: str, connected: bool):
        if self.on_status_change:
            try:
                self.on_status_change(message, connected)
            except Exception:
                pass

    async def cancel(self):
        """Cancel the current request (best effort; a notification, not a request)."""
        if self.connection and self.session_id and not self._disconnected:
            try:
                await self.connection.cancel(session_id=self.session_id)
            except Exception:
                pass

    async def stop(self):
        self._stopping = True
        for task in (self._watcher_task, self._reconnect_task, self._heartbeat_task):
            if task is not None:
                task.cancel()
        await self._teardown_current()

    async def _teardown_current(self):
        """Close the connection, kill the process, and clear all state."""
        conn = self.connection
        self.connection = None
        self.varonika_client.connection = None
        self.session_id = None
        self.varonika_client.session_id = None
        if conn is not None:
            try:
                # Sync close; rejects in-flight requests so prompts fail fast.
                result = conn.close()
                if inspect.isawaitable(result):
                    await result
            except Exception:
                pass
        if self._stderr_task is not None:
            self._stderr_task.cancel()
            self._stderr_task = None
        cm = self._cm
        self._cm = None
        self._process = None
        if cm is not None:
            try:
                await asyncio.wait_for(cm.__aexit__(None, None, None), timeout=5)
            except Exception:
                pass
