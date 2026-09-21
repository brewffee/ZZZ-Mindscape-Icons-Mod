import os
import shutil

import ini
import masks
import agent_data
import config

# --------------------------------------------------------------

# todo: validate config values before processing instead of encounrtering as we go

# Generate texture masks
masks.generate()

# Clean export dir
if config.CLEAN_EXPORTS:
    print("Force clean requested! Recreating export directory...")
    shutil.rmtree(config.EXPORT_DIR, ignore_errors=True)
    os.makedirs(config.EXPORT_DIR)
    print("")

# collect required agents
agent_data.collect()

# test
print(
    ini.create_header() + ini.create_constants() + ini.create_footer()
)

# Generate mindscape textures
#gen_textures()

# Generate INI file
#create_ini()

# Export to ZIP
#export()
