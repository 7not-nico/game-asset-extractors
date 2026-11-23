#!/usr/bin/env python3
"""Extract every Unity asset from Banners of Ruin into a de-obfuscated tree.

Source obfuscation is naming only: randomized bundle stems plus .brm lookup tables.
Internal container paths are the authoritative human-readable names.
"""
import csv
import json
import re
import shutil
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import UnityPy
from UnityPy.classes import PPtr, UnknownObject
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

GAME = Path("/run/media/eddyr/external/heroic/Banners of Ruin/BannersOfRuin_Data")
TTG = TypeTreeGenerator("2019.4.22f1")
TTG.load_local_game(str(GAME.parent))
STREAM = GAME / "StreamingAssets"
BUNDLES = STREAM / "AssetBundles" / "WindowsPlayer"
OUT = Path("/run/media/eddyr/external/heroic/Banners of Ruin/_extracted")

ASSETS = OUT
DATA = OUT / "data"
RAW = OUT / "raw"
if OUT.exists():
    shutil.rmtree(OUT)
for d in (ASSETS, DATA, RAW):
    d.mkdir(parents=True, exist_ok=True)

SKIP_KEYS = {"object_reader", "assets_file", "NodeInput", "__node__"}
RANDOM_RE = re.compile(r"^[a-z0-9]{9}$")

stats = Counter()
errors = []
manifest_rows = []
written = {}
format_counts = Counter()
image_containers = set()
source_containers = {}


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
    """Return a non-colliding path for this output, recording alias reuse."""
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
        return raw.encode("utf-8")
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

    source_containers[source_rel] = sorted(groups.keys())
    manifest_rows.append({
        "source": source_rel,
        "objects": len(objects),
        "containers": len(groups),
        "random_stem": bool(RANDOM_RE.match(path.stem)),
    })


# ---- 1. mapping tables -------------------------------------------------
print("[1/5] parsing .brm mapping tables", flush=True)
mapping = {"brm": {}, "bundle_to_assets": {}, "brm_docs": {}}
for brm in sorted(BUNDLES.rglob("*.brm")):
    doc = json.loads(brm.read_text(encoding="utf-8"))
    rel = str(brm.relative_to(BUNDLES))
    mapping["brm_docs"][rel] = doc
    entries = []

    def walk(o):
        if isinstance(o, dict):
            if "BundlePath" in o and "AssetName" in o:
                entries.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(doc)
    mapping["brm"][rel] = entries
    for e in entries:
        mapping["bundle_to_assets"].setdefault(e["BundlePath"], []).append({
            "id": e.get("Id"), "asset_name": e.get("AssetName"), "source": rel,
        })
stats["brm_entries"] = sum(len(v) for v in mapping["brm"].values())
(OUT / "mapping.json").write_text(
    json.dumps(mapping, indent=2, ensure_ascii=False), encoding="utf-8")

# ---- 2. raw copies -----------------------------------------------------
print("[2/5] copying non-Unity source files", flush=True)
for src in sorted(STREAM.iterdir()):
    if src.is_file():
        dst = RAW / "StreamingAssets" / src.name
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        stats["raw_copied"] += 1
for src in sorted(BUNDLES.rglob("*.manifest")):
    dst = RAW / "AssetBundles" / src.relative_to(BUNDLES)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    stats["raw_copied"] += 1
for src in sorted(BUNDLES.rglob("*.brm")):
    dst = RAW / "AssetBundles" / src.relative_to(BUNDLES)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)

# ---- 3. Unity bundles --------------------------------------------------
print("[3/5] extracting 908 Unity bundles", flush=True)
all_bundles = sorted(
    p for p in BUNDLES.rglob("*")
    if p.is_file() and p.open("rb").read(8) == b"UnityFS\x00"
)
for i, p in enumerate(all_bundles, 1):
    export_file(p, str(p.relative_to(BUNDLES)))
    if i % 100 == 0:
        print(f"    {i}/{len(all_bundles)} bundles", flush=True)

# ---- 4. root serialized files -----------------------------------------
print("[4/5] extracting root serialized files", flush=True)
extra = []
for p in sorted(GAME.iterdir()):
    if p.is_file() and re.match(r"^(globalgamemanagers|resources\.assets|sharedassets\d+\.assets|level\d+)$", p.name):
        extra.append(p)
for p in sorted((GAME / "Resources").iterdir()):
    if p.is_file():
        extra.append(p)
for p in extra:
    export_file(p, str(p.relative_to(GAME)))

# ---- 5. enriched data + reports ----------------------------------------
print("[5/5] writing enriched data and reports", flush=True)
for rel, doc in mapping["brm_docs"].items():
    enriched = json.loads(json.dumps(doc))

    def annotate(o):
        if isinstance(o, dict):
            if "BundlePath" in o:
                o["ExtractedContainers"] = source_containers.get(o["BundlePath"], [])
            for v in o.values():
                annotate(v)
        elif isinstance(o, list):
            for v in o:
                annotate(v)

    annotate(enriched)
    (DATA / Path(rel).name).write_text(
        json.dumps(enriched, indent=2, ensure_ascii=False), encoding="utf-8")

with (OUT / "manifest.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=["source", "objects", "containers", "random_stem"])
    w.writeheader()
    w.writerows(manifest_rows)

mapped_paths = set(mapping["bundle_to_assets"])
unmapped_random = [r["source"] for r in manifest_rows
                   if r["random_stem"] and r["source"] not in mapped_paths]

report = []
report.append(f"unity files processed : {stats['unity_files']}")
report.append(f"bundles               : {len(all_bundles)}")
report.append(f"brm entries           : {stats['brm_entries']}")
report.append(f"objects serialized    : {sum(v for k, v in stats.items() if k.startswith('obj_'))}")
report.append(f"png images            : {stats['images_png']}")
report.append(f"text assets           : {stats['text_files']}")
report.append(f"font files            : {stats['font_files']}")
report.append(f"json groups           : {stats['json_groups']}")
report.append(f"duplicate images skipped : {stats['images_deduped']}")
report.append(f"raw files copied      : {stats['raw_copied']}")
report.append(f"raw object fallbacks  : {stats['raw_fallback']}")
report.append(f"raw texture fallbacks : {stats['raw_textures']}")
report.append(f"errors                : {len(errors)}")
report.append(f"random bundles unmapped by .brm : {len(unmapped_random)}")
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
if unmapped_random:
    report.append("")
    report.append("random bundles mapped only by internal container paths (first 40):")
    for s in unmapped_random[:40]:
        report.append(f"  {s}")
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")

print("\n".join(report[:14]), flush=True)
print("OUTPUT:", OUT, flush=True)
