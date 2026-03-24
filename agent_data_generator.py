from __future__ import annotations

import typing
from typing import TypedDict, Literal, List
from textwrap import dedent
import json
import os
import shutil

import texture_generator

HashType = Literal['Select', 'Tab', 'Round']
class SkinData(TypedDict, total=False): tab: str; select: str

agent_dict: TypedDict[str, List[SkinData]]
with open('agents.json', 'rt', encoding='utf-8') as agent_data:
    agent_dict = json.load(agent_data)

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

def gen_textures(mod_name: str = "MyMod", agent: str = None) -> None:
    mod_folder = os.path.join("export", mod_name)
    if not os.path.exists(mod_folder):
        os.makedirs(mod_folder)

    agents_to_process = {agent: agent_dict[agent]} if agent else agent_dict

    skin_generators = {
        'select': texture_generator.gen_selector,
        'tab': texture_generator.gen_tab,
        'round': texture_generator.gen_round
    }

    for name, skins in agents_to_process.items():
        for i, skin in enumerate(skins):
            for skin_type, generator in skin_generators.items():
                if skin.get(skin_type, {}).get('hash'):
                    hash, offset, scale, rotation = skin[skin_type].values()
                    generator(mod_folder, name, i, offset, scale, rotation)

def create_ini(mod_name: str = "MyMod") -> None:
    mod_folder = os.path.join("export", mod_name)
    if not os.path.exists(mod_folder):
        os.makedirs(mod_folder)

    ini_path = os.path.join(mod_folder, f"{mod_name.replace(" ", "")}.ini")
    with open(ini_path, 'w', encoding='utf-8') as output:
        output.write(f"; {mod_name} {'-' * (60 - len(mod_name))}\n\n")

        for name, skins in agent_dict.items():
            output.write(f"; {name} {'-' * (60 - len(name))}\n\n")

            skin_types = ['select', 'tab', 'round']
            for i, skin in enumerate(skins):
                for skin_type in skin_types:
                    if skin.get(skin_type, {}).get('hash'):
                        output.write(create_texture_override(
                            name,
                            i,
                            skin[skin_type]['hash'],
                            typing.cast(HashType, skin_type.capitalize())
                        ))

    print('Finished generating agent data! :P')

def export(mod_name: str = "MyMod", mod_version: str = "1.0") -> None:
    zip_name = mod_name.lower().replace(" ", "_") + "_v" + mod_version

    shutil.make_archive(os.path.join("export", zip_name), "zip", "export", mod_name)
    print(f"Finished exporting {mod_name} to {zip_name}.zip")