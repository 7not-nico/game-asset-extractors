#!/usr/bin/env python3
"""Extract asset files from the Slay the Spire desktop JAR."""
import csv
import shutil
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path("/run/media/eddyr/external/sandbox-games/Slay-the-Spire-SteamRIP.com/Slay the Spire v2.3.4")
JAR = ROOT / "desktop-1.0.jar"
OUT = ROOT / "_extracted"
ASSETS = OUT / "assets"

PREFIXES = ("images/", "audio/", "localization/", "font/", "shaders/", "cityScene/")
ROOT_FILES = {
    "default.fnt", "default.png", "defaultTemplate.pfx", "monkey.g3db",
    "particle.png", "pre_particle.png", "splash.jpg", "uiskin.atlas",
    "uiskin.json", "uiskin.png", "licence-header.txt",
}

if OUT.exists():
    shutil.rmtree(OUT)
ASSETS.mkdir(parents=True, exist_ok=True)

stats = Counter()
rows = []


def wanted(name):
    if name.endswith("/"):
        return False
    return name.startswith(PREFIXES) or name in ROOT_FILES


with zipfile.ZipFile(JAR) as jar:
    for info in jar.infolist():
        name = info.filename
        if not wanted(name):
            continue
        target = ASSETS / name
        target.parent.mkdir(parents=True, exist_ok=True)
        with jar.open(info) as source, target.open("wb") as out:
            shutil.copyfileobj(source, out)
        suffix = Path(name).suffix.lower() or "(none)"
        stats["files"] += 1
        stats["bytes"] += info.file_size
        stats[f"ext_{suffix}"] += 1
        rows.append({"name": name, "size": info.file_size,
                     "compressed": info.compress_size})

report = []
report.append(f"files extracted     : {stats['files']}")
report.append(f"bytes extracted     : {stats['bytes']}")
report.append("")
report.append("families:")
for key, count in sorted(stats.items()):
    if key.startswith("ext_"):
        report.append(f"  {key[4:]}: {count}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["name", "size", "compressed"])
    writer.writeheader()
    writer.writerows(rows)
print("\n".join(report[:6]), flush=True)
print("OUTPUT:", OUT, flush=True)
