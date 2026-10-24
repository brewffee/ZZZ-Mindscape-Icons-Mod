import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
import zipfile
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image

from config import archive_name
from editor_model import Draft
from support import entry, project


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project(self.root, scripts=True)

    def run_pipeline(self):
        return subprocess.run(
            [sys.executable, "-u", str(self.root / "main.py")],
            cwd=self.root.parent, capture_output=True, text=True, timeout=45,
        )

    def test_ini_headers_match_output_masks_and_variant_count(self):
        kinds = ("Select", "Tab", "Round")
        for separate in (True, False):
            for variant_count in (1, 2):
                with self.subTest(separate=separate, variant_count=variant_count):
                    draft = Draft(self.root)
                    draft.settings["SEPARATE_INIS"] = separate
                    draft.settings["SOURCE_DIRS"] = ["sources/M6", "sources/M3"][:variant_count]
                    draft.save()
                    result = self.run_pipeline()
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    mod = self.root / "export" / "Mindscape Icons"
                    filenames = (
                        [(f"MindscapeIcons_{kind}.ini", (kind,)) for kind in kinds]
                        if separate else [("MindscapeIcons.ini", kinds)]
                    )
                    self.assertEqual(len(list(mod.glob("*.ini"))), len(filenames))
                    for filename, included_kinds in filenames:
                        text = (mod / filename).read_text(encoding="utf-8")
                        self.assertEqual(text.count("global persist $lockIcons = 0"), 1)
                        self.assertEqual(text.count("[KeySwapLock]"), 1)
                        self.assertIn("key = ctrl alt shift L", text)
                        for index, kind in enumerate(kinds, 1):
                            if kind not in included_kinds:
                                self.assertNotIn(f"$use{kind}", text)
                                self.assertNotIn(f"[KeyToggle{kind}]", text)
                                self.assertNotIn(f"[KeySwapVariant{kind}]", text)
                                continue
                            self.assertIn(f"global persist $use{kind} = 1", text)
                            self.assertIn(
                                f"[KeyToggle{kind}]\ncondition = $lockIcons == 0\n"
                                f"key = ctrl alt shift {index}\n", text,
                            )
                            if variant_count > 1:
                                self.assertIn(f"global persist $use{kind}Variant = 0", text)
                                self.assertIn(
                                    f"[KeySwapVariant{kind}]\ncondition = $lockIcons == 0\n"
                                    f"key = ctrl alt {index}\n", text,
                                )
                                self.assertIn(f"$use{kind}Variant = 0,1", text)
                                self.assertIn(f"if $use{kind}Variant == 1", text)
                            else:
                                self.assertNotIn(f"$use{kind}Variant", text)
                                self.assertNotIn(f"[KeySwapVariant{kind}]", text)

    def test_complete_pipeline_and_fresh_settings(self):
        draft = Draft(self.root)
        draft.add_skin("Alice")
        draft.agents["Alice"][1] = {
            # Deliberately scramble field order to exercise named field lookup.
            kind: {"rotation": 10, "scale": .8, "offset": [2, -4], "hash": hash_value}
            for kind, hash_value in (("select", "12345678"), ("tab", "23456789"), ("round", "34567890"))
        }
        settings = deepcopy(draft.settings)
        settings["EXPORT_DIR"] = "generated"
        settings["MOD_NAME"] = "Test Icons"
        settings["MOD_VERSION"] = "4.0"
        draft.set_settings(settings)
        draft.save()
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        output = self.root / "generated"
        mod = output / "Test Icons"
        for kind, size in (("select", (512, 500)), ("tab", (150, 54)), ("round", (150, 150))):
            for variant in ("M6", "M3"):
                for skin in ("", "Skin"):
                    path = mod / kind / f"Alice{skin}{variant}.png"
                    with Image.open(path) as image:
                        self.assertEqual(image.size, size)
            text = (mod / f"TestIcons_{kind.capitalize()}.ini").read_text(encoding="utf-8")
            self.assertIn(f"$use{kind.capitalize()}Variant = 0,1", text)
            self.assertIn(f"filename = {kind}/AliceSkinM6.png", text)
            self.assertIn("hash = 12345678" if kind == "select" else
                          "hash = 23456789" if kind == "tab" else "hash = 34567890", text)
        archive = output / archive_name(settings)
        with zipfile.ZipFile(archive) as zipped:
            self.assertIn("Test Icons/select/AliceSkinM6.png", zipped.namelist())
        self.assertTrue((self.root / "masks" / "selector.png").exists())
        self.assertFalse((self.root / "export").exists())
        # A second fresh process must honor saved changes, retain non-cleaned
        # files, and generate the combined INI mode.
        marker = output / "keep.txt"
        marker.write_text("preserve me")
        draft = Draft(self.root)
        settings = deepcopy(draft.settings)
        settings.update({"CLEAN_EXPORTS": False, "SEPARATE_INIS": False,
                         "MOD_VERSION": "5.0", "CUR_AGENT": "Alice",
                         "SATURATION_MULTIPLIER": 0})
        draft.set_settings(settings)
        draft.save()
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(marker.read_text(), "preserve me")
        self.assertTrue((mod / "TestIcons.ini").exists())
        self.assertTrue((output / archive_name(settings)).exists())
        with Image.open(mod / "select" / "AliceM6.png") as image:
            r, g, b, _ = image.getpixel((256, 250))
            self.assertEqual((r, g), (g, b))

    def test_unsafe_export_fails_before_writes(self):
        settings = json.loads((self.root / "config.json").read_text())
        settings["EXPORT_DIR"] = "."
        (self.root / "config.json").write_text(json.dumps(settings))
        result = self.run_pipeline()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("repository", result.stderr)
        self.assertFalse((self.root / "masks").exists())
        self.assertTrue((self.root / "agents.json").is_file())

    def test_ml_preflight_fails_before_cleanup_or_mask_writes(self):
        draft = Draft(self.root)
        draft.settings["IMAGE_UPSCALER"] = "realesrgan"
        draft.save()
        output = self.root / "export"
        output.mkdir()
        marker = output / "keep.txt"
        marker.write_text("preserve me")
        result = subprocess.run(
            [sys.executable, "-c",
             "import upscaler; from unittest.mock import patch; import main\n"
             "with patch('upscaler.load_model', side_effect=upscaler.UpscaleError('GPU unavailable')):\n"
             "    main.main()\n"],
            cwd=self.root, capture_output=True, text=True, timeout=45,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("GPU unavailable", result.stderr)
        self.assertEqual(marker.read_text(), "preserve me")
        self.assertFalse((self.root / "masks").exists())

    def test_chibi_pipeline_three_inis_mask_artwork_and_transforms(self):
        draft = Draft(self.root)
        settings = deepcopy(draft.settings)
        settings["SOURCE_DIRS"].append("sources/Chibi")
        settings["SATURATION_MULTIPLIER"] = 1
        draft.set_settings(settings)
        draft.add_skin("Alice")
        draft.agents["Alice"][1] = deepcopy(draft.agents["Alice"][0])
        draft.save()
        # Exercise generator initialization independently of editor persistence.
        (self.root / "agents-chibi.json").unlink()
        directory = self.root / "sources" / "Chibi"
        directory.mkdir()
        colors = {"select": (255, 0, 0, 255), "tab": (0, 255, 0, 255), "round": (0, 0, 255, 255)}
        for kind, color in colors.items():
            Image.new("RGBA", (80, 90), color).save(directory / f"Alice-{kind}.png")
        Image.new("RGBA", (80, 90), "yellow").save(directory / "AliceSkin-select.png")
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        chibi = json.loads((self.root / "agents-chibi.json").read_text())
        self.assertEqual(chibi["Alice"][0]["select"], {
            "hash": "1234abcd", "offset": [0, 0], "scale": 1.0, "rotation": 0,
        })
        mod = self.root / "export" / "Mindscape Icons"
        self.assertEqual(len(list(mod.glob("*.ini"))), 3)
        for kind, color in colors.items():
            text = (mod / f"MindscapeIcons_{kind.capitalize()}.ini").read_text()
            self.assertIn(f"$use{kind.capitalize()}Variant = 0,1,2", text)
            self.assertIn(f"if $use{kind.capitalize()}Variant == 2", text)
            self.assertIn(f"filename = {kind}/AliceChibi.png", text)
            self.assertIn(f"filename = {kind}/AliceSkinChibi.png", text)
            with Image.open(mod / kind / "AliceChibi.png") as image:
                self.assertEqual(image.getpixel((image.width // 2, image.height // 2)), color)
        with Image.open(mod / "select" / "AliceSkinChibi.png") as image:
            self.assertEqual(image.getpixel((256, 250)), (255, 255, 0, 255))
        # Preserve separate transforms and ensure non-clean generation cannot
        # resurrect a removed image via a stale exported PNG.
        draft = Draft(self.root)
        draft.chibi_agents["Alice"][0]["select"]["offset"] = [1000, 0]
        draft.settings["CLEAN_EXPORTS"] = False
        draft.save()
        (directory / "Alice-tab.png").unlink()
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        with Image.open(mod / "select" / "AliceChibi.png") as image:
            self.assertEqual(image.getchannel("A").getextrema(), (0, 0))
        text = (mod / "MindscapeIcons_Tab.ini").read_text()
        self.assertNotIn("AliceChibiTab", text)
        self.assertFalse((mod / "tab" / "AliceChibi.png").exists())

    def test_missing_variants_keep_global_indices_even_with_one_resource(self):
        draft = Draft(self.root)
        draft.settings["SOURCE_DIRS"].append("sources/Chibi")
        draft.save()
        (self.root / "sources" / "M6" / "Alice.png").unlink()
        directory = self.root / "sources" / "Chibi"
        directory.mkdir()
        Image.new("RGBA", (80, 90), "red").save(directory / "Alice-select.png")
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mod = self.root / "export" / "Mindscape Icons"
        for kind in ("Select", "Tab", "Round"):
            text = (mod / f"MindscapeIcons_{kind}.ini").read_text()
            self.assertIn(f"if $use{kind}Variant == 1", text)
            self.assertNotIn(f"if $use{kind}Variant == 0", text)
            self.assertEqual(f"if $use{kind}Variant == 2" in text, kind == "Select")
            self.assertNotIn("filename = " + kind.lower() + "/AliceM6.png", text)

    def test_chibi_only_variant_and_combined_ini(self):
        draft = Draft(self.root)
        draft.settings["SOURCE_DIRS"] = ["sources/Chibi"]
        draft.settings["SEPARATE_INIS"] = False
        draft.save()
        directory = self.root / "sources" / "Chibi"
        directory.mkdir()
        Image.new("RGBA", (80, 90), "red").save(directory / "Alice-round.png")
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        mod = self.root / "export" / "Mindscape Icons"
        self.assertEqual(len(list(mod.glob("*.ini"))), 1)
        text = (mod / "MindscapeIcons.ini").read_text()
        self.assertNotIn("[KeySwapVariant]", text)
        self.assertNotIn("$variant", text)
        self.assertIn("filename = round/AliceChibi.png", text)
        self.assertNotIn("[TextureOverrideAliceSelect]", text)
        self.assertNotIn("[TextureOverrideAliceTab]", text)

    def test_cleanup_and_missing_sources_are_visible(self):
        export = self.root / "export"
        export.mkdir()
        mod = export / "Mindscape Icons"
        mod.mkdir()
        marker = mod / "old.txt"
        marker.write_text("old")
        (self.root / "sources" / "M3" / "Alice.png").unlink()
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(marker.exists())
        self.assertIn("not found! Skipping...", result.stdout)
        self.assertTrue((export / "mindscape_icons_v3.3.zip").exists())

    def test_cleanup_removes_only_configured_mod_folder(self):
        draft = Draft(self.root)
        draft.settings["MOD_NAME"] = "Custom Icons"
        draft.save()
        export = self.root / "export"
        nested = export / "Custom Icons" / "old" / "nested"
        nested.mkdir(parents=True)
        (nested / "old.txt").write_text("old")
        (export / "old.zip").write_bytes(b"old")
        (export / ".hidden").write_text("old")
        other_mod = export / "Mindscape Icons"
        other_mod.mkdir()
        (other_mod / "keep.txt").write_text("preserve me")
        result = subprocess.run(
            [sys.executable, "-c",
             "from pathlib import Path\n"
             "from unittest.mock import patch\n"
             "import main\n"
             "remove = main.shutil.rmtree\n"
             "def remove_child(path, *args, **kwargs):\n"
             "    assert Path(path).resolve() == Path('export', 'Custom Icons').resolve(), "
             "'Only the configured mod directory may be deleted'\n"
             "    return remove(path, *args, **kwargs)\n"
             "with patch('main.shutil.rmtree', side_effect=remove_child):\n"
             "    main.main()\n"],
            cwd=self.root, capture_output=True, text=True, timeout=45,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(export.is_dir())
        self.assertFalse((export / "Custom Icons" / "old").exists())
        self.assertEqual((export / "old.zip").read_bytes(), b"old")
        self.assertEqual((export / ".hidden").read_text(), "old")
        self.assertEqual((other_mod / "keep.txt").read_text(), "preserve me")
        self.assertTrue((export / "custom_icons_v3.3.zip").exists())

    def test_cleanup_unlinks_directory_symlinks_without_deleting_targets(self):
        export = self.root / "export"
        export.mkdir()
        outside = self.root / "keep"
        outside.mkdir()
        marker = outside / "keep.txt"
        marker.write_text("preserve me")
        link = export / "Mindscape Icons"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable to this account")
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(link.is_symlink())
        self.assertTrue(link.is_dir())
        self.assertEqual(marker.read_text(), "preserve me")

    def test_main_import_does_not_generate(self):
        result = subprocess.run(
            [sys.executable, "-c", "import main; print('imported')"], cwd=self.root,
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "imported")
        self.assertFalse((self.root / "export").exists())
        self.assertFalse((self.root / "masks").exists())

    def test_single_variant_defines_toggle_constants(self):
        draft = Draft(self.root)
        settings = deepcopy(draft.settings)
        settings["SOURCE_DIRS"] = ["sources/M6/"]
        draft.set_settings(settings)
        draft.save()
        result = self.run_pipeline()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        ini = self.root / "export" / "Mindscape Icons" / "MindscapeIcons_Select.ini"
        text = ini.read_text(encoding="utf-8")
        self.assertIn("global persist $useSelect = 1", text)
        self.assertIn("filename = select/AliceM6.png", text)
        self.assertNotIn("[KeySwapVariant]", text)

    def test_editor_launches_from_another_working_directory_without_writes(self):
        script = (
            "import runpy, tkinter as tk; "
            "tk.Tk.mainloop = lambda self: self.destroy(); "
            f"runpy.run_path({str(self.root / 'editor.py')!r}, run_name='__main__')"
        )
        original = (self.root / "agents.json").read_bytes()
        result = subprocess.run(
            [sys.executable, "-c", script], cwd=self.root.parent,
            capture_output=True, text=True, timeout=20,
            env={**os.environ, "PYTHONPATH": str(self.root)},
        )
        if "no display name" in result.stderr:
            self.skipTest("Native Tk display unavailable")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertFalse((self.root / "export").exists())
        self.assertFalse((self.root / "masks").exists())


class GuiTests(unittest.TestCase):
    def setUp(self):
        import gc
        gc.collect()
        import tkinter as tk
        from editor import Editor
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project(self.root, scripts=True)
        try:
            self.window = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"Native Tk display unavailable: {exc}")
        self.window.withdraw()
        self.addCleanup(self.destroy)
        self.editor = Editor(self.window, Draft(self.root))
        self.window.update()

    def destroy(self):
        if self.editor.process is not None:
            if self.editor.process.poll() is None:
                self.editor.process.terminate()
            self.editor.process.wait(timeout=10)
        for job in self.window.tk.call("after", "info"):
            self.window.after_cancel(job)
        self.window.destroy()

    def select_mask(self, kind="select"):
        self.editor.current = ("Alice", 0, kind)
        self.editor.reset_fields()
        self.window.update()

    def test_missing_artwork_log_tags_variant_switch_and_import(self):
        editor = self.editor
        editor.draft.settings["SOURCE_DIRS"].append("sources/Chibi")
        editor.variants.configure(values=editor.draft.settings["SOURCE_DIRS"])
        self.select_mask()
        with patch("editor.messagebox.showwarning") as warning, patch("editor.messagebox.showerror") as error:
            editor.variant.set("sources/Chibi")
            editor.change_variant()
            self.window.update()
            self.assertEqual(editor.variables["scale"].get(), "1.0")
            for item in editor.tree_items:
                self.assertIn("missing_artwork", editor.tree.item(item, "tags"))
            log = editor.log.get("1.0", "end")
            self.assertIn("Alice-select.png", log)
            self.assertIn("Alice-tab.png", log)
            self.assertIn("Alice-round.png", log)
            editor.refresh_labels()
            self.assertEqual(editor.log.get("1.0", "end"), log)
            art = self.root / "chibi.png"
            Image.new("RGBA", (40, 40), "red").save(art)
            with patch("editor.filedialog.askopenfilename", return_value=str(art)), patch(
                "editor.messagebox.askyesno", return_value=False
            ):
                editor.import_art()
            select_item = next(item for item, data in editor.tree_items.items() if data[2] == "select")
            self.assertNotIn("missing_artwork", editor.tree.item(select_item, "tags"))
            editor.variables["x"].set("25")
            with patch("editor.messagebox.askyesnocancel", return_value=True):
                editor.variant.set("sources/M6")
                editor.change_variant()
            self.assertEqual(editor.draft.chibi_agents["Alice"][0]["select"]["offset"], [25, 0])
            self.assertEqual(editor.draft.agents["Alice"][0]["select"]["offset"], [0, 0])
            self.assertEqual(editor.variables["scale"].get(), "0.7")
            self.assertTrue(all("missing_artwork" not in editor.tree.item(item, "tags") for item in editor.tree_items))
            (self.root / "sources" / "M3" / "Alice.png").unlink()
            editor.variant.set("sources/M3")
            editor.change_variant()
            self.assertTrue(all("missing_artwork" in editor.tree.item(item, "tags") for item in editor.tree_items))
            self.assertIn("sources/M3 / Alice", editor.log.get("1.0", "end"))
            warning.assert_not_called()
            error.assert_not_called()

    def test_variant_switch_cancel_keeps_original_source_and_fields(self):
        self.select_mask()
        self.editor.variables["x"].set("12")
        with patch("editor.messagebox.askyesnocancel", return_value=None):
            self.editor.variant.set("sources/M3")
            self.editor.change_variant()
        self.assertEqual(self.editor.variant.get(), "sources/M6")
        self.assertEqual(self.editor.variables["x"].get(), "12")

    def test_previews_flip_vertically_without_changing_inputs_or_rendering(self):
        from PIL import ImageTk
        from textures import MASK_SPECS, render_mask

        photo_image = ImageTk.PhotoImage
        agents = deepcopy(self.editor.draft.agents)
        files = {path: path.read_bytes() for path in self.root.rglob("*.png")}
        for kind, spec in MASK_SPECS.items():
            with self.subTest(kind=kind):
                self.select_mask(kind)
                # Asymmetric artwork makes an omitted display flip detectable.
                self.editor.image = Image.new("RGBA", (80, 90), "red")
                self.editor.image.paste("blue", (0, 0, 80, 30))
                artwork = self.editor.image.tobytes()
                self.editor.preview()
                mask = self.editor.masks[kind]
                mask_pixels = mask.tobytes()
                entry = self.editor.entry()
                args = (
                    spec.size, mask, self.editor.image, tuple(entry["offset"]),
                    entry["scale"], entry["rotation"], spec.final_size,
                    self.editor.draft.settings["CONTRAST_MULTIPLIER"],
                    self.editor.draft.settings["SATURATION_MULTIPLIER"],
                )
                rendered = render_mask(*args).tobytes()
                values = self.editor.values()
                unflipped = []
                displayed = []

                def capture(target):
                    def make_photo(image):
                        target.append(image.copy())
                        return photo_image(image)
                    return make_photo

                with patch.object(Image.Image, "transpose", lambda image, method: image.copy()), patch(
                    "editor.ImageTk.PhotoImage", side_effect=capture(unflipped)
                ):
                    self.editor.preview()
                with patch("editor.ImageTk.PhotoImage", side_effect=capture(displayed)):
                    self.editor.preview()
                self.assertEqual(len(displayed), 2)
                for original, flipped in zip(unflipped, displayed):
                    expected = original.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                    self.assertNotEqual(original.tobytes(), expected.tobytes())
                    self.assertEqual(flipped.tobytes(), expected.tobytes())
                self.assertEqual(self.editor.values(), values)
                self.assertEqual(self.editor.image.tobytes(), artwork)
                self.assertEqual(mask.tobytes(), mask_pixels)
                self.assertEqual(render_mask(*args).tobytes(), rendered)
        self.assertEqual(self.editor.draft.agents, agents)
        self.assertFalse(self.editor.draft.dirty)
        for path, content in files.items():
            self.assertEqual(path.read_bytes(), content)

    def test_native_preview_apply_save_and_config(self):
        from editor import ConfigDialog
        self.select_mask()
        for kind in ("select", "tab", "round"):
            self.select_mask(kind)
            self.editor.variables["x"].set("13")
            self.editor.variables["rotation"].set("210")
            self.editor.preview()
            self.assertIn("Output", self.editor.preview_text.get())
            self.assertEqual(len(self.editor.photos), 2)
            self.assertTrue(self.editor.apply())
        self.editor.variant.set("sources/M3")
        self.editor.load_artwork()
        self.editor.preview()
        self.assertTrue(self.editor.save())
        self.assertEqual(Draft(self.root).agents["Alice"][0]["tab"]["offset"], [13, 0])
        dialog = ConfigDialog(self.editor)
        dialog.variables["MOD_NAME"].set("Edited Icons")
        dialog.variables["MOD_VERSION"].set("6.0")
        dialog.variables["CUR_AGENT"].set("Alice")
        dialog.variables["EXPORT_DIR"].set("build")
        dialog.variables["FALLBACK_MODE"].set("skip")
        dialog.variables["CLEAN_EXPORTS"].set(False)
        dialog.variables["SEPARATE_INIS"].set(False)
        dialog.variables["AUTO_APPLY_DRAFT_CHANGES"].set(True)
        dialog.variables["BACKUP_FILES"].set(False)
        dialog.variables["CONTRAST_MULTIPLIER"].set("0.5")
        dialog.variables["SATURATION_MULTIPLIER"].set("0")
        dialog.variables["IMAGE_UPSCALER"].set("realesrgan")
        dialog.sources.selection_set(1)
        dialog.move_source(-1)
        dialog.apply()
        self.assertEqual(self.editor.draft.settings["SOURCE_DIRS"][0], "sources/M3")
        self.assertEqual(self.editor.draft.settings["SATURATION_MULTIPLIER"], 0)
        self.assertEqual(self.editor.draft.settings["IMAGE_UPSCALER"], "realesrgan")
        self.assertTrue(self.editor.draft.settings["AUTO_APPLY_DRAFT_CHANGES"])
        self.assertFalse(self.editor.draft.settings["BACKUP_FILES"])
        self.assertTrue(self.editor.save())
        self.assertEqual(Draft(self.root).settings["MOD_VERSION"], "6.0")
        self.assertEqual(Draft(self.root).settings, self.editor.draft.settings)

    def test_ml_backend_reaches_both_previews_and_reports_failure(self):
        from textures import position_image, render_mask
        from upscaler import UpscaleError

        self.select_mask()
        self.editor.draft.settings["IMAGE_UPSCALER"] = "realesrgan"
        self.editor.image = Image.new("RGBA", (180, 180), (100, 80, 200, 200))
        self.editor.variables["scale"].set(str(512 / 180))
        with patch("upscaler._upscale_rgb", return_value=Image.new("RGB", (720, 720))), patch(
            "editor.position_image", wraps=position_image,
        ) as position, patch("editor.render_mask", wraps=render_mask) as render:
            self.editor.preview()
        self.assertIn("Output 512 x 500", self.editor.preview_text.get())
        self.assertEqual(position.call_args.args[-1], "realesrgan")
        self.assertEqual(render.call_args.args[-1], "realesrgan")
        self.assertFalse(position.call_args.kwargs["denoise"])
        self.assertFalse(render.call_args.kwargs["denoise"])
        with patch("upscaler._upscale_rgb", side_effect=UpscaleError("GPU unavailable")):
            self.editor.preview()
        self.assertIn("GPU unavailable", self.editor.preview_text.get())

    def test_chibi_cleanup_reaches_both_previews(self):
        from textures import position_image, render_mask
        from upscaler import _denoise_rgb, _resize_denoised

        self.select_mask()
        self.editor.variant.set("sources/Chibi")
        self.editor.image = Image.new("RGBA", (128, 128), (100, 80, 200, 200))
        self.editor.variables["scale"].set("4")
        _resize_denoised.cache_clear()
        _denoise_rgb.cache_clear()
        self.addCleanup(_resize_denoised.cache_clear)
        self.addCleanup(_denoise_rgb.cache_clear)
        with patch("editor.position_image", wraps=position_image) as position, patch(
            "editor.render_mask", wraps=render_mask,
        ) as render:
            self.editor.preview()
        self.assertIn("Output 512 x 500", self.editor.preview_text.get())
        self.assertTrue(position.call_args.kwargs["denoise"])
        self.assertTrue(render.call_args.kwargs["denoise"])
        self.assertEqual(_denoise_rgb.cache_info().misses, 1)
        self.assertEqual(_resize_denoised.cache_info().hits, 1)

    def test_generate_gates_unsaved_and_cleanup_cancel(self):
        self.editor.draft.add_agent("New")
        with patch("editor.messagebox.askokcancel", return_value=False), patch("editor.subprocess.Popen") as popen:
            self.editor.generate()
            popen.assert_not_called()
        with patch("editor.messagebox.askokcancel", return_value=True), patch.object(
            self.editor, "save", return_value=False
        ), patch("editor.subprocess.Popen") as popen:
            self.editor.generate()
            popen.assert_not_called()
        self.editor.draft = Draft(self.root)
        with patch("editor.messagebox.askyesno", return_value=False), patch("editor.subprocess.Popen") as popen:
            self.editor.generate()
            popen.assert_not_called()

    def test_native_generate_complete_and_close_guard(self):
        with patch("editor.messagebox.askyesno", return_value=True):
            self.editor.generate()
        self.assertTrue(self.editor.running)
        with patch("editor.messagebox.showinfo") as info:
            self.editor.close()
            info.assert_called_once()
        with patch("editor.subprocess.Popen") as popen:
            self.editor.generate()
            popen.assert_not_called()
        deadline = time.monotonic() + 30
        while self.editor.running and time.monotonic() < deadline:
            self.window.update()
            time.sleep(.02)
        self.assertFalse(
            self.editor.running,
            f"Process state: {self.editor.process.poll() if self.editor.process else None}\n"
            + self.editor.log.get("1.0", "end"),
        )
        self.assertIn("Generation completed", self.editor.status.get())
        self.assertIn("Archive:", self.editor.log.get("1.0", "end"))
        self.assertTrue((self.root / "export" / "mindscape_icons_v3.3.zip").exists())

    def test_subprocess_failure_and_arguments(self):
        process = Mock(stdout=io.StringIO("Injected failure log\n"))
        process.wait.return_value = 7
        with patch("editor.subprocess.Popen", return_value=process) as popen, patch(
            "editor.messagebox.askyesno", return_value=True
        ), patch("editor.threading.Thread"):
            self.editor.generate()
            args, kwargs = popen.call_args
            self.assertEqual(args[0], [sys.executable, "-u", str(self.root / "main.py")])
            self.assertEqual(kwargs["cwd"], self.root)
            self.assertNotIn("shell", kwargs)
        self.editor.read_process(process)
        with patch("editor.messagebox.showerror") as error:
            self.editor.poll()
            error.assert_called_once()
        self.assertFalse(self.editor.running)
        self.assertIn("Injected failure", self.editor.log.get("1.0", "end"))
        self.assertIn("failed", self.editor.status.get())

    def test_process_start_error_is_visible(self):
        with patch("editor.subprocess.Popen", side_effect=OSError("Missing executable")), patch(
            "editor.messagebox.askyesno", return_value=True
        ), patch("editor.messagebox.showerror") as error:
            self.editor.generate()
            error.assert_called_once()
        self.assertFalse(self.editor.running)

    def test_unapplied_edit_cancel_and_discard(self):
        self.select_mask()
        self.editor.variables["x"].set("99")
        with patch("editor.messagebox.askyesnocancel", return_value=None):
            self.assertFalse(self.editor.resolve_fields())
        self.assertEqual(self.editor.variables["x"].get(), "99")
        with patch("editor.messagebox.askyesnocancel", return_value=False):
            self.assertTrue(self.editor.resolve_fields())
        self.assertEqual(self.editor.variables["x"].get(), "0")

    def test_auto_apply_draft_changes_skips_prompt_and_applies_edits(self):
        self.select_mask()
        self.editor.variables["x"].set("99")
        settings = deepcopy(self.editor.draft.settings)
        settings["AUTO_APPLY_DRAFT_CHANGES"] = True
        self.editor.draft.set_settings(settings)

        with patch("editor.messagebox.askyesnocancel") as prompt:
            self.assertTrue(self.editor.resolve_fields())

        prompt.assert_not_called()
        self.assertEqual(self.editor.draft.agents["Alice"][0]["select"]["offset"], [99, 0])
        self.assertFalse(self.editor.fields_dirty())

    def test_navigation_applies_previous_fields_without_snapping_back(self):
        items = {data[2]: item for item, data in self.editor.tree_items.items() if data[2]}
        self.editor.tree.selection_set(items["select"])
        self.window.update()
        self.editor.variables["x"].set("12")
        with patch("editor.messagebox.askyesnocancel", return_value=True):
            self.editor.tree.selection_set(items["tab"])
            self.window.update()
        self.assertEqual(self.editor.current, ("Alice", 0, "tab"))
        self.assertEqual(self.editor.draft.agents["Alice"][0]["select"]["offset"], [12, 0])

    def test_add_import_remove_and_dirty_close_cancel(self):
        with patch("editor.simpledialog.askstring", return_value="NewAgent"):
            self.editor.add_agent()
        self.window.update()
        self.editor.add_skin()
        self.window.update()
        self.assertEqual(self.editor.current, ("NewAgent", 1, "select"))
        art = self.root / "art.png"
        image = Image.new("RGBA", (50, 60), "blue")
        image.paste("red", (0, 0, 50, 30))
        image.save(art)
        with patch("editor.filedialog.askopenfilename", return_value=str(art)), patch(
            "editor.messagebox.askyesno", return_value=True
        ) as ask_flip:
            self.editor.import_art()
        ask_flip.assert_called_once()
        target = self.editor.draft.target("sources/M6", "NewAgent", 1)
        self.assertEqual(self.editor.draft.imports[target].getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(self.editor.draft.imports[target].getpixel((0, 59)), (255, 0, 0, 255))
        self.editor.hash_value.set("abcdef01")
        self.assertTrue(self.editor.apply())
        with patch("editor.messagebox.askyesno", return_value=True):
            self.assertTrue(self.editor.save())
            self.editor.remove_mask()
        self.assertNotIn("select", self.editor.draft.agents["NewAgent"][1])
        self.assertTrue(self.editor.draft.target("sources/M6", "NewAgent", 1).exists())
        with patch("editor.messagebox.askyesnocancel", return_value=None):
            self.editor.close()
        self.assertTrue(self.window.winfo_exists())
