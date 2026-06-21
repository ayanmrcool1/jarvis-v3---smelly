from pathlib import Path
import hashlib
import json
import os
import time
import re
import queue
import threading
import asyncio
import tempfile
import uuid

import edge_tts
import pygame
import requests
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / ".env"
AUDIO_DIR = BASE_DIR / "recordings"
AUDIO_DIR.mkdir(exist_ok=True)

DEFAULT_VOICE = "en-GB-ThomasNeural"
DEFAULT_VOLUME = "+0%"

DEFAULT_TTS_PROVIDER = "edge"

ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1/text-to-speech"
ELEVENLABS_CACHE_DIR = BASE_DIR / "data" / "tts_cache" / "elevenlabs"
DEFAULT_ELEVENLABS_VOICE_ID = "zDSojkKhhVNCWoYn9KW7"
DEFAULT_ELEVENLABS_MODEL_ID = "eleven_flash_v2_5"
DEFAULT_ELEVENLABS_OUTPUT_FORMAT = "mp3_44100_128"
DEFAULT_ELEVENLABS_MAX_CHARS = 800
DEFAULT_ELEVENLABS_TIMEOUT_SECONDS = 8
DEFAULT_ELEVENLABS_CACHE_ENABLED = True
DEFAULT_ELEVENLABS_CACHE_MAX_MB = 500
DEFAULT_ELEVENLABS_CACHE_MAX_AGE_DAYS = 30

load_dotenv(ENV_PATH)


def profile_log(label, start_time=None, extra=""):
    """
    Lightweight timing logger.
    """
    if start_time is None:
        print(f"[PROFILE] {label}{extra}")
        return

    elapsed = time.perf_counter() - start_time
    print(f"[PROFILE] {label}: {elapsed:.2f}s{extra}")


def env_bool(name, default=False):
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name, default, minimum=None):
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    try:
        parsed = int(value)
    except ValueError:
        print(f"Invalid {name}={value!r}; using {default}.")
        return default

    if minimum is not None:
        parsed = max(minimum, parsed)

    return parsed


def env_float_optional(name, minimum=None, maximum=None):
    value = os.getenv(name)

    if value is None or not value.strip():
        return None

    try:
        parsed = float(value)
    except ValueError:
        print(f"Invalid {name}={value!r}; ignoring it.")
        return None

    if minimum is not None:
        parsed = max(minimum, parsed)

    if maximum is not None:
        parsed = min(maximum, parsed)

    return parsed


def env_bool_optional(name):
    value = os.getenv(name)

    if value is None or not value.strip():
        return None

    return value.strip().lower() in {"1", "true", "yes", "on"}


class JarvisTTS:
    """
    TTS provider wrapper.
    Edge TTS remains the reliable local/default provider, and ElevenLabs can be
    enabled as a premium output layer with Edge fallback.

    Optimisations:
    - Profiles generation vs playback time.
    - Streams Edge on sentence/phrase boundaries.
    - Uses a synth worker + playback worker for Edge streaming so the next
      segment can be generated while the current segment is already playing.
    """

    def __init__(self, voice=DEFAULT_VOICE, speed=1.0, rate=None, volume=DEFAULT_VOLUME):
        self.voice = voice or DEFAULT_VOICE
        self.speed = speed
        self.rate = rate if rate is not None else self._speed_to_rate(speed)
        self.volume = volume

        requested_provider = os.getenv("TTS_PROVIDER", DEFAULT_TTS_PROVIDER).strip().lower()
        if requested_provider in {"elevenlabs", "eleven_labs", "11labs"}:
            self.provider = "elevenlabs"
        elif requested_provider in {"edge", "edge_tts", "edge-tts"}:
            self.provider = "edge"
        else:
            print(f"Unknown TTS_PROVIDER={requested_provider!r}; using Edge TTS.")
            self.provider = "edge"

        self.elevenlabs_api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
        self.elevenlabs_voice_id = os.getenv(
            "ELEVENLABS_VOICE_ID",
            DEFAULT_ELEVENLABS_VOICE_ID
        ).strip()
        self.elevenlabs_model_id = os.getenv(
            "ELEVENLABS_MODEL_ID",
            DEFAULT_ELEVENLABS_MODEL_ID
        ).strip()
        self.elevenlabs_output_format = os.getenv(
            "ELEVENLABS_OUTPUT_FORMAT",
            DEFAULT_ELEVENLABS_OUTPUT_FORMAT
        ).strip()
        self.elevenlabs_max_chars = env_int(
            "ELEVENLABS_MAX_CHARS",
            DEFAULT_ELEVENLABS_MAX_CHARS,
            minimum=1
        )
        self.elevenlabs_timeout_seconds = env_int(
            "ELEVENLABS_TIMEOUT_SECONDS",
            DEFAULT_ELEVENLABS_TIMEOUT_SECONDS,
            minimum=1
        )
        self.elevenlabs_cache_enabled = env_bool(
            "ELEVENLABS_CACHE_ENABLED",
            DEFAULT_ELEVENLABS_CACHE_ENABLED
        )
        self.elevenlabs_cache_max_mb = env_int(
            "ELEVENLABS_CACHE_MAX_MB",
            DEFAULT_ELEVENLABS_CACHE_MAX_MB,
            minimum=0
        )
        self.elevenlabs_cache_max_age_days = env_int(
            "ELEVENLABS_CACHE_MAX_AGE_DAYS",
            DEFAULT_ELEVENLABS_CACHE_MAX_AGE_DAYS,
            minimum=0
        )
        self.elevenlabs_voice_settings = self._load_elevenlabs_voice_settings()

        print("Loading Edge TTS...")
        print(f"Voice: {self.voice}")
        print(f"Rate: {self.rate}")
        print(f"Volume: {self.volume}")
        print("Edge TTS loaded.")

        if self.provider == "elevenlabs":
            print("ElevenLabs TTS enabled with Edge fallback.")
            print(f"ElevenLabs voice: {self.elevenlabs_voice_id}")
            print(f"ElevenLabs model: {self.elevenlabs_model_id}")
            if self.elevenlabs_cache_enabled:
                self._cleanup_elevenlabs_cache()
                print(f"ElevenLabs cache: {ELEVENLABS_CACHE_DIR}")
            else:
                print("ElevenLabs cache disabled.")

    def _speed_to_rate(self, speed):
        try:
            percent = int(round((float(speed) - 1.0) * 100))
        except Exception:
            percent = 0

        percent = max(-50, min(50, percent))

        if percent >= 0:
            return f"+{percent}%"

        return f"{percent}%"

    def _load_elevenlabs_voice_settings(self):
        settings = {}

        stability = env_float_optional("ELEVENLABS_STABILITY", minimum=0.0, maximum=1.0)
        similarity_boost = env_float_optional(
            "ELEVENLABS_SIMILARITY_BOOST",
            minimum=0.0,
            maximum=1.0
        )
        style = env_float_optional("ELEVENLABS_STYLE", minimum=0.0, maximum=1.0)
        use_speaker_boost = env_bool_optional("ELEVENLABS_USE_SPEAKER_BOOST")

        if stability is not None:
            settings["stability"] = stability

        if similarity_boost is not None:
            settings["similarity_boost"] = similarity_boost

        if style is not None:
            settings["style"] = style

        if use_speaker_boost is not None:
            settings["use_speaker_boost"] = use_speaker_boost

        return settings

    def _safe_elevenlabs_error(self, response):
        try:
            return response.text[:400]
        except Exception:
            return "<unable to read response body>"

    def _elevenlabs_cache_key(self, text):
        cache_identity = {
            "text": text,
            "voice_id": self.elevenlabs_voice_id,
            "model_id": self.elevenlabs_model_id,
            "voice_settings": self.elevenlabs_voice_settings,
            "output_format": self.elevenlabs_output_format,
        }
        identity_json = json.dumps(
            cache_identity,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":")
        )

        return hashlib.sha256(identity_json.encode("utf-8")).hexdigest()

    def _elevenlabs_cache_path(self, text):
        return ELEVENLABS_CACHE_DIR / f"{self._elevenlabs_cache_key(text)}.mp3"

    def _is_safe_elevenlabs_cache_path(self, path):
        try:
            Path(path).resolve().relative_to(ELEVENLABS_CACHE_DIR.resolve())
            return True
        except Exception:
            return False

    def _iter_elevenlabs_cache_files(self):
        if not ELEVENLABS_CACHE_DIR.exists():
            return []

        cache_dir = ELEVENLABS_CACHE_DIR.resolve()
        expected_dir = (BASE_DIR / "data" / "tts_cache" / "elevenlabs").resolve()

        if cache_dir != expected_dir:
            print("ElevenLabs cache cleanup skipped: unexpected cache directory.")
            return []

        files = []

        for path in ELEVENLABS_CACHE_DIR.iterdir():
            if path.is_file() and path.suffix.lower() == ".mp3":
                if self._is_safe_elevenlabs_cache_path(path):
                    files.append(path)

        return files

    def _delete_cache_file(self, path):
        if not self._is_safe_elevenlabs_cache_path(path):
            print(f"Skipped unsafe ElevenLabs cache delete: {path}")
            return 0

        try:
            size = path.stat().st_size
        except OSError:
            size = 0

        try:
            path.unlink(missing_ok=True)
            return size
        except Exception as error:
            print(f"ElevenLabs cache cleanup warning: {error}")
            return 0

    def _cleanup_elevenlabs_cache(self):
        if not self.elevenlabs_cache_enabled:
            return

        ELEVENLABS_CACHE_DIR.mkdir(parents=True, exist_ok=True)

        now = time.time()
        max_age_seconds = self.elevenlabs_cache_max_age_days * 24 * 60 * 60
        cache_files = self._iter_elevenlabs_cache_files()

        if max_age_seconds > 0:
            for path in cache_files:
                try:
                    if now - path.stat().st_mtime > max_age_seconds:
                        self._delete_cache_file(path)
                except OSError:
                    pass

        cache_files = self._iter_elevenlabs_cache_files()
        max_bytes = self.elevenlabs_cache_max_mb * 1024 * 1024
        total_bytes = 0
        file_details = []

        for path in cache_files:
            try:
                stat = path.stat()
            except OSError:
                continue

            total_bytes += stat.st_size
            file_details.append((path, stat.st_size, stat.st_atime, stat.st_mtime))

        if total_bytes <= max_bytes:
            return

        file_details.sort(key=lambda item: (item[2], item[3]))

        for path, size, _accessed_at, _modified_at in file_details:
            if total_bytes <= max_bytes:
                break

            deleted_size = self._delete_cache_file(path) or size
            total_bytes = max(0, total_bytes - deleted_size)

    def _elevenlabs_request_payload(self, text):
        payload = {
            "text": text,
            "model_id": self.elevenlabs_model_id,
        }

        if self.elevenlabs_voice_settings:
            payload["voice_settings"] = self.elevenlabs_voice_settings

        return payload

    def _write_elevenlabs_audio(self, output_path, content):
        output_path.parent.mkdir(parents=True, exist_ok=True)

        if output_path.parent.resolve() == ELEVENLABS_CACHE_DIR.resolve():
            temp_path = output_path.with_suffix(f".{uuid.uuid4().hex}.tmp")

            try:
                temp_path.write_bytes(content)
                temp_path.replace(output_path)
            finally:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

            return output_path

        output_path.write_bytes(content)
        return output_path

    def _generate_elevenlabs_audio_file(self, text, output_path):
        url = f"{ELEVENLABS_API_BASE_URL}/{self.elevenlabs_voice_id}"
        headers = {
            "xi-api-key": self.elevenlabs_api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
        }
        params = {
            "output_format": self.elevenlabs_output_format,
        }

        response = requests.post(
            url,
            headers=headers,
            params=params,
            json=self._elevenlabs_request_payload(text),
            timeout=self.elevenlabs_timeout_seconds,
        )

        if response.status_code >= 400:
            error_text = self._safe_elevenlabs_error(response)
            raise RuntimeError(
                f"HTTP {response.status_code} from ElevenLabs: {error_text}"
            )

        if not response.content:
            raise RuntimeError("ElevenLabs returned an empty audio response.")

        return self._write_elevenlabs_audio(output_path, response.content)

    def _can_use_elevenlabs(self, text):
        if self.provider != "elevenlabs":
            return False

        if not self.elevenlabs_api_key:
            print("ElevenLabs API key missing; falling back to Edge TTS.")
            return False

        if not self.elevenlabs_voice_id:
            print("ElevenLabs voice ID missing; falling back to Edge TTS.")
            return False

        if not self.elevenlabs_model_id:
            print("ElevenLabs model ID missing; falling back to Edge TTS.")
            return False

        if len(text) > self.elevenlabs_max_chars:
            print(
                "ElevenLabs text exceeds "
                f"ELEVENLABS_MAX_CHARS={self.elevenlabs_max_chars}; "
                "falling back to Edge TTS."
            )
            return False

        return True

    def _speak_with_elevenlabs(self, text):
        text = text.strip()

        if not self._can_use_elevenlabs(text):
            return False

        total_start = time.perf_counter()
        print("Generating ElevenLabs speech...")

        try:
            self._cleanup_elevenlabs_cache()

            if self.elevenlabs_cache_enabled:
                audio_path = self._elevenlabs_cache_path(text)

                if audio_path.exists():
                    print("Using cached ElevenLabs speech.")
                    try:
                        os.utime(audio_path, None)
                    except Exception:
                        pass

                    play_time = self._play_audio_file(audio_path, delete_after=False)
                    print(f"[PROFILE] ElevenLabs cache playback: {play_time:.2f}s")
                    return True

                output_path = audio_path
                delete_after_playback = False
            else:
                output_path = Path(tempfile.gettempdir()) / (
                    f"jarvis_elevenlabs_{uuid.uuid4().hex}.mp3"
                )
                delete_after_playback = True

            generate_start = time.perf_counter()
            audio_path = self._generate_elevenlabs_audio_file(text, output_path)
            generate_time = time.perf_counter() - generate_start

            play_time = self._play_audio_file(
                audio_path,
                delete_after=delete_after_playback
            )

            if self.elevenlabs_cache_enabled:
                self._cleanup_elevenlabs_cache()

            print(f"[PROFILE] ElevenLabs generate: {generate_time:.2f}s")
            print(f"[PROFILE] ElevenLabs playback: {play_time:.2f}s")
            print(
                "Finished ElevenLabs speech. "
                f"TTS total time: {time.perf_counter() - total_start:.2f}s"
            )
            return True

        except Exception as error:
            print(f"ElevenLabs TTS error: {error}")
            print("Falling back to Edge TTS.")
            return False

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

    def _play_audio_file(self, audio_path, delete_after=True):
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

        if delete_after:
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

        if self._speak_with_elevenlabs(text):
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

    def _speak_stream_with_elevenlabs(self, text_chunks):
        start_time = time.perf_counter()
        print("Collecting AI response for ElevenLabs TTS...")

        full_response_parts = []

        for chunk in text_chunks:
            print(chunk, end="", flush=True)
            full_response_parts.append(chunk)

        print()

        full_response = "".join(full_response_parts).strip()

        if full_response:
            self.speak(full_response)

        total_time = time.perf_counter() - start_time
        print(f"Finished ElevenLabs streamed response speech. Total time: {total_time:.2f}s")

        return full_response

    def speak_stream(self, text_chunks):
        if self.provider == "elevenlabs":
            return self._speak_stream_with_elevenlabs(text_chunks)

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
