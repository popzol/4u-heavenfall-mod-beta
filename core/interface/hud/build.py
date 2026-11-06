"""The top-screen HUD: which layouts it is made of, and the files of the HUD size mod.

The layouts were identified in the game with research/probes/hud_probe.py.
"""

import os
import re
from collections.abc import Collection, Iterator, Mapping
from pathlib import Path
from typing import Protocol

from core.app.local_config import EMULATOR_DIR_ENV
from core.game.files.arc import parse_arc, write_arc
from core.interface.hud.hint import GLYPH_ARCS, add_glyph, add_hint
from core.game.files.gui.lanl import LANL_TYPE_HASH, parse_lanl
from core.game.files.gui.lyt import LYT_TYPE_HASH, parse_lyt
from core.interface.hud.scale import NO_EDGE, Anchor, AnchorSpec, anchor_all, anchor_point, scale_hud

LANGUAGES = ("eng", "fre", "ger", "ita", "spa")
QUEST_ARC = "core_quest.arc"
# ARC in <lang>/data/ -> layout -> anchor of every root group, or {root group: anchor} (others are not scaled).
HUD_LAYOUTS: dict[str, dict[str, AnchorSpec | dict[str, AnchorSpec]]] = {
    "core_quest.arc": {
        "ui202": Anchor.TOP_LEFT,      # clock, health, stamina, sharpness, weapon gauges
        "ui203": Anchor.TOP_LEFT,      # party list
        # Hold / fishing gauges; Frenzy icon. The mount gauge (ui204_nori) needs the executable patch.
        "ui204": {"ui204_hold": Anchor.BOTTOM, "ui204_fish": Anchor.BOTTOM, "ui204_virus": Anchor.TOP_LEFT},
        "ui205": Anchor.BOTTOM_RIGHT,  # item and ammo selector
    },
    "core_common.arc": {
        "ui001": Anchor.IN_PLACE,      # prompts (climb...) and names over the characters, placed by the code
    },
}
# ARC in <lang>/data/ -> layout -> {root group: anchor} at the HUD size only in a quest. The layout is one for the
# villages, the Gathering Hall and the quests, so the file keeps these groups at full size, every pane under one null
# (`<group>_frame`, at (0, 0) and scale 1), and the executable gives that null the HUD size towards the anchor while
# the game is in a quest (code_patch.patch_talk_size, quest_frames). Only together with the executable patch.
HUD_IN_QUEST: dict[str, dict[str, dict[str, AnchorSpec]]] = {
    "core_common.arc": {
        # the talk windows (NPCs', quests'), from their bottom-left corner; not the hall's chat log (kaiwa03, chat)
        "ui005": {"ui005_kaiwa00": Anchor.BOTTOM_LEFT, "ui005_kaiwa01": Anchor.BOTTOM_LEFT,
                  "ui005_kaiwa02": Anchor.BOTTOM_LEFT, "ui005_kaiwa04": Anchor.BOTTOM_LEFT},
    },
}
# ARC in <lang>/data/ -> layout -> root groups whose panes the game's code positions every frame in the file's own
# units (states of the HUD: the Charge Blade's phials write y -2 to their nulls and x to the shield, the bowgun's
# ammunition writes x / y to its nulls, the reload icons write theirs). Each is scaled as one: every pane keeps the
# file's numbers under one null (`<group>_frame`, the name the executable's first-pane rule knows) that takes the
# factor, so what the code writes is scaled with it instead of landing in the unscaled units.
HUD_WRAPPED: dict[str, dict[str, tuple[str, ...]]] = {
    "core_quest.arc": {
        "ui202": ("ui202_mushi", "ui202_aucher00", "ui202_slash_axe", "ui202_souken", "ui202_tati", "ui202_bowgun00",
                  "ui202_bowgun01", "ui202_hue", "ui202_gunlance", "ui202_guard_axe", "ui202_reload",
                  "ui202_tamakazu30", "ui202_b_tama", "ui202_a_bin", "ui202_panel_bin", "ui202_panel_tama"),
    },
}
FRAME_SUFFIX = "_frame"
# ARC in <lang>/data/ -> layout -> nulls of the file that take the factor as their scale while what is under them keeps
# the file's numbers (scale_hud's `unscaled`), for panes whose size the code writes every frame in the file's units:
# the item selector's icons, whose timer bar (the Wystone's) gets its height from the code.
HUD_SCALED_NULLS: dict[str, dict[str, tuple[str, ...]]] = {
    "core_quest.arc": {
        "ui205": tuple(f"ui205_icon0{i}" for i in range(5)),
    },
}
# One per area and language (164 each). The code moves the whole map layout; it is drawn as if the map's
# 128x128 frame started at the screen's top-left corner, so its top-right corner is at (72, 120).
# Only together with the executable patch (code_patch.patch_hud): the code places the map icons.
MAP_ARC = re.compile(r"m\d\d(a\d\d)?_map\d?\.arc")
MINIMAP_ANCHOR = (72.0, 120.0)
# Also only with the executable patch, which fixes what the code places: the map icons (they only change size)
# and the mount gauge (its monster face).
CODE_PATCH_LAYOUTS: dict[str, dict[str, AnchorSpec | dict[str, AnchorSpec]]] = {
    "core_quest.arc": {"ui250": Anchor.IN_PLACE, "ui204": {"ui204_nori": Anchor.BOTTOM}},
}


def layouts_of(arc_name: str, with_code_patch: bool) -> dict[str, AnchorSpec | dict[str, AnchorSpec]]:
    """HUD_LAYOUTS of an ARC, plus CODE_PATCH_LAYOUTS when the executable is patched too."""
    layouts = dict(HUD_LAYOUTS.get(arc_name, {}))
    for name, anchor in (CODE_PATCH_LAYOUTS.get(arc_name, {}) if with_code_patch else {}).items():
        current = layouts.get(name)
        layouts[name] = {**current, **anchor} if isinstance(current, dict) and isinstance(anchor, dict) else anchor
    return layouts

UPDATE_TITLE_ID = "0004000e00126100"
# Emulators keep installed titles decrypted on their virtual SD card:
# <user folder>/<emulator>/sdmc/Nintendo 3DS/<id>/<id>/title/0004000e/00126100/content/00000000.app
EMULATORS = ("Citra", "Azahar", "Lime3DS", "citra-emu", "azahar-emu", "lime3ds-emu")
UPDATE_CONTENT = Path("title") / "0004000e" / "00126100" / "content" / "00000000.app"


class GameFiles(Protocol):
    """A RomFS (core.game.executable.romfs.RomFS) or anything else with the same two methods."""
    def read(self, path: str) -> bytes: ...
    def walk(self) -> Iterator[str]: ...


def short_name(entry_name: str) -> str:
    return entry_name.split("\\")[-1]


def quest_frames(factor: float) -> list[tuple[str, str, float, float, float]]:
    """(group, its null, the null's x, y and scale in a quest) of every HUD_IN_QUEST group: the place scale_hud gives
    a null right under the group, anchor + (0 - anchor) * factor."""
    frames = []
    for layouts in HUD_IN_QUEST.values():
        for groups in layouts.values():
            for group, anchor in groups.items():
                x, y = anchor_point(anchor) or (0.0, 0.0)
                frames.append((group, group + FRAME_SUFFIX, x * (1 - factor), y * (1 - factor), factor))
    return frames


def scale_arc(raw: bytes, layouts: Mapping[str, AnchorSpec | Mapping[str, AnchorSpec]], factor: float,
              wrapped: Mapping[str, Collection[str]] | None = None,
              in_quest: Mapping[str, Mapping[str, AnchorSpec]] | None = None,
              scaled_nulls: Mapping[str, Collection[str]] | None = None,
              edge: tuple[float, float] = NO_EDGE) -> bytes:
    """The ARC with the given layouts scaled, together with every animation of the ARC that moves them. `wrapped`:
    layout -> root groups (HUD_WRAPPED) that scale as one null instead of pane by pane. `in_quest`: layout -> root
    groups (HUD_IN_QUEST) left at full size under one null each, which the executable scales in a quest.
    `scaled_nulls`: layout -> nulls of the file (HUD_SCALED_NULLS) that take the factor as their scale and leave what
    is under them as the file has it. `edge`: the interface's size against the game's (scale.py)."""
    arc = parse_arc(raw)
    entries = {short_name(e.name): e for e in arc.entries if e.type_hash == LYT_TYPE_HASH}
    animation_entries = [e for e in arc.entries if e.type_hash == LANL_TYPE_HASH]
    animations = [parse_lanl(e.data) for e in animation_entries]
    for name in dict.fromkeys([*layouts, *(in_quest or {})]):
        if name not in entries:
            raise KeyError(f"no layout named {name}")
        layout = parse_lyt(entries[name].data)
        for group in (in_quest or {}).get(name, ()):
            layout.wrap_children(layout.find(group), group + FRAME_SUFFIX, layout.plain_null())
        if name in layouts:
            anchor = layouts[name]
            anchors = anchor if isinstance(anchor, Mapping) else anchor_all(layout, anchor)
            frames = []
            for group in (wrapped or {}).get(name, ()):
                frames.append(group + FRAME_SUFFIX)
                layout.wrap_children(layout.find(group), frames[-1], layout.plain_null())
            scale_hud(layout, animations, factor, anchors, [*frames, *(scaled_nulls or {}).get(name, ())], edge)
        entries[name].data = layout.to_bytes()
    for entry, file in zip(animation_entries, animations):
        entry.data = file.to_bytes()
    return write_arc(arc)


def glyph_files(rom: GameFiles) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of the other copies of the hint's texture (hint.GLYPH_ARCS but core_quest)."""
    for lang in LANGUAGES:
        for arc_name in GLYPH_ARCS:
            if arc_name != QUEST_ARC:
                path = f"{lang}/data/{arc_name}"
                yield path, add_glyph(rom.read(path))


def hint_files(rom: GameFiles) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of the quest HUD of each language with only the target switch hint (hint.py), and
    the other copies of its texture."""
    for lang in LANGUAGES:
        path = f"{lang}/data/{QUEST_ARC}"
        yield path, add_hint(rom.read(path))
    yield from glyph_files(rom)


def hud_files(rom: GameFiles, factor: float,
              with_code_patch: bool = False, target_hint: bool = False,
              edge: tuple[float, float] = NO_EDGE) -> Iterator[tuple[str, bytes]]:
    """(RomFS path, new ARC) of every file of the HUD size mod, for the 5 languages, all from the base game's
    copies (`rom`: the mod runs the base game's code and ships its data).
    `with_code_patch` adds the minimap and the mount gauge: only together with code_patch.patch_hud in the
    executable. `target_hint` adds the target switch hint to the item selector, which then shrinks with it, and
    the other copies of its texture. `edge` keeps the HUD at the edges of a picture of another shape, at any `factor`.
    At full size nothing needs that patch: the mount gauge moves, the map and the talk windows stay the game's (the
    executable moves the map, cheats/aspect_ratio.py)."""
    smaller = factor < 1
    map_paths = [p for p in rom.walk() if p.split("/")[0] in LANGUAGES
                 and MAP_ARC.fullmatch(p.split("/")[-1])] if with_code_patch and smaller else []
    if target_hint:
        yield from glyph_files(rom)
    for lang in LANGUAGES:
        for arc_name in HUD_LAYOUTS:
            path = f"{lang}/data/{arc_name}"
            raw = rom.read(path)
            if target_hint and arc_name == QUEST_ARC:
                raw = add_hint(raw)
            yield path, scale_arc(raw, layouts_of(arc_name, with_code_patch or not smaller), factor,
                                  HUD_WRAPPED.get(arc_name),
                                  HUD_IN_QUEST.get(arc_name) if with_code_patch and smaller else None,
                                  HUD_SCALED_NULLS.get(arc_name), edge)
        for path in map_paths:
            if path.startswith(lang + "/"):
                raw = rom.read(path)
                names = [short_name(e.name) for e in parse_arc(raw).entries if e.type_hash == LYT_TYPE_HASH]
                yield path, scale_arc(raw, {name: MINIMAP_ANCHOR for name in names}, factor)


def emulator_folders() -> list[Path]:
    """User folders where Citra and its forks keep their data (Windows, Linux, macOS).

    If the environment variable HEAVENFALL_EMULATOR_DIR is set, that folder is the only one offered (an AppImage,
    a portable copy, any place the program cannot guess). Otherwise: the usual folders of each system, and on
    Linux the data folders of Flatpak installs (~/.var/app/<app id>/data/<emulator>)."""
    override = os.environ.get(EMULATOR_DIR_ENV)
    if override:
        return [Path(override).expanduser()]
    bases = [Path(os.environ[var]) for var in ("APPDATA", "XDG_DATA_HOME") if os.environ.get(var)]
    bases += [Path.home() / ".local" / "share", Path.home() / "Library" / "Application Support"]
    folders = [base / name for base in bases for name in EMULATORS]
    flatpak = Path.home() / ".var" / "app"
    folders += [path for name in EMULATORS for path in sorted(flatpak.glob(f"*/data/{name}"))]
    return folders


def find_update() -> Path | None:
    """The update's 00000000.app installed in an emulator, if any: for research tools that build from it on
    purpose (research/probes/port_probe.py update_app); a run never looks for it."""
    for folder in emulator_folders():
        sd_card = folder / "sdmc" / "Nintendo 3DS"
        if sd_card.is_dir():
            for path in sorted(sd_card.glob("*/*/" + UPDATE_CONTENT.as_posix())):
                if path.is_file():
                    return path
    return None


def hud_paths(mod_dir: Path) -> list[Path]:
    """Every file the HUD size mod can leave in a mod folder (core ARCs, the hint's texture copies and the map
    ARCs)."""
    paths = []
    for lang in LANGUAGES:
        folder = Path(mod_dir) / "romfs" / lang / "data"
        paths += [folder / name for name in dict.fromkeys([*HUD_LAYOUTS, *GLYPH_ARCS])]
        if folder.is_dir():
            paths += [p for p in folder.iterdir() if MAP_ARC.fullmatch(p.name)]
    return paths


def remove_hud_files(mod_dir: Path) -> None:
    for path in hud_paths(mod_dir):
        path.unlink(missing_ok=True)


def write_hud_files(mod_dir: Path, rom: GameFiles, factor: float,
                    with_code_patch: bool = False, target_hint: bool = False) -> list[Path]:
    """Write the HUD size mod into a mod folder (romfs/<lang>/data/...). Files of an earlier run are replaced.
    See hud_files() for `with_code_patch` and `target_hint`."""
    remove_hud_files(mod_dir)
    written = []
    for path, data in hud_files(rom, factor, with_code_patch, target_hint):
        target = Path(mod_dir) / "romfs" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(target)
    return written
