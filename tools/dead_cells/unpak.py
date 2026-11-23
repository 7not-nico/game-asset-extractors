#!/usr/bin/env python3
"""Read and extract Dead Cells PAK v1 archives without loading them into memory.

Layout: magic/version, header size, data size, 64-byte stamp, recursive entry
tree, DATA marker, then raw file bytes addressed by entry offset.
"""
import argparse
import csv
import json
import re
import struct
import zlib
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/heroic/Dead Cells/game")
PAK = GAME / "res.pak"
OUT = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted")
RAW = OUT / "raw"
CHUNK = 1024 * 1024


def read_entry(handle, prefix, entries):
    raw_len = handle.read(1)
    if not raw_len:
        raise ValueError("unexpected end of entry stream")
    name_len = raw_len[0]
    name = handle.read(name_len).decode("ascii", errors="replace")
    flags = handle.read(1)[0]
    path = f"{prefix}/{name}" if prefix else name
    if flags & 0x01:
        count = struct.unpack("<i", handle.read(4))[0]
        for _ in range(count):
            read_entry(handle, path, entries)
        return
    if flags & 0x02:
        position = struct.unpack("<q", handle.read(8))[0]
    else:
        position = struct.unpack("<i", handle.read(4))[0]
    size = struct.unpack("<i", handle.read(4))[0]
    checksum = struct.unpack("<i", handle.read(4))[0]
    entries.append({
        "path": path,
        "offset": position,
        "size": size,
        "checksum": checksum & 0xFFFFFFFF,
        "flags": flags,
    })


def build_index(entries):
    handle = PAK.open("rb")
    header = handle.read(76)
    if header[:3] != b"PAK":
        raise ValueError("not a PAK archive")
    version = header[3]
    header_size = struct.unpack_from("<i", header, 4)[0]
    data_size = struct.unpack_from("<i", header, 8)[0]
    stamp = header[12:76].decode("ascii", errors="replace")
    root_name_len = handle.read(1)[0]
    handle.read(root_name_len)
    root_flags = handle.read(1)[0]
    if not root_flags & 0x01:
        raise ValueError("root entry is not a directory")
    child_count = struct.unpack("<i", handle.read(4))[0]
    for _ in range(child_count):
        read_entry(handle, "", entries)
    handle.close()

    meta = {
        "source": str(PAK),
        "file_size": PAK.stat().st_size,
        "version": version,
        "header_size": header_size,
        "data_size": data_size,
        "stamp": stamp,
        "root_children": child_count,
        "entry_count": len(entries),
        "total_bytes": sum(e["size"] for e in entries),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "pak_index.json").write_text(
        json.dumps({"metadata": meta, "entries": entries}, indent=2),
        encoding="utf-8")
    with (OUT / "pak_index.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["path", "offset", "size", "checksum", "flags"])
        writer.writeheader()
        writer.writerows(entries)
    print("PAK", meta["version"], "stamp", stamp)
    print("header", header_size, "data", data_size, "file", meta["file_size"])
    print("entries", meta["entry_count"], "bytes", meta["total_bytes"])
    return meta


def safe_target(path):
    parts = []
    for part in Path(path).parts:
        if part in ("", ".", ".."):
            continue
        parts.append(re.sub(r'[<>:"|?*]', "_", part))
    if not parts:
        return None
    return RAW.joinpath(*parts)


def carve(entries, header_size):
    if RAW.exists():
        import shutil
        shutil.rmtree(RAW)
    RAW.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    errors = []
    families = Counter()
    largest = []
    with PAK.open("rb") as handle:
        for i, entry in enumerate(entries, 1):
            target = safe_target(entry["path"])
            if target is None:
                errors.append(f"unsafe path: {entry['path']}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            handle.seek(header_size + entry["offset"])
            remaining = entry["size"]
            digest = 1
            with target.open("wb") as out:
                while remaining > 0:
                    chunk = handle.read(min(CHUNK, remaining))
                    if not chunk:
                        errors.append(f"short read: {entry['path']}")
                        break
                    digest = zlib.adler32(chunk, digest)
                    out.write(chunk)
                    remaining -= len(chunk)
            if digest & 0xFFFFFFFF != entry["checksum"]:
                errors.append(
                    f"checksum: {entry['path']} got {digest & 0xFFFFFFFF:08x} "
                    f"want {entry['checksum']:08x}")
                stats["checksum_fail"] += 1
            stats["files"] += 1
            stats["bytes"] += entry["size"]
            families[Path(entry["path"]).suffix.lower() or "(none)"] += 1
            largest.append((entry["size"], entry["path"]))
            if i % 500 == 0:
                print(f"    {i}/{len(entries)} files", flush=True)

    largest.sort(reverse=True)
    report = []
    report.append(f"files written         : {stats['files']}")
    report.append(f"bytes written         : {stats['bytes']}")
    report.append(f"checksum failures     : {stats['checksum_fail']}")
    report.append(f"other errors          : {len(errors) - stats['checksum_fail']}")
    report.append("")
    report.append("families by extension:")
    for suffix, count in families.most_common():
        report.append(f"  {suffix}: {count}")
    report.append("")
    report.append("largest files:")
    for size, path in largest[:20]:
        report.append(f"  {size:12d}  {path}")
    if errors:
        report.append("")
        report.append("first 40 errors:")
        for message in errors[:40]:
            report.append(f"  {message}")
    (OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report[:8]), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index-only", action="store_true",
                        help="build the index without extracting file data")
    args = parser.parse_args()
    entries = []
    meta = build_index(entries)
    if not args.index_only:
        carve(entries, meta["header_size"])
    print("OUTPUT:", OUT, flush=True)


if __name__ == "__main__":
    main()
