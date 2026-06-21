import time
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
from datetime import datetime


# =========================
# JARVIS PHASE 1 SETTINGS
# =========================

SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # 80ms at 16kHz

# Wake word sensitivity.
# Higher = fewer false triggers.
WAKE_THRESHOLD = 0.85

# Speech recording settings.
# Jarvis now records until silence instead of recording a fixed 5 seconds.
SPEECH_START_RMS = 320.0
SPEECH_END_RMS = 220.0
SILENCE_SECONDS_TO_STOP = 1
MAX_COMMAND_SECONDS = 12.0
MIN_COMMAND_SECONDS = 0.4
PRE_ROLL_SECONDS = 0.32

# Try 1 first for speed.
# If transcription becomes worse, change this to 5.
WHISPER_BEAM_SIZE = 1

# Ignore clips quieter than this after recording.
MIN_AUDIO_RMS = 120.0

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


def calculate_rms(audio):
    """Calculate loudness of an audio chunk."""
    return float(np.sqrt(np.mean(audio.astype(np.float32) ** 2)))


def print_devices():
    print("\nAvailable audio devices:")
    print(sd.query_devices())
    print("\nUsing default input device.\n")


def load_wake_word_model():
    print("Downloading/loading OpenWakeWord models...")
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
    This makes Jarvis feel much faster than recording a fixed 5-second clip.
    """
    print("Waiting for speech...")

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
                last_wait_message = time.time()

            if chunk_rms >= SPEECH_START_RMS:
                recording = True
                recorded_chunks = list(pre_roll)
                chunks_recorded_after_start = 1
                silent_chunks = 0
                print("Speech detected. Recording...")

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
                break

            if chunks_recorded_after_start >= max_chunks:
                print("Max command length reached. Stopping recording.")
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
        return ""

    print(f"Transcribing with beam_size={WHISPER_BEAM_SIZE}...")

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
        return ""

    if is_likely_hallucination(transcription):
        print(f"Ignored likely Whisper hallucination: {transcription}\n")
        return ""

    print("\n==============================")
    print("TRANSCRIPTION:")
    print(transcription)
    print("==============================\n")

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

def flush_microphone_buffer(stream, seconds=0.4):
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

def handle_local_quick_command(transcription):
    """
    Handles simple commands locally without sending them to OpenAI.
    This makes common commands much faster.
    """

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

def active_listening_mode(stream, whisper_model, brain, tts):
    print("\nJARVIS ACTIVE.")
    print("Speak normally. Say 'stop listening' or 'go to sleep' to exit.\n")

    command_count = 1

    while True:
        wav_path, rms = record_until_silence(
            stream=stream,
            filename=f"active_command_{command_count}.wav"
        )

        transcription = transcribe_audio(whisper_model, wav_path, rms)

        if transcription and should_exit_active_mode(transcription):
            print("Exit phrase detected. Returning to sleep mode.\n")
            tts.speak("Going back to sleep.")
            flush_microphone_buffer(stream)
            break

        if transcription:
            quick_response = handle_local_quick_command(transcription)

            print("\n==============================")
            print("JARVIS RESPONSE:")

            if quick_response:
                print("Handled locally without OpenAI.")
                jarvis_response = quick_response
                print(jarvis_response)
                print("==============================\n")

                tts.speak(jarvis_response)

            else:
                print("Streaming from OpenAI brain...")
                jarvis_response = tts.speak_stream(
                    brain.stream_ask(transcription)
                )
                print("==============================\n")

            # Prevent speaker echo from being picked up immediately after speaking.
            flush_microphone_buffer(stream)

        command_count += 1


def main():
    print("\nStarting JARVIS Phase 1/2/3...")
    print("Press Ctrl + C to stop completely.\n")

    print_devices()

    wake_model = load_wake_word_model()
    whisper_model = load_whisper_model()
    brain = JarvisBrain()
    tts = JarvisTTS(voice="am_adam", speed=1.18)

    reset_wake_model(wake_model)

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=CHANNELS,
        dtype="int16",
        blocksize=CHUNK_SIZE
    ) as stream:

        print("JARVIS is in sleep mode.")
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

                reset_wake_model(wake_model)

                active_listening_mode(stream, whisper_model, brain, tts)

                reset_wake_model(wake_model)

                print("JARVIS is back in sleep mode.")
                print("Say: Hey Jarvis\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nJARVIS stopped by user.")