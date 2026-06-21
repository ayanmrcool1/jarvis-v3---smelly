import os
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path

import psutil


# =========================
# JARVIS PHASE 4 SYSTEM TOOLS
# =========================

APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",

    "edge": "msedge",
    "microsoft edge": "msedge",

    "notepad": "notepad",
    "note pad": "notepad",
    "notes": "notepad",

    "calculator": "calc",
    "calc": "calc",

    "cmd": "cmd",
    "command prompt": "cmd",
    "powershell": "powershell",

    "vs code": "code",
    "visual studio code": "code",
    "vscode": "code",

    "discord": "discord",
    "spotify": "spotify",

    "note pattern": "notepad",
    "note pan": "notepad",
    "note ped": "notepad",
}

WEBSITE_ALIASES = {
    "tradingview": "https://www.tradingview.com/",
    "trading view": "https://www.tradingview.com/",

    "nasdaq": "https://www.nasdaq.com/market-activity/futures",
    "nasdaq futures": "https://www.nasdaq.com/market-activity/futures",

    "google": "https://www.google.com/",
    "youtube": "https://www.youtube.com/",
    "you tube": "https://www.youtube.com/",
}

APP_DISPLAY_NAMES = {
    "notepad": "Notepad",
    "note pad": "Notepad",
    "notepads": "Notepad",
    "note pads": "Notepad",
    "note pattern": "Notepad",
    "note patten": "Notepad",
    "note pan": "Notepad",
    "note ped": "Notepad",
    "notes": "Notepad",

    "chrome": "Chrome",
    "google chrome": "Chrome",

    "edge": "Microsoft Edge",
    "microsoft edge": "Microsoft Edge",

    "calculator": "Calculator",
    "calc": "Calculator",

    "vs code": "VS Code",
    "visual studio code": "VS Code",
    "vscode": "VS Code",

    "tradingview": "TradingView",
    "trading view": "TradingView",

    "youtube": "YouTube",
    "you tube": "YouTube",

    "discord": "Discord",
    "spotify": "Spotify",
}


def get_current_datetime():
    """
    Return the current local date and time.
    """
    now = datetime.now()

    return {
        "success": True,
        "time": now.strftime("%I:%M %p").lstrip("0"),
        "date": now.strftime("%A, %B %d, %Y").replace(" 0", " "),
        "message": now.strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " "),
    }


def open_application(app_name):
    """
    Open an application or known website by name.
    Uses aliases so speech mistakes like 'note pad' still open Notepad.
    """

    if not app_name or not app_name.strip():
        return {
            "success": False,
            "message": "No application name was provided.",
        }

    clean_name = " ".join(app_name.lower().strip().split())

    try:
        if clean_name in WEBSITE_ALIASES:
            url = WEBSITE_ALIASES[clean_name]
            webbrowser.open(url)

            display_name = APP_DISPLAY_NAMES.get(clean_name, clean_name.title())

            return {
                "success": True,
                "message": f"Opening {display_name}.",
            }

        if clean_name in APP_ALIASES:
            command = APP_ALIASES[clean_name]
            subprocess.Popen(command, shell=True)

            display_name = APP_DISPLAY_NAMES.get(clean_name, clean_name.title())

            return {
                "success": True,
                "message": f"Opening {display_name}.",
            }

        if "." in clean_name:
            url = clean_name

            if not url.startswith("http"):
                url = "https://" + url

            webbrowser.open(url)

            return {
                "success": True,
                "message": f"Opening {app_name}.",
            }

        return {
            "success": False,
            "message": f"I do not have a local shortcut for {app_name} yet.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to open {app_name}: {error}",
        }


def search_web(query):
    """
    Open a web search in the default browser.
    """
    if not query or not query.strip():
        return {
            "success": False,
            "message": "No search query was provided.",
        }

    encoded_query = query.replace(" ", "+")
    url = f"https://www.google.com/search?q={encoded_query}"

    try:
        webbrowser.open(url)

        return {
            "success": True,
            "message": f"Searching the web for {query}.",
            "url": url,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to search the web: {error}",
        }


def run_terminal_command(command, timeout_seconds=10):
    """
    Run a terminal command and return the output.
    """
    if not command or not command.strip():
        return {
            "success": False,
            "message": "No command was provided.",
        }

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        output = result.stdout.strip()
        error = result.stderr.strip()

        return {
            "success": result.returncode == 0,
            "return_code": result.returncode,
            "stdout": output,
            "stderr": error,
            "message": output or error or "Command completed.",
        }

    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "message": f"Command timed out after {timeout_seconds} seconds.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to run command: {error}",
        }


def get_system_stats():
    """
    Return basic system stats.
    """
    try:
        battery = psutil.sensors_battery()

        return {
            "success": True,
            "cpu_percent": psutil.cpu_percent(interval=0.5),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(str(Path.home())).percent,
            "battery_percent": battery.percent if battery else None,
            "battery_plugged_in": battery.power_plugged if battery else None,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to get system stats: {error}",
        }


def set_volume(action):
    """
    Control Windows master speaker volume using pycaw's current high-level API.

    Supported actions:
    - up
    - down
    - mute
    - unmute
    """

    try:
        from pycaw.pycaw import AudioUtilities

        clean_action = action.lower().strip()

        device = AudioUtilities.GetSpeakers()
        volume = device.EndpointVolume

        current_volume = float(volume.GetMasterVolumeLevelScalar())
        current_mute = int(volume.GetMute())

        step = 0.10

        if clean_action == "up":
            new_volume = min(current_volume + step, 1.0)
            volume.SetMasterVolumeLevelScalar(new_volume, None)

            if current_mute:
                volume.SetMute(0, None)

            return {
                "success": True,
                "message": f"Volume increased to {int(new_volume * 100)}%.",
            }

        if clean_action == "down":
            new_volume = max(current_volume - step, 0.0)
            volume.SetMasterVolumeLevelScalar(new_volume, None)

            return {
                "success": True,
                "message": f"Volume decreased to {int(new_volume * 100)}%.",
            }

        if clean_action == "mute":
            volume.SetMute(1, None)

            return {
                "success": True,
                "message": "Volume muted.",
            }

        if clean_action == "unmute":
            volume.SetMute(0, None)

            return {
                "success": True,
                "message": "Volume unmuted.",
            }

        return {
            "success": False,
            "message": "Unsupported volume action. Use up, down, mute, or unmute.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to control volume: {error}",
        }