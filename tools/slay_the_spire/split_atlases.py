#!/usr/bin/env python3
"""Split libGDX .atlas texture pages into individual frame PNGs."""
import re
import shutil
from collections import Counter
from pathlib import Path

from PIL import Image

ROOT = Path("/run/media/eddyr/external/sandbox-games/Slay-the-Spire-SteamRIP.com/Slay the Spire v2.3.4")
ASSETS = ROOT / "_extracted/assets"
OUT = ROOT / "_extracted/atlas_frames"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

stats = Counter()
errors = []
IMAGE_EXT = (".png", ".jpg", ".jpeg")


def parse_atlas(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    pages = []
    current = None
    region = None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        if not raw.startswith((" ", "\t")):
            if line.lower().endswith(IMAGE_EXT):
                current = {"image": line, "regions": []}
                pages.append(current)
                region = None
                continue
            if ":" in line:
                continue
            region = {"name": line, "rotate": False, "xy": (0, 0), "size": (0, 0)}
            if current is not None:
                current["regions"].append(region)
            continue
        if region is None or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if key == "rotate":
            region["rotate"] = value.lower() == "true"
        elif key == "xy":
            region["xy"] = tuple(int(v) for v in value.split(","))
        elif key == "size":
            region["size"] = tuple(int(v) for v in value.split(","))
    return pages


def safe_name(value):
    return re.sub(r'[<>:"|?*\\/]', "_", value).strip() or "unnamed"


for atlas in sorted(ASSETS.rglob("*.atlas")):
    try:
        pages = parse_atlas(atlas)
    except Exception as exc:
        errors.append(f"parse {atlas.name}: {type(exc).__name__}: {exc}")
        continue
    rel = atlas.relative_to(ASSETS)
    for page in pages:
        image_path = atlas.parent / page["image"]
        if not image_path.exists():
            errors.append(f"missing page: {atlas.name} -> {page['image']}")
            continue
        with Image.open(image_path) as image:
            for region in page["regions"]:
                x, y = region["xy"]
                w, h = region["size"]
                if w <= 0 or h <= 0:
                    continue
                try:
                    frame = image.crop((x, y, x + w, y + h))
                    if region["rotate"]:
                        frame = frame.rotate(90, expand=True)
                    target = OUT / rel.parent / atlas.stem / f"{safe_name(region['name'])}.png"
                    target.parent.mkdir(parents=True, exist_ok=True)
                    frame.save(target)
                    stats["frames"] += 1
                except Exception as exc:
                    errors.append(f"crop {atlas.name}:{region['name']}: {type(exc).__name__}: {exc}")
        stats["pages"] += 1
    stats["atlases"] += 1

report = [f"atlases processed : {stats['atlases']}",
          f"pages processed   : {stats['pages']}",
          f"frames written    : {stats['frames']}",
          f"errors            : {len(errors)}"]
if errors:
    report.append("")
    report.append("first 40 errors:")
    report.extend(f"  {e}" for e in errors[:40])
(ROOT / "_extracted/atlas_report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
