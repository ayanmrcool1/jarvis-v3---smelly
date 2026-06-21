import time

import pyautogui

from tools.browser_tools import (
    get_current_browser_page,
    get_foreground_window_details,
    is_browser_window,
)


# =========================
# JARVIS BROWSER TAB TOOLS
# Browser tab control using reliable hotkeys
# =========================

TAB_CLOSE_DELAY = 0.22
TAB_SWITCH_DELAY = 0.16


def _focused_browser_check():
    """
    Confirms the active window is a browser before sending browser hotkeys.
    """

    window = get_foreground_window_details()

    if not window.get("success"):
        return {
            "success": False,
            "message": window.get("message", "I could not detect the active window."),
            "window": window,
        }

    if not is_browser_window(window):
        return {
            "success": False,
            "message": "I need the browser focused before I can control its tabs.",
            "window": window,
        }

    return {
        "success": True,
        "window": window,
    }


def _clean_match_text(match_text):
    match_text = (match_text or "").strip().lower()

    if not match_text:
        return "youtube"

    replacements = {
        "you tube": "youtube",
        "youtube tabs": "youtube",
        "youtube tab": "youtube",
        "all youtube tabs": "youtube",
    }

    return replacements.get(match_text, match_text)


def _page_matches(page, match_text):
    """
    Checks whether the current browser tab matches the requested text/site.
    """

    match_text = _clean_match_text(match_text)

    url = str(page.get("url", "") or "").lower()
    title = str(page.get("title", "") or "").lower()
    domain = str(page.get("domain", "") or "").lower()

    haystack = f"{url} {title} {domain}"

    if match_text == "youtube":
        return (
            "youtube.com" in haystack
            or "youtu.be" in haystack
            or "youtube" in title
        )

    return match_text in haystack


def close_current_browser_tab():
    """
    Closes the currently active browser tab using Ctrl+W.
    """

    check = _focused_browser_check()

    if not check.get("success"):
        return check

    try:
        pyautogui.hotkey("ctrl", "w")
        time.sleep(TAB_CLOSE_DELAY)

        return {
            "success": True,
            "message": "Closed the current tab.",
            "window": check.get("window"),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not close the current tab: {error}",
            "window": check.get("window"),
        }


def switch_browser_tab(tab_number):
    """
    Switches to a numbered browser tab.
    Chrome/Edge hotkeys:
    Ctrl+1 to Ctrl+8 = tabs 1-8
    Ctrl+9 = last tab
    """

    check = _focused_browser_check()

    if not check.get("success"):
        return check

    try:
        tab_number = int(tab_number)
    except Exception:
        return {
            "success": False,
            "message": "Which tab number do you want me to open?",
        }

    if tab_number < 1:
        return {
            "success": False,
            "message": "Tab numbers start from one.",
        }

    try:
        if tab_number <= 8:
            pyautogui.hotkey("ctrl", str(tab_number))
        else:
            pyautogui.hotkey("ctrl", "9")

        time.sleep(TAB_SWITCH_DELAY)

        return {
            "success": True,
            "message": f"Switched to tab {tab_number}.",
            "tab_number": tab_number,
            "window": check.get("window"),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not switch tabs: {error}",
            "tab_number": tab_number,
            "window": check.get("window"),
        }


def close_browser_tabs_matching(match_text="youtube", max_tabs=30):
    """
    Closes tabs in the active browser window that match a page/title/domain.

    This is designed for commands like:
    - close all YouTube tabs
    - close YouTube tabs
    - close all tabs with Gmail
    """

    check = _focused_browser_check()

    if not check.get("success"):
        return check

    match_text = _clean_match_text(match_text)

    try:
        max_tabs = int(max_tabs or 30)
    except Exception:
        max_tabs = 30

    max_tabs = max(1, min(max_tabs, 60))

    closed_count = 0
    scanned_since_last_close = 0

    try:
        for _ in range(max_tabs * 2):
            page = get_current_browser_page()

            if not page.get("success"):
                if closed_count > 0:
                    break

                return {
                    "success": False,
                    "message": page.get("message", "I could not read the current browser tab."),
                    "closed_count": closed_count,
                    "match_text": match_text,
                    "page": page,
                }

            if _page_matches(page, match_text):
                pyautogui.hotkey("ctrl", "w")
                time.sleep(TAB_CLOSE_DELAY)

                closed_count += 1
                scanned_since_last_close = 0
                continue

            pyautogui.hotkey("ctrl", "tab")
            time.sleep(TAB_SWITCH_DELAY)

            scanned_since_last_close += 1

            if scanned_since_last_close >= max_tabs:
                break

        if closed_count == 1:
            message = f"Closed one {match_text} tab."
        elif closed_count > 1:
            message = f"Closed {closed_count} {match_text} tabs."
        else:
            message = f"I couldn’t find any {match_text} tabs to close."

        return {
            "success": closed_count > 0,
            "message": message,
            "closed_count": closed_count,
            "match_text": match_text,
            "window": check.get("window"),
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"I could not close matching tabs: {error}",
            "closed_count": closed_count,
            "match_text": match_text,
            "window": check.get("window"),
        }