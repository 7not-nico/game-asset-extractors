#!/usr/bin/env python3
"""Extract all Unity assets from Sunless Skies into a readable tree."""
import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy
from UnityPy.classes import PPtr, UnknownObject
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

GAME = Path("/run/media/eddyr/external/heroic/Sunless Skies/game/Sunless Skies_Data")
OUT = Path("/run/media/eddyr/external/heroic/Sunless Skies/game/_extracted")
VERSION = "2019.4.2f1"

ASSETS = OUT
DATA = OUT / "data"
RAW = OUT / "raw"
if OUT.exists():
    shutil.rmtree(OUT)
for folder in (ASSETS, DATA, RAW):
    folder.mkdir(parents=True, exist_ok=True)

TTG = TypeTreeGenerator(VERSION)
TTG.load_local_game(str(GAME.parent))
SKIP_KEYS = {"object_reader", "assets_file", "NodeInput", "__node__"}

stats = Counter()
errors = []
manifest = []
written = {}
format_counts = Counter()
image_containers = set()


def safe_parts(container):
    parts = []
    for part in Path(str(container).strip().lstrip("/")).parts:
        part = part.replace(":", "_").replace("?", "_").replace("*", "_")
        part = part.replace("<", "_").replace(">", "_").replace("|", "_")
        part = part.replace('"', "_").strip()
        if part:
            parts.append(part)
    return parts


def output_path(container, suffix=""):
    parts = safe_parts(container)
    if not parts:
        return None
    parts[-1] += suffix
    return ASSETS.joinpath(*parts)


def claim(path):
    if path is None:
        return None
    if path not in written:
        written[path] = 1
        return path
    n = written[path] + 1
    written[path] = n
    return path.with_name(f"{path.stem}__dup{n}{path.suffix}")


def ser(value, depth=0, pid_container=None):
    if depth > 16:
        return "<depth-limit>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, bytes):
        return {"$bytes": len(value), "hex": value[:64].hex()}
    if isinstance(value, (list, tuple, set)):
        return [ser(x, depth + 1, pid_container) for x in value]
    if isinstance(value, dict):
        return {str(k): ser(v, depth + 1, pid_container)
                for k, v in value.items() if k not in SKIP_KEYS}
    if isinstance(value, PPtr):
        out = {"$pptr": {"file_id": value.file_id, "path_id": value.path_id}}
        if pid_container and value.path_id in pid_container:
            out["$pptr"]["container"] = pid_container[value.path_id]
        return out
    if isinstance(value, UnknownObject):
        node = getattr(value, "__node__", None)
        out = {"$type": getattr(node, "m_Type", "?")}
        for k, v in getattr(value, "__dict__", {}).items():
            if k != "__node__":
                out[k] = ser(v, depth + 1, pid_container)
        return out
    d = getattr(value, "__dict__", None)
    if d is not None:
        return {k: ser(v, depth + 1, pid_container)
                for k, v in d.items() if k not in SKIP_KEYS}
    return {"$repr": repr(value)[:200]}


def to_bytes(raw):
    if isinstance(raw, str):
        return raw.encode("utf-8", errors="surrogateescape")
    if isinstance(raw, (bytearray, memoryview)):
        return bytes(raw)
    if isinstance(raw, list):
        try:
            return bytes(raw)
        except (TypeError, ValueError):
            if all(isinstance(x, (bytes, bytearray)) for x in raw):
                return b"".join(bytes(x) for x in raw)
    return raw


def save_image(data, container, obj, source):
    if container and container != "None":
        if container in image_containers:
            stats["images_deduped"] += 1
            return True
        image_containers.add(container)
        target = output_path(container, ".png")
    else:
        target = OUT / "_no_container" / f"{source.replace('/', '__')}__{obj.path_id}.png"
    try:
        image = getattr(data, "image", None)
    except Exception as exc:
        errors.append(f"decode {container}: {type(exc).__name__}: {exc}")
        return False
    if image is None:
        return False
    path = claim(target)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        image.save(str(path))
        stats["images_png"] += 1
        return True
    except Exception as exc:
        errors.append(f"image {container}: {exc}")
        return False


def export_file(path, source):
    stats["unity_files"] += 1
    try:
        env = UnityPy.load(str(path))
        env.typetree_generator = TTG
    except Exception as exc:
        errors.append(f"load {source}: {exc}")
        return

    objects = list(env.objects)
    pid_container = {}
    groups = defaultdict(list)
    no_container = []
    for obj in objects:
        container = str(obj.container) if obj.container else None
        if container:
            pid_container[obj.path_id] = container
        try:
            data = obj.read()
        except Exception as exc:
            errors.append(f"read {source} {obj.path_id}: {exc}")
            for reader in (getattr(obj, "object_reader", None), obj):
                if reader is None or not hasattr(reader, "get_raw_data"):
                    continue
                try:
                    raw = reader.get_raw_data()
                    target = claim(OUT / "_raw_failed" / source.replace("/", "__") / f"{obj.path_id}.bin")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    stats["raw_fallback"] += 1
                    break
                except Exception:
                    continue
            continue
        kind = obj.type.name
        if not container:
            name = getattr(data, "m_Name", None)
            if isinstance(name, str) and name.strip():
                container = f"__by_name/{kind}/{name}"
                pid_container[obj.path_id] = container
        if kind == "Texture2D":
            format_counts[int(getattr(data, "m_TextureFormat", -1))] += 1
            if save_image(data, container, obj, source):
                continue
        elif kind == "Sprite":
            if save_image(data, container, obj, source):
                continue
        elif kind == "TextAsset":
            raw = to_bytes(getattr(data, "m_Script", None))
            if raw is not None and container:
                target = claim(output_path(container))
                if target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    stats["text_files"] += 1
                    continue
        elif kind == "Font":
            raw = to_bytes(getattr(data, "m_FontData", None))
            if raw and container:
                target = claim(output_path(container))
                if target:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(raw)
                    stats["font_files"] += 1
                    continue
        entry = {"type": kind, "path_id": obj.path_id,
                 "data": ser(data.__dict__ if hasattr(data, "__dict__") else data,
                             0, pid_container)}
        if container:
            groups[container].append(entry)
        else:
            no_container.append(entry)
        stats[f"obj_{kind}"] += 1

    for container, entries in groups.items():
        target = claim(output_path(container, ".json"))
        if not target:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"container": container, "objects": entries},
                                     indent=2, ensure_ascii=False), encoding="utf-8")
        stats["json_groups"] += 1
    if no_container:
        target = claim(ASSETS / "_no_container" / f"{source.replace('/', '__')}.json")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps({"source": source, "objects": no_container},
                                     indent=2, ensure_ascii=False), encoding="utf-8")
        stats["json_groups"] += 1
    manifest.append({"source": source, "objects": len(objects), "containers": len(groups)})
    print(f"    {source}: {len(objects)} objects, {len(groups)} containers", flush=True)


print("[1/4] copying raw sources", flush=True)
for src in sorted((GAME / "StreamingAssets").rglob("*")):
    if src.is_file():
        target = RAW / src.relative_to(GAME / "StreamingAssets")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)
        stats["raw_copied"] += 1
for src in sorted(GAME.glob("*.resource")):
    shutil.copy2(src, RAW / src.name)
    stats["raw_copied"] += 1

print("[2/4] extracting serialized files", flush=True)
targets = []
for src in sorted(GAME.iterdir()):
    if src.is_file() and (src.suffix.lower() == ".assets" or
                          re.fullmatch(r"(globalgamemanagers|level\d+)", src.name)):
        targets.append(src)
for src in sorted((GAME / "Resources").iterdir()):
    if src.is_file():
        targets.append(src)
for src in targets:
    export_file(src, str(src.relative_to(GAME)))

print("[3/4] writing mapping", flush=True)
(OUT / "mapping.json").write_text(json.dumps({
    "unity_version": VERSION,
    "sources": manifest,
    "texture_formats": {str(k): v for k, v in format_counts.most_common()},
}, indent=2, ensure_ascii=False), encoding="utf-8")
with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    writer = csv.DictWriter(fh, fieldnames=["source", "objects", "containers"])
    writer.writeheader()
    writer.writerows(manifest)

print("[4/4] writing report", flush=True)
report = [f"unity files processed : {stats['unity_files']}",
          f"objects serialized    : {sum(v for k, v in stats.items() if k.startswith('obj_'))}",
          f"png images            : {stats['images_png']}",
          f"duplicate images skipped : {stats['images_deduped']}",
          f"text assets           : {stats['text_files']}",
          f"font files            : {stats['font_files']}",
          f"json groups           : {stats['json_groups']}",
          f"raw files copied      : {stats['raw_copied']}",
          f"raw object fallbacks  : {stats['raw_fallback']}",
          f"errors                : {len(errors)}",
          "", "top object types:"]
for key, count in sorted(((k[4:], v) for k, v in stats.items() if k.startswith("obj_")),
                         key=lambda x: -x[1])[:15]:
    report.append(f"  {key}: {count}")
if errors:
    report.append("")
    report.append("first 40 errors:")
    report.extend(f"  {e}" for e in errors[:40])
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report[:9]), flush=True)
print("OUTPUT:", OUT, flush=True)
