import os.path

import config

def pre_check():
    if not bool(config.MOD_NAME):
        print("No mod name provided! Falling back to a default value...")
        config.MOD_NAME = "MyMod"

    if not bool(config.MOD_VERSION):
        config.MOD_VERSION = "1.0.0"

    if config.FILTER_EXCLUDE == False and len(config.AGENTS) == 0:
        print(
            "`FILTER_EXCLUDE` is false, but no agents were specified! If you "
            "mean to process all agents, set `FILTER_EXCLUDE` to `True` in "
            "`config.py`! If not, make sure you have specified the agents you "
            "want to include in the `AGENTS` list!"
        )
        print("Nothing left to do, aborting...")
        exit(1)

    if not os.path.exists(config.DATA_FILE):
        print(
            f"The data file `{config.DATA_FILE}` does not exist! Make sure the"
            "path provided to `DATA_FILE` in `config.py` is correct!"
        )
        print("Cannot resolve error automatically, aborting...")
        exit(1)

    # todo: ini only check
    if not bool(config.SOURCE_DIRS): # and not config.INI_ONLY
        print(
            "No source directories specified! Please supply at least one "
            "directory to the `SOURCE_DIRS` list in `config.py`!"
        )
        print("Cannot resolve error automatically, aborting...")
        exit(1)

    if not bool(config.EXPORT_DIR):
        print(
            "No export directory specified! Please provide a valid export "
            "directory in `config.py`!"
        )
        print("Cannot resolve error automatically, aborting...")
        exit(1)
    else:
        # test access to dir
        try:
            test_path = os.path.join(config.EXPORT_DIR, "test.txt")
            with open(test_path, "w", encoding="utf-8") as f:
                f.write("Looking good!")
        except Exception as e:
            print(
                f"Encountered an error while testing the export directory: {e}"
            )
            print("Cannot resolve error automatically, aborting...")
            exit(1)

        os.remove(os.path.join(config.EXPORT_DIR, "test.txt"))

    if not bool(config.RESOURCE_TYPES):
        print(
            "No resource types specified! This may be due to an error in the " 
            "config. Please check that RESOURCE_TYPES in `config.py` has "
            "at least one value specified, or that the name is typed correctly."
        )
        print("Cannot resolve error automatically, aborting...")
        exit(1)




