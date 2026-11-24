#!/usr/bin/env python3
"""Extract SteamWorld Heist assets from loose files, .z streams and .impak ZIPs."""
import csv
import re
import shutil
import struct
import zipfile
import zlib
from collections import Counter
from pathlib import Path

from PIL import Image

GAME = Path("/run/media/eddyr/external/heroic/SteamWorld Heist/game")
OUT = GAME.parent / "_extracted"
ASSETS = OUT / "assets"
ZOUT = OUT / "raw_z"
IMPAK = OUT / "impak"
FRAMES = OUT / "atlas_frames"

for folder in (ASSETS, ZOUT, IMPAK, FRAMES):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

LOOSE_EXT = {".png", ".ogg", ".wav", ".irc"}
stats = Counter()
errors = []
rows = []


def safe_parts(name):
    parts = []
    for part in Path(name).parts:
        if part in ("", ".", ".."):
            continue
        parts.append(re.sub(r'[<>:"|?*]', "_", part))
    return parts


# 1. loose assets
for src in sorted(GAME.rglob("*")):
    if not src.is_file() or src.suffix.lower() not in LOOSE_EXT:
        continue
    rel = src.relative_to(GAME)
    target = ASSETS.joinpath(*safe_parts(rel))
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    stats["loose"] += 1
    stats[f"loose_{src.suffix.lower()}"] += 1
    rows.append({"kind": "loose", "source": str(rel), "size": src.stat().st_size})

# 2. .z streams: u32 uncompressed size + zlib payload
for src in sorted(GAME.rglob("*.z")):
    rel = src.relative_to(GAME)
    blob = src.read_bytes()
    declared = struct.unpack_from("<I", blob, 0)[0]
    try:
        data = zlib.decompress(blob[4:])
    except Exception as exc:
        errors.append(f"zlib {rel}: {type(exc).__name__}: {exc}")
        continue
    if len(data) != declared:
        errors.append(f"zlib size {rel}: got {len(data)} want {declared}")
    target = ZOUT.joinpath(*safe_parts(str(rel.with_suffix(""))))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    stats["z_files"] += 1
    stats["z_bytes"] += len(data)
    rows.append({"kind": "z", "source": str(rel), "size": len(data)})

# 3. .impak archives are ZIP files
for src in sorted(GAME.rglob("*.impak")):
    rel = src.relative_to(GAME)
    dest = IMPAK.joinpath(*safe_parts(str(rel.with_suffix(""))))
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(src) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = dest.joinpath(*safe_parts(info.filename))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            stats["impak_entries"] += 1
            rows.append({"kind": "impak", "source": f"{rel}!{info.filename}",
                         "size": info.file_size})

# 4. atlas frame splitting from the decompressed map
map_path = ZOUT / "Bundle/Atlases/atlases.map"
if map_path.exists():
    atlas_pages = {}
    current = None
    for line in map_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith(":"):
            current = line[1:]
            atlas_pages[current] = []
        elif current and " = " in line:
            name, values = line.split(" = ", 1)
            try:
                x, y, w, h = (int(v) for v in values.split())
                atlas_pages[current].append((name, x, y, w, h))
            except ValueError:
                continue
    page_index = {}
    for candidate in list(GAME.rglob("*.png")) + list(IMPAK.rglob("*.png")):
        page_index.setdefault(candidate.name, candidate)
    for page, regions in atlas_pages.items():
        image_path = page_index.get(page + ".png")
        if image_path is None:
            errors.append(f"atlas page missing: {page}")
            continue
        with Image.open(image_path) as image:
            for name, x, y, w, h in regions:
                target = FRAMES.joinpath(*safe_parts(name + ".png"))
                target.parent.mkdir(parents=True, exist_ok=True)
                try:
                    image.crop((x, y, x + w, y + h)).save(target)
                    stats["frames"] += 1
                except Exception as exc:
                    errors.append(f"crop {page}:{name}: {type(exc).__name__}: {exc}")
    stats["atlas_pages"] = len(atlas_pages)

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["kind", "source", "size"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"loose assets       : {stats['loose']}",
          f"z streams inflated : {stats['z_files']}",
          f"z bytes            : {stats['z_bytes']}",
          f"impak entries      : {stats['impak_entries']}",
          f"atlas pages        : {stats['atlas_pages']}",
          f"frames written     : {stats['frames']}",
          f"errors             : {len(errors)}",
          "", "loose by extension:"]
for key, count in sorted(stats.items()):
    if key.startswith("loose_"):
        report.append(f"  {key[6:]}: {count}")
if errors:
    report.append("")
    report.append("first 40 errors:")
    report.extend(f"  {e}" for e in errors[:40])
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report[:7]), flush=True)
print("OUTPUT:", OUT, flush=True)
