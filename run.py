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

    banner("Stage 4-5  COI slice + SCC-condensation reachability (goal-aware)")
    search.main()

    banner("Reports written")
    for f in ("lsl2_phaseA.md", "lsl2_phaseA.json", "lsl2_reachability.json"):
        p = os.path.join("reports", f)
        mark = "" if os.path.exists(os.path.join(ROOT, p)) else "  (missing!)"
        print(f"  {p}{mark}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
