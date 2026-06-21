import os
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI


# =========================
# JARVIS PHASE 2/3 AI BRAIN
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
- You cannot yet control the computer.
- You cannot yet see the screen.
- If the user asks you to do something you cannot do yet, briefly say that this will be added in a later phase.

Response style:
- By default, reply in one short sentence unless the user asks for detail.
- Do not ramble.
- Do not pretend you performed actions that you cannot perform yet.
"""


class JarvisBrain:
    """
    Handles communication with OpenAI.
    Keeps basic conversation memory during the current Jarvis run.
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
        Non-streaming response.
        Kept for test_brain.py and fallback use.
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
        Streaming response.
        Yields small text chunks as OpenAI sends them back.
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
            error_text = f"AI brain error: {error}"
            yield error_text