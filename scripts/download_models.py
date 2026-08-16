import hashlib
import shutil
import sys
import urllib.request
from pathlib import Path

# SHA-256 pins for every model this script can download.
#
# WHISPER_SHA256: published on the Hugging Face blob page for
# ggerganov/whisper.cpp/ggml-small.en.bin and cross-verified against the
# downloaded artifact.
# WAKE_WORD_SHA256: computed from a fresh download of the GitHub release
# asset, size-matched against the release metadata
# (openWakeWord v0.5.1, hey_jarvis_v0.1.onnx, 1,271,370 bytes).
# If an upstream replaces an artifact, this pin fails loudly instead of
# silently loading a changed or tampered model.
WHISPER_SHA256 = "c6138d6d58ecc8322097e0f987c32f1be8bb0a18532a3f88f734d1bbf9c41e5d"
WAKE_WORD_SHA256 = "94a13cfe60075b132f6a472e7e462e8123ee70861bc3fb58434a73712ee0d2cb"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def download_file(url, destination, expected_sha256, label):
    print(f"Downloading {url} to {destination}...")

    # We use a progress bar
    def reporthook(count, block_size, total_size):
        if total_size > 0:
            progress = int(count * block_size * 100 / total_size)
            sys.stdout.write(f"\rDownloading... {progress}%")
            sys.stdout.flush()

    # Download to a .part file first so a dropped connection can never
    # leave a truncated model where the app expects a complete one.
    part = destination.with_suffix(destination.suffix + ".part")
    try:
        urllib.request.urlretrieve(url, part, reporthook=reporthook)
        if sha256_file(part) != expected_sha256:
            print(f"\nIntegrity check FAILED for {label}: the downloaded file does not match its pinned sha256. Refusing to use it.")
            part.unlink(missing_ok=True)
            return False
        part.replace(destination)
        print(f"\n{label} downloaded and verified (sha256 ok).")
        return True
    except Exception as e:
        print(f"\nFailed to download {url}: {e}")
        part.unlink(missing_ok=True)
        return False

def verify_or_download(url, destination, expected_sha256, label):
    """Verify an existing model against its pinned hash, or fetch a new one."""
    if destination.exists():
        if sha256_file(destination) == expected_sha256:
            print(f"{label} verified (sha256 ok).")
            return True
        print(f"{label} FAILED verification (hash mismatch). Deleting and re-downloading...")
        try:
            destination.unlink()
        except OSError as e:
            print(f"Could not remove corrupt {destination}: {e}")
            return False
    return download_file(url, destination, expected_sha256, label)

def main():
    base_dir = Path(__file__).parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)

    ok = True

    # Whisper Model
    whisper_model = models_dir / "ggml-small.en.bin"
    whisper_url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
    ok &= verify_or_download(whisper_url, whisper_model, WHISPER_SHA256, "Whisper model")

    # OpenWakeWord Model: prefer the custom 'Hey Varonika' model if present
    # at the project root, otherwise fetch the pinned placeholder so the
    # system can still boot (says 'Hey Jarvis' instead).
    wakeword_model = models_dir / "wakeword.onnx"
    custom_model = base_dir / "Hey_Varonika.onnx"
    if custom_model.exists():
        try:
            if not wakeword_model.exists() or sha256_file(wakeword_model) != sha256_file(custom_model):
                shutil.copy(custom_model, wakeword_model)
                print("Copied custom 'Hey Varonika' wake word model.")
            else:
                print("Custom 'Hey Varonika' wake word model already in place.")
        except OSError as e:
            print(f"Failed to copy custom wake word model: {e}")
            ok = False
    else:
        wakeword_url = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx"
        if verify_or_download(wakeword_url, wakeword_model, WAKE_WORD_SHA256, "Wake word model"):
            print("NOTE: Using 'hey_jarvis' as a placeholder for 'Hey Varonika'. You must say 'Hey Jarvis' to trigger unless a custom model is provided.")
        else:
            ok = False

    if not ok:
        print("Model setup failed. The app will not start with unverified models.")
        sys.exit(1)

if __name__ == "__main__":
    main()