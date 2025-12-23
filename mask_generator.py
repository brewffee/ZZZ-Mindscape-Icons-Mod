from pathlib import Path
from typing import List, Tuple, Union
from PIL import Image, ImageDraw

# calcs arc for rounded corners
def calculate_arc_points(
        start: Tuple[float, float],
        end: Tuple[float, float],
        num_points: int = 24
) -> List[Tuple[float, float]]:

    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2

    # dist
    dx = end[0] - start[0]
    dy = end[1] - start[1]

    # influence down
    perp_x = dy
    perp_y = -dx
    
    length = (perp_x**2 + perp_y**2) ** 0.5
    if length > 0:
        perp_x = perp_x / length * 0.2 * ((dx**2 + dy**2) ** 0.5)
        perp_y = perp_y / length * 0.2 * ((dx**2 + dy**2) ** 0.5)
    
    control_x = mid_x + perp_x
    control_y = mid_y + perp_y

    points:  List[Tuple[float, float]] = []
    for i in range(num_points + 1):
        t = i / num_points

        # B(t) = (1-t)^2 * start + 2(1-t)t * ctrk + t^2 * end
        x = (1-t)**2 * start[0] + 2*(1-t)*t * control_x + t**2 * end[0]
        y = (1-t)**2 * start[1] + 2*(1-t)*t * control_y + t**2 * end[1]
        points.append((x, y))
        print(f"ppoint({x:.2f}, {y:.2f})")

    return points

def gen_mask(
        size: Tuple[float, float],
        scale_factor: int,
        points: List[Tuple[float, float]],
        output_path: Union[str, Path] = "mask.png",
        circle: bool = False
) -> None:
    width, height = size

    mask = Image.new('RGBA', (width * scale_factor, height * scale_factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(mask)

    if (circle): draw.ellipse((0, 0, width * scale_factor, height * scale_factor), fill=(0, 0, 0, 255))
    else: draw.polygon(points, fill=(0, 0, 0, 255))

    # gives softer look after downacale
    mask = mask.resize((width, height), Image.Resampling.LANCZOS)
    mask.save(output_path, "PNG")
    print(f"Mask saved as {output_path}")

def selector_mask_points(scale_factor: int = 6) -> List[Tuple[float, float]]:
    scaled_points = []
    for point in [
        *calculate_arc_points((137, 29), (173, 0), 24),     # topleft
        (510, 0),                                           # topright
        *calculate_arc_points((374, 472), (339, 500), 24),  # bottomright
        (2, 500),                                           # bottom left
    ]: scaled_points.append((point[0] * scale_factor, point[1] * scale_factor))
    return scaled_points

def tab_mask_points(scale_factor: int = 6) -> List[Tuple[float, float]]:
    scaled_points = []
    for point in [
        (2, 22),                                            # edge topleft
        *calculate_arc_points((2,4), (6, 0), 24),           # topleft
        *calculate_arc_points((295, 0), (310, 10), 24),     # ropright
        (356, 106),                                         # edge topright
        *calculate_arc_points((356, 124), (349, 128), 24),  # bottomright
        *calculate_arc_points((62, 128), (44, 110), 24),    # bottomleft
    ]: scaled_points.append((point[0] * scale_factor, point[1] * scale_factor))
    return scaled_points


def run() -> None:
    gen_mask((512, 500), 4, selector_mask_points(4), "selector.png")
    gen_mask((358, 128), 6, tab_mask_points(6), "tab.png")
    gen_mask((284, 284), 6, [], "round.png", True)
