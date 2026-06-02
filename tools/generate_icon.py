from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
PNG_PATH = ASSETS / "icon_256.png"
ICO_PATH = ASSETS / "icon.ico"
ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def lerp(a: int, b: int, t: float) -> int:
    return round(a + (b - a) * t)


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i : i + 2], 16) for i in (0, 2, 4))


def gradient(size: int, stops: list[tuple[float, str]], angle: float = 0.0) -> Image.Image:
    image = Image.new("RGBA", (size, size))
    px = image.load()
    direction = (math.cos(angle), math.sin(angle))
    for y in range(size):
        for x in range(size):
            nx = (x / max(1, size - 1)) - 0.5
            ny = (y / max(1, size - 1)) - 0.5
            t = (nx * direction[0] + ny * direction[1]) + 0.5
            t = max(0.0, min(1.0, t))
            for idx in range(len(stops) - 1):
                left_t, left_c = stops[idx]
                right_t, right_c = stops[idx + 1]
                if left_t <= t <= right_t:
                    p = 0.0 if right_t == left_t else (t - left_t) / (right_t - left_t)
                    lc = hex_to_rgb(left_c)
                    rc = hex_to_rgb(right_c)
                    px[x, y] = (
                        lerp(lc[0], rc[0], p),
                        lerp(lc[1], rc[1], p),
                        lerp(lc[2], rc[2], p),
                        255,
                    )
                    break
    return image


def rounded_rect_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def draw_icon(logical_size: int) -> Image.Image:
    scale = 4
    size = logical_size * scale
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    corner = round(size * 0.205)
    bg_mask = rounded_rect_mask(size, corner)
    bg = gradient(
        size,
        [(0.0, "#030712"), (0.45, "#071226"), (1.0, "#10172A")],
        angle=math.radians(135),
    )
    image = Image.composite(bg, image, bg_mask)

    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.ellipse(
        (size * 0.08, size * 0.48, size * 0.92, size * 1.18),
        fill=(20, 184, 255, 66),
    )
    glow_draw.ellipse(
        (size * 0.02, size * 0.08, size * 0.72, size * 0.94),
        fill=(124, 97, 255, 44),
    )
    glow = glow.filter(ImageFilter.GaussianBlur(round(size * 0.07)))
    image.alpha_composite(glow)

    shade = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shade_draw = ImageDraw.Draw(shade)
    shade_draw.rounded_rectangle(
        (size * 0.08, size * 0.08, size * 0.92, size * 0.92),
        radius=corner,
        outline=(165, 205, 255, 28),
        width=max(1, round(size * 0.01)),
    )
    image.alpha_composite(shade)

    ring_outer = Image.new("L", (size, size), 0)
    ring_draw = ImageDraw.Draw(ring_outer)
    ring_box = (size * 0.255, size * 0.17, size * 0.745, size * 0.83)
    ring_draw.ellipse(ring_box, fill=255)
    inner = Image.new("L", (size, size), 0)
    inner_draw = ImageDraw.Draw(inner)
    inner_box = (size * 0.385, size * 0.31, size * 0.615, size * 0.69)
    inner_draw.ellipse(inner_box, fill=255)
    ring_mask = ImageChops.subtract(ring_outer, inner)

    ring_glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    ring_glow.alpha_composite(gradient(size, [(0.0, "#A78BFA"), (0.5, "#38BDF8"), (1.0, "#22D3EE")], angle=math.radians(45)))
    ring_glow.putalpha(ring_mask.filter(ImageFilter.GaussianBlur(round(size * 0.018))))
    image.alpha_composite(ring_glow)

    ring_fill = gradient(
        size,
        [(0.0, "#A78BFA"), (0.25, "#60A5FA"), (0.58, "#22D3EE"), (1.0, "#2DD4BF")],
        angle=math.radians(55),
    )
    ring_fill.putalpha(ring_mask)
    image.alpha_composite(ring_fill)

    bar_mask = Image.new("L", (size, size), 0)
    bar_draw = ImageDraw.Draw(bar_mask)
    bar_rect = (size * 0.16, size * 0.43, size * 0.84, size * 0.61)
    bar_radius = round(size * 0.09)
    bar_draw.rounded_rectangle(bar_rect, radius=bar_radius, fill=255)

    bar_shadow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    shadow_mask = bar_mask.filter(ImageFilter.GaussianBlur(round(size * 0.028)))
    bar_shadow.putalpha(shadow_mask)
    bar_shadow = Image.new("RGBA", (size, size), (0, 16, 28, 95))
    bar_shadow.putalpha(shadow_mask)
    image.alpha_composite(bar_shadow)

    bar_fill = gradient(
        size,
        [(0.0, "#2563EB"), (0.45, "#38BDF8"), (1.0, "#06B6D4")],
        angle=0,
    )
    bar_fill.putalpha(bar_mask)
    image.alpha_composite(bar_fill)

    bar_hi = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    hi_draw = ImageDraw.Draw(bar_hi)
    hi_draw.rounded_rectangle(
        (bar_rect[0] + size * 0.02, bar_rect[1] + size * 0.018, bar_rect[2] - size * 0.02, bar_rect[1] + size * 0.062),
        radius=round(size * 0.025),
        fill=(255, 255, 255, 58),
    )
    image.alpha_composite(bar_hi)

    dot = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    dot_draw = ImageDraw.Draw(dot)
    dot_r = max(1, round(size * 0.052))
    dot_c = (size * 0.5, size * 0.52)
    dot_draw.ellipse(
        (dot_c[0] - dot_r, dot_c[1] - dot_r, dot_c[0] + dot_r, dot_c[1] + dot_r),
        fill=(242, 250, 255, 245),
    )
    image.alpha_composite(dot)

    final = image.resize((logical_size, logical_size), Image.Resampling.LANCZOS)
    return final


def main() -> None:
    ASSETS.mkdir(parents=True, exist_ok=True)
    icon_256 = draw_icon(256)
    icon_256.save(PNG_PATH)
    images = [draw_icon(size) for size in ICO_SIZES]
    images[-1].save(ICO_PATH, sizes=[(size, size) for size in ICO_SIZES], append_images=images[:-1])
    print(f"Generated {PNG_PATH}")
    print(f"Generated {ICO_PATH}")


if __name__ == "__main__":
    main()
