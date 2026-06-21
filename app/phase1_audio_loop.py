import time
import math
from pathlib import Path
from collections import deque

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
from ui_state import write_ui_state, append_chat_message

# =========================
# JARVIS PHASE 1 SETTINGS
# =========================

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

WHISPER_BEAM_SIZE = 1
MIN_AUDIO_RMS = 180.0

EXIT_PHRASES = [
    "stop listening",
    "go to sleep",
    "that is all",
    "that's all",
    "goodbye",
    "bye",
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


def record_until_silence(stream, filename):
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
    silence_chunks_needed = max(1, math.ceil((SILENCE_SECONDS_TO_STOP * SAMPLE_RATE) / CHUNK_SIZE))
    max_chunks = max(1, math.ceil((MAX_COMMAND_SECONDS * SAMPLE_RATE) / CHUNK_SIZE))

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

                speech_detected_at = time.perf_counter()
                recording_started_at = speech_detected_at

                print("Speech detected. Recording...")
                profile_log("Waited for speech", record_profile_start)
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

    if recording_started_at:
        profile_log("Recorded command audio", recording_started_at)

    profile_log(
        "Recording stage total",
        record_profile_start,
        extra=f" | audio_duration={len(audio) / SAMPLE_RATE:.2f}s"
    )

    return wav_path, total_rms


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
# ACTIVE MODE
# =========================

def active_listening_mode(stream, whisper_model, router, tts):
    print("\nJARVIS ACTIVE.")
    print("Speak normally. Say 'stop listening' or 'go to sleep' to exit.\n")

    set_ui_state("LISTENING", "Active mode", "Speak normally")

    command_count = 1

    while True:
        command_profile_start = time.perf_counter()

        wav_path, rms = record_until_silence(
            stream=stream,
            filename=f"active_command_{command_count}.wav"
        )

        transcription = transcribe_audio(whisper_model, wav_path, rms)

        if transcription and should_exit_active_mode(transcription):
            print("Exit phrase detected. Returning to sleep mode.\n")

            set_ui_state("SPEAKING", "Returning to sleep", "Going back to sleep")
            tts.speak("Going back to sleep.")

            flush_microphone_buffer(stream)

            set_ui_state("STANDBY", "Awaiting wake phrase")
            break

        if transcription:
            add_chat_message("user", transcription)

            print("\n==============================")
            print("JARVIS RESPONSE:")

            set_ui_state("THINKING", "Processing", transcription[:120])

            router_profile_start = time.perf_counter()
            route_result = router.handle(transcription)
            profile_log("Router decision", router_profile_start)

            print(f"Router source: {route_result.get('source')}")

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

            flush_microphone_buffer(stream)

            set_ui_state("LISTENING", "Ready for next command", "Speak naturally")

        command_count += 1


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
