import argparse
import json
import mimetypes
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from ui_state import (
    close_all_widgets,
    close_widget,
    read_chat_history,
    read_ui_state,
)


# =========================
# JARVIS WEB HUD SERVER
# Local display layer only. The AI/voice/tool backend stays local Python.
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "web_hud"
DATA_DIR = BASE_DIR / "data"
TODO_PATH = DATA_DIR / "todo.json"
CAPABILITY_GAPS_PATH = DATA_DIR / "capability_gaps.json"
SERVER_STATE_PATH = DATA_DIR / "web_hud_server.json"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

try:
    import psutil
except Exception:
    psutil = None


def _safe_read_json(path, fallback):
    try:
        if not path.exists():
            return fallback

        with open(path, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return fallback


def _load_todo():
    payload = _safe_read_json(TODO_PATH, {"tasks": []})

    if isinstance(payload, dict):
        tasks = payload.get("tasks", [])
    else:
        tasks = payload

    if not isinstance(tasks, list):
        tasks = []

    return {
        "tasks": [
            task for task in tasks
            if isinstance(task, dict) and str(task.get("text", "")).strip()
        ]
    }


def _load_capability_gaps(limit=8):
    gaps = _safe_read_json(CAPABILITY_GAPS_PATH, [])

    if isinstance(gaps, dict):
        gaps = gaps.get("gaps", [])

    if not isinstance(gaps, list):
        gaps = []

    gaps = [
        gap for gap in gaps
        if isinstance(gap, dict)
    ]

    return list(reversed(gaps[-limit:]))


def _get_system_stats():
    if not psutil:
        return {
            "available": False,
        }

    try:
        battery = psutil.sensors_battery()

        return {
            "available": True,
            "cpu_percent": psutil.cpu_percent(interval=None),
            "ram_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage(str(BASE_DIR.anchor or "C:\\")).percent,
            "battery_percent": battery.percent if battery else None,
            "battery_plugged_in": battery.power_plugged if battery else None,
        }
    except Exception:
        return {
            "available": False,
        }


def _build_state_payload():
    state = read_ui_state()
    chat_history = read_chat_history(limit=30)

    state["chat_messages"] = chat_history[-10:]

    return {
        "success": True,
        "state": state,
        "chat_history": chat_history,
        "todo": _load_todo(),
        "system": _get_system_stats(),
        "capability_gaps": _load_capability_gaps(),
        "served_at": time.time(),
    }


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _write_server_state(host, port):
    DATA_DIR.mkdir(exist_ok=True)

    payload = {
        "url": f"http://{host}:{port}/",
        "host": host,
        "port": port,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }

    with open(SERVER_STATE_PATH, "w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)


def _is_port_available(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _find_port(host, preferred_port):
    preferred_port = int(preferred_port)

    for port in range(preferred_port, preferred_port + 20):
        if _is_port_available(host, port):
            return port

    raise RuntimeError("No available local port found for the Jarvis web HUD.")


def _chrome_paths():
    return [
        shutil.which("chrome"),
        shutil.which("chrome.exe"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        str(Path.home() / "AppData" / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"),
    ]


def _open_browser(url):
    for candidate in _chrome_paths():
        if not candidate:
            continue

        path = Path(candidate)

        if path.exists():
            try:
                subprocess.Popen(
                    [str(path), "--new-window", url],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                return
            except Exception:
                pass

    webbrowser.open(url)


class WebHudRequestHandler(BaseHTTPRequestHandler):
    server_version = "JarvisWebHud/1.0"

    def log_message(self, format, *args):
        print(f"[WEB HUD] {self.address_string()} - {format % args}")

    def _send_bytes(self, data, content_type="application/octet-stream", status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(data)

    def _send_json(self, payload, status=HTTPStatus.OK):
        self._send_bytes(
            _json_bytes(payload),
            content_type="application/json; charset=utf-8",
            status=status,
        )

    def _send_not_found(self):
        self._send_json(
            {
                "success": False,
                "message": "Not found.",
            },
            status=HTTPStatus.NOT_FOUND,
        )

    def _static_path_for(self, raw_path):
        parsed_path = unquote(urlparse(raw_path).path)

        if parsed_path == "/":
            parsed_path = "/index.html"

        relative = parsed_path.lstrip("/")
        candidate = (STATIC_DIR / relative).resolve()
        static_root = STATIC_DIR.resolve()

        try:
            candidate.relative_to(static_root)
        except ValueError:
            return None

        if not candidate.exists() or not candidate.is_file():
            return None

        return candidate

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/state":
            self._send_json(_build_state_payload())
            return

        if parsed.path == "/api/system":
            self._send_json(
                {
                    "success": True,
                    "system": _get_system_stats(),
                }
            )
            return

        if parsed.path == "/api/capability-gaps":
            query = parse_qs(parsed.query)
            limit = int(query.get("limit", ["8"])[0] or 8)
            self._send_json(
                {
                    "success": True,
                    "capability_gaps": _load_capability_gaps(limit=limit),
                }
            )
            return

        static_path = self._static_path_for(self.path)

        if not static_path:
            self._send_not_found()
            return

        content_type = mimetypes.guess_type(str(static_path))[0] or "application/octet-stream"
        self._send_bytes(static_path.read_bytes(), content_type=content_type)

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/widgets/close-all":
            close_all_widgets()
            self._send_json(
                {
                    "success": True,
                    "message": "Closed all widgets.",
                }
            )
            return

        if parsed.path.startswith("/api/widgets/") and parsed.path.endswith("/close"):
            widget_id = parsed.path[len("/api/widgets/") : -len("/close")]
            widget_id = unquote(widget_id).strip()

            if not widget_id:
                self._send_json(
                    {
                        "success": False,
                        "message": "Missing widget id.",
                    },
                    status=HTTPStatus.BAD_REQUEST,
                )
                return

            close_widget(widget_id)
            self._send_json(
                {
                    "success": True,
                    "message": "Closed widget.",
                    "widget_id": widget_id,
                }
            )
            return

        self._send_not_found()


def run_server(host=DEFAULT_HOST, port=DEFAULT_PORT, open_browser=False):
    port = _find_port(host, port)
    url = f"http://{host}:{port}/"
    _write_server_state(host, port)

    server = ThreadingHTTPServer((host, port), WebHudRequestHandler)

    if open_browser:
        threading.Timer(0.8, _open_browser, args=[url]).start()

    print(f"Jarvis web HUD running at {url}")
    print("Press Ctrl+C to stop the web HUD server.")
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description="Run the local Jarvis web HUD.")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--open", action="store_true", help="Open the HUD in Chrome/default browser.")
    args = parser.parse_args()

    run_server(
        host=args.host,
        port=args.port,
        open_browser=args.open,
    )


if __name__ == "__main__":
    main()
