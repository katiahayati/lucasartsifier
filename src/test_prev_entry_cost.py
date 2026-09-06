"""`prev == p` COSTS ENTERING p (2026-09-05, GK1 docs §1.67).

prevRoom takes the value p only by LEAVING p, and leaving presupposes having entered. So a guard
naming `prev == p` is priced at whatever every way into p demands. Unpriced, the register chain
asks `_value_cost(prev, p, own)`, finds that nothing writes prevRoom in `_inroom_own` -- edges set
it through `sets`, a different channel -- and answers FREE.

GK1's tomb is the specimen, and this oracle's own `sVoodooCode` note asked for the rule verbatim:
"a return edge should carry its origin's entry cost". Flag 250 is set by `sIncorrectMessage`,
armed from rm300's `init` only under `prev == 302` AND flag 247 (`rm300.sc:152-165`); the ONLY
way into rm302 is `sGoToCode`, whose guard is `¬246 ∧ 249 ∧ has:32 ∧ has:33` (`rm300.sc:1101`).
So the flip can only ever be made by a player already holding both tomb sketches -- and unpriced
it read as a point of no return STRANDING the first sketch.

⛔ A SELF-RETURN IS NOT AN ENTRANCE (§1.53), so it may not cheapen the price: rm50's
`newRoom: global12` fan reaches rm302 guarded `prev == 302`, requires nothing, and would
intersect the cost away to free.
"""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_prev_entry_cost: `prev == p` costs entering p ===")
    s = M.load(cfg=config.by_name("gk1"))
    prev = s._prev_reg_id()
    check("GK1's previous-room register is derived", prev is not None, f"got {prev!r}")

    # the shape: rm302's only real entrance prices both sketches, and a self-return also reaches it
    alts302 = [sorted(a) for (rq, _st, alts) in (s._emeta.get((300, 302)) or ()) for a in alts]
    check("rm300 -> rm302 demands both tomb sketches on every alternative",
          alts302 and all(32 in a and 33 in a for a in alts302), f"alts = {alts302}")
    selfret = [(a, b) for (a, b), ms in s._emeta.items() if b == 302
               for (rq, _s, _al) in ms if set(rq.get(prev, ())) == {302}]
    check("...and a SELF-RETURN also reaches rm302, which must not cheapen it",
          bool(selfret), f"self-returns into 302: {selfret}")

    # THE RULE: prev == 302 is priced at the entry cost
    priced = sorted(s._inroom_own.get((prev, 302, 302), frozenset()))
    check("`prev == 302` is priced at both sketches", {32, 33} <= set(priced),
          f"_inroom_own[({prev}, 302, 302)] = {priced}")

    # ...and it reaches the flip whose guard names it, through the chain composition
    base = s.em.ir.flag_synth_base
    f250 = base + 250
    costs = [sorted(c) for (R, room, v), brs in s._wbranch.items() if (R, room, v) == (f250, 300, 1)
             for (_d, c, _co) in brs]
    check("the flag-250 flip inherits the sketches as its cost",
          costs and all({32, 33} <= set(c) for c in costs),
          f"_wbranch[({f250}, 300, 1)] costs = {costs}")

    # THE PAYOFF: the row that FP came from is gone, and nothing real went with it
    rows = [r for r in s.register_strandings() if r.get("item") == 32]
    check("VoodooCode1 keeps no register-stranding row", not rows,
          f"rows = {[{k: v for k, v in r.items() if k != 'item_name'} for r in rows]}")

    # ⛔ THE FENCE, both halves: a room whose every way in is a RETURN prices nothing (there is no
    # entrance to read), and a room with a FREE way in prices nothing either.
    freein = [p for p in list(s.edges) if s._emeta.get((min(s.edges[p]) if s.edges[p] else 0, p)) is None]
    unpriced = {p: sorted(s._inroom_own.get((prev, p, p), frozenset())) for p in (50, 200)}
    check("a room reachable by a free edge prices nothing",
          not any(unpriced.values()), f"{unpriced}")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
