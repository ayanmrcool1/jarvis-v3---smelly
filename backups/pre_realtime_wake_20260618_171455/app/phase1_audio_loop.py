import time
from pathlib import Path
from collections import deque
from datetime import datetime

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav

from openwakeword.model import Model
from openwakeword.utils import download_models

from faster_whisper import WhisperModel
from ai_brain import JarvisBrain
from tts_engine import JarvisTTS
from speech_style import humanise_jarvis_response
from router import JarvisRouter
from ui_state import write_ui_state

from tools.system_tools import (
    open_application,
    search_web,
    get_system_stats,
    set_volume,
)


# =========================
# JARVIS PHASE 1 SETTINGS
# =========================

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz

WAKE_THRESHOLD = 0.85

SPEECH_START_RMS = 500.0
SPEECH_END_RMS = 320.0
SILENCE_SECONDS_TO_STOP = 0.35
MAX_COMMAND_SECONDS = 10.0
MIN_COMMAND_SECONDS = 0.3
PRE_ROLL_SECONDS = 0.32

WHISPER_BEAM_SIZE = 1
MIN_AUDIO_RMS = 180.0

EXIT_PHRASES = [
    "stop listening",
    "go to sleep",
    "thanks jarvis",
    "thank you jarvis",
    "that is all",
    "that's all",
]

COMMON_WHISPER_HALLUCINATIONS = [
    "thank you for watching",
    "thanks for watching",
    "thank you",
]

BASE_DIR = Path(__file__).resolve().parent.parent
RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)


# =========================
# UI STATE HELPER
# =========================

def set_ui_state(status, sub_status="", detail=""):
    """
    Safely updates the Jarvis HUD state.
    If the UI state file fails for any reason, Jarvis still keeps running.
    """

    try:
        write_ui_state(status, sub_status, detail)
    except Exception as error:
        print(f"UI state warning: {error}")


# =========================
# AUDIO HELPERS
# =========================

def calculate_rms(audio):
    """Calculate loudness of an audio chunk."""
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def print_devices():
    print("\nAvailable audio devices:")
    print(sd.query_devices())
    print("\nUsing default input device.\n")


def load_wake_word_model():
    print("Downloading/loading OpenWakeWord models...")
    set_ui_state("BOOTING", "Loading wake word model", "Preparing Hey Jarvis detection")

    download_models()
    model = Model(inference_framework="onnx")

    print("OpenWakeWord loaded.")
    print("Sleep mode wake phrase: 'Hey Jarvis'\n")

    return model


def reset_wake_model(wake_model):
    try:
        wake_model.reset()
    except Exception:
        pass


def load_whisper_model():
    print("Loading faster-whisper tiny.en model...")
    print("First run may take a while if the model is not already cached.")
    set_ui_state("BOOTING", "Loading speech model", "Preparing local transcription")

    model = WhisperModel(
        "tiny.en",
        device="cpu",
        compute_type="int8"
    )

    print("Whisper loaded.\n")
    return model


def normalize_text(text):
    text = text.lower().strip()

    for char in [".", ",", "!", "?", ";", ":"]:
        text = text.replace(char, "")

    return " ".join(text.split())


def should_exit_active_mode(transcription):
    clean_text = normalize_text(transcription)

    for phrase in EXIT_PHRASES:
        if phrase in clean_text:
            return True

    return False


def is_likely_hallucination(transcription):
    clean_text = normalize_text(transcription)

    for phrase in COMMON_WHISPER_HALLUCINATIONS:
        if clean_text == phrase:
            return True

    return False


def is_repeat_request(clean_text):
    repeat_phrases = [
        "what did you say",
        "what did you say again",
        "say that again",
        "say it again",
        "repeat that",
        "repeat what you said",
        "what was that",
        "sorry what did you say",
        "sorry what did you say again",
        "can you repeat that",
        "could you repeat that",
    ]

    return any(phrase in clean_text for phrase in repeat_phrases)


def is_tiny_acknowledgement(clean_text):
    phrases = [
        "thanks",
        "thank you",
        "cheers",
        "appreciate it",
        "i appreciate it",
        "alright thanks",
        "ok thanks",
        "okay thanks",
        "cool thanks",
        "bet thanks",
        "nice thanks",
        "sweet thanks",
    ]

    if clean_text in phrases:
        return True

    if clean_text.startswith("thanks ") or clean_text.startswith("thank you "):
        return True

    if clean_text.endswith(" thanks") or clean_text.endswith(" thank you"):
        return True

    if "i appreciate it" in clean_text and len(clean_text.split()) <= 8:
        return True

    return False


def get_instant_local_response(transcription, last_jarvis_response):
    """
    Local responses that should never go to OpenAI.
    This keeps Jarvis fast and prevents wasted TTS/tool calls.
    """

    clean_text = normalize_text(transcription)

    if is_repeat_request(clean_text):
        if last_jarvis_response:
            return f"I said, {last_jarvis_response}"
        return "I haven’t said anything yet."

    if is_tiny_acknowledgement(clean_text):
        return "Anytime."

    return None


def record_until_silence(stream, filename):
    """
    Wait until speech starts, then keep recording until silence is detected.
    """

    print("Waiting for speech...")
    set_ui_state("LISTENING", "Listening", "Waiting for speech")

    pre_roll_chunks = int((PRE_ROLL_SECONDS * SAMPLE_RATE) / CHUNK_SIZE)
    silence_chunks_needed = int((SILENCE_SECONDS_TO_STOP * SAMPLE_RATE) / CHUNK_SIZE)
    max_chunks = int((MAX_COMMAND_SECONDS * SAMPLE_RATE) / CHUNK_SIZE)

    pre_roll = deque(maxlen=pre_roll_chunks)
    recorded_chunks = []

    recording = False
    silent_chunks = 0
    chunks_recorded_after_start = 0

    last_wait_message = time.time()

    while True:
        audio_block, overflowed = stream.read(CHUNK_SIZE)

        if overflowed:
            print("Warning: microphone buffer overflowed.")

        audio_flat = audio_block.reshape(-1)
        chunk_rms = calculate_rms(audio_flat)

        if not recording:
            pre_roll.append(audio_block.copy())

            if time.time() - last_wait_message > 4:
                print("Still waiting for speech...")
                set_ui_state("LISTENING", "Still listening", "Waiting for speech")
                last_wait_message = time.time()

            if chunk_rms >= SPEECH_START_RMS:
                recording = True
                recorded_chunks = list(pre_roll)
                chunks_recorded_after_start = 1
                silent_chunks = 0

                print("Speech detected. Recording...")
                set_ui_state("LISTENING", "Speech detected", "Recording your command")

        else:
            recorded_chunks.append(audio_block.copy())
            chunks_recorded_after_start += 1

            elapsed_seconds = (chunks_recorded_after_start * CHUNK_SIZE) / SAMPLE_RATE

            if chunk_rms < SPEECH_END_RMS and elapsed_seconds >= MIN_COMMAND_SECONDS:
                silent_chunks += 1
            else:
                silent_chunks = 0

            if silent_chunks >= silence_chunks_needed:
                print("Silence detected. Stopping recording.")
                set_ui_state("THINKING", "Command captured", "Preparing transcription")
                break

            if chunks_recorded_after_start >= max_chunks:
                print("Max command length reached. Stopping recording.")
                set_ui_state("THINKING", "Command captured", "Preparing transcription")
                break

    audio = np.concatenate(recorded_chunks, axis=0).reshape(-1)

    wav_path = RECORDINGS_DIR / filename
    write_wav(str(wav_path), SAMPLE_RATE, audio)

    total_rms = calculate_rms(audio)

    print(f"Saved audio: {wav_path}")
    print(f"Audio loudness RMS: {total_rms:.2f}")

    return wav_path, total_rms


def transcribe_audio(whisper_model, wav_path, rms):
    if rms < MIN_AUDIO_RMS:
        print("Audio too quiet. Ignoring.\n")
        set_ui_state("LISTENING", "Still listening", "Audio was too quiet")
        return ""

    print(f"Transcribing with beam_size={WHISPER_BEAM_SIZE}...")
    set_ui_state("THINKING", "Transcribing", "Converting speech to text")

    segments, info = whisper_model.transcribe(
        str(wav_path),
        beam_size=WHISPER_BEAM_SIZE,
        vad_filter=True,
        condition_on_previous_text=False
    )

    text_parts = []

    for segment in segments:
        text = segment.text.strip()
        if text:
            text_parts.append(text)

    transcription = " ".join(text_parts).strip()

    if not transcription:
        print("No clear speech detected.\n")
        set_ui_state("LISTENING", "Still listening", "No clear speech detected")
        return ""

    if is_likely_hallucination(transcription):
        print(f"Ignored likely Whisper hallucination: {transcription}\n")
        set_ui_state("LISTENING", "Still listening", "Ignored unclear transcription")
        return ""

    print("\n==============================")
    print("TRANSCRIPTION:")
    print(transcription)
    print("==============================\n")

    set_ui_state("THINKING", "Command received", transcription[:120])

    return transcription


def is_jarvis_detected(prediction):
    jarvis_scores = {}

    for model_name, score in prediction.items():
        if "jarvis" in model_name.lower():
            jarvis_scores[model_name] = float(score)

    if not jarvis_scores:
        return False, 0.0, "No Jarvis model found"

    best_model = max(jarvis_scores, key=jarvis_scores.get)
    best_score = jarvis_scores[best_model]

    return best_score >= WAKE_THRESHOLD, best_score, best_model


def flush_microphone_buffer(stream, seconds=0.8):
    """
    Briefly discard mic audio after Jarvis speaks.
    This helps avoid the mic catching leftover speaker audio.
    """

    chunks_to_discard = int((seconds * SAMPLE_RATE) / CHUNK_SIZE)

    for _ in range(chunks_to_discard):
        try:
            stream.read(CHUNK_SIZE)
        except Exception:
            pass


# =========================
# OLD LOCAL HELPERS
# Kept for compatibility, but routing now mainly uses router.py
# =========================

def handle_local_quick_command(transcription):
    clean_text = normalize_text(transcription)

    time_phrases = [
        "what time is it",
        "what's the time",
        "tell me the time",
        "actual time",
        "current time",
    ]

    date_phrases = [
        "what date is it",
        "what's the date",
        "what day is it",
        "current date",
    ]

    for phrase in time_phrases:
        if phrase in clean_text:
            current_time = datetime.now().strftime("%I:%M %p").lstrip("0")
            return f"It's {current_time}."

    for phrase in date_phrases:
        if phrase in clean_text:
            current_date = datetime.now().strftime("%A, %B %d").replace(" 0", " ")
            return f"It's {current_date}."

    return None


def should_use_tools(transcription):
    clean_text = normalize_text(transcription)

    tool_keywords = [
        "open",
        "launch",
        "start",
        "bring up",
        "pull up",
        "search",
        "google",
        "look up",
        "run command",
        "terminal",
        "command prompt",
        "powershell",
        "volume",
        "mute",
        "unmute",
        "cpu",
        "ram",
        "memory usage",
        "battery",
        "system stats",
        "disk usage",
        "computer stats",
        "system",
        "stats",
        "scuts",
        "computer",
        "performance",
    ]

    for keyword in tool_keywords:
        if keyword in clean_text:
            return True

    return False


def handle_local_tool_command(transcription):
    clean_text = normalize_text(transcription)

    if "volume" in clean_text:
        if "down" in clean_text or "lower" in clean_text or "decrease" in clean_text:
            result = set_volume("down")
            return result.get("message", "Volume decreased.")

        if "up" in clean_text or "raise" in clean_text or "increase" in clean_text:
            result = set_volume("up")
            return result.get("message", "Volume increased.")

        if "mute" in clean_text or "unmute" in clean_text:
            result = set_volume("mute")
            return result.get("message", "Volume muted or unmuted.")

    if (
        "system stats" in clean_text
        or "computer stats" in clean_text
        or "system scuts" in clean_text
        or "cpu" in clean_text
        or "ram" in clean_text
        or "memory usage" in clean_text
        or "performance" in clean_text
    ):
        stats = get_system_stats()

        if not stats.get("success"):
            return stats.get("message", "I could not get system stats.")

        cpu = stats.get("cpu_percent")
        ram = stats.get("ram_percent")
        disk = stats.get("disk_percent")
        battery = stats.get("battery_percent")

        if battery is None:
            return f"CPU is at {cpu} percent, RAM is at {ram} percent, and disk usage is at {disk} percent."

        return f"CPU is at {cpu} percent, RAM is at {ram} percent, disk usage is at {disk} percent, and battery is at {battery} percent."

    open_phrases = [
        "open ",
        "launch ",
        "start ",
        "bring up ",
        "pull up ",
    ]

    for phrase in open_phrases:
        if clean_text.startswith(phrase):
            app_name = clean_text.replace(phrase, "", 1).strip()

            if app_name:
                result = open_application(app_name)

                if result.get("success"):
                    return result.get("message", f"Opening {app_name}.")

                return None

    search_phrases = [
        "search ",
        "google ",
        "look up ",
    ]

    for phrase in search_phrases:
        if clean_text.startswith(phrase):
            query = clean_text.replace(phrase, "", 1).strip()

            if query:
                result = search_web(query)
                return result.get("message", f"Searching for {query}.")

    return None


def get_forced_tool_name(transcription):
    clean_text = normalize_text(transcription)

    if (
        clean_text.startswith("open ")
        or clean_text.startswith("launch ")
        or clean_text.startswith("start ")
        or clean_text.startswith("bring up ")
        or clean_text.startswith("pull up ")
    ):
        return "open_application"

    if (
        clean_text.startswith("search ")
        or clean_text.startswith("google ")
        or clean_text.startswith("look up ")
    ):
        return "search_web"

    if "volume" in clean_text or "mute" in clean_text or "unmute" in clean_text:
        return "set_volume"

    if (
        "system" in clean_text
        or "stats" in clean_text
        or "scuts" in clean_text
        or "cpu" in clean_text
        or "ram" in clean_text
        or "battery" in clean_text
        or "performance" in clean_text
    ):
        return "get_system_stats"

    if (
        "terminal" in clean_text
        or "powershell" in clean_text
        or "command prompt" in clean_text
        or "run command" in clean_text
    ):
        return "run_terminal_command"

    return None


# =========================
# ACTIVE MODE
# =========================

def active_listening_mode(stream, whisper_model, router, tts):
    print("\nJARVIS ACTIVE.")
    print("Speak normally. Say 'stop listening' or 'go to sleep' to exit.\n")

    set_ui_state("LISTENING", "Active mode", "Speak normally")

    command_count = 1
    last_jarvis_response = ""

    while True:
        wav_path, rms = record_until_silence(
            stream=stream,
            filename=f"active_command_{command_count}.wav"
        )

        transcription = transcribe_audio(whisper_model, wav_path, rms)

        if transcription and should_exit_active_mode(transcription):
            print("Exit phrase detected. Returning to sleep mode.\n")

            jarvis_response = "Going back to sleep."
            set_ui_state("SPEAKING", "Returning to sleep", jarvis_response)
            tts.speak(jarvis_response)

            flush_microphone_buffer(stream)

            set_ui_state("STANDBY", "Awaiting wake phrase")
            break

        if transcription:
            print("\n==============================")
            print("JARVIS RESPONSE:")

            instant_response = get_instant_local_response(
                transcription=transcription,
                last_jarvis_response=last_jarvis_response,
            )

            if instant_response:
                jarvis_response = humanise_jarvis_response(instant_response)

                print("Router matched: instant_local_response")
                print(jarvis_response)

                set_ui_state("SPEAKING", "Responding", jarvis_response[:120])
                tts.speak(jarvis_response)

                last_jarvis_response = jarvis_response

                flush_microphone_buffer(stream)
                set_ui_state("LISTENING", "Ready for next command", "Speak naturally")

                print("==============================\n")

                command_count += 1
                continue

            set_ui_state("THINKING", "Processing", transcription[:120])

            route_result = router.handle(transcription)

            print(f"Router source: {route_result.get('source')}")

            if route_result.get("type") == "stream":
                set_ui_state("SPEAKING", "Responding", "Streaming response")

                jarvis_response = tts.speak_stream(
                    route_result.get("stream")
                )

                if jarvis_response:
                    set_ui_state("SPEAKING", "Responding", jarvis_response[:120])
                    last_jarvis_response = jarvis_response

            else:
                raw_response = route_result.get("response", "Done.")
                jarvis_response = humanise_jarvis_response(raw_response)

                print(jarvis_response)

                set_ui_state("SPEAKING", "Responding", jarvis_response[:120])
                tts.speak(jarvis_response)

                if jarvis_response:
                    last_jarvis_response = jarvis_response

            flush_microphone_buffer(stream)

            set_ui_state("LISTENING", "Ready for next command", "Speak naturally")

            print("==============================\n")

        command_count += 1


# =========================
# MAIN LOOP
# =========================

def main():
    print("\nStarting JARVIS Phase 1/2/3...")
    print("Press Ctrl + C to stop completely.\n")

    set_ui_state("BOOTING", "Starting J.A.R.V.I.S", "Initialising local systems")

    print_devices()

    wake_model = load_wake_word_model()
    whisper_model = load_whisper_model()

    set_ui_state("BOOTING", "Loading AI brain", "Connecting to OpenAI")
    brain = JarvisBrain()

    set_ui_state("BOOTING", "Loading voice engine", "Preparing Edge TTS")
    tts = JarvisTTS(voice="en-GB-ThomasNeural", speed=1.10)

    set_ui_state("BOOTING", "Loading router", "Preparing local tools and AI tool brain")
    router = JarvisRouter(brain)

    reset_wake_model(wake_model)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SIZE
    ) as stream:

        print("JARVIS is in sleep mode.")
        set_ui_state("STANDBY", "Awaiting wake phrase", "Say Hey Jarvis")
        print("Say: Hey Jarvis\n")

        while True:
            audio_block, overflowed = stream.read(CHUNK_SIZE)

            if overflowed:
                print("Warning: microphone buffer overflowed.")

            audio_block = audio_block.reshape(-1)

            prediction = wake_model.predict(audio_block)

            detected, score, model_name = is_jarvis_detected(prediction)

            if detected:
                print("\nWake word detected!")
                print(f"Model: {model_name}")
                print(f"Score: {score:.3f}")

                set_ui_state(
                    "LISTENING",
                    "Wake word detected",
                    "Listening for your command"
                )

                reset_wake_model(wake_model)

                active_listening_mode(stream, whisper_model, router, tts)

                reset_wake_model(wake_model)

                print("JARVIS is back in sleep mode.")
                set_ui_state("STANDBY", "Awaiting wake phrase", "Say Hey Jarvis")
                print("Say: Hey Jarvis\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        set_ui_state("OFFLINE", "Jarvis stopped", "Shutdown requested")
        print("\nJARVIS stopped by user.")