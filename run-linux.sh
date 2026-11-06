#!/usr/bin/env bash
# Starts Heavenfall Beta on Linux from the source folder (see LINUX.md).
# The first run creates .venv and installs requirements.txt into it; later runs start the program right away.
# .venv only counts as ready once the install has finished (.venv/.deps-ok holds the hash of the requirements.txt
# it was made from), so a failed or interrupted install never leaves a folder that later launches trust.

set -u
cd "$(dirname "$(readlink -f "$0")")" || exit 1

VENV=.venv
MARK="$VENV/.deps-ok"

find_python() {
    local candidate
    for candidate in python3 python; do
        if command -v "$candidate" >/dev/null 2>&1 \
            && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
            echo "$candidate"
            return 0
        fi
    done
    return 1
}

wanted_hash() {
    sha256sum requirements.txt | cut -d' ' -f1
}

ready() {
    [ -x "$VENV/bin/python" ] && [ -f "$MARK" ] && [ "$(cat "$MARK")" = "$(wanted_hash)" ]
}

fail_install() {
    rm -rf "$VENV"
    echo >&2
    echo "Heavenfall Beta: the installation failed, so $VENV was removed and the next start will try again." >&2
    echo "$1" >&2
    exit 1
}

if ! ready; then
    PYTHON=$(find_python) || {
        echo "Heavenfall Beta needs Python 3.10 or newer, and none was found. Install it with your package manager." >&2
        exit 1
    }
    # Ctrl+C in the middle of the install must not leave a half-made .venv behind either.
    trap 'rm -rf "$VENV"; echo >&2; echo "Interrupted: $VENV removed." >&2; exit 130' INT TERM
    rm -rf "$VENV"
    echo "Setting up $VENV (first run only)..."
    "$PYTHON" -m venv "$VENV" \
        || fail_install "Could not create a virtual environment. On Debian/Ubuntu: sudo apt install python3-venv"
    "$VENV/bin/python" -m pip install -r requirements.txt \
        || fail_install "pip could not install requirements.txt (no network, or a Python version the pinned packages do not support; they are tested on Python 3.13)."
    wanted_hash > "$MARK" || fail_install "Could not write $MARK."
    trap - INT TERM
fi

exec "$VENV/bin/python" -m core.gui "$@"
