"""Extract tile adjacency rules from TMX sample maps.

Parses Tiled TMX maps to collect observed tile neighbor pairs,
producing probabilistic adjacency data for Wave Function Collapse.
Flip flags (H/V/D) are preserved so flipped variants are treated as distinct tiles.
"""

import argparse
import json
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

TILEMAP_DIR = Path(__file__).parent / "Tilemap"
INDEX_FILE = Path(__file__).parent / "tile_index.json"
DEFAULT_OUTPUT = Path(__file__).parent / "tile_adjacency.json"

# Tiled flip flags (upper bits of raw GID)
FLIPPED_HORIZONTALLY = 0x80000000
FLIPPED_VERTICALLY = 0x40000000
FLIPPED_DIAGONALLY = 0x20000000
GID_MASK = 0x1FFFFFFF

# GID 1 (tile_0_0) is the empty background tile used to fill unused space.
# Including it pollutes adjacency data since it neighbors almost everything.
BACKGROUND_GID = 1

# Directions: (name, row_offset, col_offset)
DIRECTIONS = [
    ("right", 0, 1),
    ("bottom", 1, 0),
    ("left", 0, -1),
    ("top", -1, 0),
]


def flip_flags_str(raw_gid: int) -> str:
    """Return flip flags as a short string like 'H', 'HV', 'VD', or '' (no flip)."""
    flags = ""
    if raw_gid & FLIPPED_HORIZONTALLY:
        flags += "H"
    if raw_gid & FLIPPED_VERTICALLY:
        flags += "V"
    if raw_gid & FLIPPED_DIAGONALLY:
        flags += "D"
    return flags


def tile_key(raw_gid: int) -> str:
    """Return a string key combining base GID and flip flags, e.g. '170:HV' or '17'."""
    base = raw_gid & GID_MASK
    flags = flip_flags_str(raw_gid)
    if flags:
        return f"{base}:{flags}"
    return str(base)


def parse_tmx(tmx_path: Path) -> list[list[int]]:
    """Parse a TMX file and return a 2D grid of raw GIDs (flip flags preserved)."""
    tree = ET.parse(tmx_path)
    root = tree.getroot()
    width = int(root.attrib["width"])
    height = int(root.attrib["height"])

    layer = root.find(".//layer/data")
    if layer is None or layer.attrib.get("encoding") != "csv":
        raise ValueError(f"{tmx_path.name}: expected CSV-encoded layer data")

    raw_values = [int(v.strip()) for v in layer.text.strip().split(",") if v.strip()]

    grid = []
    for row in range(height):
        row_data = []
        for col in range(width):
            row_data.append(raw_values[row * width + col])
        grid.append(row_data)

    return grid


def collect_adjacency(grids: dict[str, list[list[int]]]) -> dict[str, dict[str, dict[str, int]]]:
    """Collect adjacency pair counts from all parsed grids, keyed by tile_key."""
    adj = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))

    for grid in grids.values():
        height = len(grid)
        width = len(grid[0])
        for r in range(height):
            for c in range(width):
                raw = grid[r][c]
                base = raw & GID_MASK
                if base == 0 or base == BACKGROUND_GID:
                    continue
                key = tile_key(raw)
                for direction, dr, dc in DIRECTIONS:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < height and 0 <= nc < width:
                        n_raw = grid[nr][nc]
                        n_base = n_raw & GID_MASK
                        if n_base == 0 or n_base == BACKGROUND_GID:
                            continue
                        adj[key][direction][tile_key(n_raw)] += 1

    return adj


def build_gid_to_tile_id(index_path: Path) -> dict[int, str]:
    """Load tile_index.json and return a GID -> tile_id mapping."""
    if not index_path.exists():
        return {}
    index = json.loads(index_path.read_text())
    return {t["gid"]: t["id"] for t in index["tiles"]}


def key_to_label(key: str, gid_to_tile_id: dict[int, str]) -> str:
    """Convert a tile key like '170:HV' to 'tile_5_9:HV' for display."""
    if ":" in key:
        gid_str, flags = key.split(":", 1)
        tid = gid_to_tile_id.get(int(gid_str), gid_str)
        return f"{tid}:{flags}"
    tid = gid_to_tile_id.get(int(key), key)
    return tid


def main():
    parser = argparse.ArgumentParser(description="Extract tile adjacency rules from TMX maps")
    parser.add_argument("--min-count", type=int, default=1,
                        help="Minimum occurrence count to include a neighbor (default: 1)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="Output JSON file path")
    args = parser.parse_args()

    tmx_files = sorted(TILEMAP_DIR.glob("*.tmx"))
    if not tmx_files:
        print("No TMX files found in Tilemap/")
        return

    print(f"Found {len(tmx_files)} TMX files:")
    grids = {}
    for tmx_path in tmx_files:
        grid = parse_tmx(tmx_path)
        grids[tmx_path.name] = grid
        print(f"  {tmx_path.name}: {len(grid[0])}x{len(grid)} grid")

    adj = collect_adjacency(grids)

    gid_to_tile_id = build_gid_to_tile_id(INDEX_FILE)

    # Filter by min-count and sort by count descending
    total_pairs = 0
    adjacency_out = {}
    for key in sorted(adj):
        directions = {}
        for direction in ["right", "bottom", "left", "top"]:
            neighbors = {
                nkey: count
                for nkey, count in sorted(adj[key][direction].items(), key=lambda x: -x[1])
                if count >= args.min_count
            }
            if neighbors:
                directions[direction] = neighbors
                total_pairs += sum(neighbors.values())
        if directions:
            adjacency_out[key] = directions

    # Collect all observed tile keys with their base GID and flags
    all_keys = set(adjacency_out.keys())
    for dirs in adjacency_out.values():
        for neighbors in dirs.values():
            all_keys.update(neighbors.keys())

    tile_info = {}
    for key in sorted(all_keys):
        if ":" in key:
            gid_str, flags = key.split(":", 1)
        else:
            gid_str, flags = key, ""
        gid = int(gid_str)
        info = {"gid": gid, "flip": flags}
        if gid in gid_to_tile_id:
            info["tile_id"] = gid_to_tile_id[gid]
        tile_info[key] = info

    output = {
        "metadata": {
            "source_maps": [p.name for p in tmx_files],
            "total_adjacency_pairs": total_pairs,
            "unique_tiles_observed": len(adjacency_out),
            "min_count_filter": args.min_count,
            "key_format": "GID or GID:FLAGS where FLAGS is combination of H, V, D",
            "flip_flags": {
                "H": {"name": "Horizontal flip", "effect": "좌우 반전"},
                "V": {"name": "Vertical flip", "effect": "상하 반전"},
                "D": {"name": "Diagonal flip", "effect": "대각선 반전 (X↔Y 축 교환)"},
                "HV": {"effect": "180도 회전"},
                "HD": {"effect": "시계방향 90도 회전"},
                "VD": {"effect": "반시계방향 90도 회전"},
                "HVD": {"effect": "대각선 반전 (우상↔좌하 축)"},
            },
        },
        "tile_info": tile_info,
        "adjacency": adjacency_out,
    }

    args.output.write_text(json.dumps(output, indent=2))
    print(f"\nResults:")
    print(f"  Unique tiles observed: {len(adjacency_out)}")
    print(f"  Total adjacency pairs: {total_pairs}")
    print(f"  Output: {args.output}")

    # Print a sample for verification
    for sample_key in ["17", "170:VD"]:
        if sample_key in adjacency_out:
            label = key_to_label(sample_key, gid_to_tile_id)
            print(f"\nSample — {sample_key} ({label}):")
            for d, neighbors in adjacency_out[sample_key].items():
                top3 = list(neighbors.items())[:3]
                top3_display = {k: v for k, v in top3}
                print(f"  {d}: {top3_display}")


if __name__ == "__main__":
    main()
