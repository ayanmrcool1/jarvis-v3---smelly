# JARVIS

Local voice assistant with a HUD, wake-word loop, speech-to-text, TTS, OpenAI brain, screen tools, routines, memory, and local user profiles.

Windows is the main supported platform. macOS support is partial and best-effort.

## Fresh Windows Setup

1. Install Python 3.11 from [python.org](https://www.python.org/downloads/).
   Python 3.12 should also work, but 3.11 is the safest target for the voice dependencies.
2. Download or clone this project, then extract it anywhere.
3. Double-click `Setup_Jarvis.bat`.
4. When prompted, paste your OpenAI API key.
5. Double-click `Start_Jarvis.bat`.

That starts the web HUD and the voice core quietly in the background. Logs are still written to `logs/`.

For the desktop PySide HUD instead of the browser HUD, run `Start_Jarvis_Desktop_UI.bat`.

To stop JARVIS, double-click `Stop_Jarvis.bat`.

## Debug Launch

For development, run:

```bat
Start_Jarvis_Debug.bat
```

This opens a live debug console and streams JARVIS output while also writing logs. Use this when you want startup messages, tracebacks, transcriptions, tool calls, and voice-core prints visible in real time.

## Required API Keys

`OPENAI_API_KEY` is required for the AI brain, vision tools, tool-calling, and web research. Setup creates `.env` from `.env.example` if it is missing.

TTS uses Edge TTS by default, so no TTS API key is required. ElevenLabs is optional:

```env
TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=your_key_here
```

If ElevenLabs is selected but the key is missing or fails, JARVIS falls back to Edge TTS.

## Logs

Setup and launch logs are written to `logs/`.

Useful files:

- `logs/launcher_*.log`
- `logs/setup_*.log`
- `logs/web_hud_*.log`
- `logs/desktop_hud_*.log`
- `logs/voice_core_*.log`

If the HUD opens but the voice core crashes, check the newest `voice_core_*.log`.

## macOS Partial Support

Try:

```bash
bash setup_mac.command
bash start_mac.command
bash stop_mac.command
```

macOS may run the web HUD, AI brain, microphone loop, and Edge TTS, depending on Python/package/audio permissions.

Windows-only or Windows-first features:

- Global hotkey listener
- Windows app discovery and launching
- Windows system volume control
- Some active browser/window inspection paths

Screen reading/clicking on macOS may require Accessibility and Screen Recording permissions. If audio install or microphone access fails, install/allow the missing macOS audio permissions or dependencies and rerun setup.

## Private Local Data

The following are local runtime data and are ignored by Git:

- `.env`
- `.venv/`
- `data/*.json`
- `data/user_profiles/`
- `data/tts_cache/`
- `data/jarvis_processes.json`
- `recordings/`
- `screenshots/`
- `logs/`
- `backups/`

This keeps your personal memory, profile, chat history, screenshots, recordings, logs, and API keys out of GitHub.

If these files were already tracked in a Git repository, remove them from Git tracking once:

```bash
git rm --cached -r .env .venv data recordings screenshots logs backups
```

If you are manually creating a ZIP for release, `.gitignore` will not remove files from the ZIP. Run `Reset_Jarvis_Data.bat` first, or make the ZIP from a fresh clone.

## Test A Fresh Install

In a copy of the project:

1. Remove or rename `.venv`.
2. Remove or rename `.env`.
3. Run `Setup_Jarvis.bat`.
4. Confirm `.venv` and `.env` are created.
5. Run `Start_Jarvis.bat`.
6. Check `logs/voice_core_*.log` if the voice core exits.
7. Run `Stop_Jarvis.bat` to stop the background processes.

Do not delete your real `.env` unless you have the API keys saved elsewhere.
