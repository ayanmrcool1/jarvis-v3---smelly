from __future__ import annotations

import argparse
import json
import os
import platform
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
ENV_PATH = ROOT_DIR / ".env"
LOG_DIR = ROOT_DIR / "logs"
DATA_DIR = ROOT_DIR / "data"
PROCESS_STATE_PATH = DATA_DIR / "jarvis_processes.json"


def venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"

    return VENV_DIR / "bin" / "python"


def venv_pythonw_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "pythonw.exe"

    return venv_python_path()


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def is_placeholder(value: str | None) -> bool:
    clean = str(value or "").strip()

    if not clean:
        return True

    return clean.lower() in {
        "put_key_here",
        "optional",
        "your_openai_api_key_here",
        "your_elevenlabs_api_key_here",
    }


def read_tail(path: Path, max_lines: int = 35) -> str:
    if not path.exists():
        return ""

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return ""

    return "\n".join(lines[-max_lines:])


def redirect_launcher_output(timestamp: str) -> Path:
    LOG_DIR.mkdir(exist_ok=True)
    log_path = LOG_DIR / f"launcher_{timestamp}.log"
    log_file = log_path.open("w", encoding="utf-8", buffering=1)
    sys.stdout = log_file
    sys.stderr = log_file
    print("JARVIS launcher log")
    print("=" * 18)
    print(f"Project folder: {ROOT_DIR}")
    return log_path


def validate_environment(require_voice: bool) -> bool:
    python_path = venv_python_path()

    if not python_path.exists():
        print("JARVIS is not set up yet.")
        print("Run Setup_Jarvis.bat on Windows or setup_mac.command on macOS first.")
        return False

    if not ENV_PATH.exists():
        print("Missing .env file.")
        print("Run setup again, or copy .env.example to .env and add your API keys.")
        return False

    env_values = parse_env(ENV_PATH)

    if require_voice and is_placeholder(env_values.get("OPENAI_API_KEY")):
        print("OPENAI_API_KEY is missing in .env.")
        print("The HUD can open without it, but the voice brain cannot start.")
        print("Run setup again or edit .env and add your OpenAI API key.")
        return False

    tts_provider = env_values.get("TTS_PROVIDER", "edge").strip().lower() or "edge"

    if require_voice and tts_provider in {"elevenlabs", "eleven_labs", "11labs"}:
        if is_placeholder(env_values.get("ELEVENLABS_API_KEY")):
            print("Warning: TTS_PROVIDER is elevenlabs but ELEVENLABS_API_KEY is missing.")
            print("JARVIS should fall back to Edge TTS if ElevenLabs cannot be used.")

    return True


def command_for_log(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def write_process_state(mode: str, processes: list[dict[str, object]]) -> None:
    DATA_DIR.mkdir(exist_ok=True)

    payload = {
        "mode": mode,
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "project_dir": str(ROOT_DIR),
        "processes": [
            {
                "label": str(entry["label"]),
                "pid": int(getattr(entry["process"], "pid")),
                "log_path": str(entry["log_path"]),
                "command": list(entry.get("command", [])),
            }
            for entry in processes
        ],
    }

    PROCESS_STATE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def print_platform_notes() -> None:
    system = platform.system()

    if system == "Windows":
        print("Platform: Windows.")
        return

    if system == "Darwin":
        print("Platform: macOS partial support.")
        print("Global hotkey, Windows app discovery, and Windows volume control are not available on macOS.")
        print("Screen control may need macOS Accessibility and Screen Recording permissions.")
        return

    print(f"Platform: {system or 'unknown'} is not officially supported.")


def tee_output(label: str, stream, log_file) -> None:
    try:
        for line in stream:
            text = line.rstrip("\n")
            print(f"[{label}] {text}", flush=True)
            log_file.write(line)
            log_file.flush()
    finally:
        try:
            stream.close()
        except Exception:
            pass


def start_process(
    label: str,
    command: list[str],
    log_path: Path,
    *,
    detached: bool = False,
    live_output: bool = False,
) -> tuple[subprocess.Popen, object, threading.Thread | None]:
    log_file = log_path.open("w", encoding="utf-8", buffering=1)
    log_file.write(f"JARVIS {label} log\n")
    log_file.write(f"Command: {command_for_log(command)}\n")
    log_file.write("=" * 60 + "\n")
    log_file.flush()

    creationflags = 0
    start_new_session = False

    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP

        if detached:
            if hasattr(subprocess, "CREATE_NO_WINDOW"):
                creationflags |= subprocess.CREATE_NO_WINDOW
    elif detached:
        start_new_session = True

    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"

    if live_output:
        process = subprocess.Popen(
            command,
            cwd=ROOT_DIR,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            creationflags=creationflags,
            start_new_session=start_new_session,
        )

        assert process.stdout is not None
        output_thread = threading.Thread(
            target=tee_output,
            args=(label, process.stdout, log_file),
            daemon=True,
        )
        output_thread.start()

        print(f"Started {label} (pid {process.pid})")
        print(f"  log: {log_path}")
        return process, log_file, output_thread

    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        text=True,
        env=env,
        creationflags=creationflags,
        start_new_session=start_new_session,
    )

    print(f"Started {label} (pid {process.pid})")
    print(f"  log: {log_path}")
    return process, log_file, None


def terminate_process(process: subprocess.Popen, label: str) -> None:
    if process.poll() is not None:
        return

    print(f"Stopping {label}...")

    try:
        if os.name == "nt":
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    except Exception:
        try:
            process.terminate()
        except Exception:
            pass

    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch JARVIS HUD and voice core.")
    parser.add_argument("--hud", choices=["web", "desktop", "none"], default="web")
    parser.add_argument("--hud-only", action="store_true", help="Start only the selected HUD.")
    parser.add_argument("--voice-only", action="store_true", help="Start only the voice core.")
    parser.add_argument("--no-open", action="store_true", help="Do not open the web HUD in a browser.")
    parser.add_argument("--port", type=int, default=8765, help="Preferred web HUD port.")
    parser.add_argument("--detached", action="store_true", help="Launch in the background and exit.")
    parser.add_argument("--debug", action="store_true", help="Stream child process output live to this console.")
    args = parser.parse_args()

    LOG_DIR.mkdir(exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    python_path = venv_pythonw_path() if args.detached and os.name == "nt" else venv_python_path()
    live_output = bool(args.debug)

    if args.detached:
        redirect_launcher_output(timestamp)

    launch_hud = args.hud != "none" and not args.voice_only
    launch_voice = not args.hud_only

    if args.hud_only:
        launch_voice = False

    if args.voice_only:
        launch_hud = False

    if not launch_hud and not launch_voice:
        print("Nothing to launch. Choose a HUD or voice core.")
        return 2

    print("JARVIS launcher")
    print("=" * 15)
    print(f"Project folder: {ROOT_DIR}")
    print_platform_notes()

    if not validate_environment(require_voice=launch_voice):
        return 2

    processes: list[dict[str, object]] = []

    try:
        if launch_hud and args.hud == "web":
            command = [
                str(python_path),
                "-u",
                str(ROOT_DIR / "app" / "web_hud_server.py"),
                "--port",
                str(args.port),
            ]

            if not args.no_open:
                command.append("--open")

            log_path = LOG_DIR / f"web_hud_{timestamp}.log"
            process, log_file, output_thread = start_process(
                "web HUD",
                command,
                log_path,
                detached=args.detached,
                live_output=live_output,
            )
            processes.append(
                {
                    "label": "web HUD",
                    "process": process,
                    "log_file": log_file,
                    "log_path": log_path,
                    "command": command,
                    "output_thread": output_thread,
                    "reported_exit": False,
                }
            )

        if launch_hud and args.hud == "desktop":
            command = [
                str(python_path),
                "-u",
                str(ROOT_DIR / "app" / "jarvis_ui.py"),
            ]
            log_path = LOG_DIR / f"desktop_hud_{timestamp}.log"
            process, log_file, output_thread = start_process(
                "desktop HUD",
                command,
                log_path,
                detached=args.detached,
                live_output=live_output,
            )
            processes.append(
                {
                    "label": "desktop HUD",
                    "process": process,
                    "log_file": log_file,
                    "log_path": log_path,
                    "command": command,
                    "output_thread": output_thread,
                    "reported_exit": False,
                }
            )

        if launch_voice:
            command = [
                str(python_path),
                "-u",
                str(ROOT_DIR / "app" / "phase1_audio_loop.py"),
            ]
            log_path = LOG_DIR / f"voice_core_{timestamp}.log"
            process, log_file, output_thread = start_process(
                "voice core",
                command,
                log_path,
                detached=args.detached,
                live_output=live_output,
            )
            processes.append(
                {
                    "label": "voice core",
                    "process": process,
                    "log_file": log_file,
                    "log_path": log_path,
                    "command": command,
                    "output_thread": output_thread,
                    "reported_exit": False,
                }
            )

        write_process_state("detached" if args.detached else "debug" if args.debug else "supervised", processes)

        if args.detached:
            print("")
            print("JARVIS launched in the background.")
            print(f"Process state: {PROCESS_STATE_PATH}")

            for entry in processes:
                try:
                    entry["log_file"].close()
                except Exception:
                    pass

            return 0

        print("")

        if args.debug:
            print("JARVIS debug mode is live. Child process output is shown below and also written to logs.")
            print("Press Ctrl+C here to stop this debug session.")
        else:
            print("JARVIS is launching. Keep this window open to supervise it.")
            print("Press Ctrl+C here to stop all launched JARVIS processes.")

        while processes:
            all_exited = True

            for entry in processes:
                process = entry["process"]
                assert isinstance(process, subprocess.Popen)
                return_code = process.poll()

                if return_code is None:
                    all_exited = False
                    continue

                if entry.get("reported_exit"):
                    continue

                entry["reported_exit"] = True
                label = str(entry["label"])
                log_path = Path(entry["log_path"])
                print("")
                print(f"{label} exited with code {return_code}.")

                tail = read_tail(log_path)
                if tail:
                    print(f"Last lines from {log_path}:")
                    print(tail)

            if all_exited:
                break

            time.sleep(1)

        for entry in processes:
            output_thread = entry.get("output_thread")
            if output_thread:
                output_thread.join(timeout=1)

            log_file = entry["log_file"]
            try:
                log_file.close()
            except Exception:
                pass

        return 0

    except KeyboardInterrupt:
        print("")
        print("Shutdown requested.")

        for entry in processes:
            process = entry["process"]
            assert isinstance(process, subprocess.Popen)
            terminate_process(process, str(entry["label"]))

        for entry in processes:
            output_thread = entry.get("output_thread")
            if output_thread:
                output_thread.join(timeout=1)

            log_file = entry["log_file"]
            try:
                log_file.close()
            except Exception:
                pass

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
