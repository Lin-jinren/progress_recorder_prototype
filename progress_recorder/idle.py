from __future__ import annotations

import sys
from typing import Optional


def get_idle_seconds() -> Optional[float]:
    """Seconds since the last keyboard/mouse input, or None if unsupported.

    Only asks the OS *when* the last input happened; it never sees what was typed.
    """
    if sys.platform == "win32":
        return _windows_idle_seconds()
    # TODO: macOS (Quartz CGEventSourceSecondsSinceLastEventType)
    # TODO: Linux X11 (XScreenSaverQueryInfo); Wayland has no general API.
    return None


def _windows_idle_seconds() -> Optional[float]:
    try:
        import ctypes
        from ctypes import wintypes

        class LASTINPUTINFO(ctypes.Structure):
            _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]

        info = LASTINPUTINFO()
        info.cbSize = ctypes.sizeof(info)
        if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(info)):
            return None

        get_tick_count = ctypes.windll.kernel32.GetTickCount
        get_tick_count.restype = wintypes.DWORD
        # Both values are 32-bit millisecond tick counts that wrap every ~49.7 days.
        elapsed_ms = (get_tick_count() - info.dwTime) & 0xFFFFFFFF
        return elapsed_ms / 1000.0
    except Exception:
        return None
