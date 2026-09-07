import os
import shutil
import sys
import tempfile
import urllib.request
from pathlib import Path
import contextlib
import hashlib

WAKEWORD_RESOURCE_URLS = {
    "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
    "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
}

EXPECTED_HASHES = {
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
    "ggml-small.en.bin": "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d",
    "wakeword.onnx": "e9917c470c2a2b14028162fb5fcb56fd7d87ebedf31a2877820fa518cc22514b",
}

def get_file_hash(path: Path) -> str:
    hash_sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def download_file(url, destination, expected_hash=None):
    print(f"Downloading {url} to {destination}...")
    # A dead or blocked network must fail fast, not hang the app at startup.
    # Use per-request timeout instead of socket.setdefaulttimeout to avoid
    # affecting all sockets in the process.
    # A previously killed download (app closed mid-startup) leaves an orphan
    # .part behind; clean those up so they cannot accumulate on disk.
    for stale in destination.parent.glob(f".{destination.name}.*.part"):
        with contextlib.suppress(OSError):
            stale.unlink()
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
            with open(temp_path, "wb") as f:
                while True:
                    chunk = resp.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        progress = min(100, downloaded * 100 // total)
                        sys.stdout.write(f"\rDownloading... {progress}%")
                        sys.stdout.flush()
        
        if expected_hash:
            actual_hash = get_file_hash(temp_path)
            if actual_hash.lower() != expected_hash.lower():
                raise RuntimeError(f"Hash mismatch for {destination.name}. Expected {expected_hash}, got {actual_hash}")

        os.replace(temp_path, destination)
        print("\nDownload complete.")
    except Exception as e:
        temp_path.unlink(missing_ok=True)
        print(f"\nFailed to download {url}: {e}")
        raise RuntimeError(f"Could not download model from {url}") from e

def _usable(path: Path, expected_hash: str = None) -> bool:
    """True when the file exists and is not empty. A zero-byte file left
    behind by a killed download must be re-downloaded, not treated as a
    valid model (it would load and then fail at runtime)."""
    try:
        if not (path.exists() and path.stat().st_size > 0):
            return False
        if expected_hash:
            return get_file_hash(path).lower() == expected_hash.lower()
        return True
    except OSError:
        return False

def main():
    base_dir = Path(__file__).parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)

    # Download Whisper Model
    whisper_model = models_dir / "ggml-small.en.bin"
    if not _usable(whisper_model, EXPECTED_HASHES.get("ggml-small.en.bin")):
        whisper_url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
        download_file(whisper_url, whisper_model, EXPECTED_HASHES.get("ggml-small.en.bin"))
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
            use_custom = not wakeword_model.exists()
            if not use_custom:
                use_custom = get_file_hash(custom_model) != get_file_hash(wakeword_model)
        except OSError:
            use_custom = False
    if use_custom:
        shutil.copy(custom_model, wakeword_model)
        print("Copied custom 'Hey Varonika' wake word model.")
    elif not _usable(wakeword_model):
        # URL for a pre-trained openwakeword model just to ensure we have a valid ONNX file
        wakeword_url = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx"
        download_file(wakeword_url, wakeword_model, EXPECTED_HASHES.get("wakeword.onnx"))
        print("NOTE: Downloaded 'hey_jarvis' as a placeholder for 'Hey Varonika'. You must say 'Hey Jarvis' to trigger unless a custom model is provided.")
    else:
        print("Wakeword model already exists.")

    for name, url in WAKEWORD_RESOURCE_URLS.items():
        dest = models_dir / name
        expected_hash = EXPECTED_HASHES.get(name)
        if _usable(dest, expected_hash):
            print(f"{name} already exists.")
        else:
            download_file(url, dest, expected_hash)
            print(f"Downloaded missing {name} for wake word.")

if __name__ == "__main__":
    main()
