from enum import Enum, auto
import threading

class AppState(Enum):
    IDLE = auto()
    LISTENING_FOR_WAKEWORD = auto()
    WAKEWORD_DETECTED = auto()
    LISTENING = auto()
    TRANSCRIBING = auto()
    THINKING = auto()
    EXECUTING_TOOL = auto()
    SPEAKING = auto()
    INTERRUPTED = auto()
    ERROR = auto()

class StateManager:
    def __init__(self):
        self._state = AppState.LISTENING_FOR_WAKEWORD
        self._listeners = []
        self._lock = threading.Lock()

    @property
    def current(self) -> AppState:
        with self._lock:
            return self._state

    def add_listener(self, callback):
        with self._lock:
            self._listeners.append(callback)

    def remove_listener(self, callback):
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def set_state(self, new_state: AppState):
        with self._lock:
            if self._state == new_state:
                return
            old_state = self._state
            self._state = new_state
            # Snapshot so callbacks run outside the lock (no deadlocks, no stale reads)
            listeners = list(self._listeners)
        for callback in listeners:
            try:
                callback(old_state, new_state)
            except Exception as e:
                print(f"Error in state listener: {e}")
