from tools.system_tools import open_application


# =========================
# JARVIS APP SKILL
# =========================

OPEN_PHRASES = [
    "open ",
    "launch ",
    "start ",
    "bring up ",
    "pull up ",
]


def extract_app_name(clean_text):
    """
    Extracts the app name from an open/launch command.
    Example:
    'open notepad' -> 'notepad'
    'bring up chrome' -> 'chrome'
    """

    for phrase in OPEN_PHRASES:
        if clean_text.startswith(phrase):
            return clean_text.replace(phrase, "", 1).strip()

    return ""


def handle_app_command(transcription, clean_text):
    """
    Handles app-opening commands.

    Local shortcut tries first.
    If local fails, router can send it to AI with forced open_application.
    """

    is_open_command = any(
        clean_text.startswith(phrase)
        for phrase in OPEN_PHRASES
    )

    if not is_open_command:
        return None

    app_name = extract_app_name(clean_text)

    if not app_name:
        return {
            "handled": True,
            "response": "What app do you want me to open?",
            "source": "app_skill",
        }

    result = open_application(app_name)

    if result.get("success"):
        return {
            "handled": True,
            "response": result.get("message", f"Opening {app_name}."),
            "source": "app_skill",
        }

    # Local shortcut failed, so AI should clean the messy app name and force the tool call.
    return {
        "handled": False,
        "needs_ai": True,
        "forced_tool_name": "open_application",
        "response": result.get("message", f"I could not open {app_name} locally."),
        "source": "app_skill",
    }