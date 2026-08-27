# Setting up Exa for web search

Varonika needs to search the web to answer questions that require up-to-date information. OpenCode has a built-in `websearch` tool, but it is **not available by default** when using third-party providers like Ollama, LM Studio, or custom endpoints. Without this, Varonika falls back to `webfetch`, which can only read a specific URL you give it, not search the web.

> **Using an OpenCode provider (OpenCode Zen, OpenCode Go)?** You do not need to do anything. The `websearch` tool is already available out of the box. Skip straight to the verification step.

## How it works

```text
You ask Varonika  ->  OpenCode  ->  Exa API (websearch)  ->  search results  ->  Varonika answers
```

Exa is an AI-native search API that uses semantic search instead of keywords. It finds conceptually relevant pages, not just pages that match your exact words. No API key is required for the built-in integration. The websearch tool is free to use through OpenCode's hosted backend.

## Step 1: set the environment variable (third-party providers only)

If you are using the OpenCode provider (OpenCode Zen or OpenCode Go), skip this step. The `websearch` tool is already enabled for you.

If you are using Ollama, LM Studio, OpenRouter, or any custom provider, you need to enable Exa manually. Set `OPENCODE_ENABLE_EXA` to any truthy value.

### Option A: set it every time you launch (temporary)

This only lasts for the current terminal session. Open a new terminal and you have to set it again.

**Windows PowerShell:**

```powershell
$env:OPENCODE_ENABLE_EXA="1"
python app/main.py
```

**macOS/Linux:**

```bash
OPENCODE_ENABLE_EXA=1 python app/main.py
```

### Option B: set it once in your system (permanent)

**Windows (current user):**

```powershell
[Environment]::SetEnvironmentVariable("OPENCODE_ENABLE_EXA", "1", "User")
```

**macOS/Linux (add to your shell profile):**

```bash
echo 'export OPENCODE_ENABLE_EXA=1' >> ~/.zshrc
source ~/.zshrc
```

After this, every new terminal session has it set. Restart Varonika to pick it up.

### Option C: create a launch script (permanent, no system-wide changes)

If you do not want to change system environment variables, create a small script that sets the variable and launches Varonika.

**Windows (save as `start_varonika.bat` in the Varonika folder):**

```bat
@echo off
set OPENCODE_ENABLE_EXA=1
python app/main.py
```

Double-click this file to launch Varonika with web search enabled.

**macOS/Linux (save as `start_varonika.sh` in the Varonika folder):**

```bash
#!/bin/bash
export OPENCODE_ENABLE_EXA=1
python app/main.py
```

Make it executable: `chmod +x start_varonika.sh`, then run `./start_varonika.sh`.

## Step 2: restart and verify

Quit and restart Varonika. Then ask her to search for something:

> Search the web for today's weather in Mumbai.

If `websearch` is working, she will use it and return live results. If it is not working, she will fall back to `webfetch` or say she cannot search.

You can also verify from the terminal:

```bash
OPENCODE_ENABLE_EXA=1 opencode run "search the web for the latest news and tell me the top headline"
```

If the tool is available, OpenCode will call `websearch` and return results.

## Why Exa over Parallel

OpenCode also supports Parallel as an alternative (`OPENCODE_ENABLE_PARALLEL=1`). Exa is the better choice for Varonika:

| Factor | Exa | Parallel |
| --- | --- | --- |
| Speed | 306ms to 1.5s | 2.9s to 13.6s |
| Accuracy | Higher on most benchmarks | Catches up only at expensive tiers |
| Through OpenCode | Free (no API key needed) | Free (no API key needed) |
| Best for | Real-time agents, voice, chat | Deep research, background tasks |

Varonika is a voice agent. The user expects a fast answer. Exa returns results in under a second. Parallel takes 3 to 14 seconds minimum, which is too slow for a voice experience.

## How Varonika uses search

Once enabled, the `websearch` tool is available to the LLM alongside all other OpenCode tools. The LLM decides when to use it based on the request. The flow looks like this:

```text
You: "What is the population of India?"
LLM: calls websearch("population of India 2026")
Exa: returns search results with snippets
LLM: reads the results and answers out loud
```

The LLM also has `webfetch` for reading a specific URL. The difference:

| Tool | Use it when |
| --- | --- |
| `websearch` | You need to find information, look something up, check current events, verify a fact |
| `webfetch` | You have a specific URL and want to read its content |

The AGENTS.md file already instructs the LLM to prefer DuckDuckGo when using the browser, and to always search the web when the query needs the latest information.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `websearch` still not available | Make sure `OPENCODE_ENABLE_EXA=1` is set before launching. Check with `$env:OPENCODE_ENABLE_EXA` (PowerShell) or `echo $OPENCODE_ENABLE_EXA` (bash) |
| Search returns no results | Exa may be rate-limited. Wait a moment and try again, or check your network connection |
| Varonika uses `webfetch` instead of `websearch` | The LLM may have decided `webfetch` was sufficient for the task. Try asking a question that clearly requires searching, like "what is the latest news about..." |
| Environment variable not persisting | On Windows, use `[Environment]::SetEnvironmentVariable` with the `"User"` scope. On macOS/Linux, add the export to `~/.zshrc` or `~/.bashrc` |
| OpenCode says the tool is not found | Restart OpenCode completely. The environment variable is only read at startup |
