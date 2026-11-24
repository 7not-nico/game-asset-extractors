#!/usr/bin/env python3
"""Convert Ninja Kiwi JPNG files (JPEG + PNG alpha + footer) to PNG."""
import io
import shutil
import struct
from collections import Counter
from pathlib import Path

from PIL import Image

BASE = Path("/run/media/eddyr/external/sandbox-games/Bloons-TD-5-SteamRIP.com/_extracted")
SOURCE = BASE / "Assets"
OUT = BASE / "jpng_png"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

stats = Counter()
errors = []


def safe_parts(path):
    return [p for p in path.parts if p not in ("", ".", "..")]


for src in sorted(SOURCE.rglob("*.jpng")):
    blob = src.read_bytes()
    if len(blob) < 16:
        errors.append(f"short file: {src.name}")
        continue
    alpha_offset, alpha_size, _, magic = struct.unpack("<III4s", blob[-16:])
    if magic not in (b"GEPJ", b"GNPJ") or alpha_offset <= 0 or alpha_size <= 0:
        errors.append(f"bad footer: {src.name} {magic}")
        continue
    try:
        rgb = Image.open(io.BytesIO(blob[:alpha_offset])).convert("RGB")
        alpha = Image.open(io.BytesIO(blob[alpha_offset:alpha_offset + alpha_size]))
        if alpha.size != rgb.size:
            errors.append(f"size mismatch: {src.name} {rgb.size} {alpha.size}")
            continue
        rgba = rgb.copy()
        rgba.putalpha(alpha.convert("L"))
        rel = src.relative_to(SOURCE).with_suffix(".png")
        target = OUT.joinpath(*safe_parts(rel))
        target.parent.mkdir(parents=True, exist_ok=True)
        rgba.save(target)
        stats["converted"] += 1
    except Exception as exc:
        errors.append(f"decode {src.name}: {type(exc).__name__}: {exc}")

report = [f"jpng files   : {stats['converted'] + len(errors)}",
          f"converted    : {stats['converted']}",
          f"errors       : {len(errors)}"]
if errors:
    report.append("")
    report.append("first 40 errors:")
    report.extend(f"  {e}" for e in errors[:40])
(BASE / "jpng_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
