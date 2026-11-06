"""Where this machine keeps the game files and tools (local.ini), for tests and tools.

local.ini is never committed (template: local.example.ini; `python tools/build/setup_local.py` writes and
checks it). One file serves every worktree: it is looked for in the checkout, then in the main
checkout of a git worktree. Relative paths in it are relative to the file. Environment variables set
by hand always win over it: `export_env` only fills the ones that are unset.
"""

import configparser
import os
from dataclasses import dataclass, field
from pathlib import Path

FILE_NAME = "local.ini"
CONFIG_ENV = "MH4U_LOCAL_CONFIG"
# The emulator's user folder, for an install the program cannot find by itself (an AppImage, a portable copy...).
EMULATOR_DIR_ENV = "HEAVENFALL_EMULATOR_DIR"
SECTION = "paths"
CHECKOUT = Path(__file__).resolve().parents[2]

KEYS = {
    "mh4u_rom": "decrypted EUR .3ds of MH4U",
    "mh4u_update": "decrypted update content 00000000.app of MH4U",
    "mh4u_romfs": "RomFS dump folder of MH4U (optional: setup_local.py --extract --romfs makes one)",
    "mhgen_rom": "decrypted EUR .3ds of MH Generations",
    "mhgen_romfs": "RomFS dump folder of MH Generations (optional: setup_local.py --extract --romfs)",
    "mh4u_rom_usa": "decrypted USA .3ds of MH4U (0004000000126300; version maps)",
    "mh4u_update_usa": "decrypted USA update content of MH4U (0004000E00126300)",
    "mhgen_rom_usa": "decrypted USA .3ds of MH Generations (0004000000187000)",
    "arm_toolchain": "bin folder of devkitARM or the Arm GNU Toolchain",
    "ghidra": "Ghidra install folder (the one with support/analyzeHeadless.bat)",
    "ghidra_projects": "folder of the Ghidra projects (default <work_dir>/ghidra)",
    "jdk": "JDK 21 folder, used as JAVA_HOME for Ghidra",
    "emulator_dir": "Azahar/Citra user folder (default $HEAVENFALL_EMULATOR_DIR, else %APPDATA%/Azahar)",
    "work_dir": "derived inputs and scratch (default work/ in the main checkout)",
    "beta_repo": "Heavenfall Beta's repository (tools/release/export_edition.py; default ../4u-heavenfall-mod-beta "
                 "beside the main checkout)",
}

# Files setup_local.py --extract derives from the ROMs, under <work_dir>/inputs.
INPUTS = {
    "code_update": "code_update.bin",
    "code": "code.bin",
    "quest": "quest",
    "mhgen_code": "mhgen_code.bin",
    "romfs": "romfs",
    "mhgen_romfs": "mhgen_romfs",
    "code_usa": "code_usa.bin",
    "code_usa_update": "code_usa_update.bin",
    "mhgen_usa_code": "mhgen_usa_code.bin",
}


@dataclass
class LocalConfig:
    path: Path | None
    main: Path
    values: dict[str, Path] = field(default_factory=dict)

    def get(self, key: str) -> Path | None:
        if key not in KEYS:
            raise KeyError(key)
        if key in self.values:
            return self.values[key]
        if key == "work_dir":
            return self.main / "work"
        if key == "ghidra_projects":
            return self.work_dir / "ghidra"
        if key == "emulator_dir":
            if os.environ.get(EMULATOR_DIR_ENV):
                return Path(os.environ[EMULATOR_DIR_ENV]).expanduser()
            if os.environ.get("APPDATA"):
                return Path(os.environ["APPDATA"]) / "Azahar"
        return None

    @property
    def work_dir(self) -> Path:
        return self.get("work_dir")

    @property
    def inputs(self) -> Path:
        return self.work_dir / "inputs"

    @property
    def romfs_dir(self) -> Path:
        """MH4U's RomFS: the configured dump, else the one setup_local.py --extract --romfs makes."""
        return self.get("mh4u_romfs") or self.input("romfs")

    def input(self, name: str) -> Path:
        return self.inputs / INPUTS[name]


def main_checkout(checkout: Path = CHECKOUT) -> Path:
    """The main checkout of `checkout`: itself, or for a git worktree the one that owns its .git."""
    checkout = Path(checkout).resolve()
    dot_git = checkout / ".git"
    if not dot_git.is_file():
        return checkout
    text = dot_git.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        return checkout
    gitdir = Path(text[len("gitdir:"):].strip())
    if not gitdir.is_absolute():
        gitdir = checkout / gitdir
    commondir = gitdir / "commondir"
    common = gitdir / commondir.read_text(encoding="utf-8").strip() if commondir.is_file() else gitdir
    return common.resolve().parent


def config_path(checkout: Path = CHECKOUT, environ=os.environ) -> Path | None:
    if environ.get(CONFIG_ENV):
        return Path(environ[CONFIG_ENV])
    for folder in (Path(checkout), main_checkout(checkout)):
        if (folder / FILE_NAME).is_file():
            return folder / FILE_NAME
    return None


def _parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(interpolation=None)


def load(checkout: Path = CHECKOUT, environ=os.environ) -> LocalConfig:
    path = config_path(checkout, environ)
    config = LocalConfig(path=path, main=main_checkout(checkout))
    if path is None or not path.is_file():
        return config
    parser = _parser()
    parser.read(path, encoding="utf-8")
    if parser.has_section(SECTION):
        for key, value in parser.items(SECTION):
            if key in KEYS and value.strip():
                expanded = Path(os.path.expanduser(os.path.expandvars(value.strip())))
                config.values[key] = (path.parent / expanded).resolve()
    return config


def write(path: Path, values: dict[str, str]) -> None:
    """Set `values` in local.ini at `path`, keeping its other keys."""
    unknown = set(values) - set(KEYS)
    if unknown:
        raise KeyError(f"unknown keys: {', '.join(sorted(unknown))} (known: {', '.join(KEYS)})")
    parser = _parser()
    if path.is_file():
        parser.read(path, encoding="utf-8")
    if not parser.has_section(SECTION):
        parser.add_section(SECTION)
    for key, value in values.items():
        parser.set(SECTION, key, str(value))
    with path.open("w", encoding="utf-8") as f:
        parser.write(f)


def _first_existing(*paths: Path | None) -> Path | None:
    return next((p for p in paths if p is not None and p.exists()), None)


def env_values(config: LocalConfig) -> dict[str, Path]:
    """The environment variables the tests and tools read, with the paths of this machine that exist."""
    candidates = {
        "MH4U_ROM": _first_existing(config.get("mh4u_rom")),
        "MH4U_UPDATE_APP": _first_existing(config.get("mh4u_update")),
        "MH4U_ROMFS_DIR": _first_existing(config.get("mh4u_romfs"), config.input("romfs")),
        "MH4U_CODE_BIN": _first_existing(config.input("code_update")),
        "MH4U_QUEST_DIR": _first_existing(config.input("quest")),
        "MH4U_SAVES_DIR": _first_existing(config.work_dir / "saves"),
        "MHGEN_ROM": _first_existing(config.get("mhgen_rom")),
        "MHGEN_ROMFS": _first_existing(config.get("mhgen_romfs"), config.input("mhgen_romfs")),
        "MHGEN_CODE_BIN": _first_existing(config.input("mhgen_code")),
        "MH4U_USA_ROM": _first_existing(config.get("mh4u_rom_usa")),
        "MH4U_USA_CODE_BIN": _first_existing(config.input("code_usa")),
        "MH4U_USA_UPDATE_CODE_BIN": _first_existing(config.input("code_usa_update")),
        "MH4U_USA_UPDATE_APP": _first_existing(config.get("mh4u_update_usa")),
        "MHGEN_USA_ROM": _first_existing(config.get("mhgen_rom_usa")),
        "MHGEN_USA_CODE_BIN": _first_existing(config.input("mhgen_usa_code")),
        "ARM_TOOLCHAIN": _first_existing(config.get("arm_toolchain")),
    }
    return {name: path for name, path in candidates.items() if path is not None}


def export_env(checkout: Path = CHECKOUT, environ=os.environ) -> dict[str, str]:
    """Fill the unset variables of `env_values` into `environ`; returns what was set."""
    exported = {}
    for name, path in env_values(load(checkout, environ)).items():
        if not environ.get(name):
            environ[name] = exported[name] = str(path)
    return exported


def arm_toolchain(checkout: Path = CHECKOUT, environ=os.environ) -> Path | None:
    """The assembler's bin folder: ARM_TOOLCHAIN, else local.ini's arm_toolchain."""
    if environ.get("ARM_TOOLCHAIN"):
        return Path(environ["ARM_TOOLCHAIN"])
    return load(checkout, environ).values.get("arm_toolchain")
