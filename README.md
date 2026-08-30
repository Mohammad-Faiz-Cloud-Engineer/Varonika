# Varonika

![CI](https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika/actions/workflows/ci.yml/badge.svg)
![Python Versions](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS%20%7C%20Linux-lightgrey)
![License](https://img.shields.io/github/license/Mohammad-Faiz-Cloud-Engineer/Varonika)

Varonika is a hands-free voice assistant for your PC. Say "Hey Varonika" and she listens, asks OpenCode to do the work, and speaks the answer back.

- Wake word detection ("Hey Varonika")
- Speech-to-text with Whisper (local, no cloud)
- Talks to OpenCode running on your machine
- Text-to-speech with Kokoro
- Desktop window showing status, heard text, and responses
- Live microphone selection and hotkeys (Alt+Space)
- Web search via Exa (optional, see [EXA_SETUP.md](Setup%20Docs/EXA_SETUP.md))

## Quick Start

### Windows

```powershell
winget install Python.Python.3.12
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

### macOS

```bash
brew install python@3.11
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Linux (Ubuntu/Debian/Arch/Fedora)

```bash
# Ubuntu/Debian
sudo apt update && sudo apt install python3.11 python3.11-venv python3.11-dev

# Arch
sudo pacman -S python3.11

# Fedora
sudo dnf install python3.11

python3.11 -m venv .venv
source .venv/bin/activate
pip install -e .
```

> **Linux note:** Python 3.12 is not supported on Linux due to `openwakeword` lacking wheels. Use Python 3.11.

---

## 1. Install OpenCode (Required)

Varonika has no built-in LLM. OpenCode is the brain she talks to.

```bash
npm install -g opencode-ai
# or: bun install -g opencode-ai / yarn global add opencode-ai / pnpm install -g opencode-ai
```

Configure OpenCode with an LLM provider (cloud or local via [Ollama](Setup%20Docs/OLLAMA_SETUP.md) / [LM Studio](Setup%20Docs/LMStudio.md)):

```bash
opencode
# Type /connect and follow prompts
```

---

## 2. Download Models (Optional; auto on first run)

```bash
python scripts/download_models.py
```

Fetches: Whisper (`ggml-small.en.bin`), wake word (`wakeword.onnx`), and support models (~1 GB total). First run also downloads Kokoro voice (~330 MB).

---

## 3. Run Varonika

```bash
# Windows
.\.venv\Scripts\Activate.ps1
python app/main.py

# macOS/Linux
source .venv/bin/activate
python app/main.py
```

Wait for "Hotkeys registered" in console, then say **"Hey Varonika"**.

---

## Configuration

Create `config.yaml` in the project root to override defaults:

```yaml
wake_word_threshold: 0.6
stt_model: "models/ggml-small.en.bin"
stt_language: "en"
silence_timeout_ms: 2500
energy_threshold: 0.015
tts_voice: "af_bella"
tts_speed: 0.9
tts_volume: 1.0
follow_up_timeout_ms: 2000
mic_device: ""
```

---

## Setup Guides

All detailed guides in [Setup Docs](Setup%20Docs/):

- [SETUP.md](Setup%20Docs/SETUP.md) — full from-zero guide
- [LLM_SETUP.md](Setup%20Docs/LLM_SETUP.md) — choose LLM (cloud/custom)
- [OLLAMA_SETUP.md](Setup%20Docs/OLLAMA_SETUP.md) — free local LLM with Ollama
- [LMStudio.md](Setup%20Docs/LMStudio.md) — local LLM with LM Studio
- [PLAYWRIGHT_SETUP.md](Setup%20Docs/PLAYWRIGHT_SETUP.md) — browser control
- [CHROME_DEVTOOLS_SETUP.md](Setup%20Docs/CHROME_DEVTOOLS_SETUP.md) — Chrome DevTools testing
- [GOOGLE_MCP_SETUP.md](Setup%20Docs/GOOGLE_MCP_SETUP.md) — Gmail, Calendar, Drive, Docs, Sheets
- [MEMORY_SETUP.md](Setup%20Docs/MEMORY_SETUP.md) — persistent memory between sessions
- [EXA_SETUP.md](Setup%20Docs/EXA_SETUP.md) — enable web search (Exa via OpenCode)
- [OFFICEMCP_SETUP.md](Setup%20Docs/OFFICEMCP_SETUP.md) — control MS Office (Excel, Word, PowerPoint, Outlook, Teams, OneNote)
- [COMPUTER_USE_SETUP.md](Setup%20Docs/COMPUTER_USE_SETUP.md) — control your desktop (click, type, scroll, drag in any app)

---

## Architecture

```Architecture
Microphone → Whisper STT → OpenCode (ACP) → LLM → Kokoro TTS → Speakers
                    ↑                                    ↓
              Wake Word                          Desktop Window
```

Key modules:

- `app/audio/capture.py` — microphone input
- `app/wakeword/detector.py` — wake word detection
- `app/stt/whisper_engine.py` — speech-to-text
- `app/opencode/client.py` — OpenCode ACP protocol
- `app/conversation/manager.py` — conversation state machine
- `app/tts/kokoro_engine.py` — text-to-speech
- `app/hotkeys/listener.py` — Alt+Space hotkey
- `app/ui/main_window.py` — status window

---

## Troubleshooting

| Problem | Fix |
| --------- | ----- |
| `python`/`pip` not found | Add Python to PATH (Windows installer) or activate venv |
| `opencode` not found | Install OpenCode, restart terminal |
| Wake word not detected | Say "Hey Varonika"; lower `wake_word_threshold` to 0.5; check mic dropdown |
| No audio at all | Windows Privacy → Microphone → allow desktop apps |
| "OpenCode unavailable" | `opencode` not on PATH of terminal that started Varonika |
| Connects but no answer | OpenCode has no model configured → run `opencode`, type `/connect` |
| Model download fails | Run `python scripts/download_models.py` manually |
| Hears herself | Lower speaker volume or `tts_volume`; she ignores audio while speaking |

---

## License

BSD 2-Clause License. Copyright (c) 2026, Mohammad Faiz. See [LICENSE](LICENSE).
