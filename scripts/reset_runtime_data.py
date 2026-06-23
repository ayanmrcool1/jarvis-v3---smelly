from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]

RUNTIME_TARGETS = [
    "data/memory.json",
    "data/chat_history.json",
    "data/ui_state.json",
    "data/todo.json",
    "data/routines.json",
    "data/capability_gaps.json",
    "data/web_hud_server.json",
    "data/user_profiles",
    "data/tts_cache",
    "recordings",
    "screenshots",
    "logs",
]


def safe_target(relative_path: str) -> Path:
    target = (ROOT_DIR / relative_path).resolve()
    root = ROOT_DIR.resolve()

    try:
        target.relative_to(root)
    except ValueError as error:
        raise RuntimeError(f"Unsafe reset target: {target}") from error

    return target


def remove_target(path: Path) -> str:
    if not path.exists():
        return "missing"

    if path.is_dir():
        shutil.rmtree(path)
        return "deleted directory"

    path.unlink()
    return "deleted file"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Remove local JARVIS memories, profiles, logs, screenshots, recordings, and caches."
    )
    parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
    args = parser.parse_args()

    print("JARVIS runtime data reset")
    print("=" * 25)
    print("This removes local memories, user profiles, chat history, logs, screenshots, recordings, and caches.")
    print("It does not remove app code, .env, requirements, or the virtual environment.")
    print("")

    if not args.yes:
        answer = input("Continue? Type YES to reset local runtime data: ").strip()

        if answer != "YES":
            print("Cancelled.")
            return 1

    for relative_path in RUNTIME_TARGETS:
        target = safe_target(relative_path)
        status = remove_target(target)
        print(f"{relative_path}: {status}")

    (ROOT_DIR / "data").mkdir(exist_ok=True)
    print("")
    print("Runtime data reset complete. Fresh data files will be recreated when JARVIS starts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
