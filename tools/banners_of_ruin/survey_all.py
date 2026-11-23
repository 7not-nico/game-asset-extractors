#!/usr/bin/env python3
"""Survey all bundles: type histogram, container-name samples, load failures."""
import UnityPy
from pathlib import Path
from collections import Counter

ROOT = Path("/run/media/eddyr/external/heroic/Banners of Ruin/BannersOfRuin_Data/StreamingAssets/AssetBundles/WindowsPlayer")
bundles = [p for p in ROOT.rglob("*") if p.is_file() and p.open("rb").read(8) == b"UnityFS\x00"]

types = Counter()
samples = {}
failures = []
container_total = 0
for i, p in enumerate(bundles):
    try:
        env = UnityPy.load(str(p))
    except Exception as e:
        failures.append((str(p.relative_to(ROOT)), f"load: {type(e).__name__}: {e}"))
        continue
    for obj in env.objects:
        t = obj.type.name
        types[t] += 1
        if t not in samples and obj.container:
            samples[t] = (str(p.relative_to(ROOT)), obj.container)
        container_total += 1 if obj.container else 0

print(f"bundles scanned: {len(bundles)}")
print(f"objects total: {sum(types.values())}")
print(f"objects with container paths: {container_total}")
print(f"load failures: {len(failures)}")
for f in failures[:20]:
    print("   ", f)
print("\ntype histogram:")
for t, c in types.most_common():
    print(f"  {t}: {c}")
print("\ncontainer samples:")
for t, (p, c) in samples.items():
    print(f"  {t}: {p} :: {c}")
