"""A2: Cone-of-influence (COI) slice.

Goal: shrink the ~480 globals + 32 items down to just the variables that can
influence *winnability*, so the explicit-state search (search.py) is tractable.

Method (backward slice to a fixpoint):
  relevant = vars in { goal guards , death guards , irreversible latches }
  repeat: if a variable V is relevant and some transition WRITES V, then that
          transition's own guard variables also become relevant (they decide
          *when* V gets its value, so they influence the goal too).
  until nothing new is added.

Conservative: OPAQUE guards contribute nothing to pruning (we never drop a var
because we couldn't understand a guard); anything reachable in the dependency
graph is kept.
"""

from __future__ import annotations

from collections import defaultdict

from model import load_game, Game
from analyze import derived_maps, irreversible_globals
from config import ACTIVE as CFG

# The winning terminal + its run-up. Guards in these scripts seed the goal cone.
GOAL_SCRIPTS = list(CFG.goal_scripts)


def guard_vars(t):
    """State variables mentioned in a transition's winnability guards."""
    out = set()
    for p in t.guards:
        if p.kind == "OWN":
            out.add(("item", p.var))
        elif p.kind in ("FLAG", "CMP"):
            out.add(("flag", p.var))
    return out


def effect_vars(t):
    """State variables a transition writes."""
    out = set()
    for e in t.effects:
        if e.kind in ("ACQUIRE", "DROP"):
            out.add(("item", e.arg))
        elif e.kind == "SET":
            out.add(("flag", e.arg))
    return out


def coi_slice(game: Game, goal_scripts=GOAL_SCRIPTS, extra_seeds=None):
    # index variable -> transitions that write it
    writers = defaultdict(list)
    for s in game.scripts.values():
        for t in s.transitions:
            for v in effect_vars(t):
                writers[v].append(t)

    global_sets = derived_maps(game)[3]
    latches = irreversible_globals(game, global_sets)

    relevant = set()
    # seed: goal guards + goal effects (the win-setting flags)
    for num in goal_scripts:
        if num in game.scripts:
            for t in game.scripts[num].transitions:
                relevant |= guard_vars(t)
                relevant |= effect_vars(t)
    # seed: irreversible latches (one-way gates)
    for name in latches:
        relevant.add(("flag", name))
    # seed: any explicit extras
    for v in (extra_seeds or ()):
        relevant.add(v)

    # backward fixpoint
    changed = True
    while changed:
        changed = False
        for v in list(relevant):
            for t in writers.get(v, ()):
                for gv in guard_vars(t):
                    if gv not in relevant:
                        relevant.add(gv)
                        changed = True

    items = {vid for kind, vid in relevant if kind == "item"}
    flags = {name for kind, name in relevant if kind == "flag"}
    return items, flags, latches


def main():
    game = load_game()
    items, flags, latches = coi_slice(game)
    print(f"COI slice: {len(items)} items (of {len(game.items)}), "
          f"{len(flags)} globals (of {len(game.globals)})")
    print("\nrelevant items:")
    print("  " + ", ".join(sorted(game.item_name(i) for i in items)))
    print(f"\nrelevant globals ({len(flags)}):")
    print("  " + ", ".join(sorted(flags)))
    return items, flags


if __name__ == "__main__":
    import os
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    main()
