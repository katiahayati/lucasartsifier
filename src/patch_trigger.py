"""Auto-patcher (task #16): synthesize the LucasArts guard and place it at the
CONTROLLABLE TRIGGER discovered by trigger.find_trigger -- fully automatic, no
hand-placement. Supersedes patch_ericoakford's guard-the-newRoom placement.

  softlock frontier (analysis) -> required items (analysis)
                               -> controllable trigger (trigger trace)
                               -> guard the trigger's (self changeState: K) in source
"""

from __future__ import annotations

import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game                               # noqa: E402
from patch import Synth                                   # noqa: E402
from sexpr import read_file                               # noqa: E402
from trigger import find_trigger, wrap_trigger_in_source  # noqa: E402

ERIC = os.path.join(os.path.dirname(__file__), "..",
                    "vendor", "sci-decomp-archive", "lsl2", "src")
OUT = os.path.join(os.path.dirname(__file__), "..", "out", "lsl2_autopatched")


def item_constants(eric_src):
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
    os.makedirs(os.path.join(OUT, "src"))

    done, skipped = [], []
    for spec in specs:
        room, target = spec["room"], spec["newroom_target"]
        names = [consts.get(i["id"], f"item{i['id']}") for i in spec["require_items"]]
        guard = "(and " + " ".join(f"(ego has: {n})" for n in names) + ")"

        src_path = os.path.join(ERIC, f"rm{room}.sc")
        if not os.path.isfile(src_path):
            skipped.append((room, target, names, "no decompiled source in archive"))
            continue
        try:
            forms = read_file(src_path)
            placement = find_trigger(forms, target)
            text = open(src_path, encoding="latin-1").read()
            new_text, n = wrap_trigger_in_source(text, placement, guard)
        except Exception as exc:                       # noqa: BLE001
            skipped.append((room, target, names, f"trace error: {exc}"))
            continue
        if n == 0 or placement.get("kind") in (None, "not-found", "no-trigger"):
            skipped.append((room, target, names,
                            f"no controllable trigger ({placement.get('kind')})"))
            continue
        open(os.path.join(OUT, "src", f"rm{room}.sc"), "w", encoding="latin-1").write(new_text)
        done.append((room, target, placement, names, n))

    print("=== auto-placed guards (controllable-trigger trace) ===")
    for room, target, pl, names, n in done:
        where = (f"{pl['instance']}:{pl['trigger_method']} (self changeState: {pl['trigger_state']}) "
                 f"[cutscene state {pl['cutscene_state']} -> newRoom {target}]"
                 if pl["kind"] == "trigger" else f"{pl['kind']} {pl.get('method','')}")
        print(f"  rm{room}: guard x{n} at {where}")
        print(f"           require: {names}")
    if skipped:
        print("\n=== skipped (spec emitted, but not auto-placeable this pass) ===")
        for room, target, names, why in skipped:
            print(f"  rm{room}->rm{target}: {why}  (require {names})")
    print(f"\npatched sources -> {os.path.normpath(OUT)}/src/  "
          f"({len(done)} written, {len(skipped)} skipped)")
    return done, skipped


if __name__ == "__main__":
    main()
