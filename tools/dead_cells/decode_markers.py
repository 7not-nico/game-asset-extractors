#!/usr/bin/env python3
"""Extract BTMX marker object names and properties with tolerant record sync."""
import json
import re
import struct
from collections import Counter
from pathlib import Path

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted")
TILED = BASE / "raw/tiled"
OUT = BASE / "markers"


def printable(raw):
    return bool(raw) and all(32 <= c < 127 for c in raw)


def sync_next(data, pos):
    for i in range(pos, min(len(data), pos + 48)):
        n = data[i]
        if 3 <= n <= 40 and i + 1 + n <= len(data):
            if printable(data[i + 1:i + 1 + n]):
                return i
    return None


def parse(data):
    start = data.find(b"markers")
    if start < 0:
        return []
    pos = start + len(b"markers") + 23
    count = struct.unpack_from("<H", data, pos)[0]
    pos += 6
    records = []
    for _ in range(count):
        if pos >= len(data):
            break
        name_len = data[pos]
        pos += 1
        name = data[pos:pos + name_len].decode("ascii", errors="replace")
        pos += name_len
        prop_count = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        props = {}
        for _ in range(prop_count):
            klen = data[pos]
            pos += 1
            key = data[pos:pos + klen].decode("ascii", errors="replace")
            pos += klen
            vlen = data[pos]
            pos += 1
            value = data[pos:pos + vlen].decode("ascii", errors="replace")
            pos += vlen
            props[key] = value
        type_len = data[pos]
        pos += 1
        marker_type = data[pos:pos + type_len].decode("ascii", errors="replace")
        pos += type_len
        flags = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        floats = struct.unpack_from("<4f", data, pos)
        pos += 16
        records.append({"name": name, "type": marker_type, "props": props,
                        "flags": flags, "pos": [round(v, 2) for v in floats]})
        nxt = sync_next(data, pos)
        if nxt is None:
            break
        pos = nxt
    return records


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    maps = sorted(TILED.rglob("*.tmx"))
    stats = Counter()
    types = Counter()
    props = Counter()
    for path in maps:
        try:
            records = parse(path.read_bytes())
        except Exception:
            stats["errors"] += 1
            continue
        if not records:
            stats["empty"] += 1
            continue
        target = OUT / f"{path.stem}.json"
        target.write_text(json.dumps(records, indent=2, ensure_ascii=False),
                          encoding="utf-8")
        stats["maps"] += 1
        stats["markers"] += len(records)
        for r in records:
            types[r["type"]] += 1
            props.update(r["props"].keys())
    summary = {"maps": stats["maps"], "markers": stats["markers"],
               "errors": stats["errors"], "empty": stats["empty"],
               "top_types": types.most_common(30),
               "top_properties": props.most_common(30)}
    (BASE / "markers_report.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
