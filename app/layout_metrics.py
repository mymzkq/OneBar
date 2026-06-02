from __future__ import annotations

from dataclasses import dataclass


def clamp(value: float, minimum: float, maximum: float) -> float:
    if maximum < minimum:
        maximum = minimum
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class ResponsiveMetrics:
    screen_width: int
    screen_height: int
    dpi_scale: float
    collapsed_width: int
    collapsed_height: int
    collapsed_radius: int
    collapsed_max_width: int
    expanded_width: int
    expanded_height: int
    expanded_radius: int
    search_width: int
    search_height: int
    search_bottom_margin: int


def compute_responsive_metrics(
    user_body_width: int,
    user_body_height: int,
    user_radius: int,
    screen_width: int,
    screen_height: int,
    dpi_scale: float = 1.0,
) -> ResponsiveMetrics:
    logical_width = max(320.0, float(screen_width))
    logical_height = max(240.0, float(screen_height))

    collapsed_width_max = int(round(clamp(min(680.0, logical_width * 0.72), 280.0, 680.0)))
    collapsed_width = int(round(clamp(float(user_body_width), 280.0, collapsed_width_max)))
    collapsed_height = int(round(clamp(float(user_body_height), 30.0, 52.0)))
    collapsed_radius = int(round(clamp(float(user_radius), 3.0, min(28.0, collapsed_height / 2.0))))

    expanded_width_upper = max(320.0, min(900.0, logical_width * 0.82))
    expanded_width_lower = min(620.0, expanded_width_upper)
    expanded_width = int(round(clamp(720.0, expanded_width_lower, expanded_width_upper)))

    expanded_height_upper = max(220.0, min(520.0, logical_height * 0.55))
    expanded_height_lower = min(300.0, expanded_height_upper)
    expanded_height = int(round(clamp(360.0, expanded_height_lower, expanded_height_upper)))
    expanded_radius = int(round(clamp(user_radius * 2.4, 12.0, min(32.0, expanded_height / 2.0))))

    search_width_upper = max(240.0, min(660.0, expanded_width - 80.0))
    search_width_lower = min(380.0, search_width_upper)
    search_width = int(round(clamp(expanded_width - 140.0, search_width_lower, search_width_upper)))
    search_height = int(round(clamp(44.0, 40.0, 50.0)))
    search_bottom_margin = int(round(clamp(32.0, 24.0, 40.0)))

    return ResponsiveMetrics(
        screen_width=int(round(logical_width)),
        screen_height=int(round(logical_height)),
        dpi_scale=float(dpi_scale),
        collapsed_width=collapsed_width,
        collapsed_height=collapsed_height,
        collapsed_radius=collapsed_radius,
        collapsed_max_width=collapsed_width_max,
        expanded_width=expanded_width,
        expanded_height=expanded_height,
        expanded_radius=expanded_radius,
        search_width=search_width,
        search_height=search_height,
        search_bottom_margin=search_bottom_margin,
    )
