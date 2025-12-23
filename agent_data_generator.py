from __future__ import annotations
from typing import TypedDict, Literal, List
from textwrap import dedent
import json

import texture_generator

HashType = Literal['Tab', 'Select', 'Round']
class SkinData(TypedDict, total=False): tab: str; select: str

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

def run(mod_name: str = "MyMod", agent: str = None) -> None:
    agent_dict: TypedDict[str, List[SkinData]]
    with open('agents.json', 'rt', encoding='utf-8') as agent_data:
        agent_dict = json.load(agent_data)

    with open('agent_data.ini', 'w', encoding='utf-8') as output:
        output.write(f"; {mod_name} {'-' * (60 - len(mod_name))}\n\n")

        if agent:
            agent_dict = {agent: agent_dict[agent]}

        for name, skins in sorted(agent_dict.items()):
            output.write(f"; {name} {'-' * (60 - len(name))}\n\n")

            for i, skin in enumerate(skins):

                if ('select' in skin and skin['select']['hash']):
                    hash, offset, scale, rotation = skin['select'].values()
                    texture_generator.gen_selector(name, i, offset, scale, rotation)
                    output.write(create_texture_override(name, i, hash, 'Select'))

                if ('tab' in skin and skin['tab']['hash']):
                    hash, offset, scale, rotation = skin['tab'].values()
                    texture_generator.gen_tab(name, i, offset, scale, rotation)
                    output.write(create_texture_override(name, i, hash, 'Tab'))

                if ('round' in skin and skin['round']['hash']):
                    hash, offset, scale, rotation = skin['round'].values()
                    texture_generator.gen_round(name, i, offset, scale, rotation)
                    output.write(create_texture_override(name, i, hash, 'Round'))

    print('Finished generating agent data! :P')

