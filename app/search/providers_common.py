from __future__ import annotations


def normalize(text: str) -> str:
    return text.casefold().strip()


def score_text(query: str, title: str, aliases: tuple[str, ...] = ()) -> int:
    q = normalize(query)
    if not q:
        return 0
    title_n = normalize(title)
    alias_values = [normalize(alias) for alias in aliases if alias]
    if title_n == q:
        return 1000
    if title_n.startswith(q):
        return 860
    if q in title_n:
        return 720
    for alias in alias_values:
        if alias == q:
            return 680
        if alias.startswith(q):
            return 600
        if q in alias:
            return 520
    return 0


def safe_subtitle(text: str, max_len: int = 72) -> str:
    value = str(text or "")
    return value if len(value) <= max_len else value[: max_len - 1] + "…"
