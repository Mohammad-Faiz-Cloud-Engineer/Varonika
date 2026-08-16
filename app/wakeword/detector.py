from openwakeword.model import Model
import numpy as np

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = 0.5):
        # Load the custom wake word model (no default models needed)
        try:
            self.model = Model(wakeword_models=[model_path], inference_framework="onnx")
            self.model_name = list(self.model.models.keys())[0]
        except Exception as e:
            print(f"Error loading wake word model: {e}")
            self.model = None
            self.model_name = None

        
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
