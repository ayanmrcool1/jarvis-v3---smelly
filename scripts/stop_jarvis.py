from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
PROCESS_STATE_PATH = DATA_DIR / "jarvis_processes.json"
ENTRYPOINTS = {
    "web_hud_server.py",
    "jarvis_ui.py",
    "phase1_audio_loop.py",
}


try:
    import psutil
except Exception:
    psutil = None


def load_state() -> dict:
    if not PROCESS_STATE_PATH.exists():
        return {}

    try:
        return json.loads(PROCESS_STATE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def command_text_from_record(record: dict) -> str:
    command = record.get("command") or []

    if isinstance(command, list):
        return " ".join(str(part) for part in command)

    return str(command or "")


def looks_like_jarvis_cmdline(cmdline: list[str] | tuple[str, ...] | None) -> bool:
    if not cmdline:
        return False

    command_text = " ".join(str(part) for part in cmdline).lower()
    root_text = str(ROOT_DIR).lower()

    return root_text in command_text and any(entrypoint.lower() in command_text for entrypoint in ENTRYPOINTS)


def pid_from_record(record: dict) -> int | None:
    try:
        pid = int(record.get("pid"))
    except Exception:
        return None

    return pid if pid > 0 else None


def process_matches_record(process, record: dict) -> bool:
    try:
        cmdline = process.cmdline()
    except Exception:
        return False

    return looks_like_jarvis_cmdline(cmdline)


def terminate_psutil_process(process, label: str) -> bool:
    try:
        if not process.is_running():
            print(f"{label}: already stopped.")
            return False

        print(f"Stopping {label} (pid {process.pid})...")

        children = []

        try:
            children = process.children(recursive=True)
        except Exception:
            children = []

        for child in children:
            try:
                child.terminate()
            except Exception:
                pass

        process.terminate()
        gone, alive = psutil.wait_procs([process, *children], timeout=5)

        for still_alive in alive:
            try:
                still_alive.kill()
            except Exception:
                pass

        return True

    except psutil.NoSuchProcess:
        print(f"{label}: already stopped.")
        return False
    except Exception as error:
        print(f"{label}: could not stop cleanly: {error}")
        return False


def terminate_pid_fallback(pid: int, label: str) -> bool:
    print(f"Stopping {label} (pid {pid})...")

    try:
        if os.name == "nt":
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                return True

            print((result.stdout or result.stderr or "").strip())
            return False

        os.kill(pid, signal.SIGTERM)
        time.sleep(2)

        try:
            os.kill(pid, 0)
        except OSError:
            return True

        os.kill(pid, signal.SIGKILL)
        return True

    except ProcessLookupError:
        print(f"{label}: already stopped.")
        return False
    except Exception as error:
        print(f"{label}: could not stop: {error}")
        return False


def stop_recorded_processes(state: dict) -> int:
    stopped = 0
    records = state.get("processes", [])

    if not isinstance(records, list):
        return stopped

    seen_pids: set[int] = set()

    for record in records:
        if not isinstance(record, dict):
            continue

        pid = pid_from_record(record)

        if not pid or pid in seen_pids:
            continue

        seen_pids.add(pid)
        label = str(record.get("label") or f"process {pid}")

        if psutil:
            try:
                process = psutil.Process(pid)
            except psutil.NoSuchProcess:
                print(f"{label}: already stopped.")
                continue
            except Exception as error:
                print(f"{label}: could not inspect pid {pid}: {error}")
                continue

            if not process_matches_record(process, record):
                print(f"{label}: pid {pid} no longer looks like JARVIS, skipping.")
                continue

            if terminate_psutil_process(process, label):
                stopped += 1
        elif terminate_pid_fallback(pid, label):
            stopped += 1

    return stopped


def find_orphaned_processes() -> list:
    if not psutil:
        return []

    matches = []

    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            if looks_like_jarvis_cmdline(process.info.get("cmdline")):
                matches.append(process)
        except Exception:
            continue

    return matches


def clear_state_file() -> None:
    try:
        PROCESS_STATE_PATH.unlink(missing_ok=True)
    except Exception:
        pass


def main() -> int:
    print("Stopping JARVIS")
    print("=" * 15)

    state = load_state()
    stopped = stop_recorded_processes(state)

    orphaned = find_orphaned_processes()

    for process in orphaned:
        try:
            label = f"orphaned JARVIS process {process.pid}"
            if terminate_psutil_process(process, label):
                stopped += 1
        except Exception:
            continue

    clear_state_file()

    if stopped:
        print("")
        print("JARVIS stopped.")
        return 0

    print("")
    print("No running JARVIS processes were found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
