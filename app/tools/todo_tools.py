import json
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from ui_state import open_widget as open_hud_widget
from ui_state import update_widget_content


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
TODO_PATH = DATA_DIR / "todo.json"
TODO_WIDGET_ID = "todo_widget"


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _normalise_text(text):
    return " ".join(str(text or "").strip().lower().split())


def _load_tasks():
    DATA_DIR.mkdir(exist_ok=True)

    if not TODO_PATH.exists():
        _save_tasks([])
        return []

    try:
        with open(TODO_PATH, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except Exception:
        return []

    tasks = payload.get("tasks", []) if isinstance(payload, dict) else payload

    if not isinstance(tasks, list):
        return []

    normalised_tasks = []

    for task in tasks:
        if not isinstance(task, dict):
            continue

        text = str(task.get("text", "")).strip()

        if not text:
            continue

        normalised_tasks.append(
            {
                "id": str(task.get("id") or uuid4().hex),
                "text": text,
                "done": bool(task.get("done", False)),
                "created_at": str(task.get("created_at") or _now()),
            }
        )

    return normalised_tasks


def _save_tasks(tasks):
    DATA_DIR.mkdir(exist_ok=True)

    with open(TODO_PATH, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=2)


def _sync_widget(tasks, open_widget=False):
    content = {
        "tasks": tasks,
    }

    if open_widget:
        open_hud_widget(
            widget_id=TODO_WIDGET_ID,
            widget_type="todo",
            title="TO-DO LIST",
            content=content,
        )
        return

    update_widget_content(TODO_WIDGET_ID, content)


def _public_task(task, index):
    return {
        "index": index,
        "id": task.get("id"),
        "text": task.get("text"),
        "done": bool(task.get("done")),
        "created_at": task.get("created_at"),
    }


def _match_task(tasks, task_ref, include_done=True):
    clean_ref = _normalise_text(task_ref)

    if not clean_ref:
        return None, "missing", []

    if clean_ref.isdigit():
        index = int(clean_ref) - 1

        if 0 <= index < len(tasks):
            return index, "index", []

    id_matches = [
        index for index, task in enumerate(tasks)
        if _normalise_text(task.get("id")) == clean_ref
    ]

    if len(id_matches) == 1:
        return id_matches[0], "id", []

    candidates = []

    for index, task in enumerate(tasks):
        if not include_done and task.get("done"):
            continue

        clean_text = _normalise_text(task.get("text"))

        if clean_ref == clean_text:
            return index, "exact_text", []

        if clean_ref in clean_text or clean_text in clean_ref:
            candidates.append(index)

    if len(candidates) == 1:
        return candidates[0], "partial_text", []

    return None, "ambiguous" if candidates else "not_found", candidates


def create_todo_list(reset_existing=False, confirmed=False, open_widget=True):
    """
    Ensures the internal Jarvis to-do list exists. Resetting existing tasks is
    treated as confirmation-required unless explicitly confirmed.
    """

    tasks = _load_tasks()
    reset_existing = bool(reset_existing)
    confirmed = bool(confirmed)

    if reset_existing and tasks and not confirmed:
        return {
            "success": False,
            "needs_confirmation": True,
            "message": "I can reset it, but I need confirmation first.",
            "spoken_message": "I can reset it, but I need confirmation first.",
            "task_count": len(tasks),
        }

    if reset_existing and confirmed:
        tasks = []
        _save_tasks(tasks)

    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": "Your to-do list is ready.",
        "spoken_message": "Your to-do list is ready.",
        "tasks": [_public_task(task, index + 1) for index, task in enumerate(tasks)],
        "task_count": len(tasks),
    }


def add_todo_task(task_text, open_widget=True):
    task_text = str(task_text or "").strip()

    if not task_text:
        return {
            "success": False,
            "message": "What should I add to your to-do list?",
            "spoken_message": "What should I add to your to-do list?",
        }

    tasks = _load_tasks()

    duplicate = next(
        (
            task for task in tasks
            if _normalise_text(task.get("text")) == _normalise_text(task_text)
            and not task.get("done")
        ),
        None,
    )

    if duplicate:
        _sync_widget(tasks, open_widget=bool(open_widget))
        return {
            "success": True,
            "message": "That task is already on your list.",
            "spoken_message": "That task is already on your list.",
            "task": duplicate,
            "duplicate": True,
        }

    task = {
        "id": uuid4().hex,
        "text": task_text,
        "done": False,
        "created_at": _now(),
    }
    tasks.append(task)
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Added {task_text} to your to-do list.",
        "spoken_message": f"Added {task_text} to your to-do list.",
        "task": task,
        "task_count": len(tasks),
    }


def list_todo_tasks(include_completed=False, open_widget=True):
    tasks = _load_tasks()
    include_completed = bool(include_completed)
    visible_tasks = [
        task for task in tasks
        if include_completed or not task.get("done")
    ]

    _sync_widget(tasks, open_widget=bool(open_widget))

    if not visible_tasks:
        return {
            "success": True,
            "message": "Your to-do list is empty.",
            "spoken_message": "Your to-do list is empty.",
            "tasks": [],
            "task_count": 0,
        }

    preview = ", ".join(task.get("text", "") for task in visible_tasks[:3])
    extra_count = max(0, len(visible_tasks) - 3)

    if extra_count:
        spoken = f"You have {len(visible_tasks)} tasks, including {preview}, and {extra_count} more."
    else:
        spoken = f"You have {len(visible_tasks)} tasks: {preview}."

    return {
        "success": True,
        "message": spoken,
        "spoken_message": spoken,
        "tasks": [_public_task(task, index + 1) for index, task in enumerate(tasks)],
        "task_count": len(visible_tasks),
    }


def complete_todo_task(task_ref, open_widget=True):
    tasks = _load_tasks()
    index, match_type, candidates = _match_task(tasks, task_ref, include_done=False)

    if index is None:
        return _task_match_failure(task_ref, tasks, match_type, candidates)

    tasks[index]["done"] = True
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Marked {tasks[index]['text']} as done.",
        "spoken_message": f"Marked {tasks[index]['text']} as done.",
        "task": _public_task(tasks[index], index + 1),
        "match_type": match_type,
    }


def remove_todo_task(task_ref, open_widget=True):
    tasks = _load_tasks()
    index, match_type, candidates = _match_task(tasks, task_ref, include_done=True)

    if index is None:
        return _task_match_failure(task_ref, tasks, match_type, candidates)

    task = tasks.pop(index)
    _save_tasks(tasks)
    _sync_widget(tasks, open_widget=bool(open_widget))

    return {
        "success": True,
        "message": f"Removed {task['text']} from your to-do list.",
        "spoken_message": f"Removed {task['text']} from your to-do list.",
        "removed_task": task,
        "match_type": match_type,
    }


def _task_match_failure(task_ref, tasks, match_type, candidates):
    top_matches = [
        _public_task(tasks[index], index + 1)
        for index in candidates[:3]
        if 0 <= index < len(tasks)
    ]

    if match_type == "ambiguous":
        message = "I found more than one matching task. Which one should I use?"
    else:
        message = "I could not find that task on your to-do list."

    return {
        "success": False,
        "message": message,
        "spoken_message": message,
        "task_ref": task_ref,
        "match_type": match_type,
        "top_matches": top_matches,
    }
