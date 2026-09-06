"""AN EDGE CANNOT STRAND AN ITEM EVERY CROSSER OF ITS ERA MUST HOLD (2026-09-05, GK1 §1.65).

§1.48's second opinion, asked of an EDGE row instead of a counter flip. The FLAT version of the
question is useless and was measured so on 2026-09-04: `_pclose` with the item banned reaches
everything, because it has no day structure -- "the honest instrument is day-staged, and the row
does not carry a day".

⭐ The row does carry one. Not on the edge, but on its DESTINATION: `_pstates[C]` says the least
counter value `b` can be entered at, and that IS the era the crossing happens in. With `w` in
hand the question is exactly `_closure_flip_dead(C, w, item)` -- the staged closure takes the
step into `w` with everything and dies with the item banned, so nobody without it is ever in
that era, so nobody crosses this edge without it.

GK1's `rm372 -> rm490` (into the bayou maze, era day 6) is the specimen: it refutes three
false positives at once, because day 3 cannot end without `reconVeve` (`has: 38`) or the shown
bracelet mold (flag 256) and day 4 cannot end without the tomb sketch (flag 248, raised only by
showing Magentia `VoodooCode1`).
"""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_era_forced: an edge cannot strand what its era forces ===")
    s = M.load(cfg=config.by_name("gk1"))
    C = 123
    check("GK1's day counter is a counter with a projection",
          C in getattr(s, "_counters", ()) and C in s._pstates)

    # the destination carries the era, and it is the bayou's day 6
    days490 = sorted({v for (q, v) in s._pstates[C] if q == 490})
    check("the bayou maze's era is day 6", days490 and min(days490) == 6, f"rm490 days {days490}")

    # the three items the era forces, each by a different day-end arm
    for it, nm in ((38, "reconVeve"), (40, "braceMold"), (32, "VoodooCode1")):
        check(f"{nm} is era-forced at the bayou crossing",
              s._era_forced(490, it) is not None,
              f"_era_forced(490, {it}) = {s._era_forced(490, it)!r}; "
              f"_closure_flip_dead(123, 6, {it}) = {s._closure_flip_dead(C, 6, it)!r}")

    # ...so the row they made is gone
    rows = {(e["from_room"], e["to_room"]): sorted(e["items"]) for e in s.edge_strandings()}
    check("the rm372 -> rm490 row is refuted whole", (372, 490) not in rows,
          f"still present with items {rows.get((372, 490))}")

    # ⛔ AND R5 SURVIVES: the croc mask is NOT era-forced -- a day-6 player can lack it, which is
    # exactly why the maskless arrival at the ritual is a real dead end.
    check("the croc mask is NOT era-forced, so R5 keeps its row",
          s._era_forced(480, 21) is None and (490, 480) in rows and 21 in rows[(490, 480)],
          f"_era_forced(480, 21) = {s._era_forced(480, 21)!r}; row = {rows.get((490, 480))}")

    # ⛔ THE FENCE: an era nobody crosses into refutes nothing ("not the item's doing"), which is
    # what keeps this from being a blanket suppressor on a game whose late days are unmodelled.
    check("an era nobody reaches in the record refutes nothing",
          s._closure_flip_dead(C, 7, 38) is False,
          "day 7 is unreachable in the record without docs §1.34, so this must be False")

    # ⛔ THE SCOPE, stated accurately rather than hopefully: the rule is a COUNTER's instrument,
    # so LSL2 (no counter at all) cannot be touched -- and KQ4 CAN, because it has one. That is
    # why the corpus gate is the arbiter and not this file. A first draft of this check asserted
    # KQ4 had no counter; it has global116.
    s_lsl2 = M.load(cfg=config.by_name("LSL2"))
    check("LSL2 keeps no counter, so the rule is inert there by construction",
          not getattr(s_lsl2, "_counters", ()),
          f"counters {sorted(getattr(s_lsl2, '_counters', ()))}")
    s_kq4 = M.load(cfg=config.by_name("KQ4"))
    check("KQ4 DOES keep a counter, so the rule is live there and the gate must say so",
          sorted(getattr(s_kq4, "_counters", ())) == [116],
          f"counters {sorted(getattr(s_kq4, '_counters', ()))}")
    fired = [(e["from_room"], e["to_room"], it)
             for e in s_kq4.edge_strandings() for it in e["items"]
             if s_kq4._era_forced(e["to_room"], it)]
    check("...and on KQ4 it refutes nothing: no era there forces an item",
          not fired, f"refuted {fired[:5]}")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
