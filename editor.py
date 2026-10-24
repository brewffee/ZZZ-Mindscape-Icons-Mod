"""Visual agent editor. Run with Python 3.12 and Pillow."""

from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, simpledialog, ttk
except ImportError as exc:
    raise SystemExit("editor requires Tkinter. Install Python's Tcl/Tk component and retry.") from exc

from PIL import Image, ImageChops, ImageFilter, ImageTk, UnidentifiedImageError

from config import ROOT, DEFAULTS, archive_name, resolve_path
from editor_model import (
    BLANK_HASH, DEFAULT_MASK, Draft, MaskEntry, duplicate_hashes, hash_from_filename,
    valid_hash, validate_mask, validate_transform_image,
)
from masks import preview_mask
from textures import MASK_SPECS, MaskKind, is_chibi, position_image, render_mask
from upscaler import UpscaleError

USER_ERRORS = (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError, UpscaleError)

DARK_THEME = {
    "background": "#202124",
    "surface": "#292a2d",
    "field": "#303134",
    "hover": "#3c4043",
    "border": "#5f6368",
    "foreground": "#e8eaed",
    "muted": "#9aa0a6",
    "disabled": "#777b80",
    "accent": "#8ab4f8",
    "selection": "#3c5a80",
    "canvas": "#1e1e1e",
}


def apply_dark_theme(window: tk.Misc) -> None:
    colors = DARK_THEME
    window.configure(background=colors["background"])
    style = ttk.Style(window)
    if "clam" in style.theme_names():
        style.theme_use("clam")

    style.configure(
        ".",
        background=colors["background"],
        foreground=colors["foreground"],
        bordercolor=colors["border"],
        lightcolor=colors["surface"],
        darkcolor=colors["background"],
        troughcolor=colors["surface"],
    )
    style.configure("TFrame", background=colors["background"])
    style.configure("TLabel", background=colors["background"], foreground=colors["foreground"])
    style.configure(
        "TButton",
        background=colors["surface"],
        foreground=colors["foreground"],
        padding=(8, 4),
    )
    style.map(
        "TButton",
        background=[
            ("disabled", colors["field"]),
            ("pressed", colors["selection"]),
            ("active", colors["hover"]),
        ],
        foreground=[("disabled", colors["disabled"])],
    )
    style.configure(
        "TEntry",
        fieldbackground=colors["field"],
        foreground=colors["foreground"],
        insertcolor=colors["foreground"],
    )
    style.configure(
        "TCombobox",
        fieldbackground=colors["field"],
        background=colors["surface"],
        foreground=colors["foreground"],
        arrowcolor=colors["foreground"],
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", colors["field"]), ("disabled", colors["surface"])],
        background=[("active", colors["hover"]), ("disabled", colors["surface"])],
        foreground=[("disabled", colors["disabled"])],
    )
    style.configure(
        "Treeview",
        background=colors["field"],
        fieldbackground=colors["field"],
        foreground=colors["foreground"],
        rowheight=24,
    )
    style.map(
        "Treeview",
        background=[("selected", colors["selection"])],
        foreground=[("selected", colors["foreground"])],
    )
    style.configure(
        "Treeview.Heading",
        background=colors["surface"],
        foreground=colors["foreground"],
    )
    style.map("Treeview.Heading", background=[("active", colors["hover"])])
    style.configure("TNotebook", background=colors["background"], borderwidth=0)
    style.configure(
        "TNotebook.Tab",
        background=colors["surface"],
        foreground=colors["foreground"],
        padding=(10, 5),
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", colors["field"]), ("active", colors["hover"])],
        foreground=[("disabled", colors["disabled"])],
    )
    style.configure("TCheckbutton", background=colors["background"], foreground=colors["foreground"])
    style.configure("TScale", background=colors["background"], troughcolor=colors["surface"])
    style.configure("TPanedwindow", background=colors["background"])
    style.configure(
        "TScrollbar",
        background=colors["surface"],
        troughcolor=colors["background"],
        arrowcolor=colors["foreground"],
    )


def set_validation_style(widget: ttk.Widget, base_style: str, invalid: bool) -> None:
    style = ttk.Style(widget)
    validation_style = f"Invalid.{base_style}"
    layout = style.layout(base_style)
    elements = []
    pending = list(layout)
    while pending:
        element, options = pending.pop()
        elements.append(element)
        pending.extend(options.get("children", ()))
    supports_border_color = any(
        "-bordercolor" in style.element_options(element)
        for element in elements
    )
    if supports_border_color:
        style.configure(validation_style, bordercolor="#ff0000")
    else:
        style.configure(validation_style, foreground="#ff0000")
    widget.configure(style=validation_style if invalid else base_style)


def skin_label(index: int) -> str:
    return "Base" if index == 0 else "Skin" + (str(index) if index > 1 else "")


def checkerboard(size: tuple[int, int]) -> Image.Image:
    from PIL import ImageDraw
    image = Image.new("RGBA", size, "#dddddd")
    draw = ImageDraw.Draw(image)
    for y in range(0, size[1], 12):
        for x in range(0, size[0], 12):
            if (x // 12 + y // 12) % 2:
                draw.rectangle((x, y, x + 11, y + 11), fill="#aaaaaa")
    return image


class Editor:
    def __init__(self, window: tk.Tk, draft: Draft):
        self.window = window
        self.draft = draft
        self.current: tuple[str, int, MaskKind] | None = None
        self.tree_items: dict[str, tuple[str, int, MaskKind | None]] = {}
        self.form_original: tuple[str, ...] = ()
        self.loading = False
        self.running = False
        self.process: subprocess.Popen[str] | None = None
        self.events: queue.Queue[tuple[str, str | int]] = queue.Queue()
        self.preview_job: str | None = None
        self.image: Image.Image | None = None
        self.masks: dict[MaskKind, Image.Image] = {}
        self.photos: list[ImageTk.PhotoImage] = []
        self.disabled_widgets: list[ttk.Widget] = []
        self.reported_missing: set[tuple[str, str, int, MaskKind]] = set()
        self.window.title("Mindscape Icons editor")
        apply_dark_theme(self.window)
        self.window.geometry("1200x920")
        self.window.minsize(1000, 780)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.status = tk.StringVar(value="Ready. Changes are drafts until Save.")
        toolbar = ttk.Frame(window, padding=6)
        toolbar.pack(fill="x")
        for text, command in (
            ("Save", self.save), ("Reload", self.reload),
            ("Config", self.edit_config), ("Generate Mod", self.generate),
            ("Discard Imports", self.discard_imports),
        ):
            ttk.Button(toolbar, text=text, command=command).pack(side="left", padx=3)
        ttk.Label(toolbar, textvariable=self.status).pack(side="left", padx=12)
        panes = ttk.Panedwindow(window, orient="horizontal")
        panes.pack(fill="both", expand=True, padx=6)
        navigation = ttk.Frame(panes, padding=4)
        panes.add(navigation, weight=1)
        self.search = tk.StringVar()
        ttk.Label(navigation, text="Search agents").pack(anchor="w")
        ttk.Entry(navigation, textvariable=self.search).pack(fill="x")
        self.search.trace_add("write", lambda *_: self.rebuild_tree())
        tree_area = ttk.Frame(navigation)
        tree_area.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(tree_area, show="tree", selectmode="browse")
        self.tree.tag_configure("invalid_hash", foreground="red")
        self.tree.tag_configure("missing_artwork", foreground="red")
        self.tree.pack(side="left", fill="both", expand=True)
        tree_scroll = ttk.Scrollbar(tree_area, orient="vertical", command=self.tree.yview)
        tree_scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.bind("<<TreeviewSelect>>", self.select)
        ttk.Button(navigation, text="Add Agent", command=self.add_agent).pack(fill="x")
        ttk.Button(navigation, text="Add Skin to Selected Agent", command=self.add_skin).pack(fill="x")
        right = ttk.Frame(panes, padding=6)
        panes.add(right, weight=4)
        self.selection = tk.StringVar(value="Select an agent, skin, and mask.")
        ttk.Label(right, textvariable=self.selection, font=("", 12, "bold")).pack(anchor="w")
        source_row = ttk.Frame(right)
        source_row.pack(fill="x", pady=5)
        ttk.Label(source_row, text="Source variant:").pack(side="left")
        self.variant = tk.StringVar(value=draft.settings["SOURCE_DIRS"][0])
        self.variants = ttk.Combobox(
            source_row, textvariable=self.variant,
            values=draft.settings["SOURCE_DIRS"], state="readonly", width=35,
        )
        self.variants.pack(side="left", padx=5)
        self.active_variant = self.variant.get()
        self.variants.bind("<<ComboboxSelected>>", self.change_variant)
        self.import_button = ttk.Button(source_row, text="Import Artwork", command=self.import_art)
        self.import_button.pack(side="left", padx=3)
        self.flip_buttons = [
            ttk.Button(source_row, text="Flip Vertically", command=lambda: self.flip_art(vertical=True)),
            ttk.Button(source_row, text="Flip Horizontally", command=lambda: self.flip_art(vertical=False)),
        ]
        for button in self.flip_buttons:
            button.state(["disabled"])
            button.pack(side="left", padx=3)
        self.source_info = tk.StringVar(value="M3/M6 share transforms. Chibi has separate artwork and transforms for each mask.")
        ttk.Label(right, textvariable=self.source_info, wraplength=780).pack(anchor="w")
        hash_row = ttk.Frame(right)
        hash_row.pack(fill="x", pady=7)
        ttk.Label(hash_row, text="Game texture hash:").pack(side="left")
        self.hash_value = tk.StringVar()
        self.hash_value.trace_add("write", lambda *_: self.hash_changed())
        self.hash_entry = ttk.Entry(hash_row, textvariable=self.hash_value, width=18)
        self.hash_entry.pack(side="left", padx=5)
        ttk.Button(hash_row, text="Extract from Dump Filename", command=self.pick_hash).pack(side="left")
        self.variables: dict[str, tk.StringVar] = {}
        self.sliders: dict[str, ttk.Scale] = {}
        controls = ttk.Frame(right)
        controls.pack(fill="x")
        for row, (name, label, low, high, default) in enumerate((
            ("x", "X offset (+ moves left)", -1000, 1000, "0"),
            ("y", "Y offset (+ preview down)", -1000, 1000, "0"),
            ("scale", "Image scale", 0.01, 5, "1"),
            ("rotation", "Rotation (+ preview CCW)", -360, 360, "0"),
        )):
            variable = tk.StringVar(value=default)
            self.variables[name] = variable
            ttk.Label(controls, text=label).grid(row=row, column=0, sticky="w")
            ttk.Entry(controls, textvariable=variable, width=12).grid(row=row, column=1, padx=5)
            slider = ttk.Scale(
                controls, from_=low, to=high,
                command=lambda value, key=name: self.slide(key, value),
            )
            slider.grid(row=row, column=2, sticky="ew")
            self.sliders[name] = slider
            variable.trace_add("write", lambda *_, key=name: self.input_changed(key))
        controls.columnconfigure(2, weight=1)
        buttons = ttk.Frame(right)
        buttons.pack(fill="x", pady=6)
        ttk.Button(buttons, text="Apply Changes", command=self.apply).pack(side="left", padx=3)
        ttk.Button(buttons, text="Remove Mask", command=self.remove_mask).pack(side="left", padx=3)
        self.copy_base_button = ttk.Button(
            buttons, text="Copy Base Fields", command=self.copy_base_fields,
        )
        self.copy_base_button.state(["disabled"])
        self.copy_base_button.pack(side="left", padx=3)
        ttk.Button(buttons, text="Reset Fields", command=self.reset_fields).pack(side="left", padx=3)
        ttk.Label(buttons, text="Outside dimming:").pack(side="left", padx=10)
        self.dimming = tk.DoubleVar(value=0.7)
        ttk.Scale(
            buttons, variable=self.dimming, from_=0, to=1,
            command=lambda _: self.schedule_preview(),
        ).pack(side="left", fill="x", expand=True)
        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        preview = ttk.Frame(notebook)
        notebook.add(preview, text="Alignment + Output")
        self.preview_text = tk.StringVar(value="Select a mask to preview.")
        ttk.Label(preview, textvariable=self.preview_text, wraplength=780).pack(anchor="w")
        self.canvas = tk.Canvas(preview, background=DARK_THEME["canvas"], highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", lambda _: self.schedule_preview())
        logs = ttk.Frame(notebook)
        notebook.add(logs, text="Generation Log")
        self.log = tk.Text(logs, wrap="word", state="disabled", height=15)
        self.log.configure(
            background=DARK_THEME["field"],
            foreground=DARK_THEME["foreground"],
            insertbackground=DARK_THEME["foreground"],
            selectbackground=DARK_THEME["selection"],
            selectforeground=DARK_THEME["foreground"],
            highlightthickness=0,
        )
        scrollbar = ttk.Scrollbar(logs, command=self.log.yview)
        scrollbar.pack(side="right", fill="y")
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(fill="both", expand=True)
        self.notebook = notebook
        self.rebuild_tree()
        self.window.after(100, self.poll)
        self.window.bind("<Control-s>", lambda _: self.save())
        warnings = duplicate_hashes(self.draft.agents)
        if warnings:
            self.append_log("Existing duplicate game hashes (review, not a load error):\n" + "\n".join(warnings) + "\n")
        self.warn_invalid_hashes()

    def warn_invalid_hashes(self) -> None:
        if not self.draft.hash_warnings:
            return
        text = (
            "Invalid game hashes were replaced with the blank placeholder "
            f"{BLANK_HASH} for:\n\n" + "\n".join(self.draft.hash_warnings)
            + "\n\nThe editor can continue normally. These masks will not replace game textures "
            "until valid hashes are supplied. Save writes the placeholders to agents.json."
        )
        self.append_log(text + "\n")
        messagebox.showwarning("Invalid game hashes", text, parent=self.window)
        self.draft.hash_warnings.clear()

    def error(self, exc: BaseException) -> None:
        messagebox.showerror("editor", str(exc), parent=self.window)

    def values(self) -> tuple[str, ...]:
        return (self.hash_value.get(), *(v.get() for v in self.variables.values()))

    def fields_dirty(self) -> bool:
        return self.current is not None and self.values() != self.form_original

    def entry(self, require_hash: bool = True) -> MaskEntry:
        try:
            entry: MaskEntry = {
                "hash": BLANK_HASH,
                "offset": [int(self.variables["x"].get()), int(self.variables["y"].get())],
                "scale": float(self.variables["scale"].get()),
                "rotation": float(self.variables["rotation"].get()),
            }
        except ValueError as exc:
            raise ValueError("Enter integer offsets and numeric scale/rotation.") from exc
        validate_mask(entry)
        if require_hash:
            entry["hash"] = self.hash_value.get().strip()
        return entry

    def resolve_fields(self) -> bool:
        if not self.fields_dirty():
            return True
        if self.draft.settings["AUTO_APPLY_DRAFT_CHANGES"]:
            return self.apply()
        result = messagebox.askyesnocancel(
            "Unapplied mask edits", "Apply these mask edits to the draft?\n"
            "Yes: Apply. No: Discard fields. Cancel: Stay here.", parent=self.window,
        )
        if result is None:
            return False
        if result:
            return self.apply()
        self.reset_fields()
        return True

    def rebuild_tree(self) -> None:
        if self.running:
            return
        selected = self.current
        self.loading = True
        self.tree.delete(*self.tree.get_children())
        self.tree_items.clear()
        selected_item = None
        for name, skins in sorted(self.draft.agents.items(), key=lambda item: item[0].casefold()):
            if self.search.get().casefold() not in name.casefold():
                continue
            parent = self.tree.insert("", "end", text=name, open=False)
            self.tree_items[parent] = (name, 0, None)
            for index, skin in enumerate(skins):
                node = self.tree.insert(parent, "end", text=skin_label(index), open=True)
                self.tree_items[node] = (name, index, None)
                for kind in MASK_SPECS:
                    changed = (
                        name not in self.draft.saved_agents
                        or index >= len(self.draft.saved_agents[name])
                        or skin.get(kind) != self.draft.saved_agents[name][index].get(kind)
                    )
                    item = self.tree.insert(
                        node, "end",
                        text=kind + (" [missing: select to add]" if kind not in skin else "")
                        + (" *" if changed else ""),
                    )
                    self.tree_items[item] = (name, index, kind)
                    if selected == (name, index, kind):
                        selected_item = item
        if selected_item:
            self.tree.selection_set(selected_item)
            self.tree.see(selected_item)
        self.loading = False
        self.refresh_labels()

    def update_title(self) -> None:
        dirty = self.draft.dirty or self.fields_dirty()
        self.window.title((" * " if dirty else "") + "Mindscape Icons editor")

    def hash_changed(self) -> None:
        if not self.loading:
            self.update_title()
            self.update_validation_feedback()

    def update_validation_feedback(self) -> None:
        invalid_hash = False
        missing_artwork = False
        if self.current is not None:
            hash_value = self.hash_value.get().strip()
            invalid_hash = not valid_hash(hash_value) or hash_value == BLANK_HASH
            missing_artwork = (
                self.draft.artwork_path(self.variant.get(), *self.current) is None
            )
        set_validation_style(self.hash_entry, "TEntry", invalid_hash)
        set_validation_style(self.import_button, "TButton", missing_artwork)

    def refresh_labels(self) -> None:
        invalid_items: set[str] = set()
        missing_items: set[str] = set()
        source = self.variant.get()
        agents = self.draft.agents_for(source)
        saved_agents = self.draft.saved_chibi_agents if is_chibi(source) else self.draft.saved_agents
        missing = self.report_missing_artwork().get(source, {})
        for item, (name, index, kind) in self.tree_items.items():
            if kind is None:
                continue
            entry = agents[name][index].get(kind)
            saved_skins = saved_agents.get(name, [])
            saved = saved_skins[index].get(kind) if index < len(saved_skins) else None
            self.tree.item(
                item, text=kind + (" [missing: select to add]" if entry is None else "")
                + (" *" if entry != saved else ""),
            )
            if entry is not None and (not valid_hash(entry["hash"]) or entry["hash"] == BLANK_HASH):
                node = item
                while node:
                    invalid_items.add(node)
                    node = self.tree.parent(node)
            if (name, index, kind) in missing:
                node = item
                while node:
                    missing_items.add(node)
                    node = self.tree.parent(node)
        for item in self.tree_items:
            tags = []
            if item in invalid_items:
                tags.append("invalid_hash")
            if item in missing_items:
                tags.append("missing_artwork")
            self.tree.item(item, tags=tags)
        self.update_validation_feedback()
        self.update_title()

    def report_missing_artwork(self) -> dict[str, dict[tuple[str, int, MaskKind], Path]]:
        missing = {
            source: self.draft.missing_artwork(source)
            for source in self.draft.settings["SOURCE_DIRS"]
        }
        current: set[tuple[str, str, int, MaskKind]] = set()
        warnings = []
        for source, entries in missing.items():
            for (name, index, kind), path in entries.items():
                identity = (source, name, index, kind)
                current.add(identity)
                if identity not in self.reported_missing:
                    warnings.append(f"WARNING: Missing artwork: {source} / {name} / {skin_label(index)} / {kind}: {path}")
        self.reported_missing = current
        if warnings:
            self.append_log("\n".join(warnings) + "\n")
        return missing

    def change_variant(self, _: object = None) -> None:
        source = self.variant.get()
        self.variant.set(self.active_variant)
        if not self.resolve_fields():
            return
        self.variant.set(source)
        self.active_variant = source
        if self.current is not None:
            self.reset_fields()
        else:
            self.load_artwork()

    def select(self, _: object = None) -> None:
        if self.loading or self.running or not self.tree.selection():
            return
        target = self.tree_items[self.tree.selection()[0]]
        previous = self.current
        if target == previous:
            return
        if not self.resolve_fields():
            self.rebuild_tree()
            return
        if target[2] is None:
            self.current = None
            self.image = None
            self.update_flip_buttons()
            self.update_validation_feedback()
            self.update_copy_base_button()
            self.selection.set(f"{target[0]} / {skin_label(target[1])} - select a mask below")
            self.form_original = ()
            self.schedule_preview()
            return
        self.current = (target[0], target[1], target[2])
        self.reset_fields()

    def update_copy_base_button(self) -> None:
        if self.current is not None and self.current[1] > 0 and not self.running:
            self.copy_base_button.state(["!disabled"])
        else:
            self.copy_base_button.state(["disabled"])

    def copy_base_fields(self) -> None:
        if self.running or self.current is None or self.current[1] == 0:
            return
        name, _, kind = self.current
        base_entry = self.draft.agents_for(self.variant.get())[name][0].get(kind, DEFAULT_MASK)
        for key, value in zip(
            ("x", "y", "scale", "rotation"),
            (*base_entry["offset"], base_entry["scale"], base_entry["rotation"]),
        ):
            self.variables[key].set(str(value))

    def reset_fields(self) -> None:
        if self.running or self.current is None:
            return
        name, index, kind = self.current
        self.update_copy_base_button()
        entry = self.draft.agents_for(self.variant.get())[name][index].get(kind, DEFAULT_MASK)
        self.loading = True
        self.hash_value.set(entry["hash"])
        for key, value in zip(self.variables, (*entry["offset"], entry["scale"], entry["rotation"])):
            self.variables[key].set(str(value))
        self.loading = False
        self.form_original = self.values()
        self.selection.set(f"{name} / {skin_label(index)} / {kind}")
        self.load_artwork()
        for key in self.variables:
            self.input_changed(key)
        self.update_title()

    def slide(self, name: str, value: str) -> None:
        if self.loading or self.running:
            return
        number = float(value)
        text = str(round(number)) if name in ("x", "y") else f"{number:.3f}"
        if self.variables[name].get() != text:
            self.variables[name].set(text)

    def input_changed(self, name: str) -> None:
        if self.loading:
            return
        try:
            number = float(self.variables[name].get())
            if number != number or abs(number) == float("inf"):
                return
        except ValueError:
            self.schedule_preview()
            return
        slider = self.sliders[name]
        low, high = float(slider.cget("from")), float(slider.cget("to"))
        self.loading = True
        slider.configure(from_=min(low, number), to=max(high, number))
        slider.set(number)
        self.loading = False
        self.update_title()
        self.schedule_preview()

    def load_artwork(self) -> None:
        self.image = None
        if self.current is not None:
            try:
                self.image, path = self.draft.artwork(self.variant.get(), *self.current)
                staged = path in self.draft.imports
                base = path.name == self.current[0] + ".png"
                self.source_info.set(
                    str(path) + (" [staged import]" if staged else " [base artwork]" if base else "")
                    + ("\nChibi artwork and transforms are specific to this mask."
                       if is_chibi(self.variant.get())
                       else "\nShared across mask types. Transform is shared across M3/M6 variants.")
                )
                for name in ("x", "y"):
                    bound = max(self.image.size) * 2
                    self.sliders[name].configure(from_=-bound, to=bound)
            except USER_ERRORS as exc:
                self.source_info.set(str(exc))
        self.update_flip_buttons()
        self.refresh_labels()
        self.schedule_preview()

    def update_flip_buttons(self) -> None:
        state = "disabled" if self.running or self.image is None else "!disabled"
        for button in self.flip_buttons:
            button.state([state])

    def schedule_preview(self) -> None:
        if self.preview_job is not None:
            self.window.after_cancel(self.preview_job)
        self.preview_job = self.window.after(140, self.preview)

    def preview(self) -> None:
        self.preview_job = None
        self.canvas.delete("all")
        if self.current is None or self.image is None:
            self.preview_text.set("Select a mask and import artwork if its source is missing.")
            return
        try:
            # A preview does not require the game hash to be filled in yet.
            entry = self.entry(require_hash=False)
            validate_transform_image(entry, self.image)
            kind = self.current[2]
            if kind not in self.masks:
                path = self.draft.root / "masks" / MASK_SPECS[kind].filename
                if path.exists():
                    with Image.open(path) as mask:
                        self.masks[kind] = mask.convert("RGBA")
                else:
                    self.masks[kind] = preview_mask(kind)
            mask = self.masks[kind]
            spec = MASK_SPECS[kind]
            offset = (entry["offset"][0], entry["offset"][1])
            upscaler = self.draft.settings["IMAGE_UPSCALER"]
            denoise = is_chibi(self.variant.get())
            positioned = position_image(
                mask.size, self.image, offset, entry["scale"], entry["rotation"], upscaler,
                denoise=denoise,
            )
            overlay = Image.alpha_composite(checkerboard(mask.size), positioned)
            outside = ImageChops.invert(mask.getchannel("A")).point(
                lambda value: int(value * self.dimming.get())
            )
            dim = Image.new("RGBA", mask.size, (0, 0, 0, 0))
            dim.putalpha(outside)
            overlay = Image.alpha_composite(overlay, dim)
            alpha = mask.getchannel("A")
            boundary = ImageChops.subtract(alpha, alpha.filter(ImageFilter.MinFilter(3)))
            outline = Image.new("RGBA", mask.size, "#00e5ff")
            outline.putalpha(boundary)
            overlay = Image.alpha_composite(overlay, outline)
            result = render_mask(
                spec.size, mask, self.image, offset, entry["scale"], entry["rotation"],
                spec.final_size, self.draft.settings["CONTRAST_MULTIPLIER"],
                self.draft.settings["SATURATION_MULTIPLIER"],
                upscaler,
                denoise=denoise,
            )
            result = Image.alpha_composite(checkerboard(result.size), result)
            width, height = max(self.canvas.winfo_width(), 400), max(self.canvas.winfo_height(), 200)
            self.photos.clear()
            for index, image in enumerate((overlay, result)):
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                image.thumbnail((max(width // 2 - 20, 1), max(height - 45, 1)), Image.Resampling.LANCZOS)
                photo = ImageTk.PhotoImage(image)
                self.photos.append(photo)
                x = width * (index * 2 + 1) // 4
                self.canvas.create_text(x, 15, text=("Mask overlay" if index == 0 else "Exact clipped output"), fill="white")
                self.canvas.create_image(x, height // 2 + 15, image=photo)
            self.preview_text.set(
                f"Output {result.width} x {result.height} px. Previews are vertically flipped for display only."
            )
        except USER_ERRORS as exc:
            self.preview_text.set(f"Preview: {exc}")

    def apply(self) -> bool:
        if self.running or self.current is None:
            return False
        try:
            self.draft.apply_mask(*self.current, self.entry(), self.variant.get())
            self.hash_value.set(self.draft.agents[self.current[0]][self.current[1]][self.current[2]]["hash"])
            self.form_original = self.values()
            self.refresh_labels()
            self.warn_invalid_hashes()
            warnings = duplicate_hashes(self.draft.agents)
            self.status.set("Applied to draft." + (" Duplicate hashes: see log." if warnings else ""))
            if warnings:
                self.append_log("Duplicate game hashes:\n" + "\n".join(warnings) + "\n")
            return True
        except USER_ERRORS as exc:
            self.error(exc)
            return False

    def remove_mask(self) -> None:
        if self.running or self.current is None:
            return
        if not messagebox.askyesno("Remove mask", "Remove this mask entry? Artwork is not deleted.", parent=self.window):
            return
        name, index, kind = self.current
        self.draft.agents[name][index].pop(kind, None)
        self.reset_fields()
        self.refresh_labels()

    def selected_agent(self) -> str | None:
        selection = self.tree.selection()
        return self.tree_items[selection[0]][0] if selection else None

    def add_agent(self) -> None:
        if self.running or not self.resolve_fields():
            return
        name = simpledialog.askstring("Add agent", "Agent identifier (letters, digits, underscore):", parent=self.window)
        if name is None:
            return
        try:
            self.draft.add_agent(name.strip())
            self.current = (name.strip(), 0, "select")
            self.rebuild_tree()
            self.reset_fields()
        except USER_ERRORS as exc:
            self.error(exc)

    def add_skin(self) -> None:
        if self.running:
            return
        name = self.selected_agent()
        if name is None:
            self.error(ValueError("Select an agent first."))
            return
        if not self.resolve_fields():
            return
        try:
            index = self.draft.add_skin(name)
            self.current = (name, index, "select")
            self.rebuild_tree()
            self.reset_fields()
        except USER_ERRORS as exc:
            self.error(exc)

    def import_art(self) -> None:
        if self.running or self.current is None:
            return
        path = filedialog.askopenfilename(title="Choose replacement artwork", parent=self.window)
        if not path:
            return
        try:
            name, index, kind = self.current
            target = self.draft.target(self.variant.get(), name, index, kind)
            if target.exists() or target in self.draft.imports:
                if not messagebox.askyesno(
                    "Shared artwork replacement",
                    f"Stage artwork for {target}?\n"
                    + ("This replaces artwork for this mask only.\n" if is_chibi(self.variant.get())
                       else "This source is shared by every mask for this skin/variant.\n")
                    + "Different existing artwork is replaced only on Save.", parent=self.window,
                ):
                    return
            self.draft.stage_image(
                self.variant.get(), name, index, Path(path), flip_vertical=True, kind=kind,
            )
            self.load_artwork()
            self.update_title()
        except USER_ERRORS as exc:
            self.error(exc)

    def flip_art(self, *, vertical: bool) -> None:
        if self.running or self.current is None:
            return
        try:
            name, index, kind = self.current
            self.draft.flip_image(self.variant.get(), name, index, vertical=vertical, kind=kind)
            self.load_artwork()
            self.update_title()
        except USER_ERRORS as exc:
            self.error(exc)

    def pick_hash(self) -> None:
        if self.running:
            return
        path = filedialog.askopenfilename(title="Choose a game texture dump (filename only)", parent=self.window)
        if path:
            try:
                value = hash_from_filename(path)
                if messagebox.askyesno("Review game hash", f"Use {value} from this dump filename?", parent=self.window):
                    self.hash_value.set(value)
                    self.update_title()
            except USER_ERRORS as exc:
                self.error(exc)

    def discard_imports(self) -> None:
        if self.running or not self.draft.imports:
            return
        if messagebox.askyesno("Discard imports", "Discard all staged artwork imports? No files will change.", parent=self.window):
            self.draft.discard_imports()
            self.load_artwork()
            self.update_title()

    def save(self) -> bool:
        if self.running or not self.resolve_fields():
            return False
        if self.draft.imports:
            paths = "\n".join(str(path) + (" [REPLACE]" if path.exists() else " [NEW]") for path in self.draft.imports)
            if not messagebox.askyesno("Save artwork", f"Write these artwork files?\n\n{paths}", parent=self.window):
                return False
        try:
            backups = self.draft.save()
            self.status.set("Saved." + (f" {len(backups)} backup(s); see log." if backups else ""))
            if backups:
                self.append_log("Save backups:\n" + "\n".join(map(str, backups)) + "\n")
            self.refresh_labels()
            return True
        except USER_ERRORS as exc:
            self.error(exc)
            return False
        finally:
            self.warn_invalid_hashes()

    def reload(self) -> None:
        if self.running:
            return
        if (self.draft.dirty or self.fields_dirty()) and not messagebox.askyesno(
            "Reload", "Discard all drafts and staged imports, then reload saved files?", parent=self.window
        ):
            return
        try:
            draft = Draft(self.draft.root)
        except USER_ERRORS as exc:
            self.error(exc)
            return
        self.draft = draft
        self.current = None
        self.form_original = ()
        self.variants.configure(values=draft.settings["SOURCE_DIRS"])
        self.variant.set(draft.settings["SOURCE_DIRS"][0])
        self.active_variant = self.variant.get()
        self.reported_missing.clear()
        self.masks.clear()
        self.rebuild_tree()
        self.load_artwork()
        self.status.set("Reloaded saved data.")
        self.warn_invalid_hashes()

    def edit_config(self) -> None:
        if self.running or not self.resolve_fields():
            return
        ConfigDialog(self)

    def append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_running(self, running: bool) -> None:
        self.running = running
        if running:
            def disable(parent: tk.Misc) -> None:
                for widget in parent.winfo_children():
                    if (
                        isinstance(widget, ttk.Widget)
                        and not isinstance(
                            widget,
                            (ttk.Frame, ttk.Label, ttk.LabelFrame, ttk.Panedwindow),
                        )
                        and widget is not self.notebook
                        and not widget.instate(["disabled"])
                    ):
                        widget.state(["disabled"])
                        self.disabled_widgets.append(widget)
                    disable(widget)
            disable(self.window)
        else:
            for widget in self.disabled_widgets:
                widget.state(["!disabled"])
            self.disabled_widgets.clear()
        self.update_flip_buttons()

    def generate(self) -> None:
        if self.running or not self.resolve_fields():
            return
        if self.draft.dirty:
            if not messagebox.askokcancel(
                "Save and Generate", "Generation requires saved inputs.\nSave all drafts and generate now?",
                parent=self.window,
            ) or not self.save():
                return
        try:
            self.draft.validate()
            # Detect externally modified inputs even when there is no draft.
            self.draft.save()
            settings = self.draft.settings
            export = resolve_path(self.draft.root, settings["EXPORT_DIR"])
            if settings["CLEAN_EXPORTS"] and not messagebox.askyesno(
                "Confirm export cleanup",
                f"Generation will DELETE and recreate the mod folder:\n{export / settings['MOD_NAME']}\n\n"
                "Other files and folders in the output directory will be kept.\n\nContinue?",
                parent=self.window,
            ):
                return
            self.notebook.select(1)
            self.append_log("\n--- Generating from saved inputs ---\n")
            self.process = subprocess.Popen(
                [sys.executable, "-u", str(self.draft.root / "main.py")],
                cwd=self.draft.root, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, encoding="utf-8", errors="replace",
                env=self.generation_environment(),
            )
            self.set_running(True)
            self.status.set("Generating...")
            threading.Thread(target=self.read_process, args=(self.process,), daemon=True).start()
        except USER_ERRORS as exc:
            self.error(exc)

    @staticmethod
    def generation_environment() -> dict[str, str]:
        import os
        environment = os.environ.copy()
        environment["PYTHONIOENCODING"] = "utf-8"
        return environment

    def read_process(self, process: subprocess.Popen[str]) -> None:
        try:
            if process.stdout is not None:
                for line in process.stdout:
                    self.events.put(("log", line))
                process.stdout.close()
            code = process.wait()
            self.events.put(("done", code))
        except OSError as exc:
            self.events.put(("log", f"Unable to read generation output: {exc}\n"))
            process.wait()
            self.events.put(("done", -1))

    def poll(self) -> None:
        while True:
            try:
                kind, value = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append_log(str(value))
            else:
                self.set_running(False)
                self.process = None
                settings = self.draft.settings
                export = resolve_path(self.draft.root, settings["EXPORT_DIR"])
                mod = export / settings["MOD_NAME"]
                archive = export / archive_name(settings)
                if value == 0 and mod.is_dir() and archive.is_file():
                    self.status.set("Generation completed. Review log for skipped sources.")
                    self.append_log(f"Mod folder: {mod}\nArchive: {archive}\n")
                    self.masks.clear()
                    self.schedule_preview()
                else:
                    self.status.set("Generation failed. See log.")
                    self.error(ValueError(f"Generation failed (exit {value}). See Generation Log."))
        self.window.after(100, self.poll)

    def close(self) -> None:
        if self.running:
            messagebox.showinfo("Generation running", "Wait for generation to finish before closing.", parent=self.window)
            return
        if self.draft.dirty or self.fields_dirty():
            choice = messagebox.askyesnocancel(
                "Unsaved edits", "Save all edits before closing?\nNo discards drafts and staged imports.",
                parent=self.window,
            )
            if choice is None or (choice and not self.save()):
                return
        self.window.destroy()


class ConfigDialog:
    def __init__(self, editor: Editor):
        self.editor = editor
        self.window = tk.Toplevel(editor.window)
        self.window.configure(background=DARK_THEME["background"])
        self.window.title("editor - Config")
        self.window.transient(editor.window)
        self.window.grab_set()
        self.variables: dict[str, tk.Variable] = {}
        frame = ttk.Frame(self.window, padding=14)
        frame.pack(fill="both", expand=True)
        descriptions = {
            "MOD_NAME": "Mod folder and INI name",
            "MOD_VERSION": "Version used in archive filename",
            "CUR_AGENT": "Only generate this agent (blank = all)",
            "EXPORT_DIR": "Output/ZIP directory; cleanup only removes the MOD_NAME subfolder",
            "FALLBACK_MODE": "Legacy option; cross-variant fallback is not implemented",
            "CLEAN_EXPORTS": "Delete and recreate only the MOD_NAME subfolder before generating",
            "SEPARATE_INIS": "Separate Select / Tab / Round INIs",
            "AUTO_APPLY_DRAFT_CHANGES": "Apply edited mask fields to the draft without prompting",
            "BACKUP_FILES": "Back up replaced files in a backup subfolder beside each original",
            "CONTRAST_MULTIPLIER": "Contrast: 1 unchanged, 0 flat",
            "SATURATION_MULTIPLIER": "Saturation: 1 unchanged, 0 grayscale",
            "IMAGE_UPSCALER": "Enlargement: Pillow or Real-ESRGAN anime (NVIDIA GPU)",
        }
        row = 0
        for key in DEFAULTS:
            if key == "SOURCE_DIRS":
                continue
            value = editor.draft.settings[key]
            ttk.Label(frame, text=key).grid(row=row, column=0, sticky="w", pady=4)
            if type(value) is bool:
                variable: tk.Variable = tk.BooleanVar(value=value)
                control = ttk.Checkbutton(frame, variable=variable)
            else:
                variable = tk.StringVar(value="" if value is None else str(value))
                if key == "FALLBACK_MODE":
                    control = ttk.Combobox(frame, textvariable=variable, values=("original", "skip"), state="readonly")
                elif key == "IMAGE_UPSCALER":
                    control = ttk.Combobox(
                        frame, textvariable=variable, values=("pillow", "realesrgan"), state="readonly",
                    )
                elif key == "CUR_AGENT":
                    control = ttk.Combobox(frame, textvariable=variable, values=["", *editor.draft.agents])
                else:
                    control = ttk.Entry(frame, textvariable=variable, width=35)
            self.variables[key] = variable
            control.grid(row=row, column=1, sticky="ew", padx=8)
            ttk.Label(frame, text=descriptions[key]).grid(row=row, column=2, sticky="w")
            row += 1
        ttk.Label(frame, text="SOURCE_DIRS\n(ordered)").grid(row=row, column=0, sticky="nw")
        self.sources = tk.Listbox(
            frame,
            height=5,
            exportselection=False,
            width=40,
            background=DARK_THEME["field"],
            foreground=DARK_THEME["foreground"],
            selectbackground=DARK_THEME["selection"],
            selectforeground=DARK_THEME["foreground"],
            highlightthickness=0,
        )
        for source in editor.draft.settings["SOURCE_DIRS"]:
            self.sources.insert("end", source)
        self.sources.grid(row=row, column=1, sticky="ew", padx=8)
        operations = ttk.Frame(frame)
        operations.grid(row=row, column=2, sticky="nw")
        for text, command in (
            ("Add", self.add_source), ("Remove", self.remove_source),
            ("Move Up", lambda: self.move_source(-1)), ("Move Down", lambda: self.move_source(1)),
        ):
            ttk.Button(operations, text=text, command=command).pack(side="left")
        row += 1
        self.paths = tk.StringVar()
        ttk.Label(frame, textvariable=self.paths, wraplength=850).grid(row=row, column=0, columnspan=3, sticky="w", pady=8)
        self.update_paths()
        row += 2
        ttk.Button(frame, text="Apply", command=self.apply).grid(row=row, column=1)
        ttk.Button(frame, text="Cancel", command=self.window.destroy).grid(row=row, column=2)
        self.window.protocol("WM_DELETE_WINDOW", self.window.destroy)

    def update_paths(self) -> None:
        self.paths.set("Resolved sources:\n" + "\n".join(
            str(resolve_path(self.editor.draft.root, source))
            + (" [missing directory]" if not resolve_path(self.editor.draft.root, source).is_dir() else "")
            for source in self.sources.get(0, "end")
        ))

    def add_source(self) -> None:
        path = filedialog.askdirectory(title="Choose source directory", parent=self.window)
        if path:
            target = Path(path).resolve()
            try:
                display = str(target.relative_to(self.editor.draft.root))
            except ValueError:
                display = str(target)
            self.sources.insert("end", display)
            self.update_paths()

    def remove_source(self) -> None:
        if self.sources.curselection():
            self.sources.delete(self.sources.curselection()[0])
            self.update_paths()

    def move_source(self, delta: int) -> None:
        if not self.sources.curselection():
            return
        index = self.sources.curselection()[0]
        target = index + delta
        if 0 <= target < self.sources.size():
            value = self.sources.get(index)
            self.sources.delete(index)
            self.sources.insert(target, value)
            self.sources.selection_set(target)
            self.update_paths()

    def apply(self) -> None:
        values: dict[str, object] = {key: variable.get() for key, variable in self.variables.items()}
        values["SOURCE_DIRS"] = list(self.sources.get(0, "end"))
        values["CUR_AGENT"] = values["CUR_AGENT"] or None
        try:
            for key in ("CONTRAST_MULTIPLIER", "SATURATION_MULTIPLIER"):
                values[key] = float(str(values[key]))
            backups = self.editor.draft.save_settings(values)
            if backups:
                self.editor.append_log("Config backups:\n" + "\n".join(map(str, backups)) + "\n")
            sources = self.editor.draft.settings["SOURCE_DIRS"]
            self.editor.variants.configure(values=sources)
            if self.editor.variant.get() not in sources:
                self.editor.variant.set(sources[0])
            self.editor.active_variant = self.editor.variant.get()
            if self.editor.current is not None:
                self.editor.reset_fields()
            else:
                self.editor.load_artwork()
            self.editor.update_title()
            self.editor.status.set("Configuration saved.")
            self.window.destroy()
        except USER_ERRORS as exc:
            messagebox.showerror("Invalid configuration", str(exc), parent=self.window)


def main() -> None:
    try:
        window = tk.Tk()
    except tk.TclError as exc:
        raise SystemExit(f"Unable to start Tkinter editor: {exc}\nCheck `python -m tkinter`.") from exc
    window.withdraw()
    while True:
        try:
            draft = Draft(ROOT)
            break
        except USER_ERRORS as exc:
            if not messagebox.askretrycancel(
                "Unable to load editor inputs",
                f"{exc}\n\nCorrect the file externally, then Retry. No files have been changed.",
                parent=window,
            ):
                window.destroy()
                return
    window.deiconify()
    Editor(window, draft)
    window.mainloop()


if __name__ == "__main__":
    main()
