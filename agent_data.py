from __future__ import annotations

import typing
from typing import TypedDict, Literal, List
from textwrap import dedent
import json
import os
import shutil

import textures

HashType = Literal['Select', 'Tab', 'Round']

class SkinData(TypedDict, total=False):
    tab: str
    select: str

agent_dict: TypedDict[str, List[SkinData]]
with open('agents.json', 'rt', encoding='utf-8') as agent_data:
    agent_dict = json.load(agent_data)

# --------------------------------------------------------------

def create_texture_override(agent: str, skin_idx: int, source_dirs: list[str], hash_value: str, kind: HashType) -> str:
    skin_str: str = ""
    if skin_idx > 0:
        skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    if len(source_dirs) > 1:
        override_string = dedent(f"""\
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            """)

        resource_string = ""

        for i, source_dir in enumerate(source_dirs):
            variant = os.path.basename(source_dir)

            if variant == "sources":
                variant = ""

            override_string += dedent(f"""\
                {"else" if i > 0 else ""} if $variant == {i}
                    this = Resource{agent}{skin_str}{variant}{kind}
                """)

            resource_string += dedent(f"""\
                [Resource{agent}{skin_str}{variant}{kind}]
                filename = {kind.lower()}/{agent}{skin_str}{variant}.png
                """)
        override_string += "endif\n"

        return override_string + resource_string + "\n\n"
    else:
        variant = os.path.basename(source_dirs[0])
        if variant == "sources":
            variant = ""

        return dedent(f"""\
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            this = Resource{agent}{skin_str}{variant}{kind}
            [Resource{agent}{skin_str}{variant}{kind}]
            filename = {kind.lower()}/{agent}{skin_str}{variant}.png
            
            """)


def create_ini_header(mod_name: str, source_dirs: list[str]) -> str:
    header = f"; {mod_name} {'-' * (60 - len(mod_name))}\n\n"

    if len(source_dirs) > 1:
        header += dedent(f"""\
            ; Constants {'-' * (60 - 9)}
            
            [Constants]
            global persist $variant = 0
            
            [KeySwap]
            key = ctrl space
            type = cycle
            $variant = {','.join(str(i) for i in range(len(source_dirs)))}
        
            """)

    header += f"; Overrides {'-' * (60 - 9)}\n\n"

    return header


def gen_textures(mod_name: str, agent: str, source_dirs: list[str], export_root: str) -> None:
    export_dir = os.path.join(export_root, mod_name)
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    agents_to_process = {agent: agent_dict[agent]} if agent else agent_dict

    skin_generators = {
        'select': textures.gen_selector,
        'tab': textures.gen_tab,
        'round': textures.gen_round
    }

    # Nightmare
    for name, skins in agents_to_process.items():
        for i, skin in enumerate(skins):
            for skin_type, generator in skin_generators.items():
                if skin.get(skin_type, {}).get('hash'):
                    hash, offset, scale, rotation = skin[skin_type].values()
                    for source_dir in source_dirs:
                        generator(source_dir, export_dir, name, i, offset, scale, rotation)


def create_ini(mod_name: str,  source_dirs: list[str], export_root) -> None:
    mod_folder = os.path.join(export_root, mod_name)
    if not os.path.exists(mod_folder):
        os.makedirs(mod_folder)

    ini_path = os.path.join(mod_folder, f"{mod_name.replace(" ", "")}.ini")
    with open(ini_path, 'w', encoding='utf-8') as output:
        output.write(create_ini_header(mod_name, source_dirs))

        for name, skins in agent_dict.items():
            output.write(f"; {name} {'-' * (60 - len(name))}\n\n")

            skin_types = ['select', 'tab', 'round']
            for i, skin in enumerate(skins):
                for skin_type in skin_types:
                    if skin.get(skin_type, {}).get('hash'):
                        output.write(create_texture_override(
                            name,
                            i,
                            source_dirs,
                            skin[skin_type]['hash'],
                            typing.cast(HashType, skin_type.capitalize())
                        ))

    print('Finished generating agent data! :P')


def export(mod_name: str = "MyMod", mod_version: str = "1.0") -> None:
    zip_name = mod_name.lower().replace(" ", "_") + "_v" + mod_version

    shutil.make_archive(os.path.join("export", zip_name), "zip", "export", mod_name)
    print(f"Finished exporting {mod_name} to {zip_name}.zip")
