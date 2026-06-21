from tools.system_tools import set_volume


# =========================
# JARVIS VOLUME SKILL
# =========================

def handle_volume_command(transcription, clean_text):
    """
    Handles obvious volume commands locally.
    """

    if not _looks_like_volume_command(clean_text):
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

    if "unmute" in clean_text:
        result = set_volume("unmute")

        return {
            "handled": True,
            "response": result.get("message", "Volume unmuted."),
            "source": "volume_skill",
        }

    if "mute" in clean_text:
        result = set_volume("mute")

        return {
            "handled": True,
            "response": result.get("message", "Volume muted."),
            "source": "volume_skill",
        }

    return {
        "handled": True,
        "response": "Do you want the volume up, down, or muted?",
        "source": "volume_skill",
    }


def _looks_like_volume_command(clean_text):
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
