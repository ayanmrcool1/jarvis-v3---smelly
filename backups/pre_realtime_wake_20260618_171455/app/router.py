import re
import string

from skills.app_skill import handle_app_command
from skills.volume_skill import handle_volume_command
from skills.system_skill import handle_system_command
from skills.search_skill import handle_search_command
from skills.routine_skill import handle_routine_command
from skills.screen_skill import handle_screen_command


# =========================
# JARVIS ROUTER
# Local fast path first.
# AI brain is the main intent layer.
# =========================

NUMBER_WORDS = {
    "one": 1,
    "won": 1,
    "two": 2,
    "too": 2,
    "to": 2,
    "three": 3,
    "four": 4,
    "for": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
}


def normalize_text(text):
    if not text:
        return ""

    clean_text = text.lower().strip()
    clean_text = clean_text.translate(str.maketrans("", "", string.punctuation))
    clean_text = " ".join(clean_text.split())

    return clean_text


def strip_polite_prefixes(clean_text):
    prefixes = [
        "hey jarvis ",
        "hey drivers ",
        "jarvis can you please ",
        "jarvis could you please ",
        "jarvis can you ",
        "jarvis could you ",
        "can you please ",
        "could you please ",
        "can you ",
        "could you ",
        "do you mind ",
        "please ",
        "jarvis ",
        "drivers ",
    ]

    changed = True
    stripped = clean_text

    while changed:
        changed = False

        for prefix in prefixes:
            if stripped.startswith(prefix):
                stripped = stripped.replace(prefix, "", 1).strip()
                changed = True

    return stripped


def is_thanks_or_acknowledgement(clean_text):
    exact_phrases = [
        "thanks",
        "thank you",
        "cheers",
        "appreciate it",
        "i appreciate it",
        "alright thanks",
        "ok thanks",
        "okay thanks",
        "cool thanks",
        "bet thanks",
        "nice thanks",
        "sweet thanks",
    ]

    if clean_text in exact_phrases:
        return True

    if (
        clean_text.startswith("thanks ")
        or clean_text.startswith("thank you ")
        or clean_text.endswith(" thanks")
        or clean_text.endswith(" thank you")
    ):
        return True

    if "i appreciate it" in clean_text and len(clean_text.split()) <= 8:
        return True

    return False


def get_local_conversation_response(clean_text):
    if is_thanks_or_acknowledgement(clean_text):
        return "Anytime."

    casual_acknowledgements = [
        "ok",
        "okay",
        "alright",
        "cool",
        "bet",
        "nice",
        "sweet",
        "got it",
        "yeah okay",
    ]

    if clean_text in casual_acknowledgements:
        return "Got it."

    return None


def _is_complex_open_request(stripped):
    """
    Prevents broad natural requests from being forced into open_application.
    These should go to the AI brain so it can choose YouTube/search/screen action.
    """

    complex_markers = [
        "video",
        "youtube video",
        "random",
        "one of",
        "from this",
        "from my",
        "from here",
        "on this page",
        "on my screen",
        "this page",
        "this screen",
        "what im looking at",
        "what i am looking at",
        "best",
        "option",
        "choose",
        "select",
        "pick",
        "play",
        "tab",
        "tap",
    ]

    return any(marker in stripped for marker in complex_markers)


def _parse_tab_number(stripped):
    """
    Handles:
    - tab two
    - tap two
    - tab 2
    - open up tab two
    - go to tap two
    """

    match = re.search(r"\b(?:tab|tap)\s+([0-9]+|one|won|two|too|to|three|four|for|five|six|seven|eight|nine)\b", stripped)

    if not match:
        return None

    value = match.group(1).strip()

    if value.isdigit():
        return int(value)

    return NUMBER_WORDS.get(value)


def _is_current_tab_close_request(stripped):
    close_words = [
        "close",
        "shut",
        "exit",
    ]

    current_tab_markers = [
        "this tab",
        "current tab",
        "the tab",
        "active tab",
    ]

    if not any(word in stripped for word in close_words):
        return False

    return any(marker in stripped for marker in current_tab_markers)


def _is_matching_tab_close_request(stripped):
    close_words = [
        "close",
        "shut",
    ]

    if not any(word in stripped for word in close_words):
        return False

    if "tab" not in stripped and "tabs" not in stripped:
        return False

    matching_markers = [
        "all",
        "every",
        "youtube",
        "gmail",
        "google",
        "tradingview",
        "trading view",
    ]

    return any(marker in stripped for marker in matching_markers)


def get_forced_tool_name(clean_text):
    """
    Force tools only for very obvious, low-ambiguity commands.
    Everything else goes to the AI brain with tools.
    """

    stripped = strip_polite_prefixes(clean_text)

    # -------------------------
    # Browser tab tools
    # -------------------------
    if _is_matching_tab_close_request(stripped):
        return "close_browser_tabs_matching"

    if _is_current_tab_close_request(stripped):
        return "close_current_browser_tab"

    if _parse_tab_number(stripped) is not None:
        if any(word in stripped for word in ["open", "go", "switch", "move", "bring", "pull"]):
            return "switch_browser_tab"

    # -------------------------
    # Screen / page basics
    # -------------------------
    screenshot_signals = [
        "take screenshot",
        "take a screenshot",
        "screenshot",
        "screenshot this",
        "capture screen",
        "capture my screen",
    ]

    active_window_signals = [
        "what window am i on",
        "active window",
        "what app am i on",
        "what application am i on",
    ]

    browser_page_signals = [
        "what website am i on",
        "what site am i on",
        "what page am i on",
        "what url am i on",
        "what website is this",
        "what site is this",
        "what page is this",
        "what url is this",
    ]

    if any(signal in stripped for signal in screenshot_signals):
        return "take_screenshot"

    if any(signal in stripped for signal in active_window_signals):
        return "get_active_window_info"

    if any(signal in stripped for signal in browser_page_signals):
        return "get_current_browser_page"

    open_keywords = [
        "open ",
        "launch ",
        "start ",
        "bring up ",
        "pull up ",
    ]

    for keyword in open_keywords:
        if stripped.startswith(keyword):
            if _is_complex_open_request(stripped):
                return None

            return "open_application"

    explicit_search_keywords = [
        "search ",
        "google ",
        "look up ",
        "search for ",
    ]

    for keyword in explicit_search_keywords:
        if stripped.startswith(keyword):
            return "search_web"

    if (
        "volume" in stripped
        or stripped == "mute"
        or stripped == "unmute"
        or "mute the computer" in stripped
        or "unmute the computer" in stripped
    ):
        return "set_volume"

    if (
        "system stats" in stripped
        or "system status" in stripped
        or "computer stats" in stripped
        or "cpu" in stripped
        or "ram" in stripped
        or "battery" in stripped
        or "disk usage" in stripped
    ):
        return "get_system_stats"

    if (
        "terminal" in stripped
        or "powershell" in stripped
        or "command prompt" in stripped
        or "run command" in stripped
    ):
        return "run_terminal_command"

    return None


def should_use_tool_brain(clean_text):
    """
    Broadly decide whether tools should be available.
    This is intentionally flexible: the AI brain decides the specific tool.
    """

    stripped = strip_polite_prefixes(clean_text)

    tool_context_markers = [
        "open",
        "launch",
        "start",
        "bring up",
        "pull up",
        "close",
        "shut",
        "minimise",
        "minimize",
        "maximize",
        "maximise",
        "fullscreen",
        "move",
        "click",
        "press",
        "select",
        "go with",
        "do one",
        "play",
        "put on",
        "turn on",

        "search",
        "google",
        "look up",
        "youtube",
        "video",
        "website",
        "site",
        "url",
        "page",
        "browser",
        "tab",
        "tabs",
        "tap",

        "screen",
        "screenshot",
        "window",
        "looking at",
        "this",
        "that",
        "these",
        "those",
        "here",
        "visible",
        "option",
        "options",
        "food",
        "menu",
        "order",
        "which one",
        "one of",
        "random",
        "decide",
        "recommend",
        "best",

        "app",
        "application",
        "volume",
        "mute",
        "unmute",
        "routine",
        "mode",
        "setup",
        "remember",
        "forget",
        "terminal",
        "powershell",
        "command prompt",
        "cpu",
        "ram",
        "battery",
        "performance",
        "system stats",
        "file",
        "folder",
        "desktop",
    ]

    current_or_live_words = [
        "current",
        "latest",
        "live",
        "today",
        "right now",
        "news",
        "weather",
        "stock",
        "price",
        "score",
        "traffic",
        "near me",
    ]

    if any(marker in stripped for marker in tool_context_markers):
        return True

    if any(marker in stripped for marker in current_or_live_words):
        return True

    return False


class JarvisRouter:
    """
    Main command router.
    """

    def __init__(self, brain):
        self.brain = brain

        self.local_skill_handlers = [
            handle_screen_command,
            handle_routine_command,
            handle_system_command,
            handle_volume_command,
            handle_app_command,
            handle_search_command,
        ]

    def handle(self, transcription):
        clean_text = normalize_text(transcription)

        print(f"Router clean text: {clean_text}")

        local_conversation_response = get_local_conversation_response(clean_text)

        if local_conversation_response:
            print("Router matched: local_conversation")

            return {
                "type": "text",
                "response": local_conversation_response,
                "source": "local_conversation",
            }

        for handler in self.local_skill_handlers:
            try:
                result = handler(transcription, clean_text)

                if result and result.get("handled"):
                    print(f"Router matched: {result.get('source')}")

                    return {
                        "type": "text",
                        "response": result.get("response", "Done."),
                        "source": result.get("source", "local_skill"),
                    }

            except Exception as error:
                print(f"Local router error in {handler.__name__}: {error}")

        forced_tool_name = get_forced_tool_name(clean_text)

        if forced_tool_name:
            print(f"Router forcing AI tool: {forced_tool_name}")

            return {
                "type": "stream",
                "stream": self.brain.stream_ask_with_tools(
                    transcription,
                    forced_tool_name=forced_tool_name,
                ),
                "source": "ai_forced_tool_stream",
            }

        if not should_use_tool_brain(clean_text):
            print("Router using normal AI stream without tools.")

            return {
                "type": "stream",
                "stream": self.brain.stream_ask(transcription),
                "source": "ai_normal_stream",
            }

        print("Router using AI tool streaming brain.")

        return {
            "type": "stream",
            "stream": self.brain.stream_ask_with_tools(transcription),
            "source": "ai_tool_stream",
        }