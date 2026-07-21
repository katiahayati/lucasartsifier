"""Unit tests for guard SYNTHESIS (guards.py), in ISOLATION.

The rule under test: a guard's condition is the DNF over the HOPEFUL paths of a gate, keeping
item literals positive AND negative. These pin the logic that decides WHAT goes in a guard and
WHERE it is enforced -- the two things the old `patch.py` got catastrophically wrong (it required
the fatal Spinach_Dip and ANDed two OR-alternatives).

End-to-end scoring stays in `python -m guards` / `python -m missability`; see docs/ROADMAP.md.
"""
import sys

import guards as G
from model import GAnd, GNot, Pred

PASS, FAIL = [], []
def check(name, cond):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}")


def _own(i):
    return Pred("OWN", i, None, None)


def test_own_literals():
    print("\n-- own_literals() --")
    p, n = G.own_literals(GAnd([_own(8), GNot(_own(13)), _own(12)]))
    check("positives collected", p == {8, 12})
    check("negatives collected", n == {13})
    p2, n2 = G.own_literals(GAnd([GNot(GNot(_own(8)))]))
    check("double negation is positive", p2 == {8} and not n2)
    check("empty guard yields nothing", G.own_literals(None) == (set(), set()))


def test_absorb_ordering():
    print("\n-- absorb_ordering() (ordered-cond artefacts) --")
    # rm138 shape: Sewing_Kit branch tested first, so the Fruit branch carries !own(12).
    alts = [({8, 12}, {13}, ("EXIT", 42)),
            ({8, 11}, {13, 12}, ("EXIT", 42))]
    out = G.absorb_ordering(alts)
    negs = [n for (p, n, tr) in out]
    check("`!Sewing_Kit` dropped -- it is positive in a sibling alternative",
          all(12 not in n for n in negs))
    check("`!Spinach_Dip` KEPT -- positive in no hopeful sibling, so it is a real prohibition",
          all(13 in n for n in negs))


def test_factor_and_render():
    print("\n-- factor() / render() --")
    alts = [({8, 12}, {13}, ("EXIT", 42)),
            ({8, 11}, {13, 12}, ("EXIT", 42))]
    cp, cn, rest = G.factor(alts)
    check("common positive hoisted (Grotesque_Gulp)", cp == {8})
    check("common prohibition hoisted (Spinach_Dip)", cn == {13})
    check("alternatives remain as the OR part", {frozenset(p) for (p, n) in rest} ==
          {frozenset({12}), frozenset({11})})
    cond = G.render(cp, cn, rest)
    check("renders the raft guard exactly",
          cond == "(and (gEgo has: 8) (not (gEgo has: 13)) "
                  "(or (gEgo has: 11) (gEgo has: 12)))")
    check("the FATAL item is forbidden, not required", "(not (gEgo has: 13))" in cond)
    check("alternatives are ORed, never ANDed", "(or (gEgo has: 11) (gEgo has: 12))" in cond)

    # a single alternative should not be wrapped in a pointless (or ...)
    solo = G.render({27}, set(), [])
    check("single requirement renders bare", solo == "(gEgo has: 27)")


def test_render_frontier():
    print("\n-- render_frontier() --")
    check("conjunction of stranded items",
          G.render_frontier({"items": {24, 25}, "groups": []}) ==
          "(and (gEgo has: 24) (gEgo has: 25))")
    check("a disjunctive group becomes an OR",
          G.render_frontier({"items": set(), "groups": [{30, 31}]}) ==
          "(or (gEgo has: 30) (gEgo has: 31))")
    check("group of one does not render as an OR",
          G.render_frontier({"items": set(), "groups": [{30}]}) == "(gEgo has: 30)")
    check("nothing stranded -> no guard",
          G.render_frontier({"items": set(), "groups": []}) is None)


def run():
    print("=== test_guards ===")
    test_own_literals()
    test_absorb_ordering()
    test_factor_and_render()
    test_render_frontier()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
