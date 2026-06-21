from pathlib import Path
import time
import re
import queue
import threading
import asyncio
import tempfile
import uuid

import edge_tts
import pygame


BASE_DIR = Path(__file__).resolve().parent.parent
AUDIO_DIR = BASE_DIR / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

DEFAULT_VOICE = "en-GB-ThomasNeural"
DEFAULT_VOLUME = "+0%"


class JarvisTTS:
    """
    Edge TTS engine.
    Keeps the same speak() and speak_stream() methods as the old Kokoro engine.
    """

    def __init__(self, voice=DEFAULT_VOICE, speed=1.0, rate=None, volume=DEFAULT_VOLUME):
        self.voice = voice or DEFAULT_VOICE
        self.speed = speed
        self.rate = rate if rate is not None else self._speed_to_rate(speed)
        self.volume = volume

        print("Loading Edge TTS...")
        print(f"Voice: {self.voice}")
        print(f"Rate: {self.rate}")
        print(f"Volume: {self.volume}")
        print("Edge TTS loaded.")

    def _speed_to_rate(self, speed):
        try:
            percent = int(round((float(speed) - 1.0) * 100))
        except Exception:
            percent = 0

        percent = max(-50, min(50, percent))

        if percent >= 0:
            return f"+{percent}%"

        return f"{percent}%"

    async def _generate_audio_async(self, text, output_path):
        communicate = edge_tts.Communicate(
            text=text,
            voice=self.voice,
            rate=self.rate,
            volume=self.volume,
        )
        await communicate.save(str(output_path))

    def _generate_audio_file(self, text):
        if not text or not text.strip():
            return None

        output_path = Path(tempfile.gettempdir()) / f"jarvis_edge_{uuid.uuid4().hex}.mp3"

        asyncio.run(
            self._generate_audio_async(
                text=text.strip(),
                output_path=output_path
            )
        )

        return output_path

    def _ensure_pygame_ready(self):
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def _play_audio_file(self, audio_path):
        if not audio_path or not Path(audio_path).exists():
            return

        self._ensure_pygame_ready()

        pygame.mixer.music.load(str(audio_path))
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.03)

        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

    def _speak_text(self, text):
        audio_path = self._generate_audio_file(text)
        self._play_audio_file(audio_path)

    def speak(self, text):
        if not text or not text.strip():
            return

        start_time = time.time()
        print("Generating Edge TTS speech...")

        try:
            self._speak_text(text)
        except Exception as error:
            print(f"Edge TTS playback error: {error}")
            return

        total_time = time.time() - start_time
        print(f"Finished speaking. TTS total time: {total_time:.2f}s")

    def _extract_ready_sentences(self, buffer, force=False):
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
        try:
            self._ensure_pygame_ready()

            while True:
                text = speech_queue.get()

                if text is None:
                    speech_queue.task_done()
                    break

                try:
                    self._speak_text(text)
                except Exception as error:
                    print(f"Edge TTS segment error: {error}")

                speech_queue.task_done()

        except Exception as error:
            print(f"Edge TTS stream worker error: {error}")

        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass

    def speak_stream(self, text_chunks):
        start_time = time.time()
        print("Streaming AI response into Edge TTS...")

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
                    print(f"\nFirst sentence ready for Edge TTS after {delay:.2f}s")
                    first_sentence_queued = True

                speech_queue.put(sentence)

        ready_sentences, buffer = self._extract_ready_sentences(buffer, force=True)

        for sentence in ready_sentences:
            if not first_sentence_queued:
                delay = time.time() - start_time
                print(f"\nFirst sentence ready for Edge TTS after {delay:.2f}s")
                first_sentence_queued = True

            speech_queue.put(sentence)

        speech_queue.put(None)
        speech_queue.join()
        worker.join()

        print()

        total_time = time.time() - start_time
        print(f"Finished streamed speech. Total time: {total_time:.2f}s")

        return "".join(full_response_parts).strip()