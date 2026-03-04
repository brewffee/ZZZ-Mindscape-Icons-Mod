import mask_generator
import agent_data_generator

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"
MOD_VERSION: str = "2.6.3"

# To update textures for a single agent, replace None with that agent's name
CUR_AGENT = None

# --------------------------------------------------------------

# Generate texture masks
mask_generator.run()

# Generate mindscape textures
agent_data_generator.gen_textures(CUR_AGENT)

# Generate INI file
agent_data_generator.create_ini(MOD_NAME)
