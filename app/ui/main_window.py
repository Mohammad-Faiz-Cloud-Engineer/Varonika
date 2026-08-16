from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QLabel, QSystemTrayIcon, QMenu, QApplication
)
from PySide6.QtGui import QAction, QTextCursor
from PySide6.QtCore import Signal
from app.ui.ultron_brain import UltronBrain
from app.conversation.state import AppState


class MainWindow(QMainWindow):
    ui_signal = Signal(str, str)
    state_signal = Signal(object)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("Varonika")
        self.resize(900, 550)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Left panel (Brain)
        self.brain = UltronBrain()
        layout.addWidget(self.brain, stretch=1)

        # Right panel (Chat & Status)
        right_panel = QWidget()
        right_panel.setStyleSheet("background-color: #1a1a2e;")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)

        self.status_label = QLabel("Status: LISTENING_FOR_WAKEWORD")
        self.status_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 13px; "
            "padding: 6px; background: #0f0f23; border-radius: 4px;"
        )
        right_layout.addWidget(self.status_label)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        self.chat_view.setStyleSheet(
            "background-color: #0f0f23; color: #e0e0e0; font-size: 14px; "
            "font-family: 'Segoe UI', sans-serif; border: none; padding: 8px;"
        )
        right_layout.addWidget(self.chat_view)

        layout.addWidget(right_panel, stretch=2)

        # Connect signals (thread-safe)
        self.ui_signal.connect(self._on_ui_message)
        self.state_signal.connect(self._on_state_change)

        # Register callbacks
        self.manager.set_ui_callback(self._thread_safe_emit)
        self.manager.state.add_listener(self._thread_safe_state)

        # Track streaming state
        self._streaming = False

        # System Tray
        self.tray = QSystemTrayIcon(self)
        from PySide6.QtWidgets import QStyle
        icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.tray.setIcon(icon)

        tray_menu = QMenu()
        show_action = QAction("Open Varonika", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close_app)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        # Window style
        self.setStyleSheet("background-color: #16213e;")

    def _thread_safe_emit(self, source, message):
        self.ui_signal.emit(source, message)

    def _thread_safe_state(self, old_state, new_state):
        self.state_signal.emit(new_state)

    def _on_ui_message(self, source, message):
        if source == "Varonika_stream":
            # Streaming chunk — append without newline
            if not self._streaming:
                self._streaming = True
                self.chat_view.append(
                    '<span style="color:#4ec9b0; font-weight:bold;">Varonika:</span> '
                )
            cursor = self.chat_view.textCursor()
            cursor.movePosition(QTextCursor.MoveOperation.End)
            cursor.insertText(message)
            self.chat_view.setTextCursor(cursor)
        elif source == "Varonika":
            # Final full response — end streaming block, or show the text if nothing was streamed
            if self._streaming:
                self._streaming = False
                self.chat_view.append("")  # newline
            elif message:
                self.chat_view.append(
                    f'<span style="color:#4ec9b0; font-weight:bold;">Varonika:</span> {message}'
                )
        elif source == "User":
            self._streaming = False
            self.chat_view.append(
                f'<span style="color:#569cd6; font-weight:bold;">You:</span> {message}'
            )
        elif source == "System":
            self.chat_view.append(
                f'<span style="color:#888;">{message}</span>'
            )

        # Auto-scroll
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_state_change(self, state):
        state_colors = {
            AppState.LISTENING_FOR_WAKEWORD: "#888",
            AppState.WAKEWORD_DETECTED: "#00ffff",
            AppState.LISTENING: "#00ff66",
            AppState.TRANSCRIBING: "#ff9900",
            AppState.THINKING: "#cc66ff",
            AppState.EXECUTING_TOOL: "#ff6600",
            AppState.SPEAKING: "#00ccff",
            AppState.INTERRUPTED: "#ff4444",
            AppState.ERROR: "#ff0000",
            AppState.IDLE: "#555",
        }
        color = state_colors.get(state, "#888")
        self.status_label.setText(f"Status: {state.name}")
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 13px; "
            f"padding: 6px; background: #0f0f23; border-radius: 4px;"
        )
        self.brain.set_state(state)

    def closeEvent(self, event):
        event.ignore()
        self.hide()
        self.tray.showMessage("Varonika", "Varonika is running in the background.")

    def close_app(self):
        self.manager.stop()
        QApplication.quit()
