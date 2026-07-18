"""examples.py -- one file, every softlock example we have chased, as REAL tests.

Each example is an assertion about a specific game situation: "this stranding is
found", "this item is required", "this room stays reachable". A known example that
does NOT work is a FAILURE -- the run exits non-zero and the build is RED. That is the
correct state of the world: if the disguise gate is not caught, we are not done, and
the build should say so. Nothing here is softened to "expected pending".

This is the CATALOGUE of ground-truth softlocks; _check_core.py is the separate
regression suite (fixed-bug pins). Both must eventually be green.

Run:  python3 src/examples.py     # exits 1 if any example is broken
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config          # noqa: E402
import closure as C    # noqa: E402
from model import load_game  # noqa: E402


class Ctx:
    """Per-game scaffolding, cached so cases stay cheap."""
    def __init__(self, cfg):
        self.cfg = cfg
        self._activate()
        self.g = load_game()
        self.goals = set(cfg.goal_rooms)
        self.start = cfg.start_room
        self._base = self._strand = self._reqs = None

    def _activate(self):
        # closure.py reads the ACTIVE config through the module global CFG; with two
        # games loaded we must re-point it at THIS game before any model operation, or
        # LSL2 cases silently run against KQ4's goals/start.
        config.ACTIVE = self.cfg
        C.CFG = self.cfg

    def base(self):
        self._activate()
        if self._base is None:
            self._base = C.FixModel(self.g)
        return self._base

    def strandings(self):
        if self._strand is None:
            self._strand = [(s["from_room"], s["to_room"], s["item_name"])
                            for s in C.strandings(self.base())]
        return self._strand

    def requirements(self):
        if self._reqs is None:
            self._reqs = C.requirements(self.base())
        return self._reqs

    def item_num(self, name):
        return {self.g.item_name(i): i for i in self.g.items}.get(name)

    def reach(self, regs, exhausted=()):
        self._activate()
        m = C.FixModel(self.g)
        if regs:
            m.promote(regs)
        return C.closure(m, self.start, exhausted=set(exhausted))

    def winnable(self, r):
        return bool(r.rooms & self.goals)


def strand(ctx, a, b, name):
    return (a, b, name) in ctx.strandings()


def disjunctive(ctx, a, b, names):
    want = set(names)
    return any((e["from_room"], e["to_room"]) == (a, b)
               and any(set(c["item_names"]) == want for c in e["clauses"])
               for e in ctx.requirements())


def required_via(ctx, regs, item_name):
    """Promoting `regs`, is `item_name` REQUIRED -- does exhausting it close the goal?"""
    it = ctx.item_num(item_name)
    return it is not None and not ctx.winnable(ctx.reach(regs, exhausted={it}))


def obtainable(ctx, regs, item_name):
    it = ctx.item_num(item_name)
    return it is not None and it in ctx.reach(regs).items


# ---- THE CATALOGUE: (name, game, one-line note, assertion(ctx) -> bool) ----
CASES = [
    # --- LSL2: caught by the base (flat) analysis ---
    ("Grotesque_Gulp stranded rm26->27", "LSL2",
     "eat it before the cruise and the lifeboat is unwinnable",
     lambda c: strand(c, 26, 27, "Grotesque_Gulp")),
    ("Sunscreen stranded rm26->27", "LSL2",
     "needed on the island, unobtainable past the cruise",
     lambda c: strand(c, 26, 27, "Sunscreen")),
    ("Wig stranded rm38->131", "LSL2",
     "disguise piece stranded past the barber gate",
     lambda c: strand(c, 38, 131, "Wig")),
    ("Knife stranded rm47->48", "LSL2",
     "needed on the island; cannot return past the beach",
     lambda c: strand(c, 47, 48, "Knife")),
    ("Fruit OR Sewing_Kit rm38->131 (disjunctive)", "LSL2",
     "either satisfies the gate -- a CNF clause, not one item",
     lambda c: disjunctive(c, 38, 131, {"Fruit", "Sewing_Kit"})),
    ("Sand OR Ashes rm79->80 (disjunctive)", "LSL2",
     "one-way vine swing; either crosses the chasm",
     lambda c: disjunctive(c, 79, 80, {"Sand", "Ashes"})),

    # --- LSL2: caught only via register promotion ---
    ("Parachute REQUIRED for the plane jump", "LSL2",
     "gCurrentStatus promotion: no chute -> rm65 splat, goal closes",
     lambda c: required_via(c, ["gCurrentStatus"], "Parachute")),
    ("Bikini_Top OBTAINABLE (rm34 pool -> rm134 grotto)", "LSL2",
     "the entry-write bug that hid rm134 is fixed",
     lambda c: obtainable(c, ["gCurrentStatus"], "Bikini_Top")),

    # --- LSL2: promotion must NOT false-drop these ---
    ("rm79 endgame reachable under gIslandStatus promotion", "LSL2",
     "promoting the endgame counter must not false-drop the island",
     lambda c: 79 in c.reach(["gIslandStatus"]).rooms),
    ("island stays reachable under knifeHere promotion", "LSL2",
     "knifeHere promotion once dropped the whole island; must stay 85 rooms",
     lambda c: c.winnable(c.reach(["knifeHere"]))),

    # --- LSL2: KNOWN-BROKEN (these SHOULD fail until fixed) ---
    ("Bikini_Top REQUIRED (KGB disguise gate rm47)", "LSL2",
     "TODO: 47->48 survive is a free edge; needs the henchStatus/doit/actor death-gate",
     lambda c: required_via(c, ["gCurrentEgoView", "henchStatus", "gCurrentStatus"],
                            "Bikini_Top")),
    ("Bomb REQUIRED in the crater rm82", "LSL2",
     "TODO/boundary: the gate is in the PIC control map, a binary resource we do not read",
     lambda c: required_via(c, ["gBombStatus"], "Matches")),

    # --- KQ4 ---
    ("iFeather whale rm31->44", "KQ4",
     "the whale-swallow gate; feather-gated machine entry",
     lambda c: strand(c, 31, 44, "iFeather")),
    ("KQ4 winnable with nothing removed (sanity)", "KQ4",
     "the shipped game must be winnable",
     lambda c: c.winnable(c.reach([]))),
    ("Lolotte min-arrow count (Cupid's bow)", "KQ4",
     "TODO: arrow count lives in the bow's `loop` property -- item-property state, unmodelled",
     lambda c: False),
]


def main():
    ctxs = {"LSL2": Ctx(config.LSL2), "KQ4": Ctx(config.KQ4)}
    results = []
    for name, game, note, check in CASES:
        try:
            ok = bool(check(ctxs[game]))
            results.append((ok, game, name, note, None))
        except Exception as e:      # noqa: BLE001
            results.append((False, game, name, note, f"{type(e).__name__}: {e}"))

    results.sort(key=lambda r: (r[0], r[1], r[2]))   # failures first
    print(f"\n  SOFTLOCK EXAMPLE CATALOGUE  ({len(CASES)} examples)\n")
    for ok, game, name, note, err in results:
        print(f"  {'PASS' if ok else 'FAIL'}  {game:4s} {name}")
        print(f"        {note}" + (f"  [{err}]" if err else ""))
    n_fail = sum(1 for r in results if not r[0])
    print(f"\n  {len(CASES) - n_fail} passing, {n_fail} FAILING")
    if n_fail:
        print("  Build is RED: the FAILING examples above are the open work.")
    return 1 if n_fail else 0


if __name__ == "__main__":
    raise SystemExit(main())
