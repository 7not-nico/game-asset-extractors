#!/usr/bin/env python3
"""Extract loose files, GameMaker chunks, audio streams and texture blobs."""
import bz2
import csv
import shutil
import struct
from collections import Counter
from pathlib import Path

ROOT = Path("/run/media/eddyr/external/sandbox-games/The-Slormancer-SteamRIP.com")
GAME = ROOT / "The Slormancer"
OUT = ROOT / "_extracted"
WIN = GAME / "data.win"
AGROUP = GAME / "audiogroup1.dat"
YYTEX = GAME / "Textures_Fonts_0.yytex"
LOOSE_EXT = {".json", ".ttf", ".ini", ".txt"}


def emit(rows, stats, rel, source, kind, payload):
    target = OUT / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        target.write_bytes(payload)
    else:
        shutil.copy2(payload, target)
    size = target.stat().st_size
    stats["files"] += 1
    stats[kind] += 1
    stats["bytes"] += size
    rows.append({"output": rel, "source": source, "kind": kind, "size": size})


def chunks(blob):
    """Yield (name, payload_start, payload_size) for each FORM child."""
    if blob[:4] != b"FORM":
        raise SystemExit("data.win does not open with FORM")
    off = 8
    while off + 8 <= len(blob):
        name = blob[off:off + 4].decode("latin1")
        size = struct.unpack_from("<I", blob, off + 4)[0]
        if off + 8 + size > len(blob):
            break
        yield name, off + 8, size
        off += 8 + size + (size & 1)


def audio_entries(blob, count_at, offsets_at, label, rows, stats):
    count = struct.unpack_from("<I", blob, count_at)[0]
    offsets = [struct.unpack_from("<I", blob, offsets_at + 4 * i)[0]
               for i in range(count)]
    for index, start in enumerate(offsets):
        if start + 4 > len(blob):
            continue
        length = struct.unpack_from("<I", blob, start)[0]
        data = blob[start + 4:start + 4 + length]
        if not data:
            continue
        ext = "wav" if data[:4] == b"RIFF" else "ogg" if data[:4] == b"OggS" else "bin"
        emit(rows, stats, f"audio/{label}/{index:04d}.{ext}",
             f"{label}:{start}", "audio", data)


def texture_entries(blob, start, size, rows, stats):
    count = struct.unpack_from("<I", blob, start)[0]
    records = []
    for i in range(count):
        pos = start + 4 + 4 * i
        record = struct.unpack_from("<I", blob, pos)[0]
        if record + 28 > len(blob):
            continue
        width, height = struct.unpack_from("<II", blob, record + 12)
        data_at = struct.unpack_from("<I", blob, record + 24)[0]
        records.append((data_at, width, height, record))
    records.sort()
    for index, (data_at, width, height, record) in enumerate(records):
        stop = records[index + 1][0] if index + 1 < len(records) else start + size
        if data_at >= stop or stop > len(blob):
            continue
        emit(rows, stats, f"textures/txtr/{index:04d}_{width}x{height}.bin",
             f"TXTR:{record}", "texture", blob[data_at:stop])


def main():
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True, exist_ok=True)
    stats = Counter()
    rows = []

    for src in sorted(GAME.rglob("*")):
        if src.is_file() and src.suffix.lower() in LOOSE_EXT:
            emit(rows, stats, str(src.relative_to(GAME)), str(src), "loose", src)

    blob = WIN.read_bytes()
    for name, start, size in chunks(blob):
        emit(rows, stats, f"data_win/chunks/{name}_{start}.chunk",
             f"data.win:{start}", "chunk", blob[start:start + size])
        if name == "AUDO":
            audio_entries(blob, start, start + 4, "datawin", rows, stats)
        if name == "TXTR":
            texture_entries(blob, start, size, rows, stats)

    agroup = AGROUP.read_bytes()
    audio_entries(agroup, 16, 20, "audiogroup1", rows, stats)

    packed = YYTEX.read_bytes()
    raw = bz2.decompress(packed[12:])
    emit(rows, stats, "textures/Textures_Fonts_0.fioq", str(YYTEX), "fioq", raw)

    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["output", "source", "kind", "size"])
        writer.writeheader()
        writer.writerows(rows)
    report = ["files extracted : %d" % stats["files"],
              "bytes extracted : %d" % stats["bytes"], ""]
    for kind in sorted(k for k in stats if not k.startswith("bytes") and k != "files"):
        report.append(f"  {kind}: {stats[kind]}")
    (OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report), flush=True)
    print("OUTPUT:", OUT, flush=True)


if __name__ == "__main__":
    main()
