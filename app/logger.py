import os
from datetime import datetime
from pathlib import Path


APP_NAME = "OneBar"
LOG_MAX_BYTES = 1024 * 1024
LOG_DIR = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME / "logs"
LOG_FILE = LOG_DIR / "onebar.log"


def _ensure_log_file() -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > LOG_MAX_BYTES:
        LOG_FILE.write_text("", encoding="utf-8")


def _write(level: str, message: str) -> None:
    try:
        _ensure_log_file()
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(f"[{timestamp}] [{level}] {message}\n")
    except Exception:
        pass


def log_info(message: str) -> None:
    _write("INFO", message)


def log_error(message: str, exc: Exception | None = None) -> None:
    detail = f"{message}: {type(exc).__name__}" if exc else message
    _write("ERROR", detail)
