# Running Heavenfall Beta on Linux

This page covers running the program from the source folder on a Linux desktop. You still need your own decrypted
copy of Monster Hunter 4 Ultimate and the Azahar emulator, as described in the [README](README.md).

> **Steam Deck and Android:** use the [web installer](README.md#the-web-installer) instead. It needs nothing installed.

## Quick start

You need Python 3.10 or newer (the pinned packages are tested on Python 3.13). In the extracted source folder, run:

```bash
./run-linux.sh
```

The first run creates a `.venv` folder and installs everything in `requirements.txt` into it. Later runs start the
program right away. If the installation fails or is interrupted, `.venv` is deleted, so the next run tries again from
scratch instead of crashing. If `requirements.txt` changes (for example after an update), the packages are installed
again automatically.

If you prefer to do it by hand, the same thing is:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m core.gui
```

## Where the program looks for your emulator

The program lists every emulator user folder it can find and installs the mod into the one you choose. On Linux it
looks, in this order, in:

1. `$XDG_DATA_HOME/<emulator>` and `~/.local/share/<emulator>`: a normal (native) install.
2. `~/.var/app/<app id>/data/<emulator>`: a Flatpak install.

`<emulator>` is one of `azahar-emu`, `lime3ds-emu`, `citra-emu` (or the capitalised `Azahar`, `Lime3DS`, `Citra`).

### Other installs (AppImage, portable copies, custom locations)

An AppImage or a portable copy keeps its data in a place the program cannot guess, so it is **not** detected
automatically. You have two options:

- Click **Choose folder…** in the program and select the emulator's user folder (the one that contains `load`,
  `sdmc`, `config`...). In Azahar you can open it with **File > Open Azahar Folder > User Folder**.
- Set the `HEAVENFALL_EMULATOR_DIR` environment variable to that folder before starting:

  ```bash
  HEAVENFALL_EMULATOR_DIR="$HOME/Games/azahar/user" ./run-linux.sh
  ```

  When this variable is set, it is the only folder the program offers (nothing else is searched). If the folder does
  not exist, the program says that no emulator was found. The same variable also sets the default `emulator_dir`
  for the developer tools (`local.ini`).

## Troubleshooting

- **`Could not create a virtual environment`:** on Debian and Ubuntu, install the venv module:
  `sudo apt install python3-venv`.
- **`pip could not install requirements.txt`:** check your network connection. The pinned versions are tested on
  Python 3.13; with an older Python, the install can fail because a pinned package has no build for it.
- **The window does not open and the error mentions the Qt `xcb` platform plugin:** a system library is usually
  missing. On Debian and Ubuntu, `sudo apt install libxcb-cursor0` is the common fix.
- **No emulator found:** use **Choose folder…** or `HEAVENFALL_EMULATOR_DIR`, as described above.
- **Start from a clean state:** delete the `.venv` folder and run `./run-linux.sh` again.
