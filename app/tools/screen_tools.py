import os
import base64
import json
import re
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI
import mss
from PIL import Image


# =========================
# JARVIS SCREEN TOOLS
# Screenshot + active window + vision analysis
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"
SCREENSHOT_DIR = BASE_DIR / "screenshots"
SCREENSHOT_DIR.mkdir(exist_ok=True)

load_dotenv(ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
VISION_MODEL = os.getenv("OPENAI_VISION_MODEL", os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

client = OpenAI(api_key=OPENAI_API_KEY)


def _build_monitor_metadata(sct):
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

    return monitors


def take_screenshot(filename="latest_screen.png"):
    """
    Takes a screenshot of the full virtual desktop and saves a unique copy.
    """

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        output_path = SCREENSHOT_DIR / f"screen_{timestamp}.png"
        latest_path = SCREENSHOT_DIR / (filename or "latest_screen.png")

        with mss.mss() as sct:
            virtual_monitor = sct.monitors[0]
            screenshot = sct.grab(virtual_monitor)

            img = Image.frombytes(
                "RGB",
                screenshot.size,
                screenshot.rgb
            )

            img.save(output_path)
            img.save(latest_path)
            monitors = _build_monitor_metadata(sct)

        return {
            "success": True,
            "message": "Screenshot taken.",
            "path": str(output_path),
            "screenshot_path": str(output_path),
            "latest_path": str(latest_path),
            "screenshot_mode": "full_virtual_desktop",
            "virtual_left": int(virtual_monitor["left"]),
            "virtual_top": int(virtual_monitor["top"]),
            "virtual_width": int(virtual_monitor["width"]),
            "virtual_height": int(virtual_monitor["height"]),
            "monitors": monitors,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to take screenshot: {error}",
        }


def get_active_window_info():
    """
    Returns active window title if available.
    """

    try:
        import pygetwindow as gw

        active_window = gw.getActiveWindow()

        if not active_window:
            return {
                "success": True,
                "message": "I could not detect an active window.",
                "title": None,
            }

        return {
            "success": True,
            "message": f"Active window: {active_window.title}",
            "title": active_window.title,
            "left": active_window.left,
            "top": active_window.top,
            "width": active_window.width,
            "height": active_window.height,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to get active window: {error}",
        }


def encode_image_to_base64(image_path):
    """
    Encodes an image file as base64 for OpenAI vision input.
    """

    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")


def _extract_json(text):
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


def analyse_screen(instruction=None):
    """
    Takes a screenshot and asks OpenAI vision to analyse it.
    """

    screenshot_result = take_screenshot()

    if not screenshot_result.get("success"):
        return screenshot_result

    image_path = screenshot_result.get("path")
    active_window = get_active_window_info()

    if not instruction:
        instruction = "Briefly explain what is visible on my screen. Mention any important errors, warnings, buttons, pages, charts, or text."

    try:
        base64_image = encode_image_to_base64(image_path)

        window_title = active_window.get("title") if active_window.get("success") else None
        active_window_bounds = {}

        if active_window.get("success"):
            for key in ["left", "top", "width", "height"]:
                active_window_bounds[key] = active_window.get(key)

            if active_window_bounds.get("left") is not None and active_window_bounds.get("top") is not None:
                active_window_bounds["screenshot_left"] = int(
                    active_window_bounds["left"] - screenshot_result.get("virtual_left", 0)
                )
                active_window_bounds["screenshot_top"] = int(
                    active_window_bounds["top"] - screenshot_result.get("virtual_top", 0)
                )

        screenshot_metadata = {
            "mode": screenshot_result.get("screenshot_mode"),
            "virtual_left": screenshot_result.get("virtual_left"),
            "virtual_top": screenshot_result.get("virtual_top"),
            "virtual_width": screenshot_result.get("virtual_width"),
            "virtual_height": screenshot_result.get("virtual_height"),
            "monitors": screenshot_result.get("monitors"),
        }

        prompt = f"""
You are JARVIS, the user's local Windows assistant.

The user asked you to look at their screen.

The screenshot shows the FULL virtual desktop across all monitors, not just the primary monitor.

Active window title:
{window_title}

Active window bounds in Windows virtual-desktop coordinates:
{json.dumps(active_window_bounds)}

Screenshot metadata:
{json.dumps(screenshot_metadata)}

Instruction:
{instruction}

Response style:
- Be very concise.
- Reply in one or two short sentences.
- Speak naturally, like a calm personal assistant.
- Do not say "the image shows" repeatedly.
- You are allowed to make normal visual judgments from the screenshot when the user asks how something looks.
- If something looks appetising, clear, stylish, good, bad, blurry, confusing, or hard to see, say that naturally.
- Do not say you cannot assess appearance directly when the screenshot is available.
- If visibility is poor, say what is unclear and why.
- If there is an error message, say what it likely means and the next step.
- If this is a trading chart, describe only what is visually obvious unless the user asks for deeper analysis.

Return ONLY valid JSON:
{{
  "message": "short natural answer to speak aloud",
  "visible_summary": "brief description of the relevant visible content",
  "confidence": 0.0,
  "reason": "brief reason, especially if visibility is poor"
}}
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
                                "detail": "low",
                            },
                        },
                    ],
                }
            ],
            temperature=0.2,
            max_tokens=180,
        )

        text = response.choices[0].message.content.strip()
        parsed = _extract_json(text)

        if parsed:
            message = (parsed.get("message") or "").strip()
            visible_summary = (parsed.get("visible_summary") or "").strip()
            reason = (parsed.get("reason") or "").strip()

            try:
                confidence = float(parsed.get("confidence") or 0.0)
            except Exception:
                confidence = 0.0

            if not message:
                message = visible_summary or "I can see the screen, but I cannot make out the key detail clearly."

            return {
                "success": True,
                "message": message,
                "visible_summary": visible_summary,
                "confidence": confidence,
                "reason": reason,
                "path": image_path,
                "screenshot_path": image_path,
                "latest_path": screenshot_result.get("latest_path"),
                "screenshot_mode": screenshot_result.get("screenshot_mode"),
                "active_window": active_window,
                "active_window_bounds": active_window_bounds,
                "monitors": screenshot_result.get("monitors"),
                "virtual_left": screenshot_result.get("virtual_left"),
                "virtual_top": screenshot_result.get("virtual_top"),
                "virtual_width": screenshot_result.get("virtual_width"),
                "virtual_height": screenshot_result.get("virtual_height"),
                "model": VISION_MODEL,
                "time": datetime.now().isoformat(timespec="seconds"),
            }

        return {
            "success": True,
            "message": text,
            "visible_summary": text,
            "confidence": 0.5,
            "reason": "The vision model returned plain text instead of structured JSON.",
            "path": image_path,
            "screenshot_path": image_path,
            "latest_path": screenshot_result.get("latest_path"),
            "screenshot_mode": screenshot_result.get("screenshot_mode"),
            "active_window": active_window,
            "active_window_bounds": active_window_bounds,
            "monitors": screenshot_result.get("monitors"),
            "virtual_left": screenshot_result.get("virtual_left"),
            "virtual_top": screenshot_result.get("virtual_top"),
            "virtual_width": screenshot_result.get("virtual_width"),
            "virtual_height": screenshot_result.get("virtual_height"),
            "model": VISION_MODEL,
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not analyse the screen: {error}",
            "path": image_path,
            "screenshot_path": image_path,
            "screenshot_mode": screenshot_result.get("screenshot_mode"),
            "active_window": active_window,
            "monitors": screenshot_result.get("monitors"),
        }
