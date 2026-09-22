import os
import shutil

import ini
import masks
import agent_data
import config
import validate

# --------------------------------------------------------------

validate.pre_check()

# Generate texture masks
masks.generate()

# Clean export dir
if config.CLEAN_EXPORTS:
    print("Force clean requested! Recreating export directory...")
    shutil.rmtree(config.EXPORT_DIR, ignore_errors=True)
    os.makedirs(config.EXPORT_DIR)
    print("")

# collect required agents
agents_to_process = agent_data.collect()

#validate.post_check(agents_to_process)

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
