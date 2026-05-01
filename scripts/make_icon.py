#!/usr/bin/env python3
"""Create macOS and Windows application icons from icon.png.

The source icon already contains a visible rounded-square frame with a dark
outer margin. This script crops to that visible frame, applies a transparent
rounded mask, and writes platform icon formats.
"""

from __future__ import annotations

import argparse
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw


ICONSET_SIZES = [
    (16, "icon_16x16.png"),
    (32, "icon_16x16@2x.png"),
    (32, "icon_32x32.png"),
    (64, "icon_32x32@2x.png"),
    (128, "icon_128x128.png"),
    (256, "icon_128x128@2x.png"),
    (256, "icon_256x256.png"),
    (512, "icon_256x256@2x.png"),
    (512, "icon_512x512.png"),
    (1024, "icon_512x512@2x.png"),
]

ICNS_ENTRIES = [
    ("icp4", "icon_16x16.png"),
    ("icp5", "icon_32x32.png"),
    ("icp6", "icon_32x32@2x.png"),
    ("ic07", "icon_128x128.png"),
    ("ic08", "icon_256x256.png"),
    ("ic09", "icon_512x512.png"),
    ("ic10", "icon_512x512@2x.png"),
]


def visible_bbox(image: Image.Image, threshold: float) -> tuple[int, int, int, int]:
    rgb = np.asarray(image.convert("RGB"))
    lum = 0.2126 * rgb[:, :, 0] + 0.7152 * rgb[:, :, 1] + 0.0722 * rgb[:, :, 2]
    ys, xs = np.where(lum > threshold)
    if xs.size == 0:
        raise ValueError(f"No visible pixels found above threshold {threshold}.")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def square_crop_box(
    bbox: tuple[int, int, int, int],
    image_size: tuple[int, int],
    padding: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bbox
    width = right - left
    height = bottom - top
    side = max(width, height) + padding * 2
    cx = (left + right) / 2
    cy = (top + bottom) / 2

    crop_left = round(cx - side / 2)
    crop_top = round(cy - side / 2)
    crop_left = max(0, min(crop_left, image_size[0] - side))
    crop_top = max(0, min(crop_top, image_size[1] - side))
    return crop_left, crop_top, crop_left + side, crop_top + side


def rounded_icon(
    source: Path,
    threshold: float,
    padding: int,
    radius_ratio: float,
) -> Image.Image:
    image = Image.open(source).convert("RGBA")
    crop = image.crop(square_crop_box(visible_bbox(image, threshold), image.size, padding))

    size = min(crop.size)
    if crop.size[0] != crop.size[1]:
        crop = crop.crop((0, 0, size, size))

    scale = 4
    radius = round(size * radius_ratio)
    mask_big = Image.new("L", (size * scale, size * scale), 0)
    draw = ImageDraw.Draw(mask_big)
    draw.rounded_rectangle(
        (0, 0, size * scale - 1, size * scale - 1),
        radius=radius * scale,
        fill=255,
    )
    mask = mask_big.resize((size, size), Image.Resampling.LANCZOS)
    crop.putalpha(mask)
    return crop


def write_icns(icon: Image.Image, iconset_dir: Path, output: Path) -> None:
    iconset_dir.mkdir(parents=True, exist_ok=True)
    for size, filename in ICONSET_SIZES:
        icon.resize((size, size), Image.Resampling.LANCZOS).save(iconset_dir / filename, "PNG")

    # PNG-backed ICNS slots are accepted by modern macOS and avoid relying on
    # iconutil, which can reject otherwise valid iconsets in sandboxed builds.
    payload = b""
    for code, filename in ICNS_ENTRIES:
        data = (iconset_dir / filename).read_bytes()
        payload += code.encode("ascii") + struct.pack(">I", len(data) + 8) + data

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_bytes(b"icns" + struct.pack(">I", len(payload) + 8) + payload)


def write_ico(icon: Image.Image, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    icon.save(output, sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=Path("icon.png"))
    parser.add_argument("--rounded-png", type=Path)
    parser.add_argument("--iconset-dir", type=Path, default=Path("dist/icons/BKW.iconset"))
    parser.add_argument("--icns", type=Path)
    parser.add_argument("--ico", type=Path)
    parser.add_argument("--threshold", type=float, default=8.0)
    parser.add_argument("--padding", type=int, default=0)
    parser.add_argument("--radius-ratio", type=float, default=0.23)
    args = parser.parse_args()

    icon = rounded_icon(args.input, args.threshold, args.padding, args.radius_ratio)

    if args.rounded_png:
        args.rounded_png.parent.mkdir(parents=True, exist_ok=True)
        icon.save(args.rounded_png, "PNG")
    if args.icns:
        write_icns(icon, args.iconset_dir, args.icns)
    if args.ico:
        write_ico(icon, args.ico)


if __name__ == "__main__":
    main()
