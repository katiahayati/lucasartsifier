"""A SELF-RETURN IS NOT A FIRST ENTRANCE (2026-09-04, GK1 docs §1.53).

An edge `a -> b` whose guard demands `prevRoom == b` is the return half of a round trip: taking
it presupposes having stood in b already. The projection that TRACKS prevRoom enforces that; in
every other projection prevRoom is unconstrained and the edge reads as a free door INTO b.

GK1 is the specimen. rm50's `newRoom: global12` fans twenty such returns, one of them into
rm302 -- the tomb-code inset, whose ONLY real entrance is rm300's `sGoToCode`, armed at four
sites under `¬flag246 ∧ flag249 ∧ has:32 ∧ has:33`. Through the return, a player holding
neither tomb sketch could stand in rm302 with flag 246 already set, so `register_strandings`
could not see that the flip's own precondition demands the sketch, and `sVoodooCode` was
reported stranded by a flip only its holder can cause.

⛔ The rule is asked ONLY where the question is "can this player FIRST get in" --
`_flip_live`'s walk. Dropping self-returns everywhere would SHRINK the post-flip walk, and a
smaller reachable set INVENTS strandings, which is the unsound direction."""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def main():
    print("=== test_self_return_entrance: a self-return is not a first entrance ===")
    s = M.load(cfg=config.by_name("gk1"))
    s._own_fixpoint()
    prev = s._prev_reg_id()
    check("GK1's previous-room register is derived, not named", prev is not None, f"got {prev!r}")

    # the shape exists, and in quantity -- this is not a one-edge special case
    selfret = [(a, b) for (a, b), metas in s._emeta.items()
               for (req, _s, _al) in metas if req and set(req.get(prev, ())) == {b}]
    check("GK1 has self-return edge metas (rm50's `newRoom: global12` fan among them)",
          len(selfret) >= 10 and (50, 302) in selfret, f"{len(selfret)} found; (50,302) present: {(50,302) in selfret}")

    # the tomb-code room's only REAL entrance prices both sketches
    alts302 = [sorted(a) for (req, _s, alts) in s._emeta.get((300, 302), ()) for a in alts]
    check("rm300 -> rm302 demands both tomb sketches (32, 33) on every alternative",
          alts302 and all(32 in a and 33 in a for a in alts302), f"alts = {alts302}")

    # THE FIX: with the second sketch banned, a first-entrance walk cannot stand in rm302
    R = 488                                    # flag 246, the tomb-code flag
    banned = frozenset({33})
    loose = {v for (q, v) in s._walk(R, banned) if q == 302}
    tight = {v for (q, v) in s._walk(R, banned, no_self_return=True) if q == 302}
    check("without the fix, the sketch-less player reaches rm302 (the defect)", bool(loose),
          f"values at rm302 = {sorted(loose)}")
    check("WITH the fix, the sketch-less player cannot first enter rm302", not tight,
          f"still reachable at values {sorted(tight)}")

    # and the rule must NOT tighten the ordinary walk
    free_loose = {q for (q, _v) in s._walk(R, frozenset())}
    free_tight = {q for (q, _v) in s._walk(R, frozenset(), no_self_return=True)}
    check("a player who is banned from nothing loses no ROOM to the rule",
          free_loose == free_tight,
          f"lost: {sorted(free_loose - free_tight)}")
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
