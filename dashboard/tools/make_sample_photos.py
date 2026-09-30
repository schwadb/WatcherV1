"""Create a few sample photos in the photo folder so the slideshow has something to show.

Usage:  .venv/bin/python tools/make_sample_photos.py [folder]
One photo carries an EXIF rotation tag so the server's auto-rotate can be checked.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
folder = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "photos"
folder.mkdir(parents=True, exist_ok=True)


def gradient(size: tuple[int, int], top: tuple[int, int, int], bottom: tuple[int, int, int]) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size)
    px = im.load()
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(w):
            px[x, y] = color
    return im


samples = [
    ("sample-sunset.jpg", (2400, 1600), (255, 140, 60), (40, 20, 80), "Sample photo 1 — sunset"),
    ("sample-lake.jpg", (2000, 1500), (30, 90, 160), (10, 30, 50), "Sample photo 2 — lake"),
    ("sample-portrait.jpg", (1800, 1200), (60, 150, 90), (20, 40, 30), "Sample photo 3 — EXIF rotated"),
]
for name, size, top, bottom, caption in samples:
    im = gradient(size, top, bottom)
    draw = ImageDraw.Draw(im)
    draw.rectangle([40, 40, size[0] - 40, size[1] - 40], outline=(255, 255, 255), width=8)
    draw.text((80, 80), caption, fill=(255, 255, 255))
    exif = None
    if "portrait" in name:
        exif = Image.Exif()
        exif[0x0112] = 6  # rotate 90° clockwise when displayed
    im.save(folder / name, "JPEG", quality=90, exif=exif.tobytes() if exif else b"")
    print("wrote", folder / name)
