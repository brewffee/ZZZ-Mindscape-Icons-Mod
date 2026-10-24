import json
import shutil
from copy import deepcopy
from pathlib import Path

from PIL import Image

from config import DEFAULTS, ROOT


def entry(hash_value="1234abcd"):
    return {"hash": hash_value, "offset": [0, 0], "scale": 0.7, "rotation": 0}


def project(root: Path, scripts=False):
    settings = deepcopy(DEFAULTS)
    settings["SOURCE_DIRS"] = ["sources/M6", "sources/M3"]
    (root / "config.json").write_text(json.dumps(settings), encoding="utf-8")
    (root / "agents.json").write_text(
        json.dumps({"Alice": [{"select": entry(), "tab": entry("2345bcde"), "round": entry("3456cdef")}]}),
        encoding="utf-8",
    )
    for variant in ("M6", "M3"):
        directory = root / "sources" / variant
        directory.mkdir(parents=True)
        Image.new("RGBA", (80, 90), (170, 80, 30, 185)).save(directory / "Alice.png")
    if scripts:
        for name in ("main.py", "config.py", "agent_data.py", "textures.py", "masks.py",
                     "upscaler.py", "editor_model.py", "editor.py"):
            shutil.copy2(ROOT / name, root / name)
    return settings
