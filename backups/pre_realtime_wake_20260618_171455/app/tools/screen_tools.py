import os
import base64
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


def take_screenshot(filename="latest_screen.png"):
    """
    Takes a screenshot of the primary monitor and saves it.
    """

    try:
        output_path = SCREENSHOT_DIR / filename

        with mss.mss() as sct:
            monitor = sct.monitors[1]
            screenshot = sct.grab(monitor)

            img = Image.frombytes(
                "RGB",
                screenshot.size,
                screenshot.rgb
            )

            img.save(output_path)

        return {
            "success": True,
            "message": "Screenshot taken.",
            "path": str(output_path),
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

        prompt = f"""
You are JARVIS, the user's local Windows assistant.

The user asked you to look at their screen.

Active window title:
{window_title}

Instruction:
{instruction}

Response style:
- Be very concise.
- Reply in one or two short sentences.
- Speak naturally, like a calm personal assistant.
- Do not say "the image shows" repeatedly.
- If there is an error message, say what it likely means and the next step.
- If this is a trading chart, describe only what is visually obvious unless the user asks for deeper analysis.
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
            max_tokens=90,
        )

        text = response.choices[0].message.content.strip()

        return {
            "success": True,
            "message": text,
            "path": image_path,
            "active_window": active_window,
            "model": VISION_MODEL,
            "time": datetime.now().isoformat(timespec="seconds"),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not analyse the screen: {error}",
            "path": image_path,
        }