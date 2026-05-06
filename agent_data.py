from __future__ import annotations

import typing
from typing import TypedDict, Literal, List
from textwrap import dedent
import json
import os
import shutil

from config import MOD_NAME, MOD_VERSION, CUR_AGENT, SOURCE_DIRS, EXPORT_DIR
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

    available_resources = []
    for source_dir in source_dirs:
        variant = os.path.basename(source_dir)
        if variant == "sources":
            variant = ""

        file_name = f"{kind.lower()}/{agent}{skin_str}{variant}.png"
        if os.path.exists(f"{EXPORT_DIR}/{MOD_NAME}/{file_name}"):
            available_resources.append((source_dir, variant, file_name))

    # agent has no data to override
    if not available_resources:
        return ""

    # first avaiable resource
    fallback_source, fallback_variant, fallback_file = available_resources[0]

    # multiple resource mode (toggles)
    if len(available_resources) > 1:
        override_string = dedent(f"""
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            """)

        resource_string = ""

        for i, (source_dir, variant, file_name) in enumerate(
                available_resources):
            resource_name = f"{agent}{skin_str}{variant}{kind}"

            override_string += dedent(f"""\
                {"else" if i > 0 else ""} if $variant == {i}
                    this = Resource{resource_name}
                """)

            resource_string += dedent(f"""\
                [Resource{resource_name}]
                filename = {file_name}
                """)
        override_string += "endif\n"

        return override_string + resource_string
    else:
        # single resource mode (no toggles)
        source_dir, variant, file_name = available_resources[0]
        return dedent(f"""        
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            this = Resource{agent}{skin_str}{variant}{kind}
            [Resource{agent}{skin_str}{variant}{kind}]
            filename = {file_name}
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


def gen_textures() -> None:
    print("Generating textures...")

    export_dir = os.path.join(EXPORT_DIR, MOD_NAME)
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    agents_to_process = {CUR_AGENT: agent_dict[CUR_AGENT]} if CUR_AGENT else agent_dict

    skin_generators = {
        'select': textures.gen_selector,
        'tab': textures.gen_tab,
        'round': textures.gen_round
    }

    fallback_dir = SOURCE_DIRS[0] if len(SOURCE_DIRS) > 1 else ""

    # Nightmare
    for name, skins in agents_to_process.items():
        for i, skin in enumerate(skins):
            for skin_type, generator in skin_generators.items():
                if skin.get(skin_type, {}).get('hash'):
                    hash, offset, scale, rotation = skin[skin_type].values()
                    for source_dir in SOURCE_DIRS:
                        generator(source_dir, fallback_dir, export_dir, name, i, offset, scale, rotation)
    print("")

def create_ini() -> None:
    print("Creating INI file...")
    mod_folder = os.path.join(EXPORT_DIR, MOD_NAME)
    if not os.path.exists(mod_folder):
        os.makedirs(mod_folder)

    ini_path = os.path.join(mod_folder, f"{MOD_NAME.replace(" ", "")}.ini")
    with open(ini_path, 'w', encoding='utf-8') as output:
        output.write(create_ini_header(MOD_NAME, SOURCE_DIRS))

        for name, skins in agent_dict.items():
            result = ""
            skin_types = ['select', 'tab', 'round']
            for i, skin in enumerate(skins):
                for skin_type in skin_types:
                    if skin.get(skin_type, {}).get('hash'):
                        result += create_texture_override(
                            name,
                            i,
                            SOURCE_DIRS,
                            skin[skin_type]['hash'],
                            typing.cast(HashType, skin_type.capitalize())
                        )

            if result:
                output.write(f"; {name} {'-' * (60 - len(name))}\n" + result)

        output.write(
            "\n; INI file generated by brewffee's Mindscape Icons generator :3c\n" +
            "; If you have any issues with this mod, please contact me on " +
            "discord at @brewffee.\n" +
            ";\n" +
            "; The source code for this mod's generator is available at " +
            "https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod\n"

        )

    print("Finished generating agent data! :P\n")


def export() -> None:
    print("Exporting mod contents to zip...")
    zip_name = MOD_NAME.lower().replace(" ", "_") + "_v" + MOD_VERSION

    shutil.make_archive(os.path.join("export", zip_name), "zip", "export", MOD_NAME)
    print(f"Finished exporting {MOD_NAME} to {zip_name}.zip! x3c\n")
