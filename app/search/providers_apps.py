from __future__ import annotations

import os
from pathlib import Path

from logger import log_error

from .models import SearchResult
from .providers_common import safe_subtitle, score_text

try:
    import winreg
except Exception:  # pragma: no cover - non-Windows fallback
    winreg = None


class AppsProvider:
    def __init__(self) -> None:
        self._index: list[tuple[str, Path, tuple[str, ...], int]] | None = None

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        results = []
        for title, path, aliases, priority in self._load_index():
            score = score_text(query, title, aliases)
            if score:
                results.append(SearchResult("app", title, safe_subtitle(str(path.parent)), str(path), str(path), score + priority))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _load_index(self) -> list[tuple[str, Path, tuple[str, ...], int]]:
        if self._index is not None:
            return self._index
        entries: list[tuple[str, Path, tuple[str, ...], int]] = []
        seen: set[str] = set()
        for root in self._shortcut_dirs():
            if not root.exists():
                continue
            try:
                for pattern in ("*.lnk", "*.exe"):
                    for path in root.rglob(pattern):
                        self._add_entry(entries, seen, path.stem, path, (path.stem,), 70 if path.suffix.lower() == ".lnk" else 40)
            except Exception as exc:
                log_error("App shortcut scan failed", exc)
        for title, path in self._registry_apps():
            self._add_entry(entries, seen, title, path, (title,), 20)
        self._index = entries
        return entries

    @staticmethod
    def _shortcut_dirs() -> list[Path]:
        candidates: list[Path] = []
        appdata = os.getenv("APPDATA")
        programdata = os.getenv("PROGRAMDATA")
        public = os.getenv("PUBLIC")
        if appdata:
            candidates.append(Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        if programdata:
            candidates.append(Path(programdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        candidates.append(Path.home() / "Desktop")
        if public:
            candidates.append(Path(public) / "Desktop")
        return candidates

    @staticmethod
    def _add_entry(entries: list, seen: set[str], title: str, path: Path, aliases: tuple[str, ...], priority: int) -> None:
        if not title or not path.exists():
            return
        key = title.casefold()
        if key in seen:
            return
        seen.add(key)
        entries.append((title, path, aliases, priority))

    @staticmethod
    def _registry_apps() -> list[tuple[str, Path]]:
        if winreg is None:
            return []
        roots = (
            (winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        )
        apps: list[tuple[str, Path]] = []
        for root, subkey in roots:
            try:
                with winreg.OpenKey(root, subkey) as key:
                    for index in range(winreg.QueryInfoKey(key)[0]):
                        try:
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as app_key:
                                title = str(winreg.QueryValueEx(app_key, "DisplayName")[0]).strip()
                                target = AppsProvider._registry_target(app_key)
                                if title and target and target.exists():
                                    apps.append((title, target))
                        except Exception:
                            continue
            except Exception as exc:
                log_error("App registry scan failed", exc)
        return apps

    @staticmethod
    def _registry_target(app_key) -> Path | None:
        candidates = []
        for value_name in ("DisplayIcon", "InstallLocation"):
            try:
                value = str(winreg.QueryValueEx(app_key, value_name)[0]).strip()
                if value:
                    candidates.append(value)
            except Exception:
                pass
        for raw in candidates:
            cleaned = raw.strip('"')
            if "," in cleaned:
                cleaned = cleaned.rsplit(",", 1)[0].strip('"')
            path = Path(cleaned)
            if path.is_file() and path.suffix.lower() == ".exe":
                return path
            if path.is_dir():
                for exe in path.glob("*.exe"):
                    return exe
        return None
