import json
import os
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QUrl

from config import FILE_HUB_FILE
from logger import log_error


MAX_FILE_HUB_ITEMS = 20


class FileHubManager:
    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        self.items: list[dict] = []
        self.on_changed = on_changed
        self.last_status = ""

    def start(self) -> None:
        self.load()

    def load(self) -> None:
        try:
            if not FILE_HUB_FILE.exists():
                return
            raw = json.loads(FILE_HUB_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            self.items = []
            for item in raw:
                if isinstance(item, dict) and isinstance(item.get("path"), str):
                    path = Path(item["path"])
                    normalized = str(path)
                    if normalized and all(existing.get("path") != normalized for existing in self.items):
                        self.items.append({
                            "path": normalized,
                            "name": path.name or normalized,
                            "exists": path.exists(),
                        })
            self.items = self.items[:MAX_FILE_HUB_ITEMS]
        except Exception as exc:
            log_error("File hub load failed", exc)
            self.items = []

    def save(self) -> None:
        try:
            FILE_HUB_FILE.parent.mkdir(parents=True, exist_ok=True)
            FILE_HUB_FILE.write_text(
                json.dumps(self.items[:MAX_FILE_HUB_ITEMS], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log_error("File hub save failed", exc)

    def add_paths(self, paths: list[str]) -> None:
        changed = False
        self.last_status = ""
        normalized_paths: list[str] = []
        for path in paths:
            file_path = Path(path)
            if not file_path.exists():
                continue
            normalized = str(file_path)
            if normalized in normalized_paths:
                continue
            normalized_paths.append(normalized)

        for path in normalized_paths:
            is_existing = any(item.get("path") == path for item in self.items)
            if not is_existing and len(self.items) >= MAX_FILE_HUB_ITEMS:
                self.last_status = "limit"
                continue
            if self._append_path(path, notify=False):
                changed = True
        if changed:
            del self.items[MAX_FILE_HUB_ITEMS:]
            self.save()
            self._notify_changed()
        elif self.last_status:
            self._notify_changed()

    def clear(self) -> None:
        self.items = []
        self.last_status = ""
        self.save()
        self._notify_changed()

    def remove(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        del self.items[index]
        self.save()
        self._notify_changed()

    def open_item(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        try:
            os.startfile(self.items[index]["path"])  # type: ignore[attr-defined]
        except Exception as exc:
            log_error("File hub item open failed", exc)

    def open_location(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        try:
            path = Path(self.items[index]["path"])
            if path.exists():
                os.startfile(str(path.parent))  # type: ignore[attr-defined]
        except Exception as exc:
            log_error("File hub location open failed", exc)

    def urls_for_index(self, index: int) -> list[QUrl]:
        if index < 0 or index >= len(self.items):
            return []
        return [QUrl.fromLocalFile(self.items[index]["path"])]

    def copy_path(self, index: int) -> str:
        if index < 0 or index >= len(self.items):
            return ""
        return self.items[index]["path"]

    def _append_path(self, path_text: str, notify: bool = True) -> bool:
        path = Path(path_text)
        normalized = str(path)
        if not normalized or not path.exists():
            return False
        self.items = [item for item in self.items if item.get("path") != normalized]
        self.items.insert(0, {
            "path": normalized,
            "name": path.name or normalized,
            "exists": path.exists(),
        })
        if notify:
            self.save()
            self._notify_changed()
        return True

    def refresh_exists(self) -> None:
        for item in self.items:
            item["exists"] = Path(item.get("path", "")).exists()

    def _notify_changed(self) -> None:
        if self.on_changed:
            self.on_changed()
