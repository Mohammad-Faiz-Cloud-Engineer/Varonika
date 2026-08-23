# Using LM Studio local models with OpenCode

This guide shows you how to run OpenCode (and therefore Varonika) on **local models served by LM Studio**, so nothing you say or ask ever leaves your PC.

## Why local models?

- **Privacy**: your conversations never leave your machine
- **Free**: no API bills, no limits
- **Offline**: works without internet
- **Downside**: local models are smaller than cloud models, so answers can be slower and less capable, especially with tools

## What you need

- **LM Studio** installed from [lmstudio.ai](https://lmstudio.ai/)
- **OpenCode** installed and on your PATH (Varonika needs this anyway)
- Enough hardware: 16 GB RAM minimum, a GPU with 8 GB+ VRAM makes a big difference

## Step 1: download a model in LM Studio

1. Open LM Studio and go to the **Search** tab (magnifying glass icon)
2. Search for a model. For Varonika, you want a model that is good at **tool calling** (she controls your browser and runs commands). Good starting points:

| Model | Size | Best for |
| --- | --- | --- |
| Qwen2.5-Coder-7B-Instruct | 7B | Fast, light tasks, 8 GB VRAM |
| Qwen2.5-Coder-14B-Instruct | 14B | Good balance, 12 GB+ VRAM |
| Qwen3 series (e.g. Qwen3-8B / 14B) | 8B-14B | Good general tool use |
| Llama 3.1 / 3.3 series | 8B+ | Solid all-rounders |

3. Pick a quantized version (Q4_K_M is a good quality/speed balance)
4. Click **Download**

If you have a small GPU, start with the 7B. You can always switch models later, it is a one-line config change.

## Step 2: load the model and start the server

1. Open the **Chat** tab and load your model once (this also verifies it works)
2. Open the **Server** tab (the `<>` icon)
3. Confirm the model in the dropdown is the one you downloaded
4. Set a decent **Context Length** (see the note below)
5. Click **Start Server**

The server runs at `http://localhost:1234/v1`. Keep the window open; if you close LM Studio, the server stops.

> **Context length matters for agents.** OpenCode works like an agent: it sends the task, your project files, and tool results back and forth. That eats context fast. Set the context length to at least **16384** (16K) if your RAM allows, more is better. Too little context causes confusing failures mid-task.
> **Auth:** by default LM Studio needs no API key. Only set one if you enabled "API token" in the server settings. The "Serve on Local Network" option is only needed if you want another computer to reach this server.

## Step 3: find the exact model ID

OpenCode must call the model by the **exact ID** LM Studio uses, or it will not find it.

1. With the server running, open the **Developer** tab in LM Studio (or look at the example request shown on the server page)
2. Find the JSON example. The line that says `"model": "..."` shows the ID, for example:

```json
"model": "qwen2.5-coder-7b-instruct"
```

or for newer community models:

```json
"model": "lmstudio-community/Qwen2.5-Coder-7B-Instruct-GGUF"
```

3. Copy that string exactly. It is the ID you will put in the OpenCode config.

## Step 4: configure OpenCode

OpenCode reads its config from two places:

| Scope | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` on Windows, `~/.config/opencode/opencode.jsonc` on Linux/macOS |
| Project (just Varonika) | `opencode.json` in the Varonika folder |

If Varonika is the only OpenCode user on this PC, use the global file. If other people share the Varonika repo, put it in the project file instead.

Create or edit the file, with the model ID from Step 3 in two places:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "provider": {
    "lmstudio": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "LM Studio (local)",
      "options": {
        "baseURL": "http://127.0.0.1:1234/v1"
      },
      "models": {
        "qwen2.5-coder-7b-instruct": {
          "name": "Qwen 2.5 Coder 7B (local)"
        }
      }
    }
  },
  "model": "lmstudio/qwen2.5-coder-7b-instruct"
}
```

Replace `qwen2.5-coder-7b-instruct` with your actual model ID from Step 3.

- `provider.lmstudio` is the provider name. It can be any word you like, but it must match the prefix in `model`.
- `npm` tells OpenCode how to talk to LM Studio (it speaks the OpenAI-compatible API).
- `options.baseURL` is the LM Studio server address. `http://127.0.0.1:1234/v1` and `http://localhost:1234/v1` both work.
- `models` lists the model IDs LM Studio can serve. Add more entries if you downloaded several models:

```jsonc
"models": {
  "qwen2.5-coder-7b-instruct": { "name": "Qwen 2.5 Coder 7B (local)" },
  "qwen2.5-coder-14b-instruct": { "name": "Qwen 2.5 Coder 14B (local)" }
}
```

- `model` at the top level sets the default model: `provider-name/model-id`.

**Important:** after changing the config, quit and restart OpenCode (and restart Varonika too). OpenCode only reads the config when it starts.

## Step 5: verify in OpenCode

In a terminal, from the Varonika folder, run:

```bash
opencode run "reply with exactly: OK"
```

The first line shows which model answered. If you see your local model and "OK", the connection works.

To switch between models later, run `opencode models` to list what is configured, or use the `/models` command inside OpenCode.

## Step 6: verify in Varonika

1. Close Varonika if it is running
2. Run `python app/main.py` again
3. Check the **System** message in the window: it shows the session and the model in use

It should show your local model. From then on, all her answers come from your local LM Studio model.

## Troubleshooting

| Problem | What to check |
| --- | --- |
| "Connection refused" or nothing happens | Is the LM Studio server started? Is the window still open? Is the port 1234 in your config? Try `localhost` instead of `127.0.0.1` (or the other way round). Check the firewall is not blocking LM Studio. |
| Model not found / not in the list | The model ID in `models` must match exactly what LM Studio serves. Repeat Step 3 and copy the ID character for character. |
| OpenCode hangs on the first message | The model may not be loaded. Load it in the Chat tab first. Also check your context length is big enough. |
| Tools fail or she does things wrong | The model does not support function calling well. Use a model known for tool use (Qwen2.5+, Llama 3.1+, Qwen3). Raise the context length to 16K or more. |
| Very slow answers | Use a smaller model (7B instead of 14B), a lower quantization (Q4 instead of Q8), or close other heavy apps. Check the GPU offload setting in LM Studio (VRAM) so the model runs on your GPU. |
| Out of memory / crashes | Lower the context length in both LM Studio and OpenCode, or switch to a smaller model. |
| Varonika says "OpenCode isn't available right now" | That is an OpenCode problem, not a model problem. OpenCode did not start: check it is on your PATH and runs (`opencode run "hi"`), then restart Varonika. |
| You want to go back to a cloud model | Remove the `provider.lmstudio` block or change `model` back to a provider like `anthropic/...`. Nothing else changes. |

## Quick reference

```text
Your voice -> Varonika (Whisper) -> OpenCode -> LM Studio local model (http://127.0.0.1:1234/v1) -> answer back
```

Everything runs on your machine. No cloud, no API key, no cost.
