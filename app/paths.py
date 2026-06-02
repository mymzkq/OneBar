from __future__ import annotations

import sys
from pathlib import Path


def resource_path(relative_path: str) -> Path:
    relative = Path(relative_path)
    if relative.is_absolute():
        return relative

    for base in _resource_bases():
        candidate = base / relative
        if candidate.exists():
            return candidate

    return _resource_bases()[0] / relative


def asset_path(name: str) -> Path:
    return resource_path(str(Path("assets") / name))


def _resource_bases() -> list[Path]:
    bases: list[Path] = []

    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        bases.append(Path(bundled_root))

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        bases.extend([exe_dir, exe_dir / "_internal"])

    bases.extend([Path(__file__).resolve().parents[1], Path.cwd()])

    unique: list[Path] = []
    for base in bases:
        resolved = base.resolve()
        if resolved not in unique:
            unique.append(resolved)
    return unique
