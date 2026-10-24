from __future__ import annotations

import typing
from typing import Literal
from textwrap import dedent
import json
import os
import shutil
from pathlib import Path

from config import MOD_NAME, MOD_VERSION, CUR_AGENT, SOURCE_DIRS, EXPORT_DIR, SEPARATE_INIS, load_config
import textures
from editor_model import Agents, agent_json, load_chibi, sync_chibi

HashType = Literal['Select', 'Tab', 'Round']

agent_dict: Agents
with open('agents.json', 'rt', encoding='utf-8') as agent_data:
    agent_dict = json.load(agent_data)

# --------------------------------------------------------------

def create_texture_override(agent: str, skin_idx: int, source_dirs: list[str], hash_value: str, kind: HashType) -> str:
    skin_str: str = ""
    if skin_idx > 0:
        skin_str = "Skin" + (str(skin_idx) if skin_idx > 1 else "")

    available_resources = []
    for index, source_dir in enumerate(source_dirs):
        variant = Path(source_dir).name
        if variant == "sources":
            variant = ""

        file_name = f"{kind.lower()}/{agent}{skin_str}{variant}.png"
        if (
            textures.resolve_source(source_dir, agent, skin_idx, typing.cast(textures.MaskKind, kind.lower())) is not None
            and os.path.exists(f"{EXPORT_DIR}/{MOD_NAME}/{file_name}")
        ):
            available_resources.append((index, variant, file_name))

    # agent has no data to override
    if not available_resources:
        return ""

    # multiple resource mode (toggles)
    if len(source_dirs) > 1:
        override_string = dedent(f"""
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            if $use{kind} == 1
            \t""")

        resource_string = ""

        for i, (variant_index, variant, file_name) in enumerate(
                available_resources):
            resource_name = f"{agent}{skin_str}{variant}{kind}"

            override_string += dedent(f"""\
                   {"\telse " if i > 0 else "\t"}if $use{kind}Variant == {variant_index}
                            this = Resource{resource_name}
                    """)

            resource_string += dedent(f"""\
                [Resource{resource_name}]
                filename = {file_name}
                """)
        override_string += "    endif\nendif\n"

        return override_string + resource_string
    else:
        # single resource mode (no toggles)
        variant_index, variant, file_name = available_resources[0]
        return dedent(f"""        
            [TextureOverride{agent}{skin_str}{kind}]
            hash = {hash_value}
            if $use{kind} == 1
                this = Resource{agent}{skin_str}{variant}{kind}
            endif
            [Resource{agent}{skin_str}{variant}{kind}]
            filename = {file_name}
            """)

def create_ini_header(
    mod_name: str, mod_ver: str, source_dirs: list[str], mask_kind: HashType | None = None
) -> str:
    """Create controls for one mask, or all masks when mask_kind is omitted."""
    kinds = [
        (index, kind)
        for index, kind in enumerate(("Select", "Tab", "Round"), 1)
        if mask_kind is None or kind == mask_kind
    ]
    text = f"{mod_name} v{mod_ver}"
    header = f"; {text} {'-' * (60 - len(text))}\n\n"

    header += f"; Constants {'-' * (60 - 9)}\n\n[Constants]\n"
    if len(source_dirs) > 1:
        for _, kind in kinds:
            header += f"global persist $use{kind}Variant = 0\n"
    for _, kind in kinds:
        header += f"global persist $use{kind} = 1\n"
    header += "global persist $lockIcons = 0\n\n"

    header += dedent("""\
        [KeySwapLock]
        key = ctrl alt shift L
        type = cycle
        $lockIcons = 0,1

        """)
    if len(source_dirs) > 1:
        for index, kind in kinds:
            header += dedent(f"""\
                [KeySwapVariant{kind}]
                condition = $lockIcons == 0
                key = ctrl alt {index}
                type = cycle
                $use{kind}Variant = {','.join(str(i) for i in range(len(source_dirs)))}

                """)

    for index, kind in kinds:
        header += dedent(f"""\
            [KeyToggle{kind}]
            condition = $lockIcons == 0
            key = ctrl alt shift {index}
            type = cycle
            $use{kind} = 0,1

            """)

    header += f"; Overrides {'-' * (60 - 9)}\n"

    return header


def gen_textures() -> None:
    print("Generating textures...")

    export_dir = os.path.join(EXPORT_DIR, MOD_NAME)
    if not os.path.exists(export_dir):
        os.makedirs(export_dir)

    agents_to_process = {CUR_AGENT: agent_dict[CUR_AGENT]} if CUR_AGENT else agent_dict
    stored_chibi = load_chibi(Path.cwd(), agent_dict, load_config())
    chibi_agents = sync_chibi(agent_dict, stored_chibi)
    if any(textures.is_chibi(source) for source in SOURCE_DIRS):
        chibi_path = Path("agents-chibi.json")
        if not chibi_path.exists() or chibi_agents != stored_chibi:
            chibi_path.write_bytes(agent_json(chibi_agents))

    skin_generators = {
        'select': textures.gen_select,
        'tab': textures.gen_tab,
        'round': textures.gen_round
    }

    fallback_dir = SOURCE_DIRS[0] if len(SOURCE_DIRS) > 1 else ""

    # Nightmare
    for name, skins in agents_to_process.items():
        for i, skin in enumerate(skins):
            for skin_type, generator in skin_generators.items():
                if skin.get(skin_type, {}).get('hash'):
                    for source_dir in SOURCE_DIRS:
                        entry = (chibi_agents if textures.is_chibi(source_dir) else agent_dict)[name][i][skin_type]
                        offset = (entry['offset'][0], entry['offset'][1])
                        scale = entry['scale']
                        rotation = entry['rotation']
                        generator(source_dir, fallback_dir, export_dir, name, i, offset, scale, rotation)
    print("")

def create_ini() -> None:
    print("Creating INI file...")
    mod_folder = os.path.join(EXPORT_DIR, MOD_NAME)
    if not os.path.exists(mod_folder):
        os.makedirs(mod_folder)

    footer = (
        "\n; INI file generated by brewffee's Mindscape Icons generator :3c\n"
        "; If you have any issues with this mod, please contact me on "
        "discord at @brewffee.\n"
        ";\n"
        "; The source code for this mod's generator is available at "
        "https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod\n"
    )

    def collect_overrides_for_skin_type(skin_type: str) -> str:
        collected = ""
        for name, skins in agent_dict.items():
            result = ""
            for i, skin in enumerate(skins):
                if skin.get(skin_type, {}).get('hash'):
                    result += create_texture_override(
                        name,
                        i,
                        SOURCE_DIRS,
                        skin[skin_type]['hash'],
                        typing.cast(HashType, skin_type.capitalize())
                    )

            if result:
                collected += f"\n; {name} {'-' * (60 - len(name))}\n" + result
        return collected

    if SEPARATE_INIS:
        kind_map: dict[str, HashType] = {
            'select': 'Select',
            'tab': 'Tab',
            'round': 'Round'
        }

        for skin_type, suffix in kind_map.items():
            ini_name = f"{MOD_NAME.replace(' ', '')}_{suffix}.ini"
            ini_path = os.path.join(mod_folder, ini_name)
            with open(ini_path, 'w', encoding='utf-8') as output:
                output.write(create_ini_header(MOD_NAME, MOD_VERSION, SOURCE_DIRS, suffix))
                output.write(collect_overrides_for_skin_type(skin_type))
                output.write(footer)
    else:
        ini_path = os.path.join(mod_folder, f"{MOD_NAME.replace(' ', '')}.ini")
        with open(ini_path, 'w', encoding='utf-8') as output:
            output.write(create_ini_header(MOD_NAME, MOD_VERSION, SOURCE_DIRS))
            output.write(collect_overrides_for_skin_type('select'))
            output.write(collect_overrides_for_skin_type('tab'))
            output.write(collect_overrides_for_skin_type('round'))
            output.write(footer)

    print("Finished generating agent data! :P\n")


def export() -> None:
    print("Exporting mod contents to zip...")
    zip_name = MOD_NAME.lower().replace(" ", "_") + "_v" + MOD_VERSION

    shutil.make_archive(os.path.join(EXPORT_DIR, zip_name), "zip", EXPORT_DIR, MOD_NAME)
    print(f"Finished exporting {MOD_NAME} to {zip_name}.zip! x3c\n")
