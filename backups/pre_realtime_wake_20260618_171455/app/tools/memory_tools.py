import json
import re
from pathlib import Path
from datetime import datetime


# =========================
# JARVIS MEMORY TOOLS
# Explicit + passive memory storage
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
MEMORY_PATH = BASE_DIR / "data" / "memory.json"

VALID_CATEGORIES = [
    "user_profile",
    "preferences",
    "aliases",
    "workflow_rules",
    "jarvis_rules",
    "notes",
]


def ensure_memory_file():
    """
    Ensures memory.json exists.
    """

    MEMORY_PATH.parent.mkdir(exist_ok=True)

    if not MEMORY_PATH.exists():
        default_memory = {
            "user_profile": [],
            "preferences": [],
            "aliases": [],
            "workflow_rules": [],
            "jarvis_rules": [],
            "notes": [],
        }

        save_memory_file(default_memory)


def load_memory_file():
    """
    Loads memory from C:\\Jarvis\\data\\memory.json.
    """

    ensure_memory_file()

    try:
        with open(MEMORY_PATH, "r", encoding="utf-8") as file:
            memory = json.load(file)

    except Exception as error:
        print(f"Failed to load memory file: {error}")
        memory = {}

    for category in VALID_CATEGORIES:
        if category not in memory:
            memory[category] = []

    return memory


def save_memory_file(memory):
    """
    Saves memory to C:\\Jarvis\\data\\memory.json.
    """

    try:
        MEMORY_PATH.parent.mkdir(exist_ok=True)

        with open(MEMORY_PATH, "w", encoding="utf-8") as file:
            json.dump(memory, file, indent=2)

        return {
            "success": True,
            "message": "Memory saved.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to save memory: {error}",
        }


def normalize_category(category):
    """
    Normalises memory categories.
    """

    if not category:
        return "notes"

    clean = category.lower().strip().replace(" ", "_")

    category_aliases = {
        "profile": "user_profile",
        "user": "user_profile",
        "about_user": "user_profile",
        "preference": "preferences",
        "preferences": "preferences",
        "alias": "aliases",
        "aliases": "aliases",
        "workflow": "workflow_rules",
        "workflow_rule": "workflow_rules",
        "workflow_rules": "workflow_rules",
        "jarvis_rule": "jarvis_rules",
        "jarvis_rules": "jarvis_rules",
        "note": "notes",
        "notes": "notes",
    }

    return category_aliases.get(clean, "notes")


def normalize_text(text):
    """
    Normalises text for duplicate checking.
    """

    if not text:
        return ""

    text = text.lower().strip()
    text = re.sub(r"\s+", " ", text)

    return text


def memory_exists(memory, category, content):
    """
    Checks if a similar memory already exists.
    """

    clean_content = normalize_text(content)

    for item in memory.get(category, []):
        existing_content = normalize_text(item.get("content", ""))

        if existing_content == clean_content:
            return True

    return False


def remember_memory(category, content, source="explicit", confidence=1.0, tags=None):
    """
    Saves a memory item.

    category options:
    - user_profile
    - preferences
    - aliases
    - workflow_rules
    - jarvis_rules
    - notes
    """

    if not content or not content.strip():
        return {
            "success": False,
            "message": "No memory content was provided.",
        }

    memory = load_memory_file()
    category = normalize_category(category)

    if memory_exists(memory, category, content):
        return {
            "success": True,
            "message": "I already remember that.",
        }

    item = {
        "content": content.strip(),
        "source": source,
        "confidence": float(confidence),
        "tags": tags or [],
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }

    memory[category].append(item)

    save_result = save_memory_file(memory)

    if not save_result.get("success"):
        return save_result

    return {
        "success": True,
        "message": f"I’ll remember that: {content.strip()}",
        "category": category,
        "memory": item,
    }


def list_memories(category=None):
    """
    Lists saved memories.
    """

    memory = load_memory_file()

    if category:
        category = normalize_category(category)
        memories = memory.get(category, [])

        if not memories:
            return {
                "success": True,
                "message": f"I do not have any memories saved under {category}.",
                "memories": [],
            }

        contents = [
            item.get("content", "")
            for item in memories
        ]

        return {
            "success": True,
            "message": f"{category}: " + " | ".join(contents),
            "memories": memories,
        }

    all_contents = []

    for category_name, items in memory.items():
        for item in items:
            content = item.get("content", "")

            if content:
                all_contents.append(f"{category_name}: {content}")

    if not all_contents:
        return {
            "success": True,
            "message": "I do not have any memories saved yet.",
            "memories": [],
        }

    return {
        "success": True,
        "message": "Here is what I remember: " + " | ".join(all_contents),
        "memories": memory,
    }


def forget_memory(query, category=None):
    """
    Deletes memories that contain the query text.
    """

    if not query or not query.strip():
        return {
            "success": False,
            "message": "No forget query was provided.",
        }

    memory = load_memory_file()
    clean_query = normalize_text(query)

    categories_to_search = [normalize_category(category)] if category else VALID_CATEGORIES

    removed = []

    for category_name in categories_to_search:
        kept_items = []

        for item in memory.get(category_name, []):
            content = item.get("content", "")
            clean_content = normalize_text(content)

            if clean_query in clean_content:
                removed.append(content)
            else:
                kept_items.append(item)

        memory[category_name] = kept_items

    save_result = save_memory_file(memory)

    if not save_result.get("success"):
        return save_result

    if not removed:
        return {
            "success": False,
            "message": f"I could not find a memory matching: {query}",
        }

    return {
        "success": True,
        "message": "Forgot: " + " | ".join(removed),
        "removed": removed,
    }


def build_memory_context(max_items_per_category=8):
    """
    Builds a short memory context string for the AI brain.
    This gets injected into Jarvis responses so he remembers your preferences.
    """

    memory = load_memory_file()

    sections = []

    category_labels = {
        "user_profile": "User profile",
        "preferences": "User preferences",
        "aliases": "Aliases and meanings",
        "workflow_rules": "Workflow rules",
        "jarvis_rules": "Jarvis behavior rules",
        "notes": "Useful notes",
    }

    for category in VALID_CATEGORIES:
        items = memory.get(category, [])

        if not items:
            continue

        recent_items = items[-max_items_per_category:]

        lines = [
            f"- {item.get('content')}"
            for item in recent_items
            if item.get("content")
        ]

        if lines:
            sections.append(
                f"{category_labels.get(category, category)}:\n" + "\n".join(lines)
            )

    if not sections:
        return "No saved memory yet."

    return "\n\n".join(sections)


def should_passively_consider_memory(user_text):
    """
    Quick local filter before asking AI to extract passive memories.
    This prevents wasting API calls on every random command.
    """

    if not user_text or not user_text.strip():
        return False

    clean = normalize_text(user_text)

    passive_memory_signals = [
        "i like",
        "i prefer",
        "i usually",
        "i always",
        "i never",
        "from now on",
        "going forward",
        "when i say",
        "if i say",
        "by default",
        "my default",
        "i want you to",
        "i dont want you to",
        "i don't want you to",
        "remember",
        "dont forget",
        "don't forget",
        "my trading",
        "my setup",
        "my workflow",
        "the way i like",
        "i hate when",
    ]

    return any(signal in clean for signal in passive_memory_signals)