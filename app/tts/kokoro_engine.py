import sounddevice as sd
from kokoro import KPipeline
import numpy as np
import queue
import threading
import time

SAMPLE_RATE = 24000
# Small blocks keep writes real-time paced: an interrupt is honored within
# roughly one block (1024/24000 s ~ 43 ms) plus the device buffer.
BLOCK_SIZE = 1024
# Kokoro puts ~0.4-0.6 s of silence at every sentence-final period. That is
# natural prosody, but a bit long for a chatty assistant. Compress long
# silent runs down to a short beat; anything shorter is left untouched.
SILENCE_THRESHOLD = 0.005
SILENCE_MAX = 0.15
SILENCE_MIN_TRIM = 0.25

def _compress_silences(audio: np.ndarray) -> np.ndarray:
    """Shorten silence runs longer than 250 ms to 150 ms, keep the rest."""
    silent = np.abs(audio) < SILENCE_THRESHOLD
    edges = np.flatnonzero(np.diff(silent.astype(np.int8)))
    starts = np.concatenate(([0], edges + 1))
    ends = np.concatenate((edges + 1, [len(audio)]))
    max_silence = int(SILENCE_MAX * SAMPLE_RATE)
    min_trim = int(SILENCE_MIN_TRIM * SAMPLE_RATE)
    parts = []
    for s, e in zip(starts, ends):
        if silent[s] and (e - s) > min_trim:
            parts.append(audio[s : s + max_silence])
        else:
            parts.append(audio[s:e])
    return np.concatenate(parts) if parts else audio

class TTSEngine:
    def __init__(self, voice="af_bella", speed=0.9):
        self.voice = voice
        self.speed = speed
        # Ensure we have the language model, a = American English
        self.pipeline = KPipeline(lang_code='a') 
        self._stop_event = threading.Event()
        self._queue = queue.Queue()
        self._thread = None
        self._generation = 0
        self._pending_items = 0
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
        self._lock = threading.Lock()
        self._stream = None
        self._stream_lock = threading.Lock()
        # True while the producer is mid-generation of a text. The worker
        # uses this to distinguish "answer over" from "next sentence is
        # being synthesized right now" - without it the reverb tail fires
        # mid-answer whenever the LLM pauses between sentences.
        self._producing = False
        # Set by the manager when the answer is finished (final flush).
        # The producer cannot tell "LLM thinking between sentences" from
        # "answer over" - only the manager can - so the reverb tail waits
        # for this explicit signal instead of guessing.
        self._answer_ended = False

    def _get_stream(self):
        """One persistent output stream for the whole answer.

        A single stream flows sentences together with no start/stop gaps, so
        words are never clipped at sentence boundaries. (sd.play per sentence
        restarts the device stream every sentence, and Windows eats the start
        of each restart - words come out chopped.)
        """
        with self._stream_lock:
            if self._stream is None:
                self._stream = sd.OutputStream(
                    samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                    blocksize=BLOCK_SIZE,
                )
                self._stream.start()
            return self._stream

    def _close_stream(self):
        with self._stream_lock:
            if self._stream is not None:
                try:
                    self._stream.abort()
                except Exception:
                    pass
                try:
                    self._stream.close()
                except Exception:
                    pass
                self._stream = None

    def start_worker(self):
        with self._lock:
            self._stop_event.clear()
            self._generation += 1
            gen = self._generation
        self._thread = threading.Thread(target=self._worker, args=(gen,), daemon=True)
        self._thread.start()

    def _worker(self, gen: int):
        print(f"TTS Worker {gen} started.")
        # One producer thread and one prefetch queue for the whole worker
        # lifetime. The producer pulls sentences from the queue and generates
        # their audio while the worker plays the previous audio - so a full
        # stop no longer waits for the next sentence to be synthesized.
        prefetch = queue.Queue(maxsize=3)
        IDLE = object()

        def _produce():
            while True:
                try:
                    item = self._queue.get(timeout=0.1)
                except queue.Empty:
                    # Nothing queued: tell the worker it may wait for the
                    # reverb tail (answer likely over).
                    while True:
                        try:
                            prefetch.put_nowait(IDLE)
                            break
                        except queue.Full:
                            if self._stop_event.is_set() or gen != self._generation:
                                return
                            time.sleep(0.02)
                    continue
                if item is None:
                    # Poison pill: forward it to the worker instead of
                    # re-queuing, so a later start_worker never wedges on it.
                    prefetch.put(None)
                    return
                stamp, text = item
                with self._lock:
                    if stamp != self._generation:
                        # Enqueued before the last interrupt: it was already
                        # invalidated, drop it rather than speak the tail of
                        # a cancelled request.
                        return
                    if self._stop_event.is_set() or gen != self._generation:
                        # A newer worker owns the queue now. Hand the item
                        # back rather than dropping it - a request spoken
                        # right after an interrupt must not be swallowed.
                        self._queue.put(item)
                        return
                    if self._pending_items > 0:
                        self._pending_items -= 1
                    self._speaking_owner = gen
                    self._producing = True
                try:
                    generator = self.pipeline(
                        text, voice=self.voice,
                        speed=self.speed, split_pattern=r'\n+'
                    )
                    for _, _, audio in generator:
                        if self._stop_event.is_set() or gen != self._generation:
                            return
                        if len(audio) == 0:
                            continue
                        while True:
                            try:
                                prefetch.put(audio, timeout=0.2)
                                break
                            except queue.Full:
                                # Worker is mid-playback; wait for room.
                                # Only give up when interrupted.
                                if self._stop_event.is_set() or gen != self._generation:
                                    return
                except Exception as e:
                    print(f"TTS Error: {e}")
                    with self._lock:
                        if self._speaking_owner == gen:
                            self._speaking_owner = None
                finally:
                    with self._lock:
                        self._producing = False

        threading.Thread(target=_produce, daemon=True).start()

        stream = None
        tailed = False
        try:
            while True:
                if self._stop_event.is_set() or gen != self._generation:
                    break
                try:
                    item = prefetch.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is IDLE:
                    # Producer is waiting for the next text. The reverb tail
                    # fires only after the manager signals the answer is over
                    # and nothing is still generating or queued - so it never
                    # lands mid-answer while the LLM is thinking between
                    # sentences.
                    with self._lock:
                        answer_over = self._answer_ended and not self._producing
                    if not tailed and answer_over and self._queue.empty() and prefetch.empty():
                        for _ in range(self._reverb_tail_ticks):
                            if self._stop_event.is_set() or gen != self._generation:
                                break
                            time.sleep(self._reverb_tail_tick)
                        tailed = True
                        with self._lock:
                            if self._speaking_owner == gen:
                                self._speaking_owner = None
                    continue
                if item is None:
                    break
                # A stale chunk pulled just as an interrupt landed: don't
                # write it - the successor's stream may already be live.
                if self._stop_event.is_set() or gen != self._generation:
                    break
                # New audio after an idle gap (e.g. a follow-up): raise the
                # echo guard again.
                with self._lock:
                    if self._speaking_owner != gen:
                        self._speaking_owner = gen
                tailed = False
                if stream is None:
                    stream = self._get_stream()
                # audio is a numpy array at 24000 sample rate; write() is
                # inherently blocking and paces in near real time
                try:
                    stream.write(_compress_silences(np.asarray(item, dtype=np.float32)))
                except sd.PortAudioError:
                    # Expected when the stream was aborted by an interrupt
                    # or shutdown; anything else is a real device problem
                    # worth surfacing.
                    if not (self._stop_event.is_set() or gen != self._generation):
                        print("TTS playback error: stream aborted unexpectedly")
                    break
                except Exception as e:
                    print(f"TTS playback error: {e}")
                    break
        finally:
            with self._lock:
                if self._speaking_owner == gen:
                    self._speaking_owner = None

    def speak(self, text: str):
        """Enqueue text to be spoken."""
        with self._lock:
            self._pending_items += 1
            # Stamp with the enqueue generation so a producer left over from
            # an interrupted worker can tell stale requests from fresh ones.
            stamp = self._generation
        self._queue.put((stamp, text))

    def is_speaking(self) -> bool:
        """True while audio is queued or currently playing (echo guard).

        The guard is owned by the current generation: a stale owner id left
        behind by an interrupted worker never reads as speaking because it no
        longer matches _generation.
        """
        with self._lock:
            return self._speaking_owner == self._generation or self._pending_items > 0

    def signal_answer_end(self):
        """Tell the engine the current answer is finished.

        Called by the manager once the final sentence has been enqueued.
        The reverb tail (and the echo-guard release) waits for this signal
        so it never fires while the LLM is simply pausing between
        sentences of the same answer.
        """
        with self._lock:
            self._answer_ended = True

    def stop_and_clear(self):
        """Interrupts current speech and clears queue."""
        with self._lock:
            self._stop_event.set()
            self._generation += 1  # invalidate the running worker
            self._speaking_owner = None
            self._pending_items = 0
            self._answer_ended = False
        # Abort playback: a blocking write in the old worker raises
        # PortAudioError, so it unwinds and sees the stale generation.
        self._close_stream()
        # clear queue
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        
        # restart worker immediately (orphan the old thread so audio callback isn't blocked)
        self.start_worker()

    def stop(self):
        with self._lock:
            self._stop_event.set()
            self._speaking_owner = None
        self._close_stream()
        if self._thread:
            self._queue.put(None)
            self._thread.join()
