#!/usr/bin/env python3
"""Decode all streamed AudioClips from Sunless Skies in a dedicated pass."""
import json
import re
from collections import Counter
from pathlib import Path
import shutil

import UnityPy
import fmod_toolkit

GAME = Path("/run/media/eddyr/external/heroic/Sunless Skies/game/Sunless Skies_Data")
OUT = Path("/run/media/eddyr/external/heroic/Sunless Skies/game/_extracted")
AUDIO = OUT / "audio"
if AUDIO.exists():
    shutil.rmtree(AUDIO)
AUDIO.mkdir(parents=True, exist_ok=True)

banks = {}
index = []
errors = []
seen = Counter()


def get_bank(name):
    base = Path(name.replace("\\", "/")).name
    if base not in banks:
        path = GAME / base
        banks[base] = path.read_bytes() if path.exists() else None
    return banks[base]


targets = [src for src in sorted(GAME.iterdir())
           if src.is_file() and (src.suffix.lower() == ".assets" or
                                 re.fullmatch(r"(globalgamemanagers|level\d+)", src.name))]
targets.extend(src for src in sorted((GAME / "Resources").iterdir()) if src.is_file())

for src in targets:
    env = UnityPy.load(str(src))
    for obj in env.objects:
        if obj.type.name != "AudioClip":
            continue
        try:
            data = obj.read()
        except Exception as exc:
            errors.append(f"read {src.name}:{obj.path_id}: {type(exc).__name__}: {exc}")
            continue
        name = getattr(data, "m_Name", None) or f"clip_{obj.path_id}"
        resource = getattr(data, "m_Resource", None)
        source_name = getattr(resource, "m_Source", None) or ""
        produced = {}
        method = None
        try:
            produced = data.samples or {}
            method = "unity_samples"
        except Exception as exc:
            bank = get_bank(source_name)
            if bank is None:
                errors.append(f"{name}: missing bank {source_name}")
                continue
            try:
                produced = fmod_toolkit.raw_to_wav(
                    bank, name, data.m_Channels or 2, data.m_Frequency or 44100)
                method = "full_fsb5_bank"
            except Exception as exc2:
                errors.append(f"{name}: samples {type(exc).__name__}, bank {type(exc2).__name__}: {exc2}")
                continue
        if not produced:
            errors.append(f"{name}: no decoded output")
            continue
        for wav_name, payload in produced.items():
            base = Path(wav_name).name
            seen[base] += 1
            if seen[base] > 1:
                stem = Path(base).stem
                suffix = Path(base).suffix
                base = f"{stem}__dup{seen[Path(wav_name).name]}{suffix}"
            target = AUDIO / base
            target.write_bytes(bytes(payload))
            index.append({"name": name, "source_file": src.name,
                          "resource_source": source_name,
                          "offset": getattr(resource, "m_Offset", None),
                          "size": getattr(resource, "m_Size", None),
                          "method": method,
                          "output": str(target.relative_to(OUT))})

(OUT / "audio_index.json").write_text(
    json.dumps({"clips": len(index), "errors": errors, "audio": index},
               indent=2, ensure_ascii=False), encoding="utf-8")
print("decoded", len(index), "wav files", "errors", len(errors))
for error in errors[:10]:
    print("  ", error)
