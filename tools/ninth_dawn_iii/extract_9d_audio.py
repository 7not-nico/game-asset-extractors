#!/usr/bin/env python3
"""Decode all streamed AudioClips from 9th Dawn III in a dedicated pass."""
import json
import shutil
from collections import Counter
from pathlib import Path

import UnityPy
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

GAME = Path("/run/media/eddyr/external/heroic/9th Dawn III/game/GameBin/9thDawnIII_Data")
OUT = Path("/run/media/eddyr/external/heroic/9th Dawn III/game/_extracted")
AUDIO = OUT / "audio"
if AUDIO.exists():
    shutil.rmtree(AUDIO)
AUDIO.mkdir(parents=True, exist_ok=True)

TTG = TypeTreeGenerator("2022.3.62f2")
TTG.load_local_game(str(GAME.parent))
env = UnityPy.load(str(GAME / "resources.assets"))
env.typetree_generator = TTG

index = []
errors = []
written = {}
stats = Counter()

for obj in env.objects:
    if obj.type.name != "AudioClip":
        continue
    stats["clips"] += 1
    try:
        d = obj.read()
    except Exception as exc:
        errors.append(f"read {obj.path_id}: {type(exc).__name__}: {exc}")
        continue
    name = getattr(d, "m_Name", None) or f"clip_{obj.path_id}"
    resource = getattr(d, "m_Resource", None)
    try:
        samples = d.samples or {}
    except Exception as exc:
        errors.append(f"decode {name}: {type(exc).__name__}: {exc}")
        continue
    if not samples:
        errors.append(f"decode {name}: empty samples")
        continue
    for wav_name, payload in samples.items():
        target = AUDIO / Path(wav_name).name
        if target in written:
            target = target.with_name(f"{target.stem}__dup{written[target]}{target.suffix}")
        written[target] = written.get(target, 0) + 1
        target.write_bytes(bytes(payload))
        stats["wav"] += 1
        index.append({
            "name": name,
            "container": str(obj.container) if obj.container else None,
            "source_file": getattr(resource, "m_Source", None),
            "offset": getattr(resource, "m_Offset", None),
            "size": getattr(resource, "m_Size", None),
            "output": str(target.relative_to(OUT)),
        })
    stats["decoded"] += 1

(OUT / "audio_index.json").write_text(
    json.dumps({"clips": stats["clips"], "decoded": stats["decoded"],
                "wav_files": stats["wav"], "errors": errors, "audio": index},
               indent=2, ensure_ascii=False), encoding="utf-8")

print(f"clips={stats['clips']} decoded={stats['decoded']} wav={stats['wav']} errors={len(errors)}")
for e in errors[:10]:
    print("  ", e)
