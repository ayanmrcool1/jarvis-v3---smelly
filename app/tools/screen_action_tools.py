import json
import re
import time
import ctypes
from pathlib import Path

import mss
import pyautogui
from PIL import Image, ImageDraw

from tools.screen_tools import (
    encode_image_to_base64,
    get_active_window_info,
    client,
    VISION_MODEL,
)


# =========================
# JARVIS SCREEN ACTION TOOLS
# General screen intelligence + optional clicking
# Multi-monitor + DPI-safe version
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

MIN_CLICK_CONFIDENCE = 0.72
MIN_RETRY_CLICK_CONFIDENCE = 0.68
MIN_VERIFICATION_CONFIDENCE = 0.55
MONITOR_SEAM_BLOCK_PX = 45
SCREEN_EDGE_BLOCK_PX = 8
VERIFY_CLICK_WAIT_SECONDS = 1.25
MAX_CLICK_RETRIES = 1

GENERIC_TARGETS = [
    "",
    "none",
    "null",
    "random video",
    "a random video",
    "video",
    "a video",
    "random option",
    "option",
    "an option",
    "button",
    "link",
    "card",
    "thumbnail",
    "item",
    "visible option",
    "something",
    "one",
    "one of these",
]

DANGEROUS_ACTION_WORDS = [
    "buy",
    "purchase",
    "pay",
    "payment",
    "checkout",
    "order now",
    "place order",
    "confirm order",
    "send",
    "submit",
    "delete",
    "remove",
    "cancel",
    "unsubscribe",
    "confirm",
    "accept",
    "agree",
    "password",
    "bank",
    "card",
]


def _enable_dpi_awareness():
    """
    Makes Windows mouse coordinates match screenshot coordinates more reliably.
    This is very important on multi-monitor setups and monitors using scaling.
    """

    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # Per-monitor DPI aware
        return
    except Exception:
        pass

    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


_enable_dpi_awareness()


def _capture_all_screens_for_action(filename="screen_action_latest.png"):
    """
    Captures the full virtual desktop across ALL monitors.

    mss.sct.monitors[0] is the full combined desktop.
    Coordinates returned by the AI are mapped back to this full screenshot.
    """

    output_path = SCREENSHOT_DIR / filename

    with mss.mss() as sct:
        virtual_monitor = sct.monitors[0]
        screenshot = sct.grab(virtual_monitor)

        image = Image.frombytes(
            "RGB",
            screenshot.size,
            screenshot.rgb,
        )

        image.save(output_path)

        latest_path = SCREENSHOT_DIR / "screen_action_latest.png"

        if output_path != latest_path:
            image.save(latest_path)

        monitors = []

        for index, mon in enumerate(sct.monitors):
            monitors.append(
                {
                    "index": index,
                    "left": int(mon["left"]),
                    "top": int(mon["top"]),
                    "width": int(mon["width"]),
                    "height": int(mon["height"]),
                    "right": int(mon["left"] + mon["width"]),
                    "bottom": int(mon["top"] + mon["height"]),
                }
            )

        return {
            "path": str(output_path),
            "left": int(virtual_monitor["left"]),
            "top": int(virtual_monitor["top"]),
            "width": int(virtual_monitor["width"]),
            "height": int(virtual_monitor["height"]),
            "right": int(virtual_monitor["left"] + virtual_monitor["width"]),
            "bottom": int(virtual_monitor["top"] + virtual_monitor["height"]),
            "monitors": monitors,
        }


def _extract_json(text):
    """
    Extracts JSON even if the model accidentally wraps it in prose/code fences.
    """

    parsed, _parse_error = _extract_json_result(text)
    return parsed


def _strip_json_fences(text):
    cleaned = str(text or "").strip()
    cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.I).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    return cleaned


def _find_first_json_object_text(text):
    start = text.find("{")

    if start < 0:
        return ""

    depth = 0
    in_string = False
    escape = False

    for index in range(start, len(text)):
        char = text[index]

        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1

            if depth == 0:
                return text[start : index + 1]

    return text[start:]


def _repair_json_text(text):
    repaired = str(text or "").strip()
    repaired = re.sub(r",\s*$", "", repaired)
    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)

    stack = []
    in_string = False
    escape = False

    for char in repaired:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char in "{[":
            stack.append(char)
        elif char == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif char == "]" and stack and stack[-1] == "[":
            stack.pop()

    if in_string:
        repaired = repaired.rstrip("\\") + '"'

    while stack:
        opener = stack.pop()
        repaired += "}" if opener == "{" else "]"

    repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
    return repaired


def _extract_object_after_key(text, key):
    match = re.search(rf'"{re.escape(key)}"\s*:', text)

    if not match:
        return None

    remainder = text[match.end() :]
    object_text = _find_first_json_object_text(remainder)

    if not object_text:
        return None

    try:
        return json.loads(object_text)
    except Exception:
        try:
            return json.loads(_repair_json_text(object_text))
        except Exception:
            return None


def _extract_first_candidate_object(text):
    match = re.search(r'"candidates"\s*:\s*\[', text)

    if not match:
        return None

    remainder = text[match.end() :]
    object_text = _find_first_json_object_text(remainder)

    if not object_text:
        return None

    try:
        return json.loads(object_text)
    except Exception:
        try:
            return json.loads(_repair_json_text(object_text))
        except Exception:
            return None


def _extract_string_field(text, key, default=""):
    match = re.search(rf'"{re.escape(key)}"\s*:\s*"([^"]*)"', text)
    return match.group(1).strip() if match else default


def _extract_bool_field(text, key, default=False):
    match = re.search(rf'"{re.escape(key)}"\s*:\s*(true|false)', text, flags=re.I)

    if not match:
        return default

    return match.group(1).lower() == "true"


def _extract_number_field(text, key, default=0.0):
    match = re.search(rf'"{re.escape(key)}"\s*:\s*(-?\d+(?:\.\d+)?)', text)

    if not match:
        return default

    try:
        return float(match.group(1))
    except Exception:
        return default


def _extract_partial_plan(text, parse_error):
    selected = _extract_object_after_key(text, "selected_candidate")

    if not isinstance(selected, dict):
        selected = _extract_first_candidate_object(text)

    if not isinstance(selected, dict):
        return None

    action = _extract_string_field(text, "action", "click") or "click"
    message = _extract_string_field(text, "message", "")
    target = _extract_string_field(text, "target", "") or _candidate_label(selected)
    confidence = _extract_number_field(
        text,
        "confidence",
        _candidate_confidence(selected),
    )

    plan = {
        "success": _extract_bool_field(text, "success", True),
        "action": action,
        "message": message or "I found a visible target.",
        "target": target,
        "target_type": _extract_string_field(text, "target_type", _candidate_type(selected)),
        "reason": _extract_string_field(text, "reason", selected.get("reason", "")),
        "confidence": confidence,
        "selection_reason": _extract_string_field(text, "selection_reason", ""),
        "unsafe": _extract_bool_field(text, "unsafe", False),
        "selected_candidate": selected,
        "candidates": [selected],
        "rejected_candidates": [],
        "_parse_repaired": True,
        "_parse_error": parse_error,
    }

    return plan


def _extract_json_result(text):
    if not text:
        return None, "empty response"

    cleaned = _strip_json_fences(text)

    try:
        return json.loads(cleaned), None
    except Exception as error:
        parse_error = str(error)

    object_text = _find_first_json_object_text(cleaned)

    if object_text:
        try:
            return json.loads(object_text), None
        except Exception as error:
            parse_error = str(error)

        repaired = _repair_json_text(object_text)

        try:
            parsed = json.loads(repaired)
            parsed["_parse_repaired"] = True
            parsed["_parse_error"] = parse_error
            return parsed, parse_error
        except Exception as error:
            parse_error = str(error)

    partial = _extract_partial_plan(cleaned, parse_error)

    if partial:
        return partial, parse_error

    return None, parse_error


def _instruction_has_dangerous_action(instruction):
    clean = (instruction or "").lower()
    return any(word in clean for word in DANGEROUS_ACTION_WORDS)


def _looks_generic_target(target):
    clean = str(target or "").lower().strip()
    clean = clean.replace('"', "").replace("'", "").strip()

    if clean in GENERIC_TARGETS:
        return True

    if len(clean) < 4:
        return True

    if clean.startswith("random ") and len(clean.split()) <= 3:
        return True

    return False


def _clamp(value, minimum, maximum):
    return max(minimum, min(maximum, value))


def _optional_bool(value):
    if isinstance(value, bool):
        return value

    if value is None:
        return None

    clean = str(value).strip().lower()

    if clean in ["true", "yes", "1"]:
        return True

    if clean in ["false", "no", "0"]:
        return False

    return None


def _is_lazy_center_click(screen_info, x, y):
    """
    Blocks the classic bad AI move where it clicks the middle of the screenshot.
    """

    width = screen_info["width"]
    height = screen_info["height"]

    center_x = width / 2
    center_y = height / 2

    tolerance_x = width * 0.055
    tolerance_y = height * 0.055

    return abs(x - center_x) <= tolerance_x and abs(y - center_y) <= tolerance_y


def _is_near_monitor_seam(screen_info, x):
    """
    Blocks clicks too close to monitor boundaries.
    This prevents Jarvis clicking between screens.
    """

    virtual_left = screen_info["left"]

    for monitor in screen_info["monitors"]:
        if monitor["index"] == 0:
            continue

        left_boundary = monitor["left"] - virtual_left
        right_boundary = monitor["right"] - virtual_left

        if abs(x - left_boundary) <= MONITOR_SEAM_BLOCK_PX:
            return True

        if abs(x - right_boundary) <= MONITOR_SEAM_BLOCK_PX:
            return True

    return False


def _normalise_axis_to_pixel(value, maximum, explicit_units=None):
    """
    Converts fractions, percentages, legacy 0-1000 units, or pixels to pixels.
    """

    if value is None:
        return None, "missing"

    try:
        number = float(value)
    except Exception:
        return None, "invalid"

    units = str(explicit_units or "").lower().replace("-", "_").strip()

    if units and units not in ["pixel", "pixels", "px"]:
        if 0 <= number <= 1:
            return int(round(number * (maximum - 1))), "fraction_0_1"

        if 1 < number <= 100:
            return int(round((number / 100.0) * (maximum - 1))), "percent_0_100"

    if units in ["fraction", "fraction_0_1", "0_1"]:
        if 0 <= number <= 1:
            return int(round(number * (maximum - 1))), "fraction_0_1"
        return None, "invalid_fraction_0_1"

    if units in ["percent", "percentage", "percent_0_100", "0_100"]:
        if 0 <= number <= 100:
            return int(round((number / 100.0) * (maximum - 1))), "percent_0_100"
        return None, "invalid_percent_0_100"

    if units in ["normalised", "normalized", "normalised_0_1000", "normalized_0_1000", "0_1000"]:
        if 0 <= number <= 1000:
            return int(round((number / 1000.0) * (maximum - 1))), "normalized_0_1000"
        return None, "invalid_normalized_0_1000"

    if units in ["pixel", "pixels", "px"]:
        if 0 <= number < maximum:
            return int(round(number)), "pixel"
        return None, "invalid_pixel"

    if 0 <= number <= 1:
        return int(round(number * (maximum - 1))), "auto_fraction_0_1"

    if 1 < number <= 100:
        return int(round((number / 100.0) * (maximum - 1))), "auto_percent_0_100"

    if 100 < number <= 1000:
        return int(round((number / 1000.0) * (maximum - 1))), "auto_normalized_0_1000"

    if 0 <= number < maximum:
        return int(round(number)), "auto_pixel"

    return None, "out_of_range"


def _get_click_pixels(plan, screen_info):
    """
    Supports preferred normalised 0-1000 coords, with fallback to raw pixels.
    Normalised coords are more reliable because the vision model may view a resized image.
    """

    width = screen_info["width"]
    height = screen_info["height"]

    coordinate_units = plan.get("coordinate_units") or plan.get("units")

    click_x_pct = plan.get("click_x_pct", plan.get("click_x_norm"))
    click_y_pct = plan.get("click_y_pct", plan.get("click_y_norm"))

    if click_x_pct is not None and click_y_pct is not None:
        x, x_units = _normalise_axis_to_pixel(click_x_pct, width, coordinate_units)
        y, y_units = _normalise_axis_to_pixel(click_y_pct, height, coordinate_units)

        if x is None or y is None:
            return None, None, "invalid", f"{x_units}/{y_units}"

        return (
            x,
            y,
            "normalised",
            x_units if x_units == y_units else f"{x_units}/{y_units}",
        )

    click_x = plan.get("click_x")
    click_y = plan.get("click_y")

    if click_x is None or click_y is None:
        return None, None, "missing", "missing"

    if coordinate_units:
        x, x_units = _normalise_axis_to_pixel(click_x, width, coordinate_units)
        y, y_units = _normalise_axis_to_pixel(click_y, height, coordinate_units)

        if x is None or y is None:
            return None, None, "invalid", f"{x_units}/{y_units}"

        return (
            x,
            y,
            "normalised" if "pixel" not in f"{x_units}/{y_units}" else "pixel",
            x_units if x_units == y_units else f"{x_units}/{y_units}",
        )

    try:
        raw_x = float(click_x)
        raw_y = float(click_y)
    except Exception:
        return None, None, "invalid", "invalid"

    if 0 <= raw_x <= 1 and 0 <= raw_y <= 1:
        x, x_units = _normalise_axis_to_pixel(raw_x, width)
        y, y_units = _normalise_axis_to_pixel(raw_y, height)
        return x, y, "normalised", x_units if x_units == y_units else f"{x_units}/{y_units}"

    if 1 < raw_x <= 100 and 1 < raw_y <= 100:
        x, x_units = _normalise_axis_to_pixel(raw_x, width)
        y, y_units = _normalise_axis_to_pixel(raw_y, height)
        return x, y, "normalised", x_units if x_units == y_units else f"{x_units}/{y_units}"

    if 0 <= raw_x < width and 0 <= raw_y < height:
        return int(round(raw_x)), int(round(raw_y)), "pixel", "pixel"

    return None, None, "invalid", "out_of_range"


def _candidate_label(candidate):
    return (
        candidate.get("target")
        or candidate.get("label")
        or candidate.get("text")
        or candidate.get("title")
        or candidate.get("description")
        or ""
    )


def _candidate_type(candidate):
    return (
        candidate.get("target_type")
        or candidate.get("type")
        or candidate.get("role")
        or "unknown"
    )


def _candidate_confidence(candidate, fallback=0.0):
    try:
        return float(candidate.get("confidence", fallback) or fallback)
    except Exception:
        return float(fallback or 0.0)


def _get_bbox_pixels(candidate, screen_info):
    width = screen_info["width"]
    height = screen_info["height"]
    coordinate_units = candidate.get("coordinate_units") or candidate.get("bbox_units")
    values_are_scaled = bool(coordinate_units)

    bbox = (
        candidate.get("bbox")
        or candidate.get("bounding_box")
        or candidate.get("clickable_region")
    )

    values = None

    if isinstance(bbox, dict):
        left = bbox.get("left", bbox.get("x"))
        top = bbox.get("top", bbox.get("y"))
        right = bbox.get("right")
        bottom = bbox.get("bottom")
        box_width = bbox.get("width", bbox.get("w"))
        box_height = bbox.get("height", bbox.get("h"))

        if right is None and left is not None and box_width is not None:
            right = float(left) + float(box_width)

        if bottom is None and top is not None and box_height is not None:
            bottom = float(top) + float(box_height)

        if left is not None and top is not None and right is not None and bottom is not None:
            values = [float(left), float(top), float(right), float(bottom)]

    elif isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        x1, y1, third, fourth = [float(item) for item in bbox[:4]]

        # Treat list form as x, y, width, height.
        values = [x1, y1, x1 + third, y1 + fourth]

    explicit_left = candidate.get("bbox_left_pct")
    explicit_top = candidate.get("bbox_top_pct")
    explicit_right = candidate.get("bbox_right_pct")
    explicit_bottom = candidate.get("bbox_bottom_pct")
    explicit_x = candidate.get("bbox_x_pct")
    explicit_y = candidate.get("bbox_y_pct")
    explicit_w = candidate.get("bbox_w_pct")
    explicit_h = candidate.get("bbox_h_pct")

    if (
        explicit_x is not None
        and explicit_y is not None
        and explicit_w is not None
        and explicit_h is not None
    ):
        values_are_scaled = True
        explicit_left = float(explicit_x)
        explicit_top = float(explicit_y)
        explicit_right = float(explicit_x) + float(explicit_w)
        explicit_bottom = float(explicit_y) + float(explicit_h)

    if (
        explicit_left is not None
        and explicit_top is not None
        and explicit_right is not None
        and explicit_bottom is not None
    ):
        values_are_scaled = True
        values = [
            float(explicit_left),
            float(explicit_top),
            float(explicit_right),
            float(explicit_bottom),
        ]

    if not values:
        return None

    if values_are_scaled or all(0 <= value <= 1 for value in values) or all(0 <= value <= 100 for value in values):
        left, _left_units = _normalise_axis_to_pixel(values[0], width, coordinate_units)
        top, _top_units = _normalise_axis_to_pixel(values[1], height, coordinate_units)
        right, _right_units = _normalise_axis_to_pixel(values[2], width, coordinate_units)
        bottom, _bottom_units = _normalise_axis_to_pixel(values[3], height, coordinate_units)

        if None in [left, top, right, bottom]:
            return None
    else:
        left, top, right, bottom = [int(round(value)) for value in values]

    left = int(_clamp(left, 0, width - 1))
    right = int(_clamp(right, 0, width - 1))
    top = int(_clamp(top, 0, height - 1))
    bottom = int(_clamp(bottom, 0, height - 1))

    if right <= left or bottom <= top:
        return None

    return {
        "left": left,
        "top": top,
        "right": right,
        "bottom": bottom,
        "width": right - left,
        "height": bottom - top,
    }


def _get_candidate_click_pixels(candidate, screen_info):
    click_x, click_y, coordinate_mode, coordinate_units = _get_click_pixels(candidate, screen_info)

    if click_x is not None and click_y is not None:
        return click_x, click_y, coordinate_mode, coordinate_units

    bbox = _get_bbox_pixels(candidate, screen_info)

    if not bbox:
        return None, None, "missing", "missing"

    return (
        int((bbox["left"] + bbox["right"]) / 2),
        int((bbox["top"] + bbox["bottom"]) / 2),
        "bbox_center",
        candidate.get("coordinate_units") or candidate.get("bbox_units") or "bbox",
    )


def _candidate_debug(candidate):
    return {
        "target": _candidate_label(candidate),
        "target_type": _candidate_type(candidate),
        "confidence": _candidate_confidence(candidate),
        "reason": candidate.get("reason"),
        "click_x_pct": candidate.get("click_x_pct"),
        "click_y_pct": candidate.get("click_y_pct"),
        "click_x_norm": candidate.get("click_x_norm"),
        "click_y_norm": candidate.get("click_y_norm"),
        "click_x": candidate.get("click_x"),
        "click_y": candidate.get("click_y"),
        "coordinate_units": candidate.get("coordinate_units") or candidate.get("units"),
        "bbox": (
            candidate.get("bbox")
            or candidate.get("bounding_box")
            or candidate.get("clickable_region")
        ),
    }


def _candidate_key(candidate):
    label = str(_candidate_label(candidate)).lower().strip()
    click_x = candidate.get("click_x_pct", candidate.get("click_x_norm", candidate.get("click_x")))
    click_y = candidate.get("click_y_pct", candidate.get("click_y_norm", candidate.get("click_y")))
    units = candidate.get("coordinate_units") or candidate.get("units")
    return label, str(click_x), str(click_y), str(units)


def _normalise_click_candidates(plan):
    candidates = []
    seen = set()
    selected_candidate = plan.get("selected_candidate")

    def add_candidate(candidate):
        if not isinstance(candidate, dict):
            return

        key = _candidate_key(candidate)

        if key in seen:
            return

        seen.add(key)
        candidates.append(candidate)

    plan_candidate = {
        "target": plan.get("target"),
        "target_type": plan.get("target_type"),
        "reason": plan.get("reason"),
        "confidence": plan.get("confidence"),
        "click_x_pct": plan.get("click_x_pct"),
        "click_y_pct": plan.get("click_y_pct"),
        "click_x_norm": plan.get("click_x_norm"),
        "click_y_norm": plan.get("click_y_norm"),
        "click_x": plan.get("click_x"),
        "click_y": plan.get("click_y"),
        "coordinate_units": plan.get("coordinate_units") or plan.get("units"),
        "bbox": plan.get("bbox"),
        "bbox_left_pct": plan.get("bbox_left_pct"),
        "bbox_top_pct": plan.get("bbox_top_pct"),
        "bbox_right_pct": plan.get("bbox_right_pct"),
        "bbox_bottom_pct": plan.get("bbox_bottom_pct"),
        "bbox_x_pct": plan.get("bbox_x_pct"),
        "bbox_y_pct": plan.get("bbox_y_pct"),
        "bbox_w_pct": plan.get("bbox_w_pct"),
        "bbox_h_pct": plan.get("bbox_h_pct"),
    }

    if isinstance(selected_candidate, dict):
        add_candidate(selected_candidate)
    elif not selected_candidate:
        add_candidate(plan_candidate)

    for candidate in plan.get("candidates") or []:
        add_candidate(candidate)

    add_candidate(plan_candidate)

    if isinstance(selected_candidate, str):
        selected_text = selected_candidate.lower().strip()
        candidates.sort(
            key=lambda item: selected_text not in str(_candidate_label(item)).lower()
        )

    return candidates[:3]


def _is_near_screen_edge(screen_info, x, y):
    return (
        x <= SCREEN_EDGE_BLOCK_PX
        or y <= SCREEN_EDGE_BLOCK_PX
        or x >= screen_info["width"] - SCREEN_EDGE_BLOCK_PX
        or y >= screen_info["height"] - SCREEN_EDGE_BLOCK_PX
    )


def _matches_failed_click(candidate, x, y, failed_clicks):
    label = str(_candidate_label(candidate)).lower().strip()

    for failed in failed_clicks:
        failed_x = failed.get("click_x")
        failed_y = failed.get("click_y")
        failed_label = str(failed.get("target") or "").lower().strip()

        if failed_x is not None and failed_y is not None:
            if abs(x - int(failed_x)) <= 22 and abs(y - int(failed_y)) <= 22:
                return True

        if label and failed_label and label == failed_label:
            if failed_x is None or failed_y is None:
                return True

            if abs(x - int(failed_x)) <= 50 and abs(y - int(failed_y)) <= 50:
                return True

    return False


def _prepare_click_candidate(candidate, screen_info, failed_clicks, min_confidence):
    target = _candidate_label(candidate)
    confidence = _candidate_confidence(candidate)
    click_x, click_y, coordinate_mode, coordinate_units = _get_candidate_click_pixels(candidate, screen_info)
    rejected_reason = None

    if _looks_generic_target(target):
        rejected_reason = "The target label was too generic."
    elif confidence < min_confidence:
        rejected_reason = "The target confidence was too low."
    elif click_x is None or click_y is None:
        rejected_reason = "No reliable click point was available."
    else:
        click_x = int(click_x)
        click_y = int(click_y)

        if _is_lazy_center_click(screen_info, click_x, click_y):
            rejected_reason = "The click point looked like a generic centre-screen click."
        elif _is_near_monitor_seam(screen_info, click_x):
            rejected_reason = "The click point was too close to a monitor seam."
        elif _is_near_screen_edge(screen_info, click_x, click_y) and confidence < 0.9:
            rejected_reason = "The click point was too close to the screen edge."
        elif _matches_failed_click(candidate, click_x, click_y, failed_clicks):
            rejected_reason = "This target or coordinate already failed."

    if rejected_reason:
        return {
            "valid": False,
            "reason": rejected_reason,
            "candidate": _candidate_debug(candidate),
        }

    bbox = _get_bbox_pixels(candidate, screen_info)

    return {
        "valid": True,
        "candidate": candidate,
        "target": target,
        "target_type": _candidate_type(candidate),
        "reason": candidate.get("reason"),
        "confidence": confidence,
        "coordinate_mode": coordinate_mode,
        "coordinate_units": coordinate_units,
        "click_x": int(click_x),
        "click_y": int(click_y),
        "bbox": bbox,
        "debug": _candidate_debug(candidate),
    }


def _verification_passed(verification):
    if verification.get("success") is not True:
        return False

    if verification.get("changed") is False:
        return False

    try:
        confidence = float(verification.get("confidence") or 0.0)
    except Exception:
        confidence = 0.0

    return confidence >= MIN_VERIFICATION_CONFIDENCE


def _natural_click_failure_message(verification=None, retried=False):
    reason = str((verification or {}).get("reason") or "").lower()

    if "nothing" in reason or "no relevant" in reason or "same" in reason:
        return "I clicked it, but it didn't look like anything changed."

    if retried:
        return "I tried, but I’m not confident that worked."

    return "That didn't seem to open. I can try another visible option."


def _record_failed_click(prepared, verification, after_path):
    return {
        "target": prepared.get("target"),
        "target_type": prepared.get("target_type"),
        "click_x": prepared.get("click_x"),
        "click_y": prepared.get("click_y"),
        "coordinate_units": prepared.get("coordinate_units"),
        "failure_reason": (verification or {}).get("reason"),
        "timestamp": time.time(),
        "screenshot_path": after_path,
    }


def _attempt_click_candidate(prepared, screen_info, instruction, before_path, attempt_number):
    debug_filename = f"screen_action_click_debug_{int(time.time() * 1000)}_{attempt_number}.png"
    absolute_x, absolute_y, debug_path = _safe_click(
        screen_info,
        prepared["click_x"],
        prepared["click_y"],
        prepared["target"],
        debug_filename=debug_filename,
    )

    time.sleep(VERIFY_CLICK_WAIT_SECONDS)
    after_info = _capture_all_screens_for_action(
        f"screen_action_after_click_{int(time.time() * 1000)}_{attempt_number}.png"
    )
    after_path = after_info["path"]

    verification = _verify_click_result(
        instruction=instruction,
        target=prepared["target"],
        before_path=before_path,
        after_path=after_path,
    )

    return {
        "attempt_number": attempt_number,
        "target": prepared["target"],
        "target_type": prepared["target_type"],
        "reason": prepared.get("reason"),
        "confidence": prepared["confidence"],
        "coordinate_mode": prepared["coordinate_mode"],
        "coordinate_units": prepared["coordinate_units"],
        "click_x": prepared["click_x"],
        "click_y": prepared["click_y"],
        "absolute_x": absolute_x,
        "absolute_y": absolute_y,
        "bbox": prepared.get("bbox"),
        "after_screenshot_path": after_path,
        "click_debug_path": debug_path,
        "verification": verification,
    }


def _save_click_debug_image(screen_info, x, y, target, filename="screen_action_click_debug.png"):
    """
    Saves a debug screenshot with a red marker showing where Jarvis intended to click.
    """

    try:
        image_path = screen_info["path"]
        debug_path = SCREENSHOT_DIR / filename

        image = Image.open(image_path).convert("RGB")
        draw = ImageDraw.Draw(image)

        radius = 22

        draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            outline="red",
            width=6,
        )

        draw.line((x - 34, y, x + 34, y), fill="red", width=4)
        draw.line((x, y - 34, x, y + 34), fill="red", width=4)

        label = str(target or "target")[:100]
        draw.text((x + 28, y + 28), label, fill="red")

        # Draw monitor boundaries so we can see if the click was near a seam.
        virtual_left = screen_info["left"]
        virtual_top = screen_info["top"]

        for monitor in screen_info["monitors"]:
            if monitor["index"] == 0:
                continue

            left = monitor["left"] - virtual_left
            top = monitor["top"] - virtual_top
            right = left + monitor["width"]
            bottom = top + monitor["height"]

            draw.rectangle(
                (left, top, right, bottom),
                outline="yellow",
                width=4,
            )

            draw.text(
                (left + 12, top + 12),
                f"Monitor {monitor['index']}",
                fill="yellow",
            )

        image.save(debug_path)

        return str(debug_path)

    except Exception:
        return None


def _safe_click(screen_info, x, y, target, debug_filename="screen_action_click_debug.png"):
    """
    Clicks a coordinate relative to the full virtual desktop screenshot.
    Supports multi-monitor setups.
    """

    width = screen_info["width"]
    height = screen_info["height"]

    x = int(_clamp(int(x), 0, width - 1))
    y = int(_clamp(int(y), 0, height - 1))

    debug_path = _save_click_debug_image(screen_info, x, y, target, filename=debug_filename)

    absolute_x = int(screen_info["left"] + x)
    absolute_y = int(screen_info["top"] + y)

    pyautogui.moveTo(absolute_x, absolute_y, duration=0.15)
    time.sleep(0.10)
    pyautogui.click(absolute_x, absolute_y)

    return absolute_x, absolute_y, debug_path


def _verify_click_result(instruction, target, before_path, after_path):
    """
    Uses the vision model to check whether a click appears to have produced the
    intended visible result. This is generic and intentionally not site-specific.
    """

    try:
        before_image = encode_image_to_base64(before_path)
        after_image = encode_image_to_base64(after_path)

        prompt = f"""
You are verifying whether a mouse click by JARVIS succeeded.

Original user instruction:
{instruction}

Intended visible target:
{target}

You will receive a before screenshot and an after screenshot.

Decide whether the after screenshot shows clear evidence that the user's intended action worked.
For open/play/select/click item actions, success requires evidence that the target opened, became active/selected, playback started, a detail/player view appeared, or the intended item became prominent.
If the after screenshot still looks like the same list/grid/page and the intended item is not clearly open or active, mark success false.
If the click missed, only caused a tiny hover/focus change, nothing relevant changed, the wrong thing opened, or the result is unclear, mark success false.
Do not assume success just because a click was attempted.

Return ONLY valid JSON:
{{
  "success": true,
  "changed": true,
  "message": "short natural response",
  "reason": "brief verification reason",
  "confidence": 0.0
}}
"""

        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{before_image}",
                                "detail": "low",
                            },
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{after_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            temperature=0.05,
            max_tokens=260,
        )

        raw_text = response.choices[0].message.content.strip()
        result = _extract_json(raw_text)

        if not result:
            return {
                "success": None,
                "changed": None,
                "message": "I clicked it, but I could not verify the result.",
                "reason": "Verification response was not valid JSON.",
                "confidence": 0.0,
                "raw_response": raw_text,
            }

        return {
            "success": _optional_bool(result.get("success")),
            "changed": _optional_bool(result.get("changed")),
            "message": (result.get("message") or "").strip(),
            "reason": (result.get("reason") or "").strip(),
            "confidence": float(result.get("confidence") or 0.0),
            "raw_response": raw_text,
        }

    except Exception as error:
        return {
            "success": None,
            "changed": None,
            "message": "I clicked it, but I could not verify the result.",
            "reason": str(error),
            "confidence": 0.0,
        }


def _active_window_prompt_block(active_window, screen_info):
    if not active_window.get("success"):
        return "Active window: unavailable"

    left = active_window.get("left")
    top = active_window.get("top")
    width = active_window.get("width")
    height = active_window.get("height")

    if left is None or top is None or width is None or height is None:
        return f"""
Active window title:
{active_window.get("title")}
"""

    relative_left = int(left - screen_info["left"])
    relative_top = int(top - screen_info["top"])

    return f"""
Active window title:
{active_window.get("title")}

Active window bounds in screenshot coordinates:
left={relative_left}, top={relative_top}, width={width}, height={height}
"""


def act_on_screen(instruction, allow_click=False):
    """
    General AI-first screen action tool.

    Handles natural requests involving visible content:
    - play something from this page
    - choose one of these options
    - click/open/select something visible
    - what should I order
    - decide for me from the screen
    """

    instruction = (instruction or "").strip()

    if not instruction:
        return {
            "success": False,
            "message": "What do you want me to do on the screen?",
        }

    try:
        screen_info = _capture_all_screens_for_action(
            f"screen_action_before_{int(time.time() * 1000)}.png"
        )
        image_path = screen_info["path"]
        base64_image = encode_image_to_base64(image_path)
        active_window = get_active_window_info()

        dangerous = _instruction_has_dangerous_action(instruction)
        active_window_block = _active_window_prompt_block(active_window, screen_info)
        monitor_layout = json.dumps(screen_info["monitors"], separators=(",", ":"))

        prompt = f"""
You are JARVIS, a local Windows assistant with vision and limited mouse control.

The screenshot shows the user's FULL virtual desktop across ALL monitors.
The screenshot coordinate system starts at the top-left of the full combined screenshot.

The user gave this natural instruction:
{instruction}

{active_window_block}

Full screenshot size:
width={screen_info["width"]}, height={screen_info["height"]}

Monitor layout:
{monitor_layout}

Can you click if appropriate?
{allow_click}

Dangerous action detected by safety filter?
{dangerous}

Your job:
- Understand the user's intent from natural speech, not exact keywords.
- Look at the screenshot carefully.
- If the user refers to "this page", "from here", "what I'm looking at", or "on my screen", use the visible content.
- Decide whether to answer, recommend, ask for clarification, or click.

Clicking rules:
- Only click if the user clearly wants you to physically open/play/select/click something.
- Only click a REAL visible target.
- For vague instructions like choosing a random item, selecting one result, or playing a visible item, identify multiple real visible candidates if possible.
- Candidate targets must be actual visible clickable objects: buttons, links, cards, thumbnails, titles, inputs, menu items, or similar UI elements.
- Do not return generic labels like "video", "button", "card", "item", or "random option" as the target. Use the actual visible text or a specific visual description.
- Do NOT click between monitors.
- Do NOT click the centre of the full screenshot unless an actual visible target is centred there.
- Do NOT click blank space, page background, random coordinates, or generic areas.
- Do NOT click if the target is only described as "random video", "video", "option", "button", or "item".
- If you cannot identify a real clickable target, ask or recommend instead of clicking.

Coordinate rules:
- Use 0-1000 normalized coordinates relative to the FULL screenshot.
- Set coordinate_units to "normalized_0_1000".
- Example: far left = 0, centre = 500, far right = 1000.
- Put the preferred click point in click_x_pct and click_y_pct.
- Only use raw click_x/click_y if coordinate_units is "pixel" and you are highly confident.
- Click inside the actual visible clickable object, preferably the centre of its clickable region.
- If possible, provide an approximate bounding box for the clickable target.
- Do not place the click point in whitespace between adjacent elements.

Safety:
- If the request involves buying, paying, deleting, sending, confirming, accepting, submitting, passwords, banking, or irreversible actions, do not click.

Return ONLY compact valid JSON. No markdown, no prose, no code fence.
Use at most 3 candidates and keep strings short.
Format:
{{
  "success": true,
  "action": "answer|recommend|click|ask",
  "message": "short natural response",
  "target": "specific visible target label",
  "target_type": "button|link|card|thumbnail|title|input|menu item|other",
  "reason": "brief reason",
  "confidence": 0.0,
  "selection_reason": "brief selection reason",
  "coordinate_units": "normalized_0_1000",
  "bbox_left_pct": null,
  "bbox_top_pct": null,
  "bbox_right_pct": null,
  "bbox_bottom_pct": null,
  "click_x_pct": null,
  "click_y_pct": null,
  "unsafe": false,
  "selected_candidate": {{
    "target": "specific visible target label",
    "target_type": "button|link|card|thumbnail|title|input|menu item|other",
    "reason": "short",
    "confidence": 0.0,
    "coordinate_units": "normalized_0_1000",
    "bbox_left_pct": null,
    "bbox_top_pct": null,
    "bbox_right_pct": null,
    "bbox_bottom_pct": null,
    "click_x_pct": null,
    "click_y_pct": null
  }},
  "candidates": [
    {{
      "target": "specific visible target label",
      "target_type": "button|link|card|thumbnail|title|input|menu item|other",
      "reason": "short",
      "confidence": 0.0,
      "coordinate_units": "normalized_0_1000",
      "bbox_left_pct": null,
      "bbox_top_pct": null,
      "bbox_right_pct": null,
      "bbox_bottom_pct": null,
      "click_x_pct": null,
      "click_y_pct": null
    }}
  ],
  "rejected_candidates": [
    {{
      "target": "label/description",
      "reason": "why rejected"
    }}
  ]
}}

Important:
- For click action, provide click_x_pct and click_y_pct whenever possible.
- For click action, include 1 to 3 candidates when there is more than one plausible visible target.
- selected_candidate must repeat the selected candidate object.
- For answer/recommend/ask, all click coordinates must be null.
- Keep the spoken message concise.
"""

        response = client.chat.completions.create(
            model=VISION_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt,
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                                "detail": "high",
                            },
                        },
                    ],
                }
            ],
            temperature=0.10,
            max_tokens=700,
        )

        raw_text = response.choices[0].message.content.strip()
        plan, parse_error = _extract_json_result(raw_text)

        if not plan:
            return {
                "success": False,
                "message": "I looked, but I couldn't pick a reliable target.",
                "parse_error": parse_error,
                "raw_response": raw_text,
                "screenshot_path": image_path,
            }

        action = str(plan.get("action", "answer")).lower().strip()
        message = (plan.get("message") or "").strip()
        target = plan.get("target")
        reason = plan.get("reason")
        confidence = float(plan.get("confidence") or 0.0)
        unsafe = bool(plan.get("unsafe")) or dangerous

        if not message:
            message = "I’ve checked the screen."

        if action == "click":
            if unsafe:
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I can help choose, but I won’t click that without confirmation.",
                    "target": target,
                    "reason": reason,
                    "confidence": confidence,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            if not allow_click:
                return {
                    "success": True,
                    "clicked": False,
                    "action": "recommend",
                    "message": message,
                    "target": target,
                    "reason": reason,
                    "confidence": confidence,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            candidates = _normalise_click_candidates(plan)
            candidate_debug = [_candidate_debug(candidate) for candidate in candidates]
            rejected_candidates = list(plan.get("rejected_candidates") or [])
            failed_clicks = []
            click_attempts = []

            prepared_candidates = []

            for candidate in candidates:
                prepared = _prepare_click_candidate(
                    candidate,
                    screen_info,
                    failed_clicks,
                    MIN_CLICK_CONFIDENCE,
                )

                if prepared.get("valid"):
                    prepared_candidates.append(prepared)
                else:
                    rejected_candidates.append(prepared)

            if not prepared_candidates:
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I can see the screen, but I need a clearer clickable target.",
                    "target": target,
                    "reason": "No candidate had a safe, specific click point.",
                    "confidence": confidence,
                    "candidates": candidate_debug,
                    "selected_candidate": None,
                    "rejected_candidates": rejected_candidates,
                    "selection_reason": plan.get("selection_reason"),
                    "raw_plan": plan,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            selected = prepared_candidates[0]
            attempt = _attempt_click_candidate(
                selected,
                screen_info,
                instruction,
                image_path,
                attempt_number=1,
            )
            click_attempts.append(attempt)
            verification = attempt["verification"]

            if _verification_passed(verification):
                verification_message = (verification.get("message") or "").strip()

                return {
                    "success": True,
                    "clicked": True,
                    "click_attempted": True,
                    "retried": False,
                    "action": "click",
                    "message": verification_message or message,
                    "target": selected["target"],
                    "target_type": selected["target_type"],
                    "reason": selected.get("reason") or reason,
                    "confidence": selected["confidence"],
                    "coordinate_mode": selected["coordinate_mode"],
                    "coordinate_units": selected["coordinate_units"],
                    "click_x": selected["click_x"],
                    "click_y": selected["click_y"],
                    "absolute_x": attempt["absolute_x"],
                    "absolute_y": attempt["absolute_y"],
                    "bbox": selected.get("bbox"),
                    "before_screenshot_path": image_path,
                    "after_screenshot_path": attempt["after_screenshot_path"],
                    "screenshot_path": image_path,
                    "click_debug_path": attempt["click_debug_path"],
                    "verification_result": verification.get("success"),
                    "verification_reason": verification.get("reason"),
                    "verification_confidence": verification.get("confidence"),
                    "candidates": candidate_debug,
                    "selected_candidate": selected["debug"],
                    "rejected_candidates": rejected_candidates,
                    "selection_reason": plan.get("selection_reason"),
                    "click_attempts": click_attempts,
                    "failed_clicks": failed_clicks,
                    "screen_left": screen_info["left"],
                    "screen_top": screen_info["top"],
                    "screen_width": screen_info["width"],
                    "screen_height": screen_info["height"],
                    "monitors": screen_info["monitors"],
                    "raw_plan": plan,
                    "verification_raw": verification,
                    "model": VISION_MODEL,
                }

            failed_clicks.append(
                _record_failed_click(
                    selected,
                    verification,
                    attempt["after_screenshot_path"],
                )
            )

            retry_attempt = None
            can_retry = verification.get("changed") is not True

            if MAX_CLICK_RETRIES > 0 and can_retry:
                for candidate in candidates:
                    retry_candidate = _prepare_click_candidate(
                        candidate,
                        screen_info,
                        failed_clicks,
                        MIN_RETRY_CLICK_CONFIDENCE,
                    )

                    if retry_candidate.get("valid"):
                        retry_attempt = _attempt_click_candidate(
                            retry_candidate,
                            screen_info,
                            instruction,
                            image_path,
                            attempt_number=2,
                        )
                        click_attempts.append(retry_attempt)
                        retry_verification = retry_attempt["verification"]

                        if _verification_passed(retry_verification):
                            retry_message = (retry_verification.get("message") or "").strip()

                            return {
                                "success": True,
                                "clicked": True,
                                "click_attempted": True,
                                "retried": True,
                                "action": "click",
                                "message": retry_message or "That one worked.",
                                "target": retry_candidate["target"],
                                "target_type": retry_candidate["target_type"],
                                "reason": retry_candidate.get("reason") or reason,
                                "confidence": retry_candidate["confidence"],
                                "coordinate_mode": retry_candidate["coordinate_mode"],
                                "coordinate_units": retry_candidate["coordinate_units"],
                                "click_x": retry_candidate["click_x"],
                                "click_y": retry_candidate["click_y"],
                                "absolute_x": retry_attempt["absolute_x"],
                                "absolute_y": retry_attempt["absolute_y"],
                                "bbox": retry_candidate.get("bbox"),
                                "before_screenshot_path": image_path,
                                "after_screenshot_path": retry_attempt["after_screenshot_path"],
                                "screenshot_path": image_path,
                                "click_debug_path": retry_attempt["click_debug_path"],
                                "verification_result": retry_verification.get("success"),
                                "verification_reason": retry_verification.get("reason"),
                                "verification_confidence": retry_verification.get("confidence"),
                                "candidates": candidate_debug,
                                "selected_candidate": retry_candidate["debug"],
                                "rejected_candidates": rejected_candidates,
                                "selection_reason": "First click did not verify, so I tried a different safe candidate.",
                                "click_attempts": click_attempts,
                                "failed_clicks": failed_clicks,
                                "screen_left": screen_info["left"],
                                "screen_top": screen_info["top"],
                                "screen_width": screen_info["width"],
                                "screen_height": screen_info["height"],
                                "monitors": screen_info["monitors"],
                                "raw_plan": plan,
                                "verification_raw": retry_verification,
                                "model": VISION_MODEL,
                            }

                        failed_clicks.append(
                            _record_failed_click(
                                retry_candidate,
                                retry_verification,
                                retry_attempt["after_screenshot_path"],
                            )
                        )
                        break

            last_attempt = click_attempts[-1]
            last_verification = last_attempt["verification"]

            return {
                "success": False,
                "clicked": False,
                "click_attempted": True,
                "retried": retry_attempt is not None,
                "action": "click",
                "message": _natural_click_failure_message(
                    last_verification,
                    retried=retry_attempt is not None,
                ),
                "target": last_attempt["target"],
                "target_type": last_attempt["target_type"],
                "reason": reason,
                "confidence": last_attempt["confidence"],
                "coordinate_mode": last_attempt["coordinate_mode"],
                "coordinate_units": last_attempt.get("coordinate_units"),
                "click_x": last_attempt["click_x"],
                "click_y": last_attempt["click_y"],
                "absolute_x": last_attempt["absolute_x"],
                "absolute_y": last_attempt["absolute_y"],
                "bbox": last_attempt.get("bbox"),
                "before_screenshot_path": image_path,
                "after_screenshot_path": last_attempt["after_screenshot_path"],
                "screenshot_path": image_path,
                "click_debug_path": last_attempt["click_debug_path"],
                "verification_result": last_verification.get("success"),
                "verification_reason": last_verification.get("reason"),
                "verification_confidence": last_verification.get("confidence"),
                "candidates": candidate_debug,
                "selected_candidate": selected["debug"],
                "rejected_candidates": rejected_candidates,
                "selection_reason": plan.get("selection_reason"),
                "click_attempts": click_attempts,
                "failed_clicks": failed_clicks,
                "screen_left": screen_info["left"],
                "screen_top": screen_info["top"],
                "screen_width": screen_info["width"],
                "screen_height": screen_info["height"],
                "monitors": screen_info["monitors"],
                "raw_plan": plan,
                "verification_raw": last_verification,
                "model": VISION_MODEL,
            }

        return {
            "success": True,
            "clicked": False,
            "action": action,
            "message": message,
            "target": target,
            "reason": reason,
            "confidence": confidence,
            "unsafe": unsafe,
            "raw_plan": plan,
            "screenshot_path": image_path,
            "screen_left": screen_info["left"],
            "screen_top": screen_info["top"],
            "screen_width": screen_info["width"],
            "screen_height": screen_info["height"],
            "monitors": screen_info["monitors"],
            "model": VISION_MODEL,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I couldn’t act on the screen: {error}",
        }
