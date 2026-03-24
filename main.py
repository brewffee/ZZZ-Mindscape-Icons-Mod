import mask_generator
import agent_data_generator

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "2.7"

# To update textures for a single agent, replace None with that agent's name
CUR_AGENT = None

# --------------------------------------------------------------

# Generate texture masks
mask_generator.run()

# Generate mindscape textures
agent_data_generator.gen_textures(MOD_NAME, CUR_AGENT)

# Generate INI file
agent_data_generator.create_ini(MOD_NAME)

# Export to ZIP
agent_data_generator.export(MOD_NAME, MOD_VERSION)
