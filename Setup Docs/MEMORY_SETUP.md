# Setting up memory with opencode-mem

This page explains how to give **OpenCode** (and through it, Varonika) a **memory**. Normally the agent forgets everything when you close a chat, like a person with amnesia every morning. opencode-mem gives it a memory box on your own machine, so it remembers your name, your preferences, and past fixes between sessions.

## What you get

| Thing | What it means |
| --- | --- |
| Remembers you | Your name, what you call her, how you like things done |
| Remembers the project | Past fixes, decisions, and lessons, so work is not repeated |
| Automatic learning | No manual work, important facts are picked out of conversations by themselves |
| Memory box on your PC | Everything is stored locally on your machine, nothing in the cloud |
| Full control | A web page shows every memory, you can read, search, and delete anything |
| Relevant memories in chat | When you talk about something, the agent finds related old notes and uses them |

## How it works

```text
Your chat  ->  opencode-mem (runs on your machine)  ->  memory box (local storage)
```

When you talk to the agent, opencode-mem quietly notices important facts and saves them. When a new conversation starts, the agent loads the saved memories and starts already knowing you. A small web page on your PC lets you see exactly what it remembers.

## Before you start

- **Node.js 18 or newer.** Check with `node --version`.
- **An LLM API key** (like an OpenAI or Anthropic key). This is used only to help pick out memories from conversations. The memories themselves stay on your machine.

## Step 1: install opencode-mem

```bash
npm install -g opencode-mem
```

## Step 2: run the setup wizard

```bash
opencode-mem setup
```

The wizard does the work for you: it creates the storage folder, adds opencode-mem to OpenCode's config, starts the background service, and tests the installation.

## Step 3: add your LLM key

The wizard needs a model to read conversations and decide what is worth remembering. Open or create the config file:

```text
C:\Users\<you>\.config\opencode\opencode-mem.jsonc
```

**Recommended:** Use a provider that is already authenticated in OpenCode:

```jsonc
{
  "opencodeProvider": "anthropic",
  "opencodeModel": "claude-haiku-4-5-20251001"
}
```

**Or** use a manual API key (any OpenAI-compatible provider works):

```jsonc
{
  "memoryProvider": "openai-chat",
  "memoryModel": "gpt-4o-mini",
  "memoryApiUrl": "https://api.openai.com/v1",
  "memoryApiKey": "your-api-key-here"
}
```

Replace the URL and key with your provider's. Never commit this file anywhere, the key is a secret.

## Step 4: restart and test

Quit and restart OpenCode so it loads the memory server. Then try:

> Save my work to memory.
> Remember that my name is Faiz.

Now close the chat entirely, open a fresh one, and ask:

> What do you remember about me?

If it answers with your name and the facts you saved, the memory works.

## Viewing and managing memories

Open this page in your browser:

```text
http://127.0.0.1:4747
```

You will see a timeline of every memory, a profile the agent built about you, and a search box. Delete anything you do not want kept.

## Useful commands

| Command | What it does |
| --- | --- |
| `opencode-mem status` | Check the memory service is running |
| `opencode-mem restart` | Restart the service after config changes |
| `opencode-mem stop` | Stop the service |
| `opencode-mem setup` | Re-run the setup wizard |

## Tips

- **Say it out loud if it matters.** "Remember that I prefer..." works much better than hoping it notices.
- **Talk normally otherwise.** The service picks up facts by itself, you do not need to command it every time.
- **Check the web page now and then.** You own the memories, review them like you would a diary.
- **Getting too many stale memories?** Delete the old ones on the web page; the agent only uses what is still there.

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Memory server not loaded | Restart OpenCode completely, then check `opencode mcp` lists it |
| "Save my work to memory" does nothing | Check the service with `opencode-mem status`, restart with `opencode-mem restart` |
| Web page will not open | The service is stopped. Start it and try `http://127.0.0.1:4747` again |
| No memories are saved | The LLM key in the config file is wrong or missing. Check Step 3 |
| I want to wipe everything | Delete the storage folder `C:\Users\<you>\.opencode-mem\data\` (backup first, this deletes all memories) |

## A note about Varonika

Varonika talks through OpenCode, so once this server is running, her opencode session uses the same memory box. That means she can genuinely remember you between restarts: your name, that she calls you Boss, how you like your answers. Nothing in Varonika's code needs to change; it is all config. Remember that she only remembers what happens in her own chats, and you can always see and delete everything on the web page.
