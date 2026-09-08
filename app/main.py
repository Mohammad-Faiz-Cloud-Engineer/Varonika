import asyncio
import os
import subprocess
import sys

import qasync
from PySide6.QtWidgets import QApplication

# Ensure 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import load_config
from app.conversation.manager import ConversationManager
from app.conversation.state import StateManager
from app.hotkeys.listener import HotkeyListener
from app.ui.main_window import MainWindow, load_app_icon


def check_models():
    """Ensure models are downloaded before starting."""
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    dl_script = os.path.join(scripts_dir, "download_models.py")
    if os.path.exists(dl_script):
        print("Checking models...")
        try:
            subprocess.run([sys.executable, dl_script], check=True, timeout=1800)
        except subprocess.TimeoutExpired:
            # The Whisper model alone is ~487 MB: on a slow connection the
            # in-app download can exceed any reasonable window. Tell the
            # user to run the script manually (no cap there) instead of
            # silently starting with a broken speech-to-text.
            print("WARNING: Model download timed out (slow or interrupted connection).")
            print("Run 'python scripts/download_models.py' in a terminal, wait for it to finish, then restart.")
        except Exception as e:
            # A failed download (no network, blocked site) must not crash the
            # app or block startup: warn and let the user place the models
            # manually (see README), then start anyway.
            print(f"WARNING: Model download failed ({e}).")
            print("Download the models manually and place them in the models/ folder, then restart.")


def main():
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    check_models()

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)

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

    with loop:
        loop.run_forever()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        import sys
        import traceback
        print(f"Fatal crash: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
