#!/usr/bin/env python3
"""Render BTMX collision/link tile layers into debug preview images."""
import argparse
import base64
import re
import struct
import zlib
from collections import Counter
from pathlib import Path

from PIL import Image

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted")
RAW = BASE / "raw"
TILED = RAW / "tiled"
OUT = BASE / "map_previews"
TILE_SHEETS = {"col": Image.open(TILED / "col.png").convert("RGBA"),
               "lnk": Image.open(TILED / "lnk.png").convert("RGBA")}
LAYER_NAMES = ["col", "lnk"]


def decode_layer(blob, tile_w, count):
    data = zlib.decompress(base64.b64decode(blob))
    values = struct.unpack(f"<{len(data) // 4}I", data)
    sheet = TILE_SHEETS[tile_w]
    tiles = sheet.width // 24
    canvas = Image.new("RGBA", (count[0] * 24, count[1] * 24), (0, 0, 0, 0))
    for index, gid in enumerate(values):
        if gid == 0:
            continue
        tile_index = gid - 1
        if tile_index >= tiles:
            continue
        x = (index % count[0]) * 24
        y = (index // count[0]) * 24
        tile = sheet.crop((tile_index * 24, 0, tile_index * 24 + 24, 24))
        canvas.paste(tile, (x, y))
    return canvas, values


def render(path):
    data = path.read_bytes()
    text = data.decode("latin-1")
    tile_w, tile_h, width, height = struct.unpack_from("<4H", data, 14)
    blobs = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
    layers = []
    for index, blob in enumerate(blobs[:2]):
        name = LAYER_NAMES[index]
        image, values = decode_layer(blob, name, (width, height))
        layers.append((name, image, values))
    if not layers:
        return None
    total_width = sum(image.width for _, image, _ in layers)
    max_height = max(image.height for _, image, _ in layers)
    composite = Image.new("RGBA", (total_width, max_height), (0, 0, 0, 0))
    offset = 0
    for _, image, _ in layers:
        composite.paste(image, (offset, 0))
        offset += image.width
    target = OUT / f"{path.stem}.png"
    composite.save(target)
    return [(name, len(set(values))) for name, _, values in layers]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    maps = sorted(TILED.rglob("*.tmx"))[:args.limit]
    stats = Counter()
    for path in maps:
        try:
            result = render(path)
        except Exception as exc:
            stats["errors"] += 1
            print("FAIL", path.name, type(exc).__name__, exc)
            continue
        if result is None:
            stats["no_layers"] += 1
            continue
        stats["maps"] += 1
        print(path.name, result, flush=True)
    print("maps", stats["maps"], "errors", stats["errors"])


if __name__ == "__main__":
    main()
