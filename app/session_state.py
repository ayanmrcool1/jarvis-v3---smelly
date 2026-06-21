import time


# =========================
# JARVIS SESSION STATE
# Small, generic state for incomplete multi-turn intents.
# =========================

PLACEHOLDER_WORDS = {
    "something",
    "anything",
    "whatever",
    "stuff",
    "thing",
    "a thing",
    "some stuff",
}

CANCEL_WORDS = {
    "cancel",
    "never mind",
    "nevermind",
    "forget it",
    "dont worry",
    "don't worry",
    "leave it",
}


class PendingIntentManager:
    def __init__(self, expires_after_turns=2, expires_after_seconds=60):
        self.pending = None
        self.expires_after_turns = expires_after_turns
        self.expires_after_seconds = expires_after_seconds

    def clear(self):
        self.pending = None

    def has_pending(self):
        return self.pending is not None and not self._is_expired()

    def _is_expired(self):
        if not self.pending:
            return True

        age = time.time() - self.pending.get("created_at", 0)
        turns = int(self.pending.get("turns_waited", 0))

        return age > self.expires_after_seconds or turns > self.expires_after_turns

    def _create(self, intent_type, pending_tool, required_slot, original_request, prompt):
        self.pending = {
            "pending_intent_type": intent_type,
            "pending_tool": pending_tool,
            "required_slot": required_slot,
            "original_request": original_request,
            "created_at": time.time(),
            "expires_after_turns": self.expires_after_turns,
            "expires_after_seconds": self.expires_after_seconds,
            "turns_waited": 0,
            "prompt": prompt,
        }

        return self.pending

    def create_from_incomplete_request(self, transcription, clean_text):
        if not clean_text:
            return None

        if _looks_like_incomplete_visible_search(clean_text):
            return self._create(
                intent_type="visible_search",
                pending_tool="search_web",
                required_slot="query",
                original_request=transcription,
                prompt="What should I search?",
            )

        if _looks_like_incomplete_research(clean_text):
            return self._create(
                intent_type="web_research",
                pending_tool="fast_web_research",
                required_slot="query",
                original_request=transcription,
                prompt="What should I research?",
            )

        if _looks_like_incomplete_app_open(clean_text):
            return self._create(
                intent_type="open_application",
                pending_tool="open_application",
                required_slot="app_name",
                original_request=transcription,
                prompt="Which app should I open?",
            )

        return None

    def resolve_with(self, transcription, clean_text):
        if not self.pending:
            return None

        if self._is_expired():
            self.clear()
            return None

        if _is_cancel(clean_text):
            self.clear()
            return {
                "status": "cancelled",
                "message": "No problem.",
            }

        if _looks_like_new_full_command(clean_text):
            self.clear()
            return None

        slot_value = _clean_slot_value(transcription)

        if not slot_value or _is_placeholder_text(slot_value):
            self.pending["turns_waited"] = int(self.pending.get("turns_waited", 0)) + 1

            return {
                "status": "still_missing",
                "message": self.pending.get("prompt", "What should I use?"),
            }

        pending = self.pending
        self.clear()

        return {
            "status": "resolved",
            "pending": pending,
            "slot_value": slot_value,
            "tool_name": pending.get("pending_tool"),
            "user_text": _build_completion_prompt(pending, slot_value),
        }


def _normalise(text):
    return " ".join(str(text or "").lower().strip().split())


def _is_cancel(clean_text):
    return _normalise(clean_text) in CANCEL_WORDS


def _is_placeholder_text(text):
    clean = _normalise(text)

    if clean in PLACEHOLDER_WORDS:
        return True

    filler = [
        "for me",
        "please",
        "on google",
        "up",
        "to search",
        "to research",
        "an app",
        "app",
        "application",
    ]

    for item in filler:
        clean = clean.replace(item, " ")

    clean = " ".join(clean.split())

    return not clean or clean in PLACEHOLDER_WORDS


def _contains_placeholder(clean_text):
    return any(f" {word} " in f" {clean_text} " for word in PLACEHOLDER_WORDS)


def _looks_like_incomplete_visible_search(clean_text):
    has_search_intent = (
        "search" in clean_text
        or "google" in clean_text
        or "look up" in clean_text
    )

    return has_search_intent and _contains_placeholder(clean_text)


def _looks_like_incomplete_research(clean_text):
    has_research_intent = (
        "research" in clean_text
        or "look into" in clean_text
        or "check out" in clean_text
        or "find out" in clean_text
    )

    return has_research_intent and _contains_placeholder(clean_text)


def _looks_like_incomplete_app_open(clean_text):
    stripped = _strip_request_prefixes(clean_text)
    has_open_intent = stripped.startswith(
        (
            "open ",
            "open up ",
            "launch ",
            "start ",
            "bring up ",
        )
    )

    if not has_open_intent:
        return False

    return (
        " an app" in f" {stripped}"
        or " application" in stripped
        or _contains_placeholder(stripped)
    )


def _looks_like_new_full_command(clean_text):
    return clean_text.startswith(
        (
            "open ",
            "open up ",
            "launch ",
            "start ",
            "bring up ",
            "search ",
            "search for ",
            "google ",
            "look up ",
            "research ",
            "tell me ",
            "what ",
            "why ",
            "how ",
            "can you ",
            "could you ",
            "please ",
        )
    ) and not _contains_placeholder(clean_text)


def _clean_slot_value(text):
    clean = str(text or "").strip()

    for prefix in sorted([
        "it's ",
        "its ",
        "search for ",
        "search ",
        "google ",
        "look up ",
        "research ",
        "open up ",
        "open ",
        "launch ",
        "start ",
    ], key=len, reverse=True):
        if clean.lower().startswith(prefix):
            clean = clean[len(prefix):].strip()
            break

    return clean.strip(" .,!?:;")


def _strip_request_prefixes(clean_text):
    stripped = clean_text

    for prefix in [
        "jarvis can you please ",
        "jarvis could you please ",
        "can you please ",
        "could you please ",
        "jarvis can you ",
        "jarvis could you ",
        "can you ",
        "could you ",
        "please ",
        "jarvis ",
    ]:
        if stripped.startswith(prefix):
            return stripped[len(prefix):].strip()

    return stripped


def _build_completion_prompt(pending, slot_value):
    intent_type = pending.get("pending_intent_type")
    original_request = pending.get("original_request", "")

    if intent_type == "visible_search":
        return (
            "Complete the pending visible browser search. "
            f"Original request: {original_request}. Search query: {slot_value}."
        )

    if intent_type == "web_research":
        return (
            "Complete the pending web research request and answer concisely. "
            f"Original request: {original_request}. Research query: {slot_value}."
        )

    if intent_type == "open_application":
        return (
            "Complete the pending app opening request. "
            f"Original request: {original_request}. App name: {slot_value}."
        )

    return slot_value
