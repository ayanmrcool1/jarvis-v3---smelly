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


def profile_log(label, start_time=None, extra=""):
    """
    Lightweight timing logger.
    """
    if start_time is None:
        print(f"[PROFILE] {label}{extra}")
        return

    elapsed = time.perf_counter() - start_time
    print(f"[PROFILE] {label}: {elapsed:.2f}s{extra}")


class JarvisTTS:
    """
    Edge TTS engine.
    Keeps the same speak() and speak_stream() methods as the old Kokoro engine.

    Optimisations:
    - Profiles generation vs playback time.
    - Streams on sentence/phrase boundaries.
    - Uses a synth worker + playback worker so the next segment can be generated
      while the current segment is already playing.
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

    def _generate_audio_file_profiled(self, text):
        start_time = time.perf_counter()
        audio_path = self._generate_audio_file(text)
        elapsed = time.perf_counter() - start_time
        return audio_path, elapsed

    def _ensure_pygame_ready(self):
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    def _play_audio_file(self, audio_path):
        if not audio_path or not Path(audio_path).exists():
            return 0.0

        self._ensure_pygame_ready()

        start_time = time.perf_counter()

        pygame.mixer.music.load(str(audio_path))
        pygame.mixer.music.play()

        while pygame.mixer.music.get_busy():
            time.sleep(0.02)

        elapsed = time.perf_counter() - start_time

        try:
            pygame.mixer.music.unload()
        except Exception:
            pass

        try:
            Path(audio_path).unlink(missing_ok=True)
        except Exception:
            pass

        return elapsed

    def _speak_text(self, text):
        audio_path = self._generate_audio_file(text)
        self._play_audio_file(audio_path)

    def speak(self, text):
        if not text or not text.strip():
            return

        total_start = time.perf_counter()
        print("Generating Edge TTS speech...")

        try:
            generate_start = time.perf_counter()
            audio_path = self._generate_audio_file(text)
            generate_time = time.perf_counter() - generate_start

            play_start = time.perf_counter()
            play_time = self._play_audio_file(audio_path)
            if play_time <= 0:
                play_time = time.perf_counter() - play_start

            print(f"[PROFILE] TTS generate: {generate_time:.2f}s")
            print(f"[PROFILE] TTS playback: {play_time:.2f}s")

        except Exception as error:
            print(f"Edge TTS playback error: {error}")
            return

        total_time = time.perf_counter() - total_start
        print(f"Finished speaking. TTS total time: {total_time:.2f}s")

    def _extract_ready_segments(self, buffer, force=False):
        """
        Extract speakable chunks from a streaming text buffer.

        Priority:
        1. Full sentences ending in . ! ?
        2. Long phrase boundaries like comma/semicolon/colon/dash
        3. Long text fallback on whitespace
        """

        ready_segments = []

        while True:
            match = re.match(r"(.+?[.!?])(\s+|$)", buffer, flags=re.DOTALL)

            if not match:
                break

            segment = match.group(1).strip()

            if segment:
                ready_segments.append(segment)

            buffer = buffer[match.end():].lstrip()

        # If the model is producing a long spoken phrase without sentence punctuation,
        # let Edge TTS begin at a natural phrase boundary instead of waiting forever.
        if not ready_segments and len(buffer.strip()) >= 90:
            phrase_match = None

            # Prefer punctuation phrase boundaries.
            for pattern in [
                r"^(.{45,110}?[,;:])\s+",
                r"^(.{45,110}?[–—-])\s+",
            ]:
                phrase_match = re.match(pattern, buffer, flags=re.DOTALL)
                if phrase_match:
                    break

            if phrase_match:
                segment = phrase_match.group(1).strip()
                if segment:
                    ready_segments.append(segment)
                    buffer = buffer[phrase_match.end():].lstrip()

            # Fallback: if text is getting very long, split at the last whitespace
            # before about 110 chars. This prevents long silent waits.
            elif len(buffer.strip()) >= 130:
                split_at = buffer.rfind(" ", 70, 115)

                if split_at > 0:
                    segment = buffer[:split_at].strip()

                    if segment:
                        ready_segments.append(segment)

                    buffer = buffer[split_at:].lstrip()

        if force and buffer.strip():
            ready_segments.append(buffer.strip())
            buffer = ""

        return ready_segments, buffer

    # Backward-compatible name in case any other file calls it.
    def _extract_ready_sentences(self, buffer, force=False):
        return self._extract_ready_segments(buffer, force=force)

    def _synth_queue_worker(self, synth_queue, play_queue):
        """
        Generates Edge TTS audio files in order.
        Playback happens in a separate worker so synthesis for the next segment can
        happen while the current segment is playing.
        """

        while True:
            item = synth_queue.get()

            if item is None:
                synth_queue.task_done()
                play_queue.put(None)
                break

            index, text = item

            try:
                audio_path, synth_time = self._generate_audio_file_profiled(text)
                play_queue.put((index, text, audio_path, synth_time))
            except Exception as error:
                print(f"Edge TTS synth segment error: {error}")
                play_queue.put((index, text, None, 0.0))

            synth_queue.task_done()

    def _play_queue_worker(self, play_queue):
        try:
            self._ensure_pygame_ready()

            while True:
                item = play_queue.get()

                if item is None:
                    play_queue.task_done()
                    break

                index, text, audio_path, synth_time = item

                try:
                    play_time = self._play_audio_file(audio_path)
                    print(
                        f"[PROFILE] TTS segment {index}: "
                        f"synth {synth_time:.2f}s, play {play_time:.2f}s, chars {len(text)}"
                    )
                except Exception as error:
                    print(f"Edge TTS playback segment error: {error}")

                play_queue.task_done()

        except Exception as error:
            print(f"Edge TTS play worker error: {error}")

        finally:
            try:
                pygame.mixer.quit()
            except Exception:
                pass

    def speak_stream(self, text_chunks):
        start_time = time.perf_counter()
        print("Streaming AI response into Edge TTS...")

        synth_queue = queue.Queue()
        play_queue = queue.Queue()

        synth_worker = threading.Thread(
            target=self._synth_queue_worker,
            args=(synth_queue, play_queue),
            daemon=True
        )

        play_worker = threading.Thread(
            target=self._play_queue_worker,
            args=(play_queue,),
            daemon=True
        )

        synth_worker.start()
        play_worker.start()

        buffer = ""
        full_response_parts = []
        first_segment_queued = False
        segment_index = 1

        for chunk in text_chunks:
            print(chunk, end="", flush=True)

            full_response_parts.append(chunk)
            buffer += chunk

            ready_segments, buffer = self._extract_ready_segments(buffer)

            for segment in ready_segments:
                if not first_segment_queued:
                    delay = time.perf_counter() - start_time
                    print(f"\nFirst phrase ready for Edge TTS after {delay:.2f}s")
                    first_segment_queued = True

                synth_queue.put((segment_index, segment))
                segment_index += 1

        ready_segments, buffer = self._extract_ready_segments(buffer, force=True)

        for segment in ready_segments:
            if not first_segment_queued:
                delay = time.perf_counter() - start_time
                print(f"\nFirst phrase ready for Edge TTS after {delay:.2f}s")
                first_segment_queued = True

            synth_queue.put((segment_index, segment))
            segment_index += 1

        synth_queue.put(None)

        synth_queue.join()
        play_queue.join()

        synth_worker.join()
        play_worker.join()

        print()

        total_time = time.perf_counter() - start_time
        print(f"Finished streamed speech. Total time: {total_time:.2f}s")

        return "".join(full_response_parts).strip()
