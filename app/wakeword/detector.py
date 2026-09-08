import os
import shutil
import time
import urllib.request
import hashlib

import numpy as np
from openwakeword.model import Model
import contextlib

WAKEWORD_RESOURCE_URLS = {
    "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
    "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
}

WAKEWORD_RESOURCE_HASHES = {
    "melspectrogram.onnx": "ba2b0e0f8b7b875369a2c89cb13360ff53bac436f2895cced9f479fa65eb176f",
    "embedding_model.onnx": "70d164290c1d095d1d4ee149bc5e00543250a7316b59f31d056cff7bd3075c1f",
}

_MAX_ATTEMPTS = 3

def _resource_path(name):
    # Use the project-local models folder to avoid permission errors when
    # openwakeword is installed globally/system-wide.
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "models",
        name,
    )

def _get_file_hash(path):
    hash_sha256 = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_sha256.update(chunk)
    return hash_sha256.hexdigest()

def _valid_file(path, expected_hash=None):
    try:
        if not (os.path.isfile(path) and os.path.getsize(path) > 0):
            return False
        if expected_hash:
            return _get_file_hash(path).lower() == expected_hash.lower()
        return True
    except OSError:
        return False

def _ensure_resource(name):
    target = _resource_path(name)
    expected_hash = WAKEWORD_RESOURCE_HASHES.get(name)
    if _valid_file(target, expected_hash):
        return target
    part = target + ".part"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with urllib.request.urlopen(WAKEWORD_RESOURCE_URLS[name], timeout=30) as resp, open(part, "wb") as out:
                shutil.copyfileobj(resp, out)
            if _valid_file(part, expected_hash):
                os.replace(part, target)
                print(f"Downloaded missing {name} for wake word.")
                return target
            print(f"Downloaded {name} was empty or corrupted (attempt {attempt}), retrying...")
        except Exception as e:
            print(f"Error downloading {name} (attempt {attempt}/{_MAX_ATTEMPTS}): {e}")
        finally:
            if os.path.exists(part):
                with contextlib.suppress(OSError):
                    os.remove(part)
        if attempt < _MAX_ATTEMPTS:
            time.sleep(2)
    return None

def ensure_wakeword_resources():
    """Newer openwakeword wheels omit the internal models the ONNX runtime
    needs, so every wake word fails to load on a fresh install. Download
    them into the package if absent."""
    for name in WAKEWORD_RESOURCE_URLS:
        target = _resource_path(name)
        expected_hash = WAKEWORD_RESOURCE_HASHES.get(name)
        if not _valid_file(target, expected_hash):
            if _ensure_resource(name) is None:
                raise RuntimeError(f"Failed to download and verify wakeword resource: {name}")

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = 0.6):
        self.threshold = threshold
        self.model, self.model_name = self._load(model_path)

    def _load(self, model_path):
        try:
            ensure_wakeword_resources()
            melspec_path = _resource_path("melspectrogram.onnx")
            embed_path = _resource_path("embedding_model.onnx")
            model = Model(
                wakeword_models=[model_path],
                inference_framework="onnx",
                melspec_model_path=melspec_path,
                embedding_model_path=embed_path
            )
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
