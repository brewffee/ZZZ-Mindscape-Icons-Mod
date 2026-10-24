import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageChops

from masks import preview_mask
from textures import MASK_SPECS, apply_mask, render_mask, resolve_source, source_path, source_stem


class TextureTests(unittest.TestCase):
    def setUp(self):
        self.image = Image.new("RGBA", (23, 19))
        self.image.putdata([
            ((i * 17) % 256, (i * 31) % 256, (i * 47) % 256, (i * 13) % 256)
            for i in range(23 * 19)
        ])
        self.mask = Image.new("RGBA", (11, 9))
        self.mask.putdata([(0, 0, 0, (i * 29) % 256) for i in range(99)])

    def test_original_pixel_checksums(self):
        cases = (
            ((16, 14), None, (2, -3), .73, 30, 1, 1.2,
             "c7a0447d328c71bde74e589a5b56bfd99b86e621dea6e88ec3c8ece3d3f71a01"),
            ((16, 14), (7, 4), (-3, 2), 1.3, -41, 1.2, .6,
             "aa11dafc7c4339f913e0f45c0a66465764c6853d863c763e6e67fe2de388bfe1"),
            ((14, 14), (8, 8), (0, 0), 1, 0, 0, 0,
             "1ddb03773a7b07295044231b90dc0707245088641e13a71c9d023048c24d2949"),
        )
        for size, final, offset, scale, rotation, contrast, saturation, expected in cases:
            with self.subTest(rotation=rotation):
                result = render_mask(size, self.mask, self.image, offset, scale, rotation,
                                     final, contrast, saturation)
                self.assertEqual(hashlib.sha256(result.tobytes()).hexdigest(), expected)

    def test_alpha_multiplication_matches_original_for_all_values(self):
        left = Image.new("L", (256, 256))
        right = Image.new("L", (256, 256))
        left.putdata([a for a in range(256) for _ in range(256)])
        right.putdata([b for _ in range(256) for b in range(256)])
        actual = ImageChops.multiply(left, right).tobytes()
        expected = bytes(int(a * b / 255) for a in range(256) for b in range(256))
        self.assertEqual(actual, expected)

    def test_file_wrapper_preserves_metadata(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.image.save(root / "art.png")
            self.mask.save(root / "mask.png")
            with patch("config.CONTRAST_MULTIPLIER", 1.2), patch("config.SATURATION_MULTIPLIER", .6):
                apply_mask((16, 14), root / "mask.png", root / "art.png", root / "out.png",
                           (-3, 2), 1.3, -41, (7, 4))
            with Image.open(root / "out.png") as result:
                self.assertEqual(result.size, (7, 4))
                self.assertEqual(result.info["gamma"], .45455)
                self.assertEqual(result.info["srgb"], 0)
                self.assertAlmostEqual(result.info["dpi"][0], 72, delta=.02)
                self.assertEqual(hashlib.sha256(result.tobytes()).hexdigest(),
                                 "aa11dafc7c4339f913e0f45c0a66465764c6853d863c763e6e67fe2de388bfe1")

    def test_all_real_masks(self):
        for kind, spec in MASK_SPECS.items():
            with self.subTest(kind=kind):
                mask = preview_mask(kind)
                self.assertEqual(mask.size, spec.size)
                image = Image.new("RGBA", spec.size, (100, 60, 200, 130))
                result = render_mask(spec.size, mask, image, (0, 0), 1, 210, spec.final_size)
                self.assertEqual(result.size, spec.final_size or spec.size)
                self.assertGreater(result.getchannel("A").getextrema()[1], 0)

    def test_source_naming_and_lookup(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            for variant in ("M6", "M3", "sources"):
                directory = root / variant
                directory.mkdir()
                for index in (0, 1, 2):
                    suffix = "" if variant == "sources" else variant
                    skin = ("", "Skin", "Skin2")[index]
                    self.assertEqual(source_stem(directory, "Alice", index), "Alice" + skin + suffix)
                    self.assertIsNone(resolve_source(directory, "Alice", index))
                Image.new("RGBA", (2, 2)).save(directory / "Alice.png")
                self.assertEqual(resolve_source(directory, "Alice", 2), directory / "Alice.png")
                canonical = source_path(directory, "Alice", 2)
                Image.new("RGBA", (3, 3)).save(canonical)
                self.assertEqual(resolve_source(directory, "Alice", 2), canonical)

    def test_chibi_mask_and_skin_sources(self):
        with tempfile.TemporaryDirectory() as td:
            directory = Path(td) / "Chibi"
            directory.mkdir()
            Image.new("RGBA", (2, 2)).save(directory / "Alice.png")
            with self.assertRaisesRegex(ValueError, "mask type"):
                source_path(directory, "Alice", 0)
            for kind in MASK_SPECS:
                self.assertIsNone(resolve_source(directory, "Alice", 0, kind))
                base = directory / f"Alice-{kind}.png"
                Image.new("RGBA", (2, 2)).save(base)
                self.assertEqual(resolve_source(directory, "Alice", 2, kind), base)
                canonical = source_path(directory, "Alice", 2, kind)
                self.assertEqual(canonical.name, f"AliceSkin2-{kind}.png")
                Image.new("RGBA", (3, 3)).save(canonical)
                self.assertEqual(resolve_source(directory, "Alice", 2, kind), canonical)
