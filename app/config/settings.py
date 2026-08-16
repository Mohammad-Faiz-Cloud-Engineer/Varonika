import yaml
from pathlib import Path
from dataclasses import dataclass

BASE_DIR = Path(__file__).resolve().parent.parent.parent

@dataclass
class Config:
    wake_word_model: str = "models/wakeword.onnx"
    wake_word_threshold: float = 0.5
    stt_model: str = "models/ggml-small.en.bin"
    stt_language: str = "en"
    silence_timeout_ms: int = 2500
    energy_threshold: float = 0.015
    tts_voice: str = "af_bella"
    # Below 1.0 speaks slower and articulates words more clearly.
    tts_speed: float = 0.9
    follow_up_timeout_ms: int = 2000

def _resolve_model_path(path: str) -> str:
    """Anchor relative model paths to the project root regardless of CWD."""
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / p
    return str(p)

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
    except Exception as e:
        print(f"Error loading config: {e}")
    c.wake_word_model = _resolve_model_path(c.wake_word_model)
    c.stt_model = _resolve_model_path(c.stt_model)
    return c
