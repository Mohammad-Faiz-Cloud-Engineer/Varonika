from openwakeword.model import Model
import numpy as np

class WakeWordDetector:
    def __init__(self, model_path: str, threshold: float = 0.5):
        # Load the custom wake word model (no default models needed)
        self.model = Model(wakeword_models=[model_path], inference_framework="onnx")
        self.threshold = threshold
        self.model_name = list(self.model.models.keys())[0]
        
    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """
        Process a chunk of audio (expected 16khz, int16)
        Returns True if wake word is detected
        """
        prediction = self.model.predict(audio_chunk)
        score = prediction.get(self.model_name, 0.0)
        if score > self.threshold:
            # reset state after trigger
            self.model.reset()
            return True
        return False
