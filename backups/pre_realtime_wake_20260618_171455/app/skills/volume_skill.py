from tools.system_tools import set_volume


# =========================
# JARVIS VOLUME SKILL
# =========================

def handle_volume_command(transcription, clean_text):
    """
    Handles obvious volume commands locally.
    """

    if (
        "volume" not in clean_text
        and "mute" not in clean_text
        and "unmute" not in clean_text
    ):
        return None

    if (
        "down" in clean_text
        or "lower" in clean_text
        or "decrease" in clean_text
        or "quieter" in clean_text
    ):
        result = set_volume("down")

        return {
            "handled": True,
            "response": result.get("message", "Volume decreased."),
            "source": "volume_skill",
        }

    if (
        "up" in clean_text
        or "raise" in clean_text
        or "increase" in clean_text
        or "louder" in clean_text
    ):
        result = set_volume("up")

        return {
            "handled": True,
            "response": result.get("message", "Volume increased."),
            "source": "volume_skill",
        }

    if "mute" in clean_text or "unmute" in clean_text:
        result = set_volume("mute")

        return {
            "handled": True,
            "response": result.get("message", "Volume muted or unmuted."),
            "source": "volume_skill",
        }

    return {
        "handled": True,
        "response": "Do you want the volume up, down, or muted?",
        "source": "volume_skill",
    }