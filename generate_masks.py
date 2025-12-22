from pathlib import Path
from typing import List, Tuple, Union
from PIL import Image, ImageDraw

def calculate_arc_points(start: Tuple[float, float], 
    end: Tuple[float, float],
    curve_direction: str = 'up',
    curve_strength: float = 0.2,
    num_points: int = 10
) -> List[Tuple[float, float]]:

    mid_x = (start[0] + end[0]) / 2
    mid_y = (start[1] + end[1]) / 2
    
    dx = end[0] - start[0]
    dy = end[1] - start[1]
    
    if curve_direction.lower() == 'up':
        perp_x = -dy
        perp_y = dx
    else:
        perp_x = dy
        perp_y = -dx
    
    length = (perp_x**2 + perp_y**2) ** 0.5
    if length > 0:
        perp_x = perp_x / length * curve_strength * ((dx**2 + dy**2) ** 0.5)
        perp_y = perp_y / length * curve_strength * ((dx**2 + dy**2) ** 0.5)
    
    control_x = mid_x + perp_x
    control_y = mid_y + perp_y

    points = []
    for i in range(num_points + 1):
        t = i / num_points
        # B(t) = (1-t)^2 * P0 + 2(1-t)t * P1 + t^2 * P2
        x = (1-t)**2 * start[0] + 2*(1-t)*t * control_x + t**2 * end[0]
        y = (1-t)**2 * start[1] + 2*(1-t)*t * control_y + t**2 * end[1]
        points.append((x, y))
        print(f"({x:.2f}, {y:.2f})")

    return points

def gen_selector_mask(output_path: Union[str, Path] = "selector.png") -> None:
    scale_factor = 4
    width, height = 512, 500
    
    selector = Image.new('RGBA', (width * scale_factor, height * scale_factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(selector)

    scaled_points = []
    for point in [
        *calculate_arc_points((137, 29), (173, 0), 'down', num_points=24),  # More points for smoother curve
        (510, 0),    # Top right
        *calculate_arc_points((374, 472), (339, 500), 'down', num_points=24),  # More points for smoother curve
        (2, 500),    # Bottom left
    ]: scaled_points.append((point[0] * scale_factor, point[1] * scale_factor))

    draw.polygon(scaled_points, fill=(0, 0, 0, 255))
    
    # scale down
    selector = selector.resize((width, height), Image.Resampling.LANCZOS)
    selector.save(output_path, "PNG")
    print(f"Selector mask saved as {output_path}")

def gen_tab_mask(output_path: Union[str, Path] = "tab.png") -> None:
    scale_factor = 6
    width, height = 358, 128

    selector = Image.new('RGBA', (width * scale_factor, height * scale_factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(selector)

    scaled_points = []
    for point in [
        (2, 22),
        *calculate_arc_points((2,4), (6, 0), 'down', num_points=24), # Top left
        *calculate_arc_points((295, 0), (310, 10), 'down', num_points=24), # Top right
        (356, 106),
        *calculate_arc_points((356, 124), (349, 128), 'down', num_points=24), # Bottom right
        *calculate_arc_points((62, 128), (44, 110), 'down', num_points=24), # Bottom left
    ]: scaled_points.append((point[0] * scale_factor, point[1] * scale_factor))

    draw.polygon(scaled_points, fill=(0, 0, 0, 255))

    selector = selector.resize((width, height), Image.Resampling.LANCZOS)
    selector.save(output_path, "PNG")
    print(f"Selector mask saved as {output_path}")

def gen_round_mask(output_path: Union[str, Path] = "round.png") -> None:
    # just a circle
    scale_factor = 6
    width, height = 284, 284

    selector = Image.new('RGBA', (width * scale_factor, height * scale_factor), (0, 0, 0, 0))
    draw = ImageDraw.Draw(selector)

    draw.ellipse((0, 0, width * scale_factor, height * scale_factor), fill=(0, 0, 0, 255))

    selector = selector.resize((width, height), Image.Resampling.LANCZOS)
    selector.save(output_path, "PNG")
    print(f"Selector mask saved as {output_path}")

gen_selector_mask()
gen_tab_mask()
gen_round_mask()


