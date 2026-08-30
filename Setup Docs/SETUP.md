# Varonika Setup Guide

This guide takes you from a fresh computer to talking to Varonika. There are three steps, in this order:

1. Install Python
2. Install and configure OpenCode (her brain)
3. Install and run Varonika

At the end you say "Hey Varonika" and she answers you out loud.

## Step 1: Install Python (Windows, Macintosh & Linux)

Varonika requires Python 3.11 or 3.12 (Python 3.13 is not supported yet).
*Note: On Linux, only Python 3.11 is supported.*

### Windows

1. Download the Python 3.12 installer from [python.org](https://www.python.org/downloads/).
2. Run the installer.
3. **Crucial:** At the very bottom of the installer window, check the box that says **"Add Python to PATH"** before clicking Install.

**Macintosh**
Open your Terminal and use Homebrew:

```bash
brew install python@3.12
```

**Linux (Debian/Ubuntu)**
Open your terminal and run:

```bash
sudo apt update
sudo apt install python3.11 python3.11-venv python3.11-dev
```

**Linux (Arch)**
Open your terminal and run:

```bash
sudo pacman -S python
```

### Verify

Open a new terminal or command prompt and run:

```bash
python --version
# or on some Linux/Mac systems:
python3 --version
```

It should say something like `Python 3.12.x`. If it errors, Python is not in your PATH.

## Step 2: Set up OpenCode

OpenCode acts as the intelligence and agentic brain for Varonika.

### 2.1 Install Node.js (needed for the install command)

OpenCode is distributed via npm.

- **Windows:** Download and install the LTS version from [nodejs.org](https://nodejs.org/).
- **Macintosh:** `brew install node`
- **Linux (Debian/Ubuntu):**

  ```bash
  curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
  sudo apt-get install -y nodejs
  ```

- **Linux (Arch):** `sudo pacman -S nodejs npm`

### 2.2 Install OpenCode

Once Node.js is installed, open a terminal and run:

```bash
npm install -g opencode
```

### 2.3 Give OpenCode an AI model

OpenCode needs access to an LLM. Run the setup wizard:

```bash
opencode config
```

Follow the prompts to select your preferred AI provider (e.g., Anthropic, OpenAI, Google) and enter your API key. If you want to run models locally and entirely for free, skip the API key and check out the Local LLM setup guides at the bottom of this page.

### 2.4 Test OpenCode

Make sure OpenCode is working by running:

```bash
opencode chat
```

Say "Hello", and verify that the AI responds. Type `/exit` to leave.

## Step 3: Set up Varonika

### 3.1 Get the code

In your terminal, download the Varonika repository and enter the directory:

```bash
git clone https://github.com/Mohammad-Faiz-Cloud-Engineer/Varonika.git
cd Varonika
```

### 3.2 Install the Python dependencies

Varonika relies on PyAudio for microphone capture, which requires the PortAudio system library.

**Install System Dependencies:**

- **Windows:** No extra steps needed, PortAudio is included in the Python wheel.
- **Macintosh:** `brew install portaudio`
- **Linux (Debian/Ubuntu):** `sudo apt-get install portaudio19-dev`
- **Linux (Arch):** `sudo pacman -S portaudio`

**Install Python Packages:**
Inside the Varonika folder, run:

```bash
pip install .
# or on Linux/Mac:
pip3 install .
```

### 3.3 Download the voice and speech models

Varonika runs speech recognition and text-to-speech entirely locally. Download the necessary offline AI models:

```bash
python scripts/download_models.py
# or: python3 scripts/download_models.py
```

*Note: This will download around 500MB of data and might take a few minutes depending on your internet connection.*

### 3.4 Start Varonika

Run the main application:

```bash
python app/main.py
# or: python3 app/main.py
```

### 3.5 Talk to her

Wait for the UI to appear and the status to say "Idle".
Say **"Hey Varonika"** out loud. You will hear an activation chime. Speak your request, and she will answer you out loud!

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

## Next steps

Varonika can do more once you give her extra tools:

- [LLM_SETUP.md](LLM_SETUP.md): choose which LLM she uses, cloud or custom
- [OLLAMA_SETUP.md](OLLAMA_SETUP.md): run a free local LLM with Ollama
- [LMStudio.md](LMStudio.md): run a local LLM with LM Studio
- [PLAYWRIGHT_SETUP.md](PLAYWRIGHT_SETUP.md): give her browser control
- [CHROME_DEVTOOLS_SETUP.md](CHROME_DEVTOOLS_SETUP.md): test websites in a real Chrome
- [GOOGLE_MCP_SETUP.md](GOOGLE_MCP_SETUP.md): give her access to Gmail, Calendar, Drive, Docs, and Sheets
- [MEMORY_SETUP.md](MEMORY_SETUP.md): give her a memory between sessions
