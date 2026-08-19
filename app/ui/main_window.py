import html
import threading
import time
from pathlib import Path
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QTextEdit, QLabel, QSystemTrayIcon, QMenu, QApplication, QComboBox, QSlider
)
from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtGui import QAction, QIcon, QTextCursor, QTextDocument, QTextDocumentFragment, QTextBlockFormat
import qasync
from app.ui.ultron_brain import UltronBrain
from app.conversation.state import AppState
from app.config.settings import save_config_field
from app.formatting import latex_to_text

ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"


def load_app_icon() -> QIcon:
    """Build the app icon from the logo assets.

    The multi-size .ico is preferred on Windows (taskbar + tray need small
    sizes); the high-res .png covers Linux and macOS. Both are added to one
    QIcon so Qt picks the best match per platform. Returns a null icon if no
    logo files exist, so callers can fall back.
    """
    icon = QIcon()
    for name in ("logo.ico", "logo.png"):
        path = ASSETS_DIR / name
        if path.exists():
            icon.addFile(str(path))
    return icon


class MainWindow(QMainWindow):
    ui_signal = Signal(str, str)
    state_signal = Signal(object)
    # Delivered from the background mic refresh thread (queued to the UI thread)
    mic_refresh_ready = Signal(list)

    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.setWindowTitle("Varonika")
        self.resize(900, 550)

        # Central widget
        central = QWidget()
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        # A little breathing room around the two cards so the rounded
        # corners read as separate panels against the window background.
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # Left panel (Brain)
        self.brain = UltronBrain()
        layout.addWidget(self.brain, stretch=1)

        # Right panel (Chat & Status)
        right_panel = QWidget()
        right_panel.setStyleSheet(
            "background-color: #1a1a2e; border-radius: 16px; "
            "border: 1px solid #2a2a4a;"
        )
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 12, 12, 12)

        # Mic selector: pick the microphone the wake word and STT listen
        # on (e.g. the headset used in TeamSpeak), not the laptop mic.
        mic_row = QWidget()
        mic_layout = QHBoxLayout(mic_row)
        mic_layout.setContentsMargins(0, 0, 0, 0)
        mic_label = QLabel("Mic:")
        mic_label.setStyleSheet("color: #888; font-size: 12px;")
        self.mic_combo = QComboBox()
        self.mic_combo.setStyleSheet(
            "color: #e0e0e0; font-size: 12px; background: #0f0f23; "
            "border: 1px solid #2a2a4a; border-radius: 8px; padding: 3px;"
        )
        mic_layout.addWidget(mic_label)
        mic_layout.addWidget(self.mic_combo, stretch=1)
        right_layout.addWidget(mic_row)

        self.mic_in_use_label = QLabel("Mic in use: -")
        self.mic_in_use_label.setStyleSheet(
            "color: #00d4ff; font-size: 11px; padding: 0 0 6px 0;"
        )
        right_layout.addWidget(self.mic_in_use_label)

        # TTS volume boost: she speaks too quietly on some setups even with
        # the system volume maxed, so boost the audio itself, not the OS.
        vol_row = QWidget()
        vol_layout = QHBoxLayout(vol_row)
        vol_layout.setContentsMargins(0, 0, 0, 0)
        self.vol_label = QLabel("TTS Vol:")
        self.vol_label.setStyleSheet("color: #888; font-size: 12px;")
        self.vol_slider = QSlider(Qt.Orientation.Horizontal)
        self.vol_slider.setRange(50, 500)
        self._last_vol_save = 0.0
        self.vol_slider.setValue(int(self.manager.config.tts_volume * 100))
        self.vol_slider.setStyleSheet(
            "color: #00d4ff; font-size: 12px; background: #0f0f23;"
            "QSlider::groove:horizontal { height: 6px; border-radius: 3px;"
            " background: #2a2a4a; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px;"
            " margin: -4px 0; border-radius: 7px; background: #00d4ff;"
            " border: 1px solid #0f0f23; }"
        )
        self.vol_value = QLabel(f"{self.vol_slider.value() / 100:.1f}x")
        self.vol_value.setStyleSheet("color: #e0e0e0; font-size: 12px;")
        vol_layout.addWidget(self.vol_label)
        vol_layout.addWidget(self.vol_slider, stretch=1)
        vol_layout.addWidget(self.vol_value)
        right_layout.addWidget(vol_row)
        self.vol_slider.valueChanged.connect(self._on_volume_changed)
        self.vol_slider.sliderReleased.connect(self._persist_volume)

        self.status_label = QLabel("Status: LISTENING_FOR_WAKEWORD")
        self.status_label.setStyleSheet(
            "color: #00d4ff; font-weight: bold; font-size: 13px; "
            "padding: 6px; background: #0f0f23; border-radius: 8px;"
        )
        right_layout.addWidget(self.status_label)

        self.chat_view = QTextEdit()
        self.chat_view.setReadOnly(True)
        # No visible scrollbars: scroll with the mouse wheel or a touchpad
        # gesture, so the chat area keeps its full rounded width.
        self.chat_view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.chat_view.setStyleSheet(
            "background-color: #0f0f23; color: #e0e0e0; font-size: 14px; "
            "font-family: 'Segoe UI', sans-serif; border: 1px solid #2a2a4a; "
            "border-radius: 10px; padding: 8px;"
        )
        right_layout.addWidget(self.chat_view)

        layout.addWidget(right_panel, stretch=2)

        # Connect signals (thread-safe)
        self.ui_signal.connect(self._on_ui_message)
        self.state_signal.connect(self._on_state_change)

        # Register callbacks
        self.manager.set_ui_callback(self._thread_safe_emit)
        self.manager.state.add_listener(self._thread_safe_state)

        # Track streaming state (cursor range of the streamed text)
        self._stream_start = None
        self._stream_end = None

        self._populate_mic_devices()
        self.mic_combo.currentTextChanged.connect(self._on_mic_changed)

        # Bluetooth headsets connect and disconnect at any time: refresh the
        # mic list in the background so new/removed mics appear without a
        # restart. The availability probe opens devices, so it must never run
        # on the UI thread.
        self.mic_refresh_ready.connect(self._apply_mic_refresh)
        self._mic_refresh_stop = threading.Event()
        self._mic_refresh_thread = threading.Thread(
            target=self._mic_refresh_loop, daemon=True
        )
        self._mic_refresh_thread.start()

        # Window + tray icon (Varonika logo; falls back to a stock icon
        # if the logo files are missing)
        app_icon = load_app_icon()
        if app_icon.isNull():
            from PySide6.QtWidgets import QStyle
            app_icon = QApplication.style().standardIcon(QStyle.StandardPixmap.SP_ComputerIcon)
        self.setWindowIcon(app_icon)
        self.tray = QSystemTrayIcon(app_icon, self)

        tray_menu = QMenu()
        show_action = QAction("Open Varonika", self)
        show_action.triggered.connect(self.showNormal)
        quit_action = QAction("Quit", self)
        quit_action.triggered.connect(self.close_app)
        tray_menu.addAction(show_action)
        tray_menu.addAction(quit_action)
        self.tray.setContextMenu(tray_menu)
        self.tray.show()

        # Window style: a deep background so the two rounded cards stand out
        self.setStyleSheet("background-color: #0d1023;")

    def _thread_safe_emit(self, source, message):
        self.ui_signal.emit(source, message)

    def _mic_refresh_loop(self):
        while not self._mic_refresh_stop.is_set():
            time.sleep(10)
            if self._mic_refresh_stop.is_set():
                break
            try:
                devices = self.manager.audio.list_input_devices()
            except Exception:
                continue
            self.mic_refresh_ready.emit(devices)

    def _apply_mic_refresh(self, devices):
        # Never rebuild the list under an open menu
        if self.mic_combo.view().isVisible():
            return
        # Index 0 is the synthetic "System Default" item; compare only the
        # real device entries
        current = [self.mic_combo.itemData(i) for i in range(1, self.mic_combo.count())]
        new = [data for _, data in devices]
        if current != new:
            self._populate_mic_devices(devices)
        else:
            # The device list is unchanged, but the stream may have fallen
            # back to the system default: keep the combo showing the truth.
            self.sync_mic_combo()
            self._update_mic_in_use()
        # The live stream died (e.g. Bluetooth link dropped): fall back to
        # the system default so capture recovers. Do not treat "probe could
        # not open a second handle on the busy live mic" as a dropout; that
        # would tear down a working stream every ~10 s.
        if self.manager.audio.device_name and not self.manager.audio.stream_is_healthy():
            self.manager.set_mic_device("", persist=False)
            self.sync_mic_combo()
            self._update_mic_in_use()
        # Every mic failed to open (e.g. the headset powered off mid-switch):
        # retry the system default on the next refresh so a recovered mic is
        # picked up without restarting the app.
        if self.manager.audio.active_device == "Unavailable":
            self.manager.set_mic_device("", persist=False)
            self.sync_mic_combo()
            self._update_mic_in_use()

    def _display_device(self):
        """Name of the microphone the app listens on (or is about to use).
        Before the stream opens show the requested device; when every mic
        failed to open, show 'Unavailable' instead of claiming a mic."""
        audio = self.manager.audio
        if audio.stream is not None:
            return audio.active_device
        if audio.active_device == "Unavailable":
            return "Unavailable"
        return audio.device_name or audio.active_device

    def sync_mic_combo(self):
        """Show the microphone the capture actually uses: the open stream's
        device, or the requested device before the stream has opened."""
        active = self._display_device()
        combo_idx = self.mic_combo.findData(active)
        if combo_idx < 0:
            combo_idx = 0  # "System Default"
        with QSignalBlocker(self.mic_combo):
            self.mic_combo.setCurrentIndex(combo_idx)

    def _populate_mic_devices(self, devices=None):
        if devices is None:
            try:
                devices = self.manager.audio.list_input_devices()
            except Exception as e:
                print(f"Mic enumeration failed: {e}")
                return
        try:
            default_name = self.manager.audio.p.get_default_input_device_info()["name"]
        except Exception:
            default_name = None
        with QSignalBlocker(self.mic_combo):
            self.mic_combo.clear()
            self.mic_combo.addItem("System Default", "")
            key = self.manager.audio._dedupe_key
            for idx, name in devices:
                label = name + ("  (Default)" if default_name is not None and key(name) == key(default_name) else "")
                self.mic_combo.addItem(label, name)
        self.sync_mic_combo()
        self._update_mic_in_use()

    def _update_mic_in_use(self):
        self.mic_in_use_label.setText(f"Mic in use: {self._display_device()}")

    def _on_mic_changed(self, _text):
        name = self.mic_combo.currentData() or ""
        try:
            self.manager.set_mic_device(name)
        except Exception as e:
            print(f"Mic switch failed: {e}")
        self.sync_mic_combo()
        self._update_mic_in_use()

    def _on_volume_changed(self, value):
        boost = value / 100.0
        self.vol_value.setText(f"{boost:.1f}x")
        try:
            self.manager.tts.set_volume(boost)
        except Exception as e:
            print(f"Volume set failed: {e}")
        # Writing config.yaml on every slider tick would hammer the disk:
        # persist at most once per second while dragging, and the release
        # handler below guarantees the final position is always saved.
        now = time.monotonic()
        if now - self._last_vol_save >= 1.0:
            self._last_vol_save = now
            self._persist_volume()

    def _persist_volume(self):
        boost = self.vol_slider.value() / 100.0
        self.manager.config.tts_volume = boost
        try:
            save_config_field("tts_volume", boost)
        except Exception as e:
            print(f"Volume save failed: {e}")

    def _thread_safe_state(self, old_state, new_state):
        self.state_signal.emit(new_state)

    def _markdown_fragment(self, text):
        return QTextDocumentFragment.fromMarkdown(
            latex_to_text(text),
            QTextDocument.MarkdownFeature.MarkdownDialectGitHub,
        )

    def _append_chat_block(self, html_text):
        """Append a new chat block at the document end, breaking out of any
        active list. Qt's append() copies the last block's format (including
        list membership), so text appended after a markdown bullet response
        would otherwise keep rendering as bullet points."""
        cursor = self.chat_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not cursor.atBlockStart():
            cursor.insertBlock()
        fmt = QTextBlockFormat()
        fmt.setObjectIndex(-1)
        cursor.setBlockFormat(fmt)
        cursor.insertHtml(html_text)

    def _on_ui_message(self, source, message):
        if source == "Varonika_stream":
            # Streaming chunk: append to the stream block (not document end,
            # so System notes appended mid-stream are never polluted)
            if self._stream_start is None:
                self._append_chat_block(
                    '<span style="color:#4ec9b0; font-weight:bold;">Varonika:</span> '
                )
                cursor = self.chat_view.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self._stream_start = cursor.position()
                self._stream_end = self._stream_start
            cursor = self.chat_view.textCursor()
            cursor.setPosition(self._stream_end)
            cursor.insertText(message)
            self._stream_end = cursor.position()
            self.chat_view.setTextCursor(cursor)
        elif source == "Varonika_stream_reset":
            # Interrupt killed the stream: drop stale cursors so the next
            # answer starts a fresh block at the document end.
            self._stream_start = None
            self._stream_end = None
        elif source == "Varonika":
            # Final full response: replace the streamed text with rendered Markdown,
            # or append the text if nothing was streamed
            if self._stream_start is not None:
                cursor = self.chat_view.textCursor()
                cursor.setPosition(self._stream_start)
                cursor.setPosition(self._stream_end, QTextCursor.MoveMode.KeepAnchor)
                cursor.removeSelectedText()
                if message:
                    cursor.insertFragment(self._markdown_fragment(message))
                self._stream_start = None
                self._stream_end = None
            elif message:
                self._append_chat_block(
                    '<span style="color:#4ec9b0; font-weight:bold;">Varonika:</span> '
                )
                cursor = self.chat_view.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                cursor.insertFragment(self._markdown_fragment(message))
        elif source == "User":
            self._stream_start = None
            self._stream_end = None
            self._append_chat_block(
                f'<span style="color:#569cd6; font-weight:bold;">You:</span> {html.escape(message)}'
            )
        elif source == "System":
            self._append_chat_block(
                f'<span style="color:#888;">{html.escape(message)}</span>'
            )

        # Auto-scroll
        sb = self.chat_view.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_state_change(self, state):
        state_colors = {
            AppState.LISTENING_FOR_WAKEWORD: "#888",
            AppState.LISTENING: "#00ff66",
            AppState.TRANSCRIBING: "#ff9900",
            AppState.THINKING: "#cc66ff",
            AppState.EXECUTING_TOOL: "#ff6600",
            AppState.SPEAKING: "#00ccff",
            AppState.ERROR: "#ff0000",
            AppState.IDLE: "#555",
        }
        color = state_colors.get(state, "#888")
        self.status_label.setText(f"Status: {state.name}")
        self.status_label.setStyleSheet(
            f"color: {color}; font-weight: bold; font-size: 13px; "
            f"padding: 6px; background: #0f0f23; border-radius: 8px;"
        )
        self.brain.set_state(state)

    def closeEvent(self, event):
        if getattr(self, '_force_quit', False):
            event.accept()
            return
        event.ignore()
        self.hide()
        self.tray.showMessage("Varonika", "Varonika is running in the background.")

    @qasync.asyncSlot()
    async def close_app(self):
        self._force_quit = True
        self._mic_refresh_stop.set()
        try:
            import asyncio
            await asyncio.wait_for(self.manager.stop_async(), timeout=2.0)
        except Exception:
            pass
        QApplication.quit()
