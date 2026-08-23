# Varonika Setup Guide

This guide takes you from a fresh computer to talking to Varonika. There are three steps, in this order:

1. Install Python
2. Install and configure OpenCode (her brain)
3. Install and run Varonika

At the end you say "Hey Varonika" and she answers you out loud.

---

## Step 1: Install Python

Varonika is a Python application, so Python must be on your PC first.

### Windows

#### Option A: winget (recommended; installs Python 3.12, creates venv, isolates Varonika)

```powershell
winget install Python.Python.3.12
# close and reopen terminal, then:
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .
```

#### Option B: Windows official installer

1. Open <https://www.python.org/downloads/>
2. Click **Download Python** (3.11 or 3.12; not 3.13+).
3. Run the installer. **Tick "Add Python to PATH"**.
4. Verify: `python --version`

### macOS

#### Option A: Homebrew (recommended)

```bash
brew install python@3.11
# or for Python 3.12 (also works on macOS):
brew install python@3.12
```

Then verify: `python3.11 --version` or `python3.12 --version`

#### Option B: macOS official installer

1. Open <https://www.python.org/downloads/macos/>
2. Download the **macOS 64-bit universal2 installer** for Python 3.11 or 3.12.
3. Run the installer.
4. Verify: `python3.11 --version`

> **Note:** On macOS, both Python 3.11 and 3.12 work. The `openwakeword` limitation only applies to Linux.

### Linux (Ubuntu / Debian)

Use your package manager. Do not use the python.org installer.

**Ubuntu 22.04 / 24.04 (and Debian-based):**

```bash
sudo apt update && sudo apt install python3.11 python3.11-venv python3.11-dev
```

If `python3.11` is not available in your repos, add the deadsnakes PPA (Ubuntu only):

```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**Arch / Manjaro:**

```bash
sudo pacman -S python3.11
```

**Fedora:**

```bash
sudo dnf install python3.11
```

**Any Linux (using pyenv):**

```bash
curl https://pyenv.run | bash
# restart your shell, then:
pyenv install 3.11.9
pyenv global 3.11.9
```

> **Important:** On Linux, Python 3.12 is not supported because the `openwakeword` dependency lacks pre-built wheels for Python 3.12 on Linux. Use **Python 3.11**.

### Verify

Open a terminal and run:

**Windows:**

```powershell
python --version
```

**macOS (Homebrew):**

```bash
python3.11 --version
# or
python3.12 --version
```

**Linux:**

```bash
python3.11 --version
```

You should see something like `Python 3.11.x` or `Python 3.12.x`. If the command is not found, close and reopen the terminal.

---

## Step 2: Set up OpenCode

Varonika has no AI brain of her own. OpenCode is the agent she talks to, so it must be installed and configured before she can answer anything.

### 2.1 Install Node.js (needed for the install command)

1. Go to the official Node.js website: <https://nodejs.org/>
2. Download and install the **LTS** version.
3. Verify with:

```bash
node --version
npm --version
```

Both should print a version number.

### 2.2 Install OpenCode

Open a terminal and run:

```bash
npm install -g opencode-ai
```

(This is the official install command from the OpenCode docs. Other package managers work too: `bun install -g opencode-ai`, `yarn global add opencode-ai`, `pnpm install -g opencode-ai`. On Windows you can also use `choco install opencode` or `scoop install opencode`.)

Verify the install:

```bash
opencode --version
```

### 2.3 Give OpenCode an AI model

OpenCode needs at least one AI model provider configured. You have two paths:

**Option A: a cloud provider (quickest).** Run `opencode` in a terminal, type `/connect`, pick a provider, and paste your API key when asked. OpenCode Zen is the simplest: it gives you access to several tested models with one login.

**Option B: a free local model.** If you want everything offline and free, run a local model with Ollama. See [OLLAMA_SETUP.md](OLLAMA_SETUP.md) for the step-by-step.

For more choices (LM Studio, custom endpoints, which model to use), see [LLM_SETUP.md](LLM_SETUP.md).

### 2.4 Test OpenCode

In a terminal, run `opencode` and ask it something simple, like "What is 2 + 2?". If it answers, OpenCode is ready and you can close the terminal.

---

## Step 3: Set up Varonika

### 3.1 Get the code

Open a terminal and run:

```bash
git clone https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika.git
cd Varonika
```

(No Git? Download the ZIP from the same page on GitHub and extract it, then open a terminal inside the `Varonika` folder.)

### 3.2 Install the Python dependencies

```bash
pip install -e .
```

> **Note:** If you used the Windows winget + venv method (Step 1, Option A), you already ran this. Skip this step unless you're on macOS/Linux or used the official installer.

This installs everything Varonika needs: the window interface, speech recognition, wake word, text to speech, and the OpenCode connection. It can take a few minutes; the AI libraries (especially torch) are big, so let it finish.

> If `pip` is not found, check Step 1's PATH note, or try `python -m pip install -e .`.

### 3.3 Download the voice and speech models

Varonika needs two models before she can hear and speak:

- `models/ggml-small.en.bin` (Whisper, turns your speech into text)
- `models/wakeword.onnx` (wake word, hears "Hey Varonika")
- `models/melspectrogram.onnx` (wake word support model)
- `models/embedding_model.onnx` (wake word support model)

Download them with:

```bash
python scripts/download_models.py
```

Or simply start Varonika: she downloads them automatically on the first run. (All together the models need about 1 GB of disk space.)

> If the Whisper download fails, grab it directly from [this link](https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika/releases/download/ggml-small.en/ggml-small.en.bin) and place it in the `models/` folder as `ggml-small.en.bin`.

**About the wake word:** the model included with the code responds to **"Hey Varonika"**. If you have your own trained model, drop it in the project root as `Hey_Varonika.onnx` and the script copies it into place. (The first run also downloads the Kokoro voice model, about 330 MB from Hugging Face, so she needs internet and patience on first launch.)

### 3.4 Start Varonika

```bash
python app/main.py
```

You should see:

1. The small desktop window with the Varonika brain animation.
2. `Hotkeys registered` in the console, which means she is ready.

### 3.5 Talk to her

1. Say **"Hey Varonika"**. She answers "Yes Boss" to confirm she is listening.
2. Speak your request, for example "What is the formula for torque?"
3. She sends it to OpenCode, then speaks the answer back and shows it in the window.

Wait for her "Yes Boss" before speaking, otherwise the start of your command gets clipped.

You can interrupt her mid-answer by saying the wake word again. After she answers, she keeps listening a moment for a follow-up; if you stay quiet she goes back to sleep until the wake word.

No wake word handy? Press **Alt+Space** to activate listening without speaking.

### 3.6 Tweak settings (optional)

Everything has sensible defaults, but you can create a `config.yaml` in the project root to override them:

```yaml
wake_word_threshold: 0.6           # higher = harder to trigger; lower to 0.5 if she does not trigger
stt_model: "models/ggml-small.en.bin"
stt_language: "en"
silence_timeout_ms: 2500           # pause before she stops listening
energy_threshold: 0.015            # mic sensitivity; auto-calibrated at startup
tts_voice: "af_bella"              # Kokoro voice
tts_speed: 0.9                     # below 1.0 speaks slower and more clearly
tts_volume: 1.0                    # loudness boost, 0.5x to 5.0x
follow_up_timeout_ms: 2000         # go back to sleep after this long of silence
mic_device: ""                     # e.g. "Headset Microphone"; empty = Windows default
```

---

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `python` or `pip` not found | Python was not added to PATH. Reinstall Python and tick "Add Python to PATH". |
| `opencode` not found | Reinstall OpenCode (Step 2.2), then close and reopen the terminal. |
| Nothing happens when you say the wake word | Say "Hey Varonika" (that is what the included model hears). Check the console says the wake word model loaded, and the mic dropdown in the window points at the mic you speak into ("System Default" lets Windows decide). Still silent? Lower `wake_word_threshold` to 0.5 in `config.yaml`. Wake word models are trained on one voice, so if she never responds to yours even at 0.5, use **Alt+Space** instead, or train your own model and drop it in as `Hey_Varonika.onnx`. |
| She never hears you at all (wake word and voice both dead) | Windows may be blocking microphone access for desktop apps. Go to Settings -> Privacy & security -> Microphone, allow desktop apps to access the mic, then restart Varonika. |
| The window says "OpenCode unavailable" | `opencode` is not on the PATH of the terminal that started Varonika. Install it (Step 2.2), close and reopen the terminal, then start Varonika again. |
| She connects but answers nothing | OpenCode has no AI model configured. Run `opencode`, type `/connect`, add a provider (or Ollama, see the guides), then restart Varonika. |
| First-run model download fails or times out | Run `python scripts/download_models.py` manually and let it finish. A slow connection takes a while: the Whisper model alone is about 487 MB. |
| Windows SmartScreen or antivirus blocks something | Python apps that record audio and use global hotkeys sometimes trip Windows Defender. Allow the app and Python through, then try again. |
| She hears herself and answers | She should refuse to transcribe while speaking, including the echo right after. If you still hear looping, lower the speaker volume or `tts_volume`. |
| Speech to text or wake word failed to load | Check `models/` contains `ggml-small.en.bin` and `wakeword.onnx`, then restart. |
| OpenCode is not answering | OpenCode itself must work first: run `opencode` in a terminal and ask it a question (Step 2.4). |

---

## Next steps

Varonika can do more once you give her extra tools:

- [LLM_SETUP.md](LLM_SETUP.md): choose which LLM she uses, cloud or custom
- [OLLAMA_SETUP.md](OLLAMA_SETUP.md): run a free local LLM with Ollama
- [LMStudio.md](LMStudio.md): run a local LLM with LM Studio
- [PLAYWRIGHT_SETUP.md](PLAYWRIGHT_SETUP.md): give her browser control
- [CHROME_DEVTOOLS_SETUP.md](CHROME_DEVTOOLS_SETUP.md): test websites in a real Chrome
- [GOOGLE_MCP_SETUP.md](GOOGLE_MCP_SETUP.md): give her access to Gmail, Calendar, Drive, Docs, and Sheets
- [MEMORY_SETUP.md](MEMORY_SETUP.md): give her a memory between sessions
