import os
import json
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

from tools.tool_registry import TOOL_DEFINITIONS, execute_tool_call


# =========================
# JARVIS PHASE 2/3/4 AI BRAIN
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)


SYSTEM_PROMPT = """
You are JARVIS, a personal AI assistant running locally on the user's Windows 10 computer.

Personality:
- Intelligent
- Concise
- Calm
- Direct
- Helpful
- Not overly chatty

Current capabilities:
- You can respond to the user's transcribed speech.
- You can speak aloud through local Kokoro TTS.
- You can use tools to open applications, search the web, run safe terminal commands, control volume, get system stats, and get the current date/time.
- You cannot yet see the screen.
- You cannot yet do deep browser automation.
- If the user asks for something not available yet, briefly say it will be added in a later phase.

Tool behavior:
- Use tools when the user asks you to do something on the computer.
- Do not claim you opened, searched, ran, or changed something unless a tool result confirms it.
- Keep tool result responses short.
- If a tool fails, briefly say what failed.

Response style:
- By default, reply in one short sentence unless the user asks for detail.
- Do not ramble.
"""


class JarvisBrain:
    """
    Handles communication with OpenAI.
    Supports normal chat, streaming chat, and tool calling.
    """

    def __init__(self):
        self.api_key = os.getenv("OPENAI_API_KEY")
        self.model_name = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

        if not self.api_key:
            raise ValueError(
                "OPENAI_API_KEY is missing. Add it to your C:\\Jarvis\\.env file."
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

        return f"""
Current system time: {now}

User said:
{user_text}
"""

    def ask(self, user_text, max_tokens=80):
        """
        Normal non-streaming response.
        """

        if not user_text.strip():
            return ""

        message = self._build_user_message(user_text)

        self.messages.append(
            {
                "role": "user",
                "content": message,
            }
        )

        try:
            response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.4,
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

    def stream_ask(self, user_text, max_tokens=120):
        """
        Streaming response for normal conversation.
        """

        if not user_text.strip():
            return

        message = self._build_user_message(user_text)

        self.messages.append(
            {
                "role": "user",
                "content": message,
            }
        )

        collected_text = []

        try:
            stream = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.4,
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
        """
        Tool-aware response.
        The model can call one or more tools, then gives a final response.
        """

        if not user_text.strip():
            return ""

        message = self._build_user_message(user_text)

        self.messages.append(
            {
                "role": "user",
                "content": message,
            }
        )

        try:
            tool_choice = "auto"

            if forced_tool_name:
                tool_choice = {
                    "type": "function",
                    "function": {
                        "name": forced_tool_name
                    }
                }

            first_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                tool_choice=tool_choice,
                temperature=0.2,
                max_tokens=max_tokens,
            )

            assistant_message = first_response.choices[0].message

            self.messages.append(assistant_message)

            if not assistant_message.tool_calls:
                final_text = assistant_message.content or ""

                if final_text.strip():
                    return final_text.strip()

                return "I understood, but I did not need to use a tool."

            tool_results = []

            for tool_call in assistant_message.tool_calls:
                tool_name = tool_call.function.name
                tool_args = tool_call.function.arguments

                print(f"Tool requested: {tool_name}")
                print(f"Tool arguments: {tool_args}")

                tool_result = execute_tool_call(tool_name, tool_args)

                print(f"Tool result: {tool_result}")

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

            # For simple action tools, do NOT let GPT invent a final response.
            # Just return the real Python tool result.
            if len(tool_results) == 1:
                tool_name = tool_results[0]["tool_name"]
                result = tool_results[0]["result"]

                if tool_name in ["open_application", "search_web", "set_volume"]:
                    final_text = result.get("message", "Done.")

                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": final_text,
                        }
                    )

                    return final_text

                if tool_name == "get_system_stats":
                    if result.get("success"):
                        cpu = result.get("cpu_percent")
                        ram = result.get("ram_percent")
                        disk = result.get("disk_percent")
                        battery = result.get("battery_percent")

                        if battery is None:
                            final_text = f"CPU is at {cpu} percent, RAM is at {ram} percent, and disk usage is at {disk} percent."
                        else:
                            final_text = f"CPU is at {cpu} percent, RAM is at {ram} percent, disk usage is at {disk} percent, and battery is at {battery} percent."
                    else:
                        final_text = result.get("message", "I could not get system stats.")

                    self.messages.append(
                        {
                            "role": "assistant",
                            "content": final_text,
                        }
                    )

                    return final_text

            # For more complex tools, let GPT summarize after seeing the result.
            final_response = self.client.chat.completions.create(
                model=self.model_name,
                messages=self.messages,
                temperature=0.1,
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