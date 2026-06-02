import json
from datetime import datetime
from typing import Callable

from PySide6.QtCore import QMimeData, QTimer
from PySide6.QtWidgets import QApplication

from config import CLIPBOARD_HISTORY_FILE, DEFAULT_CLIPBOARD
from logger import log_error
from search_service import detect_url


MAX_CLIPBOARD_TEXT_LENGTH = 5000
TRUNCATED_SUFFIX = "\n...[truncated]"


class ClipboardHistoryManager:
    def __init__(self, settings: dict | None = None, on_changed: Callable[[], None] | None = None) -> None:
        self.settings = dict(DEFAULT_CLIPBOARD)
        self.settings.update(settings or {})
        self.enabled = bool(self.settings.get("history_enabled", True))
        self.persist_enabled = bool(self.settings.get("persist_enabled", True))
        self.max_items = int(self.settings.get("max_items", DEFAULT_CLIPBOARD["max_items"]))
        self.paused = False
        self.items: list[dict] = []
        self.on_changed = on_changed
        self.on_url_copied: Callable[[str], None] | None = None
        self._connected = False
        self._ignore_clipboard_change = False

    def start(self) -> None:
        if self.persist_enabled:
            self.load()
        clipboard = QApplication.clipboard()
        if clipboard is not None and not self._connected:
            clipboard.dataChanged.connect(self._handle_clipboard_changed)
            self._connected = True

    def apply_settings(self, settings: dict | None) -> None:
        merged = dict(DEFAULT_CLIPBOARD)
        merged.update(settings or {})
        self.settings = merged
        self.enabled = bool(merged.get("history_enabled", True))
        previous_persist = self.persist_enabled
        self.persist_enabled = bool(merged.get("persist_enabled", True))
        self.max_items = max(10, min(100, int(merged.get("max_items", DEFAULT_CLIPBOARD["max_items"]))))
        del self.items[self.max_items:]
        if self.persist_enabled and not previous_persist:
            self.save()

    def load(self) -> None:
        try:
            if not CLIPBOARD_HISTORY_FILE.exists():
                return
            raw = json.loads(CLIPBOARD_HISTORY_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            self.items = [
                item for item in raw
                if isinstance(item, dict) and isinstance(item.get("text"), str) and item.get("text").strip()
            ][:self.max_items]
        except Exception as exc:
            log_error("Clipboard history load failed", exc)
            self.items = []

    def save(self) -> None:
        if not self.persist_enabled:
            return
        try:
            CLIPBOARD_HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
            CLIPBOARD_HISTORY_FILE.write_text(
                json.dumps(self.items[:self.max_items], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log_error("Clipboard history save failed", exc)

    def clear(self) -> None:
        self.items = []
        try:
            if CLIPBOARD_HISTORY_FILE.exists():
                CLIPBOARD_HISTORY_FILE.unlink()
        except Exception as exc:
            log_error("Clipboard history clear failed", exc)
        self._notify_changed()

    def toggle_paused(self) -> bool:
        self.paused = not self.paused
        self._notify_changed()
        return self.paused

    def copy_to_clipboard(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        self._ignore_clipboard_change = True
        clipboard.setText(self.items[index]["text"])
        QTimer.singleShot(80, self._reset_ignore_flag)

    def delete_item(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        del self.items[index]
        self.save()
        self._notify_changed()

    def _reset_ignore_flag(self) -> None:
        self._ignore_clipboard_change = False

    def _handle_clipboard_changed(self) -> None:
        if self._ignore_clipboard_change or not self.enabled or self.paused:
            return
        clipboard = QApplication.clipboard()
        if clipboard is None:
            return
        mime = clipboard.mimeData()
        if self._mime_contains_local_files(mime):
            return
        text = mime.text() if mime is not None and mime.hasText() else clipboard.text()
        self.add_text(text)

    def add_text(self, text: str) -> None:
        if not isinstance(text, str) or not text.strip():
            return
        truncated = len(text) > MAX_CLIPBOARD_TEXT_LENGTH
        stored_text = text[:MAX_CLIPBOARD_TEXT_LENGTH] + (TRUNCATED_SUFFIX if truncated else "")

        self.items = [item for item in self.items if item.get("text") != stored_text]
        self.items.insert(0, {
            "text": stored_text,
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "truncated": truncated,
        })
        del self.items[self.max_items:]
        self.save()
        self._notify_changed()
        url = detect_url(text)
        if self.on_url_copied and url:
            self.on_url_copied(url)

    @staticmethod
    def _mime_contains_local_files(mime: QMimeData | None) -> bool:
        if mime is None or not mime.hasUrls():
            return False
        urls = mime.urls()
        return bool(urls) and all(url.isLocalFile() for url in urls)

    def _notify_changed(self) -> None:
        if self.on_changed:
            self.on_changed()
