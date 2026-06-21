import json

from tools.browser_tools import (
    get_current_browser_page,
    analyse_current_page,
    save_current_website,
)

from tools.browser_tab_tools import (
    close_current_browser_tab,
    close_browser_tabs_matching,
    switch_browser_tab,
)

from tools.screen_tools import (
    analyse_screen,
    take_screenshot,
    get_active_window_info,
)

from tools.screen_action_tools import act_on_screen

from tools.system_tools import (
    get_current_datetime,
    open_application,
    search_web,
    run_terminal_command,
    get_system_stats,
    set_volume,
)

from tools.youtube_tools import (
    search_youtube,
    play_youtube_video,
)

from tools.routine_tools import (
    create_or_update_routine,
    list_routines,
    delete_routine,
)

from tools.memory_tools import (
    remember_memory,
    list_memories,
    forget_memory,
)


# =========================
# JARVIS TOOL REGISTRY
# Every new Jarvis capability should be registered here
# so the AI brain can call it from intent.
# =========================

TOOL_DEFINITIONS = [
    # =========================
    # BROWSER TAB TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "close_current_browser_tab",
            "description": (
                "Close the active browser tab using Ctrl+W. Use this for requests like "
                "'close this tab', 'close the current tab', or 'shut this tab'. "
                "This is better than act_on_screen for tab closing."
            ),
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
            "name": "close_browser_tabs_matching",
            "description": (
                "Close browser tabs matching a website or text, such as YouTube, Gmail, Google, or TradingView. "
                "Use this for requests like 'close all YouTube tabs' or 'close every Gmail tab'."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "match_text": {
                        "type": "string",
                        "description": "Website/text to match in tab URL/title/domain. Example: youtube.",
                    },
                    "max_tabs": {
                        "type": "integer",
                        "description": "Maximum number of tabs to scan. Default 30.",
                    },
                },
                "required": ["match_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "switch_browser_tab",
            "description": (
                "Switch to a numbered browser tab using Ctrl+1 through Ctrl+9. "
                "Use this for 'open tab two', 'go to tab 2', or if speech transcribes tab as tap."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "tab_number": {
                        "type": "integer",
                        "description": "The tab number to switch to, starting from 1.",
                    },
                },
                "required": ["tab_number"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # GENERAL SCREEN ACTION TOOL
    # =========================
    {
        "type": "function",
        "function": {
            "name": "act_on_screen",
            "description": (
                "Use the current screen as context and either answer, recommend, ask, or click a visible target. "
                "Use it when the user refers to visible things, options, buttons, videos, food items, choices, pages, "
                "or says to do something based on what they are looking at. Do not use this for browser tab closing; "
                "use browser tab tools instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "The user's full natural instruction about what to do with the current screen.",
                    },
                    "allow_click": {
                        "type": "boolean",
                        "description": (
                            "True only when the user appears to want Jarvis to physically click/open/play/select something. "
                            "False when they only ask for advice, explanation, or a recommendation."
                        ),
                    },
                },
                "required": ["instruction", "allow_click"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # BROWSER / PAGE TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "get_current_browser_page",
            "description": (
                "Get the active browser page URL, domain, title, and browser window information. "
                "Use this when the user asks what website, page, URL, domain, or site they are on."
            ),
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
            "name": "analyse_current_page",
            "description": (
                "Analyse the current browser page using the URL, page title, and a screenshot. "
                "Use this when the user asks to check, inspect, read, explain, review, or look at "
                "the current website/page/browser tab."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "What the user wants to know about the current browser page.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "save_current_website",
            "description": (
                "Save the current active browser page to Jarvis memory under a user-provided name. "
                "Use this when the user says this is my website, remember this website, save this page, "
                "or gives a site/page name they want Jarvis to remember."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "site_name": {
                        "type": "string",
                        "description": "The name or alias the user wants to save for the current website/page.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional notes about the website/page.",
                    },
                },
                "required": ["site_name"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # YOUTUBE TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "search_youtube",
            "description": (
                "Search YouTube directly by opening YouTube search results. "
                "Use this when the user explicitly asks to search on YouTube for a query. "
                "Do not use this for visible videos already on the user's screen; use act_on_screen for that."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The YouTube search query.",
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
            "name": "play_youtube_video",
            "description": (
                "Search YouTube and play the most likely video result. "
                "Use this when the user asks to play a YouTube video by topic or creator, not when they refer "
                "to visible items on the current page/screen. For visible on-screen videos, use act_on_screen."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The video search query, including creator/channel if provided.",
                    }
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # SCREEN / VISION TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "analyse_screen",
            "description": (
                "Look at the user's current screen by taking a screenshot and analysing it. "
                "Use this for general screen questions, visual content, errors, popups, charts, "
                "code on screen, or when the user asks what they are looking at. "
                "If the user wants a choice made or something clicked, use act_on_screen instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "instruction": {
                        "type": "string",
                        "description": "What the user wants to know about the screen.",
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_screenshot",
            "description": "Take a screenshot of the user's current screen and save it locally.",
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
            "name": "get_active_window_info",
            "description": "Get the active window title and basic window information.",
            "parameters": {
                "type": "object",
                "properties": {},
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # SYSTEM TOOLS
    # =========================
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
            "description": (
                "Open an application or website by name, such as Chrome, YouTube, Notepad, VS Code, "
                "TradingView, Calculator, Discord, Spotify, or a known website."
            ),
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
            "description": (
                "Search the general web using Google in the default browser. "
                "Do not use this for YouTube-specific searches; use search_youtube or play_youtube_video instead."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web search query.",
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
            "description": (
                "Run a safe terminal command and return the output. "
                "Do not use this for destructive commands."
            ),
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
                        "enum": ["up", "down", "mute", "unmute"],
                    }
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # ROUTINE TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "create_or_update_routine",
            "description": (
                "Create or update a saved Jarvis routine. "
                "Use this when the user says things like create a routine, save this as my trading setup, "
                "update my trading mode, or change what a setup/mode should do."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "routine_name": {"type": "string"},
                    "display_name": {"type": "string"},
                    "trigger_phrases": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["url", "app", "volume", "wait", "message"],
                                },
                                "label": {"type": "string"},
                                "value": {"type": "string"},
                            },
                            "required": ["type", "label", "value"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["routine_name", "steps"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_routines",
            "description": "List all saved Jarvis routines.",
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
            "name": "delete_routine",
            "description": "Delete a saved Jarvis routine by name.",
            "parameters": {
                "type": "object",
                "properties": {
                    "routine_name": {"type": "string"}
                },
                "required": ["routine_name"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # MEMORY TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "remember_memory",
            "description": (
                "Save something useful to Jarvis memory. "
                "Use this when the user explicitly says remember, don't forget, from now on, going forward, "
                "when I say X I mean Y, I prefer X, or tells Jarvis a lasting preference."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "user_profile",
                            "preferences",
                            "aliases",
                            "workflow_rules",
                            "jarvis_rules",
                            "notes",
                        ],
                    },
                    "content": {"type": "string"},
                    "source": {
                        "type": "string",
                        "enum": ["explicit", "passive"],
                    },
                    "confidence": {"type": "number"},
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["category", "content"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_memories",
            "description": "List saved Jarvis memories, optionally by category.",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": [
                            "user_profile",
                            "preferences",
                            "aliases",
                            "workflow_rules",
                            "jarvis_rules",
                            "notes",
                        ],
                    }
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "forget_memory",
            "description": "Forget/delete a saved Jarvis memory that matches the user's query.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "user_profile",
                            "preferences",
                            "aliases",
                            "workflow_rules",
                            "jarvis_rules",
                            "notes",
                        ],
                    },
                },
                "required": ["query"],
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
        # =========================
        # BROWSER TAB TOOLS
        # =========================
        if tool_name == "close_current_browser_tab":
            return close_current_browser_tab()

        if tool_name == "close_browser_tabs_matching":
            return close_browser_tabs_matching(
                match_text=arguments.get("match_text", "youtube"),
                max_tabs=arguments.get("max_tabs", 30),
            )

        if tool_name == "switch_browser_tab":
            return switch_browser_tab(
                tab_number=arguments.get("tab_number")
            )

        # =========================
        # GENERAL SCREEN ACTION TOOL
        # =========================
        if tool_name == "act_on_screen":
            return act_on_screen(
                instruction=arguments.get("instruction", ""),
                allow_click=bool(arguments.get("allow_click", False)),
            )

        # =========================
        # BROWSER / PAGE TOOLS
        # =========================
        if tool_name == "get_current_browser_page":
            return get_current_browser_page()

        if tool_name == "analyse_current_page":
            return analyse_current_page(
                instruction=arguments.get("instruction")
            )

        if tool_name == "save_current_website":
            return save_current_website(
                site_name=arguments.get("site_name"),
                description=arguments.get("description"),
            )

        # =========================
        # YOUTUBE TOOLS
        # =========================
        if tool_name == "search_youtube":
            return search_youtube(arguments.get("query", ""))

        if tool_name == "play_youtube_video":
            return play_youtube_video(arguments.get("query", ""))

        # =========================
        # SCREEN / VISION TOOLS
        # =========================
        if tool_name == "analyse_screen":
            return analyse_screen(
                instruction=arguments.get("instruction")
            )

        if tool_name == "take_screenshot":
            return take_screenshot()

        if tool_name == "get_active_window_info":
            return get_active_window_info()

        # =========================
        # SYSTEM TOOLS
        # =========================
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

        # =========================
        # ROUTINE TOOLS
        # =========================
        if tool_name == "create_or_update_routine":
            return create_or_update_routine(
                routine_name=arguments.get("routine_name", ""),
                display_name=arguments.get("display_name"),
                trigger_phrases=arguments.get("trigger_phrases", []),
                steps=arguments.get("steps", []),
            )

        if tool_name == "list_routines":
            return list_routines()

        if tool_name == "delete_routine":
            return delete_routine(arguments.get("routine_name", ""))

        # =========================
        # MEMORY TOOLS
        # =========================
        if tool_name == "remember_memory":
            return remember_memory(
                category=arguments.get("category", "notes"),
                content=arguments.get("content", ""),
                source=arguments.get("source", "explicit"),
                confidence=arguments.get("confidence", 1.0),
                tags=arguments.get("tags", []),
            )

        if tool_name == "list_memories":
            return list_memories(
                category=arguments.get("category")
            )

        if tool_name == "forget_memory":
            return forget_memory(
                query=arguments.get("query", ""),
                category=arguments.get("category"),
            )

        return {
            "success": False,
            "message": f"Unknown tool: {tool_name}",
        }

    except Exception as error:
        return {
            "success": False,
            "message": f"Tool execution failed: {error}",
        }