"""Tag tiles with category/description and WFC edge info using Qwen3-VL.

Supports both CUDA (NVIDIA GPU) and MPS (Apple Silicon) backends.
Default model: Qwen3-VL-8B-Instruct (recommended for 24GB+ VRAM).
"""

import argparse
import json
import time
from pathlib import Path

import torch
from PIL import Image
from tqdm import tqdm
from transformers import Qwen3VLForConditionalGeneration, AutoProcessor

BASE_DIR = Path(__file__).parent
TILES_DIR = BASE_DIR / "tiles"
INDEX_FILE = BASE_DIR / "tile_index.json"
OUTPUT_FILE = BASE_DIR / "tile_tags.json"
CHECKPOINT_FILE = BASE_DIR / "tile_tags_checkpoint.json"

MODELS = {
    "2b": "Qwen/Qwen3-VL-2B-Instruct",
    "8b": "Qwen/Qwen3-VL-8B-Instruct",
}


def get_device():
    """Auto-detect best available device."""
    if torch.cuda.is_available():
        name = torch.cuda.get_device_name(0)
        vram = torch.cuda.get_device_properties(0).total_mem / 1024**3
        print(f"CUDA device: {name} ({vram:.1f} GB)")
        return "cuda"
    elif torch.backends.mps.is_available():
        print("Using MPS (Apple Silicon)")
        return "mps"
    else:
        print("Using CPU (slow)")
        return "cpu"


def load_model(model_key: str):
    """Load model and processor."""
    model_id = MODELS[model_key]
    device = get_device()

    print(f"Loading {model_id}...")
    processor = AutoProcessor.from_pretrained(model_id)

    dtype = torch.float16 if device != "cpu" else torch.float32
    model = Qwen3VLForConditionalGeneration.from_pretrained(
        model_id,
        torch_dtype=dtype,
        device_map=device,
    )
    print(f"Model loaded on {device}")
    return model, processor


def query_vlm(model, processor, image: Image.Image, prompt: str) -> str:
    """Run a single VLM query on a tile image."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": prompt},
            ],
        }
    ]

    inputs = processor.apply_chat_template(
        messages,
        tokenize=True,
        add_generation_prompt=True,
        return_dict=True,
        return_tensors="pt",
    ).to(model.device)

    with torch.no_grad():
        output_ids = model.generate(**inputs, max_new_tokens=256, do_sample=False)

    generated_ids = [
        out_ids[len(in_ids):] for in_ids, out_ids in zip(inputs.input_ids, output_ids)
    ]
    return processor.batch_decode(generated_ids, skip_special_tokens=True)[0].strip()


CATEGORY_PROMPT = """This is a 16x16 pixel art tile from a game tileset.
Classify this tile and describe it briefly.

Reply ONLY in this exact JSON format, no other text:
{"category": "<one of: terrain, building, character, item, UI, decoration, nature, vehicle, weapon, tool, furniture, wall, floor, door, window, water, sky, underground>", "description": "<brief English description, 3-8 words>"}"""

EDGE_PROMPT = """This is a 16x16 pixel art tile from a game tileset.
Analyze the visual pattern at each of the 4 edges of this tile.
For each edge, describe what type of content meets the border.

Reply ONLY in this exact JSON format, no other text:
{"top": "<edge type>", "bottom": "<edge type>", "left": "<edge type>", "right": "<edge type>"}

Use these edge types: empty, solid, ground_top, ground_bottom, wall_left, wall_right, wall_top, wall_bottom, grass, sky, water_top, water_bottom, trunk, foliage, roof, floor, platform, mixed"""


def parse_json_response(text: str) -> dict | None:
    """Try to extract JSON from model response."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}") + 1
    if start >= 0 and end > start:
        try:
            return json.loads(text[start:end])
        except json.JSONDecodeError:
            pass

    return None


def load_checkpoint() -> dict:
    """Load checkpoint if it exists."""
    if CHECKPOINT_FILE.exists():
        data = json.loads(CHECKPOINT_FILE.read_text())
        print(f"Resuming from checkpoint: {len(data)} tiles already tagged")
        return data
    return {}


def save_checkpoint(results: dict):
    """Save intermediate results."""
    CHECKPOINT_FILE.write_text(json.dumps(results, indent=2))


def main():
    parser = argparse.ArgumentParser(description="Tag tiles with VLM")
    parser.add_argument("--model", choices=["2b", "8b"], default="8b",
                        help="Model size (default: 8b, use 2b for <16GB VRAM)")
    parser.add_argument("--checkpoint-interval", type=int, default=50,
                        help="Save checkpoint every N tiles (default: 50)")
    parser.add_argument("--reset", action="store_true",
                        help="Ignore existing checkpoint and start fresh")
    args = parser.parse_args()

    if not INDEX_FILE.exists():
        print("Error: tile_index.json not found. Run split_tiles.py first.")
        return

    index = json.loads(INDEX_FILE.read_text())
    tiles = index["tiles"]
    print(f"Found {len(tiles)} tiles to tag")

    model, processor = load_model(args.model)

    tagged = {} if args.reset else load_checkpoint()

    start_time = time.time()
    errors = []
    already_done = sum(1 for t in tiles if t["id"] in tagged)

    for i, tile_info in enumerate(tqdm(tiles, desc="Tagging tiles", initial=already_done)):
        tile_id = tile_info["id"]

        if tile_id in tagged:
            continue

        img_path = TILES_DIR / tile_info["filename"]
        if not img_path.exists():
            errors.append({"id": tile_id, "error": "file not found"})
            continue

        image = Image.open(img_path).convert("RGB")

        cat_response = query_vlm(model, processor, image, CATEGORY_PROMPT)
        cat_data = parse_json_response(cat_response)

        edge_response = query_vlm(model, processor, image, EDGE_PROMPT)
        edge_data = parse_json_response(edge_response)

        result = {
            "id": tile_id,
            "gid": tile_info["gid"],
            "row": tile_info["row"],
            "col": tile_info["col"],
            "pixel_x": tile_info["pixel_x"],
            "pixel_y": tile_info["pixel_y"],
        }

        if cat_data:
            result["category"] = cat_data.get("category", "unknown")
            result["description"] = cat_data.get("description", "")
        else:
            result["category"] = "unknown"
            result["description"] = ""
            result["raw_category_response"] = cat_response

        if edge_data:
            result["edges"] = {
                "top": edge_data.get("top", "unknown"),
                "bottom": edge_data.get("bottom", "unknown"),
                "left": edge_data.get("left", "unknown"),
                "right": edge_data.get("right", "unknown"),
            }
        else:
            result["edges"] = {"top": "unknown", "bottom": "unknown", "left": "unknown", "right": "unknown"}
            result["raw_edge_response"] = edge_response

        tagged[tile_id] = result

        if (i + 1) % args.checkpoint_interval == 0:
            save_checkpoint(tagged)
            elapsed = time.time() - start_time
            done = i + 1 - already_done
            rate = done / elapsed if elapsed > 0 else 0
            remaining = (len(tiles) - i - 1) / rate if rate > 0 else 0
            tqdm.write(f"  Checkpoint saved. Rate: {rate:.1f} tiles/s, ETA: {remaining / 60:.1f} min")

    save_checkpoint(tagged)

    output = {
        "metadata": index["metadata"],
        "total_tagged": len(tagged),
        "errors": errors,
        "tiles": [tagged[t["id"]] for t in tiles if t["id"] in tagged],
    }

    OUTPUT_FILE.write_text(json.dumps(output, indent=2))
    elapsed = time.time() - start_time
    print(f"\nDone! Tagged {len(tagged)} tiles in {elapsed / 60:.1f} minutes")
    print(f"Results saved to {OUTPUT_FILE}")

    if CHECKPOINT_FILE.exists():
        CHECKPOINT_FILE.unlink()
        print("Checkpoint file removed")


if __name__ == "__main__":
    main()
