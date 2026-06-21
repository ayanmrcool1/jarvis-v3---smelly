import json
from pathlib import Path
from datetime import datetime
from uuid import uuid4


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

UI_STATE_PATH = DATA_DIR / "ui_state.json"
CHAT_HISTORY_PATH = DATA_DIR / "chat_history.json"


DEFAULT_UI_STATE = {
    "status": "STANDBY",
    "sub_status": "Awaiting wake phrase",
    "detail": "",
    "active_widgets": [],
    "orb_position": "center",
    "chat_messages": [],
    "updated_at": "",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _normalise_state(state):
    payload = dict(DEFAULT_UI_STATE)

    if isinstance(state, dict):
        payload.update(state)

    if not isinstance(payload.get("active_widgets"), list):
        payload["active_widgets"] = []

    if payload.get("orb_position") not in {"center", "corner"}:
        payload["orb_position"] = "corner" if payload["active_widgets"] else "center"

    if not isinstance(payload.get("chat_messages"), list):
        payload["chat_messages"] = []

    return payload


def _write_state(state):
    payload = _normalise_state(state)
    payload["updated_at"] = _now()

    with open(UI_STATE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    return payload


def write_ui_state(status, sub_status="", detail=""):
    """
    Writes the current Jarvis UI state to a JSON file while preserving
    HUD widget state. The voice loop calls this frequently, so widget fields
    must not be reset during normal status updates.
    """

    payload = read_ui_state()
    payload.update(
        {
            "status": status,
            "sub_status": sub_status,
            "detail": detail,
        }
    )

    _write_state(payload)


def read_ui_state():
    """
    Reads the current Jarvis UI state.
    """

    if not UI_STATE_PATH.exists():
        return DEFAULT_UI_STATE

    try:
        with open(UI_STATE_PATH, "r", encoding="utf-8") as f:
            return _normalise_state(json.load(f))
    except Exception:
        return DEFAULT_UI_STATE


def _widget_id_for(widget_type):
    clean_type = str(widget_type or "").strip().lower()

    if clean_type.endswith("_widget"):
        return clean_type

    return f"{clean_type}_widget"


def open_widget(widget_id, widget_type, title, content=None, position=None):
    """
    Opens or updates a HUD widget entry.
    """

    state = read_ui_state()
    widget_id = str(widget_id or _widget_id_for(widget_type)).strip()
    widget_type = str(widget_type or "").strip().lower()
    position = position or "auto"

    if content is None:
        content = {}

    widget = {
        "widget_id": widget_id,
        "widget_type": widget_type,
        "title": str(title or widget_type).strip(),
        "content": content,
        "position": position,
    }

    widgets = []
    replaced = False

    for existing in state.get("active_widgets", []):
        if existing.get("widget_id") == widget_id:
            widgets.append(widget)
            replaced = True
        else:
            widgets.append(existing)

    if not replaced:
        widgets.append(widget)

    state["active_widgets"] = widgets
    state["orb_position"] = "corner" if widgets else "center"

    return _write_state(state)


def close_widget(widget_id):
    """
    Closes one HUD widget by id.
    """

    state = read_ui_state()
    widget_id = str(widget_id or "").strip()

    widgets = [
        widget
        for widget in state.get("active_widgets", [])
        if widget.get("widget_id") != widget_id
    ]

    state["active_widgets"] = widgets
    state["orb_position"] = "corner" if widgets else "center"

    return _write_state(state)


def close_all_widgets():
    """
    Closes all HUD widgets and returns the orb to center.
    """

    state = read_ui_state()
    state["active_widgets"] = []
    state["orb_position"] = "center"

    return _write_state(state)


def update_widget_content(widget_id, content):
    """
    Replaces the content field for an open HUD widget.
    """

    state = read_ui_state()
    widget_id = str(widget_id or "").strip()

    for widget in state.get("active_widgets", []):
        if widget.get("widget_id") == widget_id:
            widget["content"] = content
            break

    return _write_state(state)


def read_chat_history(limit=10):
    if not CHAT_HISTORY_PATH.exists():
        return []

    try:
        with open(CHAT_HISTORY_PATH, "r", encoding="utf-8") as f:
            messages = json.load(f)
    except Exception:
        return []

    if not isinstance(messages, list):
        return []

    try:
        limit = int(limit)
    except Exception:
        limit = 10

    return messages[-max(1, limit):]


def append_chat_message(role, text):
    """
    Stores a short rolling conversation history for the HUD chat widget.
    """

    text = str(text or "").strip()

    if not text:
        return read_chat_history()

    messages = read_chat_history(limit=30)
    messages.append(
        {
            "id": uuid4().hex,
            "role": str(role or "jarvis").strip().lower(),
            "text": text,
            "timestamp": _now(),
        }
    )
    messages = messages[-30:]

    with open(CHAT_HISTORY_PATH, "w", encoding="utf-8") as f:
        json.dump(messages, f, indent=2)

    state = read_ui_state()
    state["chat_messages"] = messages[-10:]

    for widget in state.get("active_widgets", []):
        if widget.get("widget_type") == "chat":
            widget["content"] = {
                "messages": messages[-10:],
            }

    _write_state(state)

    return messages[-10:]
