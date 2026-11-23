#!/usr/bin/env python3
import UnityPy
from pathlib import Path
from collections import Counter

B = Path("/run/media/eddyr/external/heroic/Banners of Ruin/BannersOfRuin_Data/StreamingAssets/AssetBundles/WindowsPlayer")
bundles = [p for p in B.rglob("*") if p.is_file() and p.open("rb").read(8) == b"UnityFS\x00"]
formats = Counter()
img_ok = Counter()
for p in bundles:
    env = UnityPy.load(str(p))
    for obj in env.objects:
        if obj.type.name != "Texture2D":
            continue
        try:
            d = obj.read()
            f = int(d.m_TextureFormat)
            formats[f] += 1
            img_ok[(f, bool(d.image))] += 1
        except Exception:
            formats[-1] += 1
print("texture formats:", formats.most_common())
print("image availability:", img_ok.most_common())
