#!/usr/bin/env python3
"""Extract Shader objects: parsed form, reconstructed ShaderLab, GPU bytecode."""
import csv
import json
import re
import struct
import subprocess
from collections import Counter, defaultdict
from pathlib import Path

import lz4.block
import UnityPy
from UnityPy.classes import PPtr, UnknownObject
from UnityPy.helpers.TypeTreeGenerator import TypeTreeGenerator

GAME = Path("/run/media/eddyr/external/heroic/Banners of Ruin/BannersOfRuin_Data")
BUNDLES = GAME / "StreamingAssets/AssetBundles/WindowsPlayer"
OUT = Path("/run/media/eddyr/external/heroic/Banners of Ruin/_shaders")
SUB = {
    "parsed": OUT / "parsed",
    "source": OUT / "source",
    "bytecode": OUT / "bytecode",
    "disasm": OUT / "disasm",
}
for p in SUB.values():
    p.mkdir(parents=True, exist_ok=True)

TTG = TypeTreeGenerator("2019.4.22f1")
TTG.load_local_game(str(GAME.parent))

SKIP = {"object_reader", "assets_file", "__node__", "NodeInput"}
MAGICS = {"DXBC": b"DXBC", "SPIRV": b"\x03\x02#\x07"}
stats = Counter()
rows = []
material_edges = []
shader_owner = {}


def ser(v, pid_container=None, depth=0):
    if depth > 16:
        return "<depth-limit>"
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, bytes):
        return {"$bytes": len(v), "hex": v[:64].hex()}
    if isinstance(v, (list, tuple, set)):
        return [ser(x, pid_container, depth + 1) for x in v]
    if isinstance(v, dict):
        return {str(k): ser(x, pid_container, depth + 1)
                for k, x in v.items() if k not in SKIP}
    if isinstance(v, PPtr):
        out = {"$pptr": {"file_id": v.file_id, "path_id": v.path_id}}
        if pid_container and v.path_id in pid_container:
            out["$pptr"]["container"] = pid_container[v.path_id]
        return out
    if isinstance(v, UnknownObject):
        node = getattr(v, "__node__", None)
        out = {"$type": getattr(node, "m_Type", "?")}
        for k, x in getattr(v, "__dict__", {}).items():
            if k != "__node__":
                out[k] = ser(x, pid_container, depth + 1)
        return out
    d = getattr(v, "__dict__", None)
    if d is not None:
        return {k: ser(x, pid_container, depth + 1)
                for k, x in d.items() if k not in SKIP}
    return {"$repr": repr(v)[:200]}


def safe_name(container):
    parts = [p for p in Path(container).parts if p]
    name = "__".join(parts)
    return re.sub(r"[^A-Za-z0-9._-]", "_", name)


def reconstruct_shader(pf):
    lines = []
    name = getattr(pf, "m_Name", "") or "Unnamed"
    lines.append(f'Shader "{name}" {{')

    props = getattr(getattr(pf, "m_PropInfo", None), "m_Props", [])
    if props:
        lines.append("Properties {")
        for p in props:
            pn = getattr(p, "m_Name", "")
            desc = getattr(p, "m_Description", "")
            typ = int(getattr(p, "m_Type", 0))
            values = [getattr(p, f"m_DefValue_{i}_", None) for i in range(4)]
            lines.append(f'  {pn} ("{desc}", {typ}) = {values}')
        lines.append("}")

    for sub in getattr(pf, "m_SubShaders", []):
        lines.append("SubShader {")
        tags = getattr(sub, "m_Tags", None)
        if tags:
            lines.append(f"  Tags {json.dumps(ser(tags), ensure_ascii=False)}")
        lines.append(f"  LOD {getattr(sub, 'm_LOD', 0)}")
        for pas in getattr(sub, "m_Passes", []):
            lines.append("  Pass {")
            lines.append(f'    Name "{getattr(pas, "m_Name", "")}"')
            lines.append(f'    Type {getattr(pas, "m_Type", 0)}')
            lines.append(f"    State {json.dumps(ser(getattr(pas, 'm_State', None)), ensure_ascii=False)}")
            for prog in ("progVertex", "progFragment", "progGeometry", "progHull", "progDomain", "progRayTracing"):
                lines.append(f"    {prog} {json.dumps(ser(getattr(pas, prog, None)), ensure_ascii=False)}")
            lines.append("  }")
        lines.append("}")

    fallback = getattr(pf, "m_FallbackName", "")
    if fallback:
        lines.append(f'Fallback "{fallback}"')
    custom = getattr(pf, "m_CustomEditorName", "")
    if custom:
        lines.append(f'CustomEditor "{custom}"')
    lines.append("}")
    return "\n".join(lines) + "\n"


def carve_blobs(data, base, platform):
    carved = []
    # DXBC: magic + 4 hashes + version at +20 + total size at +24
    pos = data.find(MAGICS["DXBC"])
    while pos >= 0:
        try:
            size = struct.unpack_from("<I", data, pos + 24)[0]
        except struct.error:
            size = 0
        if 64 <= size <= len(data) - pos:
            chunk = data[pos:pos + size]
            path = SUB["bytecode"] / f"{base}__p{platform}__dxbc_{pos}.dxbc"
            path.write_bytes(chunk)
            carved.append(("dxbc", str(path.relative_to(OUT)), len(chunk)))
            stats["dxbc_chunks"] += 1
        pos = data.find(MAGICS["DXBC"], pos + 4)
    # SPIR-V: magic header, carve to next magic or end
    pos = data.find(MAGICS["SPIRV"])
    while pos >= 0:
        nxt = data.find(MAGICS["SPIRV"], pos + 4)
        nxt = len(data) if nxt < 0 else nxt
        chunk = data[pos:nxt]
        path = SUB["bytecode"] / f"{base}__p{platform}__spv_{pos}.spv"
        path.write_bytes(chunk)
        carved.append(("spv", str(path.relative_to(OUT)), len(chunk)))
        stats["spv_files"] += 1
        asm = SUB["disasm"] / f"{base}__p{platform}__spv_{pos}.spvasm"
        try:
            res = subprocess.run(["spirv-dis", str(path), "-o", str(asm)],
                                 capture_output=True, timeout=30)
            if res.returncode == 0 and asm.exists():
                carved.append(("spvasm", str(asm.relative_to(OUT)), asm.stat().st_size))
                stats["spvasm_files"] += 1
        except Exception as exc:
            stats["spirv_dis_errors"] += 1
        pos = nxt
    return carved


def process_file(path, source_rel):
    env = UnityPy.load(str(path))
    env.typetree_generator = TTG
    objects = list(env.objects)
    pid_container = {o.path_id: (str(o.container) if o.container else None) for o in objects}

    for obj in objects:
        if obj.type.name not in ("Shader", "ComputeShader"):
            continue
        container = str(obj.container) if obj.container else f"{source_rel}#{obj.path_id}"
        base = safe_name(container)
        try:
            d = obj.read()
        except Exception as exc:
            stats["shader_read_errors"] += 1
            continue
        stats[f"type_{obj.type.name}"] += 1
        shader_owner[obj.path_id] = (source_rel, container)

        parsed = ser(d.__dict__, pid_container)
        (SUB["parsed"] / f"{base}.json").write_text(
            json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")

        pf = getattr(d, "m_ParsedForm", None)
        if pf is not None:
            (SUB["source"] / f"{base}.shader").write_text(
                reconstruct_shader(pf), encoding="utf-8")
            stats["shaderlab_files"] += 1

        blobs = []
        blob = getattr(d, "compressedBlob", None)
        if blob:
            raw = bytes(blob)
            platforms = getattr(d, "platforms", [])
            for i, raw_off in enumerate(getattr(d, "offsets", [])):
                off = raw_off[0] if isinstance(raw_off, (list, tuple)) else raw_off
                clen = d.compressedLengths[i][0]
                ulen = d.decompressedLengths[i][0]
                platform = platforms[i] if i < len(platforms) else -1
                try:
                    out = lz4.block.decompress(raw[off:off + clen], uncompressed_size=ulen)
                except Exception as exc:
                    stats["lz4_errors"] += 1
                    continue
                stats["blocks_decompressed"] += 1
                carved = carve_blobs(out, f"{base}_b{i}", platform)
                blobs.extend(carved)
                if not carved:
                    bp = SUB["bytecode"] / f"{base}__p{platform}__block{i}.bin"
                    bp.write_bytes(out)
                    blobs.append(("bin", str(bp.relative_to(OUT)), len(out)))
                    stats["bin_files"] += 1
        rows.append({
            "source": source_rel,
            "container": container,
            "name": getattr(pf, "m_Name", "") if pf is not None else "",
            "type": obj.type.name,
            "baked": getattr(d, "m_ShaderIsBaked", ""),
            "platforms": "|".join(str(x) for x in getattr(d, "platforms", [])),
            "blobs": len(blobs),
            "blob_detail": ";".join(f"{k}:{v}" for k, v, _ in blobs),
        })

    for obj in objects:
        if obj.type.name != "Material":
            continue
        try:
            d = obj.read()
            sid = getattr(d, "m_Shader", None)
            if sid is None:
                continue
            path_id = sid.path_id if isinstance(sid, PPtr) else None
            if path_id in shader_owner:
                src, container = shader_owner[path_id]
                material_edges.append({
                    "material": str(obj.container) if obj.container else f"{source_rel}#{obj.path_id}",
                    "shader": container,
                    "shader_bundle": src,
                    "material_bundle": source_rel,
                })
        except Exception:
            stats["material_read_errors"] += 1


# collect shader sources
sources = [(p, str(p.relative_to(BUNDLES))) for p in BUNDLES.rglob("*")
           if p.is_file() and p.open("rb").read(8) == b"UnityFS\x00"]
for p in sorted(GAME.iterdir()):
    if p.is_file() and re.match(r"^(globalgamemanagers|resources\.assets|sharedassets\d+\.assets|level\d+)$", p.name):
        sources.append((p, p.name))

for i, (p, rel) in enumerate(sources, 1):
    process_file(p, rel)
    if i % 100 == 0:
        print(f"{i}/{len(sources)} files", flush=True)

with (OUT / "index.csv").open("w", newline="", encoding="utf-8") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

graph = defaultdict(list)
for e in material_edges:
    graph[e["shader"]].append(e)
(OUT / "shader_graph.json").write_text(
    json.dumps(graph, indent=2, ensure_ascii=False), encoding="utf-8")

report = [f"shader sources: {stats['type_Shader']}",
          f"compute shaders: {stats['type_ComputeShader']}",
          f"shaderlab files: {stats['shaderlab_files']}",
          f"LZ4 blocks decompressed: {stats['blocks_decompressed']}",
          f"DXBC chunks: {stats['dxbc_chunks']}",
          f"SPIR-V files: {stats['spv_files']}",
          f"SPIR-V disassemblies: {stats['spvasm_files']}",
          f"other binary blocks: {stats['bin_files'] if 'bin_files' in stats else 0}",
          f"material-to-shader edges: {len(material_edges)}",
          f"shader read errors: {stats['shader_read_errors']}",
          f"LZ4 errors: {stats['lz4_errors']}",
          f"spirv-dis errors: {stats['spirv_dis_errors']}",
          f"material read errors: {stats['material_read_errors']}"]
(OUT / "report.txt").write_text("\n".join(report) + "\n", encoding="utf-8")
print("\n".join(report), flush=True)
print("OUTPUT:", OUT, flush=True)
