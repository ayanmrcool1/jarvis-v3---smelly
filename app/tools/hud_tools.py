from ui_state import (
    open_widget,
    close_widget,
    close_all_widgets,
    read_chat_history,
)


WIDGET_CONFIG = {
    "todo": {
        "widget_id": "todo_widget",
        "title": "TO-DO LIST",
        "content": {},
    },
    "chat": {
        "widget_id": "chat_widget",
        "title": "CONVERSATION",
        "content": {"messages": []},
    },
    "system": {
        "widget_id": "system_widget",
        "title": "SYSTEM STATUS",
        "content": {},
    },
    "spotify": {
        "widget_id": "spotify_widget",
        "title": "NOW PLAYING",
        "content": {},
    },
}


ACTION_ALIASES = {
    "show": "open",
    "hide": "close",
    "dismiss": "close",
    "remove": "close",
    "clear": "close_all",
}


def _normalise_action(action):
    clean = str(action or "").strip().lower()
    return ACTION_ALIASES.get(clean, clean)


def _normalise_widget_type(widget_type):
    clean = str(widget_type or "").strip().lower()

    if clean.endswith("_widget"):
        clean = clean[:-7]

    return clean


def _widget_content(widget_type):
    if widget_type == "chat":
        return {
            "messages": read_chat_history(limit=10),
        }

    return dict(WIDGET_CONFIG.get(widget_type, {}).get("content", {}))


def control_hud_widget(action, widget_type=None):
    """
    Opens and closes HUD widgets through ui_state.json so the live HUD can react
    through its existing polling loop.
    """

    action = _normalise_action(action)
    widget_type = _normalise_widget_type(widget_type)

    if action == "close_all":
        close_all_widgets()
        return {
            "success": True,
            "message": "Closed the HUD widgets.",
            "spoken_message": "Closed the HUD widgets.",
            "action": action,
        }

    if action not in {"open", "close"}:
        return {
            "success": False,
            "message": "I can open, close, or close all HUD widgets.",
            "spoken_message": "I can open, close, or close all HUD widgets.",
            "action": action,
            "widget_type": widget_type,
        }

    if widget_type not in WIDGET_CONFIG:
        return {
            "success": False,
            "message": "I do not have that HUD widget yet.",
            "spoken_message": "I do not have that HUD widget yet.",
            "action": action,
            "widget_type": widget_type,
            "available_widgets": sorted(WIDGET_CONFIG.keys()),
        }

    config = WIDGET_CONFIG[widget_type]
    widget_id = config["widget_id"]
    title = config["title"]

    if action == "open":
        open_widget(
            widget_id=widget_id,
            widget_type=widget_type,
            title=title,
            content=_widget_content(widget_type),
        )
        return {
            "success": True,
            "message": f"Showing {title.lower()}.",
            "spoken_message": f"Showing {title.lower()}.",
            "action": action,
            "widget_type": widget_type,
            "widget_id": widget_id,
        }

    close_widget(widget_id)
    return {
        "success": True,
        "message": f"Closed {title.lower()}.",
        "spoken_message": f"Closed {title.lower()}.",
        "action": action,
        "widget_type": widget_type,
        "widget_id": widget_id,
    }
