#!/usr/bin/env python3
"""Decode Iconoclasts Assets.dat into numbered assets, audio and shaders.

The tool packages loose assets, then walks the indexed archive to carve and
decode every embedded asset. All output lands in a sibling directory; the
repository itself receives tools only.
"""
import csv
import shutil
import struct
import zlib
from collections import Counter
from pathlib import Path

GAME = Path("/run/media/eddyr/external/heroic/Iconoclasts/game")
OUT = GAME.parent / "_extracted"
DATA = OUT / "data"
ASSETS = OUT / "assets"
AUDIO = OUT / "audio"
SHADERS = OUT / "shaders"
RAW = OUT / "raw"
BLOB = GAME / "Assets.dat"

INDEX_START = 25504
INDEX_END = 143266
INDEX_RECORDS = 29440
DATA_START = 143266
DATA_END = 105012199
GLSL_TAIL_START = 104895421
GLSL_TAIL_RECORDS = 190
TARGET_CHUNKS = 15772
OGG_SENTINEL = 1


def read_index(blob):
    records = []
    off = INDEX_START
    for _ in range(INDEX_RECORDS):
        seg, counter = struct.unpack_from("<HH", blob, off)
        records.append((seg, counter))
        off += 4
    return records


def candidate_lengths(records):
    delta = [(records[i + 1][1] - records[i][1]) & 0xFFFF
             for i in range(len(records) - 1)]
    yield "counter-delta", delta
    yield "segment-word", [seg for seg, _ in records]


def carve(lengths):
    cursor = DATA_START
    spans = []
    for length in lengths:
        if cursor >= DATA_END:
            break
        if length <= 0:
            spans.append((cursor, 0))
            continue
        take = min(length, DATA_END - cursor)
        spans.append((cursor, take))
        cursor += take
    return spans, cursor


def choose_carve(records):
    best = None
    for name, lengths in candidate_lengths(records):
        spans, cursor = carve(lengths)
        score = (cursor < DATA_END, abs(len(spans) - TARGET_CHUNKS))
        if best is None or score < best[0]:
            best = (score, name, spans, cursor)
    return best[1], best[2], best[3]


def try_image(data):
    """Find a zlib image blob anywhere inside a carved chunk."""
    pos = 0
    while True:
        stream = data.find(b"\x78\x01", pos)
        if stream < 0:
            return None
        for extra in (0, 4, 8, 12):
            header = 13 + extra
            head = stream - header
            if head < 0:
                continue
            width, height = struct.unpack_from("<HH", data, head)
            csize = struct.unpack_from("<I", data, head + 9 + extra)[0]
            if csize <= 0 or head + header + csize > len(data):
                continue
            try:
                raw = zlib.decompress(
                    data[head + header:head + header + csize])
            except zlib.error:
                continue
            if width and height and width * height * 4 == len(raw):
                return width, height, raw
        pos = stream + 2


def write_png(path, width, height, rgba):
    def pack(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))
    scan = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4]
                    for y in range(height))
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + pack(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
        + pack(b"IDAT", zlib.compress(scan, 6))
        + pack(b"IEND", b""))


def ogg_streams(blob):
    found = []
    pos = DATA_START
    while True:
        start = blob.find(b"OggS", pos, DATA_END)
        if start < 0:
            break
        serial = struct.unpack_from("<I", blob, start + 14)[0]
        end = start
        while end < DATA_END and blob[end:end + 4] == b"OggS":
            page_segments = blob[end + 26]
            body = sum(blob[end + 27:end + 27 + page_segments])
            end += 27 + page_segments + body
            if blob[end - 27] & 0x04:
                break
        found.append((serial, start, end))
        pos = max(end, start + 4)
    return found


def shader_records(blob):
    tail = blob[GLSL_TAIL_START:DATA_END]
    records = []
    pos = 0
    while pos + 4 <= len(tail):
        size = struct.unpack_from("<I", tail, pos)[0]
        if size == 0 or pos + 4 + size > len(tail):
            break
        records.append(tail[pos + 4:pos + 4 + size])
        pos += 4 + size
    if len(records) == GLSL_TAIL_RECORDS and pos == len(tail):
        return records
    parts = [part for part in tail.split(b"\x00") if part.strip()]
    if len(parts) >= GLSL_TAIL_RECORDS:
        return parts[:GLSL_TAIL_RECORDS]
    return [b"#version" + part for part in tail.split(b"#version")
            if part.strip()][:GLSL_TAIL_RECORDS]


def main():
    shutil.rmtree(OUT, ignore_errors=True)
    for folder in (DATA, ASSETS, AUDIO, SHADERS, RAW):
        folder.mkdir(parents=True, exist_ok=True)

    stats = Counter()
    rows = []

    def record(source, target, size, kind):
        target.parent.mkdir(parents=True, exist_ok=True)
        rows.append({"source": source, "kind": kind, "size": size,
                     "output": str(target.relative_to(OUT))})
        stats[kind] += 1
        stats["bytes"] += size

    for src in sorted((GAME / "data").rglob("*")):
        if src.is_file():
            target = DATA / src.relative_to(GAME / "data")
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, target)
            record(str(src.relative_to(GAME)), target, src.stat().st_size, "loose")

    for name in ("lang.cfg", "gamecontrollerdb.txt", "icon.bmp"):
        src = GAME / name
        if src.is_file():
            target = OUT / name
            shutil.copy2(src, target)
            record(name, target, src.stat().st_size, "loose")

    strategy = "n/a"
    if BLOB.is_file():
        blob = BLOB.read_bytes()
        index = read_index(blob)
        stats["index_records"] = len(index)
        strategy, spans, cursor = choose_carve(index)
        stats["carve_complete"] = int(cursor >= DATA_END)
        stats["last_chunk"] = spans[-1][1] if spans else 0

        ordinal = 0
        for start, size in spans:
            chunk = blob[start:start + size]
            image = try_image(chunk)
            if image is not None:
                width, height, rgba = image
                target = ASSETS / f"asset_{ordinal:05d}.png"
                write_png(target, width, height, rgba)
                record(f"index:{start}", target, len(rgba), "image")
            else:
                suffix = "ogg" if chunk[:4] == b"OggS" else "raw"
                target = RAW / f"asset_{ordinal:05d}.{suffix}"
                target.write_bytes(chunk)
                record(f"index:{start}", target, len(chunk), suffix)
            ordinal += 1
        stats["carved"] = ordinal

        streams = ogg_streams(blob)
        if streams:
            audio = b"".join(blob[start:end] for _, start, end in streams)
            target = AUDIO / f"asset_S{OGG_SENTINEL:05d}.ogg"
            target.write_bytes(audio)
            record("ogg:" + ",".join(str(s) for s, _, _ in streams),
                   target, len(audio), "audio")

        seq = OGG_SENTINEL + 1
        for shader in shader_records(blob):
            target = SHADERS / f"asset_S{seq:05d}.glsl"
            target.write_bytes(shader)
            record("glsl-tail", target, len(shader), "shader")
            seq += 1

    with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["source", "kind", "size", "output"])
        writer.writeheader()
        writer.writerows(rows)

    report = [
        f"index records   : {stats['index_records']}",
        f"carve strategy  : {strategy}",
        f"carve complete  : {bool(stats['carve_complete'])}",
        f"last chunk      : {stats['last_chunk']}",
        f"chunks carved   : {stats['carved']}",
        f"images decoded  : {stats['image']}",
        f"audio streams   : {stats['audio']}",
        f"shaders decoded : {stats['shader']}",
        f"loose files     : {stats['loose']}",
        f"total bytes     : {stats['bytes']}",
    ]
    (OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
    print("\n".join(report), flush=True)
    print("OUTPUT:", OUT, flush=True)


if __name__ == "__main__":
    main()
