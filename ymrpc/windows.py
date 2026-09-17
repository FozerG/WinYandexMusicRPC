import os
import subprocess
import sys
import winreg
from pathlib import Path

import win32api
import win32con
import win32event
import win32gui

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "YaMusicRPC"


class SingleInstance:
    def __init__(self):
        self._handle = win32event.CreateMutex(None, False, r"Local\WinYandexMusicRPC")
        self.already_running = win32api.GetLastError() == 183

    def close(self) -> None:
        if self._handle is not None:
            win32api.CloseHandle(self._handle)
            self._handle = None


def startup_shortcut() -> Path:
    return (
        Path(os.environ["APPDATA"]) / "Microsoft/Windows/Start Menu/Programs/Startup/YaMusicRPC.lnk"
    )


def autostart_enabled() -> bool:
    if startup_shortcut().exists():
        return True
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.QueryValueEx(key, RUN_NAME)
        return True
    except FileNotFoundError:
        return False


def set_autostart(enabled: bool) -> None:
    if enabled:
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            pythonw = Path(sys.executable).with_name("pythonw.exe")
            command = [
                str(pythonw if pythonw.exists() else sys.executable),
                str(Path(__file__).resolve().parent.parent / "main.py"),
            ]
        command.append("--run-through-startup")
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            winreg.SetValueEx(key, RUN_NAME, 0, winreg.REG_SZ, subprocess.list2cmdline(command))
        startup_shortcut().unlink(missing_ok=True)
    else:
        startup_shortcut().unlink(missing_ok=True)
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, RUN_NAME)
        except FileNotFoundError:
            pass


def hide_console() -> None:
    import win32console

    handle = win32console.GetConsoleWindow()
    if handle:
        win32gui.ShowWindow(handle, win32con.SW_HIDE)
