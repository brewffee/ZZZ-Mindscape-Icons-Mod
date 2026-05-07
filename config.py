MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "2.8.1"

# To update textures for a single agent, replace None with that agent's name
CUR_AGENT: str | None = None

SOURCE_DIRS: list[str] = ["sources/M6", "sources/M3"]
EXPORT_DIR: str = "export"

# How the generator should behave when a source file is missing.
#
# "skip" will ignore the missing variant and won't generate an INI entry for
# it, defaulting to ZZZ's original texture.
#
# "original" will use the first source's resource as a fallback.
FALLBACK_MODE: str = "original"

# Should the export directory be cleaned before generation?
CLEAN_EXPORTS: bool = True
