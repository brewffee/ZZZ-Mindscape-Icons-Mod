AUTHOR: str = "brewffee"
CONTACT: str = "@brewffee on Discord"
REPO_URL: str = "https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod"

MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "3.2-dev"

# If the filter should exclude (True) or only include (False) the agents
# specified in the AGENTS list
FILTER_EXCLUDE = True

# A list of agent names to process or skip, will resolve to the agent objects
# provided in the agents.json file
AGENTS: list[str] = []

DATA_FILE: str = "agents_new.json"
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

# todo:
#   configurable resource types (select, tab, round, portrait)
RESOURCE_TYPES: list[str] = ["Select", "Tab", "Round"] # or ["Portrait"]

# todo:
#   keybinds (variant, on/off <type>)
VARIANT_KEYBIND = "ctrl space"  # switch between variants
SKIN_KEYBINDS: list[str] = [
    "ctrl alt shift 1",         # enable/disable select icons
    "ctrl alt shift 2",         # enable/disable tab icons
    "ctrl alt shift 3",         # enable/disable round icons
    "ctrl alt shift 4",         # enable/disable portrait icons
]


