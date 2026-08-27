import asyncio
import random
import re
import threading
import time

from app.audio.capture import AudioCapture
from app.config.settings import Config, save_config_field
from app.conversation.state import AppState, StateManager
from app.formatting import latex_to_text
from app.opencode.client import OpenCodeClient
from app.stt.whisper_engine import STTEngine
from app.tts.kokoro_engine import TTSEngine
from app.wakeword.detector import WakeWordDetector
import contextlib


class ConversationManager:
    _WAKE_PHRASE_RE = re.compile(
        r"^[^a-zA-Z0-9]*(hey|ok|okay)?\s*(varonika|veronica|varonica|varunika|veronika|jarvis)[^a-zA-Z0-9]*",
        re.IGNORECASE,
    )
    # Whole-utterance only. A substring match would wipe the session when
    # the user says something like "start over from the second paragraph".
    _RESET_SESSION_RE = re.compile(
        r"^\s*(please\s+)?(reset session|forget everything|clear history|start over)\s*[.!]?\s*$",
        re.IGNORECASE,
    )

    def __init__(self, config: Config, state_manager: StateManager):
        self.config = config
        self.state = state_manager

        self.audio = AudioCapture(chunk_size=1280, device_name=config.mic_device)
        self.wakeword = WakeWordDetector(config.wake_word_model, config.wake_word_threshold)
        self.stt = STTEngine(config.stt_model, config.energy_threshold, config.silence_timeout_ms / 1000.0, language=config.stt_language)
        self.tts = TTSEngine(voice=config.tts_voice, speed=config.tts_speed, volume=config.tts_volume)
        self.opencode = OpenCodeClient()

        self.audio.add_callback(self._on_audio_chunk)
        # Both the wake word and the STT consume the same single microphone
        # stream; when that mic cannot be opened the app falls back to the
        # system default, and this surfaces that switch in the UI.
        self.audio.on_fallback = self._on_mic_fallback
        self.ui_callback = None
        self._loop = None
        self._opencode_started = False
        self.hotkeys = None

        # Wire up streaming callbacks
        self.opencode.varonika_client.on_text_chunk = self._on_stream_text
        self.opencode.varonika_client.on_tool_start = self._on_tool_start
        self.opencode.varonika_client.on_tool_update = self._on_tool_update
        # Connection-state changes (connect, disconnect, reconnect) update
        # the UI and the started flag, so the "OpenCode connected" message
        # is revoked when the connection drops instead of staying stale.
        self.opencode.on_status_change = self._on_opencode_status

        self._stream_buffer = ""
        self._seen_tool_ids: set[str] = set()
        # Monotonic interrupt generation. A request captures the generation
        # when it starts and is considered interrupted iff it has moved since.
        # This avoids the stale-flag race where a cancelled request's error
        # arrives after a newer request already started.
        self._interrupt_gen = 0
        self._interrupt_lock = threading.Lock()
        # Sequence of started requests. A request captures its sequence when
        # it starts; only the newest request may restore the state machine
        # after an interrupt. Without this, a slow ACP cancel can unwind a
        # stale request after a newer one already started (and is waiting on
        # the prompt lock in THINKING), and the stale request's
        # _return_after_interrupt would yank the new request to LISTENING,
        # silently dropping its answer.
        self._request_seq = 0

        self._stream_lock = threading.Lock()

        # Post-answer follow-up window: after she answers she keeps listening
        # briefly; if the user says nothing, she goes back to sleep.
        self._follow_up_active = False
        self._follow_up_deadline = None
        self._follow_up_timeout = config.follow_up_timeout_ms / 1000.0

        # True while a prompt is streaming to TTS. The audio callback must
        # not treat "TTS momentarily idle" as "answer over" and flip the
        # state machine out of SPEAKING: the LLM pauses between sentences
        # (and before the first sentence is buffered), during which the
        # queue is legitimately empty. Without this, streamed chunks get
        # dropped mid-answer.
        self._answer_in_flight = False
        self._active_task = None

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self.tts.start_worker()
        self.audio.start()
        # One stream feeds both consumers: the wake word and the STT can
        # never hear different microphones.
        print(f"Wake word and STT listening on: {self.audio.active_device}")

        # Start dynamic noise floor calibration (e.g. 2 seconds)
        self.stt.start_calibration(duration_sec=2.0)

        self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
        if self.stt.model is None:
            self._emit_ui(
                "System",
                "Speech-to-text failed to load. Put ggml-small.en.bin in the models folder, then restart.",
            )
        if self.wakeword.model is None:
            self._emit_ui(
                "System",
                "Wake word failed to load. Use Alt+Space to talk until the model is in place.",
            )
        if self.tts.pipeline is None:
            self._emit_ui(
                "System",
                "Voice playback failed to load. Answers will still show in the window.",
            )
        # Start opencode asynchronously
        asyncio.ensure_future(self._start_opencode(), loop=self._loop)

    async def _start_opencode(self):
        try:
            await self.opencode.start()
        except Exception as e:
            print(f"Failed to start OpenCode: {e}")
            self._emit_ui("System", f"OpenCode unavailable: {e}")
            self._opencode_started = False
            # Keep trying in the background: a transient failure (or opencode
            # installed later) self-heals without a restart, and the client
            # reports the successful reconnect through on_status_change.
            asyncio.ensure_future(self.opencode.ensure_connected())

    def _on_opencode_status(self, message: str, connected: bool):
        """Called by the OpenCode client on every connect/disconnect/reconnect."""
        self._opencode_started = connected
        self._emit_ui("System", message)

    def set_ui_callback(self, cb):
        self.ui_callback = cb

    def set_mic_device(self, name: str, persist: bool = True):
        """Switch the microphone the wake word and STT listen on (live).

        Persists the choice unless persist=False: automatic fallbacks
        (device vanished, every mic failed) must not overwrite the user's
        saved preference with "" on a transient Bluetooth dropout."""
        self.audio.set_device(name)
        # Drop audio buffered from the old mic and invalidate any in-flight
        # transcription: words recorded on the previous device must never be
        # recognized as the user's command after the switch.
        self.stt.reset()
        self.wakeword.reset()
        if persist:
            self.config.mic_device = name
            save_config_field("mic_device", name)

    def _on_mic_fallback(self, requested: str, actual: str):
        print(f"Mic '{requested}' unavailable; wake word and STT now listen on '{actual}'.")
        self._emit_ui(
            "System",
            f"Mic '{requested}' could not be opened, so I am using '{actual}' instead. "
            f"Wake word and STT both listen on '{actual}'.",
        )

    def activate_listening(self):
        """Enter listening mode from the hotkey: no follow-up timeout, waits as long as needed."""
        self._clear_follow_up()
        self.state.set_state(AppState.LISTENING)
        self.stt.discard_calibration_progress()
        self.stt.reset()

    def _arm_follow_up(self):
        """After an answer, listen briefly for a follow-up, then go back to sleep."""
        self._follow_up_active = True
        self._follow_up_deadline = None

    def _clear_follow_up(self):
        self._follow_up_active = False
        self._follow_up_deadline = None

    def interrupt(self):
        """Stop speech and cancel any in-flight OpenCode request."""
        with self._interrupt_lock:
            self._interrupt_gen += 1
            # The answer is dead: the audio callback may flip out of SPEAKING
            # again. The generation-checked finally of the stale prompt task
            # will not lower it, so an interrupt must: a stale-True flag would
            # leave the state machine stuck in SPEAKING (no speech, no flip).
            self._answer_in_flight = False
        self.tts.stop_and_clear()
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._cancel_active_task)
        # Whatever was streaming is dead: tell the UI to drop the stream
        # cursors so the next answer starts a fresh block at document end.
        self._emit_ui("Varonika_stream_reset", "")

    def _start_command_task(self, text: str):
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._create_task_on_loop, text)

    def _create_task_on_loop(self, text: str):
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        self._active_task = asyncio.create_task(self._process_command(text))

    def _cancel_active_task(self):
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
        asyncio.create_task(self.opencode.cancel())

    def _emit_ui(self, source: str, message: str):
        if self.ui_callback:
            self.ui_callback(source, message)

    def _on_stream_text(self, chunk: str):
        """Called from the ACP client when a text chunk arrives from OpenCode."""
        # Chunks can straggle in after an interrupt while the cancel is in
        # flight. The answer is dead: never speak (or buffer) its tail. The
        # state alone is not enough: right after an interrupt the state is
        # still THINKING/SPEAKING, so a straggler would pass the state check
        # and speak the cancelled answer's tail. _answer_in_flight is False
        # the moment an interrupt (or the answer's own finally) runs, and it
        # only goes True again when the next answer starts streaming.
        if not self._answer_in_flight:
            return
        # The ACP server ignores cancels: a cancelled request keeps streaming
        # until its prompt completes. If a NEWER request already started, the
        # streamed chunk belongs to the cancelled answer, not to the newer
        # one (which is still waiting on the prompt lock). Without this
        # check the cancelled answer's tail would be spoken as the new
        # answer and flip the state machine out of THINKING. _stream_seq is
        # set by OpenCodeClient.prompt() right before the request is sent.
        if self.opencode.stream_seq != self._request_seq:
            return
        if self.state.current not in [AppState.THINKING, AppState.EXECUTING_TOOL, AppState.SPEAKING]:
            return

        if self.state.current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            self.state.set_state(AppState.SPEAKING)

        with self._stream_lock:
            self._stream_buffer += chunk
            self._emit_ui("Varonika_stream", chunk)

            # Strip complete code blocks and inline code from the TTS buffer
            # so they don't mess up sentence splitting.
            while True:
                match = re.search(r'```[\s\S]*?```', self._stream_buffer)
                if not match:
                    break
                self._stream_buffer = self._stream_buffer[:match.start()] + " I've generated the code. " + self._stream_buffer[match.end():]

            while True:
                match = re.search(r'`[^`]+`', self._stream_buffer)
                if not match:
                    break
                self._stream_buffer = self._stream_buffer[:match.start()] + " code snippet " + self._stream_buffer[match.end():]

            # Check if there is an open code block (starts with ``` but not closed)
            open_code_idx = self._stream_buffer.find('```')
            if open_code_idx != -1:
                safe_text = self._stream_buffer[:open_code_idx]
                unsafe_text = self._stream_buffer[open_code_idx:]
            else:
                # Check for open inline code
                open_inline_idx = self._stream_buffer.find('`')
                if open_inline_idx != -1:
                    safe_text = self._stream_buffer[:open_inline_idx]
                    unsafe_text = self._stream_buffer[open_inline_idx:]
                else:
                    safe_text = self._stream_buffer
                    unsafe_text = ""

            # Buffer sentences for TTS. We only split on major punctuation and newlines
            # to ensure the chunks are large enough. We preserve newlines so Kokoro
            # can use them for pacing.
            sentences = re.split(r'(?<=[.!?])[ \t]+|(?<=\n)', safe_text)

            if len(sentences) > 1:
                # Combine tiny fragments (like short bullet points) into
                # larger chunks. Every chunk pays a fixed synthesis tax
                # (phonemization + model warmup), so fewer, longer chunks
                # keep the TTS producer ahead of playback and avoid pauses
                # at chunk boundaries.
                combined = []
                current = ""
                for s in sentences[:-1]:
                    current += s + " "
                    if len(current.strip()) >= 150:
                        combined.append(current.strip())
                        current = ""

                # If there's leftover combined text, it's a complete parsed
                # clause: flush it as a chunk even if it's below the
                # threshold (the LLM's next sentence may be slow to arrive).
                if current.strip():
                    combined.append(current.strip())

                for s in combined:
                    clean = self._format_speech(s)
                    if clean.strip():
                        # Re-check after formatting: interrupt() can land
                        # between the start-of-callback guards and speak(),
                        # and would otherwise enqueue the cancelled tail on
                        # the new TTS worker.
                        with self._interrupt_lock:
                            live = self._answer_in_flight
                        if not live or self.opencode.stream_seq != self._request_seq:
                            return
                        self.tts.speak(clean.strip())

                self._stream_buffer = sentences[-1] + unsafe_text
            else:
                self._stream_buffer = safe_text + unsafe_text

    def _on_tool_start(self, title: str, tool_call_id: str, *,
                        kind: str | None = None, raw_input: dict | None = None):
        # After an interrupt the cancelled prompt keeps running (ACP often
        # ignores cancel). Its tool events still carry the old stream_seq,
        # which still equals _request_seq until a newer prompt starts.
        # Without this guard they yank LISTENING into EXECUTING_TOOL and
        # STT silently stops until the stale prompt finally unwinds.
        if not self._answer_in_flight:
            return
        # A stale request's tool events must not drive the state machine or
        # the UI after a newer request took over (same rule as _on_stream_text).
        if self.opencode.stream_seq != self._request_seq:
            return
        self.state.set_state(AppState.EXECUTING_TOOL)

    def _on_tool_update(self, tool_call_id: str, *,
                        title: str | None = None, kind: str | None = None,
                        raw_input: dict | None = None,
                        locations=None, status: str | None = None):
        if not self._answer_in_flight:
            return
        if self.opencode.stream_seq != self._request_seq:
            return
        # Only emit the first in_progress update per tool call.
        # The first ToolCallProgress carries the real data (command, file path).
        # Subsequent in_progress updates repeat the same data.
        if status != "in_progress":
            return
        if tool_call_id in self._seen_tool_ids:
            return
        self._seen_tool_ids.add(tool_call_id)
        desc = self._tool_description_from_progress(title, kind, raw_input, locations)
        if desc:
            self.state.set_state(AppState.EXECUTING_TOOL)
            self._emit_ui("System", desc)

    @staticmethod
    def _tool_description_from_progress(
        title: str | None, kind: str | None,
        raw_input: dict | None, locations=None,
    ) -> str:
        """Build a human-readable one-liner from ToolCallProgress data."""
        if raw_input is None:
            raw_input = {}
        try:
            if kind == "execute":
                cmd = raw_input.get("command", "") or (title or "command")
                return f"Running: {cmd[:80]}{'...' if len(cmd) > 80 else ''}"
            if kind == "read":
                path = raw_input.get("filePath", "") or raw_input.get("path", "")
                if not path and locations:
                    path = getattr(locations[0], "path", "") or ""
                return f"Reading: {path}" if path else f"Tool: {title or 'read'}"
            if kind == "edit":
                path = raw_input.get("filePath", "") or raw_input.get("path", "")
                if not path and locations:
                    path = getattr(locations[0], "path", "") or ""
                return f"Editing: {path}" if path else f"Tool: {title or 'edit'}"
            if kind == "search":
                pattern = raw_input.get("pattern", "")
                return f"Searching: {pattern}" if pattern else f"Tool: {title or 'search'}"
            if kind == "fetch":
                url = raw_input.get("url", "")
                return f"Fetching: {url[:80]}{'...' if len(url) > 80 else ''}" if url else f"Fetching: {title}" if title else "Fetching..."
            if kind == "think":
                return "Thinking..."
        except Exception:
            pass
        return f"Tool: {title}" if title else ""

    def _on_audio_chunk(self, chunk):
        """Audio callback from the microphone: runs on the audio callback thread."""
        current = self.state.current

        # Wake word detection during idle/wakeword listening or speaking
        if current in [AppState.LISTENING_FOR_WAKEWORD, AppState.SPEAKING]:
            # Room-noise only: never while she is talking (speaker bleed
            # would raise the threshold and she would go deaf), and never
            # while the user is being transcribed (that used to hijack STT).
            # Wake word first: the trigger chunk (and the utterance that
            # led to it) must not be treated as room noise.
            if self.wakeword.process_chunk(chunk):
                print("Wake word detected!")
                if current == AppState.SPEAKING:
                    self.interrupt()

                self._clear_follow_up()
                self._emit_ui("System", "Wake word detected!")
                self.tts.signal_answer_start()
                self.tts.speak(random.choice(["Yes Boss", "Yes Sir"]))
                self.tts.signal_answer_end()
                self.state.set_state(AppState.LISTENING)
                self.stt.discard_calibration_progress()
                self.stt.reset()
                return
            if (
                self.stt.is_calibrating
                and current == AppState.LISTENING_FOR_WAKEWORD
                and not self.tts.is_speaking()
            ):
                self.stt.feed_calibration(chunk)

            # Answer finished: once she actually stops talking, open the
            # follow-up listening window. (She shows "Speaking" while the
            # answer plays, not "Listening".) The in-flight flag keeps her
            # in SPEAKING while a prompt is still streaming to TTS: between
            # sentences the queue is legitimately empty, and flipping out of
            # SPEAKING here would drop the remaining streamed chunks.
            if (current == AppState.SPEAKING and not self.tts.is_speaking()
                    and not self._answer_in_flight):
                if self._follow_up_active:
                    self.state.set_state(AppState.LISTENING)
                    self.stt.reset()
                else:
                    self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)

        # STT during active listening
        if current == AppState.LISTENING:
            if self.tts.is_speaking():
                self.stt.reset()
                return  # echo guard: don't transcribe our own speech

            # Follow-up window: after an answer she listens for a short while.
            # Any speech cancels the window; silence past the deadline puts her
            # back to sleep. Her own voice never reaches this code: the TTS
            # echo guard stays up for ~300ms after playback (reverb tail).
            if self._follow_up_active:
                if self._follow_up_deadline is None:
                    self._follow_up_deadline = time.monotonic() + self._follow_up_timeout
                elif self.stt.speech_seen:
                    self._clear_follow_up()
                elif time.monotonic() > self._follow_up_deadline:
                    self._clear_follow_up()
                    self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                    self.stt.reset()
                    return

            ready = self.stt.process_chunk(chunk)
            if ready:
                self.state.set_state(AppState.TRANSCRIBING)
                # Whisper inference is slow: never run it on the audio callback
                # thread. Daemon so a long transcribe cannot block process exit.
                threading.Thread(
                    target=self._transcribe_and_process, daemon=True
                ).start()

    def _transcribe_and_process(self):
        """Transcribe the buffered audio off the audio thread, then handle the command."""
        start_gen = self.stt.snapshot_generation()
        try:
            if self.stt.model is None:
                self.stt.reset()
                self._emit_ui(
                    "System",
                    "I heard you, but speech-to-text is not loaded. Check the models folder.",
                )
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                return
            text = self.stt.transcribe()
            if text is None:
                return  # transcription was invalidated (e.g. hotkey re-activation)

            # Remove Whisper noise/silence hallucinations like [BLANK_AUDIO] or (wind blowing).
            # Only strip Whisper-style brackets, not all parenthesized text
            # (which would remove legitimate content like "The quick (brown) fox").
            # Bracket tags: typical sound tags (BLANK_AUDIO, SOUND, MUSIC, whistling, etc.)
            # and dot/ellipsis patterns ([...], [. .]). We match any letters/spaces inside.
            text = re.sub(r'\[(?:[a-zA-Z_ -]+|\.[\.\s]*)\]', '', text)
            # Parenthetical tags: common Whisper hallucination phrases.
            text = re.sub(r'\((?:BLANK_AUDIO|CROSSTALK|silence|wind|music|sigh|laughs|applause|cheering|whistling|breathing|coughs|throat clearing)\)', '', text, flags=re.IGNORECASE)

            text = self._WAKE_PHRASE_RE.sub("", text, count=1).strip()
            if not text:
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                return

            print(f"User said: {text}")
            self._emit_ui("User", text)
            self.state.set_state(AppState.THINKING)

            # Send to OpenCode on the event loop
            if not self._loop or self._loop.is_closed():
                self._emit_ui("System", "Cannot send the command; the app is shutting down.")
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                return
            self._start_command_task(text)
        except Exception as e:
            print(f"Transcription error: {e}")
        finally:
            # Only the transcription that still owns this generation may
            # unwind TRANSCRIBING. A stale one that lost a reset/hotkey must
            # not yank a newer listen/transcribe back to sleep.
            if (self.state.current == AppState.TRANSCRIBING
                    and start_gen == self.stt.current_generation):
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)

    def _return_after_interrupt(self, request_seq: int):
        """Restore listening mode after an interrupted prompt (hotkey activation: no follow-up window).

        Only the newest request may restore: a stale request unwinding after a
        newer one started must not move the state machine out from under it.
        """
        if request_seq != self._request_seq:
            return
        if self.state.current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            self._clear_follow_up()
            self.state.set_state(AppState.LISTENING)
            self.stt.reset()

    async def _process_command(self, text: str):
        with self._interrupt_lock:
            interrupt_gen = self._interrupt_gen
            self._request_seq += 1
            request_seq = self._request_seq
        if not self.opencode.is_connected():
            # Live check: also covers a connection that dropped while idle
            # and whose background reconnect has not finished yet. An
            # interrupt landing while we reconnect must not leave the state
            # machine stuck in THINKING.
            try:
                ok = await self.opencode.ensure_connected()
            except asyncio.CancelledError:
                self._return_after_interrupt(request_seq)
                return
            except Exception:
                ok = False
            if not ok:
                self.tts.speak("OpenCode isn't available right now.")
                self.tts.signal_answer_end()
                self._emit_ui("Varonika", "OpenCode isn't available right now.")
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                return

        # Check for context reset commands
        if self._RESET_SESSION_RE.match(text):
            self._emit_ui("System", "Resetting OpenCode context...")
            try:
                # Tell OpenCode to start a new session
                await self.opencode.reset_session()
                self.tts.speak("I have cleared my memory for a fresh start.")
                self.tts.signal_answer_end()
                model = await self.opencode.get_current_model()
                self._emit_ui("System", f"Session reset successfully.\nNew Session: {self.opencode.session_id}\nModel: {model}")
            except Exception as e:
                self.tts.speak("I couldn't reset the session.")
                self.tts.signal_answer_end()
                self._emit_ui("System", f"Reset failed: {e}")

            self._arm_follow_up()
            self.state.set_state(AppState.SPEAKING)
            self.stt.reset()
            return

        with self._stream_lock:
            self._stream_buffer = ""
        self._seen_tool_ids.clear()
        # A fresh answer: the reverb tail must not fire until the final
        # flush below. Without this, a stale end signal (e.g. from the
        # "Yes Boss" ack) lets the echo guard drop mid-answer, the state
        # machine moves out of SPEAKING, and streamed chunks get dropped.
        self.tts.signal_answer_start()
        self._answer_in_flight = True
        self.state.set_state(AppState.THINKING)

        try:
            try:
                full_response = await self.opencode.prompt(text, stream_seq=request_seq)
            except asyncio.CancelledError:
                # An ACP cancel can kill the in-flight prompt task with
                # CancelledError (a BaseException in Python 3.11+, so the
                # generic except below would never see it). Without this
                # branch the task would die silently and the state machine
                # would stick in THINKING forever: no wake word, no hotkey,
                # no recognition. The request is dead either way, so restore
                # listening mode.
                self._return_after_interrupt(request_seq)
                return
            except Exception as e:
                with self._interrupt_lock:
                    was_interrupted = self._interrupt_gen > interrupt_gen
                if was_interrupted:
                    self._return_after_interrupt(request_seq)
                    return
                print(f"OpenCode error: {e}")
                if self.opencode.is_disconnected():
                    # The connection broke mid-answer. Bring it back and say
                    # the answer is lost; never pretend the stale "connected"
                    # state still holds.
                    try:
                        ok = await self.opencode.ensure_connected()
                    except Exception:
                        ok = False
                    if ok:
                        self.tts.speak("OpenCode lost its connection. I am back online, please say that again.")
                    else:
                        self.tts.speak("OpenCode lost its connection and is still unavailable.")
                else:
                    self.tts.speak("Sorry, there was an error communicating with OpenCode.")
                self.tts.signal_answer_end()
                self._emit_ui("Varonika", f"Error: {e}")
                self._clear_follow_up()
                self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
                return

            with self._interrupt_lock:
                was_interrupted = self._interrupt_gen > interrupt_gen
            if was_interrupted:
                self._return_after_interrupt(request_seq)
                return

            self.state.set_state(AppState.SPEAKING)

            # Flush any remaining buffered text to TTS
            with self._stream_lock:
                if self._stream_buffer.strip():
                    clean = self._format_speech(self._stream_buffer)
                    with self._interrupt_lock:
                        live = self._answer_in_flight
                    if live and clean.strip() and self.opencode.stream_seq == request_seq:
                        self.tts.speak(clean.strip())
                    self._stream_buffer = ""
            # The answer is complete: the reverb tail may now run once the last
            # sentence has played. Without this, the tail would fire mid-answer
            # every time the LLM pauses between sentences.
            self.tts.signal_answer_end()

            # Show full response in UI
            self._emit_ui("Varonika", full_response)

            # Listen briefly for a follow-up once she finishes speaking, then go
            # back to wake word mode. She shows "Speaking" while the answer plays;
            # the audio callback switches her to "Listening" when TTS goes idle.
            self._arm_follow_up()
            self.stt.reset()
        finally:
            # Only this task may lower the flag. If an interrupt moved the
            # generation, this answer is dead and a newer answer may already
            # be streaming: lowering the flag here would let the audio
            # callback flip out of SPEAKING mid-answer and drop its chunks
            # (a slow ACP cancel can unwind a stale task after a newer
            # prompt already started). A stale-True flag is harmless: the
            # flip only applies in SPEAKING, and every new answer re-arms
            # it before streaming.
            with self._interrupt_lock:
                if interrupt_gen == self._interrupt_gen:
                    self._answer_in_flight = False

    def _format_speech(self, text: str) -> str:
        """Convert raw LLM output into speakable text."""
        # Rewrite LaTeX math into readable text (Greek letters, fractions,
        # superscripts) so she does not speak "dollar tau equals..."
        text = latex_to_text(text)
        # A streaming chunk can end in the middle of math, leaving a lone
        # '$' behind or an unmapped LaTeX command. Drop leftover '$' and
        # '^' that survived the LaTeX conversion. Without this, she says
        # "dollar" for every unmatched delimiter. Only remove '$' NOT
        # followed by a digit, so dollar amounts like "$100" survive.
        text = re.sub(r'\$(?![0-9])', '', text)
        text = text.replace('^', '')
        text = re.sub(r'\\([a-zA-Z]+)', r'\1', text)
        # Remove markdown headers. Anchored to the line start so inline '#'
        # characters are kept (without this, "C#" would be spoken as "C").
        text = re.sub(r'(?m)^\s*#+\s*', '', text)
        # Remove markdown bold/italic
        text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
        # Remove markdown links, keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove URLs
        text = re.sub(r'https?://\S+', 'a link', text)
        # Remove bullet points
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
        # Collapse spaces and tabs, but keep newlines for TTS pacing
        text = re.sub(r'[ \t]+', ' ', text)
        return text.strip()

    async def stop_async(self):
        if self._active_task and not self._active_task.done():
            self._active_task.cancel()
            with contextlib.suppress(Exception):
                await self._active_task
        self.audio.close()
        self.tts.stop()
        if self.hotkeys:
            self.hotkeys.stop()
        with contextlib.suppress(Exception):
            await asyncio.wait_for(self.opencode.stop(), timeout=1.0)
