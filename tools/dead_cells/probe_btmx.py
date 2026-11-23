#!/usr/bin/env python3
"""Probe BTMX layer payloads by locating and inflating embedded base64 blobs."""
import base64
import re
import struct
import zlib
from pathlib import Path

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted/raw/tiled")
p = next(BASE.rglob("*.tmx"))
d = p.read_bytes()
print("file", p.name, "bytes", len(d))
print("magic", d[:4], "tiled", d[5:8].decode(), "build", d[10:17].decode())
width, height, tile_w, tile_h = struct.unpack_from("<4H", d, 18)
print("map", width, height, "tile", tile_w, tile_h)

text = d.decode("latin-1")
blobs = re.findall(r"[A-Za-z0-9+/]{20,}={0,2}", text)
print("base64 blobs", len(blobs))
for blob in blobs[:12]:
    try:
        raw = base64.b64decode(blob)
        data = zlib.decompress(raw)
        print("  b64", len(blob), "inflated", len(data), "head", data[:16].hex())
    except Exception as exc:
        print("  b64", len(blob), "skip", type(exc).__name__)
