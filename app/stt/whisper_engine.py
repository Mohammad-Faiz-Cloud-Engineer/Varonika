import numpy as np
from pywhispercpp.model import Model
import re
import time
import threading

class STTEngine:
    def __init__(self, model_path: str, energy_threshold: float = 0.015, silence_timeout: float = 2.5, language: str = "en"):
        # pywhispercpp supports ggml formats
        print(f"Loading Whisper model from {model_path}...")
        try:
            self.model = Model(model_path, n_threads=4, print_realtime=False, print_progress=False, language=language)
        except Exception as e:
            print(f"Error loading Whisper model: {e}")
            self.model = None
        self.energy_threshold = energy_threshold
        self.silence_timeout = silence_timeout

        self._lock = threading.Lock()
        # Serializes Whisper inference: the underlying model is not safe for
        # concurrent transcribe() calls.
        self._transcribe_lock = threading.Lock()
        # Bumped by reset(); a transcription in flight checks it after
        # inference and discards its result if it moved (hotkey re-activation).
        self._transcribe_gen = 0
        self.audio_buffer = []
        self.last_speech_time = time.monotonic()
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
        if audio_chunk.dtype == np.int16:
            audio_float = audio_chunk.astype(np.float32) / 32768.0
        else:
            audio_float = audio_chunk.astype(np.float32)
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
            if energy > self.energy_threshold:
                self.last_speech_time = time.monotonic()
                self.speech_seen = True
            # Silence before the first spoken chunk has no transcription value.
            # Keeping it made a hotkey activation with no speech grow forever.
            if not self.speech_seen:
                return False
            self.audio_buffer.append(audio_float)

            if time.monotonic() - self.last_speech_time > self.silence_timeout:
                return True # Ready to transcribe
        return False

    def transcribe(self) -> str | None:
        """
        Transcribes the current audio buffer and resets it.
        Serialized so Whisper never runs twice in parallel; returns None if the
        buffer was invalidated (stt.reset) while transcribing.
        """
        with self._transcribe_lock:
            with self._lock:
                if not self.audio_buffer or not self.speech_seen:
                    self.audio_buffer = []
                    self.speech_seen = False
                    self.last_speech_time = time.monotonic()
                    return None

                # pywhispercpp expects float32 np array
                full_audio = np.concatenate(self.audio_buffer)

                # Reset for next time
                self.audio_buffer = []
                self.speech_seen = False
                self.last_speech_time = time.monotonic()
                my_gen = self._transcribe_gen

            # Inference under the transcribe lock only: the audio buffer lock
            # is released so process_chunk can keep feeding new audio.
            if self.model is None:
                segments = []
            else:
                segments = self.model.transcribe(full_audio)

            with self._lock:
                if my_gen != self._transcribe_gen:
                    return None
            # Whisper splits long speech into segments whose texts do not
            # carry their leading or trailing spaces. Joining them with
            # nothing glues sentences together ("buddy?Can"), so join with a
            # space, then repair any punctuation left glued to the next word
            # ("privacy,meanwhile" -> "privacy, meanwhile"). The lookahead
            # only matches a letter, so decimals like "3.14" stay untouched.
            text = " ".join(segment.text.strip() for segment in segments)
            text = re.sub(r'([.!?,;:])(?=[A-Za-z])', r'\1 ', text)
            return text.strip()

    def reset(self):
        with self._lock:
            self.audio_buffer = []
            self.speech_seen = False
            self.last_speech_time = time.monotonic()
            self._transcribe_gen += 1
