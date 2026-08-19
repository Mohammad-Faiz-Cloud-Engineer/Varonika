import os
import shutil
import urllib.request

import numpy as np
import openwakeword
from openwakeword.model import Model

WAKEWORD_RESOURCE_URLS = {
    "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
    "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
}

def _resource_path(name):
    return os.path.join(
        os.path.dirname(os.path.abspath(openwakeword.__file__)),
        "resources",
        "models",
        name,
    )

def _valid_file(path):
    try:
        return os.path.isfile(path) and os.path.getsize(path) > 0
    except OSError:
        return False

def _ensure_resource(name):
    target = _resource_path(name)
    if _valid_file(target):
        return target
    part = target + ".part"
    try:
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with urllib.request.urlopen(WAKEWORD_RESOURCE_URLS[name], timeout=30) as resp, open(part, "wb") as out:
            shutil.copyfileobj(resp, out)
        if _valid_file(part):
            os.replace(part, target)
            print(f"Downloaded missing {name} for wake word.")
            return target
    except Exception as e:
        print(f"Error downloading {name}: {e}")
    finally:
        if os.path.exists(part):
            try:
                os.remove(part)
            except OSError:
                pass
    return None

def ensure_wakeword_resources():
    """Newer openwakeword wheels omit the internal models the ONNX runtime
    needs, so every wake word fails to load on a fresh install. Download
    them into the package if absent."""
    for name in WAKEWORD_RESOURCE_URLS:
        if not _valid_file(_resource_path(name)) and _ensure_resource(name) is None:
            break

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = 0.6):
        self.threshold = threshold
        self.model, self.model_name = self._load(model_path)

    def _load(self, model_path):
        ensure_wakeword_resources()
        try:
            model = Model(wakeword_models=[model_path], inference_framework="onnx")
            return model, list(model.models.keys())[0]
        except Exception as e:
            print(f"Error loading wake word model: {e}")
            return None, None

        
    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """
        Process a chunk of audio (expected 16khz, int16)
        Returns True if wake word is detected
        """
        if not self.model:
            return False
        prediction = self.model.predict(audio_chunk)
        score = prediction.get(self.model_name, 0.0) if self.model_name else 0.0
        if score > self.threshold:
            # reset state after trigger
            self.model.reset()
            return True
        return False

    def reset(self):
        """Clear the model's internal prediction/feature buffers, e.g. after
        a microphone switch so frames from the old device cannot trigger."""
        if self.model:
            self.model.reset()
