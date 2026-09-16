MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "3.2-dev"

# If the filter should exclude (True) or only include (False) the agents
# specified in the AGENTS list
FILTER_EXCLUDE = True

# A list of agent names to process or skip, will resolve to the agent objects
# provided in the agents.json file
AGENTS: list[str] = []

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

# ===================================================================
# How the generator should behave when a source file is missing.
#
# "skip" will ignore the missing variant and won't generate an INI entry for
# it, defaulting to ZZZ's original texture.
#
# "original" will use the first source's resource as a fallback.
# FALLBACK_MODE: str = "original"
#
# To update textures for a single agent, replace None with that agent's name
# CUR_AGENT: str | None = None

