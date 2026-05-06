import os
import shutil

from agent_data import gen_textures, create_ini, export
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

# Generate mindscape textures
gen_textures()

# Generate INI file
create_ini()

# Export to ZIP
export()
