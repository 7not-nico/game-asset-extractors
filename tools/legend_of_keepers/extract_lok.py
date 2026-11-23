#!/usr/bin/env python3
"""Extract every Unity asset from Legend of Keepers into a readable tree.

The build is a Unity 2019 serialized-file layout with named Addressables
bundles. Internal container paths are the authoritative names; the
Addressables catalog is copied and summarized as the mapping layer.
"""
import csv
import json
import re
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy
from UnityPy.classes import PPtr, UnknownObject
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

GAME = Path("/run/media/eddyr/external/heroic/Legend of Keepers Career of a Dungeon Master/game/LegendOfKeepers_Data")
OUT = Path("/run/media/eddyr/external/heroic/Legend of Keepers Career of a Dungeon Master/game/_extracted")
BUNDLES = GAME / "StreamingAssets" / "aa" / "StandaloneLinux64"
STREAM = GAME / "StreamingAssets"
VERSION = "2019.4.18f1"

ASSETS = OUT
DATA = OUT / "data"
RAW = OUT / "raw"
if OUT.exists():
    shutil.rmtree(OUT)
for d in (ASSETS, DATA, RAW):
    d.mkdir(parents=True, exist_ok=True)

TTG = TypeTreeGenerator(VERSION)
TTG.load_local_game(str(GAME.parent))
SKIP_KEYS = {"object_reader", "assets_file", "NodeInput", "__node__"}

stats = Counter()
errors = []
manifest_rows = []
written = {}
format_counts = Counter()
image_containers = set()


def safe_parts(container):
    p = str(container).strip().lstrip("/")
    parts = []
    for part in Path(p).parts:
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
    parts[-1] = parts[-1] + suffix
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


def save_image(data, container, obj, source_rel):
    if container and container != "None":
        if container in image_containers:
            stats["images_deduped"] += 1
            return True
        image_containers.add(container)
        target = output_path(container, ".png")
    else:
        target = OUT / "_no_container" / f"{source_rel.replace('/', '__')}__{obj.path_id}.png"
    try:
        img = getattr(data, "image", None)
    except Exception as exc:
        errors.append(f"decode {container}: {type(exc).__name__}: {exc}")
        try:
            raw = data.get_image_data()
            p = claim(output_path(container, ".rawtex"))
            if p:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(raw)
                stats["raw_textures"] += 1
        except Exception:
            pass
        return False
    if img is None:
        return False
    path = claim(target)
    if path is None:
        return False
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        img.save(str(path))
        stats["images_png"] += 1
        return True
    except Exception as exc:
        errors.append(f"image {container}: {exc}")
        return False


def export_file(path, source_rel):
    stats["unity_files"] += 1
    try:
        env = UnityPy.load(str(path))
        env.typetree_generator = TTG
    except Exception as exc:
        errors.append(f"load {source_rel}: {exc}")
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
            errors.append(f"read {source_rel} {obj.path_id}: {exc}")
            for reader in (getattr(obj, "object_reader", None), obj):
                if reader is None or not hasattr(reader, "get_raw_data"):
                    continue
                try:
                    raw = reader.get_raw_data()
                    p = claim(OUT / "_raw_failed" / source_rel.replace("/", "__") / f"{obj.path_id}.bin")
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(raw)
                    stats["raw_fallback"] += 1
                    break
                except Exception:
                    continue
            continue
        t = obj.type.name
        if not container:
            name = getattr(data, "m_Name", None)
            if isinstance(name, str) and name.strip():
                container = f"__by_name/{t}/{name}"
                pid_container[obj.path_id] = container

        if t == "Texture2D":
            fmt = int(getattr(data, "m_TextureFormat", -1))
            format_counts[fmt] += 1
            if save_image(data, container, obj, source_rel):
                continue
        elif t == "Sprite":
            if save_image(data, container, obj, source_rel):
                continue
        elif t == "TextAsset":
            raw = to_bytes(getattr(data, "m_Script", None))
            if raw is not None and container:
                p = claim(output_path(container))
                if p:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(raw)
                    stats["text_files"] += 1
                    continue
        elif t == "Font":
            raw = to_bytes(getattr(data, "m_FontData", None))
            if raw and container:
                p = claim(output_path(container))
                if p:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(raw)
                    stats["font_files"] += 1
                    continue
        elif t == "AudioClip":
            raw = to_bytes(getattr(data, "m_AudioData", None))
            if raw and container:
                p = claim(output_path(container, ".audio"))
                if p:
                    p.parent.mkdir(parents=True, exist_ok=True)
                    p.write_bytes(raw)
                    stats["audio_raw"] += 1
                    continue

        entry = {"type": t, "path_id": obj.path_id,
                 "data": ser(data.__dict__ if hasattr(data, "__dict__") else data,
                             0, pid_container)}
        if container:
            groups[container].append(entry)
        else:
            no_container.append(entry)
        stats[f"obj_{t}"] += 1

    for container, entries in groups.items():
        p = claim(output_path(container, ".json"))
        if not p:
            continue
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"container": container, "objects": entries},
                                indent=2, ensure_ascii=False), encoding="utf-8")
        stats["json_groups"] += 1

    if no_container:
        p = claim(ASSETS / "_no_container" / f"{source_rel.replace('/', '__')}.json")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps({"source": source_rel, "objects": no_container},
                                indent=2, ensure_ascii=False), encoding="utf-8")
        stats["json_groups"] += 1

    manifest_rows.append({"source": source_rel, "objects": len(objects),
                          "containers": len(groups)})
    print(f"    {source_rel}: {len(objects)} objects, {len(groups)} containers", flush=True)


print("[1/4] parsing Addressables catalog", flush=True)
catalog_path = STREAM / "aa" / "catalog.json"
catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
internal_ids = catalog["m_InternalIds"]
bundle_ids = [s for s in internal_ids if s.lower().endswith(".bundle")]
asset_ids = [s for s in internal_ids if not s.lower().endswith(".bundle")]
(OUT / "mapping.json").write_text(json.dumps({
    "unity_version": VERSION,
    "locator_id": catalog.get("m_LocatorId"),
    "provider_ids": catalog.get("m_ProviderIds"),
    "internal_id_count": len(internal_ids),
    "bundle_ids": bundle_ids,
    "asset_ids": asset_ids,
    "sources": [],
    "texture_formats": {},
}, indent=2, ensure_ascii=False), encoding="utf-8")

print("[2/4] copying StreamingAssets verbatim", flush=True)
for src in sorted(STREAM.rglob("*")):
    if not src.is_file() or src.suffix.lower() == ".bundle":
        continue
    dst = RAW / src.relative_to(STREAM)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    stats["raw_copied"] += 1

print("[3/4] extracting Addressables bundles", flush=True)
all_bundles = sorted(p for p in BUNDLES.rglob("*")
                     if p.is_file() and p.open("rb").read(8) == b"UnityFS\x00")
for p in all_bundles:
    export_file(p, str(p.relative_to(GAME)))
print(f"    {len(all_bundles)} bundles done", flush=True)

print("[4/4] extracting root serialized files", flush=True)
extra = []
for p in sorted(GAME.iterdir()):
    if p.is_file() and re.match(
            r"^(globalgamemanagers(\.assets)?|resources\.assets|sharedassets\d+\.assets|level\d+)$",
            p.name):
        extra.append(p)
for p in sorted((GAME / "Resources").iterdir()):
    if p.is_file():
        extra.append(p)
for p in extra:
    export_file(p, str(p.relative_to(GAME)))

mapping = json.loads((OUT / "mapping.json").read_text(encoding="utf-8"))
mapping["sources"] = manifest_rows
mapping["texture_formats"] = {str(k): v for k, v in format_counts.most_common()}
(OUT / "mapping.json").write_text(json.dumps(mapping, indent=2, ensure_ascii=False),
                                  encoding="utf-8")

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["source", "objects", "containers"])
    w.writeheader()
    w.writerows(manifest_rows)

report = []
report.append(f"unity files processed : {stats['unity_files']}")
report.append(f"addressables bundles  : {len(all_bundles)}")
report.append(f"catalog internal ids  : {len(internal_ids)}")
report.append(f"objects serialized    : {sum(v for k, v in stats.items() if k.startswith('obj_'))}")
report.append(f"png images            : {stats['images_png']}")
report.append(f"duplicate images skipped : {stats['images_deduped']}")
report.append(f"text assets           : {stats['text_files']}")
report.append(f"font files            : {stats['font_files']}")
report.append(f"audio raw             : {stats['audio_raw']}")
report.append(f"json groups           : {stats['json_groups']}")
report.append(f"raw files copied      : {stats['raw_copied']}")
report.append(f"raw object fallbacks  : {stats['raw_fallback']}")
report.append(f"raw texture fallbacks : {stats['raw_textures']}")
report.append(f"errors                : {len(errors)}")
report.append("")
report.append("texture formats (Unity enum):")
for fmt, c in format_counts.most_common():
    report.append(f"  {fmt}: {c}")
report.append("")
report.append("top object types:")
for k, c in sorted(((k[4:], v) for k, v in stats.items() if k.startswith("obj_")),
                   key=lambda x: -x[1])[:15]:
    report.append(f"  {k}: {c}")
if errors:
    report.append("")
    report.append("first 40 errors:")
    for e in errors[:40]:
        report.append(f"  {e}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report[:14]), flush=True)
print("OUTPUT:", OUT, flush=True)
