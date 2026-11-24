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
| Cross Blitz | Unity 2020 IL2CPP, `data.unity3d` + Addressables | `tools/cross_blitz/extract_cb.py` | PNG, text, font, MonoBehaviour JSON and report extraction |
| Cross Blitz | Streamed FSB5 + bundle audio | `tools/cross_blitz/extract_cb_audio.py` | Dedicated audio pass with whole-bank FSB5 fallback |
| Slay the Spire | Java/libGDX asset JAR | `tools/slay_the_spire/extract_sts.py` | JAR asset extraction preserving original paths |
| Slay the Spire | libGDX text atlases | `tools/slay_the_spire/split_atlases.py` | Atlas page cropping and rotation-corrected frame export |
| SteamWorld Heist | Custom engine, ZIP `.impak` + zlib `.z` | `tools/steamworld_heist/extract_steamworld.py` | Loose asset copy, stream inflation, archive unzip and atlas frame splitting |
| Sunless Skies | Unity 2019 Mono, many serialized files + FSB5 audio | `tools/sunless_skies/extract_sunless.py` | PNG, text, font, MonoBehaviour JSON and report extraction |
| Sunless Skies | Streamed FSB5 audio | `tools/sunless_skies/extract_sunless_audio.py` | Dedicated audio pass with WAV name deduplication |

Diagnostic probes for Dead Cells formats live beside the main tools under `tools/dead_cells/probe_*.py`.

## Requirements

- Python 3.12+
- Install Unity-tool dependencies with `python3 -m pip install --user --break-system-packages UnityPy Pillow lz4 TypeTreeGeneratorAPI`
- `UnityPy`, `Pillow`, `lz4`, `TypeTreeGeneratorAPI` for the Unity tools
- `Pillow` for the Dead Cells tools
- `fmod_toolkit` for Cross Blitz audio decoding
- `uv` and `git` are needed only for the external Xanadu Next extractor (not vendored here)

## Usage notes

- Each script carries its source-game paths as constants near the top; edit `GAME`, `OUT`, or equivalent before running on a different install.
- Run the production extractor before its companion pass: `extract_9d.py` then `extract_9d_audio.py`; `unpak.py` then `postprocess.py`; `extract_cb.py` then `extract_cb_audio.py`.
- The Dead Cells PAK reader streams in chunks and verifies Adler32 per entry; do not load the archive into memory.
- `xanadu-next` is tracked as an external tool at https://github.com/Ell/xanadu-next rather than copied here.

## Quickstart by game

### Banners of Ruin

- Edit `GAME`, `BUNDLES` and `OUT` at the top of `extract_all.py`; this build is Unity `2019.4.22f1`.
- Run `python3 tools/banners_of_ruin/extract_all.py`.
- Optional shader pass: `python3 tools/banners_of_ruin/extract_shaders.py`.
- Output lands in `_extracted/` with `mapping.json`, `manifest.csv` and `report.txt`.

### 9th Dawn III

- Edit `GAME`, `OUT` and `VERSION` in both scripts; the build is Unity `2022.3.62f2`.
- Run the main pass first: `python3 tools/ninth_dawn_iii/extract_9d.py`.
- Then run the audio pass: `python3 tools/ninth_dawn_iii/extract_9d_audio.py`.
- The audio pass is separate because decoding streamed audio inside the full pass fails with `FmodError: FORMAT`.
- `run_9d_extraction.sh` runs both passes in order.

### Legend of Keepers

- Edit `GAME`, `OUT`, `BUNDLES` and `STREAM` in `extract_lok.py`; the build is Unity `2019.4.18f1`.
- Run `python3 tools/legend_of_keepers/extract_lok.py`.
- The script summarizes the Addressables catalog, copies non-bundle StreamingAssets files verbatim and writes `pak`-style reports into `_extracted/`.

### Dead Cells

- Only `Pillow` is required. Edit `BASE`/`GAME` paths in the scripts.
- Index first: `python3 tools/dead_cells/unpak.py --index-only`.
- Carve with verification: `python3 tools/dead_cells/unpak.py`.
- Decode data: `python3 tools/dead_cells/postprocess.py`.
- Optional: `render_btmx.py` for collision previews and `decode_markers.py` for object markers.
- Outputs: `_extracted/raw/`, `data/`, `atlas_frames/`, `map_previews/` and `markers/`.

### Cross Blitz

- Edit `GAME`, `OUT` and `BUNDLES` at the top of both scripts; the build is Unity `2020.3.4f1` IL2CPP.
- No type-tree generator is used: the IL2CPP build embeds type trees in its serialized files.
- Run the main pass first: `python3 tools/cross_blitz/extract_cb.py`.
- Then run the audio pass: `python3 tools/cross_blitz/extract_cb_audio.py`.
- The audio pass uses UnityPy samples for bundle audio and a whole-bank FSB5 fallback for `espannol`.
- Outputs: `_extracted/raw/`, `audio/`, `mapping.json`, `manifest.csv` and `report.txt`.

### Slay the Spire

- Edit `ROOT` and `JAR` at the top of both scripts; assets live in `desktop-1.0.jar`.
- Extract assets first: `python3 tools/slay_the_spire/extract_sts.py`.
- Split atlases second: `python3 tools/slay_the_spire/split_atlases.py`.
- `extract_sts.py` skips Java classes, native libraries and JAR metadata.
- `split_atlases.py` parses libGDX text atlases and corrects clockwise-stored rotated regions.
- Outputs: `_extracted/assets/`, `_extracted/atlas_frames/`, `report.txt`, `manifest.csv` and `atlas_report.txt`.

### SteamWorld Heist

- Edit `GAME` at the top of `extract_steamworld.py`; output goes to a sibling `_extracted/` directory.
- Run `python3 tools/steamworld_heist/extract_steamworld.py`.
- `.impak` files are ZIP archives and `.z` files are a four-byte uncompressed size plus a zlib stream.
- The tool also parses the inflated `atlases.map` and crops named frames from both loose and archived atlas pages.
- Avoid glob patterns containing `[8888]`; page PNGs are resolved by exact filename.
- Outputs: `_extracted/assets/`, `raw_z/`, `impak/`, `atlas_frames/`, `report.txt` and `manifest.csv`.

### Sunless Skies

- Edit `GAME`, `OUT` and `VERSION` at the top of both scripts; the build is Unity `2019.4.2f1` Mono.
- Run the main pass first: `python3 tools/sunless_skies/extract_sunless.py`.
- Then run the audio pass: `python3 tools/sunless_skies/extract_sunless_audio.py`.
- The audio pass decodes streamed clips through `AudioClip.samples` with a whole-bank FSB5 fallback and deduplicates WAV names.
- Outputs: `_extracted/raw/`, `audio/`, `mapping.json`, `manifest.csv` and `report.txt`.

## Layout

```
tools/
  banners_of_ruin/
  ninth_dawn_iii/
  legend_of_keepers/
  dead_cells/
  cross_blitz/
  slay_the_spire/
  steamworld_heist/
  sunless_skies/
```
