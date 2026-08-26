import collections
import os
import queue
import threading
import time

import numpy as np
import sounddevice as sd
from scipy.signal import resample_poly

# Keep synthesis from hogging every core: on Windows the MME/WASAPI audio
# threads and the rest of the system share the machine, and a fully loaded
# CPU periodically starves the playback callback (audible ~0.7 s stalls).
# Kokoro is a small model: four threads stay well above real time.
os.environ.setdefault("OMP_NUM_THREADS", "4")
import torch

torch.set_num_threads(4)

from kokoro import KPipeline
import contextlib

SAMPLE_RATE = 24000
# Small blocks keep writes real-time paced: an interrupt is honored within
# roughly one block (1024/24000 s ~ 43 ms) plus the device buffer.
BLOCK_SIZE = 1024
# Kokoro puts ~0.4-0.6 s of silence at every sentence-final period and at the
# start of every segment, plus ~0.2 s at commas. Uncompressed, that reads as a
# staccato stutter; a 150 ms cap still reads as a pause. Trim every run
# longer than 100 ms down to 40 ms so sentence transitions flow continuously.
SILENCE_THRESHOLD = 0.005
SILENCE_MAX = 0.04
SILENCE_MIN_TRIM = 0.10
# How much finished audio may pile up ahead of playback. The producer is
# allowed to run this far in front so a slow sentence never leaves the
# speaker silent, while interrupts still stay responsive and memory stays
# bounded (60 s of float32 mono is ~5.7 MB at 24 kHz, ~11.5 MB at 48 kHz).
# Deep enough to ride out the whole LLM streaming phase even when synthesis
# is barely faster than real time.
MAX_BUFFERED_SECONDS = 60.0

def _compress_silences(audio: np.ndarray) -> np.ndarray:
    """Shorten silence runs longer than 100 ms to 40 ms, keep the rest."""
    if len(audio) == 0:
        return audio
    silent = np.abs(audio) < SILENCE_THRESHOLD
    edges = np.flatnonzero(np.diff(silent.astype(np.int8)))
    starts = np.concatenate(([0], edges + 1))
    ends = np.concatenate((edges + 1, [len(audio)]))
    max_silence = int(SILENCE_MAX * SAMPLE_RATE)
    min_trim = int(SILENCE_MIN_TRIM * SAMPLE_RATE)
    parts = []
    for s, e in zip(starts, ends, strict=False):
        if silent[s] and (e - s) > min_trim:
            parts.append(audio[s : s + max_silence])
        else:
            parts.append(audio[s:e])
    return np.concatenate(parts) if parts else audio

def _pick_output_device():
    """Return (device_index, sample_rate) for the TTS output stream.

    Prefers the WASAPI shared-mode entry for the system's default output
    device at its native rate (48 kHz typically), because MME output
    occasionally starves the callback for hundreds of milliseconds while
    the mic input stream is also open, which reads as a spoken-word hiccup.
    Falls back to the PortAudio default device at 24 kHz when no matching
    WASAPI entry can be opened (validation open is part of the pick).
    """
    try:
        devs = sd.query_devices()
        default_idx = sd.default.device[1] if sd.default.device else None
        if default_idx is None:
            try:
                default_idx = sd.query_hostapis(0).get("default_output_device", -1)
            except Exception:
                default_idx = None
        if default_idx is None or default_idx < 0:
            default_idx = None
        default_name = devs[default_idx]["name"] if default_idx is not None else ""
        if default_name:
            for i in range(len(devs)):
                d = devs[i]
                if d["max_output_channels"] <= 0:
                    continue
                api = sd.query_hostapis(d["hostapi"])["name"].lower()
                if "wasapi" not in api:
                    continue
                name = d["name"]
                # PortAudio truncates MME names to 31 chars while WASAPI
                # names arrive untruncated, so an exact comparison never
                # matches ("Headphones (realme TechLife Bud" vs "...Buds
                # T100)"). Compare by prefix in both directions: either
                # side may be the truncated one. All WASAPI outputs on a
                # machine are distinct in their first chars, so a prefix
                # match cannot pick the wrong device.
                a = name.lower()
                b = default_name.lower()
                if a.startswith(b) or b.startswith(a):
                    try:
                        s = sd.OutputStream(
                            samplerate=int(d["default_samplerate"]),
                            channels=1, dtype="float32", device=i,
                            extra_settings=sd.WasapiSettings(exclusive=False),
                            blocksize=BLOCK_SIZE, latency=0.2,
                        )
                        s.start()
                        s.stop()
                        s.close()
                        print(f"TTS output: WASAPI shared {name} "
                              f"at {int(d['default_samplerate'])} Hz")
                        return i, int(d["default_samplerate"])
                    except Exception:
                        continue
    except Exception as e:
        print(f"TTS output WASAPI lookup failed, using MME: {e}")
    print("TTS output: default device (MME) at 24 kHz")
    return None, SAMPLE_RATE

class TTSEngine:
    def __init__(self, voice="af_bella", speed=0.9, volume=1.0):
        self.voice = voice
        self.speed = speed
        # Loudness boost (1.0 = unchanged). Read under the lock and applied
        # by the producer to every audio block, so a slider move in the UI
        # takes effect from the next synthesized block on.
        self._volume = float(volume)
        # Ensure we have the language model, a = American English
        try:
            self.pipeline = KPipeline(lang_code='a')
        except Exception as e:
            print(f"Error loading TTS: {e}")
            self.pipeline = None
        self._stop_event = threading.Event()
        self._queue = queue.Queue()
        self._thread = None
        self._generation = 0
        self._pending_items = 0
        # Echo guard ownership: the generation id of the producer that
        # currently owns the guard, or None. A producer sets it when it
        # dequeues speech and clears it only if it still owns it. A stale
        # producer (killed by an interrupt) can never clear the successor's
        # guard, and a stale owner id never reads as "speaking" because it
        # no longer matches _generation.
        self._speaking_owner = None
        # After the last audio sample finishes playing, the mic can still
        # pick up the speaker's echo/reverb lingering in the room (typically
        # a few hundred milliseconds). Keep the echo guard up for that tail
        # so the assistant never transcribes (or reacts to) her own voice.
        self._reverb_tail_tick = 0.05
        self._reverb_tail_ticks = 6  # 300 ms total, checked every 50 ms
        self._lock = threading.Lock()
        # True while the producer is mid-generation of a text. Used to
        # distinguish "answer over" from "next sentence is being synthesized
        # right now".
        self._producing = False
        # Set by the manager when the answer is finished (final flush). The
        # producer cannot tell "LLM thinking between sentences" from "answer
        # over": only the manager can: so the reverb tail waits for this
        # explicit signal instead of guessing.
        self._answer_ended = False

        # Playback buffer: complete float32 mono blocks drained by the audio
        # callback. The producer may run far ahead of the speaker, so a slow
        # sentence never leaves a gap in the middle of an answer.
        self._blocks = collections.deque()
        # Block currently being played back plus the sample offset into it.
        self._cur = None
        self._audio_lock = threading.Lock()
        # Output device + sample rate. WASAPI shared mode has far more stable
        # timing than the default MME host API (MME periodically starves the
        # callback for hundreds of milliseconds while a mic stream is open).
        # WASAPI only accepts the device's native rate, so the producer
        # resamples Kokoro's 24 kHz up to it. Falls back to MME at 24 kHz
        # when no matching WASAPI output can be opened.
        self._out_device, self._out_rate = _pick_output_device()
        self._max_buffered_samples = int(MAX_BUFFERED_SECONDS * self._out_rate)
        self._stream = None
        self._stream_lock = threading.Lock()

    def _audio_callback(self, outdata, frames, _time_info, _status):
        """Called by the audio driver with a hard deadline. Never blocks,
        never allocates: pulls finished samples out of the playback buffer
        and zero-fills if it runs dry (a silent beat instead of a stutter)."""
        with self._audio_lock:
            written = 0
            if self._cur is not None:
                arr, off = self._cur
                n = min(frames, len(arr) - off)
                outdata[:n, 0] = arr[off:off + n]
                written = n
                if off + n >= len(arr):
                    self._cur = None
                else:
                    self._cur = (arr, off + n)
            while written < frames and self._blocks:
                arr = self._blocks.popleft()
                n = min(frames - written, len(arr))
                outdata[written:written + n, 0] = arr[:n]
                written += n
                if n < len(arr):
                    self._cur = (arr, n)
            if written < frames:
                outdata[written:, 0] = 0.0

    def _buffered_samples(self) -> int:
        total = 0
        if self._cur is not None:
            total += len(self._cur[0]) - self._cur[1]
        for b in self._blocks:
            total += len(b)
        return total

    def _get_stream(self):
        """One persistent output stream for the whole session.

        A single stream flows sentences together with no start/stop gaps, so
        words are never clipped at sentence boundaries. (sd.play per sentence
        restarts the device stream every sentence, and Windows eats the start
        of each restart: words come out chopped.)

        A generous device buffer (~200 ms) absorbs Windows driver jitter
        without being noticeable. WASAPI shared mode is preferred (see
        _pick_output_device); MME is the fallback. Bluetooth endpoints are
        flaky: the first open occasionally fails with a WDM-KS error while
        the device stack settles, so a failed open is retried with backoff.
        """
        with self._stream_lock:
            if self._stream is None:
                kwargs = {
                    "samplerate": self._out_rate, "channels": 1, "dtype": "float32",
                    "blocksize": BLOCK_SIZE, "callback": self._audio_callback,
                    "latency": 0.2,
                }
                if self._out_device is not None:
                    kwargs["device"] = self._out_device
                    kwargs["extra_settings"] = sd.WasapiSettings(exclusive=False)
                last_error = None
                for attempt in range(6):
                    try:
                        s = sd.OutputStream(**kwargs)
                        s.start()
                        self._stream = s
                        return self._stream
                    except Exception as e:
                        last_error = e
                        with contextlib.suppress(Exception):
                            s.close()
                        time.sleep(0.15 * (attempt + 1))
                # WASAPI is wedged (BT stack settling, device state): fall
                # back to the PortAudio default device at 24 kHz so speech
                # is never lost until the app restarts.
                try:
                    self._out_device = None
                    with self._audio_lock:
                        self._out_rate = SAMPLE_RATE
                        self._max_buffered_samples = int(
                            MAX_BUFFERED_SECONDS * SAMPLE_RATE)
                    s = sd.OutputStream(
                        samplerate=SAMPLE_RATE, channels=1, dtype="float32",
                        blocksize=BLOCK_SIZE, callback=self._audio_callback,
                        latency=0.2,
                    )
                    s.start()
                    self._stream = s
                    print("TTS output: fell back to default device (MME) at 24 kHz")
                    return self._stream
                except Exception as e2:
                    with contextlib.suppress(Exception):
                        s.close()
                    print(f"TTS output unavailable: {last_error} / fallback: {e2}")
                    return None
            return self._stream

    def _close_stream(self):
        with self._stream_lock:
            if self._stream is not None:
                with contextlib.suppress(Exception):
                    self._stream.abort()
                with contextlib.suppress(Exception):
                    self._stream.close()
                self._stream = None

    def start_worker(self):
        self._launch_worker(bump=True)

    def _launch_worker(self, bump: bool):
        with self._lock:
            # Invalidate any still-running producer before the stop event
            # is cleared. Clearing first left a window where the old
            # thread could resume and speak a cancelled answer.
            if bump:
                self._generation += 1
            gen = self._generation
            self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._producer, args=(gen,), daemon=True
        )
        self._thread.start()

    def _producer(self, gen: int):
        print(f"TTS Worker {gen} started.")
        # One producer thread for the whole worker lifetime. It pulls
        # sentences from the queue, synthesizes them, and feeds the playback
        # buffer; the audio callback drains that buffer. Synthesis runs
        # ahead of playback, so the speaker never waits on the model.
        while True:
            try:
                item = self._queue.get(timeout=0.1)
            except queue.Empty:
                if self._stop_event.is_set() or gen != self._generation:
                    return
                # Nothing queued: the answer may be over, in which case the
                # reverb tail may run once playback has drained.
                self._maybe_finish_answer(gen)
                continue
            if item is None:
                # Poison pill from stop(): leave without re-queuing so a
                # later start_worker never wedges on it. Clear the counters
                # so is_speaking() can never read as True after shutdown.
                with self._lock:
                    self._pending_items = 0
                    self._speaking_owner = None
                return
            stamp, text = item
            with self._lock:
                if stamp != self._generation:
                    # Enqueued before the last interrupt: it was already
                    # invalidated, drop it rather than speak the tail of a
                    # cancelled request. stop_and_clear already zeroed
                    # pending; do not decrement or a newer speak() could
                    # lose its echo-guard count.
                    continue
                if self._stop_event.is_set() or gen != self._generation:
                    # A newer worker owns the queue now. Hand the item back
                    # rather than dropping it: a request spoken right after
                    # an interrupt must not be swallowed.
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
                    # All CPU work (silence compression, volume gain,
                    # resampling) happens here, off the audio path: the
                    # callback only memcpys finished samples.
                    audio = _compress_silences(np.asarray(audio, dtype=np.float32))
                    with self._audio_lock:
                        out_rate = self._out_rate
                    if out_rate != SAMPLE_RATE:
                        audio = resample_poly(audio, out_rate, SAMPLE_RATE)
                    with self._lock:
                        vol = self._volume
                    if vol != 1.0:
                        # Boost loudness; clip so the audio card never gets
                        # samples beyond full scale (which would crackle).
                        audio = np.clip(audio * vol, -1.0, 1.0)
                    self._queue_audio(audio, gen)
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
                self._maybe_finish_answer(gen)

    def _queue_audio(self, audio: np.ndarray, gen: int):
        if self._get_stream() is None:
            # Output unavailable (device gone, driver error): drop this
            # segment. Speech is lost, but the echo guard still unwinds
            # normally through _maybe_finish_answer.
            return
        # Wait for buffer room. If nothing drains for several seconds the
        # device callback is dead (headset lost, driver wedged): give up on
        # this segment rather than block the producer forever, which would
        # leave the echo guard up and wedge the state machine in SPEAKING.
        deadline = time.monotonic() + 5.0
        while not self._stop_event.is_set() and gen == self._generation:
            with self._audio_lock:
                if self._buffered_samples() < self._max_buffered_samples:
                    self._blocks.append(audio)
                    return
            if time.monotonic() > deadline:
                print("TTS playback warning: buffer never drained, dropping segment")
                return
            time.sleep(0.02)

    def _maybe_finish_answer(self, gen: int):
        """Release the echo guard once the whole answer has drained.

        Called whenever the producer finds nothing queued. The tail fires
        only after the manager signalled the answer is over AND nothing is
        still generating AND every finished sample has been handed to the
        device: so it never lands mid-answer while the LLM is thinking
        between sentences, or while buffered audio is still playing.
        """
        with self._lock:
            if (self._speaking_owner != gen or not self._answer_ended
                    or self._producing or not self._queue.empty()):
                return
        with self._audio_lock:
            buffered = self._buffered_samples()
        # The last block may still be sitting in the playback buffer: wait
        # for it to drain (bounded by how much audio is left, plus margin).
        deadline = time.monotonic() + 2.0 + buffered / self._out_rate
        drained = False
        while time.monotonic() < deadline:
            if self._stop_event.is_set() or gen != self._generation:
                return
            if not self._queue.empty():
                # New speech arrived while we waited: hand back to the
                # producer loop, the guard stays up for the new answer.
                return
            with self._audio_lock:
                drained = self._buffered_samples() == 0
            if drained:
                break
            time.sleep(0.02)
        if not drained:
            # The device is wedged: release the guard anyway so the state
            # machine never gets stuck in SPEAKING. Nothing was playing, so
            # there is no echo to guard against.
            with self._lock:
                if self._speaking_owner == gen:
                    self._speaking_owner = None
            return
        for _ in range(self._reverb_tail_ticks):
            if self._stop_event.is_set() or gen != self._generation:
                return
            time.sleep(self._reverb_tail_tick)
        # Release the echo guard only if no new speech arrived while this
        # tail was sleeping (e.g. the first sentence of the next answer):
        # otherwise the guard would drop mid-answer.
        with self._lock:
            if (self._speaking_owner == gen and self._pending_items == 0
                    and not self._producing and self._queue.empty()):
                self._speaking_owner = None

    def set_volume(self, volume: float):
        """Adjust the loudness boost. Applies from the next synthesized block on."""
        with self._lock:
            self._volume = max(0.0, float(volume))

    def speak(self, text: str):
        """Enqueue text to be spoken."""
        if not text or self.pipeline is None:
            return
        with self._lock:
            # An interrupt holds this event until the replacement worker
            # starts. Enqueueing during that window would either leak a
            # pending-count (stale stamp after the generation bump) or
            # speak the cancelled answer's tail on the new worker.
            if self._stop_event.is_set():
                return
            self._pending_items += 1
            # Stamp with the enqueue generation so a producer left over from
            # an interrupted worker can tell stale requests from fresh ones.
            stamp = self._generation
        self._queue.put((stamp, text))

    def is_speaking(self) -> bool:
        """True while audio is queued, synthesized, buffered or playing (echo guard).

        The guard is owned by the current generation: a stale owner id left
        behind by an interrupted worker never reads as speaking because it no
        longer matches _generation.
        """
        with self._lock:
            return self._speaking_owner == self._generation or self._pending_items > 0

    def signal_answer_start(self):
        """Mark that a new answer is beginning.

        The reverb tail must wait for the end signal again: a previous
        signal_answer_end (e.g. from the wake word ack) would otherwise
        make the tail fire mid-answer whenever the LLM pauses between
        sentences, dropping the echo guard while she is still speaking.
        """
        with self._lock:
            self._answer_ended = False

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
        """Interrupts current speech and clears the queue and buffer."""
        with self._lock:
            self._stop_event.set()
            # Bump here (not only in start_worker) so a speak() that raced
            # in after pending was zeroed but before the worker restart
            # cannot stamp with the old generation and leak is_speaking().
            self._generation += 1
            self._speaking_owner = None
            self._pending_items = 0
            self._answer_ended = False
            # clear the text queue
            while not self._queue.empty():
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
        with self._audio_lock:
            self._blocks.clear()
            self._cur = None
        # Keep the device stream open: the callback zero-fills the moment the
        # buffer is empty, so silence is instant anyway. Reopening right
        # after an abort can fail on WASAPI (WDM-KS device still settling),
        # and reopening always risks a fresh start/stop glitch.
        # restart worker immediately (orphan the old thread so the audio
        # callback isn't blocked). Generation already bumped above.
        self._launch_worker(bump=False)

    def stop(self):
        with self._lock:
            self._stop_event.set()
            self._speaking_owner = None
        with self._audio_lock:
            self._blocks.clear()
            self._cur = None
        self._close_stream()
        if self._thread:
            self._queue.put(None)
            self._thread.join(timeout=1.0)
