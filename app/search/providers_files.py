from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from logger import log_error

from .models import SearchResult
from .providers_common import safe_subtitle, score_text


class FilesProvider:
    def __init__(self) -> None:
        self._fallback_index: list[tuple[str, Path, str]] | None = None
        self._everything_path: str | None | bool = False

    def search(self, query: str, limit: int = 50) -> list[SearchResult]:
        text = query.strip()
        if len(text) < 2:
            return []
        results = self._everything_search(text, limit)
        if not results:
            results = self._windows_search(text, limit)
        if not results:
            results = self._fallback_search(text, limit)
        return results[:limit]

    def _everything_search(self, query: str, limit: int) -> list[SearchResult]:
        es_path = self._find_everything_cli()
        if not es_path:
            return []
        try:
            completed = subprocess.run(
                [es_path, "-n", str(limit), query],
                capture_output=True,
                text=True,
                timeout=1.0,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if completed.returncode != 0:
                return []
            return self._paths_to_results(completed.stdout.splitlines(), query)
        except Exception as exc:
            log_error("Everything search failed", exc)
            return []

    def _windows_search(self, query: str, limit: int) -> list[SearchResult]:
        escaped = query.replace("'", "''")
        script = (
            "$conn=New-Object -ComObject ADODB.Connection;"
            "$rs=New-Object -ComObject ADODB.Recordset;"
            "$conn.Open('Provider=Search.CollatorDSO;Extended Properties=\"Application=Windows\"');"
            f"$sql=\"SELECT TOP {max(1, min(50, limit))} System.ItemPathDisplay,System.FileName FROM SYSTEMINDEX "
            f"WHERE CONTAINS(System.FileName, '\\\"*{escaped}*\\\"')\";"
            "$rs.Open($sql,$conn);$items=@();"
            "while(-not $rs.EOF){$items += [pscustomobject]@{Path=$rs.Fields.Item('System.ItemPathDisplay').Value};$rs.MoveNext()};"
            "$items|ConvertTo-Json -Compress"
        )
        try:
            completed = subprocess.run(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
                capture_output=True,
                text=True,
                timeout=1.0,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0,
            )
            if completed.returncode != 0 or not completed.stdout.strip():
                return []
            import json

            raw = json.loads(completed.stdout)
            if isinstance(raw, dict):
                raw = [raw]
            paths = [str(item.get("Path", "")) for item in raw if isinstance(item, dict)]
            return self._paths_to_results(paths, query)
        except Exception:
            return []

    def _fallback_search(self, query: str, limit: int) -> list[SearchResult]:
        results = []
        for name, path, kind in self._load_fallback_index():
            if len(results) >= limit:
                break
            score = score_text(query, path.name, (name,))
            if score:
                results.append(SearchResult(kind, path.name, safe_subtitle(str(path.parent)), str(path), str(path), score))
        return sorted(results, key=lambda item: item.score, reverse=True)[:limit]

    def _paths_to_results(self, paths: list[str], query: str) -> list[SearchResult]:
        results = []
        seen = set()
        for path_text in paths:
            if not path_text:
                continue
            path = Path(path_text.strip())
            if not path.exists():
                continue
            normalized = str(path)
            if normalized in seen:
                continue
            seen.add(normalized)
            kind = "folder" if path.is_dir() else "file"
            score = score_text(query, path.name, ())
            results.append(SearchResult(kind, path.name, safe_subtitle(str(path.parent)), normalized, normalized, score or 300))
        return results

    def _load_fallback_index(self) -> list[tuple[str, Path, str]]:
        if self._fallback_index is not None:
            return self._fallback_index
        entries: list[tuple[str, Path, str]] = []
        for root in self._fallback_roots():
            if not root.exists():
                continue
            try:
                if root == Path.home():
                    children = list(root.iterdir())[:160]
                    for child in children:
                        if child.name.startswith("."):
                            continue
                        entries.append((child.name.casefold(), child, "folder" if child.is_dir() else "file"))
                    continue
                for current_root, dirs, files in os.walk(root):
                    depth = len(Path(current_root).relative_to(root).parts)
                    if depth >= 3:
                        dirs[:] = []
                    dirs[:] = [name for name in dirs if not name.startswith(".")][:40]
                    for dir_name in dirs:
                        path = Path(current_root) / dir_name
                        entries.append((dir_name.casefold(), path, "folder"))
                    for file_name in files:
                        if file_name.startswith("."):
                            continue
                        path = Path(current_root) / file_name
                        entries.append((file_name.casefold(), path, "file"))
                    if len(entries) >= 5000:
                        self._fallback_index = entries
                        return entries
            except Exception as exc:
                log_error("Fallback file index failed", exc)
        self._fallback_index = entries
        return entries

    @staticmethod
    def _fallback_roots() -> list[Path]:
        home = Path.home()
        return [
            home / "Desktop",
            home / "Documents",
            home / "Downloads",
            home / "Music",
            home / "Pictures",
            home / "Videos",
            home,
        ]

    def _find_everything_cli(self) -> str | None:
        if self._everything_path is not False:
            return self._everything_path
        candidates = [
            shutil.which("es.exe"),
            r"C:\Program Files\Everything\es.exe",
            r"C:\Program Files (x86)\Everything\es.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                self._everything_path = str(candidate)
                return str(candidate)
        self._everything_path = None
        return None
