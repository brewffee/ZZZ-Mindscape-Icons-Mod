# ZZZ Mindscape Icons Mod and Editor
This a is a fork of the [ZZZ Mindscape Icons Mod](https://github.com/brewffee/ZZZ-Mindscape-Icons-Mod/) that takes the base concept made by brewffee and gives it an editor and generation options. 

This mod replaces most instances of Zenless Zone Zero's agent icons with their Mindscape artworks. For the mod download,
see [releases](releases).

Included in the repository are the Python generator and a visual `editor.py` desktop tool.
Agent image properties and game texture hashes are stored in `agents.json`, source
artwork is in `sources`, and generator settings are in `config.json`.

![The agent selection screen with Mindscape icons enabled](screenshots/selection.png)

## Installation
The latest version of this mod can be found in the [releases](releases)
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
- Python 3.12
- Image processing libraries (Pillow and OpenCV):
  ```powershell
  python -m pip install -r requirements.txt
  ```
- (Optional) Real-ESRGAN for upscaling (Requires an NVIDIA GPU)
  ```powershell
  python -m pip install -r requirements-upscaler.txt
  ```

### Visual editor

```powershell
python editor.py
```

Use the editor to choose an agent and image, adjust how the image fits, then
save your changes. When you're ready, choose **Generate Mod** to create the files
for the game. If you have unsaved changes, the editor will ask whether to save
them first.

Imported artwork is automatically flipped vertically for the game. Use **Flip
Vertically** or **Flip Horizontally** beside **Choose / Import Artwork** to adjust
its orientation. Flips are saved only when you choose **Save**.

M3 and M6 images are shared across an agent's icon shapes. Chibi uses a separate
image for each shape, with its own adjustments. Check the previews before generating the mod.

Chibi artwork is automatically cleaned before resizing in both previews and
exports. Pillow uses an edge-preserving bilateral filter; Real-ESRGAN uses
[1x DeJPG OmniSR by Philip Hofmann](https://huggingface.co/Phips/1xDeJPG_OmniSR), downloaded on first
use. Cleaned and resized images are cached during the session, so moving or
rotating the same artwork does not repeat cleanup or upscaling. Original source
files and transparency are preserved. M3 and M6 are not denoised.

Agents with missing artwork appear red for the selected variant. Details are
listed in **Generation Log**, without pop-ups. Missing icons keep the game's
original artwork. In game, **Ctrl+Space** switches between M6, M3, and Chibi.

### Edit configuration

Most users can leave the settings as they are. To change them, choose **Edit
Config** in the editor. You can also edit `config.json` directly, but close the
editor first. The settings control the mod name, image variants, output folder,
and image appearance.

Choose **Apply** to save configuration changes immediately. These changes won't
trigger a save prompt when closing the editor; other unsaved edits still will.

Enable `AUTO_APPLY_DRAFT_CHANGES` to apply edited mask fields to the draft
automatically whenever the editor would otherwise ask whether to apply them.
`BACKUP_FILES` controls backups of all replaced files, including artwork, and is
enabled by default. Backups go into a `backup` subfolder beside each original file.

For sharper enlargements of small anime artwork, optionally install
`python -m pip install -r requirements-upscaler.txt` and choose
`IMAGE_UPSCALER: realesrgan` in **Edit Config**. This uses Real-ESRGAN's 4x anime
model and requires an NVIDIA GPU with a current driver; the model downloads on
first use. The default, `pillow`, needs no GPU.

### Command-line generation

```powershell
python main.py
```

This creates the mod files in the `export` folder. Copy the generated mod folder
into ZZMI's Mods folder to use it in the game.

**Warning:** By default, generating the mod deletes and recreates only the
subfolder named by `MOD_NAME` inside the output folder. Other files and folders
are kept.