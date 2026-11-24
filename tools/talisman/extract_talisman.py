#!/usr/bin/env python3
"""Extract Talisman Digital Edition asset ZIP packs."""
import csv
import shutil
import zipfile
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/sandbox-games/Talisman.Digital.Edition.v2023.06.15.Incl.ALL.DLC/Talisman.Digital.Edition.v2023.06.15.Incl.ALL.DLC")
OUT = GAME.parent / "_extracted"
ASSETS = OUT / "assets"
RAW = OUT / "raw"

if OUT.exists():
    shutil.rmtree(OUT)
ASSETS.mkdir(parents=True, exist_ok=True)
RAW.mkdir(parents=True, exist_ok=True)

stats = Counter()
rows = []


def safe_parts(name):
    parts = []
    for part in Path(name.replace("\\", "/")).parts:
        if part in ("", ".", ".."):
            continue
        parts.append(part.replace(":", "_").replace("?", "_").replace("*", "_")
                     .replace("<", "_").replace(">", "_").replace("|", "_"))
    return parts


for name in ("manifest.lst", "revision.txt", "game.ini", "readme.txt"):
    src = GAME / name
    if src.is_file():
        shutil.copy2(src, RAW / name)
        stats["raw_copied"] += 1

for pack in sorted(GAME.glob("*.zip")):
    dest = ASSETS / pack.stem
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(pack) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = dest.joinpath(*safe_parts(info.filename))
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            suffix = Path(info.filename).suffix.lower() or "(none)"
            stats["entries"] += 1
            stats["bytes"] += info.file_size
            stats[f"ext_{suffix}"] += 1
            rows.append({"pack": pack.name, "name": info.filename,
                         "size": info.file_size, "compressed": info.compress_size})
    print(f"  {pack.name}: {stats['entries']} entries so far", flush=True)

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["pack", "name", "size", "compressed"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"packs processed   : {len(list(GAME.glob('*.zip')))}",
          f"entries extracted : {stats['entries']}",
          f"bytes extracted   : {stats['bytes']}",
          f"raw files copied   : {stats['raw_copied']}",
          "", "families:"]
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report[:4]), flush=True)
print("OUTPUT:", OUT, flush=True)
