import asyncio
import os
from pathlib import Path
from typing import Any
from app.config.settings import BASE_DIR
from acp import RequestError, spawn_agent_process
from acp.schema import (
    AgentMessageChunk, ToolCallStart,
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
        self.on_tool_start = None       # callback(title, tool_call_id)
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
                self.on_tool_start(update.title or "Tool", update.tool_call_id)

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
    def __init__(self):
        self.varonika_client = VaronikaClient()
        self.connection = None  # Agent-side connection for sending requests
        self._cm = None
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
        cwd = str(Path(cwd).resolve()) if cwd else str(BASE_DIR)
        print("Starting OpenCode ACP server...")
        import shutil
        opencode_exe = shutil.which("opencode") or "opencode"
        try:
            self._cm = spawn_agent_process(
                self.varonika_client, opencode_exe, "acp", "--cwd", cwd,
                transport_kwargs={"limit": 32 * 1024 * 1024},
            )
            self.connection, _ = await self._cm.__aenter__()
            self.varonika_client.connection = self.connection

            # Create a new session
            resp = await self.connection.new_session(cwd=cwd)
            self.session_id = resp.session_id
            self.varonika_client.session_id = self.session_id
            model = await self.get_current_model()
            print(f"OpenCode session created: {self.session_id} (Model: {model})")
        except Exception as e:
            print(f"Failed to start OpenCode ACP server: {e}")
            self._cm = None
            self.connection = None
            raise

    async def reset_session(self, cwd: str | None = None):
        """Creates a new fresh session and swaps the current context."""
        if not self.connection:
            raise RuntimeError("OpenCode not connected")
        cwd = str(Path(cwd).resolve()) if cwd else str(BASE_DIR)
        async with self._prompt_lock:
            # Try to close old session gracefully if possible
            if self.session_id:
                try:
                    await self.connection.close_session(session_id=self.session_id)
                except Exception:
                    pass

            resp = await self.connection.new_session(cwd=cwd)
            self.session_id = resp.session_id
            self.varonika_client.session_id = self.session_id
        model = await self.get_current_model()
        print(f"OpenCode session reset. New ID: {self.session_id} (Model: {model})")

    async def prompt(self, text: str, stream_seq=None) -> str:
        """Send a prompt and wait for completion. Streamed chunks arrive via session_update."""
        if not self.connection or not self.session_id:
            raise RuntimeError("OpenCode not connected")

        async with self._prompt_lock:
            self.varonika_client._accumulated_text = ""
            # Chunks that arrive from this point on belong to this request.
            self._stream_seq = stream_seq
            content = [TextContentBlock(type="text", text=text)]

            resp = await self.connection.prompt(
                prompt=content, session_id=self.session_id
            )
            return self.varonika_client._accumulated_text

    async def cancel(self):
        """Cancel the current request."""
        if self.connection and self.session_id:
            try:
                await self.connection.cancel(session_id=self.session_id)
            except Exception:
                pass

    async def stop(self):
        if self._cm:
            try:
                await self._cm.__aexit__(None, None, None)
            except Exception:
                pass
