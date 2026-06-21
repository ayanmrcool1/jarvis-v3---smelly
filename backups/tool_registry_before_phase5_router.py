import json

from tools.system_tools import (
    get_current_datetime,
    open_application,
    search_web,
    run_terminal_command,
    get_system_stats,
    set_volume,
)


# =========================
# JARVIS PHASE 4 TOOL REGISTRY
# =========================

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_datetime",
            "description": "Get the current local date and time from the computer.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "open_application",
            "description": "Open an application or website by name, such as Chrome, Notepad, VS Code, TradingView, Calculator, Discord, Spotify.",
            "parameters": {
                "type": "object",
                "properties": {
                    "app_name": {
                        "type": "string",
                        "description": "The name of the app or website to open.",
                    }
                },
                "required": ["app_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web using the default browser.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_terminal_command",
            "description": "Run a safe terminal command and return the output. Do not use this for destructive commands.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The terminal command to run.",
                    }
                },
                "required": ["command"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_stats",
            "description": "Get CPU, RAM, disk, and battery usage stats.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "set_volume",
            "description": "Control system volume. Use this for volume up, volume down, mute, or unmute.",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["up", "down", "mute"],
                        "description": "The volume action to perform.",
                    }
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },
]


BLOCKED_TERMINAL_KEYWORDS = [
    "del ",
    "erase ",
    "format ",
    "shutdown",
    "restart",
    "rmdir",
    "remove-item",
    "rm ",
    "rd ",
    "diskpart",
]


def is_safe_terminal_command(command):
    """
    Basic safety filter so the AI cannot casually delete files or shut down the PC.
    Later we can add a confirmation system for dangerous commands.
    """
    clean_command = command.lower().strip()

    for blocked in BLOCKED_TERMINAL_KEYWORDS:
        if blocked in clean_command:
            return False

    return True


def execute_tool_call(tool_name, arguments_json):
    """
    Executes a tool call requested by the AI.
    Returns a dictionary result.
    """
    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return {
            "success": False,
            "message": "Invalid tool arguments.",
        }

    try:
        if tool_name == "get_current_datetime":
            return get_current_datetime()

        if tool_name == "open_application":
            return open_application(arguments.get("app_name", ""))

        if tool_name == "search_web":
            return search_web(arguments.get("query", ""))

        if tool_name == "run_terminal_command":
            command = arguments.get("command", "")

            if not is_safe_terminal_command(command):
                return {
                    "success": False,
                    "message": "That terminal command looks potentially destructive, so I did not run it.",
                }

            return run_terminal_command(command)

        if tool_name == "get_system_stats":
            return get_system_stats()

        if tool_name == "set_volume":
            return set_volume(arguments.get("action", ""))

        return {
            "success": False,
            "message": f"Unknown tool: {tool_name}",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Tool execution failed: {error}",
        }