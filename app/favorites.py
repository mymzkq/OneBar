import json
import os
import time
import uuid
import webbrowser
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

from config import FAVORITES_FILE
from logger import log_error


MAX_FAVORITES = 120


def _normalize_url(url: str) -> str:
    text = url.strip()
    if not text:
        return ""
    parsed = urlparse(text)
    if parsed.scheme in ("http", "https") and parsed.netloc:
        return text
    if "://" in text:
        return ""
    return f"https://{text}"


def _favorite_type_for_path(path: Path) -> str:
    if path.is_dir():
        return "folder"
    if path.suffix.lower() in (".exe", ".lnk"):
        return "app"
    return "file"


def _category_for_type(item_type: str) -> str:
    return {
        "url": "url",
        "file": "file",
        "folder": "folder",
        "app": "app",
    }.get(item_type, "file")


class FavoritesManager:
    def __init__(self, on_changed: Callable[[], None] | None = None) -> None:
        self.items: list[dict] = []
        self.on_changed = on_changed

    def start(self) -> None:
        self.load()

    def load(self) -> None:
        try:
            if not FAVORITES_FILE.exists():
                return
            raw = json.loads(FAVORITES_FILE.read_text(encoding="utf-8"))
            if not isinstance(raw, list):
                return
            self.items = []
            for item in raw:
                normalized = self._normalize_item(item)
                if normalized is not None:
                    self.items.append(normalized)
            self.items = self.items[:MAX_FAVORITES]
        except Exception as exc:
            log_error("Favorites load failed", exc)
            self.items = []

    def save(self) -> None:
        try:
            FAVORITES_FILE.parent.mkdir(parents=True, exist_ok=True)
            FAVORITES_FILE.write_text(
                json.dumps(self.items[:MAX_FAVORITES], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except Exception as exc:
            log_error("Favorites save failed", exc)

    def add_url(self, title: str, url: str) -> bool:
        normalized_url = _normalize_url(url)
        if not normalized_url:
            return False
        parsed = urlparse(normalized_url)
        label = title.strip() or parsed.netloc or normalized_url
        return self._add_item("url", label, normalized_url)

    def add_path(self, path_text: str, item_type: str | None = None, title: str | None = None) -> bool:
        path = Path(path_text)
        if not path.exists():
            return False
        detected_type = item_type or _favorite_type_for_path(path)
        label = title.strip() if isinstance(title, str) and title.strip() else path.name or str(path)
        return self._add_item(detected_type, label, str(path))

    def update_item(self, index: int, title: str, target: str) -> bool:
        if index < 0 or index >= len(self.items):
            return False
        item_type = str(self.items[index].get("type", "file"))
        label = title.strip() or str(self.items[index].get("title", ""))
        if item_type == "url":
            normalized_target = _normalize_url(target)
            if not normalized_target:
                return False
        else:
            path = Path(target)
            if not path.exists():
                return False
            normalized_target = str(path)
            item_type = _favorite_type_for_path(path) if item_type not in ("app", "file", "folder") else item_type
        self.items[index].update({
            "type": item_type,
            "title": label or normalized_target,
            "target": normalized_target,
            "category": _category_for_type(item_type),
        })
        self._dedupe(index)
        self.save()
        self._notify_changed()
        return True

    def remove(self, index: int) -> None:
        if index < 0 or index >= len(self.items):
            return
        del self.items[index]
        self.save()
        self._notify_changed()

    def open_item(self, index: int) -> bool:
        if index < 0 or index >= len(self.items):
            return False
        item = self.items[index]
        try:
            if item.get("type") == "url":
                return bool(webbrowser.open(str(item.get("target", ""))))
            os.startfile(str(item.get("target", "")))  # type: ignore[attr-defined]
            return True
        except Exception as exc:
            log_error("Favorite open failed", exc)
            return False

    def _add_item(self, item_type: str, title: str, target: str) -> bool:
        if not target:
            return False
        self.items = [
            item for item in self.items
            if not (item.get("type") == item_type and item.get("target") == target)
        ]
        self.items.insert(0, {
            "id": uuid.uuid4().hex,
            "type": item_type,
            "title": title,
            "target": target,
            "category": _category_for_type(item_type),
            "created_at": int(time.time()),
        })
        del self.items[MAX_FAVORITES:]
        self.save()
        self._notify_changed()
        return True

    def _dedupe(self, current_index: int) -> None:
        if current_index < 0 or current_index >= len(self.items):
            return
        current = self.items[current_index]
        self.items = [
            item for i, item in enumerate(self.items)
            if i == current_index
            or not (item.get("type") == current.get("type") and item.get("target") == current.get("target"))
        ]

    @staticmethod
    def _normalize_item(raw: object) -> dict | None:
        if not isinstance(raw, dict):
            return None
        item_type = str(raw.get("type", ""))
        title = str(raw.get("title", "")).strip()
        target = str(raw.get("target", "")).strip()
        if item_type not in ("url", "file", "folder", "app") or not target:
            return None
        if item_type == "url":
            target = _normalize_url(target)
            if not target:
                return None
        else:
            path = Path(target)
            item_type = _favorite_type_for_path(path)
        return {
            "id": str(raw.get("id") or uuid.uuid4().hex),
            "type": item_type,
            "title": title or Path(target).name or target,
            "target": target,
            "category": _category_for_type(item_type),
            "created_at": int(raw.get("created_at") or time.time()),
        }

    def _notify_changed(self) -> None:
        if self.on_changed:
            self.on_changed()
