#!/usr/bin/env python3
"""Survey all atlas descriptors for magic, texture paths and frame counts."""
import struct
from collections import Counter
from pathlib import Path

BASE = Path("/run/media/eddyr/external/heroic/Dead Cells/game/_extracted/raw")
files = [p for p in BASE.rglob("*") if p.is_file() and p.suffix.lower() in (".atlas", ".satlas")]
print("atlas files", len(files))
magic = Counter()
missing = []
dupes = []
bad_parse = []
counts = Counter()
for p in files:
    d = p.read_bytes()
    magic[d[:4]] += 1
    if d[:4] != b"BATL":
        continue
    pos = 4
    n = d[pos]
    pos += 1
    tex = d[pos:pos + n].decode(errors="replace")
    pos += n
    candidate = p.parent / tex
    if not candidate.exists():
        missing.append((str(p.relative_to(BASE)), tex))
    names = []
    try:
        while pos < len(d):
            n = d[pos]
            pos += 1
            if n == 0:
                break
            name = d[pos:pos + n].decode(errors="replace")
            pos += n
            struct.unpack_from("<9H", d, pos)
            pos += 18
            names.append(name)
        counts[len(names)] += 1
        repeated = [k for k, v in Counter(names).items() if v > 1]
        if repeated:
            dupes.append((str(p.relative_to(BASE)), len(repeated)))
    except Exception as exc:
        bad_parse.append((str(p.relative_to(BASE)), str(exc)))
print("magic", magic)
print("frame count buckets", counts.most_common(10))
print("missing textures", len(missing), missing[:10])
print("atlases with duplicate names", len(dupes), dupes[:10])
print("parse failures", len(bad_parse), bad_parse[:10])