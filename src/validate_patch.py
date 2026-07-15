"""B3: guard-aware regression -- prove the patched game is softlock-free.

The base detector over-approximates movement (it ignores edge guards, on purpose).
So to see that the LucasArts guards actually fixed things, we compute the invariant
the guards establish: `guaranteed[C]` = the items you PROVABLY hold on arriving at
component C, because every path into C crossed edges that required them.

  guaranteed[start] = {}
  guaranteed[C]     = INTERSECTION over incoming act-edges (A->C) of
                      ( guaranteed[A]  UNION  items-required-to-cross(A->C) )

A softlock "need item X in component C" is NEUTRALIZED iff X in guaranteed[C].
We also check no guard deadlocks (each required item is obtainable before its gate),
so the goal stays reachable.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, deque

sys.path.insert(0, os.path.dirname(__file__))
import config                                             # noqa: E402
from model import load_game                               # noqa: E402
from search import SccReach, GOAL_ROOMS, START_ROOM       # noqa: E402

PATCHED = os.path.join(os.path.dirname(__file__), "..", "out", "patched_src")


def edge_guards(s: SccReach):
    """items required (own-guard) to cross each act boundary in the (patched) IR."""
    eg = defaultdict(set)
    for room, sc in s.g.scripts.items():
        ca = s.comp_of.get(room)
        if ca is None:
            continue
        for t in sc.transitions:
            own = {p.var for p in t.guards if p.kind == "OWN" and p.want}
            for e in t.effects:
                if e.kind == "GOTO" and e.arg in s.comp_of:
                    cb = s.comp_of[e.arg]
                    if cb != ca:
                        eg[(ca, cb)] |= own
    return eg


def guaranteed_items(s: SccReach, eg, all_items):
    start_c = s.comp_of[START_ROOM]
    reach = s.creach[start_c]
    incoming = defaultdict(list)          # comp -> [(pred_comp, required_items)]
    for a in reach:
        for b in s.cedges.get(a, ()):
            if b in reach:
                incoming[b].append((a, eg.get((a, b), set())))
    guaranteed = {c: set(all_items) for c in reach}
    guaranteed[start_c] = set()
    changed = True
    while changed:
        changed = False
        for b in reach:
            if b == start_c or not incoming[b]:
                continue
            new = None
            for (a, req) in incoming[b]:
                contrib = guaranteed[a] | req
                new = contrib if new is None else (new & contrib)
            if new is not None and new != guaranteed[b]:
                guaranteed[b] = new
                changed = True
    return guaranteed, reach


def deadlock_check(s: SccReach, eg):
    """each required item must be obtainable before its gate (source reachable from
    start and able to reach the gate's near side) -> guard satisfiable, no deadlock."""
    start_c = s.comp_of[START_ROOM]
    problems = []
    for (a, b), items in eg.items():
        if a not in s.creach[start_c]:
            continue
        for it in items:
            src_comps = {s.comp_of[r] for r in s.sources.get(it, set()) if r in s.comp_of}
            # obtainable before crossing a->b: a source reachable from start AND that
            # source can reach `a` (so you can get it, then arrive at the gate)
            ok = any(sc in s.creach[start_c] and a in s.creach.get(sc, set()) | {sc}
                     for sc in src_comps)
            if not ok:
                problems.append((a, b, it, s.g.item_name(it)))
    return problems


def analyze_game(src_dir):
    g = load_game(src_dir)
    s = SccReach(g)
    return s, s.analyze()


def main():
    print("Guard-aware regression (B3)\n" + "=" * 60)
    s0, cand0 = analyze_game(config.ACTIVE.src_dir)
    print(f"ORIGINAL game: {len(cand0)} softlock candidates")

    if not os.path.isdir(PATCHED):
        print("  (no patched tree; run patch_sci0.py first)")
        return
    s1, cand1 = analyze_game(PATCHED)
    eg = edge_guards(s1)
    guaranteed, reach = guaranteed_items(s1, eg, set(s1.g.items))

    survivors = [c for c in cand1
                 if c["item"] not in guaranteed.get(c["need_component_id"], set())]
    neutralized = [c for c in cand1 if c not in survivors]

    print(f"PATCHED game:  {len(cand1)} raw candidates, "
          f"{len(neutralized)} neutralized by guards, {len(survivors)} SURVIVING\n")
    print("neutralized (item now guaranteed present where needed):")
    for c in neutralized:
        print(f"  ✓ {c['item_name']} @ comp {c['need_component_id']}")
    if survivors:
        print("\nSURVIVING softlocks (need another remedy):")
        for c in survivors:
            print(f"  ✗ {c['item_name']} @ comp {c['need_component_id']}")

    # deadlock / goal-reachability
    problems = deadlock_check(s1, eg)
    start_c = s1.comp_of[START_ROOM]
    goal_comps = {s1.comp_of[r] for r in GOAL_ROOMS if r in s1.comp_of}
    goal_reachable = bool(s1.creach[start_c] & goal_comps)

    print("\n" + "-" * 60)
    print(f"goal still reachable:        {goal_reachable}")
    print(f"guard deadlocks (unsatisfiable requirements): {len(problems)}")
    for a, b, it, nm in problems:
        print(f"  ! comp{a}->comp{b} requires {nm} but it's not obtainable first")

    ok = (not survivors) and goal_reachable and (not problems)
    print("\n" + ("PASS — patched game is softlock-free and still winnable ✅"
                  if ok else "FAIL — see above ❌"))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
