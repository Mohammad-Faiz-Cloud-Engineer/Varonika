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

- Windows, macOS, or Linux (Ubuntu/Debian/Arch/Fedora)
- Python 3.11 or 3.12 (Python 3.12+ not supported on Linux due to `openwakeword`; 3.13+ unsupported on all platforms)
- The `opencode` CLI installed and available on your PATH (this is the brain she talks to)

### Windows: Quick install with winget
```powershell
winget install Python.Python.3.12
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

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

Once installed, configure which LLM OpenCode should use: a cloud provider, or a local model via [Ollama](Setup%20Docs/OLLAMA_SETUP.md) or [LM Studio](Setup%20Docs/LMStudio.md).

> **Note for Linux Users:** On Linux, Python 3.12 is not supported because the `openwakeword` dependency requires `tflite-runtime`, which has no pre-built wheels for Python 3.12 on Linux. Use **Python 3.11**. Install it via your package manager (`apt install python3.11 python3.11-venv python3.11-dev` on Ubuntu/Debian) or pyenv, not from python.org.

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
- `models/melspectrogram.onnx` (wake word support model)
- `models/embedding_model.onnx` (wake word support model)

If the tool fails to download the speech-to-text model (`ggml-small.en`), [download the model](https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika/releases/download/ggml-small.en/ggml-small.en.bin).

After downloading, copy or move the model to:

`Varonika/models/`

Then start the tool with:

```bash
python app/main.py
```

If you have your own trained wake word model, drop it at the project root as `Hey_Varonika.onnx` and the script will copy it into place. The wake word model included in this repo responds to "Hey Varonika", but wake word models are trained on one voice, so it may not hear yours; if she never responds, press **Alt+Space** instead. (A "Hey Jarvis" placeholder is fetched only if the model file is missing.)

To choose which LLM she uses (including your own custom model), see [LLM_SETUP.md](Setup%20Docs/LLM_SETUP.md).

## Setup guides

All setup guides live in the [Setup Docs](Setup%20Docs/) folder:

- [SETUP.md](Setup%20Docs/SETUP.md): the full from-zero setup guide (Python, OpenCode, Varonika)
- [LLM_SETUP.md](Setup%20Docs/LLM_SETUP.md): choose which LLM she uses, cloud or custom
- [OLLAMA_SETUP.md](Setup%20Docs/OLLAMA_SETUP.md): run a free local LLM with Ollama
- [LMStudio.md](Setup%20Docs/LMStudio.md): run a local LLM with LM Studio
- [PLAYWRIGHT_SETUP.md](Setup%20Docs/PLAYWRIGHT_SETUP.md): give her browser control with Playwright
- [CHROME_DEVTOOLS_SETUP.md](Setup%20Docs/CHROME_DEVTOOLS_SETUP.md): test websites in a real Chrome with Chrome DevTools MCP
- [GOOGLE_MCP_SETUP.md](Setup%20Docs/GOOGLE_MCP_SETUP.md): give her access to your Gmail, Calendar, Drive, Docs, and Sheets
- [MEMORY_SETUP.md](Setup%20Docs/MEMORY_SETUP.md): give her a memory so she remembers you and past fixes between sessions

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

All settings have sensible defaults, but you can create a `config.yaml` in the project root to override them:

```yaml
wake_word_threshold: 0.6           # higher = harder to trigger; lower to 0.5 if she does not trigger
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

**Nothing happens when you say the wake word.** Say "Hey Varonika" (that is what the included model hears). Check that the console shows the wake word model loaded, and that the window's mic dropdown points at the mic you are actually speaking into (use "System Default" to let Windows decide). Still silent? Lower `wake_word_threshold` to 0.5 in `config.yaml`, and check Windows microphone privacy below.

**She never hears you at all (wake word and voice both dead).** Windows may be blocking microphone access for desktop apps. Check Settings -> Privacy & security -> Microphone, allow desktop apps to access the mic, then restart Varonika.

**The window says "OpenCode unavailable".** The `opencode` command was not found on the PATH of the terminal that started Varonika. Install it (`npm install -g opencode-ai`), close and reopen the terminal, then start Varonika again.

**She connects but answers nothing.** OpenCode has no AI model configured. Run `opencode`, type `/connect`, add a provider (or Ollama, see the guides), then restart Varonika.

**Model download fails or times out on first start.** Run `python scripts/download_models.py` manually and let it finish, then start Varonika. A slow connection takes a while: the Whisper model alone is about 487 MB.

## Notes

The first run downloads the Kokoro voice model (~330 MB) from Hugging Face, so she needs internet and patience on first launch. All together the models and libraries need about 1 GB of disk space.

## License

BSD 2-Clause License. Copyright (c) 2026, Mohammad Faiz. See [LICENSE](LICENSE) for the full text.
