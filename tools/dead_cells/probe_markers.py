#!/usr/bin/env python3
"""Probe BTMX marker object records."""
import struct
from pathlib import Path

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted/raw/tiled")


def parse(data):
    pos = data.find(b"markers")
    if pos < 0:
        return None
    pos += len(b"markers") + 23
    count = struct.unpack_from("<H", data, pos)[0]
    pos += 6
    records = []
    for _ in range(count):
        n = data[pos]
        pos += 1
        name = data[pos:pos + n].decode(errors="replace")
        pos += n
        prop_count = struct.unpack_from("<H", data, pos)[0]
        pos += 2
        props = {}
        for _ in range(prop_count):
            klen = data[pos]
            pos += 1
            key = data[pos:pos + klen].decode(errors="replace")
            pos += klen
            vlen = data[pos]
            pos += 1
            value = data[pos:pos + vlen].decode(errors="replace")
            pos += vlen
            props[key] = value
        type_len = data[pos]
        pos += 1
        marker_type = data[pos:pos + type_len].decode(errors="replace")
        pos += type_len
        flags = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        floats = struct.unpack_from("<4f", data, pos)
        pos += 16
        pos += 8
        marker_id = struct.unpack_from("<I", data, pos)[0]
        pos += 4
        records.append({"name": name, "type": marker_type, "props": props,
                        "flags": flags, "floats": floats, "id": marker_id})
    return records


for path in sorted(BASE.rglob("*.tmx"))[:8]:
    records = parse(path.read_bytes())
    print("===", path.name, "records", len(records) if records else 0)
    for record in (records or [])[:3]:
        print("  ", record)
