#!/usr/bin/env python3
"""Extract Spelunky loose assets, WAD payloads and the web cache."""
import csv
import re
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path("/run/media/eddyr/external/heroic/Spelunky")
DATA = ROOT / "Data"
OUT = ROOT / "_extracted"
ASSETS = OUT / "assets"
WAD = OUT / "wad"

for folder in (ASSETS, WAD):
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)

stats = Counter()
rows = []


def safe_parts(name):
    parts = []
    for part in Path(str(name).replace("\\", "/")).parts:
        if part in ("", ".", ".."):
            continue
        parts.append(re.sub(r'[<>:"|?*]', "_", part))
    return parts


def add_row(source, target, size):
    rows.append({"source": source, "target": str(target.relative_to(OUT)), "size": size})
    stats["files"] += 1


# 1. loose Data files (WADs handled separately)
for src in sorted(DATA.rglob("*")):
    if not src.is_file() or src.suffix.lower() in (".wad", ".wix", ".sav", ".bak"):
        continue
    target = ASSETS / src.relative_to(DATA)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    add_row(str(src.relative_to(ROOT)), target, src.stat().st_size)

# 2. WAD carving via .wix indexes
for wix in sorted(DATA.rglob("*.wix")):
    wad_path = wix.with_suffix("")
    if not wad_path.exists():
        continue
    group = "(root)"
    with wad_path.open("rb") as blob:
        for line in wix.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("!group"):
                group = line[len("!group"):].strip() or "(root)"
                continue
            parts = line.split()
            if len(parts) < 3:
                continue
            name = parts[0]
            try:
                offset, size = int(parts[1]), int(parts[2])
            except ValueError:
                continue
            target = WAD / wad_path.stem / group / name
            target.parent.mkdir(parents=True, exist_ok=True)
            blob.seek(offset)
            data = blob.read(size)
            if len(data) != size:
                continue
            target.write_bytes(data)
            add_row(f"{wad_path.name}:{offset}", target, size)
            stats[f"wad_{wad_path.stem}"] += 1

# 3. animation definitions are a small text-like WAD with no index
anim = DATA / "Animations/allanimations.wad"
if anim.exists():
    target = ASSETS / "Animations/allanimations.wad"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(anim, target)
    add_row(str(anim.relative_to(ROOT)), target, anim.stat().st_size)

# 4. web cache ZIP
webcache = ROOT / "webcache.zip"
if webcache.exists():
    with zipfile.ZipFile(webcache) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            target = OUT / "webcache" / info.filename
            target.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as source, target.open("wb") as out:
                shutil.copyfileobj(source, out)
            add_row(f"webcache.zip:{info.filename}", target, info.file_size)

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "target", "size"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"files extracted : {stats['files']}",
          f"textures carved : {stats['wad_alltex']}",
          f"sounds carved   : {stats['wad_allsounds']}",
          "", "families by output suffix:"]
for suffix, count in sorted(Counter(Path(r["target"]).suffix.lower() for r in rows).items()):
    report.append(f"  {suffix or '(none)'}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
