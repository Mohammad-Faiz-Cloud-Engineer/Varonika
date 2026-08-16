import pyaudio
import numpy as np

class AudioCapture:
    def __init__(self, sample_rate=16000, chunk_size=1280): # 1280 is ~80ms at 16khz
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_listening = False
        self.callbacks = []

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        audio_np = np.frombuffer(in_data, dtype=np.int16)
        if self.is_listening:
            for cb in self.callbacks:
                cb(audio_np)
        return (in_data, pyaudio.paContinue)

    def start(self):
        if self.stream is not None:
            return
        
        self.is_listening = True
        self.stream = self.p.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.sample_rate,
            input=True,
            frames_per_buffer=self.chunk_size,
            stream_callback=self._audio_callback
        )
        self.stream.start_stream()

    def stop(self):
        self.is_listening = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None

    def close(self):
        self.stop()
        self.p.terminate()
