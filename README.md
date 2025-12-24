# ZZZ Mindscape Icons Mod
This mod replaces most instances of Zenless Zone Zero's agent icons with their Mindscape artworks. For the mod download,
see [releases](https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod/releases).

Included in the repository is the python tool used to generate the mod content. Agent image properties and hashes can be
found and configured in the `agents.json` file, and source images can be found in the `mindscapes` folder.

![The agent selection screen with Mindscape icons enabled](screenshots/selection.png)

## Installation
The latest version of this mod can be found in the [releases](https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod/releases) 
page.

## Screenshots
| ![Overworld](screenshots/overworld.png) | ![Chain Attack](screenshots/chain.png) |
|:---------------------------------------:|:--------------------------------------:|
|              **Overworld**              |            **Chain Attack**            |

| ![Selection Tabs](screenshots/tabs.png) |
|:---------------------------------------:|
|        **Agent Selection Tabs**         |

## Building
### Prerequisites
- Python 3.12 and the [Pillow](https://pypi.org/project/pillow/) library (`pip install Pillow`)

### Usage
- Run `main.py` to generate mod content. The project folder can then be imported into the ZZMI Mods folder for use 
in-game.
  - If you only want to update a single agent, edit the `CUR_AGENT` variable in `main.py` to the desured agent's name.
  - If you want to use a different image for an agent's skin art, you can add a new file in the `mindscapes` folder with
  the format `<Agent>Skin.png`, `<Agent>Skin2.png`, etc.

## Planned Features
I plan to support additional sections in the future, including:
- [ ] Character Selection screen portraits
- [ ] Agent Trust screen icons
- [ ] Agent Display portraits
- [ ] Preset Config icons

If you have the hashes for these, please let me know by creating an [issue](https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod/issues/new)!!!