from tools.system_tools import APP_ALIASES, WEBSITE_ALIASES, open_application


# =========================
# JARVIS APP SKILL
# =========================

OPEN_PHRASES = [
    "open up ",
    "open ",
    "launch ",
    "start ",
    "bring up ",
    "pull up ",
]

MULTI_STEP_CONNECTORS = [
    " and ",
    " then ",
]

FOLLOW_UP_ACTION_WORDS = [
    "search",
    "find",
    "compare",
    "fill",
    "summarize",
    "summarise",
    "read",
    "look through",
    "check",
    "choose",
    "complete",
    "submit",
    "book",
]

VISIBLE_SEARCH_PREFIXES = [
    "open a search for ",
    "open search for ",
    "open up a search for ",
    "open up search for ",
]

VISIBLE_IMAGE_PHRASES = [
    "an image of ",
    "a picture of ",
    "a photo of ",
    "images of ",
    "pictures of ",
    "photos of ",
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


def looks_like_visible_search_request(clean_text):
    """
    Keeps app opening from stealing explicit visible search/image requests.
    """

    app_name = extract_app_name(clean_text)

    if not app_name:
        return False

    if any(clean_text.startswith(prefix) for prefix in VISIBLE_SEARCH_PREFIXES):
        return True

    if any(app_name.startswith(phrase) for phrase in VISIBLE_IMAGE_PHRASES):
        return True

    if clean_text.startswith("pull up "):
        normalised = " ".join(app_name.lower().split())

        if normalised in APP_ALIASES or normalised in WEBSITE_ALIASES:
            return False

        if "." in normalised and " " not in normalised:
            return False

        return True

    return False


def looks_like_multi_step_open_command(clean_text):
    """
    Lets the AI brain handle open-and-do requests such as website automation.
    The app shortcut should only catch obvious app/site opening.
    """

    app_name = extract_app_name(clean_text)

    if not app_name:
        return False

    if not any(connector in app_name for connector in MULTI_STEP_CONNECTORS):
        return False

    return any(word in app_name for word in FOLLOW_UP_ACTION_WORDS)


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

    if looks_like_multi_step_open_command(clean_text):
        return None

    if looks_like_visible_search_request(clean_text):
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

    if result.get("needs_confirmation"):
        top_matches = result.get("top_matches") or []
        best_match = top_matches[0] if top_matches else {}
        best_score = max(
            int(best_match.get("score") or 0),
            int(best_match.get("possible_score") or 0),
        )

        if best_score < 74:
            return {
                "handled": True,
                "response": "I couldn't confidently find that app.",
                "source": "app_skill",
            }

        return {
            "handled": True,
            "response": result.get("message", f"I found a possible match for {app_name}."),
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
