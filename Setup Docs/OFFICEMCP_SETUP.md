# Setting up OfficeMCP for Office automation

This page explains how to give **OpenCode** (and through it, Varonika) the power to control **Microsoft Office** applications: Word, Excel, PowerPoint, Access, OneNote, Visio, Project, and WPS. Once set up, you can say things like "create a PowerPoint presentation about quarterly results" or "read the data from that Excel file" and she will drive the real Office application on your screen.

## What you get

| Office app | What she can do |
| --- | --- |
| Word | Create, read, edit, format documents |
| Excel | Read cells, write data, create formulas, format sheets |
| PowerPoint | Create slides, add content, run presentations |
| Access | Work with databases |
| OneNote | Read and write notes |
| Visio | Create diagrams |
| Project | Work with project plans |
| WPS apps | Same as above, for WPS Office |

> **Note:** `Officer.Outlook` and `Officer.Publisher` are both confirmed in the source code (Officer.py), but there are no Outlook-specific or Publisher-specific MCP tools. You can automate them through the `RunPython` tool.

## How it works

```text
You: "Hey Varonika, open Excel and create a budget spreadsheet"
  -> Varonika -> OpenCode -> OfficeMCP server -> COM interface -> real Excel on your screen
```

OfficeMCP talks to Office through the Windows COM interface, the same technology that VBA macros use. It opens the real application, not a file parser, so it can see and control everything a human can.

## Platform support

| Platform | Supported |
| --- | --- |
| Windows | Yes |
| macOS | **No** |
| Linux | **No** |

> **This is a hard limitation.** OfficeMCP uses Windows COM (Component Object Model) to control Office. COM does not exist on macOS or Linux. There is no workaround. If you are on macOS or Linux, this server cannot be used with Varonika.

## Before you start

1. **Windows** (10 or 11)
2. **Microsoft Office** installed and activated (Office 365, Office 2019, or later). WPS Office also works.
3. **Python 3.12 or above** installed and on PATH
4. **uv** installed (the Python package runner that OfficeMCP uses)
5. **OpenCode** installed and working with your model of choice

## Step 1: install uv

Open PowerShell or Command Prompt and run:

```powershell
pip install uv
```

Verify it is installed:

```powershell
uv --version
```

It should print a version number like `uv 0.x.x`.

## Step 2: verify Office is installed

Open PowerShell and run:

```powershell
uvx officemcp
```

If Office is installed, the server starts and waits for requests. If it is not installed, you will see errors. You can also check with a quick test in OpenCode after setup (Step 4).

## Step 3: decide on a transport mode

OfficeMCP supports two transport modes. You can run both at the same time if you want.

### Option A: stdio mode (simpler)

One OfficeMCP server process per OpenCode session. OpenCode starts it automatically when you send a prompt and kills it when you close the session. No server URL to manage.

**Best for:** single-user, single-project setups.

### Option B: SSE mode (recommended)

One OfficeMCP server process handles multiple OpenCode sessions and other MCP clients at the same time. You start it once and it stays running. More flexible, and you can share it across tools.

**Best for:** multi-project setups, or if you want the server always available.

Both modes work with Varonika. Pick whichever you prefer.

## Step 4: configure OpenCode

### If using stdio mode

Add this to your OpenCode config file. The config lives at one of these locations:

| Location | Path |
| --- | --- |
| Global (all projects) | `C:\Users\<you>\.config\opencode\opencode.jsonc` |
| Project (just Varonika) | `opencode.json` in the Varonika folder |

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "officemcp": {
        "type": "local",
        "command": ["uvx", "officemcp"],
        "enabled": true
      }
    }
  }
}
```

That is it. OpenCode will start the OfficeMCP server automatically when it needs it.

### If using SSE mode

**Step 4a:** Start the SSE server. Open a PowerShell window and run:

```powershell
uvx officemcp sse
```

The server prints its URL. By default it is `http://127.0.0.1:8888/sse`.

You can customise the port, host, and working folder:

```powershell
uvx officemcp sse --port 7777 --host 127.0.0.1 --folder D:\myofficefolder
```

Leave this window open. The server must be running for Varonika to use it.

**Step 4b:** Add this to your OpenCode config file:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "officemcp": {
        "type": "remote",
        "url": "http://127.0.0.1:8888/sse",
        "enabled": true
      }
    }
  }
}
```

If you changed the port or host in Step 4a, update the URL to match.

> **OpenCode version note:** OpenCode v2 `"type": "remote"` uses the Streamable HTTP transport. OfficeMCP's SSE server uses the older SSE transport. If the remote type does not work, use the stdio mode instead (Option A), which is fully supported. You can also use the legacy config format: `"officemcp": { "url": "http://127.0.0.1:8888/sse" }` directly under `"mcp"` without the `"servers"` wrapper.

## Step 5: restart and verify

1. Quit and restart OpenCode (config is only loaded at startup).
2. Restart Varonika if it was running.
3. Check that the server is connected:

```bash
opencode mcp
```

You should see `officemcp` listed as connected.

4. Test it by asking Varonika or OpenCode:

> Check which Office applications are installed on my computer.

If OfficeMCP is working, it will list every installed Office app.

## Available tools

OfficeMCP exposes these tools to OpenCode:

| Tool | What it does |
| --- | --- |
| `AvailableApps()` | Check if Microsoft Office applications are installed on your computer |
| `RunningApps()` | Get a list of currently running Office applications |
| `IsAppAvailable(app_name)` | Check if a specific Office application is installed |
| `Launch(app_name, visible)` | Launch a new Office application and set its visibility |
| `Visible(app_name, visible)` | Set the specified Office application's visibility to True or False |
| `Quit(app_name, force)` | Quit the specified Office application |
| `Demonstrate()` | Run a demonstration of OfficeMCP automation features |
| `Speak(text, volume, rate)` | Speak text aloud. Volume 0-100, rate -10 to 10 |
| `Beep(frequency, duration)` | Play a beep sound. Frequency 37-32767, duration 0-65535 |
| `RootFolder()` | Return the OfficeMCP root work folder (default `D:\@OfficeMCP`) |
| `IsFileExists(sub_file_path)` | Check if a file exists in the OfficeMCP root folder |
| `DownloadImage(url, save_path)` | Download an image from a given URL and save it to the specified path |
| `ScreenShot(save_path)` | Take a screenshot and save it to the specified path |
| `RunPython(code, data)` | Run python code in the OfficeMCP server context. Returns a dict with `success`, `output`, and optionally `error` |

### RunPython: the powerful one

`RunPython` is the most powerful tool in the OfficeMCP server. AI can use this tool to do anything supported by the server, including automating Office applications. Special objects give you full control over every Office application:

| Object | What it holds |
| --- | --- |
| `Officer.Word` | The current Microsoft Word COM application |
| `Officer.Excel` | The current Microsoft Excel COM application |
| `Officer.PowerPoint` | The current Microsoft PowerPoint COM application |
| `Officer.Outlook` | The current Microsoft Outlook COM application |
| `Officer.Access` | The current Microsoft Access COM application |
| `Officer.OneNote` | The current Microsoft OneNote COM application |
| `Officer.Publisher` | The current Microsoft Publisher COM application |
| `Officer.Visio` | The current Microsoft Visio COM application |
| `Officer.Project` | The current Microsoft Project COM application |
| `Officer.Kwps` | The current WPS Word COM application |
| `Officer.Ket` | The current WPS Excel COM application |
| `Officer.Kwpp` | The current WPS PowerPoint COM application |

There is an object `output` that serves as the return value of `RunPython`. Put your result into it, like `output = "run python succeeded"`, and `RunPython` will return that string to the AI model.

#### RunPython examples

**Write to an Excel cell:**

```python
Officer.Excel.ActiveSheet.Cells(1, 1).Value = "Hello from Varonika"
output = "Cell A1 set successfully"
```

**Read from an Excel cell:**

```python
val = Officer.Excel.ActiveSheet.Cells(1, 1).Value
output = f"Cell A1 contains: {val}"
```

**Create a new Word document:**

```python
doc = Officer.Word.Documents.Add()
doc.Content.Text = "This document was created by Varonika."
doc.SaveAs("D:\\@OfficeMCP\\report.docx")
output = "Document created and saved."
```

**Draw on a Visio page:**

```python
Officer.Visio.ActivePage.DrawRectangle(1, 1, 5, 3)
output = "Rectangle drawn on the page."
```

> **Security warning (from the OfficeMCP authors):** OfficeMCP does not limit the usage of Python. Especially the `RunPython` tool executes Python code created by the AI model. This is the most powerful part of OfficeMCP, but we cannot guarantee that the AI model will not do something bad to your computer. The OfficeMCP authors take no responsibility. Only use OfficeMCP in trusted environments and review what the AI is doing.

## Example prompts

Once everything is set up, try these with Varonika:

- "Open Excel and create a budget spreadsheet with monthly expenses"
- "Open Word and write a meeting notes template"
- "Create a PowerPoint presentation about our project status"
- "Read the data from D:\data\sales.xlsx and summarise it"
- "Check which Office apps are installed on this computer"
- "Open Outlook and show my recent emails"

## Troubleshooting

| Problem | Fix |
| --- | --- |
| `uvx` is not recognised | Python is not installed or `uv` is not on PATH. Install Python and run `pip install uv`. |
| Office apps not detected | Make sure Microsoft Office is installed and activated. WPS Office also works. |
| Server not listed in `opencode mcp` | Quit and restart OpenCode completely. Config is only loaded at startup. |
| COM errors or "server execution failed" | Close any Office application that is stuck or hung. Try again. Sometimes a reboot helps. |
| Varonika says "OpenCode isn't available right now" | That is an OpenCode problem, not OfficeMCP. Check OpenCode is on PATH and runs. |
| SSE server won't start (port in use) | Another process is using port 8888. Use a different port: `uvx officemcp sse --port 7777`. |
| RunPython errors | Check the Python code syntax. The `Officer` object is only available inside RunPython. |
| "OfficeMCP not working on macOS/Linux" | Correct. This server requires Windows COM. There is no workaround. |
| Office opens but does nothing | OfficeMCP uses COM automation, which controls the real application. If the app opens but no action happens, the AI model may have sent the wrong command. Try rephrasing your request. |

## A note about Varonika

Varonika talks through OpenCode, so once the OfficeMCP server is connected, she can control Office applications for you. Say "Hey Varonika" and ask her to open Word, create a spreadsheet, or anything else you need. She will drive the real Office application on your screen.

Remember: this only works on Windows. macOS and Linux users cannot use OfficeMCP.
