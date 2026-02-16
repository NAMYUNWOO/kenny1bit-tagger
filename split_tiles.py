"""Split tileset_legacy.png into individual 16x16 tiles.

Uses the same tileset referenced by the Tiled TMX maps (tileset_colored.tsx):
  - tileset_legacy.png, 543x543px, 32x32 grid = 1024 tiles, 16x16px, 1px spacing
"""

import json
from pathlib import Path
from PIL import Image

TILESHEET = Path(__file__).parent / "Tilemap" / "tileset_legacy.png"
OUT_DIR = Path(__file__).parent / "tiles"
INDEX_FILE = Path(__file__).parent / "tile_index.json"

TILE_SIZE = 16
SPACING = 1
STRIDE = TILE_SIZE + SPACING  # 17

COLS = 32
ROWS = 32


def is_empty_tile(tile: Image.Image) -> bool:
    """Check if a tile is fully transparent (no visible content)."""
    rgba = tile.convert("RGBA")
    pixels = list(rgba.getdata())
    return all(p[3] == 0 for p in pixels)


def main():
    OUT_DIR.mkdir(exist_ok=True)

    img = Image.open(TILESHEET).convert("RGBA")
    print(f"Loaded {TILESHEET.name}: {img.size}, expected grid {COLS}x{ROWS} = {COLS * ROWS} tiles")

    tiles = []
    skipped = 0

    for row in range(ROWS):
        for col in range(COLS):
            x = col * STRIDE
            y = row * STRIDE
            tile = img.crop((x, y, x + TILE_SIZE, y + TILE_SIZE))

            if is_empty_tile(tile):
                skipped += 1
                continue

            tile_id = f"tile_{row}_{col}"
            filename = f"{tile_id}.png"
            tile.save(OUT_DIR / filename)

            # Tiled GID = row * COLS + col + 1 (1-indexed)
            gid = row * COLS + col + 1

            tiles.append({
                "id": tile_id,
                "gid": gid,
                "row": row,
                "col": col,
                "pixel_x": x,
                "pixel_y": y,
                "filename": filename,
            })

    index = {
        "metadata": {
            "source": "tileset_legacy.png",
            "tile_size": TILE_SIZE,
            "spacing": SPACING,
            "grid": [COLS, ROWS],
            "total_possible": COLS * ROWS,
        },
        "total_extracted": len(tiles),
        "skipped_empty": skipped,
        "tiles": tiles,
    }

    INDEX_FILE.write_text(json.dumps(index, indent=2))
    print(f"Extracted {len(tiles)} tiles, skipped {skipped} empty tiles")
    print(f"Saved to {OUT_DIR}/ and {INDEX_FILE}")


if __name__ == "__main__":
    main()
