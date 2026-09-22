MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "3.2-dev"

# Mod author information to be printed in the INI file. I recommend updating
# this with your own contact and information if you're planning to share a
# modified copy with others. Can also be left blank if desired.
AUTHOR: str = "brewffee"
CONTACT: str = "@brewffee on Discord"
REPO_URL: str = "https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod"

# A list of agent names to process or skip, will resolve to the agent objects
# provided in the agents.json file. Leave this value empty and FILTER_EXCLUDE
# set to True to process all agents.
AGENTS: list[str] = []

# If the filter should exclude (True) or only include (False) the agents
# specified in the AGENTS list
FILTER_EXCLUDE: bool = True

# todo: ini only mode

DATA_FILE: str = "agents_new.json"
# todo: prefer a k(name) v(path) format
SOURCE_DIRS: list[str] = ["sources_new/M6", "sources_new/M3"]
EXPORT_DIR: str = "export"

# Should the export directory be cleaned before generation?
CLEAN_EXPORTS: bool = False

# todo:
#   VARIANT_FALLBACK = bool fall back to default variant if variant is missing?
#   SKIN_FALLBACK = bool fall back to default skin if skin is missing?

# todo:
#   Should the INI file be split into multiple files by icon type?
#   SPLIT_INI: bool = False

# A list of resource types to generate. Valid options can be "Select", "Tab",
# "Round", or "Portrait".
RESOURCE_TYPES: list[str] = ["Select", "Tab", "Round"]

# The keybind used for switching between variants. If there are no additional
# variants, this field can also be left blank.
VARIANT_KEYBIND: str = "ctrl space"

# todo: should probably make this optional
# The keybinds used for enabling/disabling each resource type. The order of
# the keybinds should match the order of the RESOURCE_TYPES list.
SKIN_KEYBINDS: list[str] = [
    "ctrl alt shift 1",         # enable/disable select icons
    "ctrl alt shift 2",         # enable/disable tab icons
    "ctrl alt shift 3",         # enable/disable round icons
    "ctrl alt shift 4",         # enable/disable portrait icons
]
