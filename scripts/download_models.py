import urllib.request
import shutil
import sys
import os
import tempfile
from pathlib import Path

WAKEWORD_RESOURCE_URLS = {
    "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
    "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
}

def download_file(url, destination):
    print(f"Downloading {url} to {destination}...")
    # A dead or blocked network must fail fast, not hang the app at startup.
    # Use per-request timeout instead of socket.setdefaulttimeout to avoid
    # affecting all sockets in the process.
    # A previously killed download (app closed mid-startup) leaves an orphan
    # .part behind; clean those up so they cannot accumulate on disk.
    for stale in destination.parent.glob(f".{destination.name}.*.part"):
        try:
            stale.unlink()
        except OSError:
            pass
    fd, temp_path = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".part", dir=destination.parent
    )
    os.close(fd)
    temp_path = Path(temp_path)
    
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=60) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            while True:
                chunk = resp.read(8192)
                if not chunk:
                    break
                with open(temp_path, "ab") as f:
                    f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    progress = min(100, downloaded * 100 // total)
                    sys.stdout.write(f"\rDownloading... {progress}%")
                    sys.stdout.flush()
        os.replace(temp_path, destination)
        print("\nDownload complete.")
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        print(f"\nFailed to download {url}: {e}")
        raise RuntimeError(f"Could not download model from {url}") from e

def _usable(path: Path) -> bool:
    """True when the file exists and is not empty. A zero-byte file left
    behind by a killed download must be re-downloaded, not treated as a
    valid model (it would load and then fail at runtime)."""
    try:
        return path.exists() and path.stat().st_size > 0
    except OSError:
        return False

def main():
    base_dir = Path(__file__).parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)
    
    # Download Whisper Model
    whisper_model = models_dir / "ggml-small.en.bin"
    if not _usable(whisper_model):
        whisper_url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
        download_file(whisper_url, whisper_model)
    else:
        print("Whisper model already exists.")

    # Download OpenWakeWord Model: prefer the custom 'Hey Varonika' model
    # if present at the project root, otherwise fetch a 'hey_jarvis'
    # placeholder so the system can still boot. The placeholder requires
    # saying "Hey Jarvis" instead of "Hey Varonika" until a custom model
    # is provided.
    wakeword_model = models_dir / "wakeword.onnx"
    custom_model = base_dir / "Hey_Varonika.onnx"
    use_custom = False
    if custom_model.exists():
        try:
            use_custom = not wakeword_model.exists() or wakeword_model.stat().st_size != custom_model.stat().st_size
        except OSError:
            use_custom = False
    if use_custom:
        shutil.copy(custom_model, wakeword_model)
        print("Copied custom 'Hey Varonika' wake word model.")
    elif not _usable(wakeword_model):
        # URL for a pre-trained openwakeword model just to ensure we have a valid ONNX file
        wakeword_url = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx"
        download_file(wakeword_url, wakeword_model)
        print("NOTE: Downloaded 'hey_jarvis' as a placeholder for 'Hey Varonika'. You must say 'Hey Jarvis' to trigger unless a custom model is provided.")
    else:
        print("Wakeword model already exists.")

    for name, url in WAKEWORD_RESOURCE_URLS.items():
        dest = models_dir / name
        try:
            valid = dest.exists() and dest.stat().st_size > 0
        except OSError:
            valid = False
        if valid:
            print(f"{name} already exists.")
        else:
            download_file(url, dest)
            print(f"Downloaded missing {name} for wake word.")

if __name__ == "__main__":
    main()
