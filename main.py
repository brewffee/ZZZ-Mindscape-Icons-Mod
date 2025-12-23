import mask_generator
import agent_data_generator

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"
CUR_AGENT: str = "Alice"

# --------------------------------------------------------------

# Generate texture masks
mask_generator.run()

# Generate mindscape textures and INI file
# Pass CUR_AGENT to run() if you only want to uopdate a single agent
agent_data_generator.run(MOD_NAME)
