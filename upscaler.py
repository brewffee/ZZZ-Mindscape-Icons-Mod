"""Cached, alpha-preserving artwork cleanup and optional neural upscaling."""

from __future__ import annotations

import shutil
import tempfile
import warnings
from functools import lru_cache
from pathlib import Path
from pickle import UnpicklingError
from typing import TYPE_CHECKING, Literal
from urllib.request import urlopen

from PIL import Image

if TYPE_CHECKING:
    from spandrel import ImageModelDescriptor

Upscaler = Literal["pillow", "realesrgan"]
MODEL_NAME = "RealESRGAN_x4plus_anime_6B.pth"
MODEL_URL = (
    "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.2.4/" + MODEL_NAME
)
MODEL_PATH = Path(__file__).resolve().parent / "models" / MODEL_NAME
DEJPG_NAME = "1xDeJPG_OmniSR.safetensors"
DEJPG_URL = (
    "https://huggingface.co/Phips/1xDeJPG_OmniSR/resolve/"
    "5884f99cc5ff5b146c9a9eeae8699c79bbf94e35/" + DEJPG_NAME
)
DEJPG_PATH = MODEL_PATH.parent / DEJPG_NAME
TILE_SIZE = 400
TILE_PAD = 16


class UpscaleError(RuntimeError):
    """Artwork cleanup or the selected upscaling backend could not run."""


def _download_model(path: Path, url: str = MODEL_URL) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {path.name} (first use only)...", flush=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, suffix=".tmp", delete=False) as output:
            temporary = Path(output.name)
            with urlopen(url, timeout=60) as response:
                shutil.copyfileobj(response, output)
        temporary.replace(path)
    except OSError as exc:
        raise UpscaleError(f"Unable to download {path.name}: {exc}. Retry with internet access.") from exc
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


@lru_cache(maxsize=1)
def load_model() -> ImageModelDescriptor:
    return _load_rgb_model(MODEL_PATH, MODEL_URL, 4)


@lru_cache(maxsize=1)
def load_dejpg_model() -> ImageModelDescriptor:
    return _load_rgb_model(DEJPG_PATH, DEJPG_URL, 1)


def _load_rgb_model(path: Path, url: str, scale: int) -> ImageModelDescriptor:
    try:
        import torch
        from safetensors import SafetensorError
        from spandrel import ImageModelDescriptor, ModelLoader
    except ImportError as exc:
        raise UpscaleError(
            "Real-ESRGAN needs optional dependencies. Run "
            "'python -m pip install -r requirements-upscaler.txt', then restart."
        ) from exc
    if not torch.cuda.is_available():
        raise UpscaleError(
            "Real-ESRGAN requires an NVIDIA GPU, a current driver and CUDA-enabled PyTorch. "
            "Install requirements-upscaler.txt or select the pillow upscaler."
        )
    if not path.is_file():
        _download_model(path, url)
    try:
        if path.suffix == ".safetensors":
            weights = ModelLoader().load_state_dict_from_file(path)
        else:
            # Load only tensor weights, never executable objects from the checkpoint.
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
            weights = checkpoint["params_ema"] if "params_ema" in checkpoint else checkpoint["params"]
        with warnings.catch_warnings():
            # Spandrel's OmniSR still relies on meshgrid's current "ij" default.
            warnings.filterwarnings(
                "ignore",
                message=r"torch\.meshgrid: in an upcoming release, it will be required "
                        r"to pass the indexing argument\.",
                category=UserWarning,
                module=r"torch\.functional",
            )
            model = ModelLoader().load_from_state_dict(weights)
        if not isinstance(model, ImageModelDescriptor) or (
            model.scale != scale or model.input_channels != 3 or model.output_channels != 3
        ):
            raise UpscaleError(f"{path} must contain an RGB {scale}x model.")
        return model.cuda().eval()
    except (OSError, ValueError, KeyError, RuntimeError, UnpicklingError, EOFError,
            SafetensorError) as exc:
        raise UpscaleError(f"Unable to load model {path}: {exc}") from exc


@lru_cache(maxsize=2)
def _upscale_rgb(size: tuple[int, int], pixels: bytes) -> Image.Image:
    return _infer_rgb(size, pixels, load_model(), "Real-ESRGAN")


def _infer_rgb(
    size: tuple[int, int], pixels: bytes, model: ImageModelDescriptor, label: str,
) -> Image.Image:
    import numpy as np
    import torch

    image = Image.frombytes("RGB", size, pixels)
    scale = model.scale
    result = Image.new("RGB", (image.width * scale, image.height * scale))
    try:
        with torch.inference_mode():
            for top in range(0, image.height, TILE_SIZE):
                for left in range(0, image.width, TILE_SIZE):
                    right = min(left + TILE_SIZE, image.width)
                    bottom = min(top + TILE_SIZE, image.height)
                    x0, y0 = max(left - TILE_PAD, 0), max(top - TILE_PAD, 0)
                    x1 = min(right + TILE_PAD, image.width)
                    y1 = min(bottom + TILE_PAD, image.height)
                    tile = np.array(image.crop((x0, y0, x1, y1)), dtype=np.float32) / 255.0
                    tensor = torch.from_numpy(tile).permute(2, 0, 1).unsqueeze(0).cuda()
                    output = model(tensor)[0, :, (top - y0) * scale:(bottom - y0) * scale,
                                           (left - x0) * scale:(right - x0) * scale]
                    array = output.clamp(0, 1).mul(255).round().byte().permute(1, 2, 0).cpu().numpy()
                    result.paste(Image.fromarray(array), (left * scale, top * scale))
    except RuntimeError as exc:
        raise UpscaleError(
            f"{label} GPU inference failed: {exc}. "
            "Free GPU memory/check your NVIDIA driver, or select pillow."
        ) from exc
    return result


@lru_cache(maxsize=16)
def _denoise_rgb(size: tuple[int, int], pixels: bytes, backend: Upscaler) -> Image.Image:
    if backend == "realesrgan":
        return _infer_rgb(size, pixels, load_dejpg_model(), "1x DeJPG")
    try:
        import cv2
        import numpy as np
    except ImportError as exc:
        raise UpscaleError(
            "Chibi cleanup with Pillow needs OpenCV. Run "
            "'python -m pip install -r requirements.txt', then restart."
        ) from exc
    rgb = np.frombuffer(pixels, dtype=np.uint8).reshape(size[1], size[0], 3)
    try:
        filtered = cv2.bilateralFilter(rgb, d=9, sigmaColor=75, sigmaSpace=75)
        #filtered = cv2.fastNlMeansDenoisingColored(rgb, None, h=5, hColor=8, templateWindowSize=7, searchWindowSize=21)
    except cv2.error as exc:
        raise UpscaleError(f"Chibi bilateral cleanup failed: {exc}") from exc
    return Image.fromarray(filtered)


@lru_cache(maxsize=4)
def _resize_denoised(
    source_size: tuple[int, int], pixels: bytes, size: tuple[int, int], backend: Upscaler,
) -> Image.Image:
    rgba = Image.frombytes("RGBA", source_size, pixels)
    cleaned = _denoise_rgb(source_size, rgba.convert("RGB").tobytes(), backend).convert("RGBA")
    cleaned.putalpha(rgba.getchannel("A"))
    return resize_artwork(cleaned, size, backend)


def resize_artwork(
    image: Image.Image, size: tuple[int, int], backend: Upscaler = "pillow",
    *, denoise: bool = False,
) -> Image.Image:
    if backend not in ("pillow", "realesrgan"):
        raise ValueError(f"Unknown image upscaler: {backend}")
    if min(size) < 1:
        raise ValueError("Resize dimensions must be positive.")
    if denoise:
        rgba = image.convert("RGBA")
        return _resize_denoised(rgba.size, rgba.tobytes(), size, backend).copy()
    if backend == "pillow" or (size[0] <= image.width and size[1] <= image.height):
        return image.resize(size, Image.Resampling.LANCZOS)
    rgba = image.convert("RGBA")
    rgb = rgba.convert("RGB")
    while rgb.width < size[0] or rgb.height < size[1]:
        rgb = _upscale_rgb(rgb.size, rgb.tobytes())
    result = rgb.resize(size, Image.Resampling.LANCZOS).convert("RGBA")
    # Alpha is coverage, not artwork; ML would invent unwanted opaque edges.
    result.putalpha(rgba.getchannel("A").resize(size, Image.Resampling.LANCZOS))
    return result
