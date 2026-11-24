#!/usr/bin/env python3
"""Extract Planescape Torment Enhanced Edition KEY/BIF resources and loose assets."""
import csv
import re
import shutil
import struct
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/heroic/Planescape Torment - Enhanced Edition/game")
OUT = GAME.parent / "_extracted"
RES = OUT / "resources"
LOOSE = OUT / "loose"

if OUT.exists():
    shutil.rmtree(OUT)
RES.mkdir(parents=True, exist_ok=True)
LOOSE.mkdir(parents=True, exist_ok=True)

stats = Counter()
errors = []
rows = []
written = {}

LOOSE_EXT = {".wbm", ".mve", ".ogg", ".wav", ".acm", ".tlk", ".pvrz", ".bam",
             ".mos", ".chu", ".are", ".itm", ".spl", ".cre", ".2da", ".ids",
             ".txt", ".lua", ".ini", ".json", ".xml", ".fnt", ".ttf", ".otf",
             ".jpg", ".jpeg", ".png", ".bmp"}
EXCLUDED_DIRS = {"_extract_tool", "_research-of-engine", "_extracted"}


def safe(name):
    return re.sub(r'[<>:"|?*\\/]', "_", name).strip() or "unnamed"


def ext_for(data, rtype):
    head = data[:8]
    if head.startswith(b"\x89PNG"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if head.startswith(b"RIFF") and data[8:12] == b"WAVE":
        return "wav"
    if head.startswith(b"RIFF"):
        return "riff"
    if head.startswith(b"OggS"):
        return "ogg"
    if head.startswith(b"BM"):
        return "bmp"
    if head.startswith(b"WAVCV1.0"):
        return "wavc"
    if head.startswith(b"CHUIV1") or head.startswith(b"CHU "):
        return "chu"
    if head.startswith(b"\x00\x01\x00\x00"):
        return "ttf"
    if head[:4] == b"\x34\x00\x08\x00" or (head[0] == 0x34 and head[2:4] == b"\x08\x00"):
        return "mosz"
    if head.startswith(b"BAM "):
        return "bam"
    if head.startswith(b"WED "):
        return "wed"
    if head.startswith(b"CHU "):
        return "chu"
    if head.startswith(b"TLK "):
        return "tlk"
    if head.startswith(b"ARE"):
        return "are"
    if head.startswith(b"ITM"):
        return "itm"
    if head.startswith(b"SPL"):
        return "spl"
    if head.startswith(b"CRE"):
        return "cre"
    if head.startswith(b"2DA"):
        return "2da"
    if head.startswith(b"IDS "):
        return "ids"
    if head.startswith(b"PVRZ") or head.startswith(b"PVR"):
        return "pvrz"
    if head[:4] == b"MOS ":
        return "mos"
    if head.startswith(b"DLG V1.0"):
        return "dlg"
    if head.startswith(b"PRO V1.0"):
        return "pro"
    if head.startswith(b"\x1a\x45\xdf\xa3"):
        return "wbm"
    if head.startswith(b"SC\n"):
        return "sc"
    return f"t{rtype}"


def claim(path):
    if path not in written:
        written[path] = 1
        return path
    n = written[path] + 1
    written[path] = n
    return path.with_name(f"{path.stem}__dup{n}{path.suffix}")


print("[1/4] parsing chitin.key", flush=True)
key = (GAME / "chitin.key").read_bytes()
_, _, bif_count, res_count, bif_off, res_off = struct.unpack_from("<4s4sIIII", key, 0)
bifs = []
for i in range(bif_count):
    length, name_off, name_len, loc = struct.unpack_from("<IIHH", key, bif_off + i * 12)
    name = key[name_off:name_off + name_len].split(b"\x00", 1)[0].decode("latin-1")
    bifs.append((name, length))
resources = []
for i in range(res_count):
    off = res_off + i * 14
    name = key[off:off + 8].split(b"\x00", 1)[0].decode("latin-1")
    rtype, locator = struct.unpack_from("<HI", key, off + 8)
    resources.append((name, rtype, locator >> 20, locator & 0xFFFFF))

print("[2/4] indexing BIFF entries", flush=True)
bif_entries = {}
for bif_index, (name, _) in enumerate(bifs):
    path = GAME / name
    if not path.exists():
        errors.append(f"missing BIF: {name}")
        continue
    blob = path.read_bytes()
    if blob[:8] != b"BIFFV1  ":
        errors.append(f"bad BIF magic: {name}")
        continue
    file_count, tile_count, entries_off = struct.unpack_from("<III", blob, 8)
    entries = {}
    tile_off = entries_off + file_count * 16
    for i in range(tile_count):
        locator, offset, size, count, rtype = struct.unpack_from("<IIHHH", blob, tile_off + i * 20)
        entries[locator] = (offset, size, rtype)
    for i in range(file_count):
        locator, offset, size, unknown, rtype = struct.unpack_from("<IIHHH", blob, entries_off + i * 16)
        entries[locator] = (offset, size, rtype)
    bif_entries[bif_index] = (path, entries)
    stats["bifs"] += 1
    stats["bif_file_entries"] += file_count

print("[3/4] carving resources", flush=True)
handles = {}
for name, rtype, bif_index, res_index in resources:
    entry = bif_entries.get(bif_index)
    if entry is None:
        errors.append(f"no BIF {bif_index} for {name}")
        continue
    path, entries = entry
    info = entries.get(res_index)
    if info is None:
        errors.append(f"no entry {res_index} in {path.name} for {name}")
        continue
    offset, size, bif_type = info
    handle = handles.get(bif_index)
    if handle is None:
        handle = path.open("rb")
        handles[bif_index] = handle
    handle.seek(offset)
    data = handle.read(size)
    if len(data) != size:
        errors.append(f"short read {name} from {path.name}")
        continue
    suffix = ext_for(data, rtype)
    target = claim(RES / f"t{rtype}" / f"{safe(name)}.{suffix}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    stats["resources"] += 1
    stats["bytes"] += size
    stats[f"ext_{suffix}"] += 1
    rows.append({"source": f"{path.name}:{res_index}", "name": name,
                 "type": rtype, "size": size, "output": str(target.relative_to(OUT))})

for handle in handles.values():
    handle.close()

print("[4/4] copying loose assets", flush=True)
for src in sorted(GAME.rglob("*")):
    if not src.is_file():
        continue
    rel = src.relative_to(GAME)
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        continue
    if src.suffix.lower() not in LOOSE_EXT:
        continue
    target = LOOSE / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, target)
    stats["loose"] += 1
    rows.append({"source": str(rel), "name": src.stem, "type": "loose",
                 "size": src.stat().st_size, "output": str(target.relative_to(OUT))})

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "name", "type", "size", "output"])
    writer.writeheader()
    writer.writerows(rows)

report = [f"bifs indexed        : {stats['bifs']}",
          f"bif file entries    : {stats['bif_file_entries']}",
          f"resources carved    : {stats['resources']}",
          f"bytes carved        : {stats['bytes']}",
          f"loose files copied  : {stats['loose']}",
          f"errors              : {len(errors)}",
          "", "extension families:"]
for key_name, count in sorted(stats.items()):
    if key_name.startswith("ext_"):
        report.append(f"  {key_name[4:]}: {count}")
if errors:
    report.append("")
    report.append("first 40 errors:")
    report.extend(f"  {e}" for e in errors[:40])
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report[:6]), flush=True)
print("OUTPUT:", OUT, flush=True)
