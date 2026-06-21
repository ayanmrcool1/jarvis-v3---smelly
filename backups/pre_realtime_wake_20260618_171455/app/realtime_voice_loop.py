import asyncio
import base64
import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

import numpy as np
import sounddevice as sd
import websockets
from dotenv import load_dotenv


# =========================
# JARVIS REALTIME VOICE LOOP
# V6: simple speaker-safe realtime voice
# Rule:
# - Jarvis speaking = mic muted
# - Jarvis not speaking = mic fully open
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"

load_dotenv(ENV_PATH)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
REALTIME_MODEL = os.getenv("OPENAI_REALTIME_MODEL", "gpt-realtime-2")
VOICE = os.getenv("OPENAI_REALTIME_VOICE", "cedar")

SAMPLE_RATE = 24000
CHANNELS = 1
CHUNK_MS = 20
CHUNK_SIZE = int(SAMPLE_RATE * CHUNK_MS / 1000)

POST_ASSISTANT_MUTE_SECONDS = float(
    os.getenv("REALTIME_POST_ASSISTANT_MUTE_SECONDS", "1.10")
)
PLAYBACK_DRAIN_GRACE_SECONDS = float(
    os.getenv("REALTIME_PLAYBACK_DRAIN_GRACE_SECONDS", "0.35")
)
SERVER_VAD_THRESHOLD = float(
    os.getenv("REALTIME_SERVER_VAD_THRESHOLD", "0.55")
)

REALTIME_URL = (
    "wss://api.openai.com/v1/realtime?"
    + urlencode({"model": REALTIME_MODEL})
)

SYSTEM_INSTRUCTIONS = """
You are Jarvis, a fast realtime voice assistant running locally on the user's Windows PC.

Personality:
- Speak naturally.
- Be concise.
- Calm, capable, slightly friendly.
- Do not sound robotic.
- Your name is Jarvis. Do not spell it out.
- The user is building you as a local Windows assistant.

Rules:
- Keep replies short by default.
- Do not randomly continue talking after a completed answer.
- Do not ask follow-up questions unless needed.
- For now, this realtime test cannot control the PC yet.
- If the user asks you to perform a computer action, say: "That part is not connected in realtime yet."
"""


class SharedAudioState:
    def __init__(self):
        self.lock = threading.Lock()
        self.assistant_audio_active = False
        self.response_stream_done = False
        self.last_assistant_play_time = 0.0
        self.post_assistant_mute_until = 0.0

    def mark_assistant_audio_received(self):
        with self.lock:
            self.assistant_audio_active = True
            self.response_stream_done = False

    def mark_assistant_audio_played(self):
        with self.lock:
            self.assistant_audio_active = True
            self.last_assistant_play_time = time.time()

    def mark_response_done(self):
        # Server finished sending audio.
        # Local speaker buffer may still be playing, so don't mark audio inactive yet.
        with self.lock:
            self.response_stream_done = True

    def maybe_finish_assistant_audio(self, buffer_has_audio):
        with self.lock:
            if not self.assistant_audio_active:
                return

            if buffer_has_audio:
                return

            if not self.response_stream_done:
                return

            if time.time() - self.last_assistant_play_time < PLAYBACK_DRAIN_GRACE_SECONDS:
                return

            self.assistant_audio_active = False
            self.response_stream_done = False
            self.post_assistant_mute_until = time.time() + POST_ASSISTANT_MUTE_SECONDS

    def is_mic_muted_for_assistant(self):
        with self.lock:
            if self.assistant_audio_active:
                return True

            if time.time() < self.post_assistant_mute_until:
                return True

            return False

    def get_mode(self):
        with self.lock:
            if self.assistant_audio_active:
                return "assistant_speaking_mic_muted"

            if time.time() < self.post_assistant_mute_until:
                return "post_assistant_mute"

            return "mic_open"


class RealtimeAudioPlayer:
    def __init__(self, state):
        self.buffer = bytearray()
        self.lock = threading.Lock()
        self.state = state

    async def add_audio(self, pcm_bytes):
        with self.lock:
            self.buffer.extend(pcm_bytes)

        self.state.mark_assistant_audio_received()

    async def clear(self):
        with self.lock:
            self.buffer.clear()

    def make_callback(self):
        def callback(outdata, frames, time_info, status):
            if status:
                print(f"Output audio status: {status}")

            needed_bytes = frames * CHANNELS * 2

            with self.lock:
                if len(self.buffer) >= needed_bytes:
                    chunk = self.buffer[:needed_bytes]
                    del self.buffer[:needed_bytes]
                    buffer_has_audio_after = len(self.buffer) > 0
                else:
                    chunk = bytes(self.buffer)
                    self.buffer.clear()
                    buffer_has_audio_after = False
                    chunk += b"\x00" * (needed_bytes - len(chunk))

            if any(chunk):
                self.state.mark_assistant_audio_played()

            self.state.maybe_finish_assistant_audio(buffer_has_audio_after)

            audio = np.frombuffer(chunk, dtype=np.int16)

            if len(audio) < frames:
                padded = np.zeros(frames, dtype=np.int16)
                padded[: len(audio)] = audio
                audio = padded

            outdata[:] = audio.reshape(-1, CHANNELS)

        return callback


def calculate_rms(audio_int16):
    if audio_int16 is None or len(audio_int16) == 0:
        return 0.0

    audio_float = audio_int16.astype(np.float32)
    return float(np.sqrt(np.mean(audio_float ** 2)))


async def connect_realtime():
    if not OPENAI_API_KEY:
        raise ValueError("OPENAI_API_KEY is missing from C:\\Jarvis\\.env")

    headers = {
        "Authorization": f"Bearer {OPENAI_API_KEY}",
        "OpenAI-Safety-Identifier": "local-jarvis-user",
    }

    try:
        return await websockets.connect(
            REALTIME_URL,
            additional_headers=headers,
            max_size=None,
        )
    except TypeError:
        return await websockets.connect(
            REALTIME_URL,
            extra_headers=headers,
            max_size=None,
        )


async def send_session_update(ws):
    event = {
        "type": "session.update",
        "session": {
            "type": "realtime",
            "instructions": SYSTEM_INSTRUCTIONS,
            "audio": {
                "input": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": SAMPLE_RATE,
                    },
                    "noise_reduction": {
                        "type": "near_field",
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": SERVER_VAD_THRESHOLD,
                        "prefix_padding_ms": 250,
                        "silence_duration_ms": 550,
                        "create_response": True,
                        "interrupt_response": False,
                    },
                },
                "output": {
                    "format": {
                        "type": "audio/pcm",
                        "rate": SAMPLE_RATE,
                    },
                    "voice": VOICE,
                    "speed": 1.08,
                },
            },
        },
    }

    await ws.send(json.dumps(event))


async def microphone_sender(ws, audio_queue):
    print("Microphone streaming started.")

    while True:
        pcm_bytes = await audio_queue.get()

        if pcm_bytes is None:
            break

        encoded_audio = base64.b64encode(pcm_bytes).decode("utf-8")

        event = {
            "type": "input_audio_buffer.append",
            "audio": encoded_audio,
        }

        try:
            await ws.send(json.dumps(event))
        except Exception as error:
            print(f"Microphone send error: {error}")
            break


async def event_receiver(ws, player, state):
    print("Realtime receiver started.")

    async for message in ws:
        try:
            event = json.loads(message)
        except Exception:
            print(f"Non-JSON message: {message}")
            continue

        event_type = event.get("type")

        if event_type == "session.created":
            print("Realtime session created.")

        elif event_type == "session.updated":
            print("Realtime session updated. Speak naturally now.")

        elif event_type == "input_audio_buffer.speech_started":
            print("\nServer heard user speech.")

        elif event_type == "input_audio_buffer.speech_stopped":
            print("Server user speech stopped.")

        elif event_type == "response.output_audio.delta":
            audio_delta = event.get("delta")

            if audio_delta:
                pcm_bytes = base64.b64decode(audio_delta)
                await player.add_audio(pcm_bytes)

        elif event_type == "response.output_audio_transcript.delta":
            delta = event.get("delta", "")
            if delta:
                print(delta, end="", flush=True)

        elif event_type == "response.output_audio_transcript.done":
            print()

        elif event_type == "response.done":
            state.mark_response_done()
            print("Response done.")

        elif event_type == "error":
            print("\nRealtime error:")
            print(json.dumps(event, indent=2))


async def main():
    print("\nStarting Jarvis Realtime Voice Test...")
    print(f"Model: {REALTIME_MODEL}")
    print(f"Voice: {VOICE}")
    print(f"Server VAD threshold: {SERVER_VAD_THRESHOLD}")
    print(f"Post assistant mute: {POST_ASSISTANT_MUTE_SECONDS}s")
    print("Speaker-safe mode: mic is muted while Jarvis speaks.")
    print("Press Ctrl+C to stop.\n")

    audio_queue = asyncio.Queue(maxsize=120)

    state = SharedAudioState()
    player = RealtimeAudioPlayer(state)

    loop = asyncio.get_running_loop()
    last_debug_print = 0.0

    def input_callback(indata, frames, time_info, status):
        nonlocal last_debug_print

        if status:
            print(f"Input audio status: {status}")

        audio = indata.copy().reshape(-1).astype(np.int16)
        rms = calculate_rms(audio)
        now = time.time()

        if now - last_debug_print > 2.5:
            print(f"Mic RMS: {rms:.0f} | {state.get_mode()}")
            last_debug_print = now

        # Simple fix:
        # While Jarvis is speaking, do not send mic audio at all.
        # This prevents him from hearing himself through speakers.
        if state.is_mic_muted_for_assistant():
            return

        pcm_bytes = audio.tobytes()

        try:
            loop.call_soon_threadsafe(audio_queue.put_nowait, pcm_bytes)
        except asyncio.QueueFull:
            pass

    print("Opening microphone and speakers...")

    try:
        input_stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=input_callback,
        )

        output_stream = sd.OutputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=player.make_callback(),
        )

    except Exception as error:
        print("\nAudio device error:")
        print(error)
        print("\nYour device may not support 24kHz directly. We can add resampling next if needed.")
        return

    async with await connect_realtime() as ws:
        await send_session_update(ws)

        with input_stream, output_stream:
            sender_task = asyncio.create_task(
                microphone_sender(ws, audio_queue)
            )
            receiver_task = asyncio.create_task(
                event_receiver(ws, player, state)
            )

            print("Connected. Start talking to Jarvis.\n")

            await asyncio.gather(sender_task, receiver_task)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nRealtime Jarvis stopped.")