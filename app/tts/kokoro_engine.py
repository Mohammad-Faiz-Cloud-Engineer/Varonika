import sounddevice as sd
from kokoro import KPipeline
import queue
import threading
import time

class TTSEngine:
    def __init__(self, voice="af_bella", speed=1.0):
        self.voice = voice
        self.speed = speed
        # Ensure we have the language model, a = American English
        self.pipeline = KPipeline(lang_code='a') 
        self._stop_event = threading.Event()
        self._queue = queue.Queue()
        self._thread = None
        self._generation = 0
        self._speaking = threading.Event()
        # After the last audio sample finishes playing, the mic can still pick
        # up the speaker's echo/reverb lingering in the room (typically a few
        # hundred milliseconds). Keep the echo guard up for that tail so the
        # assistant never transcribes (or reacts to) her own voice.
        self._reverb_tail_tick = 0.05
        self._reverb_tail_ticks = 6  # 300 ms total, checked every 50 ms

    def start_worker(self):
        self._stop_event.clear()
        self._generation += 1
        gen = self._generation
        self._thread = threading.Thread(target=self._worker, args=(gen,), daemon=True)
        self._thread.start()

    def _worker(self, gen):
        while not self._stop_event.is_set() and gen == self._generation:
            try:
                # Get the next sentence to speak
                text = self._queue.get(timeout=0.1)
                if text is None: # poison pill
                    break
                self._speaking.set()
                
                # Generate audio
                generator = self.pipeline(
                    text, voice=self.voice,
                    speed=self.speed, split_pattern=r'\n+'
                )
                
                for _, _, audio in generator:
                    if self._stop_event.is_set() or gen != self._generation:
                        break
                    # audio is a numpy array at 24000 sample rate
                    sd.play(audio, 24000)
                    sd.wait() # wait for this chunk to finish playing
                # Reverb tail: only wait after the final sentence (queue empty),
                # so inter-sentence streaming is not slowed down. Interruptible
                # so a hotkey stop still responds immediately.
                if self._queue.empty() and not self._stop_event.is_set():
                    for _ in range(self._reverb_tail_ticks):
                        if self._stop_event.is_set() or gen != self._generation:
                            break
                        time.sleep(self._reverb_tail_tick)
                self._speaking.clear()
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS Error: {e}")

    def speak(self, text: str):
        """Enqueue text to be spoken."""
        self._queue.put(text)

    def is_speaking(self) -> bool:
        """True while audio is queued or currently playing (echo guard)."""
        return self._speaking.is_set() or not self._queue.empty()

    def stop_and_clear(self):
        """Interrupts current speech and clears queue."""
        self._stop_event.set()
        self._speaking.clear()
        sd.stop()
        # clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        
        # restart worker immediately
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self.start_worker()

    def stop(self):
        self._stop_event.set()
        self._speaking.clear()
        sd.stop()
        if self._thread:
            self._queue.put(None)
            self._thread.join()
