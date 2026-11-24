#!/usr/bin/env python3
"""Decode Cross Blitz AudioClips in a dedicated single-purpose pass."""
import json
from pathlib import Path

import UnityPy
import fmod_toolkit

GAME = Path("/run/media/eddyr/external/sandbox-games/Cross-Blitz-SteamRIP.com/Cross Blitz v0.6.7/Cross Blitz_Data")
OUT = Path("/run/media/eddyr/external/sandbox-games/Cross-Blitz-SteamRIP.com/Cross Blitz v0.6.7/_extracted")
AUDIO = OUT / "audio"
AUDIO.mkdir(parents=True, exist_ok=True)

SOURCES = ["data.unity3d"]
SOURCES.extend(str(p.relative_to(GAME)) for p in
               (GAME / "StreamingAssets/aa/StandaloneWindows64").glob("*.bundle"))

bank = (GAME / "resources.resource").read_bytes()
index = []
errors = []

for source in SOURCES:
    env = UnityPy.load(str(GAME / source))
    for obj in env.objects:
        if obj.type.name != "AudioClip":
            continue
        data = obj.read()
        name = getattr(data, "m_Name", None) or f"clip_{obj.path_id}"
        resource = getattr(data, "m_Resource", None)
        source_name = getattr(resource, "m_Source", None) or ""
        produced = {}
        method = None
        if "resources.resource" in source_name:
            try:
                produced = fmod_toolkit.raw_to_wav(
                    bank, name, data.m_Channels or 2, data.m_Frequency or 44100)
                method = "full_fsb5_bank"
            except Exception as exc:
                errors.append(f"{name}: full bank decode: {type(exc).__name__}: {exc}")
        else:
            try:
                produced = data.samples or {}
                method = "unity_samples"
            except Exception as exc:
                errors.append(f"{name}: samples: {type(exc).__name__}: {exc}")
        if not produced:
            errors.append(f"{name}: no decoded output")
            continue
        for wav_name, payload in produced.items():
            target = AUDIO / Path(wav_name).name
            target.write_bytes(bytes(payload))
            index.append({
                "name": name,
                "source_file": source,
                "resource_source": source_name,
                "offset": getattr(resource, "m_Offset", None),
                "size": getattr(resource, "m_Size", None),
                "method": method,
                "output": str(target.relative_to(OUT)),
            })

(OUT / "audio_index.json").write_text(
    json.dumps({"clips": len(index), "errors": errors, "audio": index},
               indent=2, ensure_ascii=False), encoding="utf-8")
print("decoded", len(index), "wav files", "errors", len(errors))
for error in errors[:10]:
    print("  ", error)
