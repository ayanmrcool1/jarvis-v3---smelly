import time
import ctypes
from ctypes import wintypes
from urllib.parse import urlparse

import psutil
import pyautogui
import pyperclip

from tools.memory_tools import remember_memory
from tools.screen_tools import (
    take_screenshot,
    encode_image_to_base64,
    client,
    VISION_MODEL,
)


# =========================
# JARVIS BROWSER / PAGE TOOLS
# =========================

BROWSER_PROCESSES = [
    "chrome.exe",
    "msedge.exe",
    "firefox.exe",
    "brave.exe",
    "opera.exe",
    "opera_gx.exe",
    "operagx.exe",
    "vivaldi.exe",
]

BROWSER_TITLE_SUFFIXES = [
    " - Google Chrome",
    " - Microsoft Edge",
    " - Mozilla Firefox",
    " - Brave",
    " - Opera",
    " - Opera GX",
    " - Vivaldi",
]

LOCAL_URL_PREFIXES = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
]


def get_foreground_window_details():
    """
    Gets active window title, process name, process id, and handle on Windows.
    """

    try:
        user32 = ctypes.windll.user32

        hwnd = user32.GetForegroundWindow()

        if not hwnd:
            return {
                "success": False,
                "message": "I could not find the active window.",
            }

        length = user32.GetWindowTextLengthW(hwnd)
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

        process_name = psutil.Process(pid.value).name().lower()

        return {
            "success": True,
            "title": buffer.value,
            "process_name": process_name,
            "pid": pid.value,
            "hwnd": hwnd,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not read the active window: {error}",
        }


def is_browser_window(window_details):
    """
    Checks if active window belongs to a known browser.
    """

    if not window_details.get("success"):
        return False

    process_name = window_details.get("process_name", "").lower()

    return process_name in BROWSER_PROCESSES


def clean_browser_title(title):
    """
    Removes browser suffix from title.
    """

    clean_title = title or ""

    for suffix in BROWSER_TITLE_SUFFIXES:
        if clean_title.endswith(suffix):
            clean_title = clean_title[: -len(suffix)]

    return clean_title.strip()


def _looks_like_url(text):
    """
    Checks if copied address-bar text looks like a browser URL.
    """

    if not text:
        return False

    clean_text = text.strip().lower()

    if clean_text.startswith(("http://", "https://", "file://")):
        return True

    if any(clean_text.startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
        return True

    return False


def _normalise_url(url):
    """
    Normalises local dev URLs if the browser gives them without a scheme.
    """

    if not url:
        return ""

    url = url.strip()

    if url.lower().startswith(("http://", "https://", "file://")):
        return url

    if any(url.lower().startswith(prefix) for prefix in LOCAL_URL_PREFIXES):
        return "http://" + url

    return url


def copy_active_browser_url():
    """
    Copies the URL from the active browser address bar.
    Preserves the user's clipboard where possible.
    """

    old_clipboard = ""

    try:
        old_clipboard = pyperclip.paste()
    except Exception:
        old_clipboard = ""

    copied_url = ""

    try:
        pyautogui.hotkey("ctrl", "l")
        time.sleep(0.12)

        pyautogui.hotkey("ctrl", "c")
        time.sleep(0.12)

        copied_url = pyperclip.paste().strip()

        pyautogui.press("esc")
        time.sleep(0.05)

    except Exception:
        copied_url = ""

    finally:
        try:
            pyperclip.copy(old_clipboard)
        except Exception:
            pass

    if _looks_like_url(copied_url):
        return _normalise_url(copied_url)

    return ""


def get_current_browser_page():
    """
    Gets the active browser URL, title, domain, and process.
    """

    window = get_foreground_window_details()

    if not window.get("success"):
        return window

    if not is_browser_window(window):
        return {
            "success": False,
            "message": "I don’t think you’re focused on a browser window right now.",
            "active_window": window,
        }

    url = copy_active_browser_url()
    title = clean_browser_title(window.get("title", ""))

    if not url:
        return {
            "success": False,
            "message": "I found the browser, but I couldn’t read the current URL.",
            "active_window": window,
            "title": title,
        }

    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path

    if title and domain:
        message = f"You’re on {title}, at {domain}."
    elif domain:
        message = f"You’re on {domain}."
    else:
        message = f"You’re on {url}."

    return {
        "success": True,
        "message": message,
        "url": url,
        "domain": domain,
        "title": title,
        "process_name": window.get("process_name"),
        "active_window": window,
    }


def analyse_current_page(instruction=None):
    """
    Analyses the current browser page using URL + title + screenshot.
    Better than screenshot-only for website questions.
    """

    page = get_current_browser_page()

    if not page.get("success"):
        return page

    screenshot = take_screenshot()

    if not screenshot.get("success"):
        return screenshot

    image_path = screenshot.get("path")

    if not instruction:
        instruction = "Briefly explain what website or page I am on and what is visible."

    try:
        base64_image = encode_image_to_base64(image_path)

        prompt = f"""
You are JARVIS, the user's local Windows assistant.

The user asked about their current browser page.

Current page title:
{page.get("title")}

Current URL:
{page.get("url")}

Domain:
{page.get("domain")}

User instruction:
{instruction}

Response style:
- Be very concise.
- Reply in one or two short sentences.
- Mention the website/page name if clear.
- Mention the domain if useful.
- Use the screenshot to understand what is visible.
- Do not guess beyond the URL, title, and screenshot.
- Speak naturally, like a calm personal assistant.
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
            max_tokens=100,
        )

        text = response.choices[0].message.content.strip()

        return {
            "success": True,
            "message": text,
            "page": page,
            "screenshot_path": image_path,
            "model": VISION_MODEL,
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not analyse the current page: {error}",
            "page": page,
            "screenshot_path": image_path,
        }


def save_current_website(site_name, description=None):
    """
    Saves the current browser page as a named website/page in Jarvis memory.
    Example:
    'This is my website SanctuaryPaid, remember it.'
    """

    page = get_current_browser_page()

    if not page.get("success"):
        return page

    site_name = (site_name or "").strip()

    if not site_name:
        site_name = page.get("title") or page.get("domain") or "this website"

    url = page.get("url")
    title = page.get("title")
    domain = page.get("domain")

    memory_content = (
        f"{site_name} is a website/page the user wants JARVIS to remember. "
        f"URL: {url}. "
        f"Title: {title}. "
        f"Domain: {domain}."
    )

    if description:
        memory_content += f" Notes: {description}"

    memory_result = remember_memory(
        category="aliases",
        content=memory_content,
        source="explicit",
        confidence=1.0,
        tags=["website", site_name.lower()],
    )

    if memory_result.get("success"):
        return {
            "success": True,
            "message": f"Got it — I’ll remember {site_name} as {domain}.",
            "memory": memory_result,
            "page": page,
        }

    return memory_result