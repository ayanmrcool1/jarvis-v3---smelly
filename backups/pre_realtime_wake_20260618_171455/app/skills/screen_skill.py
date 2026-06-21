from tools.screen_tools import analyse_screen, take_screenshot, get_active_window_info


# =========================
# JARVIS SCREEN SKILL
# Local backup layer only.
# AI tool calling is the main intelligence layer.
# =========================

def handle_screen_command(transcription, clean_text):
    """
    Handles only obvious screen commands locally.

    Browser/page questions should go to the AI tool brain,
    so it can choose browser tools like get_current_browser_page
    or analyse_current_page.
    """

    screenshot_signals = [
        "take screenshot",
        "take a screenshot",
        "screenshot",
        "screenshot this",
        "capture screen",
        "capture my screen",
    ]

    active_window_signals = [
        "what window",
        "what window am i on",
        "active window",
        "what app am i on",
        "what app is open",
        "what application am i on",
    ]

    screen_vision_signals = [
        "look at my screen",
        "look at the screen",
        "what is on my screen",
        "whats on my screen",
        "what screen am i looking at",
        "read this error",
        "error on screen",
    ]

    browser_words = [
        "website",
        "site",
        "url",
        "page",
        "webpage",
        "domain",
    ]

    # Let AI handle website/page requests with browser tools.
    if any(word in clean_text for word in browser_words):
        return None

    if any(signal in clean_text for signal in screenshot_signals):
        result = take_screenshot()

        return {
            "handled": True,
            "response": result.get("message", "Screenshot taken."),
            "source": "screen_skill",
        }

    if any(signal in clean_text for signal in active_window_signals):
        result = get_active_window_info()

        if result.get("success") and result.get("title"):
            return {
                "handled": True,
                "response": f"You’re on {result.get('title')}.",
                "source": "screen_skill",
            }

        return {
            "handled": True,
            "response": result.get("message", "I could not detect the active window."),
            "source": "screen_skill",
        }

    if any(signal in clean_text for signal in screen_vision_signals):
        result = analyse_screen(instruction=transcription)

        return {
            "handled": True,
            "response": result.get("message", "I could not analyse the screen."),
            "source": "screen_skill",
        }

    return None