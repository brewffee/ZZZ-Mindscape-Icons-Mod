from agent_data import gen_textures, create_ini, export
from masks import gen_masks

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "2.7.1"

# To update textures for a single agent, replace None with that agent's name
CUR_AGENT: str | None = None

SOURCE_DIRS: list[str] = ["sources/M6", "sources/M3"]
EXPORT_DIR: str = "export"

# --------------------------------------------------------------

# Generate texture masks
gen_masks()

# Generate mindscape textures
gen_textures(MOD_NAME, CUR_AGENT, SOURCE_DIRS, EXPORT_DIR)

# Generate INI file
create_ini(MOD_NAME, SOURCE_DIRS, EXPORT_DIR)

# Export to ZIP
export(MOD_NAME, MOD_VERSION)
