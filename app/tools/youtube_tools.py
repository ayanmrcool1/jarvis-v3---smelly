import re
import urllib.parse
import urllib.request
import webbrowser


# =========================
# JARVIS YOUTUBE TOOLS
# =========================

YOUTUBE_BASE = "https://www.youtube.com"
YOUTUBE_SEARCH_URL = "https://www.youtube.com/results?search_query="


def _clean_query(query):
    """
    Cleans natural speech into a usable YouTube query.
    """

    if not query:
        return ""

    query = " ".join(str(query).strip().split())

    remove_phrases = [
        "on youtube",
        "youtube",
        "a youtube video about",
        "youtube video about",
        "a video about",
        "video about",
        "a video on",
        "video on",
        "a video of",
        "video of",
        "for me",
        "please",
    ]

    clean = query.lower()

    for phrase in remove_phrases:
        clean = clean.replace(phrase, " ")

    clean = " ".join(clean.split())

    return clean


def _youtube_search_url(query):
    encoded_query = urllib.parse.quote_plus(query)
    return f"{YOUTUBE_SEARCH_URL}{encoded_query}"


def search_youtube(query):
    """
    Open YouTube search results directly.
    Example:
    search_youtube("rocket league gameplay retals")
    """

    clean_query = _clean_query(query)

    if not clean_query:
        return {
            "success": False,
            "message": "What do you want me to search on YouTube?",
        }

    url = _youtube_search_url(clean_query)

    try:
        webbrowser.open(url)

        return {
            "success": True,
            "query": clean_query,
            "url": url,
            "message": f"Searching YouTube for {clean_query}.",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Failed to search YouTube: {error}",
        }


def _fetch_youtube_search_page(query):
    """
    Downloads YouTube search HTML so Jarvis can extract a likely first video.
    """

    url = _youtube_search_url(query)

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0 Safari/537.36"
            )
        },
    )

    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read().decode("utf-8", errors="ignore")


def _extract_first_video_id(html):
    """
    Extracts the first normal YouTube video ID from search HTML.
    """

    if not html:
        return None

    patterns = [
        r'"videoId":"([a-zA-Z0-9_-]{11})"',
        r"watch\?v=([a-zA-Z0-9_-]{11})",
    ]

    seen = set()

    for pattern in patterns:
        for video_id in re.findall(pattern, html):
            if video_id in seen:
                continue

            seen.add(video_id)

            if len(video_id) == 11:
                return video_id

    return None


def play_youtube_video(query):
    """
    Search YouTube and open the most likely first video.
    If direct video extraction fails, it falls back to YouTube results.
    """

    clean_query = _clean_query(query)

    if not clean_query:
        return {
            "success": False,
            "message": "What video should I play?",
        }

    try:
        html = _fetch_youtube_search_page(clean_query)
        video_id = _extract_first_video_id(html)

        if video_id:
            url = f"{YOUTUBE_BASE}/watch?v={video_id}&autoplay=1"
            webbrowser.open(url)

            return {
                "success": True,
                "query": clean_query,
                "video_id": video_id,
                "url": url,
                "message": f"Playing a YouTube video for {clean_query}.",
            }

        search_url = _youtube_search_url(clean_query)
        webbrowser.open(search_url)

        return {
            "success": True,
            "query": clean_query,
            "url": search_url,
            "message": f"I couldn’t pick a video directly, so I opened YouTube results for {clean_query}.",
        }

    except Exception as error:
        search_url = _youtube_search_url(clean_query)

        try:
            webbrowser.open(search_url)

            return {
                "success": True,
                "query": clean_query,
                "url": search_url,
                "message": f"I opened YouTube results for {clean_query}.",
                "warning": str(error),
            }

        except Exception as fallback_error:
            return {
                "success": False,
                "message": f"Failed to open YouTube: {fallback_error}",
            }