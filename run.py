#!/usr/bin/env python3
"""End-to-end driver for the Sierra softlock analyzer.

Runs the whole pipeline on the configured game and (re)generates the reports:
  decompiled .sc  ->  S-expr  ->  transition-system IR  ->  COI slice
                  ->  reachability / point-of-no-return frontier  ->  reports/

Usage:
    python3 run.py

The game-specific knobs (source dir, start room, goal rooms, timers) live in
src/config.py.  Everything else is generic SCI0 machinery.
"""

import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "src"))

import config      # noqa: E402
import model       # noqa: E402
import analyze     # noqa: E402
import search      # noqa: E402
import closure     # noqa: E402


def banner(title):
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def main():
    cfg = config.ACTIVE
    print("Sierra SCI/AGI softlock analyzer")
    print(f"Game:   {cfg.name}")
    print(f"Source: {cfg.src_dir}")

    if not os.path.isdir(cfg.src_dir):
        print(f"\nERROR: decompiled source not found.\n"
              f"Run  ./scripts/fetch_source.sh  to vendor it, then re-run.")
        return 1

    banner("Stage 1-2  Parse scripts + build transition-system IR")
    game = model.load_game(cfg.src_dir)
    ntr = sum(len(s.transitions) for s in game.scripts.values())
    print(f"scripts={len(game.scripts)}  globals={len(game.globals)}  "
          f"items={len(game.items)}  transitions={ntr}")

    banner("Stage 3  Derived maps + heuristic frontier  ->  Phase-A catalog")
    analyze.main(cfg.src_dir)

    banner("Stage 4-5  COI slice + SCC reachability  [LEGACY -- pending deletion]")
    print("The syntactic path. Kept only as a cross-check while the semantic core\n"
          "catches up: it is UNSOUND (it reads 'an OWN(x) guard exists in this room'\n"
          "as 'you need x here', so it cannot tell a protective item from a fatal\n"
          "one -- see src/patch.py DISABLED_WHY) but it still surfaces a few real\n"
          "cases the fixpoint cannot yet derive. Do not synthesize patches from it.\n")
    search.main()

    banner("Stage 6  Semantic core: guard-respecting fixpoint  [PRIMARY]")
    m, _r = closure.main()
    strands = closure.strandings(m)
    print(f"\nstrandings (derived, no special-casing): {len(strands)}")
    for s in strands:
        print(f"  rm{s['from_room']} -> rm{s['to_room']} strands {s['item_name']}")
    print(f"\nintra-room state machines gating movement: {len(m.machines)}")
    print(f"  trusted machine exits : {len(m.machine_edges)}")
    print(f"  exits we cannot model : {len(m.machine_untrusted)} "
          f"(fell back to the flat edge rather than invent a dead end)")

    banner("Reports written")
    for f in ("lsl2_phaseA.md", "lsl2_phaseA.json", "lsl2_reachability.json"):
        p = os.path.join("reports", f)
        mark = "" if os.path.exists(os.path.join(ROOT, p)) else "  (missing!)"
        print(f"  {p}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
