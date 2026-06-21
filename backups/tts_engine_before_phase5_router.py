from pathlib import Path
import time
import re
import queue
import threading

import numpy as np
import sounddevice as sd
from kokoro import KPipeline


# =========================
# JARVIS PHASE 3 TTS ENGINE
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 24000

DEFAULT_VOICE = "am_adam"


class JarvisTTS:
    """
    Local Kokoro text-to-speech engine.
    Supports normal speaking and sentence-by-sentence streamed speaking.
    """

    def __init__(self, voice=DEFAULT_VOICE, speed=1.18):
        self.voice = voice
        self.speed = speed

        print("Loading Kokoro TTS...")
        print(f"Voice: {self.voice}")
        print(f"Speed: {self.speed}")

        # 'a' = American English
        self.pipeline = KPipeline(lang_code="a")

        print("Kokoro TTS loaded.")

    def _play_text_to_stream(self, text, output_stream):
        """
        Generate Kokoro audio for a text segment and write it to an existing audio stream.
        """

        if not text or not text.strip():
            return

        text = text.strip()

        generator = self.pipeline(
            text,
            voice=self.voice,
            speed=self.speed
        )

        for _, _, audio in generator:
            if hasattr(audio, "cpu"):
                audio = audio.cpu().numpy()

            audio = np.asarray(audio, dtype=np.float32).reshape(-1)

            if audio.size == 0:
                continue

            output_stream.write(audio.reshape(-1, 1))

    def speak(self, text):
        """
        Speak a normal complete response.
        """

        if not text or not text.strip():
            return

        start_time = time.time()
        print("Generating/streaming speech...")

        try:
            with sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32"
            ) as output_stream:
                self._play_text_to_stream(text, output_stream)

        except Exception as error:
            print(f"TTS playback error: {error}")
            return

        total_time = time.time() - start_time
        print(f"Finished speaking. TTS total time: {total_time:.2f}s")

    def _extract_ready_sentences(self, buffer, force=False):
        """
        Pull complete sentences from the buffer.
        Leaves incomplete text in the buffer until more tokens arrive.
        """

        ready_sentences = []

        while True:
            match = re.match(r"(.+?[.!?])(\s+|$)", buffer, flags=re.DOTALL)

            if not match:
                break

            sentence = match.group(1).strip()

            if sentence:
                ready_sentences.append(sentence)

            buffer = buffer[match.end():].lstrip()

        if force and buffer.strip():
            ready_sentences.append(buffer.strip())
            buffer = ""

        return ready_sentences, buffer

    def _tts_queue_worker(self, speech_queue):
        """
        Background worker that speaks text segments as they are queued.
        """

        try:
            with sd.OutputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32"
            ) as output_stream:

                while True:
                    text = speech_queue.get()

                    if text is None:
                        speech_queue.task_done()
                        break

                    self._play_text_to_stream(text, output_stream)
                    speech_queue.task_done()

        except Exception as error:
            print(f"TTS stream worker error: {error}")

    def speak_stream(self, text_chunks):
        """
        Accepts streamed text chunks from the AI brain.
        Prints the response live and speaks completed sentences using a TTS worker thread.
        """

        start_time = time.time()
        print("Streaming AI response into TTS...")

        speech_queue = queue.Queue()
        worker = threading.Thread(
            target=self._tts_queue_worker,
            args=(speech_queue,),
            daemon=True
        )
        worker.start()

        buffer = ""
        full_response_parts = []
        first_sentence_queued = False

        for chunk in text_chunks:
            print(chunk, end="", flush=True)

            full_response_parts.append(chunk)
            buffer += chunk

            ready_sentences, buffer = self._extract_ready_sentences(buffer)

            for sentence in ready_sentences:
                if not first_sentence_queued:
                    delay = time.time() - start_time
                    print(f"\nFirst sentence ready for TTS after {delay:.2f}s")
                    first_sentence_queued = True

                speech_queue.put(sentence)

        ready_sentences, buffer = self._extract_ready_sentences(buffer, force=True)

        for sentence in ready_sentences:
            if not first_sentence_queued:
                delay = time.time() - start_time
                print(f"\nFirst sentence ready for TTS after {delay:.2f}s")
                first_sentence_queued = True

            speech_queue.put(sentence)

        speech_queue.put(None)
        speech_queue.join()
        worker.join()

        print()

        total_time = time.time() - start_time
        print(f"Finished streamed speech. Total time: {total_time:.2f}s")

        return "".join(full_response_parts).strip()