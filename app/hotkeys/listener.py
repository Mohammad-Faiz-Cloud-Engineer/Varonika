import keyboard
from app.conversation.state import AppState

class HotkeyListener:
    def __init__(self, manager, activate_key="alt+space"):
        self.manager = manager
        self.activate_key = activate_key
        self._hotkey = None

    def start(self):
        self._hotkey = keyboard.add_hotkey(self.activate_key, self._on_activate)
        print(f"Hotkeys registered: {self.activate_key} to activate.")

    def _on_activate(self):
        # Dispatch to the main event loop for thread safety
        if self.manager._loop and not self.manager._loop.is_closed():
            self.manager._loop.call_soon_threadsafe(self._handle_activate)

    def _handle_activate(self):
        print("Hotkey pressed: Activating voice input.")
        current = self.manager.state.current
        if current in [AppState.LISTENING_FOR_WAKEWORD, AppState.SPEAKING, AppState.IDLE]:
            if current == AppState.SPEAKING:
                self.manager.interrupt()
            self.manager.activate_listening()
        elif current == AppState.TRANSCRIBING:
            print("Hotkey pressed: Cancelling in-flight transcription.")
            self.manager.activate_listening()
        elif current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            print("Hotkey pressed: Interrupting current task.")
            self.manager.interrupt()

    def stop(self):
        if self._hotkey is not None:
            try:
                keyboard.remove_hotkey(self._hotkey)
            except Exception:
                keyboard.unhook_all()
