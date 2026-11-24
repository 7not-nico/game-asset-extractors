#!/usr/bin/env python3
"""Package NEO Scavenger's loose assets into a clean extraction tree."""
import csv
import shutil
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/heroic/NEO Scavenger/game")
OUT = GAME.parent / "_extracted"
INCLUDE_DIRS = ("data", "img", "SampleModFolder", "0")
INCLUDE_FILES = {"getmods.php", "getimages.php", "getmods.example.php", "_readme.txt"}

if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True, exist_ok=True)

stats = Counter()
rows = []


def copy_file(src, rel):
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    suffix = src.suffix.lower() or "(none)"
    stats["files"] += 1
    stats[f"ext_{suffix}"] += 1
    stats[f"dir_{rel.parts[0]}"] += 1
    rows.append({"source": str(rel), "size": src.stat().st_size})


for folder in INCLUDE_DIRS:
    root = GAME / folder
    if not root.exists():
        continue
    for src in sorted(root.rglob("*")):
        if src.is_file():
            copy_file(src, src.relative_to(GAME))

for src in sorted(GAME.iterdir()):
    if src.is_file() and src.name in INCLUDE_FILES:
        copy_file(src, Path(src.name))

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "size"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"files packaged : {stats['files']}", "", "by extension:"]
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
report.append("")
report.append("by directory:")
for key, count in sorted(stats.items()):
    if key.startswith("dir_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
