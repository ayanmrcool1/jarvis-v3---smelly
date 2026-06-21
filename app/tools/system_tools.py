import os
import difflib
import re
import shutil
import subprocess
import webbrowser
from datetime import datetime
from pathlib import Path
from urllib.parse import quote_plus

import psutil

from tools.progress import ToolProgress

try:
    import winreg
except ImportError:
    winreg = None


# =========================
# JARVIS PHASE 4 SYSTEM TOOLS
# =========================

APP_ALIASES = {
    "chrome": "chrome",
    "google chrome": "google chrome",

    "edge": "microsoft edge",
    "microsoft edge": "microsoft edge",

    "notepad": "notepad",
    "note pad": "notepad",
    "notes": "notepad",

    "calculator": "calculator",
    "calc": "calculator",

    "cmd": "command prompt",
    "command prompt": "command prompt",
    "powershell": "powershell",

    "vs code": "visual studio code",
    "visual studio code": "visual studio code",
    "vscode": "visual studio code",

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

    "opera gx": "Opera GX",
    "chatgpt": "ChatGPT",
    "chat gpt": "ChatGPT",
    "command prompt": "Command Prompt",
}

SHORTCUT_EXTENSIONS = {
    ".lnk",
    ".url",
    ".appref-ms",
}

SAFE_PROGRAM_EXTENSIONS = {
    ".exe",
}

UNSAFE_LAUNCHER_WORDS = {
    "uninstall",
    "uninstaller",
    "setup",
    "install",
    "installer",
    "update",
    "updater",
    "crash",
    "reporter",
    "helper",
}

SAFE_COMMAND_EXECUTABLES = {
    "notepad": {
        "display_name": "Notepad",
        "commands": ["notepad.exe"],
    },
    "calculator": {
        "display_name": "Calculator",
        "commands": ["calc.exe"],
    },
    "command prompt": {
        "display_name": "Command Prompt",
        "commands": ["cmd.exe"],
    },
    "powershell": {
        "display_name": "PowerShell",
        "commands": ["powershell.exe"],
    },
}


def _normalise_lookup_text(text):
    """
    Normalises app names for deterministic matching, not broad fuzzy matching.
    """

    text = str(text or "").lower()
    text = text.replace("&", " and ")
    text = text.replace("+", " plus ")
    text = re.sub(r"[^a-z0-9]+", " ", text)

    ignored_words = {
        "app",
        "application",
        "desktop",
    }

    words = [
        word
        for word in text.split()
        if word and word not in ignored_words
    ]

    return {
        "words": words,
        "word_set": set(words),
        "spaced": " ".join(words),
        "compact": "".join(words),
    }


def _app_match_score(query_name, candidate_name):
    query = _normalise_lookup_text(query_name)
    candidate = _normalise_lookup_text(candidate_name)

    query_compact = query["compact"]
    candidate_compact = candidate["compact"]

    if not query_compact or not candidate_compact:
        return 0

    if query_compact == candidate_compact:
        return 100

    if len(query_compact) < 4:
        return 0

    if candidate_compact.startswith(query_compact):
        return 90

    if query_compact in candidate_compact:
        return 82

    if query["word_set"] and query["word_set"].issubset(candidate["word_set"]):
        return 78

    return 0


def _possible_match_score(query_name, candidate_name):
    """
    Suggestion-only score for likely speech/STT distortions.
    It is intentionally not used as the primary auto-open signal.
    """

    query = _normalise_lookup_text(query_name)
    candidate = _normalise_lookup_text(candidate_name)

    query_compact = query["compact"]
    candidate_compact = candidate["compact"]

    if len(query_compact) < 4 or len(candidate_compact) < 4:
        return 0

    ratio = difflib.SequenceMatcher(None, query_compact, candidate_compact).ratio()

    return int(round(ratio * 100))


def _is_safe_launcher_name(name):
    candidate = _normalise_lookup_text(name)
    return not candidate["word_set"].intersection(UNSAFE_LAUNCHER_WORDS)


def _local_app_data_path():
    local_app_data = os.environ.get("LOCALAPPDATA")

    if local_app_data:
        return Path(local_app_data)

    return Path.home() / "AppData" / "Local"


def _known_app_path_specs():
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    local_app_data = _local_app_data_path()

    return [
        {
            "name": "Google Chrome",
            "paths": [
                program_files / "Google" / "Chrome" / "Application" / "chrome.exe",
                program_files_x86 / "Google" / "Chrome" / "Application" / "chrome.exe",
                local_app_data / "Google" / "Chrome" / "Application" / "chrome.exe",
            ],
            "priority": 5,
        },
        {
            "name": "Microsoft Edge",
            "paths": [
                program_files / "Microsoft" / "Edge" / "Application" / "msedge.exe",
                program_files_x86 / "Microsoft" / "Edge" / "Application" / "msedge.exe",
            ],
            "priority": 5,
        },
        {
            "name": "Opera GX",
            "paths": [
                local_app_data / "Programs" / "Opera GX" / "launcher.exe",
                local_app_data / "Programs" / "Opera GX" / "opera.exe",
                program_files / "Opera GX" / "launcher.exe",
                program_files / "Opera GX" / "opera.exe",
                program_files_x86 / "Opera GX" / "launcher.exe",
                program_files_x86 / "Opera GX" / "opera.exe",
            ],
            "priority": 15,
        },
        {
            "name": "Visual Studio Code",
            "paths": [
                local_app_data / "Programs" / "Microsoft VS Code" / "Code.exe",
                program_files / "Microsoft VS Code" / "Code.exe",
                program_files_x86 / "Microsoft VS Code" / "Code.exe",
            ],
            "priority": 15,
        },
        {
            "name": "ChatGPT",
            "paths": [
                local_app_data / "Programs" / "ChatGPT" / "ChatGPT.exe",
                program_files / "ChatGPT" / "ChatGPT.exe",
                program_files_x86 / "ChatGPT" / "ChatGPT.exe",
            ],
            "priority": 15,
        },
    ]


def _safe_iterdir(path):
    try:
        return list(path.iterdir())
    except Exception:
        return []


def _safe_rglob(path):
    for root, dir_names, file_names in os.walk(path, topdown=True, onerror=lambda error: None):
        dir_names[:] = [
            name
            for name in dir_names
            if name not in {"WindowsApps"}
        ]

        for file_name in file_names:
            yield Path(root) / file_name


def _shortcut_search_roots():
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    app_data = os.environ.get("APPDATA")
    public_dir = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))

    roots = [
        {
            "label": "common Start Menu",
            "path": program_data / "Microsoft" / "Windows" / "Start Menu" / "Programs",
            "priority": 20,
        },
        {
            "label": "user Start Menu",
            "path": Path(app_data) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
            if app_data else None,
            "priority": 10,
        },
        {
            "label": "user Desktop",
            "path": Path.home() / "Desktop",
            "priority": 30,
        },
        {
            "label": "public Desktop",
            "path": public_dir / "Desktop",
            "priority": 40,
        },
    ]

    return [
        root
        for root in roots
        if root["path"] and root["path"].exists()
    ]


def _program_files_roots():
    roots = []

    for env_name in ["ProgramFiles", "ProgramW6432", "ProgramFiles(x86)"]:
        value = os.environ.get(env_name)

        if not value:
            continue

        path = Path(value)

        if path.exists() and path not in roots:
            roots.append(path)

    return roots


def _iter_known_path_candidates():
    for spec in _known_app_path_specs():
        for path in spec["paths"]:
            if not path.exists() or path.suffix.lower() not in SAFE_PROGRAM_EXTENSIONS:
                continue

            if not _is_safe_launcher_name(path.stem):
                continue

            yield {
                "name": spec["name"],
                "path": path,
                "kind": "executable",
                "source": "known app path",
                "priority": spec["priority"],
            }


def _iter_verified_command_candidates():
    for lookup_name, spec in SAFE_COMMAND_EXECUTABLES.items():
        for command in spec["commands"]:
            resolved = shutil.which(command)

            if not resolved:
                continue

            path = Path(resolved)

            if path.suffix.lower() not in SAFE_PROGRAM_EXTENSIONS:
                continue

            yield {
                "name": spec["display_name"],
                "path": path,
                "kind": "executable",
                "source": f"verified command: {command}",
                "priority": 25,
                "lookup_name": lookup_name,
            }


def _iter_registry_app_path_candidates():
    if not winreg:
        return

    registry_roots = [
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
    ]

    access_modes = [winreg.KEY_READ]

    if hasattr(winreg, "KEY_WOW64_64KEY"):
        access_modes.append(winreg.KEY_READ | winreg.KEY_WOW64_64KEY)

    if hasattr(winreg, "KEY_WOW64_32KEY"):
        access_modes.append(winreg.KEY_READ | winreg.KEY_WOW64_32KEY)

    seen = set()

    for root_key, subkey in registry_roots:
        for access in access_modes:
            try:
                with winreg.OpenKey(root_key, subkey, 0, access) as app_paths_key:
                    index = 0

                    while True:
                        try:
                            app_key_name = winreg.EnumKey(app_paths_key, index)
                        except OSError:
                            break

                        index += 1

                        try:
                            with winreg.OpenKey(app_paths_key, app_key_name, 0, access) as app_key:
                                raw_path, _ = winreg.QueryValueEx(app_key, "")
                        except Exception:
                            continue

                        path = Path(str(raw_path).strip('"'))

                        if not path.exists() or path.suffix.lower() not in SAFE_PROGRAM_EXTENSIONS:
                            continue

                        if not _is_safe_launcher_name(path.stem):
                            continue

                        key = str(path).lower()

                        if key in seen:
                            continue

                        seen.add(key)

                        yield {
                            "name": path.stem,
                            "path": path,
                            "kind": "executable",
                            "source": "Windows App Paths",
                            "priority": 18,
                        }

            except Exception:
                continue


def _iter_shortcut_candidates():
    for root in _shortcut_search_roots():
        for path in _safe_rglob(root["path"]):
            if path.suffix.lower() not in SHORTCUT_EXTENSIONS:
                continue

            if not _is_safe_launcher_name(path.stem):
                continue

            yield {
                "name": path.stem,
                "path": path,
                "kind": "shortcut",
                "source": root["label"],
                "priority": root["priority"],
            }


def _iter_program_files_candidates(app_name):
    for root in _program_files_roots():
        for app_dir in _safe_iterdir(root):
            if not app_dir.is_dir():
                continue

            dir_score = _app_match_score(app_name, app_dir.name)
            dir_possible_score = _possible_match_score(app_name, app_dir.name)

            if max(dir_score, dir_possible_score) < 45:
                continue

            exe_paths = []

            for child in _safe_iterdir(app_dir):
                if child.is_file() and child.suffix.lower() in SAFE_PROGRAM_EXTENSIONS:
                    exe_paths.append(child)
                    continue

                if child.is_dir():
                    for nested in _safe_iterdir(child):
                        if nested.is_file() and nested.suffix.lower() in SAFE_PROGRAM_EXTENSIONS:
                            exe_paths.append(nested)

            for exe_path in exe_paths[:30]:
                if not _is_safe_launcher_name(exe_path.stem):
                    continue

                exe_score = _app_match_score(app_name, exe_path.stem)
                exe_possible_score = _possible_match_score(app_name, exe_path.stem)
                score = max(exe_score, dir_score - 5)
                possible_score = max(exe_possible_score, dir_possible_score - 5)

                if max(score, possible_score) < 45:
                    continue

                yield {
                    "name": exe_path.stem,
                    "path": exe_path,
                    "kind": "executable",
                    "source": str(root),
                    "priority": 70,
                    "score": score,
                    "possible_score": possible_score,
                }


def _format_candidate_match(candidate):
    return {
        "name": candidate.get("name"),
        "path": str(candidate.get("path")),
        "source": candidate.get("source"),
        "score": candidate.get("score", 0),
        "possible_score": candidate.get("possible_score", 0),
    }


def _score_candidate(app_name, candidate):
    score = candidate.get("score")

    if score is None:
        score = _app_match_score(app_name, candidate.get("name", ""))

    possible_score = candidate.get("possible_score")

    if possible_score is None:
        possible_score = _possible_match_score(app_name, candidate.get("name", ""))

    candidate["score"] = int(score or 0)
    candidate["possible_score"] = int(possible_score or 0)
    candidate["sort_score"] = max(candidate["score"], candidate["possible_score"])

    return candidate


def _find_installed_app(app_name):
    attempted_locations = []
    candidates = []

    for root in _shortcut_search_roots():
        attempted_locations.append(root["label"])

    attempted_locations.append("Windows App Paths")
    attempted_locations.append("known app paths")
    attempted_locations.append("verified system commands")

    attempted_locations.extend(
        str(root)
        for root in _program_files_roots()
    )

    for candidate_source in [
        _iter_known_path_candidates(),
        _iter_shortcut_candidates(),
        _iter_registry_app_path_candidates(),
        _iter_verified_command_candidates(),
        _iter_program_files_candidates(app_name),
    ]:
        if not candidate_source:
            continue

        for candidate in candidate_source:
            scored_candidate = _score_candidate(app_name, candidate)

            if scored_candidate["sort_score"] < 45:
                continue

            candidates.append(scored_candidate)

    candidates.sort(
        key=lambda item: (
            -int(item.get("score", 0)),
            -int(item.get("possible_score", 0)),
            int(item.get("priority", 99)),
            len(str(item.get("name", ""))),
        )
    )

    top_matches = [
        _format_candidate_match(candidate)
        for candidate in candidates[:5]
    ]

    confident_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("score", 0) >= 78
    ]

    if confident_candidates:
        return confident_candidates[0], attempted_locations, top_matches

    if not candidates:
        return None, attempted_locations, []

    return None, attempted_locations, top_matches


def _open_discovered_app(candidate):
    path = candidate.get("path")

    if not path:
        raise ValueError("Discovered app has no path.")

    path = Path(path)

    if path.suffix.lower() in SHORTCUT_EXTENSIONS:
        os.startfile(str(path))
        return {
            "launch_method": "shortcut",
            "resolved_path": str(path),
        }

    if path.suffix.lower() in SAFE_PROGRAM_EXTENSIONS:
        subprocess.Popen([str(path)], shell=False)
        return {
            "launch_method": "executable",
            "resolved_path": str(path),
        }

    raise ValueError(f"Unsupported app launcher type: {path.suffix}")


def _attempted_locations_message(attempted_locations):
    if not attempted_locations:
        return "known aliases and safe Windows app locations"

    unique_locations = []

    for location in attempted_locations:
        if location and location not in unique_locations:
            unique_locations.append(location)

    return ", ".join(unique_locations)


def _open_url(url):
    opened = webbrowser.open(url)

    if not opened:
        raise RuntimeError("The default browser did not accept the open request.")

    return {
        "launch_method": "webbrowser",
        "resolved_path": url,
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


def open_application(app_name, progress_callback=None):
    """
    Open an application or known website by name.
    Uses aliases so speech mistakes like 'note pad' still open Notepad.
    """

    if not app_name or not app_name.strip():
        return {
            "success": False,
            "message": "No application name was provided.",
        }

    progress = ToolProgress(progress_callback, tool_name="open_application")
    clean_name = " ".join(app_name.lower().strip().split())
    launch_context = "app"
    attempted_launch = {}

    try:
        if clean_name in WEBSITE_ALIASES:
            launch_context = "website"
            url = WEBSITE_ALIASES[clean_name]
            launch = _open_url(url)

            display_name = APP_DISPLAY_NAMES.get(clean_name, clean_name.title())

            return {
                "success": True,
                "message": f"Opening {display_name}.",
                "launch_method": "website_alias",
                "resolved_path": launch["resolved_path"],
            }

        if clean_name in APP_ALIASES:
            clean_name = APP_ALIASES[clean_name]

        if "." in clean_name:
            launch_context = "website"
            url = clean_name

            if not url.startswith("http"):
                url = "https://" + url

            launch = _open_url(url)

            return {
                "success": True,
                "message": f"Opening {app_name}.",
                "launch_method": "website_url",
                "resolved_path": launch["resolved_path"],
            }

        progress.emit("I'll check your installed apps.")
        discovered_app, attempted_locations, top_matches = _find_installed_app(clean_name)

        if discovered_app:
            launch_context = "app"
            display_name = discovered_app.get("name") or app_name

            progress.emit(f"I found {display_name}.")
            attempted_launch = {
                "resolved_path": str(discovered_app.get("path")),
                "launch_method": discovered_app.get("kind"),
                "match_score": discovered_app.get("score"),
                "match_source": discovered_app.get("source"),
            }
            launch = _open_discovered_app(discovered_app)

            return {
                "success": True,
                "message": f"Opening {display_name}.",
                "source": "app_discovery",
                "launch_method": launch["launch_method"],
                "resolved_path": launch["resolved_path"],
                "match_score": discovered_app.get("score"),
                "match_source": discovered_app.get("source"),
                "top_matches": top_matches,
            }

        if top_matches:
            best_match = top_matches[0]

            return {
                "success": False,
                "message": f"I found a possible match: {best_match.get('name')}. Should I open that?",
                "needs_confirmation": True,
                "suggested_app": best_match.get("name"),
                "suggested_path": best_match.get("path"),
                "top_matches": top_matches,
                "attempted_locations": attempted_locations,
            }

        return {
            "success": False,
            "message": f"I couldn't find {app_name} installed.",
            "attempted_locations": attempted_locations,
            "top_matches": top_matches,
        }

    except Exception as error:
        if launch_context == "website":
            return {
                "success": False,
                "message": f"I couldn't open {app_name}.",
                "error": str(error),
            }

        return {
            "success": False,
            "message": f"I found {app_name}, but it did not open.",
            "error": str(error),
            **attempted_launch,
        }


def search_web(query):
    """
    Open a web search in the default browser.
    """
    query = clean_search_query(query)

    if not query:
        return {
            "success": False,
            "message": "No search query was provided.",
        }

    encoded_query = quote_plus(query)
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


def clean_search_query(query):
    """
    Removes obvious spoken search command scaffolding from a query.
    This stays generic and does not encode product/site-specific behavior.
    """

    query = " ".join(str(query or "").strip().split())
    clean = query.lower()

    prefixes = [
        "open up an image of ",
        "open up a picture of ",
        "open up a photo of ",
        "open up images of ",
        "open up pictures of ",
        "open up photos of ",
        "open an image of ",
        "open a picture of ",
        "open a photo of ",
        "open images of ",
        "open pictures of ",
        "open photos of ",
        "show me an image of ",
        "show me a picture of ",
        "show me a photo of ",
        "show me images of ",
        "show me pictures of ",
        "show me photos of ",
        "pull up an image of ",
        "pull up a picture of ",
        "pull up a photo of ",
        "pull up images of ",
        "pull up pictures of ",
        "pull up photos of ",
        "pull up results for ",
        "show me results for ",
        "open a search for ",
        "open search for ",
        "search google for ",
        "google search for ",
        "search for ",
        "search up ",
        "google for ",
        "google search ",
        "look up ",
        "pull up ",
        "show me ",
        "search ",
        "google ",
    ]

    for prefix in sorted(prefixes, key=len, reverse=True):
        if clean.startswith(prefix):
            query = query[len(prefix):].strip()
            clean = query.lower()

            if any(word in prefix for word in ["image", "photo", "picture"]):
                query = f"{query} images".strip()
                clean = query.lower()

            break

    for connector in ["for ", "up ", "about "]:
        while clean.startswith(connector):
            query = query[len(connector):].strip()
            clean = query.lower()

    if clean.startswith("the best "):
        query = "best " + query[9:].strip()

    return " ".join(query.split())


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
