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
MONITOR_SEAM_BLOCK_PX = 45

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

    if not text:
        return None

    cleaned = text.strip()
    cleaned = cleaned.replace("```json", "").replace("```", "").strip()

    try:
        return json.loads(cleaned)
    except Exception:
        pass

    match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)

    if not match:
        return None

    try:
        return json.loads(match.group(0))
    except Exception:
        return None


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


def _percent_to_pixel(value, maximum):
    """
    Converts a 0-1000 normalised coordinate into a screenshot pixel coordinate.
    """

    value = float(value)
    value = _clamp(value, 0, 1000)
    return int(round((value / 1000.0) * (maximum - 1)))


def _get_click_pixels(plan, screen_info):
    """
    Supports preferred normalised 0-1000 coords, with fallback to raw pixels.
    Normalised coords are more reliable because the vision model may view a resized image.
    """

    width = screen_info["width"]
    height = screen_info["height"]

    click_x_pct = plan.get("click_x_pct")
    click_y_pct = plan.get("click_y_pct")

    if click_x_pct is not None and click_y_pct is not None:
        return (
            _percent_to_pixel(click_x_pct, width),
            _percent_to_pixel(click_y_pct, height),
            "normalised",
        )

    click_x = plan.get("click_x")
    click_y = plan.get("click_y")

    if click_x is None or click_y is None:
        return None, None, "missing"

    return int(click_x), int(click_y), "pixel"


def _save_click_debug_image(screen_info, x, y, target):
    """
    Saves a debug screenshot with a red marker showing where Jarvis intended to click.
    """

    try:
        image_path = screen_info["path"]
        debug_path = SCREENSHOT_DIR / "screen_action_click_debug.png"

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


def _safe_click(screen_info, x, y, target):
    """
    Clicks a coordinate relative to the full virtual desktop screenshot.
    Supports multi-monitor setups.
    """

    width = screen_info["width"]
    height = screen_info["height"]

    x = int(_clamp(int(x), 0, width - 1))
    y = int(_clamp(int(y), 0, height - 1))

    debug_path = _save_click_debug_image(screen_info, x, y, target)

    absolute_x = int(screen_info["left"] + x)
    absolute_y = int(screen_info["top"] + y)

    pyautogui.moveTo(absolute_x, absolute_y, duration=0.15)
    time.sleep(0.10)
    pyautogui.click(absolute_x, absolute_y)

    return absolute_x, absolute_y, debug_path


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
        screen_info = _capture_all_screens_for_action()
        image_path = screen_info["path"]
        base64_image = encode_image_to_base64(image_path)
        active_window = get_active_window_info()

        dangerous = _instruction_has_dangerous_action(instruction)
        active_window_block = _active_window_prompt_block(active_window, screen_info)

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
{json.dumps(screen_info["monitors"], indent=2)}

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
- For YouTube/videos, target must be an actual visible video title or clearly visible video card.
- If the user asks for a random video, choose one actual visible video title/card. Do not return "random video" as the target.
- Do NOT click between monitors.
- Do NOT click the centre of the full screenshot unless an actual visible target is centred there.
- Do NOT click blank space, page background, random coordinates, or generic areas.
- Do NOT click if the target is only described as "random video", "video", "option", "button", or "item".
- If you cannot identify a real clickable target, ask or recommend instead of clicking.

Coordinate rules:
- Prefer click_x_pct and click_y_pct.
- click_x_pct and click_y_pct must be 0 to 1000 normalised coordinates relative to the FULL screenshot.
- Example: far left = 0, centre = 500, far right = 1000.
- Only use raw click_x/click_y if you are highly confident.
- Click the centre of the actual card/thumbnail/button you are selecting.

Safety:
- If the request involves buying, paying, deleting, sending, confirming, accepting, submitting, passwords, banking, or irreversible actions, do not click.

Return ONLY valid JSON in this exact format:
{{
  "success": true,
  "action": "answer" | "recommend" | "click" | "ask",
  "message": "short natural response to speak to the user",
  "target": "specific visible target title/label/description, or null",
  "reason": "brief reason",
  "confidence": 0.0,
  "click_x_pct": null,
  "click_y_pct": null,
  "click_x": null,
  "click_y": null,
  "unsafe": false
}}

Important:
- For click action, provide click_x_pct and click_y_pct whenever possible.
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
            max_tokens=420,
        )

        raw_text = response.choices[0].message.content.strip()
        plan = _extract_json(raw_text)

        if not plan:
            return {
                "success": False,
                "message": "I looked, but I couldn’t form a reliable screen action.",
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

            if _looks_generic_target(target):
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I can see the page, but I need a clearer visible target before clicking.",
                    "target": target,
                    "reason": "The proposed target was too generic.",
                    "confidence": confidence,
                    "raw_plan": plan,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            if confidence < MIN_CLICK_CONFIDENCE:
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I can see a few options, but I’m not confident enough to click one.",
                    "target": target,
                    "reason": reason,
                    "confidence": confidence,
                    "raw_plan": plan,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            click_x, click_y, coordinate_mode = _get_click_pixels(plan, screen_info)

            if click_x is None or click_y is None:
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I found an option, but I don’t have a reliable click point.",
                    "target": target,
                    "reason": reason,
                    "confidence": confidence,
                    "raw_plan": plan,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            click_x = int(click_x)
            click_y = int(click_y)

            if _is_lazy_center_click(screen_info, click_x, click_y):
                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I can see the page, but I won’t click a generic centre point.",
                    "target": target,
                    "reason": "The proposed click point looked like a generic centre-screen click.",
                    "confidence": confidence,
                    "raw_plan": plan,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            if _is_near_monitor_seam(screen_info, click_x):
                debug_path = _save_click_debug_image(screen_info, click_x, click_y, target)

                return {
                    "success": True,
                    "clicked": False,
                    "action": "ask",
                    "message": "I found a target, but the click point was too close to the gap between monitors.",
                    "target": target,
                    "reason": "Blocked click near monitor seam.",
                    "confidence": confidence,
                    "raw_plan": plan,
                    "click_x": click_x,
                    "click_y": click_y,
                    "click_debug_path": debug_path,
                    "screenshot_path": image_path,
                    "model": VISION_MODEL,
                }

            absolute_x, absolute_y, debug_path = _safe_click(
                screen_info,
                click_x,
                click_y,
                target,
            )

            return {
                "success": True,
                "clicked": True,
                "action": "click",
                "message": message,
                "target": target,
                "reason": reason,
                "confidence": confidence,
                "coordinate_mode": coordinate_mode,
                "click_x": click_x,
                "click_y": click_y,
                "absolute_x": absolute_x,
                "absolute_y": absolute_y,
                "screenshot_path": image_path,
                "click_debug_path": debug_path,
                "screen_left": screen_info["left"],
                "screen_top": screen_info["top"],
                "screen_width": screen_info["width"],
                "screen_height": screen_info["height"],
                "monitors": screen_info["monitors"],
                "raw_plan": plan,
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