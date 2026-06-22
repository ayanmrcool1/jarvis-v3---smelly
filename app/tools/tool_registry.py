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

from tools.web_research_tools import fast_web_research

from tools.hud_tools import control_hud_widget

from tools.todo_tools import (
    create_todo_list,
    add_todo_task,
    list_todo_tasks,
    complete_todo_task,
    remove_todo_task,
)

from tools.capability_gap_tools import (
    log_capability_gap,
    summarize_capability_gaps,
)

from tools.progress import ToolProgress


# =========================
# JARVIS TOOL REGISTRY
# Every new Jarvis capability should be registered here
# so the AI brain can call it from intent.
# =========================

TOOL_DEFINITIONS = [
    # =========================
    # CAPABILITY GAP TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "log_capability_gap",
            "description": (
                "Record a genuine Jarvis capability gap when the user request cannot be completed because no "
                "appropriate current tool exists, a requested capability is missing, or the user reports that "
                "Jarvis could not do something. Do not use this for ordinary clarifying questions, confirmation "
                "requests, safety blocks, or normal no-result situations."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "original_request": {
                        "type": "string",
                        "description": "The user's original request or feedback in their own words.",
                    },
                    "attempted": {
                        "type": "string",
                        "description": "What Jarvis tried, or what would have been needed if no tool was available.",
                    },
                    "failure_reason": {
                        "type": "string",
                        "description": "Why Jarvis could not complete it.",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "missing_tool",
                            "tool_failure",
                            "app_or_website",
                            "browser_control",
                            "screen_control",
                            "web_research",
                            "system_control",
                            "terminal",
                            "memory_or_data",
                            "routine",
                            "todo",
                            "audio_voice",
                            "external_dependency",
                            "other",
                        ],
                    },
                    "source": {
                        "type": "string",
                        "enum": [
                            "ai_reported",
                            "user_reported_gap",
                            "missing_tool",
                            "unsupported_request",
                        ],
                    },
                },
                "required": ["original_request", "attempted", "failure_reason", "category"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_capability_gaps",
            "description": (
                "Summarise recent capability gaps from data/capability_gaps.json. Use this when the user asks "
                "what Jarvis cannot do, what has failed recently, what capability gaps exist, or what needs "
                "to be improved."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "How many recent gaps to summarise. Default 5.",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "missing_tool",
                            "tool_failure",
                            "app_or_website",
                            "browser_control",
                            "screen_control",
                            "web_research",
                            "system_control",
                            "terminal",
                            "memory_or_data",
                            "routine",
                            "todo",
                            "audio_voice",
                            "external_dependency",
                            "other",
                        ],
                    },
                },
                "additionalProperties": False,
            },
        },
    },

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
                "Plan or perform a visible screen interaction, especially clicking/opening/playing/selecting a visible "
                "target. Use it when the user wants Jarvis to do an action on visible UI. Do not use this for visual "
                "questions, opinions, reading, or understanding what is on screen; use analyse_screen or "
                "analyse_current_page instead. Do not use this for browser tab closing; use browser tab tools instead. "
                "Do not use this to manage Jarvis internal HUD widgets or the built-in to-do list; use HUD or to-do tools."
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
            "name": "fast_web_research",
            "description": (
                "Research current web information without opening a visible browser. Use this when the user asks "
                "for current, recent, live, online, best-right-now, prices, recommendations, comparisons, news, "
                "which option to buy, or asks you to check/look into something and tell them the answer, and they "
                "did not ask to show/open it in the browser. Return a short spoken answer with sources in separate "
                "structured fields. Do not use this for visible browser searches, app opening, current "
                "screen/page analysis, or clicking visible UI."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The web research question or search topic.",
                    },
                    "max_sources": {
                        "type": "integer",
                        "description": "Maximum sources to return. Default 5.",
                    },
                    "search_context_size": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Search context size. Default low for fast spoken answers.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
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
                "Use this for visual questions, opinions, comparisons, reading, errors, popups, charts, "
                "code on screen, or when the user asks what they are looking at, how something looks, "
                "whether something looks good, or what you think of visible content. "
                "This tool never clicks. If the user wants a visible action performed, use act_on_screen instead."
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
    # HUD WIDGET TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "control_hud_widget",
            "description": (
                "Open or close dynamic widgets on the Jarvis HUD. Use this when the user asks to show, hide, "
                "open, close, or clear HUD panels such as the to-do list, conversation/chat, system status, "
                "or now playing/Spotify. This changes the Jarvis interface only; do not use it for answering "
                "normal questions or for controlling apps outside the HUD."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {
                        "type": "string",
                        "enum": ["open", "close", "close_all"],
                        "description": "Whether to open one widget, close one widget, or close every widget.",
                    },
                    "widget_type": {
                        "type": "string",
                        "enum": ["todo", "chat", "system", "spotify"],
                        "description": "Widget to control. Omit for close_all.",
                    },
                },
                "required": ["action"],
                "additionalProperties": False,
            },
        },
    },

    # =========================
    # TODO WIDGET / DATA TOOLS
    # =========================
    {
        "type": "function",
        "function": {
            "name": "create_todo_list",
            "description": (
                "Create or prepare Jarvis's built-in HUD to-do list. Use this when the user asks to create, "
                "open, prepare, or start a Jarvis to-do list. This is an internal Jarvis data/widget feature, "
                "not an external app and not a visible screen click."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reset_existing": {
                        "type": "boolean",
                        "description": "True only if the user explicitly asks to reset or clear the existing list.",
                    },
                    "confirmed": {
                        "type": "boolean",
                        "description": "True only if the user explicitly confirms clearing existing tasks.",
                    },
                    "open_widget": {
                        "type": "boolean",
                        "description": "Whether to show the to-do widget after creating/preparing the list. Default true.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_todo_task",
            "description": (
                "Add a task to Jarvis's built-in to-do list stored in data/todo.json. Use this for requests "
                "like adding, saving, or putting an item on the user's to-do list. Do not use act_on_screen "
                "for built-in to-do list changes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_text": {
                        "type": "string",
                        "description": "The task to add.",
                    },
                    "open_widget": {
                        "type": "boolean",
                        "description": "Whether to show/update the to-do widget after adding. Default true.",
                    },
                },
                "required": ["task_text"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_todo_tasks",
            "description": (
                "List Jarvis's built-in to-do tasks and optionally show the to-do HUD widget. Use this when "
                "the user asks what is on their to-do list or asks to show their to-do list."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "include_completed": {
                        "type": "boolean",
                        "description": "Whether completed tasks should be included.",
                    },
                    "open_widget": {
                        "type": "boolean",
                        "description": "Whether to show/update the to-do widget. Default true.",
                    },
                },
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "complete_todo_task",
            "description": (
                "Mark a task on Jarvis's built-in to-do list as done. Match by task number, id, exact text, "
                "or a clear unique text fragment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_ref": {
                        "type": "string",
                        "description": "Task number, id, exact task text, or unique text fragment.",
                    },
                    "open_widget": {
                        "type": "boolean",
                        "description": "Whether to show/update the to-do widget after completing. Default true.",
                    },
                },
                "required": ["task_ref"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "remove_todo_task",
            "description": (
                "Remove a task from Jarvis's built-in to-do list. Match by task number, id, exact text, "
                "or a clear unique text fragment."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "task_ref": {
                        "type": "string",
                        "description": "Task number, id, exact task text, or unique text fragment.",
                    },
                    "open_widget": {
                        "type": "boolean",
                        "description": "Whether to show/update the to-do widget after removing. Default true.",
                    },
                },
                "required": ["task_ref"],
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
                "TradingView, Calculator, Discord, Spotify, ChatGPT, installed Start Menu apps, "
                "desktop shortcuts, or a known website."
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
                "Open a visible Google search in the user's real default browser. Use this when the user asks "
                "to search Google, show results, pull up results, open images/photos/pictures, or open a browser search. Do not use this "
                "for answering current web questions silently; use fast_web_research instead. Do not use this "
                "for YouTube-specific searches; use search_youtube or play_youtube_video instead."
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
            "description": (
                "Get CPU, RAM, disk, and battery usage stats for a spoken answer. "
                "If the user asks to show, display, open, or pull up system stats/status as a HUD panel, "
                "use control_hud_widget with widget_type system instead."
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
                "Use this only when the user clearly wants a durable preference, alias, workflow rule, "
                "profile detail, or Jarvis behavior rule stored for the future. Do not use this for recall "
                "questions like 'do you remember...' unless the user is actually asking you to save something."
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
            "description": (
                "List saved long-term Jarvis memories, optionally by category. Use this when the user asks "
                "to list/show saved memories. For normal recall questions, answer from conversation context "
                "and saved memory context first instead of dumping every memory."
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
            "description": (
                "Forget/delete a saved Jarvis memory that matches the user's query. Use only when the user "
                "clearly wants a saved memory removed, not when they ask whether you remember something."
            ),
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


def execute_tool_call(tool_name, arguments_json, progress_callback=None):
    """
    Executes a tool call requested by the AI.
    Returns a dictionary result.
    """

    progress = ToolProgress(progress_callback, tool_name=tool_name)

    try:
        arguments = json.loads(arguments_json or "{}")
    except json.JSONDecodeError:
        return {
            "success": False,
            "invalid_tool_arguments": True,
            "message": "Invalid tool arguments.",
        }

    try:
        # =========================
        # CAPABILITY GAP TOOLS
        # =========================
        if tool_name == "log_capability_gap":
            return log_capability_gap(
                original_request=arguments.get("original_request", ""),
                attempted=arguments.get("attempted", ""),
                failure_reason=arguments.get("failure_reason", ""),
                category=arguments.get("category", "other"),
                source=arguments.get("source", "ai_reported"),
            )

        if tool_name == "summarize_capability_gaps":
            return summarize_capability_gaps(
                limit=arguments.get("limit", 5),
                category=arguments.get("category"),
            )

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
        if tool_name == "fast_web_research":
            return fast_web_research(
                query=arguments.get("query", ""),
                max_sources=arguments.get("max_sources", 5),
                search_context_size=arguments.get("search_context_size", "low"),
            )

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
        # HUD WIDGET TOOLS
        # =========================
        if tool_name == "control_hud_widget":
            return control_hud_widget(
                action=arguments.get("action", ""),
                widget_type=arguments.get("widget_type"),
            )

        # =========================
        # TODO WIDGET / DATA TOOLS
        # =========================
        if tool_name == "create_todo_list":
            return create_todo_list(
                reset_existing=bool(arguments.get("reset_existing", False)),
                confirmed=bool(arguments.get("confirmed", False)),
                open_widget=arguments.get("open_widget", True),
            )

        if tool_name == "add_todo_task":
            return add_todo_task(
                task_text=arguments.get("task_text", ""),
                open_widget=arguments.get("open_widget", True),
            )

        if tool_name == "list_todo_tasks":
            return list_todo_tasks(
                include_completed=bool(arguments.get("include_completed", False)),
                open_widget=arguments.get("open_widget", True),
            )

        if tool_name == "complete_todo_task":
            return complete_todo_task(
                task_ref=arguments.get("task_ref", ""),
                open_widget=arguments.get("open_widget", True),
            )

        if tool_name == "remove_todo_task":
            return remove_todo_task(
                task_ref=arguments.get("task_ref", ""),
                open_widget=arguments.get("open_widget", True),
            )

        # =========================
        # SYSTEM TOOLS
        # =========================
        if tool_name == "get_current_datetime":
            return get_current_datetime()

        if tool_name == "open_application":
            return open_application(
                arguments.get("app_name", ""),
                progress_callback=progress.emit,
            )

        if tool_name == "search_web":
            return search_web(arguments.get("query", ""))

        if tool_name == "run_terminal_command":
            command = arguments.get("command", "")

            if not is_safe_terminal_command(command):
                return {
                    "success": False,
                    "blocked_by_safety": True,
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
