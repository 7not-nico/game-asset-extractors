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
| Balatro | LÖVE game appended to EXE | `tools/balatro/extract_balatro.py` | Read the appended ZIP and extract the full game tree |
| Talisman Digital Edition | Named ZIP asset packs | `tools/talisman/extract_talisman.py` | Extract all 25 ZIP packs with per-pack paths and manifest |
| VVVVVV | Standard ZIP plus loose locale trees | `tools/vvvvvv/extract_vvvvvv.py` | Extract `data.zip` and copy language and license files |
| NEO Scavenger | Custom engine, loose assets | `tools/neo_scavenger/extract_neoscavenger.py` | Package loose XML, PNG and mod files into a clean tree |
| Spelunky | Raw WAD + text WIX indexes | `tools/spelunky/extract_spelunky.py` | Carve textures and sounds by index and copy loose assets |
| Bloons TD 5 | Loose assets + JPNG images | `tools/bloons_td5/extract_bloons5.py` | Package the loose asset tree |
| Bloons TD 5 | JPNG (JPEG + PNG alpha) | `tools/bloons_td5/convert_jpng.py` | Composite RGB and alpha into PNG files |
| Planescape Torment EE | Infinity Engine KEY/BIF | `tools/planescape_torment/extract_pst.py` | Carve all KEY resources, copy loose locale/movie/override files |

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

### Balatro

- Edit `GAME` and `OUT` at the top of `extract_balatro.py` if the install path differs.
- Run `python3 tools/balatro/extract_balatro.py`.
- The whole game archive is a ZIP appended to `Balatro.exe`; Python's `zipfile` reads it directly.
- Outputs: `_extracted/assets/` preserving the LÖVE tree, plus `report.txt` and `manifest.csv`.

### Talisman Digital Edition

- Edit `GAME` at the top of `extract_talisman.py` if the install path differs.
- Run `python3 tools/talisman/extract_talisman.py`.
- All 25 `.zip` packs are standard ZIP archives; entries are written under `assets/<pack name>/`.
- DDS textures can be decoded on demand with Pillow; `.enc` files are preserved but not decoded.
- Outputs: `_extracted/assets/`, `raw/`, `manifest.csv` and `report.txt`.

### VVVVVV

- Edit `GAME` at the top of `extract_vvvvvv.py` if the install path differs.
- Run `python3 tools/vvvvvv/extract_vvvvvv.py`.
- `data.zip` is a standard ZIP; its entries are written under `_extracted/data/`.
- Loose `lang/` and `licenses/` trees are copied to `_extracted/lang/` and `_extracted/licenses/`.
- `.vvvvvv` files are XML level documents; outputs include `manifest.csv` and `report.txt`.

### NEO Scavenger

- Edit `GAME` at the top of `extract_neoscavenger.py` if the install path differs.
- Run `python3 tools/neo_scavenger/extract_neoscavenger.py`.
- Assets ship loose, so this is a packaging pass: `data/`, `img/`, `0/`, `SampleModFolder/` and root mod scripts are copied.
- The ELF executable is excluded because it is code, not asset data.
- Outputs: `_extracted/` with `manifest.csv` and `report.txt`.

### Spelunky

- Edit `ROOT` at the top of `extract_spelunky.py` if the install path differs.
- Run `python3 tools/spelunky/extract_spelunky.py`.
- WAD files are raw concatenations; `.wix` indexes provide `filename offset size` lines grouped by `!group NAME`.
- The tool carves entries into `wad/<archive>/<group>/<name>`, copies loose assets and extracts `webcache.zip`.
- Save files with `.sav` and `.bak` are excluded as user data.
- Outputs: `_extracted/assets/`, `wad/`, `webcache/`, `manifest.csv` and `report.txt`.

### Bloons TD 5

- Edit `GAME` at the top of `extract_bloons5.py` if the install path differs; the tool packages `Assets/` and root text files while excluding EXE, ORIG and DLL.
- Run `python3 tools/bloons_td5/extract_bloons5.py` first.
- Then run `python3 tools/bloons_td5/convert_jpng.py`.
- JPNG is JPEG RGB plus a grayscale PNG alpha mask and a 16-byte footer with magic `GEPJ` or `GNPJ`; both variants are supported.
- Outputs: `_extracted/Assets/`, `jpng_png/`, `manifest.csv`, `report.txt` and `jpng_report.txt`.

### Planescape Torment: Enhanced Edition

- Edit `GAME` at the top of `extract_pst.py` if the install path differs.
- Run `python3 tools/planescape_torment/extract_pst.py`.
- KEY locator layout: `bif = locator >> 20`, `index = locator & 0xFFFFF`.
- BIFF tile entries use locator `0x4000` and are parsed alongside file entries.
- Resources are written under `_extracted/resources/t<code>/` with magic-based extensions; loose files go to `_extracted/loose/`.
- Outputs also include `manifest.csv` and `report.txt`.

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
  balatro/
  talisman/
  vvvvvv/
  neo_scavenger/
  spelunky/
  bloons_td5/
  planescape_torment/
```
