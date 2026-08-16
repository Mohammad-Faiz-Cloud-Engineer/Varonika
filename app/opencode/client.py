import os
from typing import Any
from acp import spawn_agent_process
from acp.schema import (
    AgentMessageChunk, ToolCallStart,
    PermissionOption, AllowedOutcome, RequestPermissionResponse,
    ReadTextFileResponse,
    CreateTerminalResponse, TerminalOutputResponse,
    ReleaseTerminalResponse, WaitForTerminalExitResponse,
    KillTerminalResponse, WriteTextFileResponse,
    TextContentBlock, ToolCallUpdate,
)


class VaronikaClient:
    """
    Implements the ACP Client protocol — handles callbacks FROM OpenCode.
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
        """Always approve — permissions are auto-approved by OpenCode."""
        allow_id = next((o.option_id for o in options if o.kind.startswith("allow")), options[0].option_id)
        return RequestPermissionResponse(outcome=AllowedOutcome(outcome="selected", option_id=allow_id))

    async def read_text_file(self, path: str, session_id: str, **kwargs: Any) -> ReadTextFileResponse:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read(kwargs.get("limit", None))
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
            return None

    async def create_terminal(self, command: str, session_id: str, **kwargs: Any) -> CreateTerminalResponse:
        return CreateTerminalResponse(terminal_id="not-supported")

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> TerminalOutputResponse:
        return TerminalOutputResponse(output="", truncated=False)

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> ReleaseTerminalResponse | None:
        return None

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> WaitForTerminalExitResponse:
        return WaitForTerminalExitResponse(exit_status=0)

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> KillTerminalResponse | None:
        return None

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

    async def start(self, cwd: str = "."):
        """Starts the OpenCode ACP process and connects to it via stdio."""
        print("Starting OpenCode ACP server...")
        import shutil
        opencode_exe = shutil.which("opencode") or "opencode"
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
        print(f"OpenCode session created: {self.session_id}")

    async def reset_session(self, cwd: str = "."):
        """Creates a new fresh session and swaps the current context."""
        if not self.connection:
            raise RuntimeError("OpenCode not connected")
        # Try to close old session gracefully if possible
        if self.session_id:
            try:
                await self.connection.close_session(session_id=self.session_id)
            except Exception:
                pass
                
        resp = await self.connection.new_session(cwd=cwd)
        self.session_id = resp.session_id
        self.varonika_client.session_id = self.session_id
        print(f"OpenCode session reset. New ID: {self.session_id}")

    async def prompt(self, text: str) -> str:
        """Send a prompt and wait for completion. Streamed chunks arrive via session_update."""
        if not self.connection or not self.session_id:
            raise RuntimeError("OpenCode not connected")

        self.varonika_client._accumulated_text = ""
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
