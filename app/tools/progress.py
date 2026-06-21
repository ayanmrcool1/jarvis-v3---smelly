class ToolProgress:
    """
    Lightweight progress emitter for long-running tools.
    Tools can opt in without changing their return value contract.
    """

    def __init__(self, callback=None, tool_name="tool"):
        self.callback = callback
        self.tool_name = tool_name
        self.last_message = None

    def emit(self, message):
        if not self.callback:
            return False

        message = normalise_progress_message(message)

        if not message or message == self.last_message:
            return False

        self.last_message = message
        self.callback(message)
        return True


def normalise_progress_message(message):
    message = str(message or "").strip()

    if not message:
        return ""

    message = " ".join(message.split())

    if not message.endswith((".", "!", "?")):
        message += "."

    return message
