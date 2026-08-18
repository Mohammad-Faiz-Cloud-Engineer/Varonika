import sys
import asyncio
import os
import subprocess
from PySide6.QtWidgets import QApplication
import qasync

# Ensure 'app' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config.settings import load_config
from app.conversation.state import StateManager
from app.conversation.manager import ConversationManager
from app.ui.main_window import MainWindow, load_app_icon
from app.hotkeys.listener import HotkeyListener


def check_models():
    """Ensure models are downloaded before starting."""
    scripts_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
    dl_script = os.path.join(scripts_dir, "download_models.py")
    if os.path.exists(dl_script):
        print("Checking models...")
        subprocess.run([sys.executable, dl_script], check=True)


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
    hotkeys.start()

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
        import traceback
        import sys
        print(f"Fatal crash: {e}", file=sys.stderr)
        traceback.print_exc()
        sys.exit(1)
