"""The EMISSION MANIFEST -- a committed per-file digest of every emitted patch source tree.

WHY THIS EXISTS. The snapshot surface (`snapshot.py`) freezes whether a guard landed --
`applied`, `kind`, `sites`, the skip reason -- and never one byte of the SOURCE TEXT a placement
produced. Twice in one week a shipped-emission change went through a fully green suite (the
deny-path claim: KQ5 +34 lines across 10 files; the warned-bit merge: KQ5 5 files plus KQ6's
rm660), because NO tier at any level watched the emitted source. `tools/measure_emitted_bytes.py`
makes exactly the right comparison but is manual, so it catches only what someone remembers to
run. This module gives the suite a committed reference: per game, per emitted file, a sha256 --
so `test_emission_manifest.py` FAILS, naming the game and the file, when the emission moves.

Refreshing the manifest is a BLESS, same contract as any golden: present the delta, get sign-off,
only then run `tools/bless_emission.py --write`. A pure bit RENUMBERING (freed bits shifting later
allocations) fails this manifest too, deliberately -- benign drift is still drift someone must see.

WHAT IS HASHED. Everything the emit writes or could write: `src/**` (the appliers' whole output
surface), `game.ini` (script numbering -- a chooser script joining the set moves it), and any
other root-level file EXCEPT `resource.*` volumes, which `assemble` copies verbatim from the
stock game as compiler input -- multi-megabyte stock bytes, not emission. The loose patches
(`420.SCR`-shaped) ARE hashed: they are small, and a future applier emitting one at the root
should be caught, not scoped out.

THE SAVE-COMPAT HALF. ScummVM refuses a save unless script 0's size and the game object's offset
match the values stamped at save time (`savegame.cpp:1466-1469`); the v19 KQ5 rebuild moved
0.SCR 9948->9940 under UNTOUCHED Main.sc source and silently broke every existing save. Source
hashes cannot see that -- it was compiler-codegen drift -- so the manifest also freezes the
script-0 SIZE of every installed patch dir, and the test compares both the installs and the
newest version-numbered build trees against it. That failure's message says what it means:
installing it breaks saves.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(_HERE)
MANIFEST_PATH = os.path.join(_HERE, "testdata", "emission_manifest.json")
EMIT_DIR = os.path.join(ROOT, "build", "emission_check")
PATCHED_ROOT = os.path.expanduser("~/sierra/patched")

_SCRIPT0_NAMES = ("0.scr", "script.000")


def _tool():
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    import measure_emitted_bytes
    return measure_emitted_bytes


def games():
    """The emitted-game set, owned by the emit harness so the two can never disagree."""
    return list(_tool().GAMES)


def emit_all(out_dir=EMIT_DIR):
    """Emit every game's patched source tree in `patcher.main`'s canonical order.

    Delegates to `tools/measure_emitted_bytes.emit` -- the one harness that already mirrors the
    order, `install_mode_chooser` (a feasibility gate, not decoration) included. Returns the
    tool's exit code: nonzero means at least one game emitted NOTHING, which the caller must
    treat as a failure, never a skip.

    ONE GAME PER PROCESS (2026-11-16, so the suite can run on the local 5 GB WSL VM): in one
    process the six-game emit reached 4.7 GB RSS with 199 MB free there, because memory is not
    handed back between games. A fresh interpreter per game caps the peak at the largest single
    game and also rules out any state carried from one game's emit into the next. Same tool,
    same per-game steps -- each child runs `measure_emitted_bytes.py --games <one game>`."""
    tool = os.path.join(ROOT, "tools", "measure_emitted_bytes.py")
    rc = 0
    for g in games():
        r = subprocess.run([sys.executable, tool, _HERE, out_dir, "--games", g])
        rc = rc or r.returncode
    return rc


def hash_game_tree(game_dir):
    """{relative path: sha256} for one emitted game tree; {} when the tree is absent/empty."""
    out = {}
    for dirpath, _dirs, files in os.walk(game_dir):
        for fn in files:
            if fn.lower().startswith("resource."):        # stock volume copy, not emission
                continue
            path = os.path.join(dirpath, fn)
            with open(path, "rb") as f:
                digest = hashlib.sha256(f.read()).hexdigest()
            out[os.path.relpath(path, game_dir).replace(os.sep, "/")] = digest
    return out


def build_manifest(emit_dir=EMIT_DIR):
    return {
        "games": {g: {"files": hash_game_tree(os.path.join(emit_dir, g))} for g in games()},
        "script0_installed": installed_script0(),
    }


def diff_files(old, new):
    """(changed, added, removed) relative paths, each sorted."""
    changed = sorted(k for k in set(old) & set(new) if old[k] != new[k])
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    return changed, added, removed


def _script0_size(d):
    try:
        names = os.listdir(d)
    except OSError:
        return None
    for fn in names:
        if fn.lower() in _SCRIPT0_NAMES:
            return os.path.getsize(os.path.join(d, fn))
    return None


def installed_script0():
    """{install dir name: script-0 size} for every dir under ~/sierra/patched that ships one."""
    out = {}
    if os.path.isdir(PATCHED_ROOT):
        for name in sorted(os.listdir(PATCHED_ROOT)):
            size = _script0_size(os.path.join(PATCHED_ROOT, name))
            if size is not None:
                out[name] = size
    return out


def latest_build_script0():
    """{game: (tree name, script-0 size)} from the NEWEST `build/<game>_patch_vN` tree per game.

    Reads `<tree>/patch/` only -- that is the shipping artifact; `patch_project/` holds the
    game's own stock loose patches as compiler input (KQ5's stock 0.SCR lives there, 9672
    bytes, and comparing THAT would cry wolf on every run). Trees outside the `_patch_vN`
    naming (dagger_patch_fixed, *_guardpicker) are not scanned; the installed-dir check is the
    authoritative net, this one only catches a size break BEFORE it is installed."""
    latest = {}
    if os.path.isdir(os.path.join(ROOT, "build")):
        for name in os.listdir(os.path.join(ROOT, "build")):
            m = re.match(r"^(.+)_patch_v(\d+)$", name)
            if not m:
                continue
            game, n = m.group(1).lower(), int(m.group(2))
            if game not in latest or n > latest[game][0]:
                latest[game] = (n, name)
    out = {}
    for game, (_n, name) in sorted(latest.items()):
        size = _script0_size(os.path.join(ROOT, "build", name, "patch"))
        if size is not None:
            out[game] = (name, size)
    return out


def load():
    if not os.path.exists(MANIFEST_PATH):
        return None
    with open(MANIFEST_PATH) as f:
        return json.load(f)


def save(manifest):
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=True)
        f.write("\n")
