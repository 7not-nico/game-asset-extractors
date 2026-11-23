#!/usr/bin/env python3
"""Probe the BATL atlas layout by decoding one atlas and cropping frames."""
import struct
from pathlib import Path

from PIL import Image

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted/raw")
OUT = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted/atlas_probe")

data = (BASE / "atlas/fxDisplace.atlas").read_bytes()
assert data[:4] == b"BATL"
pos = 4
n = data[pos]
pos += 1
texture = data[pos:pos + n].decode()
pos += n
print("texture", texture)

image = Image.open(BASE / "atlas" / texture)
print("image size", image.size)

records = []
while pos < len(data):
    n = data[pos]
    pos += 1
    if n == 0:
        print("zero name at", pos - 1, "remaining", len(data) - pos)
        break
    name = data[pos:pos + n].decode()
    pos += n
    values = struct.unpack_from("<9H", data, pos)
    pos += 18
    records.append((name, values))

print("records", len(records))
for name, values in records[:8]:
    print(name, values)

OUT.mkdir(parents=True, exist_ok=True)
for name, values in records[:3]:
    flag, x, y, w, h, dx, dy, orig_w, orig_h = values
    crop = image.crop((x, y, x + w, y + h))
    crop.save(OUT / f"{name}.png")
    print("saved", name, crop.size)
