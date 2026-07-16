"""B4 prep: realize the LucasArts guards in the *recompilable* EricOakford source
(SCICompanion dialect: `ego`, `curRoom`, named item constants `iSunscreen`…), so
the user can compile them with SCICompanion on Windows and play the fixed game.

Reuses the same PatchSpecs the in-model realizer used (src/patch.py); only the
surface syntax differs (numeric item ids -> game.sh enum names).
"""

from __future__ import annotations

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game                               # noqa: E402
from patch import Synth                                   # noqa: E402
from patch_sci0 import wrap_newroom                       # noqa: E402

ERIC = os.path.join(os.path.dirname(__file__), "..",
                    "vendor", "sci-decomp-archive", "lsl2", "src")
OUT = os.path.join(os.path.dirname(__file__), "..", "out", "patched_ericoakford")


def item_constants(eric_src):
    """id -> constant name, parsed from game.sh's inventory enum (`iSunscreen ;9`)."""
    txt = open(os.path.join(eric_src, "game.sh"), encoding="latin-1").read()
    m = {}
    for name, num in re.findall(r"(i[A-Za-z0-9_]+)\s*;\s*(\d+)", txt):
        m[int(num)] = name
    return m


def main():
    game = load_game()
    specs = [s for s in Synth(game).patch_specs() if s["op"] == "add_guard"]
    consts = item_constants(ERIC)

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    shutil.copytree(ERIC, OUT)

    edits = []
    by_room = {}
    for s in specs:
        by_room.setdefault(s["room"], []).append(s)
    for room, gs in by_room.items():
        path = os.path.join(OUT, f"rm{room}.sc")
        if not os.path.exists(path):
            edits.append((room, "MISSING", []))
            continue
        text = open(path, encoding="latin-1").read()
        total = 0
        names_used = []
        for g in gs:
            names = [consts.get(i["id"], f"item{i['id']}") for i in g["require_items"]]
            names_used = names
            guard = "(and " + " ".join(f"(ego has: {n})" for n in names) + ")"
            text, n = wrap_newroom(text, g["newroom_target"], guard)
            total += n
        open(path, "w", encoding="latin-1").write(text)
        edits.append((room, gs[0]["newroom_target"], names_used, total))

    print(f"patched recompilable source -> {os.path.normpath(OUT)}\n")
    for room, target, names, n in edits:
        print(f"  rm{room}.sc: guarded (curRoom newRoom: {target}) x{n}")
        print(f"     require: (and {' '.join(f'(ego has: {x})' for x in names)})")
    return edits


if __name__ == "__main__":
    main()
