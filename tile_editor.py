"""Tile Editor GUI — place tiles on a map and edit VLM-generated tags.

Usage:
    python tile_editor.py
"""

import json
import sys
import tkinter as tk
from tkinter import ttk, filedialog, simpledialog, messagebox
from collections import defaultdict
from pathlib import Path

IS_MAC = sys.platform == "darwin"
MOD = "Command" if IS_MAC else "Control"
MOD_LABEL = "Cmd" if IS_MAC else "Ctrl"

from PIL import Image, ImageTk

BASE_DIR = Path(__file__).parent
TILES_DIR = BASE_DIR / "tiles"
INDEX_FILE = BASE_DIR / "tile_index.json"
TAGS_FILE = BASE_DIR / "tile_tags.json"
ADJACENCY_FILE = BASE_DIR / "tile_adjacency.json"

SCALE = 2
TILE_SIZE = 16
SCALED = TILE_SIZE * SCALE  # 32

PALETTE_COLS = 32
DEFAULT_MAP_W = 32
DEFAULT_MAP_H = 24

CATEGORIES = [
    "terrain", "building", "character", "item", "UI", "decoration",
    "nature", "vehicle", "weapon", "tool", "furniture", "wall",
    "floor", "door", "window", "water", "sky", "underground",
]

EDGE_TYPES = [
    "empty", "solid", "ground_top", "ground_bottom",
    "wall_left", "wall_right", "wall_top", "wall_bottom",
    "grass", "sky", "water_top", "water_bottom",
    "trunk", "foliage", "roof", "floor", "platform", "mixed",
]


class TileEditorApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Kenney 1-Bit Tile Editor")
        self.root.geometry("1280x800")

        # Data
        self.tile_list: list[dict] = []       # from tile_index.json
        self.tags: dict[str, dict] = {}       # tile_id -> {category, description, edges}
        self.images: dict[str, ImageTk.PhotoImage] = {}  # tile_id -> scaled PhotoImage
        self.pil_images: dict[str, Image.Image] = {}     # tile_id -> PIL Image (scaled)
        self.gid_to_tile_id: dict[int, str] = {}
        self.selected_tile: str | None = None
        self.grid: list[list[int]] = []       # map grid[row][col] = gid (0=empty)
        self.map_w = DEFAULT_MAP_W
        self.map_h = DEFAULT_MAP_H
        self.palette_tile_ids: list[str] = []  # currently displayed tile ids in palette
        self.adjacency: dict = {}             # from tile_adjacency.json
        self.tile_id_to_gid: dict[str, int] = {}

        self._load_data()
        self._build_menu()
        self._build_ui()
        self.new_map_silent(self.map_w, self.map_h)

    # ─── Data loading ────────────────────────────────────────────────

    def _load_data(self):
        # Load tile index
        if INDEX_FILE.exists():
            index = json.loads(INDEX_FILE.read_text())
            self.tile_list = index["tiles"]
        else:
            messagebox.showwarning("Warning", "tile_index.json not found. Run split_tiles.py first.")
            self.tile_list = []

        # Load tags
        if TAGS_FILE.exists():
            tag_data = json.loads(TAGS_FILE.read_text())
            for t in tag_data.get("tiles", []):
                self.tags[t["id"]] = {
                    "category": t.get("category", ""),
                    "description": t.get("description", ""),
                    "edges": t.get("edges", {"top": "empty", "bottom": "empty", "left": "empty", "right": "empty"}),
                }

        # Build gid mapping
        for t in self.tile_list:
            self.gid_to_tile_id[t["gid"]] = t["id"]

        # Build reverse mapping tile_id -> gid
        for t in self.tile_list:
            self.tile_id_to_gid[t["id"]] = t["gid"]

        # Load adjacency data
        if ADJACENCY_FILE.exists():
            adj_data = json.loads(ADJACENCY_FILE.read_text())
            self.adjacency = adj_data.get("adjacency", {})

        # Load tile images
        for t in self.tile_list:
            tile_id = t["id"]
            img_path = TILES_DIR / t["filename"]
            if img_path.exists():
                pil = Image.open(img_path).convert("RGBA")
                pil_scaled = pil.resize((SCALED, SCALED), Image.NEAREST)
                self.pil_images[tile_id] = pil_scaled
                self.images[tile_id] = ImageTk.PhotoImage(pil_scaled)

    # ─── Menu ────────────────────────────────────────────────────────

    def _build_menu(self):
        menubar = tk.Menu(self.root)

        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="New Map...", command=self.new_map)
        file_menu.add_command(label="Open Map...", command=self.load_map)
        file_menu.add_command(label="Save Map...", command=self.save_map)
        file_menu.add_separator()
        file_menu.add_command(label="Save All Tags", command=self.save_tags,
                              accelerator=f"{MOD_LABEL}+Shift+S")
        file_menu.add_command(label="Update Adjacency from Map", command=self.update_adjacency,
                              accelerator=f"{MOD_LABEL}+Shift+A")
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)
        menubar.add_cascade(label="File", menu=file_menu)

        # Keyboard shortcuts
        self.root.bind_all(f"<{MOD}-Shift-s>", lambda e: self.save_tags())
        self.root.bind_all(f"<{MOD}-Shift-a>", lambda e: self.update_adjacency())

        self.root.config(menu=menubar)

    # ─── UI layout ───────────────────────────────────────────────────

    def _build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        # Left: palette
        left = ttk.Frame(main, width=300)
        main.add(left, weight=0)
        self._build_palette(left)

        # Center: map canvas
        center = ttk.Frame(main)
        main.add(center, weight=1)
        self._build_canvas(center)

        # Right: tag editor
        right = ttk.Frame(main, width=280)
        main.add(right, weight=0)
        self._build_tag_editor(right)

        # Unified mouse-wheel scroll: route to whichever scrollable canvas
        # the mouse is currently over.
        self._hover_canvas: tk.Canvas | None = None
        self.palette_canvas.bind("<Enter>", lambda e: self._set_hover(self.palette_canvas))
        self.palette_canvas.bind("<Leave>", lambda e: self._set_hover(None))
        self._tag_canvas.bind("<Enter>", lambda e: self._set_hover(self._tag_canvas))
        self._tag_canvas.bind("<Leave>", lambda e: self._set_hover(None))

        self.root.bind_all("<MouseWheel>", self._on_mousewheel)
        self.root.bind_all("<Button-4>", self._on_mousewheel)
        self.root.bind_all("<Button-5>", self._on_mousewheel)

    def _set_hover(self, canvas: tk.Canvas | None):
        self._hover_canvas = canvas

    def _on_mousewheel(self, event):
        if self._hover_canvas is None:
            return
        if event.num == 4:
            self._hover_canvas.yview_scroll(-3, "units")
        elif event.num == 5:
            self._hover_canvas.yview_scroll(3, "units")
        elif event.delta:
            self._hover_canvas.yview_scroll(-1 * (event.delta // 120), "units")

    # ─── Palette (left) ─────────────────────────────────────────────

    def _build_palette(self, parent: ttk.Frame):
        # Filter row
        filter_frame = ttk.Frame(parent)
        filter_frame.pack(fill=tk.X, padx=4, pady=4)

        ttk.Label(filter_frame, text="Category:").pack(side=tk.LEFT)
        self.cat_filter_var = tk.StringVar(value="All")
        cat_cb = ttk.Combobox(filter_frame, textvariable=self.cat_filter_var,
                              values=["All"] + CATEGORIES, state="readonly", width=14)
        cat_cb.pack(side=tk.LEFT, padx=4)
        cat_cb.bind("<<ComboboxSelected>>", lambda e: self._refresh_palette())

        # Search
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar()
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=16)
        search_entry.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        self.search_var.trace_add("write", lambda *_: self._refresh_palette())

        # Scrollable canvas for tiles
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        self.palette_canvas = tk.Canvas(container, bg="#333333")
        scrollbar = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.palette_canvas.yview)
        self.palette_canvas.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.palette_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.palette_inner = ttk.Frame(self.palette_canvas)
        self.palette_canvas.create_window((0, 0), window=self.palette_inner, anchor="nw")
        self.palette_inner.bind("<Configure>",
                                lambda e: self.palette_canvas.configure(scrollregion=self.palette_canvas.bbox("all")))

        self._refresh_palette()

    def _refresh_palette(self):
        for w in self.palette_inner.winfo_children():
            w.destroy()

        cat = self.cat_filter_var.get()
        search = self.search_var.get().lower().strip()

        filtered = []
        for t in self.tile_list:
            tid = t["id"]
            tag = self.tags.get(tid, {})
            if cat != "All" and tag.get("category", "") != cat:
                continue
            if search:
                desc = tag.get("description", "").lower()
                if search not in tid.lower() and search not in desc:
                    continue
            filtered.append(tid)

        self.palette_tile_ids = filtered
        self.palette_labels: dict[str, tk.Label] = {}

        for i, tid in enumerate(filtered):
            r, c = divmod(i, PALETTE_COLS)
            if tid in self.images:
                lbl = tk.Label(self.palette_inner, image=self.images[tid],
                               bd=1, relief=tk.FLAT, bg="#333333")
                lbl.grid(row=r, column=c, padx=0, pady=0)
                lbl.bind("<Button-1>", lambda e, t=tid: self._on_palette_click(t))
                self.palette_labels[tid] = lbl

        # Re-highlight selected
        if self.selected_tile and self.selected_tile in self.palette_labels:
            self.palette_labels[self.selected_tile].configure(relief=tk.SOLID, bg="#FFD700")

    def _on_palette_click(self, tile_id: str):
        # Remove old highlight
        if self.selected_tile and self.selected_tile in self.palette_labels:
            self.palette_labels[self.selected_tile].configure(relief=tk.FLAT, bg="#333333")

        self.selected_tile = tile_id

        # Add highlight
        if tile_id in self.palette_labels:
            self.palette_labels[tile_id].configure(relief=tk.SOLID, bg="#FFD700")

        self._show_tile_tags(tile_id)

    # ─── Map canvas (center) ────────────────────────────────────────

    def _build_canvas(self, parent: ttk.Frame):
        container = ttk.Frame(parent)
        container.pack(fill=tk.BOTH, expand=True)

        self.map_canvas = tk.Canvas(container, bg="#1a1a1a")
        h_scroll = ttk.Scrollbar(container, orient=tk.HORIZONTAL, command=self.map_canvas.xview)
        v_scroll = ttk.Scrollbar(container, orient=tk.VERTICAL, command=self.map_canvas.yview)
        self.map_canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        v_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        h_scroll.pack(side=tk.BOTTOM, fill=tk.X)
        self.map_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.map_canvas.bind("<Button-1>", self._on_canvas_click)
        self.map_canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.map_canvas.bind("<Button-3>", self._on_canvas_right_click)
        self.map_canvas.bind("<B3-Motion>", self._on_canvas_right_click)

    def _on_canvas_click(self, event):
        self._place_tile(event)

    def _on_canvas_drag(self, event):
        self._place_tile(event)

    def _place_tile(self, event):
        if not self.selected_tile:
            return
        col = int(self.map_canvas.canvasx(event.x)) // SCALED
        row = int(self.map_canvas.canvasy(event.y)) // SCALED
        if 0 <= row < self.map_h and 0 <= col < self.map_w:
            # Find gid for selected tile
            gid = 0
            for t in self.tile_list:
                if t["id"] == self.selected_tile:
                    gid = t["gid"]
                    break
            if gid and self.grid[row][col] != gid:
                self.grid[row][col] = gid
                self._render_cell(row, col)

    def _on_canvas_right_click(self, event):
        col = int(self.map_canvas.canvasx(event.x)) // SCALED
        row = int(self.map_canvas.canvasy(event.y)) // SCALED
        if 0 <= row < self.map_h and 0 <= col < self.map_w:
            if self.grid[row][col] != 0:
                self.grid[row][col] = 0
                self._render_cell(row, col)

    def _render_grid(self):
        self.map_canvas.delete("all")
        self.map_canvas.configure(scrollregion=(0, 0, self.map_w * SCALED, self.map_h * SCALED))
        self._cell_images: dict[tuple[int, int], int] = {}

        for row in range(self.map_h):
            for col in range(self.map_w):
                x, y = col * SCALED, row * SCALED
                # Grid lines
                self.map_canvas.create_rectangle(x, y, x + SCALED, y + SCALED,
                                                  outline="#333333", fill="#1a1a1a", tags="grid")
                gid = self.grid[row][col]
                if gid != 0:
                    tid = self.gid_to_tile_id.get(gid)
                    if tid and tid in self.images:
                        img_id = self.map_canvas.create_image(x, y, anchor=tk.NW,
                                                               image=self.images[tid], tags="tile")
                        self._cell_images[(row, col)] = img_id

    def _render_cell(self, row: int, col: int):
        x, y = col * SCALED, row * SCALED
        # Remove old tile image if any
        if (row, col) in self._cell_images:
            self.map_canvas.delete(self._cell_images[(row, col)])
            del self._cell_images[(row, col)]

        gid = self.grid[row][col]
        if gid != 0:
            tid = self.gid_to_tile_id.get(gid)
            if tid and tid in self.images:
                img_id = self.map_canvas.create_image(x, y, anchor=tk.NW,
                                                       image=self.images[tid], tags="tile")
                self._cell_images[(row, col)] = img_id

    # ─── Tag editor (right) ─────────────────────────────────────────

    def _build_tag_editor(self, parent: ttk.Frame):
        parent.configure(padding=8)

        # Make right panel scrollable
        canvas = tk.Canvas(parent, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        inner = ttk.Frame(canvas)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        self._tag_canvas = canvas

        # Preview
        ttk.Label(inner, text="Selected Tile", font=("", 12, "bold")).pack(pady=(0, 4))

        self.preview_label = tk.Label(inner, bg="#333333", width=64, height=64)
        self.preview_label.pack(pady=4)
        self.preview_photo = None  # keep reference

        self.info_var = tk.StringVar(value="No tile selected")
        ttk.Label(inner, textvariable=self.info_var).pack(pady=(0, 8))

        ttk.Separator(inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # Category
        ttk.Label(inner, text="Category").pack(anchor=tk.W)
        self.tag_category_var = tk.StringVar()
        self.tag_category_cb = ttk.Combobox(inner, textvariable=self.tag_category_var,
                                             values=CATEGORIES, state="readonly", width=24)
        self.tag_category_cb.pack(fill=tk.X, pady=(0, 8))

        # Description
        ttk.Label(inner, text="Description").pack(anchor=tk.W)
        self.tag_desc_var = tk.StringVar()
        self.tag_desc_entry = ttk.Entry(inner, textvariable=self.tag_desc_var, width=28)
        self.tag_desc_entry.pack(fill=tk.X, pady=(0, 8))

        # Edges
        ttk.Label(inner, text="Edges", font=("", 10, "bold")).pack(anchor=tk.W, pady=(4, 2))

        self.edge_vars: dict[str, tk.StringVar] = {}
        for side in ("top", "bottom", "left", "right"):
            f = ttk.Frame(inner)
            f.pack(fill=tk.X, pady=1)
            ttk.Label(f, text=f"  {side.capitalize()}:", width=10).pack(side=tk.LEFT)
            var = tk.StringVar()
            cb = ttk.Combobox(f, textvariable=var, values=EDGE_TYPES, state="readonly", width=18)
            cb.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.edge_vars[side] = var

        # Buttons
        btn_frame = ttk.Frame(inner)
        btn_frame.pack(fill=tk.X, pady=12)
        ttk.Button(btn_frame, text="Save Tag", command=self._save_current_tag).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="Save All Tags to File", command=self.save_tags).pack(fill=tk.X, pady=2)

        # ── Recommended Neighbors ──
        ttk.Separator(inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(inner, text="Recommended Neighbors", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        # 3x3 grid: the center is the selected tile, 8 surrounding cells are neighbors
        # Layout positions: (row_offset, col_offset) -> grid position
        #   (-1,-1) (-1,0) (-1,1)
        #   ( 0,-1) CENTER ( 0,1)
        #   ( 1,-1) ( 1,0) ( 1,1)
        self.neighbor_frame = ttk.Frame(inner)
        self.neighbor_frame.pack(pady=4)

        self.neighbor_labels: dict[tuple[int, int], tk.Label] = {}
        self.neighbor_photos: dict[tuple[int, int], ImageTk.PhotoImage] = {}
        self.neighbor_tile_ids: dict[tuple[int, int], str | None] = {}

        dir_names = {
            (-1, -1): "TL", (-1, 0): "Top", (-1, 1): "TR",
            (0, -1): "Left", (0, 0): "", (0, 1): "Right",
            (1, -1): "BL", (1, 0): "Bottom", (1, 1): "BR",
        }

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                gr, gc = dr + 1, dc + 1  # grid row/col in the 3x3 frame
                lbl = tk.Label(self.neighbor_frame, bg="#222222", width=4, height=2,
                               relief=tk.SUNKEN, bd=1)
                lbl.grid(row=gr, column=gc, padx=1, pady=1)
                self.neighbor_labels[(dr, dc)] = lbl
                self.neighbor_tile_ids[(dr, dc)] = None
                # Click on neighbor to select it in palette
                lbl.bind("<Button-1>", lambda e, d=(dr, dc): self._on_neighbor_click(d))

        # Direction labels below the grid
        self.neighbor_info_var = tk.StringVar(value="Select a tile to see neighbors")
        ttk.Label(inner, textvariable=self.neighbor_info_var, wraplength=250).pack(pady=(4, 0))

        # Neighbor list (scrollable, top neighbors per direction)
        ttk.Separator(inner, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)
        ttk.Label(inner, text="Top Neighbors by Direction", font=("", 10, "bold")).pack(anchor=tk.W, pady=(0, 4))

        self.neighbor_list_frame = ttk.Frame(inner)
        self.neighbor_list_frame.pack(fill=tk.X)

    def _show_tile_tags(self, tile_id: str):
        # Preview image (4x scale for preview)
        if tile_id in self.pil_images:
            preview = self.pil_images[tile_id].resize((64, 64), Image.NEAREST)
            self.preview_photo = ImageTk.PhotoImage(preview)
            self.preview_label.configure(image=self.preview_photo, width=64, height=64)

        # Info
        gid = 0
        for t in self.tile_list:
            if t["id"] == tile_id:
                gid = t["gid"]
                break
        self.info_var.set(f"ID: {tile_id}  |  GID: {gid}")

        # Tags
        tag = self.tags.get(tile_id, {})
        self.tag_category_var.set(tag.get("category", ""))
        self.tag_desc_var.set(tag.get("description", ""))
        edges = tag.get("edges", {})
        for side in ("top", "bottom", "left", "right"):
            self.edge_vars[side].set(edges.get(side, "empty"))

        # Update neighbor recommendations
        self._update_neighbors(tile_id)

    def _save_current_tag(self):
        if not self.selected_tile:
            messagebox.showinfo("Info", "No tile selected.")
            return

        self.tags[self.selected_tile] = {
            "category": self.tag_category_var.get(),
            "description": self.tag_desc_var.get(),
            "edges": {side: var.get() for side, var in self.edge_vars.items()},
        }
        messagebox.showinfo("Saved", f"Tag for {self.selected_tile} updated in memory.\n"
                            "Use 'Save All Tags' to write to file.")

    # ─── Adjacency update from map canvas ───────────────────────────

    def update_adjacency(self):
        """Extract adjacency pairs from the current map grid and merge into tile_adjacency.json."""
        BACKGROUND_GID = 1
        DIRECTIONS = [("right", 0, 1), ("bottom", 1, 0), ("left", 0, -1), ("top", -1, 0)]

        # 1. Collect adjacency pairs from grid
        new_adj: dict[str, dict[str, dict[str, int]]] = defaultdict(lambda: defaultdict(lambda: defaultdict(int)))
        for r in range(self.map_h):
            for c in range(self.map_w):
                gid = self.grid[r][c]
                if gid == 0 or gid == BACKGROUND_GID:
                    continue
                for direction, dr, dc in DIRECTIONS:
                    nr, nc = r + dr, c + dc
                    if 0 <= nr < self.map_h and 0 <= nc < self.map_w:
                        n_gid = self.grid[nr][nc]
                        if n_gid == 0 or n_gid == BACKGROUND_GID:
                            continue
                        new_adj[str(gid)][direction][str(n_gid)] += 1

        if not new_adj:
            messagebox.showinfo("Update Adjacency", "No adjacency pairs found in current map.\nPlace at least two non-background tiles next to each other.")
            return

        # 2. Merge into self.adjacency
        added_pairs = 0
        for key, dirs in new_adj.items():
            for direction, neighbors in dirs.items():
                for n_key, count in neighbors.items():
                    self.adjacency.setdefault(key, {}).setdefault(direction, {})
                    old_count = self.adjacency[key][direction].get(n_key, 0)
                    self.adjacency[key][direction][n_key] = old_count + count
                    added_pairs += count

        # 3. Save to tile_adjacency.json
        # Load existing file to preserve metadata and tile_info
        if ADJACENCY_FILE.exists():
            try:
                existing = json.loads(ADJACENCY_FILE.read_text())
            except Exception:
                existing = {}
        else:
            existing = {}

        metadata = existing.get("metadata", {})
        tile_info = existing.get("tile_info", {})

        # Add "editor" to source_maps if not present
        source_maps = metadata.get("source_maps", [])
        if "editor" not in source_maps:
            source_maps.append("editor")
        metadata["source_maps"] = source_maps

        # Update tile_info for any newly observed tiles
        gid_to_tile_id = self.gid_to_tile_id
        all_keys: set[str] = set(self.adjacency.keys())
        for dirs in self.adjacency.values():
            for neighbors in dirs.values():
                all_keys.update(neighbors.keys())

        for key in all_keys:
            if key not in tile_info:
                gid = int(key)
                info: dict = {"gid": gid, "flip": ""}
                if gid in gid_to_tile_id:
                    info["tile_id"] = gid_to_tile_id[gid]
                tile_info[key] = info

        # Recount total pairs
        total_pairs = 0
        for dirs in self.adjacency.values():
            for neighbors in dirs.values():
                total_pairs += sum(neighbors.values())

        metadata["total_adjacency_pairs"] = total_pairs
        metadata["unique_tiles_observed"] = len(self.adjacency)

        output = {
            "metadata": metadata,
            "tile_info": tile_info,
            "adjacency": self.adjacency,
        }
        ADJACENCY_FILE.write_text(json.dumps(output, indent=2))

        # 4. Refresh neighbor display for currently selected tile
        if self.selected_tile:
            self._update_neighbors(self.selected_tile)

        messagebox.showinfo("Update Adjacency", f"Added {added_pairs} adjacency pairs from map.\nSaved to {ADJACENCY_FILE.name}")

    # ─── Neighbor recommendations ────────────────────────────────────

    def _get_top_neighbor(self, tile_id: str, direction: str) -> str | None:
        """Get the most frequent neighbor tile_id for a given direction."""
        gid = self.tile_id_to_gid.get(tile_id, 0)
        if gid == 0:
            return None
        key = str(gid)
        adj = self.adjacency.get(key, {})
        neighbors = adj.get(direction, {})
        if not neighbors:
            return None
        # Get highest count neighbor (keys are GID strings, possibly with flip flags)
        best_key = max(neighbors, key=lambda k: neighbors[k])
        # Parse GID from key (may be "170" or "170:HV")
        base_gid = int(best_key.split(":")[0]) if ":" in best_key else int(best_key)
        return self.gid_to_tile_id.get(base_gid)

    def _get_top_neighbors(self, tile_id: str, direction: str, limit: int = 5) -> list[tuple[str, int]]:
        """Get top N neighbor (tile_id, count) pairs for a direction."""
        gid = self.tile_id_to_gid.get(tile_id, 0)
        if gid == 0:
            return []
        key = str(gid)
        adj = self.adjacency.get(key, {})
        neighbors = adj.get(direction, {})
        if not neighbors:
            return []
        sorted_neighbors = sorted(neighbors.items(), key=lambda x: -x[1])[:limit]
        result = []
        for nkey, count in sorted_neighbors:
            base_gid = int(nkey.split(":")[0]) if ":" in nkey else int(nkey)
            tid = self.gid_to_tile_id.get(base_gid)
            if tid:
                result.append((tid, count))
        return result

    def _update_neighbors(self, tile_id: str):
        """Update the 3x3 neighbor grid and the detailed neighbor list."""
        # Direction mapping: (row_offset, col_offset) -> adjacency direction name
        # Cardinal directions map directly; diagonals are inferred
        cardinal_map = {
            (-1, 0): "top",
            (1, 0): "bottom",
            (0, -1): "left",
            (0, 1): "right",
        }
        # For diagonals, use intersection of two cardinal directions' neighbor sets
        diagonal_map = {
            (-1, -1): ("top", "left"),
            (-1, 1): ("top", "right"),
            (1, -1): ("bottom", "left"),
            (1, 1): ("bottom", "right"),
        }

        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                lbl = self.neighbor_labels[(dr, dc)]
                if dr == 0 and dc == 0:
                    # Center = selected tile
                    if tile_id in self.images:
                        self.neighbor_photos[(0, 0)] = self.images[tile_id]
                        lbl.configure(image=self.images[tile_id], bg="#444444",
                                      width=SCALED, height=SCALED)
                    self.neighbor_tile_ids[(0, 0)] = tile_id
                    continue

                neighbor_tid = None
                if (dr, dc) in cardinal_map:
                    direction = cardinal_map[(dr, dc)]
                    neighbor_tid = self._get_top_neighbor(tile_id, direction)
                elif (dr, dc) in diagonal_map:
                    # Infer diagonal: find tiles that appear in BOTH cardinal neighbor sets
                    dir_a, dir_b = diagonal_map[(dr, dc)]
                    neighbor_tid = self._infer_diagonal_neighbor(tile_id, dir_a, dir_b)

                self.neighbor_tile_ids[(dr, dc)] = neighbor_tid
                if neighbor_tid and neighbor_tid in self.images:
                    self.neighbor_photos[(dr, dc)] = self.images[neighbor_tid]
                    lbl.configure(image=self.images[neighbor_tid], bg="#333333",
                                  width=SCALED, height=SCALED)
                else:
                    self.neighbor_photos.pop((dr, dc), None)
                    lbl.configure(image="", text="?", bg="#222222",
                                  width=4, height=2)

        # Update detailed neighbor list
        for w in self.neighbor_list_frame.winfo_children():
            w.destroy()

        self._neighbor_list_photos = []  # prevent GC of PhotoImages

        for direction in ("top", "right", "bottom", "left"):
            top_n = self._get_top_neighbors(tile_id, direction)
            if not top_n:
                continue
            dir_frame = ttk.Frame(self.neighbor_list_frame)
            dir_frame.pack(fill=tk.X, pady=2)
            ttk.Label(dir_frame, text=f"{direction.capitalize()}:", width=8).pack(side=tk.LEFT)
            for tid, count in top_n:
                if tid in self.pil_images:
                    tile_frame = ttk.Frame(dir_frame)
                    tile_frame.pack(side=tk.LEFT, padx=1)
                    photo = ImageTk.PhotoImage(self.pil_images[tid])
                    self._neighbor_list_photos.append(photo)
                    tile_lbl = tk.Label(tile_frame, image=photo, bd=1, relief=tk.RAISED)
                    tile_lbl.pack()
                    tile_lbl.bind("<Button-1>", lambda e, t=tid: self._on_palette_click(t))
                    ttk.Label(tile_frame, text=str(count), font=("", 7)).pack()

        has_data = bool(self.adjacency.get(str(self.tile_id_to_gid.get(tile_id, 0)), {}))
        if has_data:
            self.neighbor_info_var.set("Click a neighbor to select it")
        else:
            self.neighbor_info_var.set("No adjacency data for this tile")

    def _infer_diagonal_neighbor(self, tile_id: str, dir_a: str, dir_b: str) -> str | None:
        """Infer a diagonal neighbor by finding tiles that appear as neighbors in both directions."""
        gid = self.tile_id_to_gid.get(tile_id, 0)
        if gid == 0:
            return None
        key = str(gid)
        adj = self.adjacency.get(key, {})

        neighbors_a = set()
        for nkey in adj.get(dir_a, {}):
            base = int(nkey.split(":")[0]) if ":" in nkey else int(nkey)
            neighbors_a.add(base)

        # For each neighbor in dir_a, check if it has dir_b neighbors in common
        # Actually: find tiles T such that T is a dir_a neighbor of tile_id,
        # and T has dir_b neighbors. Pick the best one.
        best_tid = None
        best_score = 0
        for nkey_a, count_a in adj.get(dir_a, {}).items():
            base_a = int(nkey_a.split(":")[0]) if ":" in nkey_a else int(nkey_a)
            # Check what's to the dir_b of this neighbor
            n_adj = self.adjacency.get(str(base_a), {})
            for nkey_b, count_b in n_adj.get(dir_b, {}).items():
                score = count_a + count_b
                if score > best_score:
                    best_score = score
                    base_b = int(nkey_b.split(":")[0]) if ":" in nkey_b else int(nkey_b)
                    best_tid = self.gid_to_tile_id.get(base_b)

        return best_tid

    def _on_neighbor_click(self, pos: tuple[int, int]):
        """Click a neighbor cell to select that tile in the palette."""
        tid = self.neighbor_tile_ids.get(pos)
        if tid:
            self._on_palette_click(tid)

    # ─── File I/O ────────────────────────────────────────────────────

    def new_map(self):
        w = simpledialog.askinteger("New Map", "Width (tiles):", initialvalue=DEFAULT_MAP_W, minvalue=1, maxvalue=256)
        if not w:
            return
        h = simpledialog.askinteger("New Map", "Height (tiles):", initialvalue=DEFAULT_MAP_H, minvalue=1, maxvalue=256)
        if not h:
            return
        self.new_map_silent(w, h)

    def new_map_silent(self, w: int, h: int):
        self.map_w = w
        self.map_h = h
        self.grid = [[0] * w for _ in range(h)]
        self._cell_images = {}
        self._render_grid()

    def save_map(self):
        path = filedialog.asksaveasfilename(defaultextension=".json",
                                            filetypes=[("JSON", "*.json")],
                                            title="Save Map")
        if not path:
            return
        data = {"width": self.map_w, "height": self.map_h, "grid": self.grid}
        Path(path).write_text(json.dumps(data, indent=2))
        messagebox.showinfo("Saved", f"Map saved to {path}")

    def load_map(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json")], title="Open Map")
        if not path:
            return
        data = json.loads(Path(path).read_text())
        self.map_w = data["width"]
        self.map_h = data["height"]
        self.grid = data["grid"]
        self._cell_images = {}
        self._render_grid()

    def save_tags(self):
        # Rebuild tile_tags.json in the same format as tag_tiles.py output
        tiles_out = []
        for t in self.tile_list:
            tid = t["id"]
            tag = self.tags.get(tid, {})
            tiles_out.append({
                "id": tid,
                "gid": t["gid"],
                "row": t["row"],
                "col": t["col"],
                "pixel_x": t.get("pixel_x", 0),
                "pixel_y": t.get("pixel_y", 0),
                "category": tag.get("category", ""),
                "description": tag.get("description", ""),
                "edges": tag.get("edges", {"top": "empty", "bottom": "empty",
                                            "left": "empty", "right": "empty"}),
            })

        # Preserve original metadata if file exists
        metadata = {
            "source": "tileset_legacy.png",
            "tile_size": 16,
            "spacing": 1,
            "grid": [32, 32],
            "total_possible": 1024,
        }
        if TAGS_FILE.exists():
            try:
                orig = json.loads(TAGS_FILE.read_text())
                metadata = orig.get("metadata", metadata)
            except Exception:
                pass

        output = {
            "metadata": metadata,
            "total_tagged": len([t for t in tiles_out if t["category"]]),
            "errors": [],
            "tiles": tiles_out,
        }
        TAGS_FILE.write_text(json.dumps(output, indent=2))
        messagebox.showinfo("Saved", f"Tags saved to {TAGS_FILE}")


def main():
    root = tk.Tk()
    TileEditorApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
