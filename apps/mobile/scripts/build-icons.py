#!/usr/bin/env python3
"""Regenerate every launcher/splash asset from one geometry definition.

Why a script instead of checked-in art: the first icon set shipped an inverted V in template blue
(`#0072de` on `#e6f4fe`), which is neither the letter nor the palette the app uses. Hand-drawing six
PNGs means the next tweak drifts again. Here the shape is a parameter, so "the V is upright and purple"
is a fact in the repo, not a property of a binary blob nobody can diff.

    /usr/bin/python3 scripts/build-icons.py

Palette (keep in sync with src/theme colors.background / the purple accent):
    background  #0f1115
    V gradient  #a78bfa -> #7c3aed   (top -> bottom)

Geometry is expressed as fractions of the canvas edge, so the same V is cut at every size. `--scale`
shrinks the letter about the centre: the Android adaptive foreground must stay inside the 66% safe
zone, and a favicon needs the letter to fill the tile.
"""

from __future__ import annotations

import argparse
import pathlib

from PIL import Image, ImageDraw

BACKGROUND = (15, 17, 21, 255)  # #0f1115
PURPLE_TOP = (167, 139, 250)  # #a78bfa
PURPLE_BOTTOM = (124, 58, 237)  # #7c3aed
WHITE = (255, 255, 255, 255)

# The V, as fractions of the canvas edge, drawn stroke-centre to stroke-centre.
STROKE = 0.164
HALF_WIDTH = 0.246
ARM_HEIGHT = 0.395

SUPERSAMPLE = 4  # PIL lines are aliased; cut at 4x and let LANCZOS round the edges.
RESAMPLE = getattr(getattr(Image, "Resampling", Image), "LANCZOS")


def _lerp(start: tuple[int, int, int], end: tuple[int, int, int], t: float) -> tuple[int, int, int, int]:
    r, g, b = (round(start[i] + (end[i] - start[i]) * t) for i in range(3))
    return (r, g, b, 255)


def v_geometry(canvas: int, scale: float) -> tuple[tuple[float, float], tuple[float, float], tuple[float, float], float]:
    """Apex, left arm top, right arm top and stroke width, with the ink box centred on the canvas."""
    stroke = STROKE * canvas * scale
    half_width = HALF_WIDTH * canvas * scale
    arm_height = ARM_HEIGHT * canvas * scale
    centre = canvas / 2
    apex_y = centre + (arm_height + stroke) / 2 - stroke / 2
    top_y = apex_y - arm_height
    return (centre, apex_y), (centre - half_width, top_y), (centre + half_width, top_y), stroke


def v_mask(size: int, scale: float) -> Image.Image:
    """Antialiased coverage mask of the letter, white on black, same size as the canvas."""
    canvas = size * SUPERSAMPLE
    mask = Image.new("L", (canvas, canvas), 0)
    draw = ImageDraw.Draw(mask)
    apex, left, right, stroke = v_geometry(canvas, scale)
    radius = stroke / 2
    for start, end in ((apex, left), (apex, right)):
        draw.line([start, end], fill=255, width=int(round(stroke)))
    # Round caps: PIL's line has square ends, so a disc at every stroke end makes them round.
    for x, y in (apex, left, right):
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=255)
    return mask.resize((size, size), Image.LANCZOS)


def gradient(size: int, scale: float, colour: bool = True) -> Image.Image:
    """Vertical #a78bfa -> #7c3aed ramp spanning the letter, or flat white for the monochrome cut.

    Built as a one-pixel-wide strip and stretched: a per-pixel loop over 1024x1024 costs seconds and
    buys nothing, the ramp only varies on y.
    """
    if not colour:
        return Image.new("RGBA", (size, size), WHITE)
    apex, _, _, stroke = v_geometry(size, scale)
    arm_height = ARM_HEIGHT * size * scale
    top = apex[1] - arm_height - stroke / 2
    height = arm_height + stroke
    strip = Image.new("RGBA", (1, size))
    for y in range(size):
        t = min(max((y - top) / height, 0.0), 1.0)
        strip.putpixel((0, y), _lerp(PURPLE_TOP, PURPLE_BOTTOM, t))
    return strip.resize((size, size), RESAMPLE)


def cut(size: int, scale: float, background: tuple[int, int, int, int] | None, colour: bool = True) -> Image.Image:
    """The letter over `background` (None = transparent), at `scale` of the full-bleed size."""
    tile = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    tile.paste(gradient(size, scale, colour), (0, 0), v_mask(size, scale))
    return tile


def flat(size: int, colour: tuple[int, int, int, int]) -> Image.Image:
    return Image.new("RGBA", (size, size), colour)


def safe_zone_report(size: int, scale: float) -> str:
    """How much of the adaptive-icon safe circle the letter uses (must stay under 100%)."""
    mask = v_mask(size, scale)
    box = mask.getbbox()
    if box is None:
        raise SystemExit("empty mask — the letter vanished, check the geometry constants")
    left, top, right, bottom = box
    centre = size / 2
    # The safe zone is a 66dp circle inside the 108dp canvas: radius 0.305 of the edge.
    reach = max(
        ((x - centre) ** 2 + (y - centre) ** 2) ** 0.5
        for x in (left, right)
        for y in (top, bottom)
    )
    used = reach / (0.305 * size)
    verdict = "ok" if used <= 1.0 else "TOO BIG — it will be clipped by the launcher mask"
    return f"{used * 100:.0f}% of the safe radius ({verdict})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets", type=pathlib.Path, default=pathlib.Path(__file__).resolve().parent.parent / "assets")
    parser.add_argument("--dry-run", action="store_true", help="print what would be written, touch nothing")
    args = parser.parse_args()

    # The icon is also the legacy Android source: full-bleed, no rounding (launchers mask it themselves).
    outputs: dict[str, Image.Image] = {
        "icon.png": cut(1024, 1.0, BACKGROUND),
        "android-icon-background.png": flat(512, BACKGROUND),
        "android-icon-foreground.png": cut(512, 0.66, None),
        "android-icon-monochrome.png": cut(432, 0.66, None, colour=False),
        "splash-icon.png": cut(1024, 0.5, BACKGROUND),
        "favicon.png": cut(48, 1.0, BACKGROUND),
    }

    print(f"adaptive foreground stays inside the mask: {safe_zone_report(512, 0.66)}")

    for name, image in outputs.items():
        path = args.assets / name
        if args.dry_run:
            print(f"{name:30s} {image.size} (dry run)")
            continue
        rgb = image.convert("RGB") if name == "icon.png" else image
        rgb.save(path, optimize=True)
        print(f"{name:30s} {image.size} {path.stat().st_size:>8} B")


if __name__ == "__main__":
    main()
