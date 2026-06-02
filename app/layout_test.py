from __future__ import annotations

import sys

from layout_metrics import compute_responsive_metrics


CASES = [
    (1366, 768, 1.00),
    (1920, 1080, 1.00),
    (1920, 1080, 1.25),
    (2560, 1440, 1.25),
    (2560, 1440, 1.50),
    (3840, 2160, 1.50),
    (3840, 2160, 2.00),
]


def check_case(width: int, height: int, scale: float) -> bool:
    logical_width = int(round(width / scale))
    logical_height = int(round(height / scale))
    metrics = compute_responsive_metrics(340, 34, 5, logical_width, logical_height, scale)
    ok = True
    if metrics.collapsed_width > metrics.screen_width:
        ok = False
    if metrics.expanded_width > metrics.screen_width:
        ok = False
    if metrics.expanded_height > metrics.screen_height:
        ok = False
    if metrics.search_width > metrics.expanded_width - 80:
        ok = False
    if metrics.collapsed_radius > metrics.collapsed_height / 2:
        ok = False
    if metrics.expanded_radius > metrics.expanded_height / 2:
        ok = False
    status = "PASS" if ok else "FAIL"
    print(
        f"{status} {width}x{height}@{int(scale * 100)}% "
        f"logical={metrics.screen_width}x{metrics.screen_height} "
        f"collapsed={metrics.collapsed_width}x{metrics.collapsed_height} r{metrics.collapsed_radius} "
        f"expanded={metrics.expanded_width}x{metrics.expanded_height} r{metrics.expanded_radius} "
        f"search={metrics.search_width}x{metrics.search_height}"
    )
    return ok


def main() -> int:
    passed = all(check_case(width, height, scale) for width, height, scale in CASES)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
