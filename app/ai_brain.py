import os
import json
import queue
import threading
import time
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from speech_style import humanise_jarvis_response
from tools.memory_tools import build_memory_context
from tools.user_profile_tools import build_user_profile_context
from tools.tool_registry import TOOL_DEFINITIONS, execute_tool_call
from tools.capability_gap_tools import record_tool_failure_if_gap


# =========================
# JARVIS AI BRAIN
# AI chat + streaming + tool calling
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


SYSTEM_PROMPT = """
You are Jarvis, a personal AI assistant running locally on the user's Windows 10 computer.

Core architecture:
- You are the main intent-understanding layer.
- Do not rely on exact trigger words.
- Infer what the user wants from natural speech, context, and available tools.
- Local routing only handles fast obvious shortcuts; you decide the real intent when tools are available.

Personality:
- Intelligent.
- Concise.
- Calm.
- Direct.
- Helpful.
- Slightly friendly, like a capable personal butler.
- Not overly chatty.
- Not robotic.
- Your name is Jarvis. Do not spell it out as J-A-R-V-I-S.

Current capabilities:
- You can respond to the user's transcribed speech.
- You can speak aloud through the configured TTS voice.
- You can open apps/websites, search the web, search/play YouTube videos, run safe terminal commands, control volume, get system stats, and get date/time.
- You can create, update, list, and delete routines.
- You can remember, list, and forget useful long-term information.
- You can maintain a per-user runtime profile for lightweight personalisation.
- You can inspect the screen, inspect browser pages, and act on visible screen content.
- You can control browser tabs with hotkeys.
- You can do fast web research for current online information without opening a visible browser.
- You can open and close dynamic HUD widgets such as to-do, chat, system status, and now playing.
- You can create, add to, list, complete, and remove tasks from Jarvis's built-in to-do list.
- You can log and summarise recent capability gaps when requests fail or a missing capability is reported.

Speed and speech rules:
- Be extremely concise by default.
- For casual conversation, reply in ONE short sentence only.
- Do not add follow-up questions like “What do you need?”, “Anything else?”, or “How can I help?” unless the user clearly asks for options.
- Do not add filler after answering.
- Use short spoken answers because this assistant speaks aloud.
- Avoid multi-sentence responses unless the user asks for detail.

Action timing:
- When using tools, acknowledge briefly first, then perform the action.
- Do not overtalk while acting.
- A short phrase like “On it.”, “I’ll check.”, or “Opening it now.” is enough.
- For successful simple actions, avoid repeating yourself after the tool finishes.

AI-first tool behavior:
- If the user asks you to do something on the computer, use the most relevant tool.
- If the user wants browser tabs closed or switched, use browser tab tools, not screen vision.
- For normal stable/general questions, answer directly.
- Use fast_web_research for current, recent, online, price, recommendation, comparison, news, "best right now", "check out what the best is", "find me the best", "compare", or "which should I buy" requests when the user wants an answer and did not ask to open/show a browser.
- Use search_web when the user explicitly wants a visible browser search, such as search Google, show me, pull up, open images/photos/pictures, or open a tab and search.
- Use open_application when the user wants to open an app or known website.
- Use close_current_browser_tab for “close this tab” or “close current tab”.
- Use close_browser_tabs_matching for “close all YouTube tabs” or “close every Gmail tab”.
- Use switch_browser_tab for “open tab two”, “go to tab 2”, or when speech transcribes tab as tap.
- If the user asks a visual question, opinion, comparison, reading, or asks what is visible on the screen, use analyse_screen or analyse_current_page.
- Visual questions include "does this look good", "what do you think of this", "which one looks better", "can you read this", and "what am I looking at".
- Use act_on_screen only when the user wants a visible action performed, such as click, select, open, play, press, choose, or activate something on the screen.
- Do not require exact action words. Infer whether the intent is visual understanding or visible interaction.
- If the user wants you to physically do it, open it, play it, select it, go with it, choose one, or click something visible, call act_on_screen with allow_click=true.
- If the user only asks what is visible, how it looks, what you think, whether it looks good, or asks for an explanation, use analyse_screen or analyse_current_page instead.
- If the user asks what website/page/URL they are on, use get_current_browser_page.
- Use control_hud_widget when the user wants to show, hide, open, close, or clear Jarvis HUD panels/widgets.
- If the user says "show", "display", "open", or "pull up" system stats/status, use control_hud_widget with widget_type system. If they ask "what is my CPU/RAM/system usage", use get_system_stats.
- Use the to-do tools for Jarvis's built-in to-do list: create_todo_list, add_todo_task, list_todo_tasks, complete_todo_task, and remove_todo_task.
- Do not use act_on_screen to add, complete, remove, or create items in Jarvis's built-in to-do list.
- If a tool fails, briefly say what failed.
- Do not claim you opened, clicked, searched, analysed, or changed something unless a tool result confirms it.
- If no available tool or current capability can complete the user's request, call log_capability_gap instead of only apologising.
- If the user reports that Jarvis could not or cannot do something, use judgment and call log_capability_gap when it is a real capability gap.
- If the user asks what Jarvis cannot do, what has failed recently, or what needs improvement, call summarize_capability_gaps.
- Do not log normal clarification needs, confirmation requests, safety refusals, empty/no-result states, or temporary context issues as capability gaps unless they reveal a missing capability.

Examples:
- "What are the best wireless headphones right now?" -> fast_web_research.
- "Find wireless headphones under $50 and compare the best options" -> fast_web_research.
- "Can you check out what the best wireless headphones are?" -> fast_web_research.
- "Search Google for wireless headphones" -> search_web.
- "Show me wireless headphones" -> search_web.
- "Open pictures of wireless headphones" -> search_web.
- “Close this tab” -> close_current_browser_tab.
- “Close all YouTube tabs” -> close_browser_tabs_matching, match_text: youtube.
- “Open tab two” -> switch_browser_tab, tab_number: 2.
- “Play something from this page” -> act_on_screen, allow_click=true.
- “Does this look good?” -> analyse_screen.
- “What do you think of this on my screen?” -> analyse_screen.
- “Which option looks better?” -> analyse_screen.
- “Which food option should I pick?” -> analyse_screen.
- “Choose one of these options” -> act_on_screen, allow_click=true.
- “Click the best one” -> act_on_screen, allow_click=true.
- “Read this error” -> analyse_screen.
- “What website am I on?” -> get_current_browser_page.
- "Show my to-do list" -> control_hud_widget, action: open, widget_type: todo.
- "Show system stats" -> control_hud_widget, action: open, widget_type: system.
- "What is my CPU usage?" -> get_system_stats.
- "Create a new to-do list" -> create_todo_list.
- "Add fix the bugs in drivers to my to-do list" -> add_todo_task, task_text: fix the bugs in drivers.
- "Mark fix the bugs in drivers as done" -> complete_todo_task.
- "Hide the chat" -> control_hud_widget, action: close, widget_type: chat.
- "Close all widgets" -> control_hud_widget, action: close_all.

YouTube behavior:
- If the user asks to search on YouTube for a topic, call search_youtube.
- If the user asks to play a YouTube video by topic or creator and is NOT referring to visible on-screen options, call play_youtube_video.
- For YouTube playback/action requests, if the user refers to a visible video on this page/screen, use act_on_screen. For visual questions about screen content, use analyse_screen instead.
- Never turn YouTube requests into Google searches with site:youtube.com.

Search behavior:
- Do NOT use search_web for ordinary general questions.
- Use fast_web_research for current/latest/live web information, recommendations, comparisons, current prices, current options, or "check out/find me the best" requests when the user wants an answer.
- Only use search_web when the user explicitly asks to search, google, look up, show, pull up, open images/photos/pictures, or open visible results in a browser.
- If the request is YouTube-specific, use search_youtube or play_youtube_video instead.
- If the user asks something stable like travel duration, definitions, explanations, or simple facts, answer directly without search_web.

Safety:
- Do not click irreversible or risky actions such as buying, paying, sending, deleting, submitting, confirming, accepting, or handling passwords unless the user gives clear explicit confirmation.
- For uncertain screen actions, ask briefly or recommend instead of clicking.
- For future email, calendar, and messaging actions, prefer official API tools when available; use current page/screen tools only when the user wants visible UI control.

Runtime profile behavior:
- Use the runtime user profile as soft context for tone, vocabulary, habits, workflows, and project context.
- The runtime profile guides your judgment, but it does not override the current request, safety, or common sense.
- Prefer remember_user_profile_detail for durable personalisation such as response preferences, repeated corrections, vocabulary, workflows, project context, and Jarvis behavior guidance.
- Use legacy memory tools for general long-term facts and notes that are not specifically user personalisation.
- Do not save temporary comments, one-off moods, or sensitive personal information unless the user clearly wants it remembered.
- A new active user may have a blank profile; do not assume details from another user.

Response style:
- By default, reply in one short sentence unless the user asks for detail.
- Avoid robotic labels like “preferences:”, “user_profile:”, or “tool result”.
- Avoid overly formal phrases such as “How can I assist you today?”.
- Good examples: “Of course.”, “Done.”, “Got it.”, “I’ve got you.”, “That’s handled.”
- Stay smooth, concise, and useful.

Memory behavior:
- Use the runtime profile and saved memory when relevant.
- Decide memory intent from meaning, not from exact words.
- Recall questions like "do you remember what we discussed" are questions, not save-memory requests.
- Save personalisation with remember_user_profile_detail when the user clearly wants a durable preference, repeated correction, vocabulary, workflow, project context, or Jarvis behavior rule stored for the future.
- Save legacy memory with remember_memory for useful general long-term information such as saved websites, broad notes, or aliases that are not specifically active-user personalisation.
- Do not save random temporary comments.
- Do not save sensitive personal information unless the user clearly asks you to remember it.
"""


class JarvisBrain:
    """
    Handles communication with OpenAI.
    Supports normal chat, streaming chat, tool calling, and streaming tool-calling.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError(
                f"OPENAI_API_KEY is missing. Add it to your {ENV_PATH} file."
            )

        self.client = OpenAI(api_key=self.api_key)

        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]

        print(f"OpenAI brain loaded using model: {self.model_name}")

    def _build_user_message(self, user_text):
        now = datetime.now().strftime("%A, %d %B %Y, %I:%M %p")
        user_profile_context = build_user_profile_context()
        memory_context = build_memory_context()

        return f"""
Current system time: {now}

Runtime user profile:
{user_profile_context}

Saved Jarvis memory:
{memory_context}

User said:
{user_text}
"""

    def _direct_tool_response(self, tool_name, result):
        if not isinstance(result, dict):
            return "Done."

        direct_message_tools = [
            "open_application",
            "fast_web_research",
            "search_web",
            "search_youtube",
            "play_youtube_video",
            "act_on_screen",
            "close_current_browser_tab",
            "close_browser_tabs_matching",
            "switch_browser_tab",
            "set_volume",
            "create_or_update_routine",
            "list_routines",
            "delete_routine",
            "remember_memory",
            "list_memories",
            "forget_memory",
            "remember_user_profile_detail",
            "list_user_profile",
            "forget_user_profile_detail",
            "analyse_screen",
            "take_screenshot",
            "get_active_window_info",
            "get_current_browser_page",
            "analyse_current_page",
            "save_current_website",
            "control_hud_widget",
            "create_todo_list",
            "add_todo_task",
            "list_todo_tasks",
            "complete_todo_task",
            "remove_todo_task",
            "log_capability_gap",
            "summarize_capability_gaps",
        ]

        if tool_name in direct_message_tools:
            message = (
                result.get("spoken_message")
                or result.get("message")
                or "Done."
            )
            return humanise_jarvis_response(message)

        if tool_name == "get_system_stats":
            if result.get("success"):
                cpu = result.get("cpu_percent")
                ram = result.get("ram_percent")
                disk = result.get("disk_percent")
                battery = result.get("battery_percent")

                if battery is None:
                    text = (
                        f"CPU is at {cpu} percent, RAM is at {ram} percent, "
                        f"and disk usage is at {disk} percent."
                    )
                else:
                    text = (
                        f"CPU is at {cpu} percent, RAM is at {ram} percent, "
                        f"disk usage is at {disk} percent, and battery is at {battery} percent."
                    )

                return humanise_jarvis_response(text)

            return humanise_jarvis_response(
                result.get("message", "I could not get system stats.")
            )

        if tool_name == "get_current_datetime":
            return humanise_jarvis_response(result.get("message", "Done."))

        return None

    def _record_tool_failure_gap(self, user_text, tool_name, arguments_json, tool_result):
        try:
            gap_result = record_tool_failure_if_gap(
                original_request=user_text,
                tool_name=tool_name,
                arguments_json=arguments_json,
                result=tool_result,
            )

            if gap_result and gap_result.get("success"):
                gap = gap_result.get("gap", {})
                print(
                    "Capability gap logged: "
                    f"{gap.get('category')} | {gap.get('original_request')}"
                )

        except Exception as error:
            print(f"Capability gap logging warning: {error}")

    def _tool_start_phrase(self, tool_name, arguments_json="", user_text=""):
        try:
            arguments = json.loads(arguments_json or "{}")
        except Exception:
            arguments = {}

        clean_user_text = (user_text or "").lower()

        if tool_name == "close_current_browser_tab":
            return "Closing it."

        if tool_name == "close_browser_tabs_matching":
            match_text = str(arguments.get("match_text", "") or "").strip()

            if match_text:
                return f"Closing {match_text} tabs."

            return "Closing those tabs."

        if tool_name == "switch_browser_tab":
            tab_number = arguments.get("tab_number")

            if tab_number:
                return f"Switching to tab {tab_number}."

            return "Switching tabs."

        if tool_name == "act_on_screen":
            allow_click = bool(arguments.get("allow_click", False))

            if allow_click:
                if "close" in clean_user_text and "tab" in clean_user_text:
                    return "Closing it."
                if "video" in clean_user_text or "youtube" in clean_user_text:
                    return "On it — choosing one now."
                if "food" in clean_user_text or "order" in clean_user_text or "menu" in clean_user_text:
                    return "I’ll take a look."
                return "On it."

            return "Let me take a look."

        if tool_name == "fast_web_research":
            return "I'll check the web."

        if tool_name == "analyse_screen":
            return "I’ll check the screen."

        if tool_name == "analyse_current_page":
            return "I’ll check the page."

        if tool_name == "get_current_browser_page":
            return "Checking the page."

        if tool_name == "take_screenshot":
            return "Taking a screenshot."

        if tool_name == "open_application":
            app_name = str(arguments.get("app_name", "")).strip()

            if app_name:
                return f"Opening {app_name}."

            return "Opening it."

        if tool_name == "search_youtube":
            return "Searching YouTube."

        if tool_name == "play_youtube_video":
            return "Finding a video."

        if tool_name == "search_web":
            return "Searching now."

        if tool_name == "run_terminal_command":
            return "Running it now."

        if tool_name == "get_system_stats":
            return "Checking system stats."

        if tool_name == "set_volume":
            return None

        if tool_name in [
            "create_or_update_routine",
            "list_routines",
            "delete_routine",
            "remember_memory",
            "list_memories",
            "forget_memory",
            "save_current_website",
        ]:
            return None

        return "On it."

    def _should_speak_before_tool(self, tool_name):
        pre_speech_tools = [
            "act_on_screen",
            "fast_web_research",
            "analyse_screen",
            "analyse_current_page",
            "get_current_browser_page",
            "take_screenshot",
            "open_application",
            "search_youtube",
            "play_youtube_video",
            "search_web",
            "run_terminal_command",
            "get_system_stats",
            "close_current_browser_tab",
            "close_browser_tabs_matching",
            "switch_browser_tab",
        ]

        return tool_name in pre_speech_tools

    def _should_suppress_final_response(self, tool_name, result, pre_tool_phrase):
        """
        Prevents double-speaking:
        Example: 'Opening YouTube.' then 'Of course — opening YouTube.'
        """

        if not pre_tool_phrase:
            return False

        if not isinstance(result, dict):
            return False

        if not result.get("success"):
            return False

        simple_success_tools = [
            "open_application",
            "search_web",
            "search_youtube",
            "play_youtube_video",
            "take_screenshot",
            "close_current_browser_tab",
            "close_browser_tabs_matching",
            "switch_browser_tab",
        ]

        if tool_name in simple_success_tools:
            return True

        if tool_name == "act_on_screen" and result.get("clicked"):
            return True

        return False

    def _execute_tool_call_with_progress(self, tool_name, arguments_json, spoken_progress_parts=None):
        """
        Runs a tool in a worker thread so progress callbacks can be yielded to TTS.
        The final tool result remains the authoritative outcome.
        """

        progress_queue = queue.Queue()
        result_box = {}

        def progress_callback(message):
            message = str(message or "").strip()

            if not message:
                return

            if not message.endswith((".", "!", "?")):
                message += "."

            print(f"[PROFILE] Tool progress event: {tool_name}: {message}")
            progress_queue.put(message)

        def run_tool():
            tool_start = time.perf_counter()
            print(f"[PROFILE] Tool execution started: {tool_name}")

            try:
                result_box["result"] = execute_tool_call(
                    tool_name,
                    arguments_json,
                    progress_callback=progress_callback,
                )
            except Exception as error:
                result_box["result"] = {
                    "success": False,
                    "message": f"Tool execution failed: {error}",
                }
            finally:
                elapsed = time.perf_counter() - tool_start
                result_box["elapsed"] = elapsed
                print(f"[PROFILE] Tool execution finished: {tool_name}: {elapsed:.2f}s")
                progress_queue.put(None)

        worker = threading.Thread(target=run_tool, daemon=True)
        worker.start()

        while True:
            try:
                message = progress_queue.get(timeout=0.1)
            except queue.Empty:
                if not worker.is_alive():
                    break
                continue

            if message is None:
                break

            if spoken_progress_parts is not None:
                spoken_progress_parts.append(message)

            yield message + " "

        worker.join()

        return result_box.get(
            "result",
            {
                "success": False,
                "message": "Tool execution ended without a result.",
            },
        )

    def ask(self, user_text, max_tokens=70):
        if not user_text.strip():
            return ""

        user_message = {
            "role": "user",
            "content": self._build_user_message(user_text),
        }

        self.messages.append(user_message)

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.35,
                max_tokens=max_tokens,
            )

            jarvis_response = response.choices[0].message.content.strip()

            self.messages.append(
                {
                    "role": "assistant",
                    "content": jarvis_response,
                }
            )

            return jarvis_response

        except Exception as error:
            return f"AI brain error: {error}"

    def stream_ask(self, user_text, max_tokens=80):
        if not user_text.strip():
            return

        user_message = {
            "role": "user",
            "content": self._build_user_message(user_text),
        }

        self.messages.append(user_message)

        collected_text = []

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.3,
                max_tokens=max_tokens,
                stream=True,
            )

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta and delta.content:
                    collected_text.append(delta.content)
                    yield delta.content

            final_text = "".join(collected_text).strip()

            if final_text:
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )

        except Exception as error:
            yield f"AI brain error: {error}"

    def ask_with_tools(self, user_text, max_tokens=120, forced_tool_name=None):
        if not user_text.strip():
            return ""

        user_message = {
            "role": "user",
            "content": self._build_user_message(user_text),
        }

        self.messages.append(user_message)

        tool_choice = "auto"

        if forced_tool_name:
            tool_choice = {
                "type": "function",
                "function": {
                    "name": forced_tool_name,
                },
            }

        try:
            first_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                tool_choice=tool_choice,
                temperature=0.2,
                max_tokens=max_tokens,
            )

            assistant_message = first_response.choices[0].message

            self.messages.append(
                assistant_message.model_dump(exclude_none=True)
            )

            if not assistant_message.tool_calls:
                final_text = assistant_message.content or ""

                if final_text.strip():
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": final_text.strip(),
                        }
                    )

                    return final_text.strip()

                return "I understood, but I did not use a tool."

            tool_results = []

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments

                print(f"Tool requested: {tool_name}")
                print(f"Tool arguments: {tool_args}")

                tool_result = execute_tool_call(tool_name, tool_args)

                print(f"Tool result: {tool_result}")

                self._record_tool_failure_gap(
                    user_text=user_text,
                    tool_name=tool_name,
                    arguments_json=tool_args,
                    tool_result=tool_result,
                )

                tool_results.append(
                    {
                        "tool_name": tool_name,
                        "result": tool_result,
                    }
                )

                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(tool_result),
                    }
                )

            if len(tool_results) == 1:
                tool_name = tool_results[0]["tool_name"]
                result = tool_results[0]["result"]

                direct_response = self._direct_tool_response(tool_name, result)

                if direct_response:
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": direct_response,
                        }
                    )

                    return direct_response

            final_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.2,
                max_tokens=max_tokens,
            )

            final_text = final_response.choices[0].message.content.strip()

            self.messages.append(
                {
                    "role": "assistant",
                    "content": final_text,
                }
            )

            return final_text

        except Exception as error:
            return f"AI tool-calling error: {error}"

    def stream_ask_with_tools(self, user_text, max_tokens=150, forced_tool_name=None):
        if not user_text.strip():
            return

        user_message = {
            "role": "user",
            "content": self._build_user_message(user_text),
        }

        working_messages = self.messages + [user_message]
        self.messages.append(user_message)

        tool_choice = "auto"

        if forced_tool_name:
            tool_choice = {
                "type": "function",
                "function": {
                    "name": forced_tool_name,
                },
            }

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=working_messages,
                tools=TOOL_DEFINITIONS,
                tool_choice=tool_choice,
                temperature=0.2,
                max_tokens=max_tokens,
                stream=True,
            )

            collected_text = []
            tool_calls = {}

            for chunk in stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    collected_text.append(delta.content)
                    yield delta.content

                if delta.tool_calls:
                    for tool_call_delta in delta.tool_calls:
                        index = tool_call_delta.index

                        if index not in tool_calls:
                            tool_calls[index] = {
                                "id": "",
                                "type": "function",
                                "function": {
                                    "name": "",
                                    "arguments": "",
                                },
                            }

                        if tool_call_delta.id:
                            tool_calls[index]["id"] = tool_call_delta.id

                        if tool_call_delta.function:
                            if tool_call_delta.function.name:
                                tool_calls[index]["function"]["name"] += (
                                    tool_call_delta.function.name
                                )

                            if tool_call_delta.function.arguments:
                                tool_calls[index]["function"]["arguments"] += (
                                    tool_call_delta.function.arguments
                                )

            if not tool_calls:
                final_text = "".join(collected_text).strip()

                if final_text:
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": final_text,
                        }
                    )
                else:
                    fallback_text = "I heard you, but I’m not sure what to do with that."
                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": fallback_text,
                        }
                    )
                    yield fallback_text

                return

            assistant_tool_calls = []
            tool_result_messages = []
            direct_responses = []
            spoken_pre_tool_parts = []
            spoken_progress_parts = []
            suppressed_final_response = False

            for index in sorted(tool_calls.keys()):
                call = tool_calls[index]

                tool_name = call["function"]["name"]
                arguments_json = call["function"]["arguments"] or "{}"
                tool_call_id = call["id"] or f"call_{index}"

                print(f"Tool requested: {tool_name}")
                print(f"Tool arguments: {arguments_json}")

                pre_tool_phrase = self._tool_start_phrase(
                    tool_name=tool_name,
                    arguments_json=arguments_json,
                    user_text=user_text,
                )

                if pre_tool_phrase and self._should_speak_before_tool(tool_name):
                    spoken_phrase = pre_tool_phrase.strip()

                    if spoken_phrase and not spoken_phrase.endswith((".", "!", "?")):
                        spoken_phrase += "."

                    print(f"Pre-tool speech: {spoken_phrase}")
                    spoken_pre_tool_parts.append(spoken_phrase)
                    yield spoken_phrase + " "

                tool_result = yield from self._execute_tool_call_with_progress(
                    tool_name,
                    arguments_json,
                    spoken_progress_parts=spoken_progress_parts,
                )

                print(f"Tool result: {tool_result}")

                self._record_tool_failure_gap(
                    user_text=user_text,
                    tool_name=tool_name,
                    arguments_json=arguments_json,
                    tool_result=tool_result,
                )

                assistant_tool_call = {
                    "id": tool_call_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": arguments_json,
                    },
                }

                tool_message = {
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "name": tool_name,
                    "content": json.dumps(tool_result),
                }

                assistant_tool_calls.append(assistant_tool_call)
                tool_result_messages.append(tool_message)

                direct_response = self._direct_tool_response(tool_name, tool_result)

                if direct_response:
                    if self._should_suppress_final_response(
                        tool_name=tool_name,
                        result=tool_result,
                        pre_tool_phrase=pre_tool_phrase,
                    ):
                        suppressed_final_response = True
                    else:
                        direct_responses.append(direct_response.strip())

            assistant_tool_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": assistant_tool_calls,
            }

            self.messages.append(assistant_tool_message)
            self.messages.extend(tool_result_messages)

            working_messages.append(assistant_tool_message)
            working_messages.extend(tool_result_messages)

            if direct_responses:
                final_text = " ".join(direct_responses).strip()

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )

                if final_text:
                    yield final_text

                return

            if suppressed_final_response:
                final_text = " ".join(
                    spoken_pre_tool_parts + spoken_progress_parts
                ).strip() or "Done."

                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )

                return

            final_stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=working_messages,
                temperature=0.2,
                max_tokens=100,
                stream=True,
            )

            collected_final_text = []

            for chunk in final_stream:
                if not chunk.choices:
                    continue

                delta = chunk.choices[0].delta

                if delta.content:
                    collected_final_text.append(delta.content)
                    yield delta.content

            final_text = "".join(collected_final_text).strip()

            if final_text:
                self.messages.append(
                    {
                        "role": "assistant",
                        "content": final_text,
                    }
                )

        except Exception as error:
            print(f"AI tool stream error: {error}")
            yield f"Something went wrong while using my tools: {error}"
