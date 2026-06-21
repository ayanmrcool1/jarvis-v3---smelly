import json
import re
from pathlib import Path


# =========================
# JARVIS ROUTINE TOOLS
# Lets Jarvis create/update/list routines in data/routines.json
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
ROUTINES_PATH = BASE_DIR / "data" / "routines.json"


SUPPORTED_STEP_TYPES = [
    "url",
    "app",
    "volume",
    "wait",
    "message",
]


def load_routines_file():
    """
    Load routines from C:\\Jarvis\\data\\routines.json.
    """

    if not ROUTINES_PATH.exists():
        ROUTINES_PATH.parent.mkdir(exist_ok=True)
        ROUTINES_PATH.write_text("{}", encoding="utf-8")
        return {}

    try:
        with open(ROUTINES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as error:
        print(f"Failed to load routines file: {error}")
        return {}


def save_routines_file(routines):
    """
    Save routines to C:\\Jarvis\\data\\routines.json.
    """

    try:
        ROUTINES_PATH.parent.mkdir(exist_ok=True)

        with open(ROUTINES_PATH, "w", encoding="utf-8") as file:
            json.dump(routines, file, indent=2)

        return {
            "success": True,
            "message": "Routines saved.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to save routines: {error}",
        }


def make_routine_key(routine_name):
    """
    Converts routine names into safe keys.

    Example:
    'Trading Prep' -> 'trading_prep'
    """

    clean = routine_name.lower().strip()
    clean = re.sub(r"[^a-z0-9\s_]", "", clean)
    clean = re.sub(r"\s+", "_", clean)

    return clean


def normalise_trigger_phrases(routine_name, trigger_phrases):
    """
    Ensures routines have sensible trigger phrases.
    """

    routine_name_clean = routine_name.lower().strip()

    default_triggers = [
        routine_name_clean,
        f"start {routine_name_clean}",
        f"open {routine_name_clean}",
        f"run {routine_name_clean}",
    ]

    final_triggers = []

    for phrase in default_triggers + (trigger_phrases or []):
        phrase = phrase.lower().strip()

        if phrase and phrase not in final_triggers:
            final_triggers.append(phrase)

    return final_triggers


def validate_steps(steps):
    """
    Validates and cleans routine steps.
    """

    cleaned_steps = []

    if not isinstance(steps, list):
        return cleaned_steps

    for step in steps:
        if not isinstance(step, dict):
            continue

        step_type = str(step.get("type", "")).lower().strip()
        label = str(step.get("label", "")).strip()
        value = step.get("value")

        if step_type not in SUPPORTED_STEP_TYPES:
            continue

        if value is None or str(value).strip() == "":
            continue

        value = str(value).strip()

        if not label:
            label = value

        # Basic safety checks
        if step_type == "url":
            if not value.startswith("http://") and not value.startswith("https://"):
                value = "https://" + value

        if step_type == "volume":
            if value not in ["up", "down", "mute"]:
                continue

        cleaned_steps.append(
            {
                "type": step_type,
                "label": label,
                "value": value,
            }
        )

    return cleaned_steps


def create_or_update_routine(routine_name, display_name=None, trigger_phrases=None, steps=None):
    """
    Creates or updates a routine in routines.json.

    Example steps:
    [
        {"type": "url", "label": "TradingView", "value": "https://www.tradingview.com/"},
        {"type": "app", "label": "Chrome", "value": "chrome"},
        {"type": "volume", "label": "Volume down", "value": "down"}
    ]
    """

    if not routine_name or not routine_name.strip():
        return {
            "success": False,
            "message": "No routine name was provided.",
        }

    routines = load_routines_file()

    routine_key = make_routine_key(routine_name)
    clean_steps = validate_steps(steps or [])

    if not clean_steps:
        return {
            "success": False,
            "message": "I could not create the routine because no valid steps were provided.",
        }

    display_name = display_name or routine_name.strip()

    routines[routine_key] = {
        "display_name": display_name,
        "trigger_phrases": normalise_trigger_phrases(routine_name, trigger_phrases or []),
        "steps": clean_steps,
    }

    save_result = save_routines_file(routines)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Saved routine: {display_name}.",
        "routine_key": routine_key,
        "routine": routines[routine_key],
    }


def list_routines():
    """
    Lists saved routines.
    """

    routines = load_routines_file()

    if not routines:
        return {
            "success": True,
            "message": "No routines are saved yet.",
            "routines": [],
        }

    routine_names = [
        routine_data.get("display_name", routine_key)
        for routine_key, routine_data in routines.items()
    ]

    return {
        "success": True,
        "message": "Saved routines: " + ", ".join(routine_names),
        "routines": routine_names,
    }


def delete_routine(routine_name):
    """
    Deletes a routine by name.
    """

    if not routine_name or not routine_name.strip():
        return {
            "success": False,
            "message": "No routine name was provided.",
        }

    routines = load_routines_file()
    routine_key = make_routine_key(routine_name)

    if routine_key not in routines:
        return {
            "success": False,
            "message": f"I could not find a routine called {routine_name}.",
        }

    display_name = routines[routine_key].get("display_name", routine_name)
    del routines[routine_key]

    save_result = save_routines_file(routines)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Deleted routine: {display_name}.",
    }