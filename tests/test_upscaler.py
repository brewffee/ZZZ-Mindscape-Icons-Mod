import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import warnings
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from PIL import Image, ImageChops, ImageDraw

from masks import preview_mask
from support import project
from textures import MASK_SPECS, apply_mask, position_image, render_mask
from upscaler import MODEL_PATH, UpscaleError, _download_model, _upscale_rgb, load_model, resize_artwork
from upscaler import _load_rgb_model


def artwork():
    image = Image.new("RGBA", (180, 180))
    draw = ImageDraw.Draw(image)
    draw.ellipse((15, 15, 165, 165), fill=(240, 180, 110, 220), outline="black", width=3)
    draw.polygon(((30, 70), (90, 10), (155, 70)), fill=(30, 70, 170, 255))
    draw.line((40, 110, 80, 100, 140, 110), fill="black", width=2)
    return image


class UpscalerTests(unittest.TestCase):
    def test_model_loading_suppresses_only_upstream_meshgrid_warning(self):
        meshgrid_warning = (
            "torch.meshgrid: in an upcoming release, it will be required "
            "to pass the indexing argument."
        )

        class Descriptor:
            scale = 4
            input_channels = 3
            output_channels = 3

            def cuda(self):
                return self

            def eval(self):
                return self

        def construct(weights):
            warnings.warn_explicit(
                meshgrid_warning, UserWarning, "functional.py", 554, module="torch.functional",
            )
            warnings.warn("Other model warning", UserWarning)
            return Descriptor()

        torch = Mock()
        torch.cuda.is_available.return_value = True
        torch.load.return_value = {"params": {}}
        spandrel = Mock()
        spandrel.ImageModelDescriptor = Descriptor
        spandrel.ModelLoader.return_value.load_from_state_dict.side_effect = construct
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "model.pth"
            path.touch()
            with patch.dict(sys.modules, {"torch": torch, "spandrel": spandrel}), \
                    warnings.catch_warnings(record=True) as caught:
                warnings.simplefilter("always")
                model = _load_rgb_model(path, "unused", 4)
                self.assertIsInstance(model, Descriptor)
                self.assertEqual([str(item.message) for item in caught], ["Other model warning"])
                warnings.warn_explicit(
                    meshgrid_warning, UserWarning, "functional.py", 554,
                    module="torch.functional",
                )
                self.assertEqual(len(caught), 2)

    def test_pillow_is_pixel_identical_and_ml_is_lazy(self):
        image = artwork()
        with patch("upscaler.load_model", side_effect=AssertionError("ML must not load")):
            for backend, size in (("pillow", (512, 512)), ("realesrgan", (90, 90)),
                                  ("realesrgan", image.size)):
                with self.subTest(backend=backend, size=size):
                    actual = resize_artwork(image, size, backend)
                    expected = image.resize(size, Image.Resampling.LANCZOS)
                    self.assertEqual(actual.tobytes(), expected.tobytes())

    def test_ml_enlargement_exact_dimensions_alpha_and_cache_inputs(self):
        image = artwork()

        def fake_model(size, pixels):
            self.assertEqual(size, (180, 180))
            self.assertEqual(pixels, image.convert("RGB").tobytes())
            return Image.new("RGB", (720, 720), (30, 80, 200))

        with patch("upscaler._upscale_rgb", side_effect=fake_model) as upscale:
            result = resize_artwork(image, (512, 512), "realesrgan")
        upscale.assert_called_once()
        self.assertEqual(result.size, (512, 512))
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.getpixel((256, 256))[:3], (30, 80, 200))
        expected_alpha = image.getchannel("A").resize((512, 512), Image.Resampling.LANCZOS)
        self.assertEqual(result.getchannel("A").tobytes(), expected_alpha.tobytes())

    def test_multiple_passes_for_more_than_four_times(self):
        with patch("upscaler._upscale_rgb", side_effect=lambda size, pixels: Image.new(
            "RGB", (size[0] * 4, size[1] * 4),
        )) as upscale:
            result = resize_artwork(Image.new("RGBA", (10, 10)), (50, 50), "realesrgan")
        self.assertEqual(result.size, (50, 50))
        self.assertEqual(upscale.call_count, 2)

    def test_invalid_backend_and_dimensions(self):
        for backend, size in (("invalid", (2, 2)), ("pillow", (0, 2))):
            with self.subTest(backend=backend, size=size), self.assertRaises(ValueError):
                resize_artwork(artwork(), size, backend)

    def test_explicit_ml_failure_never_falls_back(self):
        with patch("upscaler._upscale_rgb", side_effect=UpscaleError("GPU unavailable")):
            with self.assertRaisesRegex(UpscaleError, "GPU unavailable"):
                resize_artwork(artwork(), (512, 512), "realesrgan")

    def test_failed_download_is_not_cached(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "models" / "model.pth"
            with patch("upscaler.urlopen", side_effect=OSError("offline")):
                with self.assertRaisesRegex(UpscaleError, "offline"):
                    _download_model(path)
            self.assertFalse(path.exists())
            self.assertEqual(list(path.parent.iterdir()), [])

    def test_download_is_saved_atomically_without_temporary_files(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "models" / "model.pth"
            with patch("upscaler.urlopen", return_value=io.BytesIO(b"weights")):
                _download_model(path)
            self.assertEqual(path.read_bytes(), b"weights")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_missing_optional_dependencies_have_actionable_error(self):
        load_model.cache_clear()
        with patch.dict(sys.modules, {"torch": None}):
            with self.assertRaisesRegex(UpscaleError, "requirements-upscaler.txt"):
                load_model()

    def test_unavailable_cuda_has_actionable_error(self):
        load_model.cache_clear()
        torch = Mock()
        torch.cuda.is_available.return_value = False
        with patch.dict(sys.modules, {"torch": torch, "spandrel": Mock()}):
            with self.assertRaisesRegex(UpscaleError, "NVIDIA GPU"):
                load_model()

    def test_render_and_export_use_configured_backend(self):
        image = artwork()
        scale = 512 / 180
        with patch("upscaler._upscale_rgb", return_value=Image.new(
            "RGB", (720, 720), (30, 80, 200),
        )) as upscale:
            for kind, spec in MASK_SPECS.items():
                mask = preview_mask(kind)
                ml = render_mask(
                    spec.size, mask, image, (3, -2), scale, 15, spec.final_size,
                    1, 1, "realesrgan",
                )
                pil = render_mask(
                    spec.size, mask, image, (3, -2), scale, 15, spec.final_size, 1, 1,
                )
                self.assertEqual(ml.size, spec.final_size or spec.size)
                self.assertEqual(ml.getchannel("A").tobytes(), pil.getchannel("A").tobytes())
                self.assertNotEqual(ml.convert("RGB").tobytes(), pil.convert("RGB").tobytes())
            with tempfile.TemporaryDirectory() as td:
                root = Path(td)
                image.save(root / "art.png")
                preview_mask("select").save(root / "mask.png")
                with patch("config.IMAGE_UPSCALER", "realesrgan"):
                    apply_mask((512, 500), root / "mask.png", root / "art.png", root / "out.png",
                               (3, -2), scale, 15)
                with Image.open(root / "out.png") as output:
                    expected = render_mask(
                        (512, 500), preview_mask("select"), image, (3, -2), scale, 15,
                        upscaler="realesrgan",
                    )
                    self.assertEqual(output.tobytes(), expected.tobytes())
            self.assertGreater(upscale.call_count, 3)

    def test_position_and_rotation_keep_existing_geometry(self):
        image = artwork()
        with patch("textures.resize_artwork", wraps=resize_artwork) as resize:
            position_image((512, 500), image, (12, -8), 0.5, 45, "realesrgan")
        resize.assert_called_once_with(image, (90, 90), "realesrgan", denoise=False)


@unittest.skipUnless(os.environ.get("TEST_REAL_UPSCALER") == "1", "Opt-in NVIDIA/model integration")
class RealUpscalerTests(unittest.TestCase):
    def test_180px_artwork_with_real_model_and_selector(self):
        image = artwork()
        _upscale_rgb.cache_clear()
        result = resize_artwork(image, (512, 512), "realesrgan")
        self.assertEqual(result.size, (512, 512))
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.getchannel("A").tobytes(), image.getchannel("A").resize(
            (512, 512), Image.Resampling.LANCZOS,
        ).tobytes())
        pil = resize_artwork(image, (512, 512))
        self.assertIsNotNone(ImageChops.difference(
            result.convert("RGB"), pil.convert("RGB"),
        ).getbbox())
        before = _upscale_rgb.cache_info()
        rendered = render_mask(
            (512, 500), preview_mask("select"), image, (0, 0), 512 / 180,
            upscaler="realesrgan",
        )
        self.assertEqual(rendered.size, (512, 500))
        self.assertGreater(_upscale_rgb.cache_info().hits, before.hits)

    def test_real_model_pipeline_creates_images_ini_and_archive(self):
        load_model()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            settings = project(root, scripts=True)
            settings["IMAGE_UPSCALER"] = "realesrgan"
            (root / "config.json").write_text(json.dumps(settings), encoding="utf-8")
            agents = json.loads((root / "agents.json").read_text())
            for entry in agents["Alice"][0].values():
                entry["scale"] = 512 / 180
            (root / "agents.json").write_text(json.dumps(agents), encoding="utf-8")
            for variant in settings["SOURCE_DIRS"]:
                artwork().save(root / variant / "Alice.png")
            (root / "models").mkdir()
            shutil.copyfile(MODEL_PATH, root / "models" / MODEL_PATH.name)
            result = subprocess.run(
                [sys.executable, str(root / "main.py")], cwd=root,
                capture_output=True, text=True, timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            with zipfile.ZipFile(root / "export" / "mindscape_icons_v3.3.zip") as archive:
                for kind, spec in MASK_SPECS.items():
                    filename = f"Mindscape Icons/{kind}/AliceM6.png"
                    with Image.open(io.BytesIO(archive.read(filename))) as output:
                        self.assertEqual(output.size, spec.final_size or spec.size)
                        self.assertGreater(output.getchannel("A").getextrema()[1], 0)
                    self.assertIn(
                        f"Mindscape Icons/MindscapeIcons_{kind.capitalize()}.ini",
                        archive.namelist(),
                    )
