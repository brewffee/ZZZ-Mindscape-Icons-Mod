import os
import shutil

from agent_data import collect_agents
from masks import gen_masks
from config import CLEAN_EXPORTS, EXPORT_DIR

# --------------------------------------------------------------

# Generate texture masks
gen_masks()

# Clean export dir
if CLEAN_EXPORTS:
    print("Force clean requested! Recreating export directory...")
    shutil.rmtree(EXPORT_DIR, ignore_errors=True)
    os.makedirs(EXPORT_DIR)
    print("")

# collect required agents
collect_agents()

# Generate mindscape textures
#gen_textures()

# Generate INI file
#create_ini()

# Export to ZIP
#export()
