import asyncio
import re
import threading
import time
import random
from app.conversation.state import StateManager, AppState
from app.audio.capture import AudioCapture
from app.wakeword.detector import WakeWordDetector
from app.stt.whisper_engine import STTEngine
from app.tts.kokoro_engine import TTSEngine
from app.opencode.client import OpenCodeClient
from app.config.settings import Config


class ConversationManager:
    _WAKE_PHRASE_RE = re.compile(
        r"^\s*(hey|ok|okay)?\s*(varonika|veronica|varonica|varunika|jarvis)[,\s!?.-]*",
        re.IGNORECASE,
    )
    def __init__(self, config: Config, state_manager: StateManager):
        self.config = config
        self.state = state_manager

        self.audio = AudioCapture(chunk_size=1280)
        self.wakeword = WakeWordDetector(config.wake_word_model, config.wake_word_threshold)
        self.stt = STTEngine(config.stt_model, config.energy_threshold, config.silence_timeout_ms / 1000.0, language=config.stt_language)
        self.tts = TTSEngine(voice=config.tts_voice, speed=config.tts_speed)
        self.opencode = OpenCodeClient()

        self.audio.add_callback(self._on_audio_chunk)
        self.ui_callback = None
        self._loop = None
        self._opencode_started = False
        self.hotkeys = None

        # Wire up streaming callbacks
        self.opencode.varonika_client.on_text_chunk = self._on_stream_text
        self.opencode.varonika_client.on_tool_start = self._on_tool_start

        self._stream_buffer = ""
        # Monotonic interrupt generation. A request captures the generation
        # when it starts and is considered interrupted iff it has moved since.
        # This avoids the stale-flag race where a cancelled request's error
        # arrives after a newer request already started.
        self._interrupt_gen = 0
        self._interrupt_lock = threading.Lock()

        # Post-answer follow-up window: after she answers she keeps listening
        # briefly; if the user says nothing, she goes back to sleep.
        self._follow_up_active = False
        self._follow_up_deadline = None
        self._follow_up_timeout = config.follow_up_timeout_ms / 1000.0

    def start(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self.tts.start_worker()
        self.audio.start()
        
        # Start dynamic noise floor calibration (e.g. 2 seconds)
        self.stt.start_calibration(duration_sec=2.0)
        
        self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
        # Start opencode asynchronously
        asyncio.ensure_future(self._start_opencode(), loop=self._loop)

    async def _start_opencode(self):
        try:
            await self.opencode.start()
            self._opencode_started = True
            model = await self.opencode.get_current_model()
            self._emit_ui("System", f"OpenCode connected.\nSession: {self.opencode.session_id}\nModel: {model}")
        except Exception as e:
            print(f"Failed to start OpenCode: {e}")
            self._emit_ui("System", f"OpenCode unavailable: {e}")
            self._opencode_started = False

    def set_ui_callback(self, cb):
        self.ui_callback = cb

    def activate_listening(self):
        """Enter listening mode from the hotkey: no follow-up timeout, waits as long as needed."""
        self._clear_follow_up()
        self.state.set_state(AppState.LISTENING)
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
        self.tts.stop_and_clear()
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.opencode.cancel(), self._loop)
        # Whatever was streaming is dead — tell the UI to drop the stream
        # cursors so the next answer starts a fresh block at document end.
        self._emit_ui("Varonika_stream_reset", "")

    def _emit_ui(self, source: str, message: str):
        if self.ui_callback:
            self.ui_callback(source, message)

    def _on_stream_text(self, chunk: str):
        """Called from the ACP client when a text chunk arrives from OpenCode."""
        # Chunks can straggle in after an interrupt while the cancel is in
        # flight. The answer is dead — never speak (or buffer) its tail.
        if self.state.current not in [AppState.THINKING, AppState.EXECUTING_TOOL, AppState.SPEAKING]:
            return
        self._stream_buffer += chunk
        self._emit_ui("Varonika_stream", chunk)

        # Buffer sentences for TTS
        sentences = re.split(r'(?<=[.!?])\s+', self._stream_buffer)
        if len(sentences) > 1:
            # All but the last are complete sentences
            for s in sentences[:-1]:
                clean = self._format_speech(s)
                if clean.strip():
                    self.tts.speak(clean.strip())
            self._stream_buffer = sentences[-1]

    def _on_tool_start(self, title: str, tool_call_id: str):
        self.state.set_state(AppState.EXECUTING_TOOL)
        self._emit_ui("System", f"Tool: {title}")

    def _on_audio_chunk(self, chunk):
        """Audio callback from the microphone — runs on the audio callback thread."""
        current = self.state.current

        # Wake word detection during idle/wakeword listening or speaking
        if current in [AppState.LISTENING_FOR_WAKEWORD, AppState.SPEAKING]:
            if self.stt.is_calibrating:
                # Calibration must consume real audio or it never completes:
                # it runs only while she listens for the wake word.
                self.stt.process_chunk(chunk)
            if self.wakeword.process_chunk(chunk):
                print("Wake word detected!")
                if current == AppState.SPEAKING:
                    self.interrupt()
                    self.state.set_state(AppState.INTERRUPTED)

                self._clear_follow_up()
                self.state.set_state(AppState.WAKEWORD_DETECTED)
                self._emit_ui("System", "Wake word detected!")
                self.tts.speak(random.choice(["Yes Boss", "Yes Sir"]))
                self.tts.signal_answer_end()
                self.state.set_state(AppState.LISTENING)
                self.stt.reset()
                return

            # Answer finished: once she actually stops talking, open the
            # follow-up listening window. (She shows "Speaking" while the
            # answer plays, not "Listening".)
            if current == AppState.SPEAKING and not self.tts.is_speaking():
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
                # Whisper inference is slow — never run it on the audio callback thread
                threading.Thread(target=self._transcribe_and_process, daemon=True).start()

    def _transcribe_and_process(self):
        """Transcribe the buffered audio off the audio thread, then handle the command."""
        text = self.stt.transcribe()
        if text is None:
            return  # transcription was invalidated (e.g. hotkey re-activation)
        
        # Remove Whisper noise/silence hallucinations like [BLANK_AUDIO] or (wind blowing)
        text = re.sub(r'\[.*?\]|\(.*?\)|\*.*?\*', '', text)
        
        text = self._WAKE_PHRASE_RE.sub("", text, count=1).strip()
        if not text:
            self._clear_follow_up()
            self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
            return

        print(f"User said: {text}")
        self._emit_ui("User", text)
        self.state.set_state(AppState.THINKING)

        # Send to OpenCode on the event loop
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(
                self._process_command(text), self._loop
            )

    def _return_after_interrupt(self):
        """Restore listening mode after an interrupted prompt (hotkey activation: no follow-up window)."""
        if self.state.current in [AppState.THINKING, AppState.EXECUTING_TOOL]:
            self._clear_follow_up()
            self.state.set_state(AppState.LISTENING)
            self.stt.reset()

    async def _process_command(self, text: str):
        with self._interrupt_lock:
            interrupt_gen = self._interrupt_gen
        if not self._opencode_started:
            self.tts.speak("OpenCode isn't available right now.")
            self.tts.signal_answer_end()
            self._emit_ui("Varonika", "OpenCode isn't available right now.")
            self._clear_follow_up()
            self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
            return
            
        # Check for context reset commands
        lower_text = text.lower().strip()
        reset_phrases = ["reset session", "forget everything", "clear history", "start over"]
        if any(phrase in lower_text for phrase in reset_phrases):
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

        self._stream_buffer = ""
        self.state.set_state(AppState.THINKING)

        try:
            full_response = await self.opencode.prompt(text)
        except Exception as e:
            with self._interrupt_lock:
                was_interrupted = self._interrupt_gen > interrupt_gen
            if was_interrupted:
                self._return_after_interrupt()
                return
            print(f"OpenCode error: {e}")
            self.tts.speak("Sorry, there was an error communicating with OpenCode.")
            self.tts.signal_answer_end()
            self._emit_ui("Varonika", f"Error: {e}")
            self._clear_follow_up()
            self.state.set_state(AppState.LISTENING_FOR_WAKEWORD)
            return

        with self._interrupt_lock:
            was_interrupted = self._interrupt_gen > interrupt_gen
        if was_interrupted:
            self._return_after_interrupt()
            return

        self.state.set_state(AppState.SPEAKING)

        # Flush any remaining buffered text to TTS
        if self._stream_buffer.strip():
            clean = self._format_speech(self._stream_buffer)
            if clean.strip():
                self.tts.speak(clean.strip())
            self._stream_buffer = ""
        # The answer is complete — the reverb tail may now run once the last
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

    def _format_speech(self, text: str) -> str:
        """Convert raw LLM output into speakable text."""
        # Remove code blocks
        text = re.sub(r'```[\s\S]*?```', ' I\'ve generated the code. ', text)
        # Remove inline code
        text = re.sub(r'`[^`]+`', ' code snippet ', text)
        # Remove markdown headers
        text = re.sub(r'#+\s*', '', text)
        # Remove markdown bold/italic
        text = re.sub(r'\*{1,3}(.*?)\*{1,3}', r'\1', text)
        # Remove markdown links, keep text
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        # Remove URLs
        text = re.sub(r'https?://\S+', 'a link', text)
        # Remove bullet points
        text = re.sub(r'^\s*[-*]\s+', '', text, flags=re.MULTILINE)
        # Collapse whitespace
        text = re.sub(r'\s+', ' ', text)
        return text.strip()

    async def stop_async(self):
        self.audio.stop()
        self.tts.stop()
        if self.hotkeys:
            self.hotkeys.stop()
        try:
            await asyncio.wait_for(self.opencode.stop(), timeout=1.0)
        except Exception:
            pass
