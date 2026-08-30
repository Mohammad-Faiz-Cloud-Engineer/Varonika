# Setting up Computer Use MCP in OpenCode

This page explains how to give **OpenCode** (and through it, Varonika) the power to control your entire desktop. Once set up, the AI can see running apps, read their interface elements, click buttons, type text, scroll, drag, and press keys, all through the accessibility layer without taking over your real mouse and keyboard.

This works on **Windows, macOS, and Linux**.

## What you get

| Thing | What it means |
| --- | --- |
| See running apps | List all open applications and read their interface |
| Read app state | Get the full accessibility tree and a screenshot of any app |
| Click and type | Click buttons, fill forms, type text into any app |
| Scroll and drag | Scroll lists, drag elements between locations |
| Press keys | Send keyboard shortcuts like `ctrl+s` or `page_up` |
| Screen capture | Take screenshots of the whole desktop or individual windows |

## How it works

```text
OpenCode  ->  open-computer-use (MCP server)  ->  accessibility API  ->  your desktop apps
```

Open Computer Use is a local MCP server that talks to your OS accessibility APIs (UI Automation on Windows, AX on macOS, AT-SPI2 on Linux). It reads the interface tree of running apps and can interact with them. OpenCode talks to it through the standard MCP protocol. Everything runs locally on your machine.

## Before you start

- **Node.js.** Check with `node --version`.
- **OpenCode installed** and working with your model of choice.
- **A signed-in desktop session.** This tool needs a real GUI desktop to work.

### Platform-specific requirements

| Platform | Requirements |
| --- | --- |
| **Windows** | Signed-in desktop session. UI Automation works out of the box. |
| **macOS 14+** | One-time permission grants: Accessibility and Screen Recording. The `ocu doctor` command walks you through it. |
| **Linux** | Signed-in desktop session with AT-SPI2 (GNOME, KDE, and other major desktops ship it by default). |

## Step 1: install Open Computer Use

```bash
npm install -g @opensymph/open-computer-use
```

Verify it works:

```bash
ocu --version
```

### macOS: grant permissions

Run the doctor command. It checks what permissions are missing and opens the right System Settings pages:

```bash
ocu doctor
```

You need to grant **Accessibility** and **Screen Recording** to the Open Computer Use app. The `ocu doctor` command walks you through which permissions are missing and opens the right System Settings pages. This is a one-time step. The permissions survive version upgrades.

### Linux: check your desktop session

Make sure you are running in a logged-in desktop session (not a pure SSH tty). AT-SPI2 needs D-Bus access to the session bus. GNOME, KDE, XFCE, and other major desktops provide this by default.

If tools return empty results, check that these environment variables are set:

```bash
echo $XDG_RUNTIME_DIR
echo $DBUS_SESSION_BUS_ADDRESS
```

If they are empty, try logging out and back in, or run `ocu doctor` for diagnostics.

## Step 2: connect to OpenCode

### Option A: auto-install (recommended)

```bash
ocu install-opencode-mcp
```

This writes the config to your OpenCode config file automatically.

### Option B: manual config

Create or edit your OpenCode config file and add this block:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "open-computer-use": {
      "type": "local",
      "command": "open-computer-use",
      "args": ["mcp"],
      "enabled": true
    }
  }
}
```

Where to put it:

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` on Windows, `~/.config/opencode/opencode.jsonc` on Linux/macOS |
| Project (just this repo) | `opencode.json` in the project folder |

## Step 3: verify it works

Test from the command line first:

```bash
ocu call list_apps
```

You should see a JSON response listing running applications. If it works, restart OpenCode and the tools will be available to the AI.

## Tools available

Nine core tools, identical across all platforms:

| Tool | What it does |
| --- | --- |
| `list_apps` | List running and recently used applications |
| `get_app_state` | Read an app's accessibility tree and screenshot |
| `click` | Click by element index or screenshot coordinates |
| `perform_secondary_action` | Invoke an element's own secondary action |
| `scroll` | Scroll an element by pages, or a window by pixel deltas |
| `drag` | Drag between two coordinates |
| `type_text` | Type text, Unicode-safe, background-first |
| `press_key` | Press a key or chord (`ctrl+s`, `return`, `page_up`...) |
| `set_value` | Set the value of a settable control directly |

Five additional window-level tools (currently Windows only, macOS and Linux in progress):

| Tool | What it does |
| --- | --- |
| `list_windows` | List all windows across running apps |
| `get_window` | Get a specific window's details |
| `get_window_state` | Get structured window state with accessibility tree and screenshots |
| `launch_app` | Launch an application (requires env var gate) |
| `activate_window` | Bring a window to the foreground (requires env var gate) |

## CLI usage

You can run any tool directly from the shell without going through OpenCode:

```bash
# List running apps
ocu call list_apps

# Get app state
ocu call get_app_state --args '{"app": "Notepad"}'

# Chain multiple calls in sequence
ocu call --calls '[
  {"tool": "list_apps", "args": {}},
  {"tool": "get_app_state", "args": {"app": "Notepad"}}
]'
```

Display-level commands (CLI only, not MCP tools):

```bash
# Take a screenshot of the whole desktop
open-computer-use screenshot --output shot.png

# Get cursor position
open-computer-use cursor-position
```

## Security

Open Computer Use has built-in guardrails:

- **Password managers are always refused.** The tool will not interact with password manager apps.
- **App launching and focus stealing are gated.** These require explicit environment variables to enable.
- **Global input injection is gated.** Moving the real pointer/keyboard requires an explicit opt-in flag.
- **Everything runs locally.** No data leaves your machine. No cloud service involved.

### Windows-specific environment variables

| Variable | What it enables |
| --- | --- |
| `OPEN_COMPUTER_USE_WINDOWS_ALLOW_APP_LAUNCH=1` | Allow `launch_app` to start new apps |
| `OPEN_COMPUTER_USE_WINDOWS_ALLOW_FOCUS_ACTIONS=1` | Allow `activate_window` to steal focus |
| `OPEN_COMPUTER_USE_WINDOWS_ALLOW_FOREGROUND_INPUT=1` | Allow `global` input method to move real pointer/keyboard |
| `OPEN_COMPUTER_USE_WINDOWS_ALLOW_UIA_TEXT_FALLBACK=1` | Allow UIA text input fallback |

### macOS-specific environment variable

| Variable | What it enables |
| --- | --- |
| `OPEN_COMPUTER_USE_MACOS_ALLOW_FOREGROUND_INPUT=1` | Allow `global` input method to move real pointer/keyboard |

### Linux-specific environment variable

| Variable | What it enables |
| --- | --- |
| `OPEN_COMPUTER_USE_ALLOW_GLOBAL_POINTER_FALLBACKS=1` | Allow `global` input method to move real pointer/keyboard via xdotool |

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `open-computer-use: command not found` | Run `npm bin -g` to find the global npm bin path, add it to your PATH |
| macOS: tools return empty results | Run `ocu doctor`, grant Accessibility and Screen Recording in System Settings |
| Linux: tools return empty results | Make sure you are in a logged-in desktop session, not SSH. Check `XDG_RUNTIME_DIR` and `DBUS_SESSION_BUS_ADDRESS` |
| Windows: tools return empty results | Make sure you are in a signed-in desktop session, not a headless SSH session |
| `list_apps` is empty on Windows via SSH | UI Automation needs a real desktop session. SSH-only sessions cannot see GUI apps |
| Server starts but OpenCode cannot connect | Make sure your config has `"args": ["mcp"]` without that arg the CLI mode starts instead of the MCP server. Restart OpenCode after changing config |
| Permission denied on macOS | Run `open-computer-use doctor` and follow the prompts |

## Further reading

- [GitHub: opensymph/open-computer-use](https://github.com/opensymph/open-computer-use) - source code and full documentation
- [Architecture docs](https://github.com/opensymph/open-computer-use/blob/main/docs/ARCHITECTURE.md) - how the three runtimes work
- [MIT License](https://github.com/opensymph/open-computer-use/blob/main/LICENSE)
