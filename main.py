import mask_generator
import agent_data_generator

# --------------------------------------------------------------

MOD_NAME: str = "Mindscape Icons"
CUR_AGENT: str | None = None # Enter an agent's name to only update that agent

# --------------------------------------------------------------

# Generate texture masks
mask_generator.run()

# Generate mindscape textures and INI file
agent_data_generator.run(MOD_NAME, CUR_AGENT)
