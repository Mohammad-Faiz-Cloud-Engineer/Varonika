# Varonika

Varonika is a hands free voice assistant for your PC. You say "Hey Varonika", she listens, asks OpenCode to do the work, and speaks the answer back to you.

She can open apps, search the web, read files, run commands, and answer questions. She runs fully on your machine, in the background, and only starts listening after you say the wake word.

## What it does

- Wake word detection ("Hey Varonika") so she is never recording unless you call her
- Speech to text with Whisper (local, no cloud)
- Talks to OpenCode, which runs on your machine too
- Text to speech with Kokoro, so you hear the answer, not just read it
- A small desktop window that shows what she is doing, what she heard, and what she said
- Hotkeys if you do not want to use your voice

## Requirements

- Windows (it is built and tested on Windows)
- Python 3.11 or newer
- The `opencode` CLI installed and available on your PATH (this is the brain she talks to)

## Setup

```bash
pip install -e .
```

Varonika needs a few models before she can hear and speak. The app downloads them automatically on first start, or you can do it yourself:

```bash
python scripts/download_models.py
```

This fetches:

- `models/ggml-small.en.bin` (Whisper speech to text model)
- `models/wakeword.onnx` (wake word model)

If you have your own trained wake word model, drop it at the project root as `Hey_Varonika.onnx` and the script will copy it into place. Without a custom model, the script downloads a placeholder that responds to "Hey Jarvis" instead.

## Running

```bash
python app/main.py
```

First launch checks the models, then starts the desktop window and the background listener. You will see "Hotkeys registered" in the console when she is ready.

## Talking to her

1. Say "Hey Varonika". She switches to listening mode.
2. Speak your request. She shows what she heard on screen, then sends it to OpenCode.
3. She speaks the answer while it is displayed in the window.

You can interrupt her while she is talking by saying the wake word again.

### Hotkeys

- `Alt+Space`: activate listening mode without using the wake word
- `Alt+T`: toggle between wake word mode and continuous listening mode

## Configuration

All settings have sensible defaults, but you can create a `config.yaml` next to the project root to override them:

```yaml
wake_word_phrase: "Hey Varonika"   # what you say to wake her
wake_word_threshold: 0.5           # higher = harder to trigger
stt_model: "models/ggml-small.en.bin"
stt_language: "en"
silence_timeout_ms: 2500           # pause before she stops listening
energy_threshold: 0.015            # mic sensitivity
tts_voice: "af_bella"              # Kokoro voice
continuous_mode: true              # keep listening after each answer
conversation_timeout: 8
opencode_port: 8080
```

## How it fits together

- `app/audio/capture.py` reads microphone audio in small chunks
- `app/wakeword/detector.py` watches those chunks for the wake word
- `app/stt/whisper_engine.py` turns your speech into text
- `app/opencode/client.py` talks to OpenCode over the ACP protocol
- `app/conversation/manager.py` runs the state machine and ties it all together
- `app/tts/kokoro_engine.py` turns the answer into spoken audio
- `app/ui/main_window.py` is the little status window

## Troubleshooting

**She hears herself and answers her own voice.** This should not happen anymore. She refuses to transcribe while she is speaking, and she no longer says "Yes?" after the wake word, so your command is not clipped.

**OpenCode stops responding after a big answer.** This was a bug in the data line limit. The connection now allows very large messages, so long tool results no longer kill the link.

**Nothing happens when you say the wake word.** Check that the console shows the wake word model loaded, and that your mic is the default input device. If you are using the placeholder model, you must say "Hey Jarvis".

## Notes

The first run downloads the Kokoro voice model and may take a little while. Be patient, she warms up.

## License

Private project. Use it, change it, break it, fix it.