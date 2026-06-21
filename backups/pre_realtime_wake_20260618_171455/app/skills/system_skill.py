from tools.system_tools import get_current_datetime, get_system_stats


# =========================
# JARVIS SYSTEM SKILL
# =========================

def handle_system_command(transcription, clean_text):
    """
    Handles local system commands:
    - time
    - date
    - CPU/RAM/system stats
    """

    # -------------------------
    # Time
    # -------------------------
    time_phrases = [
        "what time is it",
        "whats the time",
        "what's the time",
        "tell me the time",
        "current time",
        "actual time",
    ]

    for phrase in time_phrases:
        if phrase in clean_text:
            result = get_current_datetime()

            return {
                "handled": True,
                "response": f"It's {result.get('time')}.",
                "source": "system_skill",
            }

    # -------------------------
    # Date
    # -------------------------
    date_phrases = [
        "what date is it",
        "whats the date",
        "what's the date",
        "what day is it",
        "current date",
    ]

    for phrase in date_phrases:
        if phrase in clean_text:
            result = get_current_datetime()

            return {
                "handled": True,
                "response": f"It's {result.get('date')}.",
                "source": "system_skill",
            }

    # -------------------------
    # System stats
    # -------------------------
    if (
        "system stats" in clean_text
        or "computer stats" in clean_text
        or "system scuts" in clean_text
        or "cpu" in clean_text
        or "ram" in clean_text
        or "memory usage" in clean_text
        or "battery" in clean_text
        or "performance" in clean_text
    ):
        stats = get_system_stats()

        if not stats.get("success"):
            return {
                "handled": True,
                "response": stats.get("message", "I could not get system stats."),
                "source": "system_skill",
            }

        cpu = stats.get("cpu_percent")
        ram = stats.get("ram_percent")
        disk = stats.get("disk_percent")
        battery = stats.get("battery_percent")

        if battery is None:
            response = (
                f"CPU is at {cpu} percent, RAM is at {ram} percent, "
                f"and disk usage is at {disk} percent."
            )
        else:
            response = (
                f"CPU is at {cpu} percent, RAM is at {ram} percent, "
                f"disk usage is at {disk} percent, and battery is at {battery} percent."
            )

        return {
            "handled": True,
            "response": response,
            "source": "system_skill",
        }

    return None