"""Unit tests for the TEXT-REWRITING layer of the patcher, in isolation.

The v1.0-lb2 review's §5.3: "patcher placement flow ... LB2 deferral/forwarding rewrites have NO
direct unit test". They are the layer with the least excuse for that, because the interesting
ones are pure functions from source text to source text -- no game, no model, no IR. What has
been standing in for tests is the end-to-end placement surface, which reports `applied=True
sites=1` whether or not `sites=1` was the whole story.

That distinction is this project's most expensive recurring bug, twice over (findings #4 and #8):
a guard wrapped ONE of several doors into the same commitment and the player walked around it,
and nothing in the surface could say so, because one wrapped door and one door look identical
from outside. So these tests are written against the arm COUNT and against which arms were
chosen, not merely against "something was rewritten".

The fixtures are LB2's rm520 -- the act-4->5 exit interceptor, copied from the game's own source
-- and mutations of it that a next game could plausibly spell.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import patcher as P                                                      # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


# LB2's rm520::newRoom, verbatim from build/sweep/dagger/src/rm520.sc. The second arm is the
# commit: at act 4 with the grapes, every exit is diverted into rm26, the act-break card.
RM520 = """(instance rm520 of Rm
\t(method (newRoom param1)
\t\t(cond
\t\t\t((== param1 456)
\t\t\t\t(super newRoom: param1)
\t\t\t)
\t\t\t((and (== global123 4) (global0 has: 31))
\t\t\t\t(= param1 26)
\t\t\t\t(WrapMusic dispose:)
\t\t\t\t((ScriptID 22 0) doit: 31)
\t\t\t)
\t\t\t(else
\t\t\t\t(global103 fade:)
\t\t\t\t(super newRoom: param1)
\t\t\t)
\t\t)
\t)
)
"""

STAGE = "(== global123 4)"
COND = "(and (gEgo has: 24) (gEgo has: 25))"


def _wrapped_arms(text):
    """How many arm heads carry our marker -- the count the placement surface should report."""
    return text.count("; softlock-guard: hold the act flip")


def test_single_arm_is_wrapped():
    print("\n-- guard_flip_interceptor: the LB2 shape (the positive it exists for) --")
    out, n = P.guard_flip_interceptor(RM520, 26, STAGE, COND)
    check("the commit arm is wrapped, and only it", n == 1 and _wrapped_arms(out) == 1,
          detail="n=%r wrapped=%d" % (n, _wrapped_arms(out)))
    check("the demand is conjoined ONTO the arm's own head, stage kept",
          "((and (and (== global123 4) (global0 has: 31)) %s)" % COND in out,
          detail=out)
    check("the stock exit arm below is untouched (a held exit falls through to it)",
          "(else\n\t\t\t\t(global103 fade:)" in out)
    check("an arm that pins the stage but routes somewhere ELSE is not a commit",
          P.guard_flip_interceptor(RM520, 999, STAGE, COND)[1] == 0)


def test_every_matching_arm_is_wrapped():
    print("\n-- guard_flip_interceptor: N doors into one commitment --")
    # The same commitment reached two ways: the game re-tests the stage in a second arm that
    # routes into the same pocket (here, the sole-exit shortcut a `doit` twin or a second
    # `cond` arm would spell). Wrapping one of them leaves the other open, which is finding #4
    # and finding #8 both -- and the surface still says the demand is placed.
    two_doors = RM520.replace(
        "\t\t\t(else\n",
        "\t\t\t((and (== global123 4) (global0 has: 12))\n"
        "\t\t\t\t(= param1 26)\n"
        "\t\t\t\t(WrapMusic dispose:)\n"
        "\t\t\t)\n"
        "\t\t\t(else\n")
    out, n = P.guard_flip_interceptor(two_doors, 26, STAGE, COND)
    check("BOTH arms committing the flip are wrapped",
          _wrapped_arms(out) == 2,
          detail="wrapped %d of 2 arms -- the unwrapped one is a bypass the player walks "
                 "straight through:\n%s" % (_wrapped_arms(out), out))
    check("...and the count returned is the number of doors, not 1",
          n == 2, detail="n=%r" % (n,))

    # The same thing across METHODS: `newRoom` and its `doit` twin both committing.
    twin = RM520.replace("\t(method (newRoom param1)", "\t(method (doit param1)", 1)
    both = RM520.rstrip()[:-1] + twin[twin.index("\t(method"):]
    out2, n2 = P.guard_flip_interceptor(both, 26, STAGE, COND)
    check("a `doit` twin of the same commit is wrapped too",
          _wrapped_arms(out2) == 2 and n2 == 2,
          detail="wrapped=%d n=%r" % (_wrapped_arms(out2), n2))


def test_stage_match_is_structural():
    print("\n-- guard_flip_interceptor: the stage must be PINNED, not merely present --")
    # A head that mentions the stage inside a disjunction does not pin it: this arm runs at act
    # 4 AND at act 9. Conjoining our demand there gates a crossing the spec says nothing about,
    # which is the wall-shaped failure, not the missed-guard-shaped one.
    disj = RM520.replace("((and (== global123 4) (global0 has: 31))",
                         "((and (or (== global123 4) (== global123 9)) (global0 has: 31))")
    out, n = P.guard_flip_interceptor(disj, 26, STAGE, COND)
    check("an arm that only MENTIONS the stage under an (or ...) is refused",
          n == 0 and _wrapped_arms(out) == 0,
          detail="the head runs at act 9 as well, so the demand would gate a crossing the "
                 "spec never scoped: n=%r\n%s" % (n, out))

    # ...and the bare form still matches: a head that IS the stage test pins it.
    bare = RM520.replace("((and (== global123 4) (global0 has: 31))", "((== global123 4)")
    check("a head that IS the stage test still matches",
          P.guard_flip_interceptor(bare, 26, STAGE, COND)[1] == 1)

    # A NEGATED stage does not pin it either -- that arm is every act but this one.
    neg = RM520.replace("((and (== global123 4) (global0 has: 31))",
                        "((and (not (== global123 4)) (global0 has: 31))")
    check("a NEGATED stage test does not pin the stage",
          P.guard_flip_interceptor(neg, 26, STAGE, COND)[1] == 0,
          detail="the arm runs at every act EXCEPT the one the spec scopes to")

    # ...and the head this function has to recognise most often is ITS OWN PREVIOUS OUTPUT: a
    # second demand forwarded onto the same hold arrives at an arm we already wrapped, where
    # the stage sits one `and` deeper. It is pinned exactly as hard as before -- conjunction is
    # associative -- and refusing it silently dropped LB2's forwarded act-5 demand from the
    # emitted patch. The surface diff caught that; this check is so the next one does not need to.
    once, n1 = P.guard_flip_interceptor(RM520, 26, STAGE, COND)
    twice, n2 = P.guard_flip_interceptor(once, 26, STAGE, "(gEgo has: 30)")
    check("an arm THIS function already wrapped is still pinned (forwarding re-matches it)",
          n1 == 1 and n2 == 1 and _wrapped_arms(twice) == 2,
          detail="second pass n=%r:\n%s" % (n2, twice))


def run():
    print("=== test_patch_text ===")
    test_single_arm_is_wrapped()
    test_every_matching_arm_is_wrapped()
    test_stage_match_is_structural()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
