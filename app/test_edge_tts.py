import asyncio
import tempfile
import time
from pathlib import Path

import edge_tts
import pygame


VOICE = "en-GB-ThomasNeural"
RATE = "+0%"
VOLUME = "+0%"


async def make_audio(text, output_path):
    communicate = edge_tts.Communicate(
        text=text,
        voice=VOICE,
        rate=RATE,
        volume=VOLUME,
    )
    await communicate.save(str(output_path))


def play_audio(path):
    pygame.mixer.init()
    pygame.mixer.music.load(str(path))
    pygame.mixer.music.play()

    while pygame.mixer.music.get_busy():
        time.sleep(0.05)

    pygame.mixer.quit()


async def main():
    text = "Good evening, sir. Edge voice systems are now online."

    output_path = Path(tempfile.gettempdir()) / "jarvis_edge_test.mp3"

    t0 = time.perf_counter()
    await make_audio(text, output_path)
    t1 = time.perf_counter()

    print(f"Generated in {t1 - t0:.2f}s")
    print(f"Audio file: {output_path}")

    play_audio(output_path)


if __name__ == "__main__":
    asyncio.run(main())