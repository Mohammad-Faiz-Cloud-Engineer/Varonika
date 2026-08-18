import yaml
from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent.parent.parent

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
    return c
