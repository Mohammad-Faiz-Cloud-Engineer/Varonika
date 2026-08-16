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
        # Echo guard ownership: the generation id of the worker that currently
        # owns the guard, or None. A worker sets it when it dequeues speech and
        # clears it only if it still owns it. A stale worker (killed by an
        # interrupt) can never clear the successor's guard, and a stale owner id
        # never reads as "speaking" because it no longer matches _generation.
        self._speaking_owner = None
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
                self._speaking_owner = gen
                
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
                if self._speaking_owner == gen:
                    self._speaking_owner = None
                
            except queue.Empty:
                continue
            except Exception as e:
                print(f"TTS Error: {e}")
                if self._speaking_owner == gen:
                    self._speaking_owner = None

    def speak(self, text: str):
        """Enqueue text to be spoken."""
        self._queue.put(text)

    def is_speaking(self) -> bool:
        """True while audio is queued or currently playing (echo guard).

        The guard is owned by the current generation: a stale owner id left
        behind by an interrupted worker never reads as speaking because it no
        longer matches _generation.
        """
        return self._speaking_owner == self._generation or not self._queue.empty()

    def stop_and_clear(self):
        """Interrupts current speech and clears queue."""
        self._stop_event.set()
        self._generation += 1  # invalidate the running worker
        self._speaking_owner = None
        sd.stop()
        # clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        
        # restart worker immediately (orphan the old thread so audio callback isn't blocked)
        self.start_worker()

    def stop(self):
        self._stop_event.set()
        self._speaking_owner = None
        sd.stop()
        if self._thread:
            self._queue.put(None)
            self._thread.join()
