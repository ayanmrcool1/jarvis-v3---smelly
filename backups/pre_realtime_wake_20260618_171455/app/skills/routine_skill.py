import json
import time
import webbrowser
import difflib
from pathlib import Path

from tools.system_tools import open_application, set_volume


# =========================
# JARVIS ROUTINE SKILL
# Loads and runs routines from data/routines.json
# Now supports:
# - fuzzy routine matching
# - describing routines
# - avoiding accidental routine runs during create/update/delete/list commands
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
ROUTINES_PATH = BASE_DIR / "data" / "routines.json"


def load_routines():
    """
    Loads saved routines from C:\\Jarvis\\data\\routines.json.
    """

    if not ROUTINES_PATH.exists():
        return {}

    try:
        with open(ROUTINES_PATH, "r", encoding="utf-8") as file:
            return json.load(file)

    except Exception as error:
        print(f"Failed to load routines: {error}")
        return {}


def open_url(label, url):
    """
    Opens a website URL.
    """

    try:
        webbrowser.open(url)

        return {
            "success": True,
            "message": f"Opened {label}.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to open {label}: {error}",
        }


def run_routine_step(step):
    """
    Runs one routine step.

    Supported step types:
    - url
    - app
    - volume
    - wait
    - message
    """

    step_type = step.get("type")
    label = step.get("label", "step")
    value = step.get("value")

    if step_type == "url":
        return open_url(label, value)

    if step_type == "app":
        return open_application(value)

    if step_type == "volume":
        return set_volume(value)

    if step_type == "wait":
        try:
            seconds = float(value)
            time.sleep(seconds)

            return {
                "success": True,
                "message": f"Waited {seconds} seconds.",
            }

        except Exception as error:
            return {
                "success": False,
                "message": f"Failed to wait: {error}",
            }

    if step_type == "message":
        return {
            "success": True,
            "message": str(value),
        }

    return {
        "success": False,
        "message": f"Unknown routine step type: {step_type}",
    }


def run_routine(routine_key, routine_data):
    """
    Runs all steps in a saved routine.
    """

    display_name = routine_data.get("display_name", routine_key)
    steps = routine_data.get("steps", [])

    if not steps:
        return {
            "handled": True,
            "response": f"{display_name} started.",
            "source": "routine_skill",
            "details": [],
        }

    results = []

    for step in steps:
        result = run_routine_step(step)
        results.append(result)

        # Small delay so apps/sites do not all fire at the exact same millisecond.
        time.sleep(0.3)

    successful_steps = [
        result for result in results
        if result.get("success")
    ]

    if successful_steps:
        return {
            "handled": True,
            "response": f"{display_name} started.",
            "source": "routine_skill",
            "details": results,
        }

    return {
        "handled": True,
        "response": f"I tried to start {display_name}, but nothing opened.",
        "source": "routine_skill",
        "details": results,
    }


def is_routine_management_command(clean_text):
    """
    If the user is creating/updating/deleting/listing routines,
    do not accidentally run or describe a routine locally.
    Let the AI routine tools handle it.
    """

    create_words = [
        "create",
        "creating",
        "make",
        "making",
        "save",
        "saving",
        "set up",
        "setting up",
        "setup",
        "build",
        "building",
    ]

    update_words = [
        "update",
        "updating",
        "change",
        "changing",
        "edit",
        "editing",
        "modify",
        "modifying",
        "replace",
        "replacing",
    ]

    delete_words = [
        "delete",
        "deleting",
        "remove",
        "removing",
        "forget",
        "forgetting",
    ]

    list_phrases = [
        "list routines",
        "show routines",
        "saved routines",
        "what routines",
        "which routines",
        "tell me my routines",
        "tell me which routines",
    ]

    routine_words = [
        "routine",
        "routines",
        "mode",
        "setup",
    ]

    if any(phrase in clean_text for phrase in list_phrases):
        return True

    if any(routine_word in clean_text for routine_word in routine_words):
        if any(word in clean_text for word in create_words):
            return True

        if any(word in clean_text for word in update_words):
            return True

        if any(word in clean_text for word in delete_words):
            return True

    return False


def is_description_request(clean_text):
    """
    Detects when the user is asking what a routine does,
    instead of asking to run it.
    """

    description_phrases = [
        "what does",
        "what do",
        "what is inside",
        "whats inside",
        "what's inside",
        "inside of",
        "what is in",
        "whats in",
        "what's in",
        "tell me what",
        "show me what",
        "describe",
        "explain",
        "what are the steps",
        "routine steps",
        "steps in",
    ]

    return any(phrase in clean_text for phrase in description_phrases)


def is_run_request(clean_text):
    """
    Detects when the user is asking to run/start/open a routine.
    """

    run_phrases = [
        "start ",
        "run ",
        "open ",
        "launch ",
        "begin ",
        "activate ",
    ]

    return any(clean_text.startswith(phrase) for phrase in run_phrases)


def routine_candidates_for(routine_key, routine_data):
    """
    Builds possible names/phrases for a routine.
    """

    candidates = []

    candidates.append(routine_key.replace("_", " ").lower().strip())

    display_name = routine_data.get("display_name", "")
    if display_name:
        candidates.append(display_name.lower().strip())

    for trigger in routine_data.get("trigger_phrases", []):
        if trigger:
            candidates.append(trigger.lower().strip())

    # Remove duplicates while preserving order.
    unique_candidates = []

    for candidate in candidates:
        if candidate and candidate not in unique_candidates:
            unique_candidates.append(candidate)

    return unique_candidates


def extract_possible_routine_target(clean_text):
    """
    Extracts the likely routine name from a command.

    Example:
    'start quick test' -> 'quick test'
    'start click test start click test' -> 'click test'
    """

    prefixes = [
        "start ",
        "run ",
        "open ",
        "launch ",
        "begin ",
        "activate ",
    ]

    target = clean_text

    for prefix in prefixes:
        if target.startswith(prefix):
            target = target.replace(prefix, "", 1).strip()
            break

    # If Whisper repeats the command, trim after the repeated command word.
    repeated_markers = [
        " start ",
        " run ",
        " open ",
        " launch ",
        " begin ",
        " activate ",
    ]

    for marker in repeated_markers:
        if marker in target:
            target = target.split(marker)[0].strip()
            break

    return target


def find_matching_routine(clean_text, routines):
    """
    Finds a routine by exact phrase or fuzzy match.
    Handles cases like:
    'start click test' -> 'quick test'
    """

    if not routines:
        return None, None

    # 1. Exact phrase match first.
    for routine_key, routine_data in routines.items():
        for candidate in routine_candidates_for(routine_key, routine_data):
            if candidate in clean_text:
                return routine_key, routine_data

    # 2. Fuzzy match against likely command target.
    possible_target = extract_possible_routine_target(clean_text)

    all_candidates = []

    for routine_key, routine_data in routines.items():
        for candidate in routine_candidates_for(routine_key, routine_data):
            all_candidates.append(
                {
                    "routine_key": routine_key,
                    "routine_data": routine_data,
                    "candidate": candidate,
                }
            )

    candidate_names = [
        item["candidate"]
        for item in all_candidates
    ]

    fuzzy_matches = difflib.get_close_matches(
        possible_target,
        candidate_names,
        n=1,
        cutoff=0.55,
    )

    if fuzzy_matches:
        matched_name = fuzzy_matches[0]

        for item in all_candidates:
            if item["candidate"] == matched_name:
                print(f"Routine fuzzy matched: '{possible_target}' -> '{matched_name}'")
                return item["routine_key"], item["routine_data"]

    return None, None


def describe_routine(routine_key, routine_data):
    """
    Returns a spoken description of a routine instead of running it.
    """

    display_name = routine_data.get("display_name", routine_key)
    steps = routine_data.get("steps", [])

    if not steps:
        response = f"{display_name} has no steps saved yet."

        return {
            "handled": True,
            "response": response,
            "source": "routine_skill",
        }

    spoken_steps = []

    for index, step in enumerate(steps, start=1):
        step_type = step.get("type", "step")
        label = step.get("label", "")
        value = step.get("value", "")

        if step_type == "url":
            spoken_steps.append(f"{index}, open {label}.")

        elif step_type == "app":
            spoken_steps.append(f"{index}, open {label}.")

        elif step_type == "volume":
            spoken_steps.append(f"{index}, set volume {value}.")

        elif step_type == "wait":
            spoken_steps.append(f"{index}, wait {value} seconds.")

        elif step_type == "message":
            spoken_steps.append(f"{index}, say {value}.")

        else:
            spoken_steps.append(f"{index}, {label}.")

    response = f"{display_name} has {len(steps)} steps: " + " ".join(spoken_steps)

    return {
        "handled": True,
        "response": response,
        "source": "routine_skill",
    }


def handle_routine_command(transcription, clean_text):
    """
    Handles saved routines.

    It can:
    - run a routine
    - describe a routine
    - fuzzy match routine names

    Important:
    Do NOT fuzzy match normal chat like "what is your name".
    """

    # Do not run routines while the user is trying to manage routines.
    if is_routine_management_command(clean_text):
        return None

    routines = load_routines()

    if not routines:
        return None

    # -------------------------
    # Work out whether this even sounds routine-related
    # -------------------------
    routine_words = [
        "routine",
        "routines",
        "mode",
        "setup",
    ]

    run_words = [
        "start ",
        "run ",
        "open ",
        "launch ",
        "begin ",
        "activate ",
    ]

    sounds_like_routine_command = (
        any(word in clean_text for word in routine_words)
        or any(clean_text.startswith(word) for word in run_words)
    )

    # Allow exact routine name by itself, e.g. "love" or "quick test".
    exact_simple_match = False

    for routine_key, routine_data in routines.items():
        simple_commands = routine_candidates_for(routine_key, routine_data)

        if clean_text in simple_commands:
            exact_simple_match = True
            break

    if not sounds_like_routine_command and not exact_simple_match:
        return None

    routine_key, routine_data = find_matching_routine(clean_text, routines)

    if not routine_key or not routine_data:
        return None

    display_name = routine_data.get("display_name", routine_key)
    print(f"Routine matched: {routine_key}")

    # If user asks what it does, describe it instead of running it.
    if is_description_request(clean_text):
        return describe_routine(routine_key, routine_data)

    # If the user is clearly asking to start/run/open it, run it.
    if is_run_request(clean_text):
        return run_routine(routine_key, routine_data)

    # If the routine name/trigger is said by itself, run it.
    simple_commands = routine_candidates_for(routine_key, routine_data)

    if clean_text in simple_commands:
        return run_routine(routine_key, routine_data)

    # If it matched a routine but the intent is unclear, describe instead of running.
    return {
        "handled": True,
        "response": f"I found {display_name}. Say start {display_name} if you want me to run it.",
        "source": "routine_skill",
    }