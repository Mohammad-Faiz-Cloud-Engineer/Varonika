import pyaudio
import numpy as np
import queue
import threading

class AudioCapture:
    def __init__(self, sample_rate=16000, chunk_size=1280): # 1280 is ~80ms at 16khz
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_listening = False
        self.callbacks = []
        
        self.queue = queue.Queue()
        self.worker_thread = None
        self._stop_event = threading.Event()

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        audio_np = np.frombuffer(in_data, dtype=np.int16).copy()
        if self.is_listening:
            # Put audio data in the queue to be processed by the background worker.
            # This prevents blocking the real-time audio thread.
            try:
                self.queue.put_nowait(audio_np)
            except queue.Full:
                pass
        return (in_data, pyaudio.paContinue)

    def _worker_loop(self):
        while not self._stop_event.is_set():
            try:
                audio_np = self.queue.get(timeout=0.1)
                if audio_np is None:
                    break
                
                # We snapshot callbacks to be safe, though they are usually static
                cbs = list(self.callbacks)
                for cb in cbs:
                    cb(audio_np)
            except queue.Empty:
                continue
            except Exception as e:
                print(f"Audio processing error: {e}")

    def start(self):
        if self.stream is not None:
            return

        if self.p is None:
            self.p = pyaudio.PyAudio()

        self._stop_event.clear()
        self.is_listening = True
        
        # Start background worker thread
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()

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
            
        self._stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            self.queue.put(None) # Sentinel
            self.worker_thread.join(timeout=1.0)
            self.worker_thread = None
            
        # Clear any remaining items in queue
        while not self.queue.empty():
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def close(self):
        self.stop()
        if self.p:
            self.p.terminate()
            self.p = None
