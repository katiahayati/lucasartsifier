"""B2: SCI0 source realizer -- apply PatchSpecs to the decompiled scripts.

For an `add_guard` spec we wrap the room's `(RECEIVER newRoom: TARGET)` call in the
LucasArts guard, so the irreversible crossing is only permitted once the player
holds the resources that would otherwise be stranded:

    (if (and (gEgo has: 5) (gEgo has: 8) (gEgo has: 9))
        (gCurRoom newRoom: 27)
    else
        (NotNow)          ; softlock-guard: fetch what you need first
    )

Produces a full copy of the source tree under out/patched_src/ with the affected
rooms edited, leaving the originals untouched.
"""

from __future__ import annotations

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config                                             # noqa: E402
from patch import Synth                                   # noqa: E402
from model import load_game                               # noqa: E402

OUT = os.path.join(os.path.dirname(__file__), "..", "out", "patched_src")


def wrap_newroom(text, target, guard_sexpr):
    """Wrap every `(RECV newRoom: target)` send in the LucasArts guard.
    newRoom targets here are literal ints, so the send has no inner parens."""
    pat = re.compile(r"\([^()]*newRoom:\s*" + str(target) + r"\b[^()]*\)")
    n = 0

    def repl(m):
        nonlocal n
        n += 1
        send = m.group(0)
        return (f"(if {guard_sexpr}\n\t\t\t\t{send}\n\t\t\telse\n"
                f"\t\t\t\t(NotNow) ; softlock-guard: fetch required items first\n\t\t\t)")

    return pat.sub(repl, text), n


def realize(specs, src_dir, out_dir=OUT):
    if os.path.isdir(out_dir):
        shutil.rmtree(out_dir)
    shutil.copytree(src_dir, out_dir)
    # also copy the game.ini sibling (load_game reads it one level up)
    ini_src = os.path.join(src_dir, "..", "game.ini")
    if os.path.exists(ini_src):
        shutil.copy(ini_src, os.path.join(out_dir, "..", "game.ini"))

    applied = []
    guards = [s for s in specs if s["op"] == "add_guard"]
    # group guards by room; a room may gate several targets
    by_room = {}
    for g in guards:
        by_room.setdefault(g["room"], []).append(g)

    for room, gs in by_room.items():
        path = os.path.join(out_dir, f"rm{room}.sc")
        if not os.path.exists(path):
            applied.append((room, "MISSING FILE", 0))
            continue
        text = open(path, encoding="latin-1").read()
        total = 0
        for g in gs:
            text, n = wrap_newroom(text, g["newroom_target"], g["guard_sexpr"])
            total += n
            applied.append((room, f"newRoom:{g['newroom_target']} guard {g['guard_sexpr']}", n))
        open(path, "w", encoding="latin-1").write(text)
    return out_dir, applied


def main():
    game = load_game()
    specs = Synth(game).patch_specs()
    out_dir, applied = realize(specs, config.ACTIVE.src_dir)
    print(f"patched source tree -> {os.path.normpath(out_dir)}\n")
    for room, what, n in applied:
        flag = "" if n else "   (no newRoom match!)"
        print(f"  rm{room}: wrapped x{n}  [{what[:70]}]{flag}")
    # sanity: patched tree must still parse
    g2 = load_game(out_dir)
    print(f"\npatched tree parses OK: {len(g2.scripts)} scripts")
    return out_dir


if __name__ == "__main__":
    main()
