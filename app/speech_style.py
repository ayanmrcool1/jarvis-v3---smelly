import re


# =========================
# JARVIS SPEECH STYLE
# Makes tool/local responses sound less robotic.
# =========================

def clean_memory_text(text):
    """
    Cleans technical memory wording.
    """

    text = text.replace("User prefers", "you prefer")
    text = text.replace("User likes", "you like")
    text = text.replace("User wants", "you want")
    text = text.replace("User usually", "you usually")
    text = text.replace("User always", "you always")
    text = text.replace("User never", "you never")

    return text


def humanise_jarvis_response(response):
    """
    Converts raw tool responses into smoother spoken responses.
    """

    if not response:
        return "Done."

    text = response.strip()

    # -------------------------
    # Memory responses
    # -------------------------
    if text.startswith("I’ll remember that:"):
        memory = text.replace("I’ll remember that:", "", 1).strip()
        memory = clean_memory_text(memory)

        return f"Got it — I’ll keep that in mind. {memory}"

    if text.startswith("I already remember that"):
        return "I already had that saved."

    if text.startswith("Here is what I remember:"):
        memory = text.replace("Here is what I remember:", "", 1).strip()
        memory = memory.replace("preferences:", "")
        memory = memory.replace("user_profile:", "")
        memory = memory.replace("aliases:", "")
        memory = memory.replace("workflow_rules:", "")
        memory = memory.replace("jarvis_rules:", "")
        memory = memory.replace("notes:", "")
        memory = clean_memory_text(memory)
        memory = " ".join(memory.split())

        if memory:
            return f"I remember that {memory[0].lower() + memory[1:]}"
        return "I don’t have much saved yet."

    if text.startswith("I do not have any memories"):
        return "I don’t have anything saved yet."

    if text.startswith("Forgot:"):
        forgotten = text.replace("Forgot:", "", 1).strip()
        forgotten = clean_memory_text(forgotten)
        return f"Done — I forgot {forgotten}."

    # -------------------------
    # Routine responses
    # -------------------------
    if text.startswith("Saved routine:"):
        routine = text.replace("Saved routine:", "", 1).strip().rstrip(".")
        return f"Done — I saved {routine}."

    if text.startswith("Deleted routine:"):
        routine = text.replace("Deleted routine:", "", 1).strip().rstrip(".")
        return f"Done — I deleted {routine}."

    if text.startswith("Saved routines:"):
        routines = text.replace("Saved routines:", "", 1).strip()
        return f"You’ve got these routines saved: {routines}."

    # -------------------------
    # App opening
    # -------------------------
    if text.startswith("Opening "):
        app = text.replace("Opening", "", 1).strip().rstrip(".")
        return f"Of course — opening {app}."

    # -------------------------
    # Web search
    # -------------------------
    if text.startswith("Searching the web for"):
        query = text.replace("Searching the web for", "", 1).strip().rstrip(".")
        return f"Sure — searching for {query}."

    # -------------------------
    # Volume
    # -------------------------
    volume_down_match = re.search(r"Volume decreased from \d+% to (\d+)%", text)
    if volume_down_match:
        new_volume = volume_down_match.group(1)
        return f"Done — volume’s down to {new_volume} percent."

    volume_up_match = re.search(r"Volume increased from \d+% to (\d+)%", text)
    if volume_up_match:
        new_volume = volume_up_match.group(1)
        return f"Done — volume’s up to {new_volume} percent."

    if text == "Volume muted.":
        return "Muted."

    if text == "Volume unmuted.":
        return "Unmuted."

    # -------------------------
    # System stats
    # -------------------------
    if text.startswith("CPU is at"):
        return text.replace("CPU is at", "Right now, CPU is at", 1)

    return text