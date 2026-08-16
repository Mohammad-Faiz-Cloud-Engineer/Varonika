import keyboard
from app.conversation.state import StateManager, AppState

class HotkeyListener:
    def __init__(self, state_manager: StateManager, manager, activate_key="alt+space", toggle_continuous_key="alt+t"):
        self.state_manager = state_manager
        self.manager = manager
        self.activate_key = activate_key
        self.toggle_continuous_key = toggle_continuous_key

    def start(self):
        keyboard.add_hotkey(self.activate_key, self._on_activate)
        keyboard.add_hotkey(self.toggle_continuous_key, self._on_toggle)
        print(f"Hotkeys registered: {self.activate_key} to activate, {self.toggle_continuous_key} to toggle mode.")

    def _on_activate(self):
        print("Hotkey pressed: Activating voice input.")
        current = self.state_manager.current
        if current in [AppState.LISTENING_FOR_WAKEWORD, AppState.SPEAKING, AppState.IDLE]:
            if current == AppState.SPEAKING:
                self.manager.interrupt()
            self.state_manager.set_state(AppState.LISTENING)
            self.manager.stt.reset()
        elif current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            print("Hotkey pressed: Interrupting current task.")
            self.manager.interrupt()

    def _on_toggle(self):
        self.manager.config.continuous_mode = not self.manager.config.continuous_mode
        state = "ON" if self.manager.config.continuous_mode else "OFF"
        print(f"Continuous mode toggled {state}.")
        self.manager._emit_ui("System", f"Continuous Mode: {state}")
