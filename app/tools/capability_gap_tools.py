import json
import re
from datetime import datetime
from pathlib import Path


# =========================
# JARVIS CAPABILITY GAPS
# Lightweight log of unmet requests and failed tool outcomes.
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
CAPABILITY_GAPS_PATH = DATA_DIR / "capability_gaps.json"
MAX_STORED_GAPS = 250

VALID_CATEGORIES = {
    "missing_tool",
    "tool_failure",
    "app_or_website",
    "browser_control",
    "screen_control",
    "web_research",
    "system_control",
    "terminal",
    "memory_or_data",
    "routine",
    "todo",
    "audio_voice",
    "external_dependency",
    "other",
}

TOOL_CATEGORY_MAP = {
    "open_application": "app_or_website",
    "search_web": "web_research",
    "fast_web_research": "web_research",
    "search_youtube": "web_research",
    "play_youtube_video": "web_research",
    "get_current_browser_page": "browser_control",
    "analyse_current_page": "browser_control",
    "save_current_website": "browser_control",
    "close_current_browser_tab": "browser_control",
    "close_browser_tabs_matching": "browser_control",
    "switch_browser_tab": "browser_control",
    "analyse_screen": "screen_control",
    "take_screenshot": "screen_control",
    "get_active_window_info": "screen_control",
    "act_on_screen": "screen_control",
    "get_current_datetime": "system_control",
    "get_system_stats": "system_control",
    "set_volume": "system_control",
    "run_terminal_command": "terminal",
    "create_or_update_routine": "routine",
    "list_routines": "routine",
    "delete_routine": "routine",
    "remember_memory": "memory_or_data",
    "list_memories": "memory_or_data",
    "forget_memory": "memory_or_data",
    "create_todo_list": "todo",
    "add_todo_task": "todo",
    "list_todo_tasks": "todo",
    "complete_todo_task": "todo",
    "remove_todo_task": "todo",
}

GAP_TRACKING_TOOLS = {
    "log_capability_gap",
    "summarize_capability_gaps",
}

INPUT_REQUIRED_TOOLS = {
    "open_application",
    "search_web",
    "fast_web_research",
    "search_youtube",
    "play_youtube_video",
    "analyse_current_page",
    "save_current_website",
    "act_on_screen",
    "run_terminal_command",
    "create_or_update_routine",
    "delete_routine",
    "remember_memory",
    "forget_memory",
    "add_todo_task",
    "complete_todo_task",
    "remove_todo_task",
}


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _clean_text(value, limit=900):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)

    if len(text) <= limit:
        return text

    return text[: limit - 3].rstrip() + "..."


def _load_gap_file():
    if not CAPABILITY_GAPS_PATH.exists():
        return []

    try:
        with open(CAPABILITY_GAPS_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception as error:
        print(f"Failed to load capability gaps: {error}")
        return []

    if isinstance(payload, list):
        return [
            item for item in payload
            if isinstance(item, dict)
        ]

    if isinstance(payload, dict):
        gaps = payload.get("gaps", [])
        if isinstance(gaps, list):
            return [
                item for item in gaps
                if isinstance(item, dict)
            ]

    return []


def _save_gap_file(gaps):
    DATA_DIR.mkdir(exist_ok=True)

    with open(CAPABILITY_GAPS_PATH, "w", encoding="utf-8") as file:
        json.dump(gaps[-MAX_STORED_GAPS:], file, indent=2)


def _normalise_category(category):
    clean = re.sub(r"[^a-z0-9_]+", "_", str(category or "").lower()).strip("_")

    aliases = {
        "missing_capability": "missing_tool",
        "unsupported": "missing_tool",
        "unsupported_request": "missing_tool",
        "apps": "app_or_website",
        "application": "app_or_website",
        "website": "app_or_website",
        "browser": "browser_control",
        "screen": "screen_control",
        "vision": "screen_control",
        "research": "web_research",
        "web": "web_research",
        "system": "system_control",
        "memory": "memory_or_data",
        "data": "memory_or_data",
        "tasks": "todo",
    }

    clean = aliases.get(clean, clean)

    if clean in VALID_CATEGORIES:
        return clean

    return "other"


def _parse_arguments(arguments_json):
    if isinstance(arguments_json, dict):
        return arguments_json

    try:
        parsed = json.loads(arguments_json or "{}")
    except Exception:
        return {}

    return parsed if isinstance(parsed, dict) else {}


def _has_meaningful_arguments(arguments):
    for value in (arguments or {}).values():
        if value is None:
            continue

        if isinstance(value, bool):
            continue

        if isinstance(value, (int, float)):
            return True

        if isinstance(value, str) and value.strip():
            return True

        if isinstance(value, (list, tuple, dict)) and value:
            return True

    return False


def _failure_reason(result):
    if not isinstance(result, dict):
        return _clean_text(result)

    for key in ["spoken_message", "message", "error", "stderr"]:
        value = result.get(key)

        if value:
            return _clean_text(value)

    return "Jarvis could not complete the request."


def _format_tool_attempt(tool_name, arguments):
    if not arguments:
        return f"Called tool {tool_name} with no arguments."

    safe_arguments = {}

    for key, value in arguments.items():
        if isinstance(value, str):
            safe_arguments[key] = _clean_text(value, limit=220)
        else:
            safe_arguments[key] = value

    return f"Called tool {tool_name} with arguments {json.dumps(safe_arguments, sort_keys=True)}."


def _category_for_tool(tool_name, result=None):
    if tool_name in TOOL_CATEGORY_MAP:
        return TOOL_CATEGORY_MAP[tool_name]

    if isinstance(result, dict) and "Unknown tool:" in str(result.get("message", "")):
        return "missing_tool"

    return "tool_failure"


def should_log_tool_failure(tool_name, arguments_json, result):
    """
    Returns True only when a failed tool outcome is useful as a capability gap.
    Routine clarifications, no-op outcomes, and user-context misses stay out.
    """

    if tool_name in GAP_TRACKING_TOOLS:
        return False

    if not isinstance(result, dict):
        return False

    if result.get("success") is not False:
        return False

    if result.get("capability_gap") is True:
        return True

    if result.get("capability_gap") is False:
        return False

    if result.get("invalid_tool_arguments"):
        return True

    if result.get("needs_confirmation") or result.get("blocked_by_safety"):
        return False

    arguments = _parse_arguments(arguments_json)

    if tool_name in INPUT_REQUIRED_TOOLS and not _has_meaningful_arguments(arguments):
        return False

    if tool_name == "run_terminal_command" and result.get("return_code") is not None:
        return False

    if tool_name == "close_browser_tabs_matching":
        if result.get("closed_count") == 0 and result.get("stop_reason") != "error":
            return False

    if tool_name in {"close_current_browser_tab", "switch_browser_tab"}:
        if result.get("window") and not result.get("error"):
            return False

    if tool_name in {"get_current_browser_page", "analyse_current_page"}:
        if result.get("active_window") and not result.get("error"):
            return False

    if tool_name in {"complete_todo_task", "remove_todo_task"}:
        if result.get("match_type") in {"missing", "not_found", "ambiguous"}:
            return False

    if tool_name in {"forget_memory", "delete_routine"} and not result.get("error"):
        return False

    return True


def log_capability_gap(
    original_request,
    attempted,
    failure_reason,
    category="other",
    source="ai_reported",
    tool_name=None,
    tool_arguments=None,
    metadata=None,
):
    """
    Append a capability gap to data/capability_gaps.json.
    """

    original_request = _clean_text(original_request, limit=1200)
    attempted = _clean_text(attempted, limit=1200)
    failure_reason = _clean_text(failure_reason, limit=1200)
    category = _normalise_category(category)

    if not original_request:
        original_request = "Unknown request."

    if not attempted:
        attempted = "No concrete attempt was recorded."

    if not failure_reason:
        failure_reason = "Jarvis could not complete the request."

    gap = {
        "timestamp": _now(),
        "original_request": original_request,
        "attempted": attempted,
        "failure_reason": failure_reason,
        "category": category,
        "source": _clean_text(source or "ai_reported", limit=80),
    }

    if tool_name:
        gap["tool_name"] = _clean_text(tool_name, limit=120)

    if tool_arguments is not None:
        gap["tool_arguments"] = tool_arguments

    if metadata:
        gap["metadata"] = metadata

    gaps = _load_gap_file()
    gaps.append(gap)
    _save_gap_file(gaps)

    return {
        "success": True,
        "message": "Capability gap logged.",
        "spoken_message": "I cannot do that yet, but I logged the gap.",
        "gap": gap,
        "gap_count": len(gaps),
        "path": str(CAPABILITY_GAPS_PATH),
    }


def record_tool_failure_if_gap(original_request, tool_name, arguments_json, result):
    """
    Log a failed tool result if it represents a genuine capability gap.
    """

    if not should_log_tool_failure(tool_name, arguments_json, result):
        return None

    arguments = _parse_arguments(arguments_json)
    category = _category_for_tool(tool_name, result=result)
    attempted = _format_tool_attempt(tool_name, arguments)
    reason = _failure_reason(result)
    metadata = {
        "result_keys": sorted(str(key) for key in result.keys()),
    }

    return log_capability_gap(
        original_request=original_request,
        attempted=attempted,
        failure_reason=reason,
        category=category,
        source="tool_failure",
        tool_name=tool_name,
        tool_arguments=arguments,
        metadata=metadata,
    )


def load_capability_gaps(limit=None, category=None):
    gaps = _load_gap_file()

    if category:
        clean_category = _normalise_category(category)
        gaps = [
            gap for gap in gaps
            if _normalise_category(gap.get("category")) == clean_category
        ]

    if limit is not None:
        try:
            limit = int(limit)
        except Exception:
            limit = 5

        limit = max(1, min(50, limit))
        gaps = gaps[-limit:]

    return gaps


def _summary_line(gap):
    category = _normalise_category(gap.get("category"))
    request = _clean_text(gap.get("original_request"), limit=120)
    reason = _clean_text(gap.get("failure_reason"), limit=140)

    if reason:
        return f"{category}: {request} - {reason}"

    return f"{category}: {request}"


def summarize_capability_gaps(limit=5, category=None):
    """
    Summarise recent recorded gaps for questions like "what can't you do?".
    """

    gaps = load_capability_gaps(limit=limit, category=category)

    if not gaps:
        return {
            "success": True,
            "message": "I do not have any recent capability gaps logged.",
            "spoken_message": "I do not have any recent capability gaps logged.",
            "gaps": [],
            "path": str(CAPABILITY_GAPS_PATH),
        }

    recent = list(reversed(gaps))
    lines = [_summary_line(gap) for gap in recent]

    category_counts = {}

    for gap in gaps:
        category_name = _normalise_category(gap.get("category"))
        category_counts[category_name] = category_counts.get(category_name, 0) + 1

    top_categories = sorted(
        category_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )

    category_text = ", ".join(
        f"{name} ({count})"
        for name, count in top_categories[:3]
    )

    spoken_items = [
        _clean_text(gap.get("original_request"), limit=90)
        for gap in recent[:3]
        if gap.get("original_request")
    ]

    if len(spoken_items) == 1:
        spoken = f"Recently, the main gap was: {spoken_items[0]}."
    else:
        spoken = "Recently, I have struggled with: " + "; ".join(spoken_items) + "."

    if category_text:
        spoken += f" The main categories are {category_text}."

    return {
        "success": True,
        "message": "Recent capability gaps:\n- " + "\n- ".join(lines),
        "spoken_message": spoken,
        "gaps": recent,
        "category_counts": category_counts,
        "path": str(CAPABILITY_GAPS_PATH),
    }
