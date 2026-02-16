# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kenney 1-Bit Tile Tagger — a multi-stage Python pipeline that splits a 1-bit pixel art tileset into individual tiles, tags them with semantic metadata using a Vision Language Model (Qwen3-VL), extracts tile adjacency rules from sample maps, and provides a GUI editor for map building and tag/adjacency refinement. Output includes category, description, WFC (Wave Function Collapse) edge compatibility data, and probabilistic adjacency rules.

## Commands

```bash
# Install dependencies (requires Python 3, CUDA recommended)
pip install -r requirements.txt

# Stage 1: Split tileset into individual 16x16 tile PNGs
python split_tiles.py

# Stage 2: Tag tiles with VLM
python tag_tiles.py              # 8B model (default, needs 24GB+ VRAM)
python tag_tiles.py --model 2b   # 2B model (needs ~5GB VRAM)
python tag_tiles.py --reset      # Ignore checkpoint, start fresh
python tag_tiles.py --checkpoint-interval 100  # Custom checkpoint interval

# Stage 3: Extract adjacency rules from TMX sample maps
python extract_adjacency.py
python extract_adjacency.py --min-count 2      # Filter low-frequency pairs

# GUI Tile Editor (map building, tag editing, adjacency update)
python tile_editor.py
```

There are no tests or linting configured.

## Architecture

**Multi-stage pipeline:**

1. **`split_tiles.py`** — Reads `Tilemap/tileset_legacy.png` (543×543px, 32×32 grid). Extracts non-empty 16×16 tiles with 1px spacing (stride=17). Outputs individual PNGs to `tiles/` and a `tile_index.json` with position metadata. Tiles are mapped to Tiled GID via `gid = row * COLS + col + 1`.

2. **`tag_tiles.py`** — Loads a Qwen3-VL model and runs two sequential VLM queries per tile: (1) category classification from 18 predefined categories, (2) edge-type analysis for 4 sides from 18 predefined edge types. Outputs `tile_tags.json`. Supports checkpoint-based resumability (saves every 50 tiles by default to `tile_tags_checkpoint.json`).

3. **`extract_adjacency.py`** — Parses `Tilemap/*.tmx` sample maps and collects 4-directional (right/bottom/left/top) adjacency pair counts. Preserves Tiled flip flags (H/V/D) so flipped tile variants are treated as distinct. Outputs `tile_adjacency.json` with metadata, tile_info, and adjacency data. Skips GID 0 (empty) and GID 1 (background).

4. **`tile_editor.py`** — Tkinter GUI with three panels: tile palette (left, filterable by category/search), map canvas (center, click-to-place/right-click-to-erase), and tag editor (right, edit category/description/edges + adjacency-based neighbor recommendations). Supports saving/loading maps as JSON. Can update `tile_adjacency.json` by extracting adjacency from the editor map canvas and merging with existing data.

**Device auto-detection:** CUDA → MPS (Apple Silicon) → CPU fallback, handled in `get_device()`.

**VLM response parsing:** Attempts direct JSON parse first, then falls back to regex extraction of `{...}` from response text.

**Editor keyboard shortcuts:** `Ctrl+Shift+S` / `Cmd+Shift+S` (Save All Tags), `Ctrl+Shift+A` / `Cmd+Shift+A` (Update Adjacency from Map).

## Key Data

- **18 categories:** terrain, building, character, item, UI, decoration, nature, vehicle, weapon, tool, furniture, wall, floor, door, window, water, sky, underground
- **18 edge types:** empty, solid, ground_top, ground_bottom, wall_left, wall_right, wall_top, wall_bottom, grass, sky, water_top, water_bottom, trunk, foliage, roof, floor, platform, mixed
- **Source tileset:** `Tilemap/tileset_legacy.png`
- **Generated files (gitignored):** `tiles/`, `tile_index.json`, `tile_tags.json`, `tile_tags_checkpoint.json`
- **Adjacency file:** `tile_adjacency.json` — `{metadata, tile_info, adjacency}` structure; adjacency keys are GID strings (plain or with flip flags like `"170:HV"`)

## Notes

- README is written in Korean.
- The `Tilemap/` directory contains Tiled editor integration files (`.tsx`, `.tmx` maps).
- The `Tilesheet/` directory contains alternative tileset format variants (colored, monochrome, transparent, packed).
