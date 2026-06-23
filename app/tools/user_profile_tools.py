import json
import os
import re
from datetime import datetime
from pathlib import Path


# =========================
# JARVIS USER PROFILE TOOLS
# Per-user runtime personalisation context.
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
PROFILE_DIR = BASE_DIR / "data" / "user_profiles"

SCHEMA_VERSION = 1

VALID_PROFILE_CATEGORIES = [
    "identity",
    "response_preferences",
    "vocabulary",
    "habits",
    "workflows",
    "project_context",
    "jarvis_behavior",
    "safety_preferences",
    "corrections",
    "notes",
]

CATEGORY_LABELS = {
    "identity": "Identity",
    "response_preferences": "Response preferences",
    "vocabulary": "Vocabulary and terms",
    "habits": "Habits",
    "workflows": "Workflows",
    "project_context": "Project context",
    "jarvis_behavior": "Jarvis behavior guidance",
    "safety_preferences": "Safety preferences",
    "corrections": "Repeated corrections",
    "notes": "Useful notes",
}

CATEGORY_ALIASES = {
    "profile": "identity",
    "user_profile": "identity",
    "user": "identity",
    "identity": "identity",
    "preference": "response_preferences",
    "preferences": "response_preferences",
    "response_preference": "response_preferences",
    "response_preferences": "response_preferences",
    "style": "response_preferences",
    "vocab": "vocabulary",
    "vocabulary": "vocabulary",
    "term": "vocabulary",
    "terms": "vocabulary",
    "language": "vocabulary",
    "habit": "habits",
    "habits": "habits",
    "workflow": "workflows",
    "workflows": "workflows",
    "workflow_rule": "workflows",
    "workflow_rules": "workflows",
    "project": "project_context",
    "project_context": "project_context",
    "context": "project_context",
    "jarvis": "jarvis_behavior",
    "jarvis_rule": "jarvis_behavior",
    "jarvis_rules": "jarvis_behavior",
    "assistant_behavior": "jarvis_behavior",
    "behavior": "jarvis_behavior",
    "behaviour": "jarvis_behavior",
    "safety": "safety_preferences",
    "safety_preference": "safety_preferences",
    "safety_preferences": "safety_preferences",
    "confirmation": "safety_preferences",
    "correction": "corrections",
    "corrections": "corrections",
    "note": "notes",
    "notes": "notes",
}


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _safe_user_id(value):
    clean = str(value or "").strip().lower()
    clean = re.sub(r"[^a-z0-9_-]+", "_", clean)
    clean = clean.strip("_")

    if not clean:
        clean = "default"

    return clean[:64]


def get_active_user_id():
    """
    Resolves the active profile id.
    Defaults to the Windows user so one machine account gets one profile without setup.
    """

    configured_user = (
        os.getenv("JARVIS_USER_ID")
        or os.getenv("JARVIS_PROFILE_ID")
        or os.getenv("USERNAME")
        or os.getenv("USER")
        or "default"
    )

    return _safe_user_id(configured_user)


def _get_configured_display_name():
    display_name = os.getenv("JARVIS_USER_NAME")

    if display_name and display_name.strip():
        return display_name.strip()

    return None


def get_profile_path(user_id=None):
    user_id = _safe_user_id(user_id or get_active_user_id())
    return PROFILE_DIR / f"{user_id}.json"


def _default_profile(user_id=None):
    user_id = _safe_user_id(user_id or get_active_user_id())
    now = _now()

    return {
        "schema_version": SCHEMA_VERSION,
        "user_id": user_id,
        "display_name": _get_configured_display_name(),
        "summary": "",
        "created_at": now,
        "updated_at": now,
        **{category: [] for category in VALID_PROFILE_CATEGORIES},
    }


def _normalise_category(category):
    if not category:
        return "notes"

    clean = str(category or "").lower().strip().replace(" ", "_")
    return CATEGORY_ALIASES.get(clean, "notes")


def _normalise_text(text):
    clean = str(text or "").lower().strip()
    return re.sub(r"\s+", " ", clean)


def _clean_content(content):
    clean = str(content or "").strip()
    clean = re.sub(r"\s+", " ", clean)
    return clean


def _profile_has_detail(profile, category, content):
    clean_content = _normalise_text(content)

    for item in profile.get(category, []):
        if _normalise_text(item.get("content", "")) == clean_content:
            return True

    return False


def ensure_user_profile(user_id=None):
    """
    Ensures the active user's profile file exists.
    New users start with a blank/minimal profile.
    """

    profile_path = get_profile_path(user_id)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    if not profile_path.exists():
        save_user_profile(_default_profile(user_id))

    return profile_path


def load_user_profile(user_id=None):
    """
    Loads the active user profile from data/user_profiles/<user_id>.json.
    """

    user_id = _safe_user_id(user_id or get_active_user_id())
    profile_path = ensure_user_profile(user_id)

    try:
        with open(profile_path, "r", encoding="utf-8") as file:
            profile = json.load(file)
    except Exception as error:
        print(f"Failed to load user profile {profile_path}: {error}")
        return _default_profile(user_id)

    if not isinstance(profile, dict):
        profile = _default_profile(user_id)

    changed = False

    if profile.get("schema_version") != SCHEMA_VERSION:
        profile["schema_version"] = SCHEMA_VERSION
        changed = True

    if profile.get("user_id") != user_id:
        profile["user_id"] = user_id
        changed = True

    if "display_name" not in profile:
        profile["display_name"] = _get_configured_display_name()
        changed = True

    if "summary" not in profile:
        profile["summary"] = ""
        changed = True

    if "created_at" not in profile:
        profile["created_at"] = _now()
        changed = True

    if "updated_at" not in profile:
        profile["updated_at"] = _now()
        changed = True

    for category in VALID_PROFILE_CATEGORIES:
        if not isinstance(profile.get(category), list):
            profile[category] = []
            changed = True

    configured_display_name = _get_configured_display_name()
    if configured_display_name and profile.get("display_name") != configured_display_name:
        profile["display_name"] = configured_display_name
        changed = True

    if changed:
        save_user_profile(profile)

    return profile


def save_user_profile(profile):
    """
    Saves a user profile to its own profile file.
    """

    try:
        PROFILE_DIR.mkdir(parents=True, exist_ok=True)

        user_id = _safe_user_id(profile.get("user_id") or get_active_user_id())
        profile["user_id"] = user_id
        profile["updated_at"] = _now()

        with open(get_profile_path(user_id), "w", encoding="utf-8") as file:
            json.dump(profile, file, indent=2)

        return {
            "success": True,
            "message": "User profile saved.",
            "user_id": user_id,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to save user profile: {error}",
        }


def remember_user_profile_detail(
    category,
    content,
    source="explicit",
    confidence=1.0,
    tags=None,
):
    """
    Saves a durable personalisation detail for the active user.
    """

    content = _clean_content(content)

    if not content:
        return {
            "success": False,
            "message": "No profile detail was provided.",
        }

    profile = load_user_profile()
    category = _normalise_category(category)

    if _profile_has_detail(profile, category, content):
        return {
            "success": True,
            "message": "That profile detail is already saved.",
            "spoken_message": "I already had that in your profile.",
            "user_id": profile.get("user_id"),
        }

    now = _now()
    item = {
        "content": content,
        "source": source or "explicit",
        "confidence": float(confidence),
        "tags": tags or [],
        "created_at": now,
        "updated_at": now,
    }

    profile[category].append(item)
    save_result = save_user_profile(profile)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"Saved profile detail: {content}",
        "spoken_message": "Got it. I'll keep that in your profile.",
        "user_id": profile.get("user_id"),
        "category": category,
        "profile_detail": item,
    }


def list_user_profile(category=None):
    """
    Lists saved details for the active user's runtime profile.
    """

    profile = load_user_profile()
    categories = [_normalise_category(category)] if category else VALID_PROFILE_CATEGORIES

    lines = []

    for category_name in categories:
        for item in profile.get(category_name, []):
            content = item.get("content")

            if content:
                lines.append(f"{CATEGORY_LABELS.get(category_name, category_name)}: {content}")

    if not lines:
        return {
            "success": True,
            "message": "This user profile is blank.",
            "spoken_message": "This profile is blank so far.",
            "user_id": profile.get("user_id"),
            "profile": profile,
        }

    return {
        "success": True,
        "message": "Current user profile: " + " | ".join(lines),
        "spoken_message": f"I found {len(lines)} saved profile details.",
        "user_id": profile.get("user_id"),
        "profile": profile,
        "details": lines,
    }


def forget_user_profile_detail(query, category=None):
    """
    Deletes active-user profile details matching a query.
    """

    clean_query = _normalise_text(query)

    if not clean_query:
        return {
            "success": False,
            "message": "No profile detail query was provided.",
        }

    profile = load_user_profile()
    categories = [_normalise_category(category)] if category else VALID_PROFILE_CATEGORIES
    removed = []

    for category_name in categories:
        kept_items = []

        for item in profile.get(category_name, []):
            content = item.get("content", "")

            if clean_query in _normalise_text(content):
                removed.append(content)
            else:
                kept_items.append(item)

        profile[category_name] = kept_items

    save_result = save_user_profile(profile)

    if not save_result.get("success"):
        return save_result

    if not removed:
        return {
            "success": False,
            "message": f"I could not find a profile detail matching: {query}",
            "spoken_message": "I couldn't find that in your profile.",
            "user_id": profile.get("user_id"),
        }

    return {
        "success": True,
        "message": "Forgot profile detail: " + " | ".join(removed),
        "spoken_message": "Done. I removed that from your profile.",
        "user_id": profile.get("user_id"),
        "removed": removed,
    }


def _trim_context(text, max_chars):
    if len(text) <= max_chars:
        return text

    trimmed = text[: max(0, max_chars - 4)].rstrip()
    trimmed = trimmed.rsplit("\n", 1)[0].rstrip()

    return trimmed + "\n..."


def build_user_profile_context(max_items_per_category=5, max_chars=1600):
    """
    Builds a compact runtime profile block for the AI brain.
    Profile guidance should influence tone/action choices, not override the current request.
    """

    profile = load_user_profile()
    user_id = profile.get("user_id") or get_active_user_id()
    display_name = profile.get("display_name") or user_id

    sections = [
        "Profile guidance: use this as soft context. The current user request and safety still take priority.",
        f"Active user: {display_name} ({user_id}).",
    ]

    summary = str(profile.get("summary") or "").strip()

    if summary:
        sections.append(f"Summary: {summary}")

    has_details = False

    for category in VALID_PROFILE_CATEGORIES:
        items = profile.get(category, [])

        if not items:
            continue

        recent_items = items[-max_items_per_category:]
        lines = [
            f"- {item.get('content')}"
            for item in recent_items
            if item.get("content")
        ]

        if not lines:
            continue

        has_details = True
        sections.append(
            f"{CATEGORY_LABELS.get(category, category)}:\n" + "\n".join(lines)
        )

    if not has_details and not summary:
        sections.append("No saved profile details yet.")

    return _trim_context("\n\n".join(sections), max_chars)
