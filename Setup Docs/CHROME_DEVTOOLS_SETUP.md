# Setting up Chrome DevTools MCP for browser testing

This page explains how to test software in a real browser using **Chrome DevTools MCP**. It gives OpenCode (and through it, Varonika) the ability to open websites, click buttons, fill forms, read console errors, watch network requests, take screenshots, and even run performance checks, exactly like a human tester would.

## What you can test with it

| Thing | What it means |
| --- | --- |
| Page testing | Open any URL, click, type, use menus, submit forms |
| UI verification | See the page's structure and take screenshots to check the design |
| Console errors | Read JavaScript errors and warnings from the page |
| Network checks | See every request the page makes and its status |
| Form flows | Fill a login form, submit, and verify what happens next |
| Mobile view | Pretend to be a phone or tablet and test the responsive layout |
| Performance | Record a trace and check LCP, INP, and CLS scores |

## How it works

```text
OpenCode  ->  Chrome DevTools MCP server  ->  your Chrome browser (real one)
```

The server talks to Chrome through the DevTools Protocol, the same thing the F12 developer tools use. When you use it to test a local site like `localhost:3000`, it behaves like a real visitor, so it catches real bugs.

## Step 1: decide where to put the config

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` on Windows, `~/.config/opencode/opencode.jsonc` on Linux/macOS |
| Project (just this repo) | `opencode.json` in the project folder |

Put it in the global file if you want browser testing everywhere, or the project file for just this repo.

## Step 2: add the Chrome DevTools MCP server

Add this block to the config file:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "chrome-devtools": {
      "type": "local",
      "command": ["npx", "-y", "chrome-devtools-mcp@latest"],
      "enabled": true
    }
  }
}
```

That is the minimum. The server launches its own clean Chrome instance for testing.

## Step 3: restart and verify

Config is only loaded at startup, so quit and restart OpenCode after saving.

Check the server registered:

```bash
opencode mcp
```

You should see `chrome-devtools` listed as connected. Then ask OpenCode to test something:

> Open [https://example.com](https://example.com) and tell me what the page says.

A fresh Chrome window opens, OpenCode reads the page, and answers.

## Useful options

You can add flags to the `command` list to change the behavior:

```json
"command": [
  "npx", "-y", "chrome-devtools-mcp@latest",
  "--headless", "--viewport=1920x1080"
]
```

| Flag | What it does |
| --- | --- |
| `--headless` | Run Chrome invisibly, no window. Good for background test runs |
| `--viewport=1920x1080` | Set the browser window size for desktop testing |
| `--device="iPhone 15"` | Emulate a phone for mobile testing |
| `--channel=stable` | Use your installed Chrome instead of the bundled Chromium |
| `--autoConnect` | Connect to your already-running Chrome (Chrome will ask permission, click Allow) |
| `--browserUrl=http://127.0.0.1:9222` | Attach to a Chrome you started yourself with remote debugging |
| `--isolated` | Use a completely fresh profile with no cookies or history |
| `--slim` | Expose a minimal set of 3 tools (navigation, scripts, screenshots only) |

## Testing a real site, step by step

Ask OpenCode in plain words. For example, to test a login flow on `localhost:3000`:

1. "Open localhost:3000 and take a snapshot of the page"
2. "Click the login button"
3. "Fill the username and password fields"
4. "Submit the form and tell me what happens"
5. "Check the console for errors and list any failed network requests"
6. "Take a screenshot of the result"

You can also ask for a full report at the end:

> Test the signup flow on localhost:3000. Fill the form, submit it, check for console errors and failed requests, and give me a test report with screenshots.

## The tools it gives OpenCode

| Tool | What it does |
| --- | --- |
| `navigate_page` / `new_page` | Open a URL in the current or a new tab |
| `list_pages` / `select_page` / `close_page` | Manage open tabs |
| `take_snapshot` | Read the page as text with clickable element IDs |
| `take_screenshot` | Save a picture of the page or an element |
| `click` / `fill` / `fill_form` | Click things and fill forms |
| `type_text` / `press_key` | Type text and press keys like Enter |
| `hover` / `drag` / `upload_file` | Hover, drag elements, upload files |
| `handle_dialog` | Accept or dismiss browser dialogs |
| `evaluate_script` | Run JavaScript in the page |
| `wait_for` | Wait until some text appears on the page |
| `emulate` / `resize_page` | Pretend to be a different device, or resize the window |
| `lighthouse_audit` | Run a full Lighthouse check (performance, accessibility, SEO) |
| `performance_start_trace` / `performance_stop_trace` | Record a performance trace |
| `list_console_messages` / `get_console_message` | See console logs and errors |
| `list_network_requests` / `get_network_request` | See all network requests and their status codes |
| `take_heapsnapshot` | Capture a heap snapshot for memory debugging |

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Server not listed in `opencode mcp` | Quit and restart OpenCode completely. A stale server process is the usual cause |
| Chrome asks for permission | That is normal when connecting to your running Chrome. Click Allow |
| Connection drops right after connecting | Another DevTools window is already attached. Close other DevTools connections |
| No permission dialog appears | Your Chrome is too old. Update to Chrome 144 or newer |
| `npx` downloads slowly | Use a proxy, or preinstall with `npm install -g chrome-devtools-mcp` |
| Sites block the test browser | Some sites block automated browsers. Add `--channel=stable` to use your normal Chrome |

## A note about Varonika

Varonika talks through OpenCode, so this same setup automatically gives her browser testing too. Once the server is running, you can ask her things like "open my website on localhost, test the search box, and tell me if there are any console errors." She will drive the browser and report back. Varonika also has OpenCode's own built-in browser tools even without this setup. This server adds the full Chrome DevTools feature set on top.
