import json
import os
import tempfile
import tkinter as tk
import unittest
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch
from tkinter import ttk

from PIL import Image

from editor import DARK_THEME, ConfigDialog, Editor, apply_dark_theme
from editor_model import (
    BLANK_HASH, Draft, duplicate_hashes, hash_from_filename, validate_mask,
    validate_transform_image,
)
from support import entry, project


class DraftTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        project(self.root)
        self.draft = Draft(self.root)

    def artwork(self, color="red"):
        path = self.root / "import.png"
        Image.new("RGBA", (12, 14), color).save(path)
        return path

    def test_noop_save_keeps_exact_bytes_and_no_backups(self):
        original = (self.root / "agents.json").read_bytes()
        self.assertFalse(self.draft.dirty)
        self.assertEqual(self.draft.save(), [])
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertEqual(list(self.root.rglob("*.bak")), [])

    def test_backups_can_be_disabled_for_json_and_artwork(self):
        settings = deepcopy(self.draft.settings)
        settings["BACKUP_FILES"] = False
        self.draft.set_settings(settings)
        self.draft.add_agent("Bob")
        target = self.draft.target("sources/M6", "Alice", 0)
        target.write_bytes((self.root / "sources" / "M6" / "Alice.png").read_bytes())
        self.draft.stage_image("sources/M6", "Alice", 0, self.artwork("blue"))

        backups = self.draft.save()

        self.assertEqual(backups, [])
        self.assertEqual(list(self.root.rglob("*.bak")), [])
        self.assertEqual(list(self.root.rglob("backup")), [])
        self.assertEqual(list(self.root.rglob(".editor-*")), [])
        with Image.open(target) as image:
            self.assertEqual(image.getpixel((0, 0)), (0, 0, 255, 255))

    def test_disabled_backups_preserve_atomic_rollback(self):
        agents_path = self.root / "agents.json"
        config_path = self.root / "config.json"
        original_agents = agents_path.read_bytes()
        original_config = config_path.read_bytes()
        self.draft.add_agent("Bob")
        settings = deepcopy(self.draft.settings)
        settings["BACKUP_FILES"] = False
        self.draft.set_settings(settings)
        replace = os.replace
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Injected replacement failure")
            return replace(source, target)

        with patch("editor_model.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "Previous files restored"):
                self.draft.save()

        self.assertEqual(agents_path.read_bytes(), original_agents)
        self.assertEqual(config_path.read_bytes(), original_config)
        self.assertEqual(list(self.root.rglob(".editor-rollback-*")), [])
        self.assertEqual(list(self.root.rglob("*.json.*.bak")), [])

    def test_backups_use_each_original_files_local_backup_folder(self):
        self.enable_chibi()
        self.draft.save()
        originals = {}
        for source, kind in (
            ("sources/M6", "select"), ("sources/M3", "tab"),
            ("sources/Chibi", "select"), ("sources/Chibi", "tab"),
            ("sources/Chibi", "round"),
        ):
            target = self.draft.target(source, "Alice", 0, kind)
            target.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (12, 14), "red").save(target)
            originals[target] = target.read_bytes()
            self.draft.stage_image(source, "Alice", 0, self.artwork("blue"), kind=kind)
        for name in ("agents.json", "agents-chibi.json"):
            path = self.root / name
            originals[path] = path.read_bytes()
        self.draft.add_agent("Bob")

        backups = self.draft.save()

        self.assertEqual(len(backups), len(originals))
        for original, content in originals.items():
            matches = [
                backup for backup in backups
                if backup.parent == original.parent / "backup"
                and backup.name.startswith(original.name + ".")
            ]
            self.assertEqual(len(matches), 1, str(original))
            self.assertEqual(matches[0].read_bytes(), content)
        self.assertEqual(list(self.root.glob("*.bak")), [])
        self.assertEqual(self.draft.save(), [])

    def test_disabled_backups_restore_overwritten_artwork_on_save_failure(self):
        settings = deepcopy(self.draft.settings)
        settings["BACKUP_FILES"] = False
        self.draft.set_settings(settings)
        originals = {self.root / "config.json": (self.root / "config.json").read_bytes()}
        for source in self.draft.settings["SOURCE_DIRS"]:
            target = self.draft.target(source, "Alice", 0)
            Image.new("RGBA", (12, 14), "red").save(target)
            originals[target] = target.read_bytes()
            self.draft.stage_image(source, "Alice", 0, self.artwork("blue"))
        replace = os.replace
        calls = 0

        def fail_third(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("Injected replacement failure")
            return replace(source, target)

        with patch("editor_model.os.replace", side_effect=fail_third):
            with self.assertRaisesRegex(ValueError, "Previous files restored"):
                self.draft.save()

        for path, content in originals.items():
            self.assertEqual(path.read_bytes(), content)
        self.assertEqual(list(self.root.rglob("*.bak")), [])
        self.assertEqual(list(self.root.rglob(".editor-*")), [])
        self.assertTrue(self.draft.dirty)

    def test_backup_folder_creation_failure_does_not_replace_original(self):
        original = (self.root / "agents.json").read_bytes()
        (self.root / "backup").write_text("not a directory", encoding="utf-8")
        self.draft.add_agent("Bob")
        with self.assertRaisesRegex(ValueError, "Save failed"):
            self.draft.save()
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertEqual(list(self.root.rglob(".editor-*")), [])
        self.assertTrue(self.draft.dirty)

    def enable_chibi(self):
        settings = deepcopy(self.draft.settings)
        settings["SOURCE_DIRS"].append("sources/Chibi")
        self.draft.set_settings(settings)

    def test_chibi_defaults_save_and_independent_transforms(self):
        self.enable_chibi()
        self.draft.add_skin("Alice")
        self.draft.agents["Alice"][1] = {"select": entry("abcdef12")}
        original = deepcopy(self.draft.agents)
        chibi = self.draft.agents_for("sources/Chibi")
        for index, skin in enumerate(chibi["Alice"]):
            for kind, mask in skin.items():
                self.assertEqual(mask, {
                    "hash": original["Alice"][index][kind]["hash"],
                    "offset": [0, 0], "scale": 1.0, "rotation": 0,
                })
        self.assertFalse((self.root / "agents-chibi.json").exists())
        adjusted = {**entry(), "offset": [12, -30], "rotation": 90, "scale": 1.5}
        # Missing artwork must not prevent editing hashes and transforms.
        self.draft.apply_mask("Alice", 0, "select", adjusted, "sources/Chibi")
        self.assertEqual(self.draft.agents, original)
        self.draft.save()
        loaded = Draft(self.root)
        self.assertEqual(loaded.agents, original)
        self.assertEqual(loaded.agents_for("sources/Chibi")["Alice"][0]["select"], adjusted)
        self.assertFalse(loaded.dirty)
        self.assertEqual(loaded.save(), [])

    def test_chibi_uses_canonical_hashes_and_tracks_structure_changes(self):
        self.enable_chibi()
        self.draft.apply_mask("Alice", 0, "tab", entry("abcdef12"), "sources/Chibi")
        self.assertEqual(self.draft.agents["Alice"][0]["tab"]["hash"], "abcdef12")
        self.draft.agents["Alice"][0]["select"]["hash"] = "abcdef34"
        self.draft.agents["Alice"][0].pop("round")
        self.draft.add_skin("Alice")
        self.draft.agents["Alice"][1] = {"round": entry("abcdef56")}
        self.draft.add_agent("Bob")
        self.draft.save()
        data = json.loads((self.root / "agents-chibi.json").read_text())
        self.assertEqual(data["Alice"][0]["select"]["hash"], "abcdef34")
        self.assertNotIn("round", data["Alice"][0])
        self.assertEqual(data["Alice"][1]["round"]["scale"], 1.0)
        self.assertEqual(data["Bob"], [{}])
        # Hashes are authoritative in agents.json, even after external edits.
        data["Alice"][0]["select"]["hash"] = "11111111"
        data["Alice"][0]["select"]["offset"] = [3, 4]
        (self.root / "agents-chibi.json").write_text(json.dumps(data))
        loaded = Draft(self.root)
        self.assertEqual(loaded.agents_for("Chibi")["Alice"][0]["select"]["hash"], "abcdef34")
        self.assertEqual(loaded.agents_for("Chibi")["Alice"][0]["select"]["offset"], [3, 4])
        self.assertTrue(loaded.dirty)
        loaded.save()
        saved = json.loads((self.root / "agents-chibi.json").read_text())
        self.assertEqual(saved["Alice"][0]["select"]["hash"], "abcdef34")
        self.assertFalse(Draft(self.root).dirty)

    def test_chibi_imports_missing_artwork_and_skin_fallbacks(self):
        self.enable_chibi()
        self.draft.add_skin("Alice")
        self.draft.agents["Alice"][1] = {"select": entry()}
        self.assertEqual(len(self.draft.missing_artwork("sources/Chibi")), 4)
        target = self.draft.stage_image("sources/Chibi", "Alice", 0, self.artwork(), kind="select")
        self.assertEqual(target.name, "Alice-select.png")
        self.assertEqual(len(self.draft.missing_artwork("sources/Chibi")), 2)
        self.assertEqual(self.draft.artwork("sources/Chibi", "Alice", 1, "select")[1], target)
        self.draft.discard_imports()
        self.assertEqual(len(self.draft.missing_artwork("sources/Chibi")), 4)
        self.draft.stage_image("sources/Chibi", "Alice", 1, self.artwork(), kind="select")
        self.draft.save()
        loaded = Draft(self.root)
        self.assertEqual(loaded.artwork("sources/Chibi", "Alice", 1, "select")[1].name, "AliceSkin-select.png")
        self.assertEqual(len(loaded.missing_artwork("sources/Chibi")), 3)
        self.assertEqual(loaded.missing_artwork("sources/M6"), {})
        (self.root / "sources" / "M6" / "Alice.png").unlink()
        self.assertEqual(len(loaded.missing_artwork("sources/M6")), 4)

    def test_chibi_save_conflict_and_rollback(self):
        self.enable_chibi()
        original = (self.root / "config.json").read_bytes()
        with patch("editor_model.os.replace", side_effect=OSError("Injected failure")):
            with self.assertRaisesRegex(ValueError, "Save failed"):
                self.draft.save()
        self.assertFalse((self.root / "agents-chibi.json").exists())
        self.assertEqual((self.root / "config.json").read_bytes(), original)
        self.draft.save()
        self.draft.chibi_agents["Alice"][0]["select"]["offset"] = [2, 3]
        path = self.root / "agents-chibi.json"
        path.write_text(path.read_text() + "\n")
        with self.assertRaisesRegex(ValueError, "changed outside"):
            self.draft.save()

    def test_load_replaces_invalid_hashes_and_saves_repairs(self):
        path = self.root / "agents.json"
        agents = {
            "Alice": [
                {"select": entry("bad"), "tab": entry(None), "round": entry("ABCDEF12")},
                {"select": entry(12345678)},
                {"round": entry("gggggggg")},
            ],
            "Bob": [{"tab": entry("")}],
        }
        path.write_text(json.dumps(agents), encoding="utf-8")
        original = path.read_bytes()
        draft = Draft(self.root)
        self.assertEqual(draft.hash_warnings, [
            "Alice / base: select, tab", "Alice / skin1: select",
            "Alice / skin2: round", "Bob / base: tab",
        ])
        self.assertEqual(draft.agents["Alice"][0]["round"]["hash"], "ABCDEF12")
        for name, index, kind in (
            ("Alice", 0, "select"), ("Alice", 0, "tab"), ("Alice", 1, "select"),
            ("Alice", 2, "round"), ("Bob", 0, "tab"),
        ):
            self.assertEqual(draft.agents[name][index][kind]["hash"], BLANK_HASH)
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(draft.dirty)
        draft.hash_warnings.clear()
        self.assertTrue(draft.dirty)
        backups = draft.save()
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(json.loads(path.read_bytes()), draft.agents)
        loaded = Draft(self.root)
        self.assertEqual(loaded.hash_warnings, [])
        self.assertFalse(loaded.dirty)

    def test_load_sorts_agents_and_save_repairs_json_order(self):
        path = self.root / "agents.json"
        path.write_text(
            json.dumps({"Zoe": [{}], "alice": [{}], "Bob": [{}]}),
            encoding="utf-8",
        )
        original = path.read_bytes()

        draft = Draft(self.root)
        self.assertEqual(list(draft.agents), ["alice", "Bob", "Zoe"])
        self.assertTrue(draft.dirty)
        backups = draft.save()

        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(list(json.loads(path.read_text(encoding="utf-8"))), ["alice", "Bob", "Zoe"])
        self.assertFalse(draft.dirty)
        self.assertEqual(draft.save(), [])

    def test_save_replaces_invalid_hashes_and_preserves_other_edits(self):
        self.draft.agents["Alice"][0]["select"]["hash"] = "not hex"
        self.draft.agents["Alice"][0]["tab"]["hash"] = ""
        self.draft.agents["Alice"][0]["round"]["offset"] = [10, -20]
        self.draft.save()
        self.assertEqual(self.draft.hash_warnings, ["Alice / base: select, tab"])
        loaded = Draft(self.root)
        self.assertEqual(loaded.agents["Alice"][0]["select"]["hash"], BLANK_HASH)
        self.assertEqual(loaded.agents["Alice"][0]["tab"]["hash"], BLANK_HASH)
        self.assertEqual(loaded.agents["Alice"][0]["round"]["offset"], [10, -20])
        self.assertFalse(self.draft.dirty)

    def test_save_spaces_inline_mask_objects(self):
        self.draft.agents["Alice"][0]["select"]["hash"] = "89abcdef"

        self.draft.save()

        saved = (self.root / "agents.json").read_text(encoding="utf-8")
        self.assertIn(
            '      "select": { "hash": "89abcdef", "offset": [0, 0], '
            '"scale": 0.7, "rotation": 0 }',
            saved,
        )

    def test_hash_repair_does_not_hide_structural_errors(self):
        path = self.root / "agents.json"
        for field, value in (("offset", [1.5, 0]), ("scale", 0), ("rotation", "bad")):
            with self.subTest(field=field):
                invalid = entry("bad")
                invalid[field] = value
                path.write_text(json.dumps({"Alice": [{"select": invalid}]}), encoding="utf-8")
                with self.assertRaisesRegex(ValueError, field):
                    Draft(self.root)
        self.draft.agents["Alice"][0]["select"]["hash"] = "bad"
        self.draft.agents["Alice"][0]["select"]["scale"] = 0
        original = path.read_bytes()
        with self.assertRaisesRegex(ValueError, "scale"):
            self.draft.save()
        self.assertEqual(path.read_bytes(), original)

    def test_apply_invalid_hash_uses_placeholder_without_mutating_input(self):
        data = entry("invalid")
        self.draft.apply_mask("Alice", 0, "select", data, "sources/M6")
        self.assertEqual(data["hash"], "invalid")
        self.assertEqual(self.draft.agents["Alice"][0]["select"]["hash"], BLANK_HASH)
        self.assertEqual(self.draft.hash_warnings, ["Alice / base: select"])
        self.draft.save()
        self.assertEqual(Draft(self.root).agents, self.draft.agents)

    def test_apply_still_rejects_missing_fields(self):
        data = entry()
        del data["hash"]
        with self.assertRaisesRegex(ValueError, "expected hash"):
            self.draft.apply_mask("Alice", 0, "select", data, "sources/M6")
        self.assertEqual(self.draft.hash_warnings, [])

    def test_failed_hash_repair_save_can_be_retried(self):
        path = self.root / "agents.json"
        original = path.read_bytes()
        self.draft.agents["Alice"][0]["select"]["hash"] = "invalid"
        with patch("editor_model.shutil.copy2", side_effect=OSError("No permission")):
            with self.assertRaisesRegex(ValueError, "Save failed"):
                self.draft.save()
        self.assertEqual(path.read_bytes(), original)
        self.assertTrue(self.draft.dirty)
        self.draft.hash_warnings.clear()
        self.draft.save()
        self.assertFalse(self.draft.dirty)
        self.assertEqual(Draft(self.root).agents["Alice"][0]["select"]["hash"], BLANK_HASH)

    def test_blank_placeholders_do_not_trigger_duplicate_warnings(self):
        self.draft.agents["Alice"][0]["select"]["hash"] = BLANK_HASH
        self.draft.agents["Alice"][0]["tab"]["hash"] = BLANK_HASH
        self.assertEqual(duplicate_hashes(self.draft.agents), [])

    def editor(self):
        editor = Editor.__new__(Editor)
        editor.draft = self.draft
        editor.window = Mock()
        editor.append_log = Mock()
        editor.hash_value = Mock()
        editor.hash_value.get.return_value = "invalid"
        editor.variables = {}
        for key, value in (("x", "0"), ("y", "0"), ("scale", "0.7"), ("rotation", "0")):
            editor.variables[key] = Mock()
            editor.variables[key].get.return_value = value
        return editor

    def test_editor_apply_warns_and_updates_invalid_hash_field(self):
        editor = self.editor()
        editor.running = False
        editor.current = ("Alice", 0, "select")
        editor.variant = Mock()
        editor.variant.get.return_value = "sources/M6"
        editor.refresh_labels = Mock()
        editor.status = Mock()
        with patch("editor.messagebox.showwarning") as warning:
            self.assertTrue(editor.apply())
        self.assertIn("Alice / base: select", warning.call_args.args[1])
        editor.hash_value.set.assert_called_once_with(BLANK_HASH)
        self.assertEqual(self.draft.hash_warnings, [])

    def test_editor_save_warns_but_continues(self):
        editor = self.editor()
        editor.running = False
        editor.resolve_fields = Mock(return_value=True)
        editor.status = Mock()
        editor.refresh_labels = Mock()
        self.draft.agents["Alice"][0]["tab"]["hash"] = "bad"
        with patch("editor.messagebox.showwarning") as warning:
            self.assertTrue(editor.save())
        self.assertIn("Alice / base: tab", warning.call_args.args[1])
        self.assertIn(BLANK_HASH, warning.call_args.args[1])
        self.assertEqual(Draft(self.root).agents["Alice"][0]["tab"]["hash"], BLANK_HASH)

    def tree_editor(self):
        editor = self.editor()
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor.tree = ttk.Treeview(window)
        editor.tree_items = {}
        editor.running = False
        editor.current = None
        editor.search = Mock()
        editor.search.get.return_value = ""
        editor.variant = Mock()
        editor.variant.get.return_value = "sources/M6"
        editor.reported_missing = set()
        editor.update_validation_feedback = Mock()
        editor.update_title = Mock()
        return editor

    def test_editor_dark_theme_uses_dark_widget_colors(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)

        apply_dark_theme(window)
        style = ttk.Style(window)

        self.assertEqual(window.cget("background"), DARK_THEME["background"])
        self.assertEqual(style.lookup("TFrame", "background"), DARK_THEME["background"])
        self.assertEqual(style.lookup("TEntry", "fieldbackground"), DARK_THEME["field"])
        self.assertEqual(style.lookup("Treeview", "background"), DARK_THEME["field"])

    def test_running_does_not_disable_or_lighten_layout_widgets(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor = Editor(window, self.draft)
        panes = next(
            widget for widget in window.winfo_children()
            if isinstance(widget, ttk.Panedwindow)
        )
        toolbar = next(
            widget for widget in window.winfo_children()
            if isinstance(widget, ttk.Frame)
        )

        editor.set_running(True)

        self.assertFalse(panes.instate(["disabled"]))
        self.assertFalse(toolbar.instate(["disabled"]))
        self.assertEqual(ttk.Style(window).lookup("TPanedwindow", "background"), DARK_THEME["background"])
        self.assertTrue(all(button.instate(["disabled"]) for button in editor.flip_buttons))

        editor.set_running(False)

    def tree_tags(self, editor):
        return {
            (editor.tree.item(item, "text").removesuffix(" *"), editor.tree_items[item]):
                editor.tree.item(item, "tags")
            for item in editor.tree_items
        }

    def test_tree_highlights_invalid_masks_and_only_their_ancestors(self):
        self.draft.add_skin("Alice")
        self.draft.add_skin("Alice")
        self.draft.add_agent("Bob")
        self.draft.agents["Alice"][1] = {"select": entry(BLANK_HASH), "tab": entry()}
        self.draft.agents["Alice"][2] = {"round": entry("invalid")}
        editor = self.tree_editor()
        editor.rebuild_tree()
        tagged = {
            identity for identity, tags in self.tree_tags(editor).items()
            if "invalid_hash" in tags
        }
        self.assertEqual(tagged, {
            ("Alice", ("Alice", 0, None)),
            ("Skin", ("Alice", 1, None)),
            ("select", ("Alice", 1, "select")),
            ("Skin2", ("Alice", 2, None)),
            ("round", ("Alice", 2, "round")),
        })
        editor.search.get.return_value = "Bob"
        editor.rebuild_tree()
        self.assertTrue(all(not tags for tags in self.tree_tags(editor).values()))

    def test_tree_displays_agents_alphabetically(self):
        self.draft.agents = {"Zoe": [{}], "alice": [{}], "Bob": [{}]}
        editor = self.tree_editor()
        editor.rebuild_tree()

        roots = editor.tree.get_children()
        self.assertEqual([editor.tree.item(item, "text") for item in roots], ["alice", "Bob", "Zoe"])

    def test_tree_highlights_update_after_repairs_removal_and_save(self):
        self.draft.agents["Alice"][0]["select"]["hash"] = BLANK_HASH
        self.draft.agents["Alice"][0]["tab"]["hash"] = BLANK_HASH
        editor = self.tree_editor()
        editor.rebuild_tree()
        self.assertEqual(sum(bool(tags) for tags in self.tree_tags(editor).values()), 4)
        self.draft.apply_mask("Alice", 0, "select", entry(), "sources/M6")
        editor.refresh_labels()
        self.assertEqual(sum(bool(tags) for tags in self.tree_tags(editor).values()), 3)
        self.draft.save()
        editor.refresh_labels()
        self.assertEqual(sum(bool(tags) for tags in self.tree_tags(editor).values()), 3)
        self.draft.agents["Alice"][0].pop("tab")
        editor.refresh_labels()
        self.assertTrue(all(not tags for tags in self.tree_tags(editor).values()))

    def test_tree_highlights_load_time_hash_replacements(self):
        path = self.root / "agents.json"
        agents = json.loads(path.read_text(encoding="utf-8"))
        agents["Alice"][0]["round"]["hash"] = "invalid"
        path.write_text(json.dumps(agents), encoding="utf-8")
        editor = self.tree_editor()
        editor.draft = Draft(self.root)
        editor.rebuild_tree()
        self.assertEqual(sum(bool(tags) for tags in self.tree_tags(editor).values()), 3)

    def test_agent_skin_mask_round_trip(self):
        self.draft.add_agent("NewAgent")
        index = self.draft.add_skin("NewAgent")
        self.assertEqual(index, 1)
        self.draft.stage_image("sources/M6", "NewAgent", index, self.artwork())
        self.draft.apply_mask("NewAgent", index, "round", entry(), "sources/M6")
        self.draft.agents["Alice"][0].pop("tab")
        self.draft.save()
        loaded = Draft(self.root)
        self.assertEqual(loaded.agents, self.draft.agents)
        self.assertEqual(loaded.agents["NewAgent"][0], {})
        self.assertEqual(loaded.agents["NewAgent"][1]["round"], entry())
        self.assertNotIn("tab", loaded.agents["Alice"][0])
        self.assertTrue((self.root / "sources" / "M6" / "NewAgentSkinM6.png").exists())
        self.assertFalse(loaded.dirty)

    def test_add_agent_keeps_draft_and_saved_json_alphabetical(self):
        self.draft.add_agent("Aaron")

        self.assertEqual(list(self.draft.agents), ["Aaron", "Alice"])
        self.draft.save()
        saved = json.loads((self.root / "agents.json").read_text(encoding="utf-8"))
        self.assertEqual(list(saved), ["Aaron", "Alice"])

    def test_invalid_agents_and_skin_collision(self):
        for name in ("alice", "../Oops", "CON", "Bad Name", "1Wrong", "AliceSkin"):
            with self.subTest(name=name):
                if name == "AliceSkin":
                    self.draft.add_skin("Alice")
                with self.assertRaises(ValueError):
                    self.draft.add_agent(name)

    def test_unknown_cur_agent(self):
        settings = deepcopy(self.draft.settings)
        settings["CUR_AGENT"] = "Missing"
        with self.assertRaisesRegex(ValueError, "CUR_AGENT"):
            self.draft.set_settings(settings)

    def test_validation_rejects_invalid_transform(self):
        for key, value in (
            ("hash", "abcd"), ("hash", "g1234567"), ("offset", [1.1, 0]),
            ("scale", 0), ("scale", True), ("scale", float("nan")),
            ("rotation", float("inf")), ("scale", 10 ** 1000),
            ("offset", [2 ** 40, 0]),
        ):
            with self.subTest(key=key, value=value):
                data = entry()
                data[key] = value
                with self.assertRaises(ValueError):
                    validate_mask(data)
        for scale in (1e-8, 1e9, 1e308):
            data = entry()
            data["scale"] = scale
            with self.assertRaises(ValueError):
                validate_transform_image(data, Image.new("RGBA", (10, 10)))

    def test_hash_filename(self):
        self.assertEqual(hash_from_filename("texture-9ec5D7fe-ps-t0.dds"), "9ec5d7fe")
        for filename in ("photo.png", "1234abcd-2345bcde.dds", "asset1234abcd.dds", "01234abcd.dds"):
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                hash_from_filename(filename)

    def test_shared_transform_and_duplicate_warnings(self):
        self.draft.apply_mask("Alice", 0, "select", entry(), "sources/M6")
        self.draft.apply_mask("Alice", 0, "tab", entry(), "sources/M3")
        self.assertEqual(self.draft.agents["Alice"][0]["select"], self.draft.agents["Alice"][0]["tab"])
        self.assertEqual(len(duplicate_hashes(self.draft.agents)), 1)

    def test_import_dedup_discard_and_transparency(self):
        base = self.root / "sources" / "M6" / "Alice.png"
        self.assertIsNone(self.draft.stage_image("sources/M6", "Alice", 0, base))
        self.assertFalse(self.draft.dirty)
        target = self.draft.stage_image("sources/M6", "Alice", 0, self.artwork((1, 2, 3, 40)))
        self.assertFalse(target.exists())
        self.draft.save()
        with Image.open(target) as image:
            self.assertEqual(image.getpixel((0, 0)), (1, 2, 3, 40))
        self.draft.stage_image("sources/M6", "Alice", 0, self.artwork("blue"))
        self.draft.discard_imports()
        self.assertFalse(self.draft.dirty)

    def test_import_can_flip_vertically_before_saving(self):
        path = self.root / "vertical.png"
        image = Image.new("RGBA", (2, 2))
        image.putpixel((0, 0), (255, 0, 0, 255))
        image.putpixel((0, 1), (0, 0, 255, 255))
        image.save(path)
        target = self.draft.stage_image("sources/M6", "Alice", 0, path, flip_vertical=True)
        staged = self.draft.imports[target]
        self.assertEqual(staged.getpixel((0, 0)), (0, 0, 255, 255))
        self.assertEqual(staged.getpixel((0, 1)), (255, 0, 0, 255))
        self.draft.save()
        with Image.open(target) as saved:
            self.assertEqual(saved.getpixel((0, 0)), (0, 0, 255, 255))
            self.assertEqual(saved.getpixel((0, 1)), (255, 0, 0, 255))

    def asymmetric_artwork(self):
        image = Image.new("RGBA", (2, 2))
        image.putdata([(255, 0, 0, 255), (0, 255, 0, 128),
                       (0, 0, 255, 64), (255, 255, 0, 0)])
        return image

    def test_flip_existing_artwork_stages_saves_and_double_flip_is_noop(self):
        base = self.root / "sources" / "M6" / "Alice.png"
        original = self.asymmetric_artwork()
        original.save(base)
        original_bytes = base.read_bytes()
        for vertical, operation in (
            (True, Image.Transpose.FLIP_TOP_BOTTOM),
            (False, Image.Transpose.FLIP_LEFT_RIGHT),
        ):
            with self.subTest(vertical=vertical):
                draft = Draft(self.root)
                target = draft.flip_image("sources/M6", "Alice", 0, vertical=vertical)
                expected = original.transpose(operation)
                self.assertEqual(draft.imports[target].tobytes(), expected.tobytes())
                self.assertEqual(base.read_bytes(), original_bytes)
                self.assertTrue(draft.dirty)
                self.assertIsNone(draft.flip_image("sources/M6", "Alice", 0, vertical=vertical))
                self.assertFalse(draft.dirty)
                draft.flip_image("sources/M6", "Alice", 0, vertical=vertical)
                draft.save()
                loaded, _ = Draft(self.root).artwork("sources/M6", "Alice", 0)
                self.assertEqual(loaded.tobytes(), expected.tobytes())
                target.unlink()

    def test_flip_staged_import_composes_and_can_be_discarded(self):
        path = self.root / "import.png"
        original = self.asymmetric_artwork()
        original.save(path)
        target = self.draft.stage_image("sources/M6", "Alice", 0, path, flip_vertical=True)
        self.draft.flip_image("sources/M6", "Alice", 0, vertical=False)
        expected = original.transpose(Image.Transpose.FLIP_TOP_BOTTOM).transpose(
            Image.Transpose.FLIP_LEFT_RIGHT,
        )
        self.assertEqual(self.draft.imports[target].tobytes(), expected.tobytes())
        self.draft.flip_image("sources/M6", "Alice", 0, vertical=False)
        self.assertEqual(
            self.draft.imports[target].tobytes(),
            original.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes(),
        )
        self.draft.discard_imports()
        self.assertFalse(target.exists())
        self.assertFalse(self.draft.dirty)

    def test_flip_chibi_skin_fallback_only_changes_selected_skin_and_mask(self):
        self.enable_chibi()
        self.draft.add_skin("Alice")
        self.draft.agents["Alice"][1] = {"select": entry()}
        source = self.root / "sources" / "Chibi"
        source.mkdir()
        original = self.asymmetric_artwork()
        original.save(source / "Alice-select.png")
        original.save(source / "Alice-tab.png")
        self.draft.save()
        target = self.draft.flip_image(
            "sources/Chibi", "Alice", 1, vertical=False, kind="select",
        )
        self.assertEqual(target.name, "AliceSkin-select.png")
        for index, kind in ((0, "select"), (0, "tab"), (1, "tab")):
            image, _ = self.draft.artwork("sources/Chibi", "Alice", index, kind)
            self.assertEqual(image.tobytes(), original.tobytes())
        self.draft.save()
        image, _ = Draft(self.root).artwork("sources/Chibi", "Alice", 1, "select")
        self.assertEqual(image.tobytes(), original.transpose(Image.Transpose.FLIP_LEFT_RIGHT).tobytes())

    def artwork_editor(self):
        editor = self.editor()
        editor.running = False
        editor.current = ("Alice", 0, "select")
        editor.variant = Mock()
        editor.variant.get.return_value = "sources/M6"
        editor.load_artwork = Mock()
        editor.update_title = Mock()
        editor.error = Mock()
        return editor

    def test_editor_import_flips_by_default_without_orientation_prompt(self):
        editor = self.artwork_editor()
        path = self.root / "import.png"
        original = self.asymmetric_artwork()
        original.save(path)
        with patch("editor.filedialog.askopenfilename", return_value=str(path)), \
                patch("editor.messagebox.askyesno") as prompt:
            editor.import_art()
        prompt.assert_not_called()
        image, _ = self.draft.artwork("sources/M6", "Alice", 0)
        self.assertEqual(image.tobytes(), original.transpose(Image.Transpose.FLIP_TOP_BOTTOM).tobytes())
        editor.load_artwork.assert_called_once()
        editor.update_title.assert_called_once()
        editor.error.assert_not_called()

    def test_editor_import_still_confirms_replacement(self):
        editor = self.artwork_editor()
        path = self.artwork()
        self.draft.stage_image("sources/M6", "Alice", 0, path)
        with patch("editor.filedialog.askopenfilename", return_value=str(path)), \
                patch("editor.messagebox.askyesno", return_value=False) as prompt:
            editor.import_art()
        self.assertEqual(prompt.call_args.args[0], "Shared artwork replacement")
        editor.load_artwork.assert_not_called()

    def test_editor_flip_refreshes_and_respects_guards(self):
        editor = self.artwork_editor()
        with patch.object(self.draft, "flip_image") as flip:
            for vertical in (True, False):
                editor.flip_art(vertical=vertical)
                flip.assert_called_with("sources/M6", "Alice", 0, vertical=vertical, kind="select")
            self.assertEqual(editor.load_artwork.call_count, 2)
            self.assertEqual(editor.update_title.call_count, 2)
            flip.reset_mock()
            editor.running = True
            editor.flip_art(vertical=True)
            editor.running = False
            editor.current = None
            editor.flip_art(vertical=False)
            flip.assert_not_called()

    def test_editor_flip_reports_missing_artwork(self):
        editor = self.artwork_editor()
        editor.variant.get.return_value = "sources/Chibi"
        editor.flip_art(vertical=True)
        editor.error.assert_called_once()
        self.assertIn("No source", str(editor.error.call_args.args[0]))
        self.assertEqual(self.draft.imports, {})
        editor.load_artwork.assert_not_called()

    def test_flip_buttons_follow_artwork_availability(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor = Editor(window, self.draft)

        def assert_disabled(expected):
            for button in editor.flip_buttons:
                self.assertEqual(button.instate(["disabled"]), expected)

        assert_disabled(True)
        editor.current = ("Alice", 0, "select")
        editor.reset_fields()
        assert_disabled(False)
        editor.set_running(True)
        assert_disabled(True)
        editor.set_running(False)
        assert_disabled(False)

        missing = self.root / "sources" / "M6" / "Alice.png"
        missing.unlink()
        editor.load_artwork()
        assert_disabled(True)
        editor.set_running(True)
        editor.set_running(False)
        assert_disabled(True)
        with patch("editor.filedialog.askopenfilename", return_value=str(self.artwork())):
            editor.import_art()
        assert_disabled(False)
        with patch("editor.messagebox.askyesno", return_value=True):
            editor.discard_imports()
        assert_disabled(True)

        missing.write_text("invalid image")
        editor.load_artwork()
        assert_disabled(True)
        Image.new("RGBA", (12, 14), "red").save(missing)
        editor.load_artwork()
        assert_disabled(False)

        parent = next(item for item, target in editor.tree_items.items() if target[2] is None)
        editor.tree.selection_set(parent)
        editor.select()
        assert_disabled(True)
        self.assertIsNone(editor.image)

    def test_copy_base_fields_copies_transforms_and_is_disabled_on_base_skin(self):
        self.draft.add_skin("Alice")
        self.draft.agents["Alice"][0]["select"].update({
            "offset": [15, -8],
            "scale": 1.25,
            "rotation": 37,
        })
        self.draft.agents["Alice"][1]["select"] = {
            **entry("abcdef12"),
            "offset": [1, 2],
            "scale": 0.8,
            "rotation": -10,
        }
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor = Editor(window, self.draft)
        editor.current = ("Alice", 0, "select")
        editor.reset_fields()

        self.assertTrue(editor.copy_base_button.instate(["disabled"]))
        button_texts = [
            child.cget("text") for child in editor.copy_base_button.master.winfo_children()
            if isinstance(child, ttk.Button)
        ]
        self.assertLess(button_texts.index("Copy Base Fields"), button_texts.index("Reset Fields"))

        editor.current = ("Alice", 1, "select")
        editor.reset_fields()
        self.assertFalse(editor.copy_base_button.instate(["disabled"]))
        original_hash = editor.hash_value.get()

        editor.copy_base_button.invoke()

        self.assertEqual(
            tuple(editor.variables[key].get() for key in ("x", "y", "scale", "rotation")),
            ("15", "-8", "1.25", "37"),
        )
        self.assertEqual(editor.hash_value.get(), original_hash)

    def test_hash_and_missing_artwork_feedback_updates_after_applying(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor = Editor(window, self.draft)
        editor.current = ("Alice", 0, "select")
        editor.reset_fields()

        source = self.root / "sources" / "M6" / "Alice.png"
        source.unlink()
        editor.hash_value.set("invalid")
        self.assertEqual(editor.hash_entry.cget("style"), "Invalid.TEntry")

        with patch("editor.messagebox.showwarning"):
            self.assertTrue(editor.apply())
        self.assertEqual(editor.hash_value.get(), BLANK_HASH)
        self.assertEqual(editor.import_button.cget("style"), "Invalid.TButton")

        Image.new("RGBA", (12, 14), "red").save(source)
        editor.load_artwork()
        self.assertEqual(editor.import_button.cget("style"), "TButton")
        editor.hash_value.set("abcdef12")
        self.assertEqual(editor.hash_entry.cget("style"), "TEntry")

        style = ttk.Style(window)
        for widget, style_name in (
            (editor.hash_entry, "Invalid.TEntry"),
            (editor.import_button, "Invalid.TButton"),
        ):
            self.assertTrue(
                style.lookup(style_name, "bordercolor") == "#ff0000"
                or style.lookup(style_name, "foreground") == "#ff0000"
            )

    def test_flip_buttons_follow_variant_changes_and_reload(self):
        window = tk.Tk()
        window.withdraw()
        self.addCleanup(window.destroy)
        editor = Editor(window, self.draft)
        editor.current = ("Alice", 0, "select")
        editor.reset_fields()
        (self.root / "sources" / "M3" / "Alice.png").unlink()
        editor.variant.set("sources/M3")
        editor.change_variant()
        self.assertTrue(all(button.instate(["disabled"]) for button in editor.flip_buttons))
        editor.variant.set("sources/M6")
        editor.change_variant()
        self.assertTrue(all(not button.instate(["disabled"]) for button in editor.flip_buttons))
        editor.reload()
        self.assertTrue(all(button.instate(["disabled"]) for button in editor.flip_buttons))

    def test_config_and_import_saved_together(self):
        settings = deepcopy(self.draft.settings)
        settings["SOURCE_DIRS"].reverse()
        settings["MOD_VERSION"] = "4.0"
        settings["SATURATION_MULTIPLIER"] = 0
        self.draft.set_settings(settings)
        self.draft.stage_image("sources/M3", "Alice", 0, self.artwork())
        backups = self.draft.save()
        self.assertTrue(backups)
        self.assertEqual(Draft(self.root).settings, settings)

    def config_dialog(self):
        editor = self.editor()
        editor.running = False
        editor.current = None
        editor.variants = Mock()
        editor.variant = Mock()
        editor.variant.get.return_value = "sources/M6"
        editor.load_artwork = Mock()
        editor.update_title = Mock()
        editor.status = Mock()
        editor.fields_dirty = Mock(return_value=False)
        dialog = ConfigDialog.__new__(ConfigDialog)
        dialog.editor = editor
        dialog.window = Mock()
        dialog.variables = {}
        for key, value in self.draft.settings.items():
            if key != "SOURCE_DIRS":
                dialog.variables[key] = Mock()
                dialog.variables[key].get.return_value = value
        dialog.variables["MOD_VERSION"].get.return_value = "4.0"
        dialog.sources = Mock()
        dialog.sources.get.return_value = tuple(self.draft.settings["SOURCE_DIRS"])
        return dialog

    def test_config_apply_saves_immediately_and_close_does_not_prompt(self):
        dialog = self.config_dialog()
        with patch("editor.messagebox.showerror") as error:
            dialog.apply()
        error.assert_not_called()
        self.assertEqual(Draft(self.root).settings["MOD_VERSION"], "4.0")
        self.assertFalse(self.draft.dirty)
        dialog.window.destroy.assert_called_once()
        with patch("editor.messagebox.askyesnocancel") as prompt:
            dialog.editor.close()
        prompt.assert_not_called()
        dialog.editor.window.destroy.assert_called_once()
        self.assertEqual(self.draft.save(), [])

    def test_config_apply_enabling_chibi_does_not_prompt_on_close(self):
        dialog = self.config_dialog()
        dialog.sources.get.return_value = ("sources/M6", "sources/M3", "sources/Chibi")
        dialog.apply()
        self.assertIn("sources/Chibi", Draft(self.root).settings["SOURCE_DIRS"])
        self.assertFalse(self.draft.dirty)
        with patch("editor.messagebox.askyesnocancel") as prompt:
            dialog.editor.close()
        prompt.assert_not_called()
        dialog.editor.window.destroy.assert_called_once()
        self.draft.save()
        self.assertTrue((self.root / "agents-chibi.json").exists())
        self.assertFalse(Draft(self.root).dirty)

    def test_config_apply_does_not_persist_a_draft_only_agent_selection(self):
        self.draft.add_agent("Bob")
        dialog = self.config_dialog()
        dialog.variables["CUR_AGENT"].get.return_value = "Bob"
        with patch("editor.messagebox.showerror") as error:
            dialog.apply()
        error.assert_called_once()
        self.assertIsNone(Draft(self.root).settings["CUR_AGENT"])
        self.assertIsNone(self.draft.settings["CUR_AGENT"])
        self.assertIn("Bob", self.draft.agents)
        dialog.window.destroy.assert_not_called()

    def test_config_apply_preserves_unsaved_agents_and_imports(self):
        original = (self.root / "agents.json").read_bytes()
        self.draft.add_agent("Bob")
        target = self.draft.stage_image("sources/M6", "Alice", 0, self.artwork())
        dialog = self.config_dialog()
        dialog.apply()
        self.assertEqual(Draft(self.root).settings["MOD_VERSION"], "4.0")
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertFalse(target.exists())
        self.assertIn(target, self.draft.imports)
        self.assertTrue(self.draft.dirty)
        with patch("editor.messagebox.askyesnocancel", return_value=None) as prompt:
            dialog.editor.close()
        prompt.assert_called_once()
        dialog.editor.window.destroy.assert_not_called()
        self.draft.save()
        self.assertIn("Bob", Draft(self.root).agents)
        self.assertTrue(target.exists())

    def test_config_apply_honors_disabled_backups(self):
        dialog = self.config_dialog()
        dialog.variables["BACKUP_FILES"].get.return_value = False
        dialog.apply()
        self.assertEqual(Draft(self.root).settings["MOD_VERSION"], "4.0")
        self.assertEqual(list(self.root.rglob("*.bak")), [])
        self.assertEqual(list(self.root.rglob(".editor-*")), [])

    def test_config_apply_keeps_backups_and_can_save_again(self):
        original = (self.root / "config.json").read_bytes()
        dialog = self.config_dialog()
        dialog.apply()
        backups = list((self.root / "backup").glob("config.json.*.bak"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        dialog.variables["MOD_VERSION"].get.return_value = "5.0"
        dialog.apply()
        self.assertEqual(Draft(self.root).settings["MOD_VERSION"], "5.0")
        self.assertFalse(self.draft.dirty)

    def test_config_apply_failure_restores_settings_and_keeps_dialog_open(self):
        original = (self.root / "config.json").read_bytes()
        settings = deepcopy(self.draft.settings)
        dialog = self.config_dialog()
        with (
            patch("editor_model.os.replace", side_effect=OSError("Injected failure")),
            patch("editor.messagebox.showerror") as error,
        ):
            dialog.apply()
        error.assert_called_once()
        self.assertIn("Save failed", error.call_args.args[1])
        self.assertEqual((self.root / "config.json").read_bytes(), original)
        self.assertEqual(self.draft.settings, settings)
        self.assertFalse(self.draft.dirty)
        dialog.window.destroy.assert_not_called()
        dialog.editor.load_artwork.assert_not_called()

    def test_config_apply_rejects_external_config_changes(self):
        dialog = self.config_dialog()
        path = self.root / "config.json"
        external = path.read_bytes() + b"\n"
        path.write_bytes(external)
        settings = deepcopy(self.draft.settings)
        with patch("editor.messagebox.showerror") as error:
            dialog.apply()
        error.assert_called_once()
        self.assertIn("changed outside", error.call_args.args[1])
        self.assertEqual(path.read_bytes(), external)
        self.assertEqual(self.draft.settings, settings)
        dialog.window.destroy.assert_not_called()

    def test_config_cannot_orphan_import(self):
        self.draft.stage_image("sources/M6", "Alice", 0, self.artwork())
        settings = deepcopy(self.draft.settings)
        settings["SOURCE_DIRS"] = ["sources/M3"]
        with self.assertRaisesRegex(ValueError, "staged imports"):
            self.draft.set_settings(settings)
        self.assertEqual(self.draft.settings["SOURCE_DIRS"], ["sources/M6", "sources/M3"])

    def test_stale_json_and_artwork(self):
        for kind in ("json", "art"):
            with self.subTest(kind=kind):
                draft = Draft(self.root)
                if kind == "json":
                    path = self.root / "agents.json"
                    original = path.read_bytes()
                    path.write_bytes(original + b"\n")
                else:
                    path = draft.target("sources/M6", "Alice", 0)
                    draft.stage_image("sources/M6", "Alice", 0, self.artwork())
                    Image.new("RGBA", (8, 9)).save(path)
                with self.assertRaisesRegex(ValueError, "outside"):
                    draft.save()

    def test_failure_during_save_restores_previous_files(self):
        self.draft.add_agent("New")
        self.draft.stage_image("sources/M6", "New", 0, self.artwork())
        original = (self.root / "agents.json").read_bytes()
        replace = os.replace
        calls = 0

        def fail_second(source, target):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise OSError("Injected replacement failure")
            return replace(source, target)

        with patch("editor_model.os.replace", side_effect=fail_second):
            with self.assertRaisesRegex(ValueError, "Previous files restored"):
                self.draft.save()
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertFalse(self.draft.target("sources/M6", "New", 0).exists())
        self.assertTrue(self.draft.dirty)
        self.assertEqual(list(self.root.rglob(".editor-*")), [])
        self.draft.save()
        self.assertFalse(self.draft.dirty)

    def test_preflight_backup_failure_changes_nothing(self):
        self.draft.add_agent("New")
        original = (self.root / "agents.json").read_bytes()
        with patch("editor_model.shutil.copy2", side_effect=OSError("No permission")):
            with self.assertRaisesRegex(ValueError, "Save failed"):
                self.draft.save()
        self.assertEqual((self.root / "agents.json").read_bytes(), original)
        self.assertEqual(list(self.root.rglob(".editor-*")), [])

    def test_rollback_failure_reports_recovery_location(self):
        self.draft.add_agent("New")
        settings = deepcopy(self.draft.settings)
        settings["MOD_VERSION"] = "5"
        self.draft.set_settings(settings)
        replace = os.replace
        calls = 0

        def fail_after_first(source, target):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError("Device failure")
            return replace(source, target)

        with patch("editor_model.os.replace", side_effect=fail_after_first):
            with self.assertRaisesRegex(ValueError, r"Recovery needed:[\s\S]*backup:.*\.bak"):
                self.draft.save()

    def test_invalid_image_is_not_staged(self):
        path = self.root / "bad.png"
        path.write_text("not an image")
        with self.assertRaises(OSError):
            self.draft.stage_image("sources/M6", "Alice", 0, path)
        self.assertFalse(self.draft.imports)

    def test_source_directory_link_preserves_configured_variant_name(self):
        alias = self.root / "sources" / "Alias"
        try:
            alias.symlink_to(self.root / "sources" / "M6", target_is_directory=True)
        except OSError:
            self.skipTest("Creating symlinks is unavailable to this account")
        settings = deepcopy(self.draft.settings)
        settings["SOURCE_DIRS"] = ["sources/Alias"]
        self.draft.set_settings(settings)
        target = self.draft.stage_image("sources/Alias", "Alice", 0, self.artwork())
        self.assertEqual(target.name, "AliceAlias.png")
        self.draft.save()
        image, resolved = self.draft.artwork("sources/Alias", "Alice", 0)
        self.assertEqual(resolved, target)
        self.assertEqual(image.size, (12, 14))
