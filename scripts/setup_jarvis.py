from __future__ import annotations

import argparse
import getpass
import os
import platform
import shutil
import subprocess
import sys
import time
import venv
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
VENV_DIR = ROOT_DIR / ".venv"
ENV_PATH = ROOT_DIR / ".env"
ENV_EXAMPLE_PATH = ROOT_DIR / ".env.example"
REQUIREMENTS_PATH = ROOT_DIR / "requirements.txt"
LOG_DIR = ROOT_DIR / "logs"

MIN_PYTHON = (3, 11)
MAX_PYTHON_EXCLUSIVE = (3, 13)

WINDOWS_ONLY_REQUIREMENTS = {
    "comtypes",
    "pycaw",
    "pywin32-ctypes",
    "win32_setctime",
}

CORE_IMPORT_CHECKS = [
    "dotenv",
    "openai",
    "sounddevice",
    "openwakeword",
    "faster_whisper",
    "edge_tts",
    "pygame",
    "PySide6",
    "psutil",
    "mss",
    "pyautogui",
]


class Logger:
    def __init__(self) -> None:
        LOG_DIR.mkdir(exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.path = LOG_DIR / f"setup_{timestamp}.log"
        self._file = self.path.open("w", encoding="utf-8")

    def write(self, message: str = "") -> None:
        print(message)
        self._file.write(message + "\n")
        self._file.flush()

    def close(self) -> None:
        self._file.close()


def command_text(command: list[str]) -> str:
    return " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)


def run_command(
    command: list[str],
    logger: Logger,
    *,
    check: bool = True,
    env: dict[str, str] | None = None,
) -> int:
    logger.write("")
    logger.write(f"$ {command_text(command)}")

    process = subprocess.Popen(
        command,
        cwd=ROOT_DIR,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert process.stdout is not None

    for line in process.stdout:
        logger.write(line.rstrip())

    return_code = process.wait()

    if check and return_code != 0:
        raise RuntimeError(f"Command failed with exit code {return_code}: {command_text(command)}")

    return return_code


def is_supported_python(version: tuple[int, int]) -> bool:
    return MIN_PYTHON <= version < MAX_PYTHON_EXCLUSIVE


def describe_supported_python() -> str:
    return "Python 3.11 or 3.12"


def validate_current_python(logger: Logger) -> None:
    version = sys.version_info[:2]

    logger.write(f"Using Python: {sys.executable}")
    logger.write(f"Python version: {platform.python_version()}")

    if is_supported_python(version):
        return

    raise RuntimeError(
        f"JARVIS setup needs {describe_supported_python()}. "
        f"This interpreter is Python {platform.python_version()}."
    )


def venv_python_path() -> Path:
    if os.name == "nt":
        return VENV_DIR / "Scripts" / "python.exe"

    return VENV_DIR / "bin" / "python"


def read_python_version(python_path: Path) -> tuple[int, int] | None:
    if not python_path.exists():
        return None

    result = subprocess.run(
        [
            str(python_path),
            "-c",
            "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')",
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return None

    try:
        major, minor = result.stdout.strip().split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def move_existing_venv(logger: Logger, reason: str) -> None:
    if not VENV_DIR.exists():
        return

    backup_path = ROOT_DIR / f".venv_backup_{time.strftime('%Y%m%d_%H%M%S')}"
    logger.write("")
    logger.write(f"Existing .venv will be moved aside: {reason}")
    logger.write(f"Backup path: {backup_path}")
    VENV_DIR.rename(backup_path)


def ensure_venv(logger: Logger, recreate: bool = False) -> Path:
    python_path = venv_python_path()

    if recreate and VENV_DIR.exists():
        move_existing_venv(logger, "--recreate-venv was requested")

    version = read_python_version(python_path)

    if VENV_DIR.exists() and not python_path.exists():
        move_existing_venv(logger, "it does not contain a Python executable")
        version = None

    if version and not is_supported_python(version):
        move_existing_venv(
            logger,
            f"it uses Python {version[0]}.{version[1]}, but JARVIS expects {describe_supported_python()}",
        )
        version = None

    if not VENV_DIR.exists():
        logger.write("")
        logger.write("Creating .venv...")
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV_DIR)

    python_path = venv_python_path()

    if not python_path.exists():
        raise RuntimeError(f"Virtual environment Python was not created at {python_path}")

    logger.write(f"Virtual environment ready: {python_path}")
    return python_path


def requirement_name(line: str) -> str:
    clean = line.strip()

    if not clean or clean.startswith("#"):
        return ""

    clean = clean.split(";", 1)[0].strip()

    if " @ " in clean:
        return clean.split(" @ ", 1)[0].strip().lower()

    for separator in ["==", ">=", "<=", "~=", "!=", ">", "<"]:
        if separator in clean:
            return clean.split(separator, 1)[0].strip().lower()

    return clean.strip().lower()


def requirements_for_platform(logger: Logger) -> Path:
    system = platform.system()

    if system == "Windows":
        return REQUIREMENTS_PATH

    generated_path = LOG_DIR / f"requirements_{system.lower() or 'nonwindows'}_generated.txt"
    kept_lines: list[str] = []
    skipped: list[str] = []

    for line in REQUIREMENTS_PATH.read_text(encoding="utf-8").splitlines():
        name = requirement_name(line)

        if name in WINDOWS_ONLY_REQUIREMENTS:
            skipped.append(line.strip())
            continue

        kept_lines.append(line)

    generated_path.write_text("\n".join(kept_lines) + "\n", encoding="utf-8")

    if skipped:
        logger.write("")
        logger.write("Non-Windows install: skipping Windows-only packages:")
        for item in skipped:
            logger.write(f"  - {item}")

    return generated_path


def install_requirements(python_path: Path, logger: Logger, skip_install: bool = False) -> None:
    if skip_install:
        logger.write("")
        logger.write("Skipping dependency installation because --skip-install was requested.")
        return

    if not REQUIREMENTS_PATH.exists():
        raise RuntimeError(f"Missing requirements file: {REQUIREMENTS_PATH}")

    pip_env = os.environ.copy()
    pip_env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"

    run_command([str(python_path), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], logger, env=pip_env)

    requirements_path = requirements_for_platform(logger)
    run_command([str(python_path), "-m", "pip", "install", "-r", str(requirements_path)], logger, env=pip_env)

    logger.write("")
    logger.write("Checking installed package metadata...")
    run_command([str(python_path), "-m", "pip", "check"], logger, check=False, env=pip_env)


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}

    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")

    return values


def set_env_values(path: Path, updates: dict[str, str]) -> None:
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    seen: set[str] = set()
    output: list[str] = []

    for raw_line in lines:
        stripped = raw_line.strip()

        if not stripped or stripped.startswith("#") or "=" not in raw_line:
            output.append(raw_line)
            continue

        key = raw_line.split("=", 1)[0].strip()

        if key in updates:
            output.append(f"{key}={updates[key]}")
            seen.add(key)
        else:
            output.append(raw_line)

    for key, value in updates.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def is_placeholder(value: str | None) -> bool:
    clean = str(value or "").strip()

    if not clean:
        return True

    return clean.lower() in {
        "put_key_here",
        "optional",
        "your_openai_api_key_here",
        "your_elevenlabs_api_key_here",
    }


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    suffix = "Y/n" if default else "y/N"
    answer = input(f"{prompt} [{suffix}]: ").strip().lower()

    if not answer:
        return default

    return answer in {"y", "yes"}


def configure_env(logger: Logger) -> None:
    if not ENV_PATH.exists():
        logger.write("")
        logger.write("Creating .env from .env.example...")

        if ENV_EXAMPLE_PATH.exists():
            shutil.copyfile(ENV_EXAMPLE_PATH, ENV_PATH)
        else:
            ENV_PATH.write_text("OPENAI_API_KEY=\nOPENAI_MODEL=gpt-4o-mini\n", encoding="utf-8")

        updates: dict[str, str] = {}

        if sys.stdin.isatty():
            logger.write("")
            logger.write("OPENAI_API_KEY is required for the voice brain and AI tools.")
            openai_key = getpass.getpass("Paste your OpenAI API key, or press Enter to fill it later: ").strip()

            if openai_key:
                updates["OPENAI_API_KEY"] = openai_key

            use_elevenlabs = ask_yes_no("Use ElevenLabs TTS instead of free Edge TTS?", default=False)
            updates["TTS_PROVIDER"] = "elevenlabs" if use_elevenlabs else "edge"

            if use_elevenlabs:
                elevenlabs_key = getpass.getpass("Paste your ElevenLabs API key, or press Enter to fill it later: ").strip()
                updates["ELEVENLABS_API_KEY"] = elevenlabs_key
            else:
                updates["ELEVENLABS_API_KEY"] = ""

        if updates:
            set_env_values(ENV_PATH, updates)
    else:
        logger.write("")
        logger.write(".env already exists, so setup will not overwrite it.")

    env_values = parse_env(ENV_PATH)
    missing_openai = is_placeholder(env_values.get("OPENAI_API_KEY"))
    tts_provider = env_values.get("TTS_PROVIDER", "edge").strip().lower() or "edge"
    missing_elevenlabs = tts_provider in {"elevenlabs", "eleven_labs", "11labs"} and is_placeholder(
        env_values.get("ELEVENLABS_API_KEY")
    )

    logger.write("")
    logger.write("Configuration check:")

    if missing_openai:
        logger.write("  - OPENAI_API_KEY is missing. Add it to .env before starting the voice core.")
    else:
        logger.write("  - OPENAI_API_KEY is set.")

    if missing_elevenlabs:
        logger.write("  - ELEVENLABS_API_KEY is missing, so JARVIS will fall back to Edge TTS.")
    elif tts_provider in {"elevenlabs", "eleven_labs", "11labs"}:
        logger.write("  - ElevenLabs TTS is configured.")
    else:
        logger.write("  - Edge TTS is selected. No TTS API key is required.")


def ensure_runtime_dirs(logger: Logger) -> None:
    for path in [
        ROOT_DIR / "data",
        ROOT_DIR / "recordings",
        ROOT_DIR / "screenshots",
        LOG_DIR,
    ]:
        path.mkdir(exist_ok=True)

    logger.write("")
    logger.write("Runtime folders are ready.")


def run_import_check(python_path: Path, logger: Logger) -> None:
    modules = list(CORE_IMPORT_CHECKS)

    if platform.system() == "Windows":
        modules.append("pycaw")

    code = (
        "import importlib, sys\n"
        f"modules = {modules!r}\n"
        "missing = []\n"
        "for name in modules:\n"
        "    try:\n"
        "        importlib.import_module(name)\n"
        "    except Exception as exc:\n"
        "        missing.append(f'{name}: {exc}')\n"
        "if missing:\n"
        "    print('\\n'.join(missing))\n"
        "    raise SystemExit(1)\n"
        "print('Core imports succeeded.')\n"
    )

    logger.write("")
    logger.write("Running a quick import check...")
    return_code = run_command([str(python_path), "-c", code], logger, check=False)

    if return_code != 0:
        logger.write("")
        logger.write("Some imports failed. The setup log above has details.")
        logger.write("Usually this means dependency installation failed or the Python version is unsupported.")


def print_platform_notes(logger: Logger) -> None:
    system = platform.system()

    logger.write("")

    if system == "Windows":
        logger.write("Platform: Windows. This is the primary supported platform for JARVIS.")
        return

    if system == "Darwin":
        logger.write("Platform: macOS. Support is partial.")
        logger.write("The web HUD, AI brain, microphone loop, and Edge TTS may work.")
        logger.write("Windows app launching, Windows volume control, and global hotkeys are Windows-only.")
        logger.write("Screen control may require macOS Accessibility and Screen Recording permissions.")
        return

    logger.write(f"Platform: {system or 'unknown'}. This platform is not officially supported.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up JARVIS for a fresh checkout.")
    parser.add_argument("--skip-install", action="store_true", help="Create/validate files without installing packages.")
    parser.add_argument("--recreate-venv", action="store_true", help="Move the current .venv aside and create a new one.")
    args = parser.parse_args()

    logger = Logger()

    try:
        logger.write("JARVIS setup")
        logger.write("=" * 12)
        logger.write(f"Project folder: {ROOT_DIR}")

        print_platform_notes(logger)
        validate_current_python(logger)
        ensure_runtime_dirs(logger)
        python_path = ensure_venv(logger, recreate=args.recreate_venv)
        install_requirements(python_path, logger, skip_install=args.skip_install)
        configure_env(logger)

        if not args.skip_install:
            run_import_check(python_path, logger)

        logger.write("")
        logger.write("Setup complete.")
        logger.write("Start JARVIS with Start_Jarvis.bat on Windows or start_mac.command on macOS.")
        logger.write("Stop JARVIS with Stop_Jarvis.bat on Windows or stop_mac.command on macOS.")
        logger.write(f"Setup log: {logger.path}")
        return 0

    except Exception as error:
        logger.write("")
        logger.write(f"Setup failed: {error}")
        logger.write(f"Setup log: {logger.path}")
        return 1

    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
