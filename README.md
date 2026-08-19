# Varonika

![CI](https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika/actions/workflows/ci.yml/badge.svg)
![Python Versions](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![License](https://img.shields.io/github/license/Mohammad-Faiz-Cloud-Engineer/Varonika)

Varonika is a hands free voice assistant for your PC. You say "Hey Varonika", she listens, asks OpenCode to do the work, and speaks the answer back to you.

She can open apps, search the web, read files, run commands, and answer questions. Voice processing runs on your machine; the LLM is whichever local or cloud provider OpenCode is configured to use. She runs in the background and only starts listening after you say the wake word.

## What it does

- Wake word detection ("Hey Varonika") so she only records your speech after you call her
- Speech to text with Whisper (local, no cloud)
- Talks to OpenCode, which runs on your machine too
- Text to speech with Kokoro, so you hear the answer, not just read it
- A small desktop window that shows what she is doing, what she heard, and what she said
- Live microphone selection: pick which mic she listens on (e.g. your headset) right from the window
- Hotkeys if you do not want to use your voice

## Requirements

- Windows, macOS, or Linux (Ubuntu)
- Python 3.11 or 3.12 (Python 3.13+ is not currently supported due to underlying dependency constraints)
- The `opencode` CLI installed and available on your PATH (this is the brain she talks to)

### Install OpenCode first

OpenCode is the brain behind Varonika. She has no built-in LLM of her own, so you must install and set up OpenCode before she can answer anything. Install it with one of these (pick the one for your package manager):

```bash
npm install -g opencode-ai
```

```bash
bun install -g opencode-ai
```

```bash
yarn global add opencode-ai
```

```bash
pnpm install -g opencode-ai
```

Once installed, configure which LLM OpenCode should use (a cloud provider, or a local model via LM Studio, see [LMStudio.md](Setup%20Docs/LMStudio.md)).

> **Note for Linux Users:** On Linux (Ubuntu), Python 3.12 is currently not supported. This is because the `openwakeword` dependency requires `tflite-runtime` on Linux, which does not have pre-built wheels for Python 3.12. Please use Python 3.11 on Linux.

## Setup

```bash
pip install -e .
```

Varonika needs a few models before she can hear and speak. The app downloads them automatically on first start, or you can do it yourself:

```bash
python scripts/download_models.py
```

This fetches:

- `models/ggml-small.en.bin` (Whisper speech to text model)
- `models/wakeword.onnx` (wake word model)

If the tool fails to download the speech-to-text model (`ggml-small.en`), [download the model](https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika/releases/download/ggml-small.en/ggml-small.en.bin).

After downloading, copy or move the model to:

`Varonika/models/`

Then start the tool with:

```bash
python app/main.py
```

If you have your own trained wake word model, drop it at the project root as `Hey_Varonika.onnx` and the script will copy it into place. Without a custom model, the script downloads a placeholder that responds to "Hey Jarvis" instead.

To choose which LLM she uses (including your own custom model), see [LLM_SETUP.md](Setup%20Docs/LLM_SETUP.md).

## Running

```bash
python app/main.py
```

First launch checks the models, then starts the desktop window and the background listener. You will see "Hotkeys registered" in the console when she is ready.

## Talking to her

1. Say "Hey Varonika". She answers "Yes Boss" (or "Yes Sir") to confirm she is listening.
2. Speak your request. She shows what she heard on screen, then sends it to OpenCode.
3. She speaks the answer while it is displayed in the window.

Wait for her "Yes Boss" ack before speaking, otherwise the start of your command is clipped while she is talking.

You can interrupt her while she is talking by saying the wake word again.

After she answers she keeps listening for a short follow-up question. If you stay quiet for about 2 seconds (see `follow_up_timeout_ms`), she stops listening and goes back to sleep until you say the wake word again.

### Hotkeys

- `Alt+Space`: activate listening mode without using the wake word

## Configuration

All settings have sensible defaults, but you can create a `config.yaml` next to the project root to override them:

```yaml
wake_word_threshold: 0.6           # higher = harder to trigger
stt_model: "models/ggml-small.en.bin"
stt_language: "en"
silence_timeout_ms: 2500           # pause before she stops listening
energy_threshold: 0.015            # mic sensitivity; auto-calibrated at startup, this value only applies until calibration completes
tts_voice: "af_bella"              # Kokoro voice
tts_speed: 0.9                     # below 1.0 speaks slower and more clearly
tts_volume: 1.0                    # TTS loudness boost, 0.5x to 5.0x (slider in the window too)
follow_up_timeout_ms: 2000         # after an answer, go back to sleep if you stay silent this long
mic_device: ""                     # e.g. "Headset Microphone"; empty = Windows default input device
```

## How it fits together

- `app/audio/capture.py` reads microphone audio in small chunks
- `app/wakeword/detector.py` watches those chunks for the wake word
- `app/stt/whisper_engine.py` turns your speech into text
- `app/opencode/client.py` talks to OpenCode over the ACP protocol
- `app/conversation/manager.py` runs the state machine and ties it all together
- `app/tts/kokoro_engine.py` turns the answer into spoken audio
- `app/hotkeys/listener.py` listens for the Alt+Space hotkey
- `app/ui/main_window.py` is the little status window

## Troubleshooting

**She hears herself and answers her own voice.** This should not happen anymore. She refuses to transcribe while she is speaking (and for a fraction of a second afterwards, so the speaker's echo in the room is ignored too), and the "Yes Boss" ack after the wake word is not transcribed.

**OpenCode stops responding after a big answer.** This was a bug in the data line limit. The connection now allows very large messages, so long tool results no longer kill the link.

**Nothing happens when you say the wake word.** Check that the console shows the wake word model loaded, and that the window's mic dropdown points at the mic you are actually speaking into (use "System Default" to let Windows decide). If you are using the placeholder model, you must say "Hey Jarvis".

## Notes

The first run downloads the Kokoro voice model and may take a little while. Be patient, she warms up.

## License

BSD 2-Clause License. Copyright (c) 2026, Mohammad Faiz. See [LICENSE](LICENSE) for the full text.
