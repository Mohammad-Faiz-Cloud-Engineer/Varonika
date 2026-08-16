import urllib.request
import shutil
import sys
from pathlib import Path

def download_file(url, destination):
    print(f"Downloading {url} to {destination}...")
    
    # We use a progress bar
    def reporthook(count, block_size, total_size):
        if total_size > 0:
            progress = int(count * block_size * 100 / total_size)
            sys.stdout.write(f"\rDownloading... {progress}%")
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, destination, reporthook=reporthook)
        print("\nDownload complete.")
    except Exception as e:
        print(f"\nFailed to download {url}: {e}")

def main():
    base_dir = Path(__file__).parent.parent
    models_dir = base_dir / "models"
    models_dir.mkdir(exist_ok=True)
    
    # Download Whisper Model
    whisper_model = models_dir / "ggml-small.en.bin"
    if not whisper_model.exists():
        whisper_url = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-small.en.bin"
        download_file(whisper_url, whisper_model)
    else:
        print("Whisper model already exists.")

    # Download OpenWakeWord Model — prefer the custom 'Hey Varonika' model
    # if present at the project root, otherwise fetch a placeholder so the
    # system can still boot (says 'Hey Jarvis' instead).
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
    elif not wakeword_model.exists():
        # URL for a pre-trained openwakeword model just to ensure we have a valid ONNX file
        wakeword_url = "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx"
        download_file(wakeword_url, wakeword_model)
        print("NOTE: Downloaded 'hey_jarvis' as a placeholder for 'Hey Varonika'. You must say 'Hey Jarvis' to trigger unless a custom model is provided.")
    else:
        print("Wakeword model already exists.")

if __name__ == "__main__":
    main()
