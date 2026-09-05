"""A COUNTER STEP AT A VALUE ITS ROOM CANNOT HOLD IS NOT A STEP (2026-09-05, GK1 docs §1.61).

`_rstep[C][room]` says the game advances C from f to t HERE. `_pstates[C]` says which values C
can actually hold at each room. Where they disagree the step is a fiction, and not a harmless
one: a counter's steps are what `_staged_pre` reseeds the crosser at, so an unattainable step
TELEPORTS a player into the room it names (docs §1.57's landing-seed leak).

Sound because `_pstates` OVER-approximates -- the permissive walk ignores every guard on a
register it does not itself carry, so "not attainable" is a refutation and never a guess -- and
terminating because the pass only ever removes.
"""
import sys

import config
import missability as M

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def attainable(s, C):
    out = {}
    for (q, v) in s._pstates[C]:
        out.setdefault(q, set()).add(v)
    return out


def main():
    print("=== test_step_prune: a step at a value its room cannot hold is not a step ===")
    s = M.load(cfg=config.by_name("gk1"))
    C = 123
    check("GK1's day counter is a counter with a projection",
          C in getattr(s, "_counters", ()) and C in s._pstates,
          f"counters={sorted(getattr(s, '_counters', ()))}")
    att = attainable(s, C)

    # THE INVARIANT, asked of every step of every counter in the game
    bad = [(C2, room, f, t)
           for C2 in sorted(getattr(s, "_counters", ()))
           if C2 in s._pstates
           for room, sts in s._rstep.get(C2, {}).items()
           for (f, t) in sts if f not in attainable(s, C2).get(room, ())]
    check("no counter step survives at a from-value its room cannot hold",
          not bad, f"unattainable steps: {sorted(bad)[:8]}")

    # ...and the branch tables are pruned WITH the steps (same rule, two places)
    badb = [(room, v, sorted(d[C]))
            for (R, room, v), brs in s._wbranch.items() if R == C
            for (d, _c, _co) in brs
            if d.get(C) and not (set(d[C]) & att.get(room, set()))]
    check("no day-write BRANCH survives at a from-value its room cannot hold",
          not badb, f"unattainable branches: {sorted(badb)[:8]}")

    # THE PAYOFF on the live model: the finale room's clamps start where the room does
    r750 = sorted({f for (f, _t) in s._rstep.get(C, {}).get(750, ())})
    check("the finale room's day clamps start at the day it can first be reached",
          r750 and min(r750) == min(att.get(750, {0})),
          f"rm750 step from-values {r750}; attainable days {sorted(att.get(750, ()))}")

    # ...and the opening rooms' phantom self-steps are gone (they are day 0 there, never day 1)
    opening = {q: sorted(s._rstep.get(C, {}).get(q, ())) for q in (17, 93, 180)}
    check("the opening rooms keep no phantom day-1 self-step",
          not any(opening.values()), f"{opening}")

    # ⛔ THE FENCE: pruning must not silence the counter. The bedroom day loop is the game's
    # real day system and every one of its steps must survive.
    r370 = sorted(s._rstep.get(C, {}).get(370, ()))
    check("the bedroom's day loop is untouched -- consecutive steps, still there",
          len(r370) >= 6 and all(t == f + 1 for (f, t) in r370),
          f"rm370 steps = {r370}")
    check("the day counter still has steps at all after pruning",
          any(s._rstep.get(C, {}).values()), "every day step was pruned -- the counter is dead")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
