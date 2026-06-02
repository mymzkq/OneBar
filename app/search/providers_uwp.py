import json
import subprocess

from logger import log_error

from .models import SearchResult
from .providers_common import score_text


class UwpProvider:
    def __init__(self) -> None:
        self._index: list[tuple[str, str, tuple[str, ...]]] | None = None

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        results = []
        for title, app_id, aliases in self._load_index():
            score = score_text(query, title, aliases)
            if score:
                results.append(SearchResult("uwp", title, "AppsFolder", app_id, "uwp", score + 45))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _load_index(self) -> list[tuple[str, str, tuple[str, ...]]]:
        if self._index is not None:
            return self._index
        entries: list[tuple[str, str, tuple[str, ...]]] = []
        command = "Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress"
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", command],
                capture_output=True,
                text=True,
                timeout=3.2,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if completed.returncode == 0 and completed.stdout.strip():
                raw = json.loads(completed.stdout)
                if isinstance(raw, dict):
                    raw = [raw]
                seen = set()
                for item in raw:
                    if not isinstance(item, dict):
                        continue
                    name = str(item.get("Name", "")).strip()
                    app_id = str(item.get("AppID", "")).strip()
                    key = app_id.casefold()
                    if not name or not app_id or key in seen:
                        continue
                    seen.add(key)
                    entries.append((name, app_id, (name,)))
        except Exception as exc:
            log_error("UWP provider unavailable", exc)
        self._index = entries
        return entries
