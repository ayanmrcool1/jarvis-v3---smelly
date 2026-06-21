import json
from pathlib import Path
from datetime import datetime


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UI_STATE_PATH = DATA_DIR / "ui_state.json"


DEFAULT_UI_STATE = {
    "status": "STANDBY",
    "sub_status": "Awaiting wake phrase",
    "detail": "",
    "updated_at": "",
}


def write_ui_state(status, sub_status="", detail=""):
    """
    Writes the current Jarvis UI state to a JSON file.
    """

    payload = {
        "status": status,
        "sub_status": sub_status,
        "detail": detail,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    with open(UI_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)


def read_ui_state():
    """
    Reads the current Jarvis UI state.
    """

    if not UI_STATE_PATH.exists():
        return DEFAULT_UI_STATE

    try:
        with open(UI_STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return DEFAULT_UI_STATE