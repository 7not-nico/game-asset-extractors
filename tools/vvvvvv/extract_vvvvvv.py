#!/usr/bin/env python3
"""Extract VVVVVV data.zip and loose language/license files."""
import csv
import shutil
import zipfile
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/heroic/VVVVVV/game")
OUT = GAME.parent / "_extracted"
DATA = OUT / "data"
LANG = OUT / "lang"
LICENSES = OUT / "licenses"

for folder in (DATA, LANG, LICENSES):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

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


with zipfile.ZipFile(GAME / "data.zip") as archive:
    for info in archive.infolist():
        if info.is_dir():
            continue
        target = DATA.joinpath(*safe_parts(info.filename))
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(info) as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
        suffix = Path(info.filename).suffix.lower() or "(none)"
        stats["zip_entries"] += 1
        stats[f"ext_{suffix}"] += 1
        rows.append({"source": "data.zip", "name": info.filename,
                     "size": info.file_size})

for folder, dest in ((GAME / "lang", LANG), (GAME / "licenses", LICENSES)):
    if not folder.exists():
        continue
    for src in sorted(folder.rglob("*")):
        if not src.is_file():
            continue
        target = dest / src.relative_to(folder)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        stats["loose_files"] += 1
        rows.append({"source": str(folder.name), "name": str(src.relative_to(folder)),
                     "size": src.stat().st_size})

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "name", "size"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"zip entries        : {stats['zip_entries']}",
          f"loose files copied : {stats['loose_files']}",
          "", "families:"]
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
