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


# --- trigger.arming_contexts: what counts as the game taking the controls ------------------------
#
# `handsoff_before` decides whether an arming is an ARRIVAL COMMIT -- the classification that
# sent LB2's rm250 wrap to a different site after the play test found it sitting inside the
# commit. It is answered by searching the source text between two offsets, and source text
# contains comments and message strings, which are not code.
ARM = """(instance rm300 of Rm
\t(method (init)
\t\t%s
\t\t(self setScript: sACTBREAK)
\t)
)
"""


def test_handsoff_ignores_comments_and_strings():
    print("\n-- trigger.arming_contexts: a handsOff in a COMMENT is not a handsOff --")
    import trigger as T                                                  # noqa: E402
    real = T.arming_contexts(ARM % "(global1 handsOff:)", "sACTBREAK", ego="global0")
    check("a real handsOff before the arming is seen",
          len(real) == 1 and real[0]["handsoff_before"] is True,
          detail="%r" % (real,))

    commented = T.arming_contexts(ARM % "; the cab ride does (global1 handsOff:) elsewhere",
                                  "sACTBREAK", ego="global0")
    check("a handsOff inside a COMMENT is not the game taking the controls",
          len(commented) == 1 and commented[0]["handsoff_before"] is False,
          detail="a commented-out send classifies this arming as an arrival commit, which "
                 "routes its guard somewhere else entirely: %r" % (commented,))

    stringed = T.arming_contexts(ARM % '(Print {you hear a handsOff: click})',
                                 "sACTBREAK", ego="global0")
    check("a handsOff inside a message STRING is not one either",
          len(stringed) == 1 and stringed[0]["handsoff_before"] is False,
          detail="%r" % (stringed,))


def test_unreadable_deliverer_is_not_a_cleared_one():
    print("\n-- patcher._cutscene_delivers: 'could not read' is not 'no cutscene' --")
    # False keeps the IN-PLACE GATE, which is the arrangement the user's play test caught
    # sitting inside a commit. Answering it from a file we never read asserts what we could not
    # check, so a missing performer has to be a third answer.
    check("a room with no known title answers None, not False",
          P._cutscene_delivers("/nonexistent", {}, 300, 250) is None)
    check("a title whose file does not exist answers None, not False",
          P._cutscene_delivers("/nonexistent", {300: "rm300"}, 300, 250) is None)


def test_interceptor_shape_census():
    """WHERE THE INTERCEPTOR SHAPE EXISTS AT ALL, across the corpus.

    The review's §1.2: the shape was generalised from ONE instance and its census lived in a
    memory note rather than anywhere a run could check. It is cheap to measure -- the function
    is pure text -- so it is measured here: for every room script, every `(== globalN v)` it
    contains as a candidate stage and every `(= paramN <room>)` as a candidate pocket, does any
    arm match?

    MEASURED 2026-08-14: LSL2 0, KQ4 0, KQ6 0, LB2 6 -- rm500's act-2->3 arm, rm520's act-4->5
    arm (the one that ships), and four in rm666, the game's own room-remap dispatcher. So the
    mechanism is LB2-shaped today but not LB2-unique even within LB2, and a game whose
    interceptor is spelled differently will show up here as a zero that ought not to be."""
    print("\n-- guard_flip_interceptor: the corpus census, not a memory note --")
    import os as _os                                                     # noqa: E402
    import re                                                            # noqa: E402
    import config                                                        # noqa: E402
    want = {"LSL2": 0, "KQ4": 0, "KQ6": 0, "dagger": 6}
    for name, expect in want.items():
        cfg = config.by_name(name)
        if cfg is None or not _os.path.isdir(cfg.src_dir):
            check("%s: interceptor-shaped arms" % name, False, "NO src tree -- not measured")
            continue
        hits = 0
        for fn in sorted(_os.listdir(cfg.src_dir)):
            if not fn.endswith(".sc"):
                continue
            text = open(_os.path.join(cfg.src_dir, fn), errors="replace").read()
            stages = set(re.findall(r"\(==\s*global\d+\s+-?\d+\)", text))
            pockets = {int(x) for x in re.findall(r"\(=\s*param\d+\s+(\d+)\s*\)", text)}
            for st in stages:
                for pk in pockets:
                    if P.guard_flip_interceptor(text, pk, st, "(gEgo has: 1)")[1]:
                        hits += 1
        check("%s: %d interceptor-shaped arm(s)" % (name, expect), hits == expect,
              detail="measured %d, expected %d -- if a new game shows 0 here, its commit is "
                     "spelled some other way and falls to REFUSED silently" % (hits, expect))


# KQ5's henchman arming, verbatim shape from build/kq5/ir/src/castle.sc: the `setScript:`
# rides a MULTI-SELECTOR CASCADE whose first argument nests two parens deep. The flat
# `[^()]*` arm-event pattern could not see it -- "trigger found but no site rewritten" was
# the whole castle-fish placement gap (rm54->rm59/rm54->rm67, 2026-08-18).
HENCHMAN = """(instance theHenchMan of Actor
\t(properties
\t\tx 1000
\t)

\t(method (init)
\t\t(super init:)
\t\t(self
\t\t\tview: (if (== global11 58) 898 else 884)
\t\t\tsetCycle: Walk
\t\t\tsetLoop: -1
\t\t\tlooper: 0
\t\t\tsetScript: theHenchManScript
\t\t)
\t\t(if (not global333)
\t\t\t(= global333 1)
\t\t)
\t)
)
"""

# The flat single-selector spelling every prior game uses (KQ4's whale). The cascade fix must
# leave this emission byte-identical -- KQ4 is golden.
WHALE = """(instance Room31 of Rm
\t(properties
\t\tpicture 31
\t)

\t(method (init)
\t\t(super init:)
\t\t(global0 setScript: whaleActions)
\t)
)
"""


def test_arm_event_wraps_the_whole_cascade():
    print("\n-- arm-event: the arming statement is the send, not a flat regex span --")
    import trigger as T
    place = {"kind": "arm-event", "trigger_instance": "theHenchMan", "trigger_method": "init",
             "target_script": "theHenchManScript", "target_room": 59}
    out, n = T.wrap_trigger_in_source(HENCHMAN, place, "(gEgo has: 37)", "(Refuse)")
    check("the cascaded arming is found and wrapped once", n == 1,
          detail="n=%r\n%s" % (n, out))
    check("the WHOLE send is inside the gate (view/setCycle held with the setScript)",
          "(if " in out and out.index("(if (") < out.index("view:")
          and "arm only when survivable" in out,
          detail=out)
    check("the file still balances", out.count("(") == out.count(")"), detail=out)
    check("the sibling statement after the send is NOT wrapped",
          out.index("arm only when survivable") < out.index("(if (not global333)"),
          detail=out)

    flat, n2 = T.wrap_trigger_in_source(
        WHALE, {"kind": "arm-event", "trigger_instance": "Room31", "trigger_method": "init",
                "target_script": "whaleActions", "target_room": 32},
        "(gEgo has: 8)", "(Refuse)")
    check("the flat single-selector send wraps exactly as before (KQ4 golden shape)",
          n2 == 1 and "(if (gEgo has: 8)\n\t\t\t\t(global0 setScript: whaleActions)\n\t\t\t)"
          in flat,
          detail=flat)


# KQ5's computed edge exit, verbatim shape from rm036.sc: `doit` reads `(gEgo edgeHit:)`,
# resolves the destination through `edgeToRoom:` into a temp, and `newRoom:`s the temp. Three
# derivations in one site: edgeHit is a positional fact (the ego WALKED there), an
# edgeToRoom-assigned variable holds the room's own nav values, and a var destination is
# located by the variable and discriminated by dest_test.
RM036 = """(instance rm036 of KQ5Room
\t(properties
\t\tpicture 36
\t\tnorth 38
\t\twest 35
\t)

\t(method (init)
\t\t(super init:)
\t\t(global0 posn: 149 140)
\t)

\t(method (doit &tmp temp0)
\t\t(cond
\t\t\t(script
\t\t\t\t(script doit:)
\t\t\t)
\t\t\t(
\t\t\t\t(and
\t\t\t\t\t(global0 edgeHit:)
\t\t\t\t\t(= temp0 (self edgeToRoom: (global0 edgeHit:)))
\t\t\t\t)
\t\t\t\t(global2 newRoom: temp0)
\t\t\t)
\t\t)
\t)
)
"""


def test_computed_edge_exit_is_a_positional_direct():
    print("\n-- find_trigger: an edgeToRoom dispatch is a positional direct exit --")
    import sexpr
    import trigger as T
    forms = sexpr.read_all(RM036)
    p = T.find_trigger(forms, 35, ego=0)
    check("the crossing is classified direct + positional (edgeHit IS where the ego stands)",
          p["kind"] == "direct" and p.get("positional") and p.get("instance") == "rm036",
          detail=repr(p))
    check("the destination variable and its discriminator both ride the placement",
          p.get("dest_var") == "temp0" and p.get("dest_test") == "(== temp0 35)",
          detail=repr(p))
    # ...and the other declared direction resolves through the same site.
    p38 = T.find_trigger(forms, 38, ego=0)
    check("the sibling direction resolves through the same dispatch",
          p38["kind"] == "direct" and p38.get("dest_test") == "(== temp0 38)",
          detail=repr(p38))
    # the wrap: turn-back (a doit refusal machine-guns), walk-in posn as the safe target
    place = {**p, "obj_globals": {"ego": "global0", "room": "global2", "game": "global1",
                                  "hands": None}}
    guard = "(or (not (== temp0 35)) (== ((global9 at: 2) owner:) 36))"
    out, n = T.wrap_trigger_in_source(RM036, place, guard, "(Refuse)")
    check("the var-destination site is rewritten (no literal newRoom exists to find)",
          n == 1 and "sgTurnBack" in out, detail="n=%r\n%s" % (n, out))
    check("the turn-back walks to the room's own walk-in position (the strip cannot hold it)",
          "MoveTo 149 140" in out, detail=out)
    check("the file still balances", out.count("(") == out.count(")"), detail=out)


# Main.sc's lamb EAT case, verbatim shape: the first bite KEEPS the item (put + re-get, the
# half-lamb cel write) and sets the hunger flag rm32's death demands; only the else arm's bare
# put destroys it. USER-corrected 2026-08-18b: "it HAS to be half the leg of lamb."
LAMB_EAT = """(instance KQ5 of Game
	(method (handleEvent param1)
		(switch (global9 indexOf: (global69 curInvIcon:))
			(2
				(proc0_9 16)
				(proc0_29 141)
				(global0 put: 2 1)
				(param1 claimed: 1)
			)
			(19
				(if (== (++ global316) 1)
					(proc0_27 4)
					(proc0_9 16)
					(proc0_29 142)
					(global0 put: 19 global11)
					(global0 get: 19)
				else
					(proc0_29 143)
					(global0 put: 19 1)
				)
				(param1 claimed: 1)
			)
		)
	)
)
"""

# rm006's lamb throw: the put sits inside the race-check `if local0` fork, but NO arm re-gets
# -- the whole case must stay wrapped exactly as it ships today.
LAMB_THROW = """(instance nest of RFeature
	(method (handleEvent param1)
		(switch (global9 indexOf: (global69 curInvIcon:))
			(19
				(if local0
					(proc0_29 215)
				else
					(= local2 3)
					(global0 put: 19 6)
					(catAndMouse changeState: 4)
				)
				(param1 claimed: 1)
			)
		)
	)
)
"""


def test_market_wrap_spares_the_reget_branch():
    print("\n-- wrap_forbidden_case: a put the same branch re-gets is not a spend --")
    import trigger as T
    out, n = T.wrap_forbidden_case(LAMB_EAT, r"put:\s*19\b", 19,
                                   "(not (gEgo has: 19))", "(Refuse)")
    check("exactly one wrap lands (the destroying arm)", n == 1, detail="n=%r\n%s" % (n, out))
    check("the first bite stays stock (+4 / flag 16 / re-get untouched)",
          "(if (not (gEgo has: 19))\n" not in out.split("else")[0]
          and out.index("(proc0_27 4)") < out.index("(Refuse)"),
          detail=out)
    check("the destroying put is inside the refusal wrap",
          out.index("(Refuse)") > out.index("put: 19 1") - 400
          and "(if (not (gEgo has: 19))" in out,
          detail=out)
    check("the pie case is untouched", "(global0 put: 2 1)" in out
          and out.count("Refuse") == 1, detail=out)
    check("the file still balances", out.count("(") == out.count(")"), detail=out)

    out2, n2 = T.wrap_forbidden_case(LAMB_THROW, r"put:\s*19\b", 19,
                                     "(not (gEgo has: 19))", "(Refuse)")
    base2, nb2 = T.wrap_forbidden_case(LAMB_THROW.replace("(global0 get: 19)", ""),
                                       r"put:\s*19\b", 19,
                                       "(not (gEgo has: 19))", "(Refuse)")
    check("a no-reget fork keeps the whole-case wrap (shipped emissions cannot churn)",
          n2 == 1 and out2 == base2 and out2.index("(if (not (gEgo has: 19))")
          < out2.index("(if local0"),
          detail=out2)


# === THE 2026-08-19d REVIEW: the two new appliers, and the span arithmetic under them ==========
#
# docs/REVIEW-2026-08-19d-FIXES.md F1/F2/F5/F6/F14/F15. Both appliers shipped with NO test of any
# kind, and both are pure text manipulation -- the layer this file's opening docstring calls the
# one with the least excuse for that. Each fixture below is a shape a next game spells routinely
# and KQ5 happens not to: an arming in an `else`, a procedure with an earlier unrelated branch,
# an arming with no wrap around it at all, and a message string containing a paren.

# F1. An arming in the ELSE branch. Conjoining the demand onto this `(if`'s TEST does not hold
# the ambush -- it INVERTS it: the encounter then arms exactly when the player cannot survive
# it, and the placement row still reports `applied: True`.
ELSE_ARM = """(instance rm300 of Rm
\t(method (init)
\t\t(super init:)
\t\t(if (== global11 58)
\t\t\t(theGuard setScript: patrolScript)
\t\telse
\t\t\t(theGuard setScript: ambushScript)
\t\t)
\t)
)
"""

# ...and the same fork held INSIDE an outer arming. The inner `if` is disqualified, but the
# outer one holds the whole fork in its then branch, so it is a sound hold and the search must
# keep going OUTWARD rather than refusing.
NESTED_ELSE_ARM = """(instance rm300 of Rm
\t(method (init)
\t\t(super init:)
\t\t(if (not (proc0_12 41))
\t\t\t(if (== global11 58)
\t\t\t\t(theGuard setScript: patrolScript)
\t\t\telse
\t\t\t\t(theGuard setScript: ambushScript)
\t\t\t)
\t\t)
\t)
)
"""

# ...and the plain positive: a then-branch arming, with a nested value-`if` earlier in the same
# branch whose `else` belongs to IT and must not be mistaken for the outer one's.
THEN_ARM = """(instance rm300 of Rm
\t(method (init)
\t\t(super init:)
\t\t(if (not (proc0_12 41))
\t\t\t(theGuard view: (if (== global11 58) 898 else 884))
\t\t\t(theGuard setScript: ambushScript)
\t\t)
\t)
)
"""


def test_enclosing_if_test_respects_the_else_branch():
    print("\n-- patcher._enclosing_if_test: the else branch is not the then branch --")
    pos = THEN_ARM.index("setScript: ambushScript")
    span = P._enclosing_if_test(THEN_ARM, pos)
    check("a then-branch arming finds its own arming test",
          span is not None and THEN_ARM[span[0]:span[1]] == "(not (proc0_12 41))",
          detail="span=%r -> %r" % (span, span and THEN_ARM[span[0]:span[1]]))

    pos = ELSE_ARM.index("setScript: ambushScript")
    span = P._enclosing_if_test(ELSE_ARM, pos)
    check("an ELSE-branch arming does NOT return the test that would invert the guard",
          span is None,
          detail="span=%r -> %r. Conjoining a demand onto `(== global11 58)` arms the ambush "
                 "exactly when the player CANNOT survive it, and the row still says "
                 "applied=True." % (span, span and ELSE_ARM[span[0]:span[1]]))

    pos = NESTED_ELSE_ARM.index("setScript: ambushScript")
    span = P._enclosing_if_test(NESTED_ELSE_ARM, pos)
    check("...but an OUTER if holding the whole fork in its then branch is still a hold",
          span is not None and NESTED_ELSE_ARM[span[0]:span[1]] == "(not (proc0_12 41))",
          detail="span=%r -> %r" % (span, span and NESTED_ELSE_ARM[span[0]:span[1]]))


# F15. `_balanced_span` counted raw parens with no string or comment handling, and
# `_enclosing_if_test` scans the WHOLE file -- so one `(` inside a message string shifts every
# span computed after it. castle.sc contains no `{` at all, which is the only reason the two
# 2026-08-19d appliers were safe there.
STRINGY = """(instance rm300 of Rm
\t(method (init)
\t\t(Print {a paren ( in a message})
\t\t; and a paren ( in a comment
\t\t(if (not (proc0_12 41))
\t\t\t(theGuard setScript: ambushScript)
\t\t)
\t)
)
"""


def test_balanced_span_ignores_strings_and_comments():
    print("\n-- patcher._balanced_span: a paren in a string is not a paren --")
    i = STRINGY.index("(instance")
    check("the whole instance form spans to its own closing paren",
          P._balanced_span(STRINGY, i) == len(STRINGY.rstrip()),
          detail="span ends at %d, the form ends at %d"
                 % (P._balanced_span(STRINGY, i), len(STRINGY.rstrip())))
    pos = STRINGY.index("setScript: ambushScript")
    span = P._enclosing_if_test(STRINGY, pos)
    check("...and the arming test is still found past an unbalanced string and comment",
          span is not None and STRINGY[span[0]:span[1]] == "(not (proc0_12 41))",
          detail="span=%r -> %r" % (span, span and STRINGY[span[0]:span[1]]))


# F2. The `fuse-arm` applier took the FIRST `(if` in the procedure, not the one containing the
# spawn. `proc550_16` is a single top-level `if`, so KQ5 never showed it; a procedure with any
# earlier branch gets a guard that holds nothing and gates something unrelated -- while
# reporting `applied: True sites=1`.
SPAWNER = """(procedure (proc550_16)
\t(if (== global5 1)
\t\t(Load 132 835)
\t)
\t(if (and (!= global332 7) (> (Random 0 100) 20))
\t\t(switch global11
\t\t\t(57
\t\t\t\t(theCat posn: 91 172 init:)
\t\t\t)
\t\t\t(58
\t\t\t\t(theCat posn: 103 115 init:)
\t\t\t)
\t\t)
\t\t(= global332 1)
\t)
)
"""

# KQ5's own shape, verbatim in structure: one top-level `if`, the spawn inside it. That emission
# is play-confirmed and must not move by a byte.
KQ5_SPAWNER = """(procedure (proc550_16)
\t(if (and (!= global332 7) (> (Random 0 100) 20))
\t\t(Load 132 835)
\t\t(switch global11
\t\t\t(57
\t\t\t\t(theCat posn: 91 172 init:)
\t\t\t)
\t\t)
\t\t(= global332 1)
\t)
)
"""

# ...and a spawn with no arming around it: refusing WHOLE is the doctrine, because holding the
# guarded sites and leaving this one open is a claim of coverage the patch does not have.
BARE_SPAWNER = """(procedure (proc550_16)
\t(if (== global5 1)
\t\t(theCat posn: 91 172 init:)
\t)
\t(theCat posn: 103 115 init:)
)
"""

DEMAND = "(and (proc0_12 63) (gEgo has: 24))"


def test_fuse_arm_holds_the_if_that_spawns():
    print("\n-- patcher._place_fuse_arm: the arming is the `if` around the SPAWN --")
    place = getattr(P, "_place_fuse_arm", None)
    if place is None:
        check("the fuse-arm applier is a testable function",
              False,
              detail="`patcher._place_fuse_arm` does not exist -- the applier is inline in "
                     "`apply_guards`, so its text arithmetic has no test at all (F14).")
        return
    out, n, why = place(SPAWNER, "proc550_16", ["theCat"], DEMAND)
    check("the demand lands on the arming that performs the spawn",
          why is None and n == 1
          and "(and (and (!= global332 7) (> (Random 0 100) 20)) %s)" % DEMAND in out,
          detail="n=%r why=%r\n%s" % (n, why, out))
    check("...and NOT on the unrelated branch that happens to come first",
          "(and (== global5 1)" not in out,
          detail="a guard on `(== global5 1)` holds no spawn at all and gates the Load "
                 "instead:\n%s" % out)
    check("the file still balances", out.count("(") == out.count(")"), detail=out)

    out2, n2, why2 = place(KQ5_SPAWNER, "proc550_16", ["theCat"], DEMAND)
    check("KQ5's own shape emits exactly what it shipped (one wrap on the sole arming)",
          why2 is None and n2 == 1
          and "(and (and (!= global332 7) (> (Random 0 100) 20)) %s) ; softlock-guard" % DEMAND
          in out2,
          detail="n=%r why=%r\n%s" % (n2, why2, out2))

    out3, n3, why3 = place(BARE_SPAWNER, "proc550_16", ["theCat"], DEMAND)
    check("a spawn outside every `(if` refuses WHOLE rather than half-holding",
          why3 is not None and n3 == 0 and out3 == BARE_SPAWNER,
          detail="n=%r why=%r\n%s" % (n3, why3, out3))

    out4, n4, why4 = place(SPAWNER, "proc550_16", ["theRat"], DEMAND)
    check("a host the procedure never inits is a refusal, not a guess",
          why4 is not None and n4 == 0 and out4 == SPAWNER, detail="why=%r" % (why4,))


# F5. `capture-arm` only landed on KQ5 because an UNRELATED spec (the rm54 fish discriminator)
# had already wrapped the same send. Stock `theHenchMan::init` has no enclosing `(if` at all, so
# `_enclosing_if_test` returns None and the applier refuses -- retire the fish guard and the
# capture guard silently stops shipping, with `test_kq5_ground_truth` still green because it
# pins the SPEC and not the applied edit.
STOCK_HENCH = """(instance theHenchMan of Actor
\t(properties
\t\tx 1000
\t)

\t(method (init)
\t\t(super init:)
\t\t(self
\t\t\tview: (if (== global11 58) 898 else 884)
\t\t\tsetCycle: Walk
\t\t\tsetScript: theHenchManScript
\t\t)
\t)
)
"""

# ...and the same file after the edge pass has wrapped it, which is what KQ5 actually ships.
WRAPPED_HENCH = STOCK_HENCH.replace(
    "\t\t(self\n",
    "\t\t(if (or (not (== global11 54)) (gEgo has: 37))\n\t\t(self\n").replace(
    "\t\t)\n\t)\n)\n", "\t\t)\n\t\t)\n\t)\n)\n")

CAP_DEMAND = "(or (not (proc0_12 96)) (gEgo has: 24))"


def test_capture_arm_creates_its_own_hold():
    print("\n-- patcher._place_capture_arm: the hold must not depend on another spec --")
    place = getattr(P, "_place_capture_arm", None)
    if place is None:
        check("the capture-arm applier is a testable function",
              False,
              detail="`patcher._place_capture_arm` does not exist -- the applier is inline in "
                     "`apply_guards`, so its text arithmetic has no test at all (F14).")
        return
    out, n, why = place(WRAPPED_HENCH, "theHenchManScript", "theHenchMan", CAP_DEMAND)
    check("an existing wrap is strengthened in place (KQ5's shipped shape)",
          why is None and n == 1
          and "(and (or (not (== global11 54)) (gEgo has: 37)) " in out and CAP_DEMAND in out,
          detail="n=%r why=%r\n%s" % (n, why, out))

    out2, n2, why2 = place(STOCK_HENCH, "theHenchManScript", "theHenchMan", CAP_DEMAND)
    check("...and a STOCK arming with no wrap gets one of its OWN, rather than refusing",
          why2 is None and n2 == 1 and CAP_DEMAND in out2
          and out2.index("(if ") < out2.index("view:"),
          detail="n=%r why=%r -- the capture hold shipped on KQ5 only because the rm54 fish "
                 "discriminator had already wrapped this send; retire that guard and this one "
                 "silently stops shipping.\n%s" % (n2, why2, out2))
    check("the whole cascade is inside the created hold, not just the setScript",
          why2 is None and out2.index("(if ") < out2.index("setCycle: Walk"), detail=out2)
    check("the file still balances", out2.count("(") == out2.count(")"), detail=out2)


def test_a_refused_arming_does_not_orphan_its_host():
    """🔴 F6, DECLARED RED 2026-08-19e -- the cure moves a PLAY-CONFIRMED emission.

    Both the fish wrap and the capture hold sit INSIDE `theHenchMan::init`, AFTER
    `(super init:)`. A refused arming therefore leaves the actor in the cast with `script == 0`,
    and rm054's verb-3 handler reads `(>= (((ScriptID 550 3) script:) state:) 1)` -- a send to
    0 -- guarded only by `(global5 contains: (ScriptID 550 3))`, which a cast-resident
    scriptless actor satisfies.

    THE INVARIANT: a wrap placed inside a host's OWN `init` must either cover `(super init:)`
    (so a refusal keeps the host out of the cast) or dispose the host on the refusal. Neither
    is what ships, on KQ5 or in the applier. Both cures change emitted bytes for a patch the
    USER has already play-tested, so this is DECLARED rather than made silently."""
    print("\n-- 🔴 a refused arming must not leave its host cast-resident (F6) --")
    place = getattr(P, "_place_capture_arm", None)
    if place is None:
        check("🔴 KNOWN GAP: the hold covers `(super init:)`, or refuses by disposing the host",
              False, detail="no `_place_capture_arm` to exercise (F14)")
        return
    out, _n, why = place(STOCK_HENCH, "theHenchManScript", "theHenchMan", CAP_DEMAND)
    i_super = out.index("(super init:)")
    i_if = out.index("(if ") if "(if " in out else len(out)
    check("🔴 KNOWN GAP: the hold covers `(super init:)`, or refuses by disposing the host",
          why is None and (i_if < i_super or "dispose:" in out),
          detail="the wrap starts at %d and `(super init:)` runs at %d, so a refused arming "
                 "adds theHenchMan to the cast with no script; rm054.sc:447-449 then sends "
                 "`state:` to 0. Cure: wrap the `init:` CALL SITES (what `fuse-arm` does), or "
                 "add `else (self dispose:)`. Both move a play-confirmed emission, so this is "
                 "declared, not slipped in." % (i_if, i_super))


def run():
    print("=== test_patch_text ===")
    test_single_arm_is_wrapped()
    test_every_matching_arm_is_wrapped()
    test_stage_match_is_structural()
    test_handsoff_ignores_comments_and_strings()
    test_unreadable_deliverer_is_not_a_cleared_one()
    test_interceptor_shape_census()
    test_arm_event_wraps_the_whole_cascade()
    test_computed_edge_exit_is_a_positional_direct()
    test_market_wrap_spares_the_reget_branch()
    test_enclosing_if_test_respects_the_else_branch()
    test_balanced_span_ignores_strings_and_comments()
    test_fuse_arm_holds_the_if_that_spawns()
    test_capture_arm_creates_its_own_hold()
    test_a_refused_arming_does_not_orphan_its_host()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
