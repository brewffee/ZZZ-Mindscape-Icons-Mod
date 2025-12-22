from __future__ import annotations

import os
from typing import TypedDict, Literal, List, Tuple
from textwrap import dedent
import json
import mask

HashType = Literal['Tab', 'Select', 'Round']
class SkinData(TypedDict, total=False): tab: str; select: str

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"

# --------------------------------------------------------------

def generate_selector_tecture(agent: str, skin_idx: int, offset: Tuple[int, int] = (0, 0), scale: float = 1.0, rotation: float = 0.0) -> None:
    skin_str: str = ""
    if (skin_idx > 0): skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    print(f"Creating selector for {agent} {skin_str} ({offset}, {scale}, {rotation})")
    if not os.path.isfile(f"mindscapes/{agent}{skin_str}.png"):
        image = f"mindscapes/{agent}.png"
    else:
        image: str = f"mindscapes/{agent}{skin_str}.png"

    mask.mask_and_combine(
        size=(512, 500),
        mask_path="selector.png",
        image_path=image,
        output_path=f"select/{agent}{skin_str}.png",
        image_offset=offset,
        image_scale=scale,
        image_rotation=rotation
    )

def generate_tab_texture(agent: str, skin_idx: int, offset: Tuple[int, int] = (0, 0), scale: float = 1.0, rotation: float = 0.0) -> None:
    skin_str: str = ""
    if (skin_idx > 0): skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    print(f"Creating tab for {agent} {skin_str} ({offset}, {scale}, {rotation})")
    if not os.path.isfile(f"mindscapes/{agent}{skin_str}.png"):
        image = f"mindscapes/{agent}.png"
    else:
        image: str = f"mindscapes/{agent}{skin_str}.png"

    mask.mask_and_combine(
        size=(358, 128),
        final_size=(150, 54),
        mask_path="tab.png",
        image_path=image,
        output_path=f"tab/{agent}{skin_str}.png",
        image_offset=offset,
        image_scale=scale,
        image_rotation=rotation
    )

def generate_round_texture(agent: str, skin_idx: int, offset: Tuple[int, int] = (0, 0), scale: float = 1.0, rotation: float = 0.0) -> None:
    skin_str: str = ""
    if (skin_idx > 0): skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    print(f"Creating round for {agent} {skin_str} ({offset}, {scale}, {rotation})")
    if not os.path.isfile(f"mindscapes/{agent}{skin_str}.png"):
        image = f"mindscapes/{agent}.png"
    else:
        image: str = f"mindscapes/{agent}{skin_str}.png"

    mask.mask_and_combine(
        size=(284, 284),
        final_size=(150, 150),
        mask_path="round.png",
        image_path=image,
        output_path=f"round/{agent}{skin_str}.png",
        image_offset=offset,
        image_scale=scale,
        image_rotation=rotation
    )

# --------------------------------------------------------------

def create_texture_override(agent: str, skin_idx: int, hash_value: str, kind: HashType) -> str:
    skin_str: str = ""
    if (skin_idx > 0): skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    file_path: str = f"{kind.lower()}/{agent}{skin_str}.png"

    return dedent(f"""\
        [TextureOverride{agent}{skin_str}{kind}]
        hash = {hash_value}
        this = Resource{agent}{skin_str}{kind}
        [Resource{agent}{skin_str}{kind}]
        filename = {file_path}
        
        """)

agents: TypedDict[str, List[SkinData]]
with open('agents.json', 'rt', encoding='utf-8') as agent_data:
    agents = json.load(agent_data)

with open('agent_data.ini', 'w', encoding='utf-8') as output:
    output.write(f"; {MOD_NAME} {'-' * (60 - len(MOD_NAME))}\n\n")

    for name, skins in sorted(agents.items()):
        output.write(f"; {name} {'-' * (60 - len(name))}\n\n")

        for i, skin in enumerate(skins):
            generate_selector_tecture(name, i, skin['select']['offset'], skin['select']['scale'], skin['select']['rotation'])
            generate_tab_texture(name, i, skin['tab']['offset'], skin['tab']['scale'], skin['tab']['rotation'])
            generate_round_texture(name, i, skin['round']['offset'], skin['round']['scale'], skin['round']['rotation'])

            if ('tab' in skin and skin['tab']['hash']): output.write(create_texture_override(name, i, skin['tab']['hash'], 'Tab'))
            if ('select' in skin and skin['select']['hash']): output.write(create_texture_override(name, i, skin['select']['hash'], 'Select'))
            if ('round' in skin and skin['round']['hash']): output.write(create_texture_override(name, i, skin['round']['hash'], 'Round'))

print('Agent data generated successfully')
exit(0)

