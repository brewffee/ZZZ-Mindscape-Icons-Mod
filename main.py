from pathlib import Path
import os
import shutil

from config import ROOT, load_config, resolve_path


def main() -> None:
    settings = load_config()
    os.chdir(ROOT)
    # Load/validate agent data before any cleanup or mask writes.
    from editor_model import Draft
    Draft(ROOT).validate()
    from agent_data import gen_textures, create_ini, export
    from masks import gen_masks

    if settings["IMAGE_UPSCALER"] == "realesrgan":
        from upscaler import load_model
        load_model()
    export_dir: Path = resolve_path(ROOT, settings["EXPORT_DIR"])
    gen_masks()
    if settings["CLEAN_EXPORTS"]:
        mod_dir = export_dir / settings["MOD_NAME"]
        print(f"Force clean requested! Removing mod folder {mod_dir}...")
        if mod_dir.is_symlink():
            mod_dir.unlink()
        elif mod_dir.exists():
            shutil.rmtree(mod_dir)
        export_dir.mkdir(parents=True, exist_ok=True)
    gen_textures()
    create_ini()
    export()


if __name__ == "__main__":
    main()
