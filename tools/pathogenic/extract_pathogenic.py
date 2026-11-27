#!/usr/bin/env python3
"""Extract every file from a Godot 4 PCK into a sibling output directory."""
import csv
import hashlib
import shutil
import struct
from collections import Counter
from pathlib import Path

ROOT = Path("/run/media/eddyr/external/sandbox-games/Pathogenic_SteamRIP.com")
GAME = ROOT / "Pathogenic"
BLOB = GAME / "pathogenic.pck"
OUT = ROOT / "_extracted"
CHUNK = 4 * 1024 * 1024


def read_header(handle):
    head = handle.read(104)
    magic, version, major, minor, patch, flags = struct.unpack_from("<6I", head, 0)
    file_base, directory = struct.unpack_from("<QQ", head, 24)
    if magic != 0x43504447:
        raise SystemExit("bad PCK magic")
    if version != 4:
        raise SystemExit(f"unsupported PCK version {version}")
    return {
        "version": version,
        "engine": f"{major}.{minor}.{patch}",
        "flags": flags,
        "file_base": file_base,
        "directory": directory,
    }


def read_entries(handle, header):
    handle.seek(header["directory"])
    count = struct.unpack("<I", handle.read(4))[0]
    for _ in range(count):
        length = struct.unpack("<I", handle.read(4))[0]
        raw = handle.read(length)
        if len(raw) != length:
            raise SystemExit("truncated path in PCK directory")
        offset, size = struct.unpack("<QQ", handle.read(16))
        digest = handle.read(16)
        flags = struct.unpack("<I", handle.read(4))[0]
        name = raw.split(b"\0", 1)[0].decode("utf-8")
        if name.startswith("res://"):
            name = name[6:]
        yield {
            "path": name,
            "offset": header["file_base"] + offset,
            "size": size,
            "md5": digest.hex(),
            "flags": flags,
        }


def safe_target(name):
    parts = Path(name).parts
    if not parts or any(p in ("", ".", "..") for p in parts):
        raise SystemExit(f"unsafe PCK path: {name}")
    target = OUT.joinpath(*parts)
    if not target.resolve().is_relative_to(OUT.resolve()):
        raise SystemExit(f"PCK path escapes output: {name}")
    return target


def extract():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    rows = []
    with BLOB.open("rb") as handle:
        header = read_header(handle)
        entries = list(read_entries(handle, header))
        for entry in entries:
            target = safe_target(entry["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            handle.seek(entry["offset"])
            hasher = hashlib.md5()
            remaining = entry["size"]
            with target.open("wb") as out:
                while remaining:
                    block = handle.read(min(CHUNK, remaining))
                    if not block:
                        raise SystemExit(f"short read for {entry['path']}")
                    out.write(block)
                    hasher.update(block)
                    remaining -= len(block)
            verified = hasher.hexdigest() == entry["md5"]
            stats["files"] += 1
            stats["bytes"] += entry["size"]
            stats[f"flag_{entry['flags']}"] += 1
            stats[f"ext_{Path(entry['path']).suffix.lower() or '(none)'}"] += 1
            stats["md5_ok" if verified else "md5_bad"] += 1
            rows.append({
                "path": entry["path"],
                "offset": entry["offset"],
                "size": entry["size"],
                "ext": Path(entry["path"]).suffix.lower(),
                "flags": entry["flags"],
                "md5": entry["md5"],
                "verified": verified,
            })
    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = [
        f"pck               : {BLOB}",
        f"engine            : {header['engine']}",
        f"pack flags        : {header['flags']}",
        f"files extracted   : {stats['files']}",
        f"bytes extracted   : {stats['bytes']}",
        f"md5 verified      : {stats['md5_ok']}",
        f"md5 mismatched    : {stats['md5_bad']}",
        "families:",
    ]
    for key, count in sorted(stats.items()):
        if key.startswith("ext_"):
            report.append(f"  {key[4:]}: {count}")
    (OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report), flush=True)
    print("OUTPUT:", OUT, flush=True)


if __name__ == "__main__":
    extract()
