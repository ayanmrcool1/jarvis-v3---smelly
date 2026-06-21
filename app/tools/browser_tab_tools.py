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
HARD_SCAN_SECONDS = 14.0
HARD_SCAN_ITERATIONS = 90
MAX_SAFE_TAB_SCAN = 40


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


def _page_signature(page):
    """
    Builds a best-effort tab identity from URL, domain, and title.
    """

    url = str(page.get("url", "") or "").lower().strip()
    domain = str(page.get("domain", "") or "").lower().strip()
    title = str(page.get("title", "") or "").lower().strip()

    signature = "|".join([url, domain, title]).strip("|")

    return signature or None


def _release_browser_modifier_keys():
    """
    Safety cleanup in case a hotkey sequence is interrupted.
    """

    for key in ["ctrl", "shift", "alt"]:
        try:
            pyautogui.keyUp(key)
        except Exception:
            pass


def _send_browser_hotkey(*keys):
    try:
        pyautogui.hotkey(*keys)
    finally:
        _release_browser_modifier_keys()


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

    This uses a bounded hotkey scan. Full tab enumeration is not available with
    the current approach, so the scan stops on return-to-start, read failure
    after successful closes, a safe scan limit, or a hard time/iteration limit.
    """

    check = _focused_browser_check()

    if not check.get("success"):
        return check

    match_text = _clean_match_text(match_text)

    try:
        max_tabs = int(max_tabs or 30)
    except Exception:
        max_tabs = 30

    max_tabs = max(1, min(max_tabs, MAX_SAFE_TAB_SCAN))

    closed_count = 0
    scanned_non_matching_tabs = 0
    iterations = 0
    stop_reason = "scan_complete"
    first_seen_signature = None
    saw_different_signature = False
    started_at = time.monotonic()
    hard_iteration_limit = min(max_tabs * 3, HARD_SCAN_ITERATIONS)

    try:
        for _ in range(hard_iteration_limit):
            iterations += 1

            if time.monotonic() - started_at >= HARD_SCAN_SECONDS:
                stop_reason = "safety_time_limit"
                break

            page = get_current_browser_page()

            if not page.get("success"):
                if closed_count > 0:
                    stop_reason = "page_unreadable_after_closing"
                    break

                return {
                    "success": False,
                    "message": page.get("message", "I could not read the current browser tab."),
                    "closed_count": closed_count,
                    "match_text": match_text,
                    "page": page,
                }

            signature = _page_signature(page)

            if _page_matches(page, match_text):
                _send_browser_hotkey("ctrl", "w")
                time.sleep(TAB_CLOSE_DELAY)

                closed_count += 1
                continue

            if first_seen_signature is None:
                first_seen_signature = signature
            elif (
                signature
                and signature == first_seen_signature
                and saw_different_signature
            ):
                stop_reason = "returned_to_start"
                break

            if (
                first_seen_signature
                and signature
                and signature != first_seen_signature
            ):
                saw_different_signature = True

            scanned_non_matching_tabs += 1

            if scanned_non_matching_tabs >= max_tabs:
                stop_reason = "safe_scan_limit"
                break

            _send_browser_hotkey("ctrl", "tab")
            time.sleep(TAB_SWITCH_DELAY)

        else:
            stop_reason = "hard_iteration_limit"

        if time.monotonic() - started_at >= HARD_SCAN_SECONDS:
            stop_reason = "safety_time_limit"

        _release_browser_modifier_keys()

        try:
            pyautogui.press("esc")
        except Exception:
            pass

        if stop_reason in [
            "safe_scan_limit",
            "hard_iteration_limit",
            "safety_time_limit",
        ]:
            scan_note = " I stopped after a safe limited scan."
        else:
            scan_note = ""

        if closed_count == 1:
            message = f"Closed one {match_text} tab.{scan_note}"
        elif closed_count > 1:
            message = f"Closed {closed_count} {match_text} tabs.{scan_note}"
        else:
            if stop_reason in [
                "safe_scan_limit",
                "hard_iteration_limit",
                "safety_time_limit",
            ]:
                message = f"I could not find any {match_text} tabs in the safe scan."
            else:
                message = f"I couldn't find any {match_text} tabs to close."

        return {
            "success": closed_count > 0,
            "message": message,
            "closed_count": closed_count,
            "match_text": match_text,
            "scanned_non_matching_tabs": scanned_non_matching_tabs,
            "iterations": iterations,
            "stop_reason": stop_reason,
            "window": check.get("window"),
        }

    except Exception as error:
        _release_browser_modifier_keys()

        try:
            pyautogui.press("esc")
        except Exception:
            pass

        return {
            "success": False,
            "message": f"I could not close matching tabs: {error}",
            "closed_count": closed_count,
            "match_text": match_text,
            "scanned_non_matching_tabs": scanned_non_matching_tabs,
            "iterations": iterations,
            "stop_reason": "error",
            "window": check.get("window"),
        }
