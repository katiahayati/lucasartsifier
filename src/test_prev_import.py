"""A `prev == p` GUARD IMPORTS THE EDGES FROM p (2026-09-05, GK1 docs §1.56/§1.57).

Standing at `a` with `prev == p` means the player TOOK some edge `p -> a`, so the disjunction of
those edges' requirements held at that crossing. ⛔ Only what PERSISTS may be imported -- a flag
can be cleared between the crossing and now -- and the one thing that always does is a COUNTER'S
LOWER BOUND: `C == 7` at the crossing means `C >= 7` now, because a counter may not be wound
backwards (the `_counters` rule).

GK1's dream room is the specimen and the reason the rule exists. `rm550.sc:47` -- the ROOM'S OWN
init -- does `setScript: doTheDream` unconditionally, and state 61 of that script is
`(++ global123)`. So ENTERING rm550 *is* the day advance, and the only guard on it is the
entrance. Without the import the day projection reads rm550 as attainable from day 2, its
increment becomes a free day-ender, and §1.34's day fan cannot be bounded (docs §1.57 leak 1).
"""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_prev_import: a `prev == p` guard imports the edges from p ===")
    s = M.load(cfg=config.by_name("gk1"))
    C, prev = 123, s._prev_reg_id()
    check("GK1's day counter is a counter and prevRoom is derived",
          C in getattr(s, "_counters", ()) and prev is not None,
          f"counters={sorted(getattr(s, '_counters', ()))} prev={prev!r}")

    # the shape: the ONLY edge into rm550 demands prev == 540 ...
    metas = s._emeta.get((500, 550)) or []
    check("the only edge into the dream room demands `prev == 540`",
          len(metas) >= 1 and all(set(rq.get(prev, ())) == {540} for rq, _s, _a in metas)
          and not [k for k in s._emeta if k[1] == 550 and k[0] != 500],
          f"metas={[{k: sorted(v) for k, v in rq.items()} for rq, _s, _a in metas]}")

    # ... and the only edge from rm540 into rm500 is day-7 gated, which is what gets imported
    src = s._emeta.get((540, 500)) or []
    check("the only edge from rm540 into rm500 is day-7 gated",
          src and all(min(rq.get(C, {0})) == 7 for rq, _s, _a in src),
          f"reqs={[{k: sorted(v) for k, v in rq.items()} for rq, _s, _a in src]}")

    # THE RULE: the import lands on the edge, as a lower bound, not as the exact value
    got = {v for rq, _s, _a in metas for v in rq.get(C, ())}
    check("the dream-room edge carries the imported lower bound `day >= 7`",
          got and min(got) == 7, f"edge req for {C} = {sorted(got)}")

    # ...and the projection agrees: nobody stands in the dream room before day 7
    days550 = {v for (q, v) in s._pstates[C] if q == 550}
    check("the day projection cannot reach the dream room before day 7",
          days550 and min(days550) == 7, f"rm550 days = {sorted(days550)}")

    # THE FENCE, both halves. (a) only the counter is imported -- a flag is not persistent.
    flags = {R for rq, _s, _a in metas for R in rq
             if R not in (prev, C)} - {R for rq, _s, _a in (s._emeta.get((500, 550)) or [])
                                       for R in rq if R in (prev, C)}
    imported_flags = flags & {R for rq, _s, _a in src for R in rq if R not in (prev, C)}
    check("no clearable flag is imported -- only the counter's lower bound",
          not imported_flags,
          f"flags imported from the source edge: {sorted(imported_flags)}")

    # (b) THE RULE APPLIED WHEREVER IT IS JUSTIFIED. For every prev-guarded edge all of
    # whose ways in are day-guarded, the edge must carry at least their common floor. (The
    # converse -- "an unjustified edge gained nothing" -- is NOT checkable in-process: a day
    # floor may be NATIVE. rm50's `newRoom: global12` fan is the trap, and it cost a wrong
    # test: `(50, 510)` carries `day >= 7` with and without this rule, because §1.39 already
    # gives an icon-derived destination its click gate. Measured both ways, byte for byte.)
    floor = min(set(s.em.reg_vals.get(C, ())) | {0})
    missed, emptied_justified = [], []
    for (a, b), ms in s._emeta.items():
        for rq, _s, _a in ms:
            P = set(rq.get(prev, ()))
            if not P:
                continue
            ways = []
            for p in P:
                got = s._emeta.get((p, a)) if a in s.edges.get(p, ()) else None
                if not got:
                    ways = None
                    break
                ways.extend(w for w, _x, _y in got)
            if not ways or not all(w.get(C) for w in ways):
                continue                       # nothing to import: the permissive side
            lo = min(min(w[C]) for w in ways)
            if lo <= floor:
                continue
            have = set(rq.get(C, ()))
            if not have:
                emptied_justified.append((a, b))
            elif min(have) < lo:
                missed.append((a, b, sorted(have), lo))
    check("every justified prev edge carries its imported floor",
          not missed, f"edges the import missed: {sorted(missed)[:6]}")

    # (c) AND IT NEVER DELETES AN EDGE. Intersecting a req down to the empty set would silently
    # remove a door -- the unsound direction for every walk built on `_emeta`. Asked of the
    # edges the import TOUCHES: three others (`(205,380)`, `(370,371)`, `(370,372)`) carry a
    # natively empty day req, identical with and without this rule, and are somebody else's
    # lead.
    check("no edge the import touches is left with an empty day requirement",
          not emptied_justified, f"emptied by the import: {emptied_justified[:6]}")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
