# Setting up a local LLM with Ollama

This page explains how to run your own **local LLM** using **Ollama** and make **OpenCode** (and through it, Varonika) use it. No internet needed after setup, no API bills, and your code never leaves your machine.

## What you get

| Thing | What it means |
| --- | --- |
| Free forever | No per-token charges, the model runs on your own computer |
| Private | Nothing you ask is sent to any cloud |
| Offline | Works without internet once the model is downloaded |
| Easy switching | Add more models any time with one command |

The trade-off: local models are smaller than cloud ones, so answers are a bit slower and less smart on weak hardware. A small model on a laptop is still fine for everyday tasks.

## How it works

```text
OpenCode  ->  Ollama (runs on your machine)  ->  your model (lives on your disk)
```

Ollama is a free program that downloads models and serves them to anything that asks. OpenCode talks to it the same way it talks to cloud providers, so there is no code change anywhere. Varonika picks it up automatically.

## Step 1: install Ollama

| System | How |
| --- | --- |
| Windows | Download the installer from [ollama.com/download](https://ollama.com/download) and run it. Ollama keeps running in the background afterwards |
| macOS | `brew install --cask ollama-app` |
| Linux | `curl -fsSL https://ollama.com/install.sh \| sh` |

Check it is alive:

```bash
ollama list
```

If it prints an empty table (or your models), you are good. If it says "connection refused", start it with `ollama serve`.

## Step 2: pull a model

Models are downloaded with one command. For example:

```bash
ollama pull qwen3.5
```

See [ollama.com/models](https://ollama.com/models) for the full catalog. Good first picks:

| Model | Size | Best for |
| --- | --- | --- |
| `qwen3.5` | small | A good all-round starter on normal laptops |
| `llama3.2` | small | Fast general chat and simple tasks |
| `gemma4` | medium | Good explanations and small coding tasks |
| `qwen3.5-coder` | medium | Coding focused, better on stronger machines |

The download is big (several GB for medium models), so give it time. Check what you have with `ollama list`, and copy the model name exactly from that list, you will need it next.

## Step 3: add Ollama to OpenCode's config

OpenCode reads its config from two places:

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` on Windows, `~/.config/opencode/opencode.jsonc` on Linux/macOS |
| Project (just this repo) | `opencode.json` in the project folder |

Create or edit the file and add this block:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "model": "ollama/qwen3.5",
  "provider": {
    "ollama": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Ollama (local)",
      "options": {
        "baseURL": "http://localhost:11434/v1"
      },
      "models": {
        "qwen3.5": { "name": "Qwen 3.5 (local)" }
      }
    }
  }
}
```

What each part means:

| Field | Meaning |
| --- | --- |
| `baseURL` | Where Ollama listens on your machine. `11434` is Ollama's port, leave it unless you changed it |
| `models` | The models OpenCode may use. Each entry must match a name from `ollama list` |
| `model` | Your default model. Write it as `ollama/<model-name>` |

If you pulled a different model, replace `qwen3.5` with its exact name from `ollama list`, in all three places.

If OpenCode ever asks for an API key for Ollama, any placeholder works, for example `ollama`. Local Ollama does not really check keys.

## Step 4: verify

1. Quit and restart OpenCode, config is only loaded at startup.
2. Check the model is visible:

```bash
opencode models
```

3. Test it directly:

```bash
opencode run "reply with exactly: OK"
```

The first line of output shows the model in use. If it replies "OK", the setup works.

4. Restart Varonika (`python app/main.py`). The **System** message in her window shows which model she is using, it should say your Ollama model.

## Making answers better

- **Give the model more context.** OpenCode needs a generous context window to work well. For a model pulled through Ollama, set a larger context once:

```bash
ollama run qwen3.5 --num-ctx 32768 /bye
```

Bigger numbers like 32768 or 65536 help tool use work reliably.

- **Tool calls failing silently?** Almost always the context window is too small. Raise `num_ctx` as above and retry.

- **Slow answers?** Smaller models respond faster. On a laptop, 7B-class models are the sweet spot; 30B+ models need a real GPU.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `connection refused` | Ollama is not running. Start it with `ollama serve`, or reinstall on Windows so it starts with the system |
| `model not found` | The name in the config does not match `ollama list`. Copy the exact name, including any `:tag` |
| OpenCode still shows the old cloud model | You added the config but did not set `model`, or did not restart OpenCode |
| Answers are nonsense or tools fail | Raise the context window (`num_ctx` above) or pick a bigger model |
| Very slow responses | Check with `ollama ps` whether the model is on the GPU. If it is all CPU, pick a smaller model |
| Config error at startup | Check the JSON: `provider` must be an object, and the model entries go under `models` |

## A note about Varonika

Varonika only talks through OpenCode, so once OpenCode uses Ollama, she uses it too. You can switch back to a cloud model any time by editing the same config file, it is a one-line change. Keep in mind local models are slower, so her answers may take a little longer, and very complex coding tasks are better left to a cloud model.
