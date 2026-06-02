import json
import os
from pathlib import Path
from typing import Any

from i18n import DEFAULT_LANGUAGE, normalize_language
from logger import log_error


APP_NAME = "OneBar"
CONFIG_DIR = Path(os.getenv("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME
CONFIG_FILE = CONFIG_DIR / "settings.json"
DATA_DIR = CONFIG_DIR
CLIPBOARD_HISTORY_FILE = DATA_DIR / "clipboard_history.json"
FILE_HUB_FILE = DATA_DIR / "file_hub.json"
FAVORITES_FILE = DATA_DIR / "favorites.json"

DEFAULT_APPEARANCE: dict[str, Any] = {
    "body_width": 340,
    "body_height": 34,
    "radius": 5,
    "shadow_enabled": True,
    "animation_enabled": True,
    "brand_text": "OneBar",
}

DEFAULT_BEHAVIOR: dict[str, Any] = {
    "auto_hide_enabled": False,
    "auto_hide_delay_seconds": 5,
    "collapse_on_outside_click": True,
    "music_preview_enabled": True,
    "usb_drive_prompt_enabled": True,
}

DEFAULT_STATUS: dict[str, Any] = {
    "show_time": True,
    "show_cpu": False,
    "show_memory": False,
    "show_network": False,
    "update_interval_ms": 1000,
}

SEARCH_ENGINE_KEYS = ("bing", "google", "duckduckgo", "baidu")

DEFAULT_SEARCH: dict[str, Any] = {
    "default_engine": "bing",
}

DEFAULT_HOTKEY: dict[str, Any] = {
    "search_hotkey_enabled": False,
    "search_hotkey": "Ctrl+Alt+Space",
}

DEFAULT_CLIPBOARD: dict[str, Any] = {
    "history_enabled": True,
    "persist_enabled": True,
    "url_open_prompt_enabled": True,
    "max_items": 30,
}

APPEARANCE_LIMITS = {
    "body_width": (280, 680),
    "body_height": (30, 48),
    "radius": (3, 24),
}

APPEARANCE_STEPS = {
    "body_width": 10,
    "body_height": 1,
    "radius": 1,
}

DEFAULT_SETTINGS: dict[str, Any] = {
    "language": DEFAULT_LANGUAGE,
    "shapeMode": "attached",
    "appearance": dict(DEFAULT_APPEARANCE),
    "behavior": dict(DEFAULT_BEHAVIOR),
    "status": dict(DEFAULT_STATUS),
    "search": dict(DEFAULT_SEARCH),
    "hotkey": dict(DEFAULT_HOTKEY),
    "clipboard": dict(DEFAULT_CLIPBOARD),
}


def _clamp_int(value: Any, minimum: int, maximum: int, fallback: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = fallback
    return max(minimum, min(maximum, parsed))


def _normalize_appearance(raw: Any) -> tuple[dict[str, Any], bool]:
    appearance = dict(DEFAULT_APPEARANCE)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        appearance.update(raw)

    for key, (minimum, maximum) in APPEARANCE_LIMITS.items():
        normalized = _clamp_int(
            appearance.get(key),
            minimum,
            maximum,
            DEFAULT_APPEARANCE[key],
        )
        if normalized != appearance.get(key):
            changed = True
        appearance[key] = normalized

    for key in ("shadow_enabled", "animation_enabled"):
        normalized = bool(appearance.get(key, DEFAULT_APPEARANCE[key]))
        if normalized != appearance.get(key):
            changed = True
        appearance[key] = normalized

    brand_text = appearance.get("brand_text", DEFAULT_APPEARANCE["brand_text"])
    if not isinstance(brand_text, str):
        brand_text = DEFAULT_APPEARANCE["brand_text"]
        changed = True
    brand_text = brand_text.strip()
    if not brand_text:
        brand_text = DEFAULT_APPEARANCE["brand_text"]
        changed = True
    if len(brand_text) > 12:
        brand_text = brand_text[:12]
        changed = True
    appearance["brand_text"] = brand_text

    return appearance, changed


def _normalize_behavior(raw: Any) -> tuple[dict[str, Any], bool]:
    behavior = dict(DEFAULT_BEHAVIOR)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        behavior.update(raw)

    auto_hide_enabled = behavior.get("auto_hide_enabled", DEFAULT_BEHAVIOR["auto_hide_enabled"])
    if not isinstance(auto_hide_enabled, bool):
        auto_hide_enabled = DEFAULT_BEHAVIOR["auto_hide_enabled"]
        changed = True
    behavior["auto_hide_enabled"] = auto_hide_enabled

    collapse_on_outside_click = behavior.get(
        "collapse_on_outside_click",
        DEFAULT_BEHAVIOR["collapse_on_outside_click"],
    )
    if not isinstance(collapse_on_outside_click, bool):
        collapse_on_outside_click = DEFAULT_BEHAVIOR["collapse_on_outside_click"]
        changed = True
    behavior["collapse_on_outside_click"] = collapse_on_outside_click

    music_preview_enabled = behavior.get(
        "music_preview_enabled",
        DEFAULT_BEHAVIOR["music_preview_enabled"],
    )
    if not isinstance(music_preview_enabled, bool):
        music_preview_enabled = DEFAULT_BEHAVIOR["music_preview_enabled"]
        changed = True
    behavior["music_preview_enabled"] = music_preview_enabled

    usb_drive_prompt_enabled = behavior.get(
        "usb_drive_prompt_enabled",
        DEFAULT_BEHAVIOR["usb_drive_prompt_enabled"],
    )
    if not isinstance(usb_drive_prompt_enabled, bool):
        usb_drive_prompt_enabled = DEFAULT_BEHAVIOR["usb_drive_prompt_enabled"]
        changed = True
    behavior["usb_drive_prompt_enabled"] = usb_drive_prompt_enabled

    delay = _clamp_int(
        behavior.get("auto_hide_delay_seconds"),
        5,
        5,
        DEFAULT_BEHAVIOR["auto_hide_delay_seconds"],
    )
    if delay != behavior.get("auto_hide_delay_seconds"):
        changed = True
    behavior["auto_hide_delay_seconds"] = delay

    return behavior, changed


def _normalize_status(raw: Any) -> tuple[dict[str, Any], bool]:
    status = dict(DEFAULT_STATUS)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        status.update(raw)

    for key in ("show_time", "show_cpu", "show_memory", "show_network"):
        normalized = status.get(key, DEFAULT_STATUS[key])
        if not isinstance(normalized, bool):
            normalized = DEFAULT_STATUS[key]
            changed = True
        status[key] = normalized

    interval = _clamp_int(
        status.get("update_interval_ms"),
        1000,
        1000,
        DEFAULT_STATUS["update_interval_ms"],
    )
    if interval != status.get("update_interval_ms"):
        changed = True
    status["update_interval_ms"] = interval

    return status, changed


def _normalize_search(raw: Any) -> tuple[dict[str, Any], bool]:
    search = dict(DEFAULT_SEARCH)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        search.update(raw)

    engine = search.get("default_engine", DEFAULT_SEARCH["default_engine"])
    if engine not in SEARCH_ENGINE_KEYS:
        engine = DEFAULT_SEARCH["default_engine"]
        changed = True
    search["default_engine"] = engine
    return search, changed


def _normalize_hotkey(raw: Any) -> tuple[dict[str, Any], bool]:
    hotkey = dict(DEFAULT_HOTKEY)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        hotkey.update(raw)

    enabled = hotkey.get("search_hotkey_enabled", DEFAULT_HOTKEY["search_hotkey_enabled"])
    if not isinstance(enabled, bool):
        enabled = DEFAULT_HOTKEY["search_hotkey_enabled"]
        changed = True
    hotkey["search_hotkey_enabled"] = enabled

    shortcut = hotkey.get("search_hotkey", DEFAULT_HOTKEY["search_hotkey"])
    if not isinstance(shortcut, str) or not shortcut.strip():
        shortcut = DEFAULT_HOTKEY["search_hotkey"]
        changed = True
    hotkey["search_hotkey"] = shortcut.strip()
    return hotkey, changed


def _normalize_clipboard(raw: Any) -> tuple[dict[str, Any], bool]:
    clipboard = dict(DEFAULT_CLIPBOARD)
    changed = not isinstance(raw, dict)

    if isinstance(raw, dict):
        clipboard.update(raw)

    for key in ("history_enabled", "persist_enabled", "url_open_prompt_enabled"):
        normalized = clipboard.get(key, DEFAULT_CLIPBOARD[key])
        if not isinstance(normalized, bool):
            normalized = DEFAULT_CLIPBOARD[key]
            changed = True
        clipboard[key] = normalized

    max_items = _clamp_int(
        clipboard.get("max_items"),
        10,
        100,
        DEFAULT_CLIPBOARD["max_items"],
    )
    if max_items != clipboard.get("max_items"):
        changed = True
    clipboard["max_items"] = max_items

    return clipboard, changed


def _normalize_settings(raw: dict[str, Any] | None) -> tuple[dict[str, Any], bool]:
    settings = dict(DEFAULT_SETTINGS)
    settings["appearance"] = dict(DEFAULT_APPEARANCE)
    settings["behavior"] = dict(DEFAULT_BEHAVIOR)
    settings["status"] = dict(DEFAULT_STATUS)
    settings["search"] = dict(DEFAULT_SEARCH)
    settings["hotkey"] = dict(DEFAULT_HOTKEY)
    settings["clipboard"] = dict(DEFAULT_CLIPBOARD)
    changed = False

    if isinstance(raw, dict):
        settings.update(raw)
    else:
        changed = True

    language = normalize_language(settings.get("language"))
    if language != settings.get("language"):
        changed = True
    settings["language"] = language

    if settings.get("shapeMode") != "attached":
        settings["shapeMode"] = "attached"
        changed = True

    appearance, appearance_changed = _normalize_appearance(settings.get("appearance"))
    settings["appearance"] = appearance
    changed = changed or appearance_changed

    behavior, behavior_changed = _normalize_behavior(settings.get("behavior"))
    settings["behavior"] = behavior
    changed = changed or behavior_changed

    status, status_changed = _normalize_status(settings.get("status"))
    settings["status"] = status
    changed = changed or status_changed

    search, search_changed = _normalize_search(settings.get("search"))
    settings["search"] = search
    changed = changed or search_changed

    hotkey, hotkey_changed = _normalize_hotkey(settings.get("hotkey"))
    settings["hotkey"] = hotkey
    changed = changed or hotkey_changed

    clipboard, clipboard_changed = _normalize_clipboard(settings.get("clipboard"))
    settings["clipboard"] = clipboard
    changed = changed or clipboard_changed

    return settings, changed


def load_settings() -> dict[str, Any]:
    try:
        raw = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        if CONFIG_FILE.exists():
            log_error("Settings load failed", exc)
        settings, _ = _normalize_settings(None)
        return settings

    settings, changed = _normalize_settings(raw)
    if changed:
        save_settings(settings)
    return settings


def save_settings(settings: dict[str, Any]) -> None:
    normalized, _ = _normalize_settings(settings)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
