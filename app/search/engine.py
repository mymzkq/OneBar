from __future__ import annotations

import os
import subprocess
from pathlib import Path

from logger import log_error

from .models import SearchResult
from .providers_apps import AppsProvider
from .providers_files import FilesProvider
from .providers_settings import SettingsProvider
from .providers_system import SystemToolsProvider
from .providers_uwp import UwpProvider


TYPE_PRIORITY = {
    "app": 260,
    "uwp": 250,
    "setting": 220,
    "system": 210,
    "folder": 48,
    "file": 44,
}


class SearchEngine:
    def __init__(self) -> None:
        self.providers = [
            AppsProvider(),
            UwpProvider(),
            SettingsProvider(),
            SystemToolsProvider(),
            FilesProvider(),
        ]

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        text = query.strip()
        if not text:
            return []
        results: list[SearchResult] = []
        for provider in self.providers:
            try:
                results.extend(provider.search(text, limit))
            except Exception as exc:
                log_error("Search provider failed", exc)
        return self._rank_and_dedupe(results, limit)

    @staticmethod
    def _rank_and_dedupe(results: list[SearchResult], limit: int) -> list[SearchResult]:
        seen: set[str] = set()
        deduped: list[SearchResult] = []
        for item in sorted(
            results,
            key=lambda result: (result.score + TYPE_PRIORITY.get(result.type, 0), result.title.casefold()),
            reverse=True,
        ):
            key = f"{item.type}:{item.target.casefold()}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
            if len(deduped) >= limit:
                break
        return deduped

    def prewarm_static_indexes(self) -> None:
        for provider in self.providers:
            if isinstance(provider, FilesProvider):
                continue
            try:
                provider.search("", 1)
            except Exception as exc:
                log_error("Search prewarm failed", exc)

    @staticmethod
    def open_result(result: SearchResult | dict) -> bool:
        if isinstance(result, dict):
            result_type = str(result.get("type", ""))
            target = str(result.get("target") or result.get("path") or result.get("uri") or result.get("command") or result.get("app_id") or "")
        else:
            result_type = result.type
            target = result.target
        try:
            if result_type == "setting":
                os.startfile(target)  # type: ignore[attr-defined]
                return True
            if result_type == "system":
                subprocess.Popen(target, shell=True)
                return True
            if result_type == "uwp":
                subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{target}"])
                return True
            if result_type in ("app", "file", "folder"):
                os.startfile(str(Path(target)))  # type: ignore[attr-defined]
                return True
        except Exception as exc:
            log_error("Search result open failed", exc)
        return False
