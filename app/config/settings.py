import yaml
from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Every Whisper model the app recognizes, from smallest to strongest.
# Files in models/ named ggml-<name>.bin (e.g. ggml-large-v3.bin) are
# detected automatically; when several are present the strongest wins.
WHISPER_MODEL_NAMES = [
    "tiny.en", "tiny",
    "base.en", "base",
    "small.en", "small",
    "medium.en", "medium",
    "large-v1", "large-v2", "large-v3", "large-v3-turbo",
]
DEFAULT_STT_MODEL = "models/ggml-small.bin"
# A real whisper model is always several tens of MB; anything smaller is a
# stray or corrupted file and must not be picked up as "the model".
MIN_WHISPER_MODEL_BYTES = 5 * 1024 * 1024

@dataclass
class Config:
    wake_word_model: str = "models/wakeword.onnx"
    wake_word_threshold: float = 0.6
    stt_model: str = "models/ggml-small.bin"
    stt_language: str = "en"
    silence_timeout_ms: int = 2500
    energy_threshold: float = 0.015
    tts_voice: str = "af_bella"
    # Below 1.0 speaks slower and articulates words more clearly.
    tts_speed: float = 0.9
    # TTS loudness boost, applied to the audio before playback (1.0 = normal,
    # 2.0 = twice as loud). The desktop window has a slider for this too.
    tts_volume: float = 1.0
    follow_up_timeout_ms: int = 2000
    # Microphone for the wake word and STT. Empty = Windows default input
    # device. Set this to the mic you use in TeamSpeak / Discord etc. (e.g.
    # "Headset Microphone") so Varonika listens on that mic instead of the
    # laptop's built-in one.
    mic_device: str = ""

def detect_stt_model(models_dir: Path):
    """Return the strongest Whisper model present in models_dir, or None.

    Any file named ggml-<known>.bin (see WHISPER_MODEL_NAMES) counts, so a
    user can switch STT simply by dropping a model file into the models
    folder. When several are present the strongest (largest) wins; stray
    files below MIN_WHISPER_MODEL_BYTES are ignored.
    """
    if not models_dir.is_dir():
        return None
    best = None
    best_rank = -1
    try:
        for f in models_dir.iterdir():
            if not f.is_file():
                continue
            name = f.name
            if not (name.startswith("ggml-") and name.endswith(".bin")):
                continue
            stem = name[len("ggml-"):-len(".bin")]
            if stem not in WHISPER_MODEL_NAMES:
                continue
            try:
                if f.stat().st_size < MIN_WHISPER_MODEL_BYTES:
                    continue
            except OSError:
                continue
            rank = WHISPER_MODEL_NAMES.index(stem)
            if rank > best_rank:
                best = f
                best_rank = rank
    except OSError:
        return None
    return str(best) if best else None

def _resolve_model_path(path: str) -> str:
    """Anchor relative model paths to the project root regardless of CWD."""
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / p
    return str(p)

def save_config_field(key: str, value) -> bool:
    """Persist one config field to config.yaml, preserving existing keys.

    The app's config file is optional and user-local (gitignored). Runtime
    choices like the selected microphone are written back so they survive a
    restart; without this the app silently falls back to the system default
    mic on every launch. Returns False on failure so callers can warn
    without breaking the live change that already happened.
    """
    config_path = BASE_DIR / "config.yaml"
    try:
        data = {}
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
        data[key] = value
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, sort_keys=False, default_flow_style=False)
        return True
    except (OSError, yaml.YAMLError) as e:
        print(f"Warning: could not save config '{key}': {e}")
        return False

def load_config() -> Config:
    config_path = BASE_DIR / "config.yaml"
    c = Config()
    try:
        if config_path.exists():
            with open(config_path, "r") as f:
                data = yaml.safe_load(f) or {}
                for k, v in data.items():
                    if hasattr(c, k):
                        default_val = getattr(c, k)
                        expected_type = type(default_val)
                        try:
                            cast_val = expected_type(v)
                            setattr(c, k, cast_val)
                        except (ValueError, TypeError):
                            print(f"Warning: Could not cast config '{k}' value '{v}' to {expected_type.__name__}. Using default.")
    except yaml.YAMLError as e:
        print(f"YAML Error loading config: {e}")
    except OSError as e:
        print(f"OS Error loading config: {e}")
    c.wake_word_model = _resolve_model_path(c.wake_word_model)
    c.stt_model = _resolve_model_path(c.stt_model)
    # Auto-detect the Whisper model only when the user did not pin one in
    # config.yaml: an explicit stt_model always wins. An empty stt_model is
    # treated as "not set" (it would otherwise resolve to the project folder
    # and crash the model load). Dropping a ggml-*.bin file into models/ is
    # enough to switch the speech-to-text model.
    if "stt_model" not in data or not str(data.get("stt_model", "")).strip():
        detected = detect_stt_model(BASE_DIR / "models")
        if detected:
            print(f"STT: using Whisper model {Path(detected).name} (found in models/)")
            c.stt_model = detected
    return c
