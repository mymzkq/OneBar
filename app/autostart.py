import os
import sys
from pathlib import Path


APP_NAME = "OneBar"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def _is_windows() -> bool:
    return os.name == "nt"


def _main_script() -> Path:
    return Path(__file__).resolve().parent / "main.py"


def _command() -> str:
    return f'"{Path(sys.executable).resolve()}" "{_main_script()}"'


def is_enabled() -> bool:
    if not _is_windows():
        return False

    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, APP_NAME)
    except FileNotFoundError:
        return False
    except OSError:
        return False

    return str(_main_script()) in str(value)


def set_enabled(enabled: bool) -> None:
    if not _is_windows():
        raise RuntimeError("Autostart is only implemented on Windows in this preview.")

    import winreg

    with winreg.OpenKey(
        winreg.HKEY_CURRENT_USER,
        RUN_KEY,
        0,
        winreg.KEY_SET_VALUE,
    ) as key:
        if enabled:
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, _command())
            return

        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
