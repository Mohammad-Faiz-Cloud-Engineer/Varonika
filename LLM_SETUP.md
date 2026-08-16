# Setting up your own LLM

Varonika does not have her own built-in brain. She talks to **OpenCode** running on your machine, and OpenCode talks to the LLM. This means the model she uses is whatever model OpenCode is configured to use, and you can point it at any model you like.

## How it works

```
Your voice  ->  Varonika (Whisper)  ->  OpenCode (ACP)  ->  LLM provider  ->  answer back to you
```

Changing the model is a config change in OpenCode, not a code change. Varonika picks it up automatically on her next start.

## What model is she using right now?

Ask her:

> "Which LLM model are you using?"

or check the list of models OpenCode can see:

```bash
opencode models
```

## Step 1: decide where to put the config

OpenCode reads its config from two places (the global one wins over nothing; the project one is optional):

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` on Windows, `~/.config/opencode/opencode.json` on Linux/macOS |
| Project (just Varonika) | `opencode.json` in the Varonika folder |

If you only use Varonika, put everything in the global file. If you share Varonika with other people, put a project-level `opencode.json` in the repo instead (without any API keys in it).

## Option A: use a model OpenCode already knows

List the models that are available:

```bash
opencode models
```

Pick one from the list and add it to your config file:

```jsonc
{
  "model": "ollama-cloud/gemma4:31b"
}
```

Or set it with an environment variable (temporary, useful for testing):

```bash
OPENCODE_MODEL=ollama-cloud/gemma4:31b python app/main.py
```

## Option B: use your own custom model (your own API endpoint)

If you have your own OpenAI-compatible endpoint (any provider that speaks the OpenAI API: a cloud service, a self-hosted server, LM Studio, Ollama, etc.), add it as a custom provider:

```jsonc
{
  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "My Provider",
      "options": {
        "baseURL": "https://your-api-url.com/v1",
        "apiKey": "your-api-key"
      },
      "models": {
        "my-model": {
          "name": "My Model"
        }
      }
    }
  },
  "model": "myprovider/my-model"
}
```

Replace `https://your-api-url.com/v1` with your endpoint, `your-api-key` with your key, and `my-model` with the model ID your endpoint accepts.

### Keep API keys out of files you share

Never commit an API key. Two safer ways:

1. Environment variable:

```bash
set MYPROVIDER_API_KEY=your-api-key        # Windows PowerShell
export MYPROVIDER_API_KEY=your-api-key     # Linux / macOS
```

```jsonc
{
  "provider": {
    "myprovider": {
      "npm": "@ai-sdk/openai-compatible",
      "options": {
        "baseURL": "https://your-api-url.com/v1",
        "apiKey": "{env:MYPROVIDER_API_KEY}"
      },
      "models": {
        "my-model": { "name": "My Model" }
      }
    }
  },
  "model": "myprovider/my-model"
}
```

2. `opencode auth login` logs in interactively and stores the credential outside the repo.

## Step 2: verify

Restart Varonika (close the window and run `python app/main.py` again), then ask:

> "Which LLM model are you using?"

She should answer with the model you configured. You can also confirm the model loads by running:

```bash
opencode run "reply with exactly: OK"
```

The first line of output shows the model in use.

## Troubleshooting

**"OpenCode isn't available right now."** OpenCode did not start. Check it is installed and on your PATH, then try `opencode run "hi"` in a terminal.

**The model ID in the list has a different format than mine.** Model IDs look like `provider/model-name`. Copy the ID exactly as `opencode models` prints it.

**She says the model name but answers oddly.** Some models are better at following tool-use instructions than others. If a model refuses to use tools, pick a different one, it is a one-line config change.