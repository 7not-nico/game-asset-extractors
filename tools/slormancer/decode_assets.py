#!/usr/bin/env python3
"""Decode GameMaker texture pages, sprite frames and font glyphs to PNG."""
import bz2
import json
import struct
import zlib
from pathlib import Path

import fioq_decode

ROOT = Path("/run/media/eddyr/external/sandbox-games/The-Slormancer-SteamRIP.com")
GAME = ROOT / "The Slormancer"
WIN = GAME / "data.win"
YYTEX = GAME / "Textures_Fonts_0.yytex"
OUT = ROOT / "_extracted"


def chunk_map(blob):
    found = {}
    off = 8
    while off + 8 <= len(blob):
        name = blob[off:off + 4].decode("latin1")
        size = struct.unpack_from("<I", blob, off + 4)[0]
        found[name] = (off + 8, size)
        off += 8 + size + (size & 1)
    return found


def qoi_decode(data):
    """Decode FIOQ, choosing the run-width variant that reaches every pixel."""
    width, height = struct.unpack_from("<HH", data, 4)
    total = width * height
    best = None
    for mask in (0x0F, 0x1F, 0x3F):
        image = fioq_decode.decode_fioq(data, mask)
        count = fioq_decode.DECODED_COUNT
        if best is None or count > best[0]:
            best = (count, image.convert("RGBA").tobytes())
        if count == total:
            return width, height, bytes(best[1])
    raise ValueError(f"FIOQ decoded {best[0]} of {total} pixels")


def pack(tag, payload):
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def png(width, height, rgba):
    scan = b"".join(b"\x00" + rgba[y * width * 4:(y + 1) * width * 4]
                    for y in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + pack(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + pack(b"IDAT", zlib.compress(scan, 6))
            + pack(b"IEND", b""))


def crop(page, x, y, width, height):
    pw, ph, rgba = page
    if width <= 0 or height <= 0 or x + width > pw or y + height > ph:
        return None
    rows = [rgba[((y + row) * pw + x) * 4:((y + row) * pw + x + width) * 4]
            for row in range(height)]
    return width, height, b"".join(rows)


def string_at(blob, ptr):
    """Chunks point directly at NUL-terminated string bytes, not length fields."""
    if not 0 < ptr < len(blob):
        return ""
    end = blob.find(b"\0", ptr, min(len(blob), ptr + 4096))
    if end < 0:
        return ""
    return blob[ptr:end].decode("utf-8", "replace")


def pointer_list(blob, start):
    count = struct.unpack_from("<I", blob, start)[0]
    if count > 1000000:
        raise ValueError("implausible pointer count")
    return [struct.unpack_from("<I", blob, start + 4 + 4 * i)[0]
            for i in range(count)]


def decode_pages(blob, txtr):
    """Decode one page per TXTR record; record order is the page index."""
    start, _ = txtr
    records = pointer_list(blob, start)
    pages = []
    for index, ptr in enumerate(records):
        if ptr + 28 > len(blob):
            raise ValueError(f"TXTR record {index} out of bounds")
        expected_w, expected_h = struct.unpack_from("<II", blob, ptr + 12)
        magic = struct.unpack_from("<I", blob, ptr + 24)[0]
        if magic == 0:
            source = YYTEX.read_bytes()
            width, height = struct.unpack_from("<HH", source, 4)
            length = struct.unpack_from("<I", source, 8)[0]
            compressed = source[12:12 + length]
        else:
            if blob[magic:magic + 4] != b"2zoq":
                raise ValueError(f"TXTR record {index} has no texture header")
            width, height = struct.unpack_from("<HH", blob, magic + 4)
            length = struct.unpack_from("<I", blob, magic + 8)[0]
            compressed = blob[magic + 12:magic + 12 + length]
        if (width, height) != (expected_w, expected_h):
            raise ValueError(f"TXTR record {index} dimension mismatch")
        raw = bz2.decompress(compressed)
        page = qoi_decode(raw)
        if page[0] != width or page[1] != height or len(page[2]) != width * height * 4:
            raise ValueError(f"TXTR record {index} decoded pixel mismatch")
        pages.append(page)
        target = OUT / f"textures/decoded/page_{index:03d}.png"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(png(*page))
    return pages


def tpag_items(blob, tp):
    start, _ = tp
    items = {}
    for index, ptr in enumerate(pointer_list(blob, start)):
        if ptr + 22 > len(blob):
            continue
        x, y, w, h = struct.unpack_from("<4H", blob, ptr)
        page = struct.unpack_from("<H", blob, ptr + 20)[0]
        items[ptr] = (page, x, y, w, h, index)
    return items


def safe(name):
    return "".join(c if c.isalnum() or c in "_-." else "_" for c in name)


def sprites(blob, sprt, items, pages):
    start, _ = sprt
    count = 0
    for ptr in pointer_list(blob, start):
        if ptr + 88 > len(blob) or struct.unpack_from("<i", blob, ptr + 56)[0] != -1:
            continue
        name = string_at(blob, struct.unpack_from("<I", blob, ptr)[0])
        width, height = struct.unpack_from("<II", blob, ptr + 4)
        origin_x, origin_y = struct.unpack_from("<ii", blob, ptr + 48)
        special = struct.unpack_from("<I", blob, ptr + 60)[0]
        cursor = ptr + 76 + (4 if special >= 2 else 0) + (4 if special >= 3 else 0)
        frames = struct.unpack_from("<I", blob, cursor)[0]
        if frames > 1000:
            continue
        folder = OUT / "sprites" / safe(name or f"sprite_{count}")
        folder.mkdir(parents=True, exist_ok=True)
        meta = {"name": name, "width": width, "height": height,
                "origin_x": origin_x, "origin_y": origin_y, "frames": frames,
                "images": []}
        for i in range(frames):
            tptr = struct.unpack_from("<I", blob, cursor + 4 + 4 * i)[0]
            item = items.get(tptr)
            if item is None:
                continue
            page, x, y, w, h, index = item
            piece = crop(pages[page], x, y, w, h) if page < len(pages) else None
            if piece is None:
                continue
            image = f"frame_{i:03d}.png"
            (folder / image).write_bytes(png(*piece))
            meta["images"].append({"file": image, "tpag": index,
                                   "source": [x, y, w, h], "page": page})
        (folder / "sprite.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        count += 1
    return count


def fonts(blob, font, items, pages):
    start, _ = font
    count = 0
    for ptr in pointer_list(blob, start):
        if ptr + 60 > len(blob):
            continue
        name = string_at(blob, struct.unpack_from("<I", blob, ptr)[0])
        tptr = struct.unpack_from("<I", blob, ptr + 28)[0]
        item = items.get(tptr)
        glyphs = []
        cursor = struct.unpack_from("<I", blob, ptr + 56)[0]
        end = min(len(blob), cursor + 4096 * 16)
        while cursor + 16 <= end:
            code, x, y, w, h, shift, offset, kern = struct.unpack_from(
                "<8H", blob, cursor)
            if not (0 < code <= 0x10FFFF) or w == 0 or h == 0 or w > 4096 or h > 4096:
                break
            glyphs.append({"char": chr(code), "x": x, "y": y, "w": w, "h": h,
                           "shift": shift - 65536 if shift > 32767 else shift,
                           "offset": offset - 65536 if offset > 32767 else offset,
                           "kerning": kern})
            cursor += 16 + kern * 4
        folder = OUT / "fonts" / safe(name or f"font_{count}")
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "font.json").write_text(
            json.dumps({"name": name, "glyphs": glyphs}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        if item is not None and item[0] < len(pages):
            for glyph in glyphs:
                piece = crop(pages[item[0]], glyph["x"], glyph["y"],
                             glyph["w"], glyph["h"])
                if piece is None:
                    continue
                target = folder / f"glyph_{ord(glyph['char']):05d}.png"
                target.write_bytes(png(*piece))
        count += 1
    return count


def main():
    for folder in (OUT / "sprites", OUT / "fonts"):
        if folder.exists():
            import shutil
            shutil.rmtree(folder)
    blob = WIN.read_bytes()
    table = chunk_map(blob)
    pages = decode_pages(blob, table["TXTR"])
    items = tpag_items(blob, table["TPAG"])
    sprite_count = sprites(blob, table["SPRT"], items, pages)
    font_count = fonts(blob, table["FONT"], items, pages)
    print(f"pages decoded : {len(pages)}")
    print(f"tpag records  : {len(items)}")
    print(f"sprite sets   : {sprite_count}")
    print(f"font sets     : {font_count}")
    print("OUTPUT:", OUT, flush=True)


if __name__ == "__main__":
    main()
