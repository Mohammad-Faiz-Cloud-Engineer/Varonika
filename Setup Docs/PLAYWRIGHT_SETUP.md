# Setting up Playwright browser control in OpenCode

This page explains how to give **OpenCode** the power to control a real browser with **Playwright**. Once set up, OpenCode (and through it, Varonika) can open websites, click buttons, fill forms, take screenshots, and run tests, all by itself.

## What you get

| Thing | What it means |
| --- | --- |
| Open a website | OpenCode can navigate to any URL and see the page |
| Click and type | OpenCode can press buttons, fill forms, use menus |
| Read the page | OpenCode reads the page's structure, not just screenshots, so it is fast and accurate |
| Screenshots | OpenCode can save a picture of the page and look at it |
| Test websites | OpenCode can go through a whole user flow step by step, like a tester |

## How it works

```text
OpenCode  ->  Playwright MCP server (a small helper program)  ->  real browser (Chromium by default)
```

Playwright MCP is Microsoft's official browser server. OpenCode talks to it through the MCP standard, and the server drives a real browser on your machine. You just add one small block to OpenCode's config file. No code changes needed.

## Before you start

- **Node.js 20 or newer.** Playwright MCP is an npm package. Check with `node --version`.
- **OpenCode installed** and working with your model of choice.

The browser itself downloads automatically on first use. You do not install Playwright separately.

## Step 1: decide where to put the config

OpenCode reads its config from two places:

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.json` on Windows, `~/.config/opencode/opencode.json` on Linux/macOS |
| Project (just this repo) | `opencode.json` in the project folder |

If you use OpenCode with several projects, put it in the global file. If only this project needs browser control, put a project-level `opencode.json` instead. Both work, and the project one wins over the global one.

## Step 2: add the Playwright MCP server

Create or edit the config file and add this block:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "playwright": {
      "type": "local",
      "command": ["npx", "-y", "@playwright/mcp@latest"],
      "enabled": true
    }
  }
}
```

That is the whole setup. `npx` downloads the server package on first run, and the browser downloads on first use.

## Step 3: restart OpenCode and check it works

Config is loaded only when OpenCode starts, so quit and restart OpenCode after saving.

Check the server is registered:

```bash
opencode mcp
```

You should see `playwright` listed as connected. Then ask OpenCode something like:

> Open [https://example.com](https://example.com) and tell me what the page says.

OpenCode will open a real browser window, read the page, and answer.

## Useful options

You can add flags to the `command` list to change how the browser behaves:

```json
"command": [
  "npx", "-y", "@playwright/mcp@latest",
  "--browser=firefox", "--headless"
]
```

| Flag | What it does |
| --- | --- |
| `--browser=chromium` | Use Chromium (default). Also: `firefox`, `webkit`, `chrome`, `msedge` |
| `--headless` | Run the browser invisibly, no window. Good for background tasks |
| `--device="iPhone 15"` | Pretend to be a phone or tablet, for mobile testing |
| `--user-data-dir="C:\path"` | Keep a permanent profile, so logins and settings survive between sessions |
| `--storage-state="C:\path\state.json"` | Start the browser already logged in, using saved cookies |

Example: a persistent profile with Chrome so OpenCode stays logged into a site:

```json
"command": [
  "npx", "-y", "@playwright/mcp@latest",
  "--browser=chrome", "--user-data-dir=C:\\playwright-profile"
]
```

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `npx` is not recognized | Node.js is not installed or not on PATH. Install Node.js 20+ and reopen the terminal |
| Server starts but no browser opens | The browser downloads on first use, give it a minute. Or add `--headless` |
| OpenCode says the config is invalid | Check the JSON: `command` must be a list, and `"type": "local"` must be present |
| OpenCode will not start because of a bad config | Run with `OPENCODE_DISABLE_PROJECT_CONFIG=1` to skip the project config, fix the file, then restart normally |
| Tool list is missing playwright tools | Check `opencode mcp`. If it is not there, restart OpenCode and check the config path with `opencode config print` |

## A note about Varonika

Varonika talks to OpenCode on your machine, so this same setup automatically gives her browser control too. Once the server is running, you can ask her things like "open Google and search for today's cricket score" and she will drive the browser for you.
