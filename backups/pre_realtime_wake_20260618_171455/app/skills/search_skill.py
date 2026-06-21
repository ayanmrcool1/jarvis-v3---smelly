from tools.system_tools import search_web
from tools.youtube_tools import search_youtube, play_youtube_video


# =========================
# JARVIS SEARCH / YOUTUBE SKILL
# Only catches obvious search/media shortcuts.
# Ambiguous visible-screen requests are left for AI tool brain.
# =========================

SEARCH_PHRASES = [
    "search ",
    "google ",
    "look up ",
    "search for ",
    "google for ",
]

POLITE_PREFIXES = [
    "jarvis can you please ",
    "jarvis could you please ",
    "jarvis can you ",
    "jarvis could you ",
    "can you please ",
    "could you please ",
    "can you ",
    "could you ",
    "please ",
    "jarvis ",
]

SCREEN_CONTEXT_SIGNALS = [
    "from my screen",
    "on my screen",
    "from the screen",
    "on the screen",
    "from this screen",
    "on this screen",
    "from my page",
    "on my page",
    "from this page",
    "on this page",
    "from the page",
    "on the page",
    "from here",
    "on here",
    "right here",
    "what im looking at",
    "what i am looking at",
    "looking at right now",
    "one of these",
    "these options",
    "this option",
    "that option",
    "visible",
]


def strip_polite_prefixes(clean_text):
    stripped = clean_text

    changed = True

    while changed:
        changed = False

        for prefix in POLITE_PREFIXES:
            if stripped.startswith(prefix):
                stripped = stripped.replace(prefix, "", 1).strip()
                changed = True

    return stripped


def has_screen_context(clean_text):
    return any(signal in clean_text for signal in SCREEN_CONTEXT_SIGNALS)


def _clean_query(query):
    if not query:
        return ""

    query = " ".join(query.strip().split())

    replacements = {
        "redals": "retals",
        "retles": "retals",
        "retels": "retals",
        "our rocket league": "rocket league",
    }

    for old, new in replacements.items():
        query = query.replace(old, new)

    filler = [
        "for me",
        "please",
    ]

    for item in filler:
        query = query.replace(item, " ")

    return " ".join(query.split())


def extract_search_query(clean_text):
    stripped = strip_polite_prefixes(clean_text)

    for phrase in SEARCH_PHRASES:
        if stripped.startswith(phrase):
            return stripped.replace(phrase, "", 1).strip()

    return ""


def extract_youtube_search_query(clean_text):
    stripped = strip_polite_prefixes(clean_text)

    direct_prefixes = [
        "search on youtube ",
        "search youtube ",
        "youtube search ",
        "search youtube for ",
        "search on youtube for ",
        "youtube search for ",
    ]

    for prefix in direct_prefixes:
        if stripped.startswith(prefix):
            return _clean_query(stripped.replace(prefix, "", 1))

    action_prefixes = [
        "go to youtube and search ",
        "open youtube and search ",
        "go on youtube and search ",
        "go youtube and search ",
    ]

    for prefix in action_prefixes:
        if stripped.startswith(prefix):
            return _clean_query(stripped.replace(prefix, "", 1))

    if stripped.startswith("search for ") and stripped.endswith(" on youtube"):
        query = stripped.replace("search for ", "", 1)
        query = query.rsplit(" on youtube", 1)[0]
        return _clean_query(query)

    if stripped.startswith("look up ") and stripped.endswith(" on youtube"):
        query = stripped.replace("look up ", "", 1)
        query = query.rsplit(" on youtube", 1)[0]
        return _clean_query(query)

    return ""


def extract_youtube_play_query(clean_text):
    """
    Catches obvious topic-based YouTube play requests.
    Does NOT catch visible-screen/page requests.
    """

    if has_screen_context(clean_text):
        return ""

    stripped = strip_polite_prefixes(clean_text)

    play_prefixes = [
        "play a youtube video about ",
        "play youtube video about ",
        "play a video about ",
        "play video about ",
        "play a video on ",
        "play video on ",
        "play a video of ",
        "play video of ",
        "find and play a video about ",
        "find me a video about ",
        "find a video about ",
        "play ",
    ]

    for prefix in play_prefixes:
        if stripped.startswith(prefix):
            query = stripped.replace(prefix, "", 1).strip()

            if query.endswith(" on youtube"):
                query = query.rsplit(" on youtube", 1)[0]

            query = query.replace("a video by ", "")
            query = query.replace("video by ", "")
            query = query.replace("youtube video by ", "")

            return _clean_query(query)

    return ""


def handle_search_command(transcription, clean_text):
    """
    Handles obvious web search and obvious YouTube shortcuts locally.
    Ambiguous screen/page/video choices go to the AI brain.
    """

    youtube_search_query = extract_youtube_search_query(clean_text)

    if youtube_search_query:
        result = search_youtube(youtube_search_query)

        return {
            "handled": True,
            "response": result.get("message", f"Searching YouTube for {youtube_search_query}."),
            "source": "youtube_search_skill",
        }

    youtube_play_query = extract_youtube_play_query(clean_text)

    if youtube_play_query:
        result = play_youtube_video(youtube_play_query)

        return {
            "handled": True,
            "response": result.get("message", f"Playing {youtube_play_query} on YouTube."),
            "source": "youtube_play_skill",
        }

    stripped = strip_polite_prefixes(clean_text)

    is_search_command = any(
        stripped.startswith(phrase)
        for phrase in SEARCH_PHRASES
    )

    if not is_search_command:
        return None

    query = extract_search_query(clean_text)

    if not query:
        return {
            "handled": True,
            "response": "What do you want me to search?",
            "source": "search_skill",
        }

    result = search_web(query)

    if result.get("success"):
        return {
            "handled": True,
            "response": result.get("message", f"Searching the web for {query}."),
            "source": "search_skill",
        }

    return {
        "handled": True,
        "response": result.get("message", f"I could not search for {query}."),
        "source": "search_skill",
    }