from __future__ import annotations

import os
import json
from typing import Literal

from config import FILTER_EXCLUDE, AGENTS, SOURCE_DIRS

HashType = Literal['Select', 'Tab', 'Round']

# --------------------------------------------------------------

agent_data: dict
def collect_agents():
    print("Collecting agents...")

    global agent_data
    with open('agents_new.json', 'rt', encoding='utf-8') as d:
        agent_data = json.load(d)

    # quick validation of agent names
    for agent in AGENTS:
        if agent not in agent_data:
            print(
                f"Requested agent '{agent}' could not be found! Make sure the "
                "agent's name is spelled correctly, or add them to the "
                "agents.json file if you haven't already."
            )

    # exclude/include filters
    if FILTER_EXCLUDE:
        agent_data = {k: agent_data[k] for k in agent_data if k not in AGENTS}
    else:
        agent_data = {k: agent_data[k] for k in agent_data if k in AGENTS}

    count = len(agent_data)
    print(f"Found {count} agent entr{"ies" if count != 1 else "y"}!\n")
    # print([k for k in agent_data])

    return validate_agents()

def validate_agents():
    print("Validating agent entries...")

    # validate source files and hashes
    agents_to_process: dict = {}
    invalid_entries, valid_entries = 0, 0
    for [agent, skins] in agent_data.items():

        # verify a source file exists in <SRC>/<Agent><Skin>.png
        for i, [skin, data] in enumerate(skins.items()):
            source_file = f"{agent}{skin}.png"
            source_lenient = f"{agent}.png"

            for j, [source_dir] in enumerate(SOURCE_DIRS):
                variant_name = os.path.basename(source_dir)
                if variant_name == "sources":
                    variant_name = ""

                path = os.path.join(source_dir, source_file)
                path_lenient = os.path.join(source_dir, source_lenient)

                exists = os.path.exists(path)
                exists_lenient = os.path.exists(path_lenient) if i == 0 else False

                # todo: handle fallbacks
                #   if VARIANT_FALLBACK is True, and j0 has a source, add a flag to exp data (dont just regen file)
                #   same for SKIN_FALLBACK and i0 having source
                #   probably add data.variant_fallback and data.skin_fallback?
                # default skin (0) doesn't need a skin name in the source file
                if not exists and not exists_lenient:
                    print(
                        f"[{agent}] Couldn't find a source file for Skin #{i} "
                        f"'{skin}' in '{source_dir}'! Make sure the file "
                        f"'{source_file}' "
                        f"{f"or '{source_lenient}'" if i == 0 else "" }is "
                        "present in the source directories!"
                    )
                    invalid_entries += 1
                    continue
                else:
                    data["source"] = path if exists else path_lenient
                    valid_entries += 1

                # AnbyStreetStreakM6
                key = agent + skin + variant_name
                if key not in agents_to_process:
                    agents_to_process[key] = {}
                agents_to_process[key] = data

    total = valid_entries + invalid_entries
    print(f"Found {valid_entries}/{total} valid agent entr{"ies" if total != 1 else "y"}!")
    print(agents_to_process)

    return agents_to_process
