from pathlib import Path
from typing import Tuple, Union
from PIL import Image, PngImagePlugin
import struct

def mask_and_combine(
        size: Tuple[int, int],
        mask_path: Union[str, Path],
        image_path: Union[str, Path],
        output_path: Union[str, Path],
        image_offset: Tuple[int, int] = (1, 1),
        image_scale: float = 1.0,
        image_rotation: float = 0.0,
        final_size: Tuple[int, int] = None,
) -> None:
    mask = Image.open(mask_path).convert("RGBA")
    image = Image.open(image_path).convert("RGBA")

    if image_scale != 1.0:
        new_size = (int(image.width * image_scale), int(image.height * image_scale))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    if image_rotation != 0:
        image = image.rotate(-image_rotation, expand=True, resample=Image.BICUBIC)

    img_x = -image_offset[0] + (mask.width - image.width) // 2
    img_y = -image_offset[1] + (mask.height - image.height) // 2

    masked_result = Image.new('RGBA', mask.size)
    for x in range(mask.width):
        for y in range(mask.height):
            _, _, _, mask_alpha = mask.getpixel((x, y))

            src_x, src_y = x - img_x, y - img_y
            if 0 <= src_x < image.width and 0 <= src_y < image.height:
                r, g, b, img_alpha = image.getpixel((src_x, src_y))
                combined_alpha = int(mask_alpha * img_alpha / 255)
                masked_result.putpixel((x, y), (r, g, b, combined_alpha))
            else:
                masked_result.putpixel((x, y), (0, 0, 0, 0))

    result = Image.new('RGBA', (size[0], size[1]), (0, 0, 0, 0))

    position = (
        (size[0] - mask.width) // 2,
        (size[1] - mask.height) // 2
    )
    result.alpha_composite(masked_result, position)

    png_info = PngImagePlugin.PngInfo()
    png_info.add(b"gAMA", struct.pack(">I", 45455))
    png_info.add(b"sRGB", struct.pack("B", 0))

    if final_size is not None:
        result = result.resize(final_size, Image.Resampling.LANCZOS)

    result.save(
        output_path,
        pnginfo=png_info,
        dpi=(72, 72),
    )
    print(f"Masked image saved as {output_path}")