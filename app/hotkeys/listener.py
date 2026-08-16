import keyboard
from app.conversation.state import StateManager, AppState

class HotkeyListener:
    def __init__(self, state_manager: StateManager, manager, activate_key="alt+space"):
        self.state_manager = state_manager
        self.manager = manager
        self.activate_key = activate_key

    def start(self):
        keyboard.add_hotkey(self.activate_key, self._on_activate)
        print(f"Hotkeys registered: {self.activate_key} to activate.")

    def _on_activate(self):
        print("Hotkey pressed: Activating voice input.")
        current = self.state_manager.current
        if current in [AppState.LISTENING_FOR_WAKEWORD, AppState.SPEAKING, AppState.IDLE]:
            if current == AppState.SPEAKING:
                self.manager.interrupt()
            self.manager.activate_listening()
        elif current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            print("Hotkey pressed: Interrupting current task.")
            self.manager.interrupt()
