import pyaudio
import numpy as np
import queue
import threading

class AudioCapture:
    def __init__(self, sample_rate=16000, chunk_size=1280, device_name=""): # 1280 is ~80ms at 16khz
        self.sample_rate = sample_rate
        self.chunk_size = chunk_size
        self.device_name = device_name or ""
        self.p = pyaudio.PyAudio()
        self.stream = None
        self.is_listening = False
        self.callbacks = []
        self.active_device = self._default_device_name()
        
        self.queue = queue.Queue(maxsize=50)
        self.worker_thread = None
        self._stop_event = threading.Event()

    def _canonical_name(self, index: int) -> str:
        """Full display name for a device index. PortAudio reports MME
        entries with Windows-truncated 31-char names; when the entry at
        index is such a truncated name, resolve it to the device's full
        name (the truncated name is a prefix of the full one) so the
        label and the dropdown stay consistent."""
        try:
            name = self.p.get_device_info_by_index(index).get("name", "")
        except Exception:
            return ""
        if len(name) != 31:
            return name
        best = name
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    n = info.get("name", "")
                    if len(n) > len(best) and n.lower().startswith(name.lower()):
                        best = n
            except Exception:
                continue
        return best

    def _default_device_name(self) -> str:
        try:
            idx = self.p.get_default_input_device_info().get("index")
            if idx is None:
                return "System Default"
            return self._canonical_name(idx) or "System Default"
        except Exception:
            return "System Default"

    # Windows virtual capture devices that are not real microphones:
    # the sound mapper wrappers and the output-mix/loopback captures.
    _VIRTUAL_MARKERS = (
        "sound mapper", "primary sound capture", "stereo mix",
        "pc speaker", "what u hear", "wave out mix",
    )

    @staticmethod
    def _dedupe_key(name: str) -> str:
        return name[:31].lower()

    def _is_available(self, index: int) -> bool:
        """True when the device actually opens for capture at our format.
        Paired-but-disconnected Bluetooth headsets leave ghost endpoints
        that Windows lists but that cannot be opened."""
        try:
            s = self.p.open(
                format=pyaudio.paInt16, channels=1, rate=self.sample_rate,
                input=True, frames_per_buffer=self.chunk_size,
                input_device_index=index,
            )
            s.close()
            return True
        except Exception:
            return False

    def list_input_devices(self):
        """List all input-capable microphones as [(index, raw_name), ...],
        one entry per physical device, excluding Windows' virtual capture
        devices (sound mapper wrappers, stereo mix, loopbacks). PortAudio
        repeats devices across host APIs, and Windows truncates MME device
        names to 31 chars; merge such truncated entries with the device's
        full-name entry. Finally, drop devices that cannot be opened at our
        sample rate right now (disconnected Bluetooth ghosts, dead jacks)."""
        devices = []
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0:
                    name = info.get("name", f"Device {i}")
                    if any(m in name.lower() for m in self._VIRTUAL_MARKERS):
                        continue
                    api_name = self.p.get_host_api_info_by_index(
                        info.get("hostApi", 0)
                    ).get("name", "")
                    is_modern = "wasapi" in api_name.lower() or "wdm-ks" in api_name.lower()
                    devices.append((i, name, is_modern))
            except Exception:
                continue
        seen = {}
        for i, name, is_modern in devices:
            key = name.lower()
            if key not in seen or (is_modern and not seen[key][2]):
                seen[key] = (i, name, is_modern)
        full_by_prefix = {}
        for i, name, _ in seen.values():
            if len(name) > 31:
                full_by_prefix.setdefault(self._dedupe_key(name), True)
        result = []
        for i, name, is_modern in seen.values():
            if len(name) == 31 and self._dedupe_key(name) in full_by_prefix:
                continue
            result.append((i, name, is_modern))
        return [(i, name) for i, name, _ in result
                if any(self._is_available(c) for c in self._device_candidates(name))]

    def _matches(self, wanted: str, candidate_name: str) -> bool:
        """True when candidate_name belongs to the wanted device. Handles
        case differences, Windows' 31-char MME name truncation, and the
        truncated name being used as the wanted string. Never matches two
        unrelated devices that merely share a name prefix: the truncation
        rule only applies when one name is exactly 31 chars and a prefix
        of the other."""
        w, c = wanted.lower(), candidate_name.lower()
        if w == c or w in c or c in w:
            return True
        return (len(c) == 31 and w.startswith(c)) or (len(w) == 31 and c.startswith(w))

    def _is_modern_index(self, index: int) -> bool:
        try:
            api_name = self.p.get_host_api_info_by_index(
                self.p.get_device_info_by_index(index).get("hostApi", 0)
            ).get("name", "")
            return "wasapi" in api_name.lower() or "wdm-ks" in api_name.lower()
        except Exception:
            return False

    def _device_candidates(self, name: str):
        """All PortAudio indices for a device name, modern host APIs
        (WASAPI/WDM-KS) first. A device appears once per host API, and only
        some entries accept our 16 kHz format (WASAPI often does not), so
        callers must try each until one opens. Scans the raw enumeration:
        the deduped list has only one entry per device."""
        if not name:
            return []
        candidates = []
        for i in range(self.p.get_device_count()):
            try:
                info = self.p.get_device_info_by_index(i)
                if info.get("maxInputChannels", 0) > 0 and self._matches(name, info.get("name", "")):
                    candidates.append(i)
            except Exception:
                continue
        modern = [i for i in candidates if self._is_modern_index(i)]
        return modern + [i for i in candidates if i not in modern]

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def _audio_callback(self, in_data, frame_count, time_info, status):
        if self.is_listening:
            audio_np = np.frombuffer(in_data, dtype=np.int16).copy()
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

        try:
            candidates = self._device_candidates(self.device_name)
            if self.device_name and not candidates:
                print(f"Warning: mic '{self.device_name}' not found, using the system default.")
            last_error = None
            opened_index = None
            for device_index in candidates:
                try:
                    self.stream = self.p.open(
                        format=pyaudio.paInt16,
                        channels=1,
                        rate=self.sample_rate,
                        input=True,
                        frames_per_buffer=self.chunk_size,
                        stream_callback=self._audio_callback,
                        input_device_index=device_index,
                    )
                    opened_index = device_index
                    break
                except Exception as e:
                    last_error = e
                    self.stream = None
            if self.stream is None:
                # No matching entry opened (or no device was selected):
                # fall back to the system default input device.
                if last_error:
                    print(f"Mic '{self.device_name}' could not be opened ({last_error}), trying the system default.")
                self.stream = self.p.open(
                    format=pyaudio.paInt16,
                    channels=1,
                    rate=self.sample_rate,
                    input=True,
                    frames_per_buffer=self.chunk_size,
                    stream_callback=self._audio_callback,
                )
            self.stream.start_stream()
            self.active_device = self._canonical_name(opened_index) \
                if opened_index is not None else self._default_device_name()
            print(f"Audio input device: {self.active_device}")
        except Exception as e:
            print(f"Error opening audio stream: {e}")
            self.is_listening = False
            self.stream = None
            self.active_device = "Unavailable"
            self._stop_event.set()

    def set_device(self, name: str):
        """Switch the microphone live (e.g. the headset used for TeamSpeak)."""
        name = name or ""
        if name == self.device_name and self.stream is not None:
            print(f"Microphone in use: {self.active_device}")
            return
        self.device_name = name
        self.stop()
        self.start()
        print(f"Microphone in use: {self.active_device}")

    def stop(self):
        self.is_listening = False
        if self.stream:
            self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            
        self._stop_event.set()
        if self.worker_thread and self.worker_thread.is_alive():
            try:
                self.queue.put_nowait(None) # Sentinel
            except queue.Full:
                pass
            self.worker_thread.join(timeout=1.0)
            if self.worker_thread.is_alive():
                print("Warning: Audio worker thread did not terminate.")
            self.worker_thread = None
            
        # Clear any remaining items in queue
        while True:
            try:
                self.queue.get_nowait()
            except queue.Empty:
                break

    def close(self):
        self.stop()
        if self.p:
            self.p.terminate()
            self.p = None
