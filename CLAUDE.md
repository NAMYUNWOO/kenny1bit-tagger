# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Kenney 1-Bit Tile Tagger — a two-stage Python pipeline that splits a 1-bit pixel art tileset into individual tiles and tags them with semantic metadata using a Vision Language Model (Qwen3-VL). Output includes category, description, and WFC (Wave Function Collapse) edge compatibility data.

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
```

There are no tests or linting configured.

## Architecture

**Two-stage pipeline:**

1. **`split_tiles.py`** — Reads `Tilemap/tileset_legacy.png` (543×543px, 32×32 grid). Extracts non-empty 16×16 tiles with 1px spacing (stride=17). Outputs individual PNGs to `tiles/` and a `tile_index.json` with position metadata. Tiles are mapped to Tiled GID via `gid = row * COLS + col + 1`.

2. **`tag_tiles.py`** — Loads a Qwen3-VL model and runs two sequential VLM queries per tile: (1) category classification from 18 predefined categories, (2) edge-type analysis for 4 sides from 18 predefined edge types. Outputs `tile_tags.json`. Supports checkpoint-based resumability (saves every 50 tiles by default to `tile_tags_checkpoint.json`).

**Device auto-detection:** CUDA → MPS (Apple Silicon) → CPU fallback, handled in `get_device()`.

**VLM response parsing:** Attempts direct JSON parse first, then falls back to regex extraction of `{...}` from response text.

## Key Data

- **18 categories:** terrain, building, character, item, UI, decoration, nature, vehicle, weapon, tool, furniture, wall, floor, door, window, water, sky, underground
- **18 edge types:** empty, solid, ground_top, ground_bottom, wall_left, wall_right, wall_top, wall_bottom, grass, sky, water_top, water_bottom, trunk, foliage, roof, floor, platform, mixed
- **Source tileset:** `Tilemap/tileset_legacy.png`
- **Generated files (gitignored):** `tiles/`, `tile_index.json`, `tile_tags.json`, `tile_tags_checkpoint.json`

## Notes

- README is written in Korean.
- The `Tilemap/` directory contains Tiled editor integration files (`.tsx`, `.tmx` maps).
- The `Tilesheet/` directory contains alternative tileset format variants (colored, monochrome, transparent, packed).
