import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw, ImageStat

from masks import preview_mask
from textures import apply_mask, position_image, render_mask
from upscaler import (
    UpscaleError, _denoise_rgb, _resize_denoised, resize_artwork,
)


def jpeg_artwork():
    clean = Image.new("RGB", (128, 128), (230, 180, 130))
    draw = ImageDraw.Draw(clean)
    draw.rectangle((24, 24, 95, 95), fill=(30, 80, 170), outline="black", width=3)
    draw.line((28, 60, 90, 45), fill="black", width=2)
    data = io.BytesIO()
    clean.save(data, format="JPEG", quality=40)
    data.seek(0)
    with Image.open(data) as image:
        rgba = image.convert("RGBA")
    alpha = Image.new("L", rgba.size)
    alpha.putdata([i % 256 for i in range(128 * 128)])
    rgba.putalpha(alpha)
    return rgba


class DenoisingTests(unittest.TestCase):
    def setUp(self):
        _denoise_rgb.cache_clear()
        _resize_denoised.cache_clear()
        self.addCleanup(_denoise_rgb.cache_clear)
        self.addCleanup(_resize_denoised.cache_clear)

    def test_bilateral_reduces_flat_region_noise_without_blurring_outline(self):
        image = jpeg_artwork()
        result = resize_artwork(image, image.size, denoise=True)
        region = (30, 70, 89, 89)
        before = sum(ImageStat.Stat(image.convert("RGB").crop(region)).var)
        after = sum(ImageStat.Stat(result.convert("RGB").crop(region)).var)
        self.assertLess(after, before * 0.6)
        # A dark outline next to a light background must remain a hard edge.
        outline = result.getpixel((24, 80))
        background = result.getpixel((23, 80))
        assert isinstance(outline, tuple) and isinstance(background, tuple)
        self.assertLess(max(outline[:3]), 60)
        self.assertGreater(min(background[:3]), 90)
        self.assertEqual(result.getchannel("A").tobytes(), image.getchannel("A").tobytes())

    def test_denoising_precedes_upscaling_and_runs_only_once_at_source_resolution(self):
        image = jpeg_artwork()
        events = []

        def denoise(size, pixels, model, label):
            events.append("denoise")
            self.assertEqual(size, image.size)
            self.assertEqual(pixels, image.convert("RGB").tobytes())
            return Image.new("RGB", size, (20, 40, 60))

        def upscale(size, pixels):
            events.append("upscale")
            self.assertEqual(pixels, Image.new("RGB", size, (20, 40, 60)).tobytes())
            return Image.new("RGB", (size[0] * 4, size[1] * 4), (50, 100, 150))

        with patch("upscaler.load_dejpg_model"), patch(
            "upscaler._infer_rgb", side_effect=denoise,
        ), patch("upscaler._upscale_rgb", side_effect=upscale):
            result = resize_artwork(image, (512, 512), "realesrgan", denoise=True)
            self.assertEqual(events, ["denoise", "upscale"])
            # Return a copy so callers cannot corrupt the cached result.
            result.putpixel((0, 0), (255, 0, 0, 255))
            again = resize_artwork(image, (512, 512), "realesrgan", denoise=True)
            pixel = again.getpixel((0, 0))
            assert isinstance(pixel, tuple)
            self.assertEqual(pixel[:3], (50, 100, 150))
            self.assertEqual(events, ["denoise", "upscale"])
            # A size change reuses native-resolution cleanup.
            resize_artwork(image, (500, 500), "realesrgan", denoise=True)
            self.assertEqual(events, ["denoise", "upscale", "upscale"])
        expected = image.getchannel("A").resize((512, 512), Image.Resampling.LANCZOS)
        self.assertEqual(again.getchannel("A").tobytes(), expected.tobytes())

    def test_cache_tracks_pixels_backend_and_size_not_placement(self):
        image = jpeg_artwork()
        for offset, rotation in (((0, 0), 0), ((10, -20), 15)):
            position_image((512, 500), image, offset, 4, rotation, denoise=True)
        self.assertEqual(_resize_denoised.cache_info().misses, 1)
        self.assertEqual(_resize_denoised.cache_info().hits, 1)
        resize_artwork(image, (510, 510), denoise=True)
        self.assertEqual(_denoise_rgb.cache_info().misses, 1)
        image.putpixel((0, 0), (255, 255, 255, 255))
        resize_artwork(image, (512, 512), denoise=True)
        self.assertEqual(_denoise_rgb.cache_info().misses, 2)
        with patch("upscaler.load_dejpg_model"), patch(
            "upscaler._infer_rgb", return_value=image.convert("RGB"),
        ):
            resize_artwork(image, image.size, "realesrgan", denoise=True)
        self.assertEqual(_denoise_rgb.cache_info().misses, 3)

    def test_cleanup_applies_at_unit_scale_and_when_shrinking(self):
        image = jpeg_artwork()
        for scale in (1, 0.5):
            with self.subTest(scale=scale):
                result = position_image(image.size, image, (0, 0), scale, 0, denoise=True)
                cleaned = resize_artwork(
                    image, (int(image.width * scale), int(image.height * scale)), denoise=True,
                )
                expected = position_image(image.size, cleaned, (0, 0), 1, 0)
                self.assertEqual(result.tobytes(), expected.tobytes())

    def test_non_chibi_does_not_load_cleanup_dependencies(self):
        image = jpeg_artwork()
        with patch("upscaler._denoise_rgb", side_effect=AssertionError("Unexpected cleanup")):
            result = resize_artwork(image, (512, 512))
        self.assertEqual(result.tobytes(), image.resize(
            (512, 512), Image.Resampling.LANCZOS,
        ).tobytes())

    def test_cleanup_errors_are_actionable_and_not_cached(self):
        image = jpeg_artwork()
        with patch.dict(sys.modules, {"cv2": None}):
            with self.assertRaisesRegex(UpscaleError, "requirements.txt"):
                resize_artwork(image, image.size, denoise=True)
        self.assertEqual(_denoise_rgb.cache_info().currsize, 0)
        with patch("upscaler.load_dejpg_model", side_effect=UpscaleError("DeJPG unavailable")):
            with self.assertRaisesRegex(UpscaleError, "DeJPG unavailable"):
                resize_artwork(image, (512, 512), "realesrgan", denoise=True)
        self.assertEqual(_resize_denoised.cache_info().currsize, 0)

    def test_multiple_neural_enlargements_do_not_repeat_cleanup(self):
        image = jpeg_artwork()
        with patch("upscaler.load_dejpg_model"), patch(
            "upscaler._infer_rgb", return_value=image.convert("RGB"),
        ) as cleanup, patch(
            "upscaler._upscale_rgb",
            side_effect=lambda size, pixels: Image.new("RGB", (size[0] * 4, size[1] * 4)),
        ) as upscale:
            result = resize_artwork(image, (640, 640), "realesrgan", denoise=True)
        self.assertEqual(result.size, (640, 640))
        cleanup.assert_called_once()
        self.assertEqual(upscale.call_count, 2)

    def test_chibi_export_matches_shared_preview_renderer_for_all_shapes(self):
        image = jpeg_artwork()
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            chibi = root / "cHiBi"
            chibi.mkdir()
            source = chibi / "Alice-select.png"
            image.save(source)
            for kind in ("select", "tab", "round"):
                mask = preview_mask(kind)
                mask_path = root / f"{kind}.png"
                mask.save(mask_path)
                output = root / f"{kind}-out.png"
                with patch("config.IMAGE_UPSCALER", "pillow"), patch(
                    "config.CONTRAST_MULTIPLIER", 1,
                ), patch("config.SATURATION_MULTIPLIER", 1):
                    apply_mask(mask.size, mask_path, source, output, (2, -3), 4, 15)
                expected = render_mask(
                    mask.size, mask, image, (2, -3), 4, 15,
                    contrast=1, saturation=1, denoise=True,
                )
                with Image.open(output) as actual:
                    self.assertEqual(actual.tobytes(), expected.tobytes())


@unittest.skipUnless(os.environ.get("TEST_REAL_UPSCALER") == "1", "Opt-in NVIDIA/model integration")
class RealDenoisingTests(unittest.TestCase):
    def test_real_dejpg_then_upscale_preserves_alpha_and_reuses_cache(self):
        image = jpeg_artwork()
        _denoise_rgb.cache_clear()
        _resize_denoised.cache_clear()
        self.addCleanup(_denoise_rgb.cache_clear)
        self.addCleanup(_resize_denoised.cache_clear)
        result = resize_artwork(image, (512, 512), "realesrgan", denoise=True)
        self.assertEqual(result.size, (512, 512))
        self.assertEqual(result.mode, "RGBA")
        self.assertEqual(result.getchannel("A").tobytes(), image.getchannel("A").resize(
            (512, 512), Image.Resampling.LANCZOS,
        ).tobytes())
        self.assertNotEqual(_denoise_rgb(
            image.size, image.convert("RGB").tobytes(), "realesrgan",
        ).tobytes(), image.convert("RGB").tobytes())
        again = resize_artwork(image, (512, 512), "realesrgan", denoise=True)
        self.assertEqual(result.tobytes(), again.tobytes())
        self.assertEqual(_resize_denoised.cache_info().hits, 1)
