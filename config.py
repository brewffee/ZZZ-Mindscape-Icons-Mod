"""Validated JSON settings; existing generator constant imports remain supported."""

from __future__ import annotations

import json
import math
import re
import warnings
from copy import deepcopy
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard, TypedDict, cast

from upscaler import Upscaler

ROOT = Path(__file__).resolve().parent


class Settings(TypedDict):
    MOD_NAME: str
    MOD_VERSION: str
    CUR_AGENT: str | None
    SOURCE_DIRS: list[str]
    EXPORT_DIR: str
    FALLBACK_MODE: str
    CLEAN_EXPORTS: bool
    SEPARATE_INIS: bool
    AUTO_APPLY_DRAFT_CHANGES: bool
    BACKUP_FILES: bool
    CONTRAST_MULTIPLIER: float
    SATURATION_MULTIPLIER: float
    IMAGE_UPSCALER: Upscaler


DEFAULTS: Settings = {
    "MOD_NAME": "Mindscape Icons",
    "MOD_VERSION": "3.3",
    "CUR_AGENT": None,
    "SOURCE_DIRS": ["sources/M6", "sources/M3", "sources/Chibi"],
    "EXPORT_DIR": "export",
    "FALLBACK_MODE": "original",
    "CLEAN_EXPORTS": True,
    "SEPARATE_INIS": True,
    "AUTO_APPLY_DRAFT_CHANGES": False,
    "BACKUP_FILES": True,
    "CONTRAST_MULTIPLIER": 1.0,
    "SATURATION_MULTIPLIER": 1.2,
    "IMAGE_UPSCALER": "pillow",
}


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_object)
    except (ValueError, OSError) as exc:
        raise ValueError(f"{path}: {exc}") from exc


def safe_component(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a nonempty string.")
    if re.search(r'[<>:"/\\|?*\x00-\x1f\[\];=]', value) or value.endswith((" ", ".")):
        raise ValueError(f"{label} contains unsafe filename/INI characters.")
    if value in (".", "..") or re.fullmatch(
        r"(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value
    ):
        raise ValueError(f"{label} is a reserved filename.")
    return value


def resolve_path(root: Path, value: str) -> Path:
    return (root / value).resolve()


def overlaps(a: Path, b: Path) -> bool:
    return a == b or a in b.parents or b in a.parents


def finite_number(value: object) -> TypeGuard[int | float]:
    if type(value) not in (int, float):
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def validate_settings(value: object, root: Path = ROOT) -> Settings:
    if not isinstance(value, dict) or set(value) != set(DEFAULTS):
        keys = set(value) if isinstance(value, dict) else set()
        raise ValueError(
            f"Configuration keys: missing {sorted(set(DEFAULTS) - keys)}, "
            f"unknown {sorted(keys - set(DEFAULTS))}."
        )
    for key in ("MOD_NAME", "MOD_VERSION"):
        safe_component(value[key], key)
    if value["CUR_AGENT"] is not None and not isinstance(value["CUR_AGENT"], str):
        raise ValueError("CUR_AGENT must be an agent name or null.")
    for key in (
        "CLEAN_EXPORTS", "SEPARATE_INIS", "AUTO_APPLY_DRAFT_CHANGES", "BACKUP_FILES",
    ):
        if type(value[key]) is not bool:
            raise ValueError(f"{key} must be true or false.")
    for key in ("CONTRAST_MULTIPLIER", "SATURATION_MULTIPLIER"):
        number = value[key]
        if not finite_number(number) or number < 0:
            raise ValueError(f"{key} must be a finite nonnegative number.")
    if value["FALLBACK_MODE"] not in ("original", "skip"):
        raise ValueError("FALLBACK_MODE must be original or skip.")
    if value["IMAGE_UPSCALER"] not in ("pillow", "realesrgan"):
        raise ValueError("IMAGE_UPSCALER must be pillow or realesrgan.")
    sources = value["SOURCE_DIRS"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("SOURCE_DIRS must be a nonempty ordered list of directories.")
    resolved: list[Path] = []
    variants: set[str] = set()
    for source in sources:
        if not isinstance(source, str) or not source.strip():
            raise ValueError("Each source directory must be a nonempty path.")
        path = resolve_path(root, source)
        variant = "" if path.name == "sources" else safe_component(path.name, "Variant")
        if path in resolved or variant.casefold() in variants:
            raise ValueError(f"Duplicate source directory or variant name: {source}")
        if path.exists() and not path.is_dir():
            raise ValueError(f"Source is not a directory: {path}")
        # Sources may be external, but may not point into generated/protected data.
        for protected in (root / ".git", root / ".github", root / "masks"):
            if overlaps(path, protected.resolve()):
                raise ValueError(f"Source overlaps protected project data: {path}")
        resolved.append(path)
        variants.add(variant.casefold())
    export = value["EXPORT_DIR"]
    if not isinstance(export, str) or not export.strip():
        raise ValueError("EXPORT_DIR must be a nonempty directory path.")
    target = resolve_path(root, export)
    root = root.resolve()
    if target.exists() and not target.is_dir():
        raise ValueError(f"Export path is not a directory: {target}")
    if target == Path(target.anchor) or overlaps(target, Path.home().resolve()):
        # A normal repository is often inside the user's home; descendants are
        # permitted except the home itself and its ancestors.
        home = Path.home().resolve()
        if target == Path(target.anchor) or target == home or target in home.parents:
            raise ValueError(f"Unsafe export directory: {target}")
    if target == root or target in root.parents:
        raise ValueError(f"Export directory would contain the repository: {target}")
    protected_paths = [
        root / ".git", root / ".github", root / "masks", root / "screenshots",
        root / "sources", root / "tests", root / "models", root / "backup",
        *resolved,
        *(root / name for name in (
            "agents.json", "agents-chibi.json", "config.json", "config.py", "editor.py", "editor_model.py",
            "main.py", "agent_data.py", "textures.py", "masks.py", "upscaler.py",
            "requirements.txt", "requirements-upscaler.txt", "README.md",
        )),
    ]
    if any(overlaps(target, path.resolve()) for path in protected_paths):
        raise ValueError(f"Export directory overlaps project inputs: {target}")
    return cast(Settings, deepcopy(value))


def load_config(root: Path = ROOT) -> Settings:
    path = root / "config.json"
    if not path.exists():
        warnings.warn(f"{path} is missing; using built-in defaults.", stacklevel=2)
        return validate_settings(deepcopy(DEFAULTS), root)
    value = read_json(path)
    # Older saved configurations predate these optional settings.
    if isinstance(value, dict):
        if "BACKUP_JSON_FILES" in value:
            if "BACKUP_FILES" in value:
                raise ValueError("Use only BACKUP_FILES; remove the old BACKUP_JSON_FILES setting.")
            value["BACKUP_FILES"] = value.pop("BACKUP_JSON_FILES")
        for key in ("IMAGE_UPSCALER", "AUTO_APPLY_DRAFT_CHANGES", "BACKUP_FILES"):
            if key not in value:
                value[key] = DEFAULTS[key]
    return validate_settings(value, root)


def archive_name(settings: Settings) -> str:
    return (
        settings["MOD_NAME"].lower().replace(" ", "_")
        + "_v" + settings["MOD_VERSION"] + ".zip"
    )


# Defer generator settings until a legacy constant is requested. The editor can
# import validation helpers even when config.json needs correction.
_generator_settings: Settings | None = None


def __getattr__(name: str) -> object:
    global _generator_settings
    if name not in DEFAULTS:
        raise AttributeError(name)
    if _generator_settings is None:
        _generator_settings = load_config()
    return _generator_settings[name]


if TYPE_CHECKING:
    MOD_NAME: str
    MOD_VERSION: str
    CUR_AGENT: str | None
    SOURCE_DIRS: list[str]
    EXPORT_DIR: str
    FALLBACK_MODE: str
    CLEAN_EXPORTS: bool
    SEPARATE_INIS: bool
    CONTRAST_MULTIPLIER: float
    SATURATION_MULTIPLIER: float
    IMAGE_UPSCALER: Upscaler
