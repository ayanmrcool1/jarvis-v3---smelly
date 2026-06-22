import os
import queue
import threading
import time
import math
from pathlib import Path
from collections import deque

import numpy as np
import sounddevice as sd
from scipy.io.wavfile import write as write_wav

from openwakeword.model import Model
from openwakeword.utils import download_models

from dotenv import load_dotenv
from faster_whisper import WhisperModel
from ai_brain import JarvisBrain
from keybind_listener import GlobalHotkeyListener
from tts_engine import JarvisTTS
from speech_style import humanise_jarvis_response
from router import JarvisRouter
from ui_state import write_ui_state, append_chat_message

# =========================
# JARVIS PHASE 1 SETTINGS
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
load_dotenv(ENV_PATH)


def get_env_float(name, default):
    value = os.getenv(name)

    if value is None or str(value).strip() == "":
        return default

    try:
        return float(value)
    except ValueError:
        print(f"Invalid {name} value: {value!r}. Using {default}.")
        return default


def get_env_int(name, default, minimum=None):
    value = os.getenv(name)

    if value is None or str(value).strip() == "":
        return default

    try:
        parsed = int(value)
    except ValueError:
        print(f"Invalid {name} value: {value!r}. Using {default}.")
        return default

    if minimum is not None and parsed < minimum:
        print(f"Invalid {name} value: {value!r}. Using {default}.")
        return default

    return parsed


SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz

WAKE_THRESHOLD = 0.85

SPEECH_START_RMS = 500.0
SPEECH_END_RMS = 320.0
SILENCE_SECONDS_TO_STOP = 0.4
MAX_COMMAND_SECONDS = 10.0
MIN_COMMAND_SECONDS = 0.3
PRE_ROLL_SECONDS = 1.5
WAKE_SPEECH_START_TIMEOUT_SECONDS = get_env_float(
    "JARVIS_WAKE_SPEECH_START_TIMEOUT_SECONDS",
    6.0,
)
WAKE_FOLLOWUP_SPEECH_START_TIMEOUT_SECONDS = get_env_float(
    "JARVIS_FOLLOWUP_SPEECH_START_TIMEOUT_SECONDS",
    8.0,
)
WAKE_SESSION_MAX_TURNS = get_env_int(
    "JARVIS_WAKE_SESSION_MAX_TURNS",
    8,
    minimum=1,
)
KEYBIND_SILENCE_SECONDS_TO_STOP = get_env_float(
    "JARVIS_KEYBIND_SILENCE_SECONDS",
    5.0,
)
KEYBIND_SPEECH_START_TIMEOUT_SECONDS = get_env_float(
    "JARVIS_KEYBIND_SPEECH_START_TIMEOUT_SECONDS",
    5.0,
)
HOTKEY_TEXT = os.getenv("JARVIS_HOTKEY", "ctrl+space").strip() or "ctrl+space"

WHISPER_BEAM_SIZE = 1
MIN_AUDIO_RMS = 180.0

COMMON_WHISPER_HALLUCINATIONS = [
    "thank you for watching",
    "thanks for watching",
    "thank you",
]

WAKE_SESSION_END_REQUESTS = {
    "done",
    "im done",
    "i am done",
    "thats all",
    "that is all",
    "nothing else",
    "no thanks",
    "no thank you",
    "go to sleep",
    "stop listening",
    "goodbye",
    "bye",
}

RECORDINGS_DIR = BASE_DIR / "recordings"
RECORDINGS_DIR.mkdir(exist_ok=True)


# =========================
# PROFILING HELPER
# =========================

def profile_log(label, start_time=None, extra=""):
    """
    Lightweight timing logger for finding STT / GPT / TTS bottlenecks.
    """
    if start_time is None:
        print(f"[PROFILE] {label}{extra}")
        return

    elapsed = time.perf_counter() - start_time
    print(f"[PROFILE] {label}: {elapsed:.2f}s{extra}")



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


def add_chat_message(role, text):
    """
    Safely mirrors accepted conversation turns into the HUD chat history.
    """

    try:
        append_chat_message(role, text)
    except Exception as error:
        print(f"HUD chat warning: {error}")


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

    return text


def is_likely_hallucination(transcription):
    clean_text = normalize_text(transcription)

    for phrase in COMMON_WHISPER_HALLUCINATIONS:
        if clean_text == phrase:
            return True

    return False


def record_until_silence(
    stream,
    filename,
    silence_seconds_to_stop=SILENCE_SECONDS_TO_STOP,
    max_command_seconds=MAX_COMMAND_SECONDS,
    min_command_seconds=MIN_COMMAND_SECONDS,
    speech_start_timeout_seconds=None,
    stop_event=None,
    manual_stop_label="Manual stop requested",
):
    """
    Wait until speech starts, then keep recording until silence is detected.
    Also prints profiling for:
    - waiting time before speech
    - actual recording duration
    - total record function time
    """

    record_profile_start = time.perf_counter()
    speech_detected_at = None
    recording_started_at = None

    print("Waiting for speech...")
    set_ui_state("LISTENING", "Listening", "Waiting for speech")

    pre_roll_chunks = max(1, math.ceil((PRE_ROLL_SECONDS * SAMPLE_RATE) / CHUNK_SIZE))
    silence_chunks_needed = max(1, math.ceil((silence_seconds_to_stop * SAMPLE_RATE) / CHUNK_SIZE))
    max_chunks = max(1, math.ceil((max_command_seconds * SAMPLE_RATE) / CHUNK_SIZE))
    speech_start_deadline = None

    if speech_start_timeout_seconds is not None:
        speech_start_deadline = time.monotonic() + max(
            0.1,
            float(speech_start_timeout_seconds),
        )

    pre_roll = deque(maxlen=pre_roll_chunks)
    recorded_chunks = []

    recording = False
    silent_chunks = 0
    chunks_recorded_after_start = 0

    last_wait_message = time.time()

    while True:
        if stop_event and stop_event.is_set():
            if recording and recorded_chunks:
                print(f"{manual_stop_label}. Stopping recording.")
                set_ui_state("THINKING", "Command captured", "Preparing transcription")
                break

            print(f"{manual_stop_label}. Cancelling listening.")
            set_ui_state("STANDBY", "Listening cancelled")
            return None, 0.0, "cancelled"

        if (
            not recording
            and speech_start_deadline is not None
            and time.monotonic() >= speech_start_deadline
        ):
            print("No speech detected. Returning to sleep mode.")
            set_ui_state("STANDBY", "No speech detected")
            return None, 0.0, "timeout"

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

                speech_detected_at = time.perf_counter()
                recording_started_at = speech_detected_at

                print("Speech detected. Recording...")
                profile_log("Waited for speech", record_profile_start)
                set_ui_state("LISTENING", "Speech detected", "Recording your command")

        else:
            recorded_chunks.append(audio_block.copy())
            chunks_recorded_after_start += 1

            elapsed_seconds = (chunks_recorded_after_start * CHUNK_SIZE) / SAMPLE_RATE

            if chunk_rms < SPEECH_END_RMS and elapsed_seconds >= min_command_seconds:
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

    if recording_started_at:
        profile_log("Recorded command audio", recording_started_at)

    profile_log(
        "Recording stage total",
        record_profile_start,
        extra=f" | audio_duration={len(audio) / SAMPLE_RATE:.2f}s"
    )

    return wav_path, total_rms, "captured"


def transcribe_audio(whisper_model, wav_path, rms):
    transcribe_profile_start = time.perf_counter()

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
        vad_parameters={
            "threshold": 0.5,
            "min_silence_duration_ms": 250,
            "speech_pad_ms": 100,
        },
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

    profile_log("Whisper STT", transcribe_profile_start)

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
# SHARED VOICE TURN
# =========================

def route_and_speak(transcription, router, tts):
    add_chat_message("user", transcription)

    print("\n==============================")
    print("JARVIS RESPONSE:")

    set_ui_state("THINKING", "Processing", transcription[:120])

    router_profile_start = time.perf_counter()
    route_result = router.handle(transcription)
    profile_log("Router decision", router_profile_start)

    print(f"Router source: {route_result.get('source')}")

    jarvis_response = ""

    if route_result.get("type") == "stream":
        set_ui_state("SPEAKING", "Responding", "Streaming response")

        tts_profile_start = time.perf_counter()
        jarvis_response = tts.speak_stream(
            route_result.get("stream")
        )
        profile_log("TTS stream call returned", tts_profile_start)

        if jarvis_response:
            set_ui_state("SPEAKING", "Responding", jarvis_response[:120])
            add_chat_message("jarvis", jarvis_response)

    else:
        raw_response = route_result.get("response", "Done.")
        jarvis_response = humanise_jarvis_response(raw_response)

        print(jarvis_response)

        set_ui_state("SPEAKING", "Responding", jarvis_response[:120])
        tts.speak(jarvis_response)
        add_chat_message("jarvis", jarvis_response)

    return {
        "response": jarvis_response or "",
        "route_result": route_result,
    }


def response_invites_follow_up(response, router):
    pending_intents = getattr(router, "pending_intents", None)

    if pending_intents and pending_intents.has_pending():
        return True

    clean_response = str(response or "").strip()

    if not clean_response:
        return False

    return clean_response.endswith("?")


def user_requested_wake_session_end(transcription):
    clean_text = normalize_text(transcription)

    if not clean_text:
        return False

    return clean_text in WAKE_SESSION_END_REQUESTS


def should_continue_wake_session(result, router, handled_turns):
    status = result.get("status")

    if status == "session_closed":
        return False, "user ended the session"

    if status == "timeout":
        return False, "no follow-up speech detected"

    if status == "cancelled":
        return False, "listening was cancelled"

    if status != "handled":
        return False, "no command was handled"

    if handled_turns >= WAKE_SESSION_MAX_TURNS:
        return False, "wake session safety limit reached"

    if response_invites_follow_up(result.get("response"), router):
        return True, "follow-up invited"

    return False, "turn completed"


def run_voice_turn(
    stream,
    whisper_model,
    router,
    tts,
    filename,
    silence_seconds_to_stop=SILENCE_SECONDS_TO_STOP,
    speech_start_timeout_seconds=WAKE_SPEECH_START_TIMEOUT_SECONDS,
    stop_event=None,
    manual_stop_label="Manual stop requested",
    session_end_checker=None,
):
    command_profile_start = time.perf_counter()

    wav_path, rms, capture_status = record_until_silence(
        stream=stream,
        filename=filename,
        silence_seconds_to_stop=silence_seconds_to_stop,
        speech_start_timeout_seconds=speech_start_timeout_seconds,
        stop_event=stop_event,
        manual_stop_label=manual_stop_label,
    )

    if capture_status != "captured":
        return {
            "status": capture_status,
            "transcription": "",
            "response": "",
        }

    transcription = transcribe_audio(whisper_model, wav_path, rms)

    if not transcription:
        return {
            "status": "no_transcription",
            "transcription": "",
            "response": "",
        }

    if session_end_checker and session_end_checker(transcription):
        print("Wake session end intent detected. Returning to sleep mode.")
        set_ui_state("STANDBY", "Conversation ended")
        add_chat_message("user", transcription)

        return {
            "status": "session_closed",
            "transcription": transcription,
            "response": "",
        }

    response_result = route_and_speak(transcription, router, tts)
    flush_microphone_buffer(stream)

    profile_log("Full voice turn", command_profile_start)

    return {
        "status": "handled",
        "transcription": transcription,
        "response": response_result.get("response", ""),
        "route_result": response_result.get("route_result", {}),
    }


def wake_word_command_mode(stream, whisper_model, router, tts, next_filename):
    print("\nWake command mode active.")
    print("Listening for one command, with bounded follow-up if needed.\n")

    handled_turns = 0
    waiting_for_followup = False

    while True:
        if waiting_for_followup:
            print("Follow-up session still active. Listening again.\n")
            set_ui_state("LISTENING", "Follow-up invited", "Listening for your reply")
            speech_start_timeout = WAKE_FOLLOWUP_SPEECH_START_TIMEOUT_SECONDS
        else:
            set_ui_state("LISTENING", "Wake word detected", "Listening for your command")
            speech_start_timeout = WAKE_SPEECH_START_TIMEOUT_SECONDS

        result = run_voice_turn(
            stream=stream,
            whisper_model=whisper_model,
            router=router,
            tts=tts,
            filename=next_filename(),
            silence_seconds_to_stop=SILENCE_SECONDS_TO_STOP,
            speech_start_timeout_seconds=speech_start_timeout,
            session_end_checker=user_requested_wake_session_end,
        )

        if result.get("status") == "handled":
            handled_turns += 1

        should_continue, reason = should_continue_wake_session(
            result,
            router,
            handled_turns,
        )

        print(f"Wake session decision: {reason}.")

        if not should_continue:
            break

        waiting_for_followup = True


def keybind_command_mode(stream, whisper_model, router, tts, next_filename, stop_event):
    print("\nKeybind command mode active.")
    print("Listening for one manual command.\n")

    set_ui_state("LISTENING", "Keybind active", "Listening for your command")

    return run_voice_turn(
        stream=stream,
        whisper_model=whisper_model,
        router=router,
        tts=tts,
        filename=next_filename(),
        silence_seconds_to_stop=KEYBIND_SILENCE_SECONDS_TO_STOP,
        speech_start_timeout_seconds=KEYBIND_SPEECH_START_TIMEOUT_SECONDS,
        stop_event=stop_event,
        manual_stop_label="Hotkey pressed again",
    )


def consume_hotkey_trigger(trigger_queue):
    triggered = False

    while True:
        try:
            trigger_queue.get_nowait()
            triggered = True
        except queue.Empty:
            return triggered


# =========================
# MAIN LOOP
# =========================

def main():
    print("\nStarting JARVIS Phase 1/2/3...")
    print("Press Ctrl + C to stop completely.\n")

    set_ui_state("BOOTING", "Starting J.A.R.V.I.S", "Initialising local systems")

    print_devices()

    boot_profile_start = time.perf_counter()
    wake_model = load_wake_word_model()
    profile_log("Wake model load", boot_profile_start)

    whisper_profile_start = time.perf_counter()
    whisper_model = load_whisper_model()
    profile_log("Whisper model load", whisper_profile_start)

    set_ui_state("BOOTING", "Loading AI brain", "Connecting to OpenAI")
    brain = JarvisBrain()

    set_ui_state("BOOTING", "Loading voice engine", "Preparing Kokoro TTS")
    tts = JarvisTTS(voice="en-GB-ThomasNeural", speed=1.05)

    set_ui_state("BOOTING", "Loading router", "Preparing local tools and AI tool brain")
    router = JarvisRouter(brain)

    reset_wake_model(wake_model)

    trigger_mode = {"value": "idle"}
    trigger_lock = threading.Lock()
    hotkey_trigger_queue = queue.Queue()
    keybind_stop_event = threading.Event()

    def set_trigger_mode(mode):
        with trigger_lock:
            trigger_mode["value"] = mode

            if mode != "keybind":
                keybind_stop_event.clear()

    def on_hotkey_pressed():
        with trigger_lock:
            mode = trigger_mode["value"]

            if mode == "idle":
                hotkey_trigger_queue.put(time.monotonic())
                return

            if mode == "keybind":
                keybind_stop_event.set()
                return

        print("Hotkey ignored while Jarvis is already handling a command.")

    hotkey_listener = None

    try:
        hotkey_listener = GlobalHotkeyListener(HOTKEY_TEXT, on_hotkey_pressed).start()
        print(f"Global keybind enabled: {hotkey_listener.display_name}")
    except Exception as error:
        print(f"Global keybind disabled: {error}")

    hotkey_label = hotkey_listener.display_name if hotkey_listener else HOTKEY_TEXT
    standby_detail = f"Say Hey Jarvis or press {hotkey_label}"
    command_count = {"value": 1}

    def next_filename():
        filename = f"active_command_{command_count['value']}.wav"
        command_count["value"] += 1
        return filename

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SIZE
    ) as stream:

        print("JARVIS is in sleep mode.")
        set_ui_state("STANDBY", "Awaiting wake phrase or keybind", standby_detail)
        print(f"Say: Hey Jarvis or press {hotkey_label}\n")

        while True:
            audio_block, overflowed = stream.read(CHUNK_SIZE)

            if overflowed:
                print("Warning: microphone buffer overflowed.")

            if consume_hotkey_trigger(hotkey_trigger_queue):
                print("\nGlobal keybind pressed.")

                reset_wake_model(wake_model)
                set_trigger_mode("keybind")
                keybind_stop_event.clear()

                try:
                    keybind_command_mode(
                        stream=stream,
                        whisper_model=whisper_model,
                        router=router,
                        tts=tts,
                        next_filename=next_filename,
                        stop_event=keybind_stop_event,
                    )
                finally:
                    set_trigger_mode("idle")

                reset_wake_model(wake_model)

                print("JARVIS is back in sleep mode.")
                set_ui_state(
                    "STANDBY",
                    "Awaiting wake phrase or keybind",
                    standby_detail,
                )
                print(f"Say: Hey Jarvis or press {hotkey_label}\n")
                continue

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

                set_trigger_mode("wake")

                try:
                    wake_word_command_mode(
                        stream=stream,
                        whisper_model=whisper_model,
                        router=router,
                        tts=tts,
                        next_filename=next_filename,
                    )
                finally:
                    set_trigger_mode("idle")

                reset_wake_model(wake_model)

                print("JARVIS is back in sleep mode.")
                set_ui_state(
                    "STANDBY",
                    "Awaiting wake phrase or keybind",
                    standby_detail,
                )
                print(f"Say: Hey Jarvis or press {hotkey_label}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        set_ui_state("OFFLINE", "Jarvis stopped", "Shutdown requested")
        print("\nJARVIS stopped by user.")
