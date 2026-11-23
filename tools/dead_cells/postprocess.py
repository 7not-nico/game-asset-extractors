#!/usr/bin/env python3
"""Decode Dead Cells gameplay data and split BATL atlases into frame images."""
import argparse
import csv
import json
import re
import struct
from collections import Counter
from pathlib import Path

from PIL import Image

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted")
RAW = BASE / "raw"
DATA = BASE / "data"
FRAMES = BASE / "atlas_frames"


def safe_name(value):
    return re.sub(r'[<>:"|?*\\/]', "_", str(value)).strip() or "unnamed"


def decode_cdb():
    DATA.mkdir(parents=True, exist_ok=True)
    source = RAW / "data.cdb"
    doc = json.loads(source.read_text(encoding="utf-8"))
    if doc.get("compress"):
        raise SystemExit("data.cdb is compressed; no decoder available")
    (DATA / "data.cdb.json").write_text(
        json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")
    sheets_dir = DATA / "sheets"
    sheets_dir.mkdir(parents=True, exist_ok=True)
    names = []
    for sheet in doc.get("sheets", []):
        name = safe_name(sheet.get("name"))
        names.append(name)
        (sheets_dir / f"{name}.json").write_text(
            json.dumps(sheet, indent=2, ensure_ascii=False), encoding="utf-8")
        columns = [c.get("name", "") for c in sheet.get("columns", [])]
        with (sheets_dir / f"{name}.csv").open("w", newline="", encoding="utf-8") as fh:
            writer = csv.writer(fh)
            writer.writerow(columns)
            for line in sheet.get("lines", []):
                writer.writerow([line.get(column, "") for column in columns])
    print(f"cdb: format={doc.get('format')} sheets={len(names)}")
    return len(names)


def parse_batl(data):
    if data[:4] != b"BATL":
        return None
    pos = 4
    n = data[pos]
    pos += 1
    texture = data[pos:pos + n].decode(errors="replace")
    pos += n
    frames = []
    while pos < len(data):
        n = data[pos]
        pos += 1
        if n == 0:
            break
        name = data[pos:pos + n].decode(errors="replace")
        pos += n
        values = struct.unpack_from("<9H", data, pos)
        pos += 18
        frames.append((name, values))
    return texture, frames


def split_atlases():
    atlases = [p for p in RAW.rglob("*")
               if p.is_file() and p.suffix.lower() in (".atlas", ".satlas")]
    stats = Counter()
    errors = []
    for atlas in atlases:
        data = atlas.read_bytes()
        parsed = parse_batl(data)
        if parsed is None:
            stats["skipped_non_batl"] += 1
            continue
        texture_name, frames = parsed
        texture_path = atlas.parent / texture_name
        if not texture_path.exists():
            errors.append(f"missing texture: {atlas} -> {texture_name}")
            continue
        rel = atlas.relative_to(RAW)
        out_dir = FRAMES / rel.parent / atlas.stem
        out_dir.mkdir(parents=True, exist_ok=True)
        seen = Counter()
        with Image.open(texture_path) as image:
            for name, values in frames:
                flag, x, y, w, h, dx, dy, orig_w, orig_h = values
                seen[name] += 1
                suffix = "" if seen[name] == 1 else f"__{seen[name]}"
                target = out_dir / f"{safe_name(name)}{suffix}.png"
                try:
                    image.crop((x, y, x + w, y + h)).save(target)
                    stats["frames"] += 1
                except Exception as exc:
                    errors.append(f"crop {rel}:{name}: {type(exc).__name__}: {exc}")
        stats["atlases"] += 1
    report = []
    report.append(f"atlases processed   : {stats['atlases']}")
    report.append(f"non-BATL skipped    : {stats['skipped_non_batl']}")
    report.append(f"frames written      : {stats['frames']}")
    report.append(f"errors              : {len(errors)}")
    if errors:
        report.append("")
        report.append("first 40 errors:")
        report.extend(f"  {e}" for e in errors[:40])
    (BASE / "postprocess_report.txt").write_text(
        "\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--cdb-only", action="store_true")
    parser.add_argument("--atlas-only", action="store_true")
    args = parser.parse_args()
    if not args.atlas_only:
        decode_cdb()
    if not args.cdb_only:
        split_atlases()
    print("OUTPUT:", BASE, flush=True)


if __name__ == "__main__":
    main()
