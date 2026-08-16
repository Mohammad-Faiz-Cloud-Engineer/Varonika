import numpy as np
from pywhispercpp.model import Model
import time
import threading

class STTEngine:
    def __init__(self, model_path: str, energy_threshold: float = 0.015, silence_timeout: float = 2.5, language: str = "en"):
        # pywhispercpp supports ggml formats
        print(f"Loading Whisper model from {model_path}...")
        self.model = Model(model_path, n_threads=4, print_realtime=False, print_progress=False, language=language)
        self.energy_threshold = energy_threshold
        self.silence_timeout = silence_timeout

        self._lock = threading.Lock()
        self.audio_buffer = []
        self.last_speech_time = time.time()
        self.speech_seen = False

        # Calibration state
        self.is_calibrating = False
        self.calibration_buffer = []
        self.calibration_chunks_needed = 0

    def start_calibration(self, duration_sec: float = 2.0, chunk_size: int = 1280, sample_rate: int = 16000):
        """Starts collecting audio chunks to establish a dynamic noise floor."""
        print(f"Calibrating noise floor for {duration_sec}s...")
        self.is_calibrating = True
        self.calibration_buffer = []
        self.calibration_chunks_needed = int((sample_rate * duration_sec) / chunk_size)

    def process_chunk(self, audio_chunk: np.ndarray) -> bool:
        """
        Takes 16kHz int16 audio chunk.
        Returns True if silence timeout is reached after speech.
        """
        # Convert to float32 for energy calculation
        audio_float = audio_chunk.astype(np.float32) / 32768.0
        energy = float(np.sqrt(np.mean(audio_float**2)))

        if self.is_calibrating:
            self.calibration_buffer.append(energy)
            if len(self.calibration_buffer) >= self.calibration_chunks_needed:
                # Finished calibrating
                avg_noise = float(np.mean(self.calibration_buffer))
                # Set threshold to avg noise + a buffer (e.g., +0.01 or 1.5x)
                self.energy_threshold = max(0.01, avg_noise * 1.5)
                print(f"Calibration complete. New noise threshold: {self.energy_threshold:.4f}")
                self.is_calibrating = False
            return False

        with self._lock:
            self.audio_buffer.append(audio_float)
            if energy > self.energy_threshold:
                self.last_speech_time = time.time()
                self.speech_seen = True

            if time.time() - self.last_speech_time > self.silence_timeout:
                return True # Ready to transcribe
        return False

    def transcribe(self) -> str:
        """
        Transcribes the current audio buffer and resets it.
        """
        with self._lock:
            if not self.audio_buffer or not self.speech_seen:
                self.audio_buffer = []
                self.speech_seen = False
                self.last_speech_time = time.time()
                return ""

            # pywhispercpp expects float32 np array
            full_audio = np.concatenate(self.audio_buffer)

            # Reset for next time
            self.audio_buffer = []
            self.speech_seen = False
            self.last_speech_time = time.time()

        # Inference outside the lock — it is slow and reset() must not block on it
        segments = self.model.transcribe(full_audio)
        text = "".join([segment.text for segment in segments]).strip()
        return text

    def reset(self):
        with self._lock:
            self.audio_buffer = []
            self.speech_seen = False
            self.last_speech_time = time.time()
