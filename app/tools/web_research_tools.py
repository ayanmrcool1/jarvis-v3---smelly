import os
import re
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


# =========================
# JARVIS FAST WEB RESEARCH
# Current web answers without opening a visible browser.
# =========================

BASE_DIR = Path(__file__).resolve().parents[2]
ENV_PATH = BASE_DIR / ".env"

DEFAULT_WEB_MODEL = "gpt-4o-mini"
DEFAULT_CONTEXT_SIZE = "low"
VALID_CONTEXT_SIZES = {"low", "medium", "high"}


def _clean_text(value, limit=900):
    text = str(value or "").strip()
    text = re.sub(r"\s+", " ", text)

    if len(text) <= limit:
        return text

    return text[: limit - 3].rstrip() + "..."


def _strip_spoken_noise(text):
    """
    Removes citation/link/debug formatting that should never be read aloud.
    The fuller answer and structured sources stay available separately.
    """

    text = str(text or "").strip()

    if not text:
        return ""

    text = re.sub(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]+\)", r"\1", text)
    text = re.sub(r"\((?:https?://|www\.)[^)]+\)", "", text)
    text = re.sub(r"(?:https?://|www\.)\S+", "", text)
    text = re.sub(r"\[[0-9,\s]+\]", "", text)
    text = re.sub(r"\[(?:source|sources|citation|citations|ref|refs)[^\]]*\]", "", text, flags=re.I)
    text = re.sub(r"\butm_[a-z_]+=[^\s&)]*", "", text, flags=re.I)
    text = re.sub(r"^[#>*\-\s]+", "", text, flags=re.MULTILINE)
    text = text.replace("**", "").replace("__", "").replace("`", "")
    text = re.sub(r"\s+", " ", text)

    return text.strip(" -")


def _split_sentences(text):
    return [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?])\s+", text)
        if sentence and sentence.strip()
    ]


def _trim_to_sentence_boundary(text, limit):
    text = str(text or "").strip()

    if len(text) <= limit:
        return text

    clipped = text[:limit].rstrip()
    boundary = max(clipped.rfind("."), clipped.rfind("!"), clipped.rfind("?"))

    if boundary >= 80:
        return clipped[: boundary + 1].strip()

    return clipped.rstrip(" ,;:-") + "."


def _short_spoken_message(text, limit=330):
    text = _strip_spoken_noise(text)
    text = _clean_text(text, limit=900)

    if not text:
        return "I couldn't find a useful web answer."

    # Avoid speaking whole markdown lists. Use only the first few useful lines.
    list_lines = [
        re.sub(r"^[*\-\d.)\s]+", "", line).strip()
        for line in str(text).splitlines()
        if line.strip()
    ]

    if len(list_lines) > 1:
        text = " ".join(list_lines[:3])

    sentences = _split_sentences(text)
    message = " ".join(sentence for sentence in sentences[:3] if sentence).strip()
    message = _strip_spoken_noise(message)
    message = _trim_to_sentence_boundary(message, limit)

    return message or "I found a few current details."


def _normalise_context_size(value):
    clean = str(value or os.getenv("JARVIS_WEB_SEARCH_CONTEXT", DEFAULT_CONTEXT_SIZE))
    clean = clean.strip().lower()

    if clean not in VALID_CONTEXT_SIZES:
        return DEFAULT_CONTEXT_SIZE

    return clean


def _extract_sources(response, max_sources):
    sources = []
    seen_urls = set()

    def add_source(url, title=""):
        url = str(url or "").strip()
        title = _clean_text(title, limit=160)

        if not url or url in seen_urls:
            return

        seen_urls.add(url)
        sources.append(
            {
                "title": title,
                "url": url,
            }
        )

    for item in getattr(response, "output", []) or []:
        item_type = getattr(item, "type", "")

        if item_type == "message":
            for content in getattr(item, "content", []) or []:
                for annotation in getattr(content, "annotations", []) or []:
                    if getattr(annotation, "type", "") == "url_citation":
                        add_source(
                            getattr(annotation, "url", ""),
                            getattr(annotation, "title", ""),
                        )

        if item_type == "web_search_call":
            action = getattr(item, "action", None)

            for source in getattr(action, "sources", []) or []:
                add_source(getattr(source, "url", ""))

    return sources[:max_sources]


def _responses_web_search(client, model, query, context_size):
    instructions = (
        "You are Jarvis doing fast web research for spoken output. "
        "Use current web information. Give a useful answer, but keep it concise. "
        "Mention only the strongest findings unless the user asks for detail. "
        "Do not dump long lists, raw URLs, or citation markup in the prose."
    )

    return client.responses.create(
        model=model,
        input=query,
        instructions=instructions,
        tools=[
            {
                "type": "web_search",
                "search_context_size": context_size,
            }
        ],
        include=["web_search_call.action.sources"],
        max_output_tokens=450,
    )


def _responses_web_search_preview(client, model, query, context_size):
    instructions = (
        "You are Jarvis doing fast web research for spoken output. "
        "Use current web information. Give a useful answer, but keep it concise. "
        "Mention only the strongest findings unless the user asks for detail. "
        "Do not dump long lists, raw URLs, or citation markup in the prose."
    )

    return client.responses.create(
        model=model,
        input=query,
        instructions=instructions,
        tools=[
            {
                "type": "web_search_preview",
                "search_context_size": context_size,
            }
        ],
        include=["web_search_call.action.sources"],
        max_output_tokens=450,
    )


def fast_web_research(query, max_sources=5, search_context_size="low"):
    """
    Uses OpenAI's hosted web search tool to answer current internet questions
    without opening a visible browser tab.
    """

    query = (query or "").strip()

    if not query:
        return {
            "success": False,
            "message": "What should I look up?",
            "spoken_message": "What should I look up?",
            "query": query,
            "sources": [],
        }

    try:
        max_sources = int(max_sources)
    except Exception:
        max_sources = 5

    max_sources = max(1, min(10, max_sources))
    context_size = _normalise_context_size(search_context_size)

    load_dotenv(ENV_PATH)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        return {
            "success": False,
            "message": "I need the OpenAI API key before I can research the web.",
            "spoken_message": "I need the OpenAI API key before I can research the web.",
            "query": query,
            "sources": [],
            "error": "OPENAI_API_KEY is missing.",
        }

    model = os.getenv("OPENAI_WEB_MODEL") or os.getenv("OPENAI_MODEL") or DEFAULT_WEB_MODEL
    client = OpenAI(api_key=api_key)
    web_search_type = "web_search"

    try:
        try:
            response = _responses_web_search(client, model, query, context_size)
        except Exception as first_error:
            web_search_type = "web_search_preview"

            try:
                response = _responses_web_search_preview(
                    client,
                    model,
                    query,
                    context_size,
                )
            except Exception as second_error:
                return {
                    "success": False,
                    "message": "I couldn't use web research from this OpenAI setup.",
                    "spoken_message": "I couldn't use web research from this OpenAI setup.",
                    "query": query,
                    "answer": "",
                    "sources": [],
                    "error": str(second_error),
                    "first_error": str(first_error),
                    "model": model,
                    "search_context_size": context_size,
                }

        answer = _clean_text(getattr(response, "output_text", ""), limit=1800)
        sources = _extract_sources(response, max_sources=max_sources)
        spoken_message = _short_spoken_message(answer)

        if not answer:
            return {
                "success": False,
                "message": "I searched, but I couldn't form a useful answer.",
                "spoken_message": "I searched, but I couldn't form a useful answer.",
                "query": query,
                "answer": "",
                "sources": sources,
                "model": model,
                "search_context_size": context_size,
                "web_search_type": web_search_type,
            }

        return {
            "success": True,
            "message": spoken_message,
            "spoken_message": spoken_message,
            "query": query,
            "answer": answer,
            "raw_answer": answer,
            "sources": sources,
            "model": model,
            "search_context_size": context_size,
            "web_search_type": web_search_type,
        }

    except Exception as error:
        return {
            "success": False,
            "message": "I couldn't complete the web research.",
            "spoken_message": "I couldn't complete the web research.",
            "query": query,
            "answer": "",
            "sources": [],
            "error": str(error),
            "model": model,
            "search_context_size": context_size,
        }
