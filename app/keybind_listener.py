import ctypes
import re
import sys
import threading
import queue
from ctypes import wintypes


# Windows RegisterHotKey modifier flags.
MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

WM_HOTKEY = 0x0312
WM_QUIT = 0x0012


MODIFIER_ALIASES = {
    "ctrl": ("Ctrl", MOD_CONTROL),
    "control": ("Ctrl", MOD_CONTROL),
    "alt": ("Alt", MOD_ALT),
    "shift": ("Shift", MOD_SHIFT),
    "win": ("Win", MOD_WIN),
    "windows": ("Win", MOD_WIN),
    "cmd": ("Win", MOD_WIN),
    "command": ("Win", MOD_WIN),
}


KEY_ALIASES = {
    "space": (0x20, "Space"),
    "spacebar": (0x20, "Space"),
    "enter": (0x0D, "Enter"),
    "return": (0x0D, "Enter"),
    "tab": (0x09, "Tab"),
    "esc": (0x1B, "Esc"),
    "escape": (0x1B, "Esc"),
    "backspace": (0x08, "Backspace"),
    "delete": (0x2E, "Delete"),
    "del": (0x2E, "Delete"),
    "insert": (0x2D, "Insert"),
    "home": (0x24, "Home"),
    "end": (0x23, "End"),
    "pageup": (0x21, "PageUp"),
    "page_up": (0x21, "PageUp"),
    "pagedown": (0x22, "PageDown"),
    "page_down": (0x22, "PageDown"),
    "up": (0x26, "Up"),
    "down": (0x28, "Down"),
    "left": (0x25, "Left"),
    "right": (0x27, "Right"),
}


def parse_hotkey(hotkey_text):
    """
    Parses strings like "ctrl+space", "Control + Shift + J", or "alt+f8".
    Returns (modifier_flags, virtual_key_code, display_name).
    """

    raw_text = str(hotkey_text or "").strip()

    if not raw_text:
        raise ValueError("Hotkey cannot be empty.")

    parts = [
        part.strip().lower()
        for part in re.split(r"\s*\+\s*", raw_text)
        if part.strip()
    ]

    modifiers = 0
    key_names = []

    for part in parts:
        if part in MODIFIER_ALIASES:
            _, modifier_flag = MODIFIER_ALIASES[part]
            modifiers |= modifier_flag
        else:
            key_names.append(part)

    if len(key_names) != 1:
        raise ValueError(
            "Hotkey must have exactly one non-modifier key, such as ctrl+space."
        )

    vk_code, key_display = _virtual_key_for(key_names[0])

    display_parts = []

    for name, flag in [
        ("Ctrl", MOD_CONTROL),
        ("Alt", MOD_ALT),
        ("Shift", MOD_SHIFT),
        ("Win", MOD_WIN),
    ]:
        if modifiers & flag:
            display_parts.append(name)

    display_parts.append(key_display)

    return modifiers, vk_code, "+".join(display_parts)


def _virtual_key_for(key_name):
    if key_name in KEY_ALIASES:
        return KEY_ALIASES[key_name]

    if re.fullmatch(r"f([1-9]|1[0-9]|2[0-4])", key_name):
        function_number = int(key_name[1:])
        return 0x70 + function_number - 1, f"F{function_number}"

    if len(key_name) == 1 and key_name.isalpha():
        return ord(key_name.upper()), key_name.upper()

    if len(key_name) == 1 and key_name.isdigit():
        return ord(key_name), key_name

    raise ValueError(f"Unsupported hotkey key: {key_name}")


class GlobalHotkeyListener:
    """
    Small Windows global hotkey listener using RegisterHotKey.
    The callback is called from a daemon thread whenever the hotkey fires.
    """

    def __init__(self, hotkey_text, callback, hotkey_id=0x4A56):
        self.hotkey_text = str(hotkey_text or "").strip()
        self.callback = callback
        self.hotkey_id = hotkey_id
        self.modifiers, self.vk_code, self.display_name = parse_hotkey(
            self.hotkey_text
        )

        self._thread = None
        self._thread_id = None
        self._started = threading.Event()
        self._startup_queue = queue.Queue(maxsize=1)

    def start(self):
        if not sys.platform.startswith("win"):
            raise RuntimeError("Global hotkeys are only supported on Windows.")

        if self._thread and self._thread.is_alive():
            return self

        self._thread = threading.Thread(
            target=self._message_loop,
            name="JarvisGlobalHotkey",
            daemon=True,
        )
        self._thread.start()

        try:
            startup_error = self._startup_queue.get(timeout=2.0)
        except queue.Empty:
            raise RuntimeError("Timed out while registering global hotkey.")

        if startup_error:
            raise startup_error

        return self

    def stop(self):
        if not self._thread_id:
            return

        ctypes.windll.user32.PostThreadMessageW(
            self._thread_id,
            WM_QUIT,
            0,
            0,
        )

    def _message_loop(self):
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        self._thread_id = kernel32.GetCurrentThreadId()

        registered = False

        try:
            registered = bool(
                user32.RegisterHotKey(
                    None,
                    self.hotkey_id,
                    self.modifiers | MOD_NOREPEAT,
                    self.vk_code,
                )
            )

            if not registered:
                raise ctypes.WinError()

            self._started.set()
            self._startup_queue.put(None)

            msg = wintypes.MSG()

            while True:
                result = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)

                if result == 0:
                    break

                if result == -1:
                    raise ctypes.WinError()

                if msg.message == WM_HOTKEY and msg.wParam == self.hotkey_id:
                    try:
                        self.callback()
                    except Exception as error:
                        print(f"Hotkey callback warning: {error}")

                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))

        except Exception as error:
            if not self._started.is_set():
                self._startup_queue.put(error)
            else:
                print(f"Global hotkey listener stopped unexpectedly: {error}")

        finally:
            if registered:
                user32.UnregisterHotKey(None, self.hotkey_id)
