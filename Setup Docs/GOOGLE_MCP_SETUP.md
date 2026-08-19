# Setting up Google access with google-mcp-server (ngs)

This page explains how to give **OpenCode** (and through it, Varonika) access to your **Google account**: Gmail, Calendar, Drive, Docs, Sheets, and Slides. Once set up, you can ask her things like "check my mail", "what's on my calendar tomorrow", or "find that PDF in my Drive".

## What you get

| Google service | What she can do |
| --- | --- |
| Gmail | Search and read emails, manage labels |
| Calendar | List, create, update, and delete events |
| Drive | Find files, read metadata, create and delete files |
| Docs | Read documents, create new ones, append text |
| Sheets | Read and edit spreadsheets |
| Slides | Read and create presentations |

Multiple Google accounts are supported, and she picks the right one automatically.

## How it works

```text
OpenCode  ->  google-mcp-server (runs on your machine)  ->  your Google account (via Google's APIs)
```

This server is a mature, stable program written in Go. It logs into Google once, stores the login token on your machine, and refreshes it automatically when it expires. Nothing is stored on any cloud other than Google itself.

## Before you start

You need a **Google Cloud project** with a few APIs turned on, and **OAuth credentials**. This is a one-time setup, takes about 10 minutes, and costs nothing.

## Step 1: create a Google Cloud project and enable the APIs

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in.
2. Create a new project (or pick an existing one).
3. Go to **APIs & Services > Library** and enable these APIs, one by one:

| API | Needed for |
| --- | --- |
| Gmail API | Email |
| Google Calendar API | Calendar |
| Google Drive API | Drive |
| Google Docs API | Docs |
| Google Sheets API | Sheets |
| Google Slides API | Slides |

## Step 2: create OAuth credentials

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth client ID**.
3. Choose **Desktop app** as the application type and give it a name like "Google MCP Server".
4. Click Create, then **Download JSON** on the created client.
5. Rename the downloaded file to `config.json`.

Now place it where the server looks for it. Create the folder and move it:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.google-mcp-server"
Move-Item -Path .\config.json -Destination "$env:USERPROFILE\.google-mcp-server\config.json"
```

On Linux/macOS the path is `~/.google-mcp-server/config.json`.

Alternative: set two environment variables instead of the file: `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET`. The file is easier, stick with it.

## Step 3: install the server

**Windows:** download the pre-built Windows binary from the [releases page](https://github.com/ngs/google-mcp-server/releases). It is a single `.exe` file. Put it somewhere permanent like `C:\Tools\google-mcp-server.exe`.

**macOS / Linux (Homebrew):**

```bash
brew tap ngs/tap
brew install google-mcp-server
```

**Or build from source (if you have Go installed):**

```bash
go install go.ngs.io/google-mcp-server@latest
```

## Step 4: log in to Google (first time only)

Run the server directly once. This opens your browser for the Google login:

```bash
C:\Tools\google-mcp-server.exe        # Windows
google-mcp-server                      # macOS / Linux
```

A browser window opens, log in with your Google account, and click through the permission screens. The login token is saved on your machine at `~/.google-mcp-accounts/<your-email>.json`. From now on the server just uses the saved token.

## Step 5: add it to OpenCode's config

Create or edit `opencode.json` in the project folder (or `C:\Users\<you>\.config\opencode\opencode.json` for all projects) and add:

```json
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "google": {
      "type": "local",
      "command": ["C:\\Tools\\google-mcp-server.exe"],
      "enabled": true
    }
  }
}
```

On macOS/Linux the command is the binary path, for example `["/opt/homebrew/bin/google-mcp-server"]`.

## Step 6: restart and verify

Quit and restart OpenCode, then check the server registered:

```bash
opencode mcp
```

You should see `google` listed as connected. Then test it:

> List my Google calendars.
> Show my recent Gmail messages.
> List files in my Google Drive.

If those return real data, everything works.

## Security note

This gives the agent **real access to your Google account**, including reading your mail. Treat it like giving a human assistant your passwords:

- Only use it on your own machine, the tokens are stored in your user folder
- Check what the agent does with your data now and then
- To take the access away at any time: delete the token file `~/.google-mcp-accounts/<email>.json`, or revoke access in your Google account settings at [myaccount.google.com](https://myaccount.google.com)

## Troubleshooting

| Problem | Fix |
| --- | --- |
| Login browser does not open | Make sure you are running the server directly (Step 4) and `config.json` exists with your client ID and secret |
| "Invalid client" error | The `config.json` is not the OAuth JSON you downloaded, or the app type is not "Desktop app" |
| Permission denied | You did not grant all the requested permissions during login. Re-run Step 4 |
| Connection works but tokens expired | Tokens refresh automatically. If it still fails, delete `~/.google-mcp-accounts/<email>.json` and log in again (Step 4) |
| Rate limit errors | The server backs off automatically, just wait a bit before asking again |
| Server not listed in `opencode mcp` | Quit and restart OpenCode completely, then check the command path in the config |

## A note about Varonika

Varonika talks through OpenCode, so this same setup automatically gives her your Google access too. Once it works, you can say things like "Hey Varonika, check my mail and tell me what's new" or "Hey Varonika, what meetings do I have tomorrow?" and she will look it up and speak the answer. Remember the security note above, she only does what you ask.
