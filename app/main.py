import asyncio
import contextlib
import os
import subprocess
import sys
import threading

import qasync
from PySide6.QtWidgets import QApplication

# Ensure 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import load_config
from app.conversation.manager import ConversationManager
from app.conversation.state import StateManager
from app.hotkeys.listener import HotkeyListener
from app.ui.main_window import MainWindow, load_app_icon


def check_models(app):
    """Ensure models are downloaded before starting.

    Runs the download script in a background thread so the Qt event loop
    stays responsive and the splash screen can repaint smoothly.
    """
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    dl_script = os.path.join(scripts_dir, "download_models.py")
    if not os.path.exists(dl_script):
        return

    from PySide6.QtWidgets import QSplashScreen
    from PySide6.QtCore import Qt

    app_icon = load_app_icon()
    splash = QSplashScreen(app_icon.pixmap(256, 256) if not app_icon.isNull() else None)
    splash.show()
    splash.showMessage("Checking...", Qt.AlignBottom | Qt.AlignCenter, Qt.white)

    error_holder: list[str] = []
    show_download_msg = [False]  # mutable container for cross-thread flag

    def _run_download():
        import time as _time
        try:
            process = subprocess.Popen([sys.executable, dl_script])
            start_time = _time.time()
            while process.poll() is None:
                _time.sleep(0.1)
                elapsed = _time.time() - start_time
                if 2.0 < elapsed <= 1800:
                    show_download_msg[0] = True
                elif elapsed > 1800:
                    process.kill()
                    error_holder.append("timeout")
                    return
            if process.returncode != 0:
                error_holder.append(f"exit {process.returncode}")
        except Exception as e:
            error_holder.append(str(e))

    dl_thread = threading.Thread(target=_run_download, daemon=True)
    dl_thread.start()

    # Keep the splash alive while the download thread runs.
    # app.processEvents() lets the splash repaint; a 50ms sleep prevents burning CPU.
    import time
    while dl_thread.is_alive():
        if show_download_msg[0]:
            show_download_msg[0] = False
            splash.showMessage(
                "Downloading AI Models (this may take a few minutes)...",
                Qt.AlignBottom | Qt.AlignCenter,
                Qt.white,
            )
        app.processEvents()
        time.sleep(0.05)

    splash.close()

    if error_holder:
        reason = error_holder[0]
        if reason == "timeout":
            print("WARNING: Model download timed out (slow or interrupted connection).")
            print("Run 'python scripts/download_models.py' in a terminal, wait for it to finish, then restart.")
        else:
            print(f"WARNING: Model download failed ({reason}).")
            print("Download the models manually and place them in the models/ folder, then restart.")


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

    check_models(app)

    app_icon = load_app_icon()
    if not app_icon.isNull():
        app.setWindowIcon(app_icon)

    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)

    config = load_config()
    state = StateManager()
    manager = ConversationManager(config, state)

    window = MainWindow(manager)

    hotkeys = HotkeyListener(manager)
    manager.hotkeys = hotkeys
    try:
        hotkeys.start()
    except Exception as e:
        # A blocked global hotkey registration (driver interference, locked
        # session) must not brick startup: the wake word still works.
        print(f"WARNING: Could not register hotkeys ({e}); wake word still works.")

    # Pass the running loop so the manager can schedule coroutines
    manager.start(loop)
    # The mic stream opened inside manager.start(): show the device that
    # actually opened (the configured mic, or the fallback default).
    window.sync_mic_combo()
    window.show()

    try:
        with loop:
            loop.run_forever()
    finally:
        with contextlib.suppress(Exception):
            loop.run_until_complete(manager.stop_async())


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys
        import traceback
        print(f"Fatal crash: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
