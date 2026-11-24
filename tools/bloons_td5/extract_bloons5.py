#!/usr/bin/env python3
"""Package Bloons TD 5's loose asset tree into a clean extraction directory."""
import csv
import shutil
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/sandbox-games/Bloons-TD-5-SteamRIP.com/BloonsTD5")
OUT = GAME.parent / "_extracted"
ASSETS = OUT / "assets"
EXCLUDE = {".exe", ".orig", ".dll"}

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

stats = Counter()
rows = []


def package(src, rel):
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    suffix = src.suffix.lower() or "(none)"
    stats["files"] += 1
    stats["bytes"] += src.stat().st_size
    stats[f"ext_{suffix}"] += 1
    rows.append({"source": str(rel), "size": src.stat().st_size})


assets_root = GAME / "Assets"
for src in sorted(assets_root.rglob("*")):
    if src.is_file() and src.suffix.lower() not in EXCLUDE:
        package(src, src.relative_to(GAME))

for src in sorted(GAME.glob("*.txt")):
    package(src, Path(src.name))

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "size"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"files packaged : {stats['files']}",
          f"bytes packaged : {stats['bytes']}",
          "", "families:"]
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
