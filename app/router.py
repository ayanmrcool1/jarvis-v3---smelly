import string

from session_state import PendingIntentManager
from skills.app_skill import looks_like_multi_step_open_command
from skills.volume_skill import handle_volume_command
from skills.system_skill import handle_system_command
from skills.routine_skill import handle_routine_command
from skills.screen_skill import handle_screen_command


# =========================
# JARVIS ROUTER
# Local fast path first.
# If local misses, AI tool brain decides what to do.
# =========================

def normalize_text(text):
    """
    Normalizes speech text for routing.
    """

    if not text:
        return ""

    clean_text = text.lower().strip()
    clean_text = clean_text.translate(str.maketrans("", "", string.punctuation))
    clean_text = " ".join(clean_text.split())

    return clean_text


def get_forced_tool_name(clean_text):
    """
    Forces the AI to call a tool only for obvious executable commands.

    This is NOT the main intelligence layer.
    Main intelligence is handled by stream_ask_with_tools() after local misses.
    """

    # -------------------------
    # Screen / vision tools
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
        "what window",
        "what window am i on",
        "active window",
        "what app am i on",
        "what app is open",
        "what application am i on",
        "what window is this",
    ]

    screen_vision_signals = [
        "look at my screen",
        "look at the screen",
        "read my screen",
        "read the screen",
        "read this screen",
        "what is on my screen",
        "whats on my screen",
        "what screen am i looking at",
        "what am i looking at",
        "what is this screen",
        "whats this screen",
        "read this error",
        "what does this error mean",
        "error on screen",
        "warning on screen",
        "can you see this",
    ]

    if any(signal in clean_text for signal in screenshot_signals):
        return "take_screenshot"

    if any(signal in clean_text for signal in active_window_signals):
        return "get_active_window_info"

    if any(signal in clean_text for signal in screen_vision_signals):
        return "analyse_screen"

    # Memory and routine-management intent is deliberately left to the AI brain.

    # -------------------------
    # App opening tools
    # -------------------------
    visible_search_prefixes = [
        "open a search for ",
        "open search for ",
        "open up a search for ",
        "open up search for ",
        "open up an image of ",
        "open up a picture of ",
        "open up a photo of ",
        "open up images of ",
        "open up pictures of ",
        "open up photos of ",
        "open an image of ",
        "open a picture of ",
        "open a photo of ",
        "open images of ",
        "open pictures of ",
        "open photos of ",
        "pull up an image of ",
        "pull up a picture of ",
        "pull up a photo of ",
        "pull up images of ",
        "pull up pictures of ",
        "pull up photos of ",
    ]

    if any(clean_text.startswith(prefix) for prefix in visible_search_prefixes):
        return "search_web"

    open_keywords = [
        "open ",
        "launch ",
        "bring up ",
    ]

    for keyword in open_keywords:
        if clean_text.startswith(keyword):
            if looks_like_multi_step_open_command(clean_text):
                return None

            return "open_application"

    # -------------------------
    # Search tools
    # -------------------------
    protected_show_requests = [
        "show me memory",
        "show me memories",
        "show me routine",
        "show me routines",
        "show me my memory",
        "show me my memories",
        "show me my routine",
        "show me my routines",
        "show me the screen",
        "show me my screen",
        "show me this screen",
    ]

    if any(clean_text.startswith(prefix) for prefix in protected_show_requests):
        return None

    search_keywords = [
        "search for ",
        "google for ",
        "google search for ",
        "google search ",
        "pull up results for ",
        "show me results for ",
        "search ",
        "google ",
    ]

    for keyword in sorted(set(search_keywords), key=len, reverse=True):
        if clean_text.startswith(keyword):
            return "search_web"

    # -------------------------
    # Volume tools
    # -------------------------
    if looks_like_volume_command(clean_text):
        return "set_volume"

    # -------------------------
    # System stats tools
    # -------------------------
    if looks_like_system_stats_command(clean_text):
        return "get_system_stats"

    # -------------------------
    # Terminal tools
    # -------------------------
    if clean_text.startswith(("run command ", "run terminal command ", "run powershell command ")):
        return "run_terminal_command"

    return None


def looks_like_volume_command(clean_text):
    if clean_text in ["mute", "unmute"]:
        return True

    if clean_text.startswith(
        (
            "mute ",
            "unmute ",
            "volume ",
            "turn volume ",
            "set volume ",
            "lower volume",
            "raise volume",
            "increase volume",
            "decrease volume",
        )
    ):
        return True

    if "volume" in clean_text:
        return any(
            word in clean_text
            for word in ["up", "down", "lower", "raise", "increase", "decrease", "mute", "unmute"]
        )

    return False


def looks_like_system_stats_command(clean_text):
    display_intent_prefixes = (
        "show ",
        "show me ",
        "display ",
        "open ",
        "pull up ",
        "bring up ",
    )

    if clean_text.startswith(display_intent_prefixes):
        return False

    direct_phrases = [
        "system stats",
        "system status",
        "computer stats",
        "computer status",
        "performance stats",
        "cpu usage",
        "ram usage",
        "memory usage",
        "battery level",
        "battery percentage",
        "disk usage",
    ]

    return any(phrase in clean_text for phrase in direct_phrases)


class JarvisRouter:
    """
    Main command router.

    Correct architecture:
    1. Local skill handlers catch obvious instant executable commands first.
    2. Forced tool routing handles very obvious tool intent.
    3. If still not handled, AI tool-streaming brain decides:
       - call a function, or
       - answer normally.
    """

    def __init__(self, brain):
        self.brain = brain
        self.pending_intents = PendingIntentManager()

        self.local_skill_handlers = [
            handle_screen_command,
            handle_routine_command,
            handle_system_command,
            handle_volume_command,
        ]

    def handle(self, transcription):
        """
        Main routing function.

        Returns:
        - type: 'text' or 'stream'
        - response: normal text response
        - stream: streamed AI/tool response
        - source: where the response came from
        """

        clean_text = normalize_text(transcription)

        print(f"Router clean text: {clean_text}")

        pending_result = self.pending_intents.resolve_with(transcription, clean_text)

        if pending_result:
            status = pending_result.get("status")

            if status in ["cancelled", "still_missing"]:
                return {
                    "type": "text",
                    "response": pending_result.get("message", "No problem."),
                    "source": "pending_intent",
                }

            if status == "resolved":
                print(f"Router completed pending intent: {pending_result.get('tool_name')}")

                return {
                    "type": "stream",
                    "stream": self.brain.stream_ask_with_tools(
                        pending_result.get("user_text", transcription),
                        forced_tool_name=pending_result.get("tool_name"),
                    ),
                    "source": "pending_intent_stream",
                }

        pending = self.pending_intents.create_from_incomplete_request(
            transcription,
            clean_text,
        )

        if pending:
            print(f"Router created pending intent: {pending.get('pending_intent_type')}")

            return {
                "type": "text",
                "response": pending.get("prompt", "What should I use?"),
                "source": "pending_intent",
            }

        # -------------------------
        # 1. Local fast path
        # -------------------------
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

        # -------------------------
        # 2. Forced AI tool path for obvious intent
        # -------------------------
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

        # -------------------------
        # 3. Main AI tool brain fallback
        # -------------------------
        print("Router using AI tool streaming brain.")

        return {
            "type": "stream",
            "stream": self.brain.stream_ask_with_tools(transcription),
            "source": "ai_tool_stream",
        }
