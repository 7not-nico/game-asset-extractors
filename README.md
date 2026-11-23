# Game asset extractors

Asset extraction and format-probing scripts written for a set of installed GOG games.

No game assets, extracted output, or proprietary data are included — only the tools.

## Tools

| Game | Format | Tool | What it does |
| --- | --- | --- | --- |
| Banners of Ruin | Unity 2019, obfuscated Addressables bundles | `tools/banners_of_ruin/extract_all.py` | Full Unity bundle + root-file extraction with `.brm` name mapping |
| Banners of Ruin | Unity baked shaders | `tools/banners_of_ruin/extract_shaders.py` | Shader blob decode and export |
| 9th Dawn III | Unity 2022, serialized files + streamed FSB5 audio | `tools/ninth_dawn_iii/extract_9d.py` | PNG, text, font, MonoBehaviour JSON and report extraction |
| 9th Dawn III | Streamed FSB5 audio | `tools/ninth_dawn_iii/extract_9d_audio.py` | Dedicated single-file pass that decodes all AudioClips to WAV |
| Legend of Keepers | Unity 2019, Addressables + serialized files | `tools/legend_of_keepers/extract_lok.py` | Bundle/root extraction with catalog summary and raw StreamingAssets copies |
| Dead Cells | HashLink/Haxe, PAK v1 archive | `tools/dead_cells/unpak.py` | Streaming PAK indexer and checksum-verified carve |
| Dead Cells | BATL atlases + `data.cdb` | `tools/dead_cells/postprocess.py` | Sheet decode and atlas frame splitting |
| Dead Cells | BTMX maps | `tools/dead_cells/render_btmx.py` | Collision/link layer preview rendering |
| Dead Cells | BTMX markers | `tools/dead_cells/decode_markers.py` | Marker object name/property extraction |

Diagnostic probes for Dead Cells formats live beside the main tools under `tools/dead_cells/probe_*.py`.

## Requirements

- Python 3.12+
- `UnityPy`, `Pillow`, `lz4`, `TypeTreeGeneratorAPI` for the Unity tools
- `Pillow` for the Dead Cells tools
- `uv` and `git` are needed only for the external Xanadu Next extractor (not vendored here)

## Usage notes

- Each script carries its source-game paths as constants near the top; edit `GAME`, `OUT`, or equivalent before running on a different install.
- Run the production extractor before its companion pass: `extract_9d.py` then `extract_9d_audio.py`; `unpak.py` then `postprocess.py`.
- The Dead Cells PAK reader streams in chunks and verifies Adler32 per entry; do not load the archive into memory.
- `xanadu-next` is tracked as an external tool at https://github.com/Ell/xanadu-next rather than copied here.

## Layout

```
tools/
  banners_of_ruin/
  ninth_dawn_iii/
  legend_of_keepers/
  dead_cells/
```
