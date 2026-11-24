#!/usr/bin/env python3
"""Extract the LÖVE ZIP appended to Balatro.exe."""
import csv
import shutil
import zipfile
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/sandbox-games/Balatro-SteamRIP.com/Balatro")
EXE = GAME / "Balatro.exe"
OUT = GAME.parent / "_extracted"
ASSETS = OUT / "assets"

if OUT.exists():
    shutil.rmtree(OUT)
ASSETS.mkdir(parents=True, exist_ok=True)

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


with zipfile.ZipFile(EXE) as archive:
    for info in archive.infolist():
        if info.is_dir():
            continue
        target = ASSETS.joinpath(*safe_parts(info.filename))
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
        suffix = Path(info.filename).suffix.lower() or "(none)"
        stats["files"] += 1
        stats["bytes"] += info.file_size
        stats[f"ext_{suffix}"] += 1
        rows.append({"name": info.filename, "size": info.file_size,
                     "compressed": info.compress_size})

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["name", "size", "compressed"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"files extracted : {stats['files']}",
          f"bytes extracted : {stats['bytes']}",
          "", "families:"]
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
