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


def code_parens(text):
    """`(opens, closes)` counting ONLY the parens that are code.

    A raw `text.count("(") == text.count(")")` is not a balance test for SCI source and cannot
    be one: a message string is allowed to contain a lone paren, so a perfectly good file fails
    it and a file broken by an edit INSIDE a message still fails it by the same amount. Every
    fixture below that carries an unbalanced message is measured with this instead -- which is
    the same walk `patcher._skip_noncode` performs, so the test asks the question the patcher
    has to answer rather than an easier one."""
    o = c = 0
    j, n = 0, len(text)
    while j < n:
        nxt = P._skip_noncode(text, j, n)
        if nxt is not None:
            j = nxt
            continue
        if text[j] == "(":
            o += 1
        elif text[j] == ")":
            c += 1
        j += 1
    return o, c


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

# ...and the same fork held INSIDE an outer arming.
#
# ⚠️ RE-DERIVED 2026-08-20 (R2). This fixture used to assert that the search CLIMBS OUTWARD to
# `(not (proc0_12 41))` and holds there, on the reasoning that an outer `if` holding the whole
# fork in its then branch is a sound hold. It withholds the ambush, so it is sound in that one
# sense -- and it is the WRONG SITE, for the reason `trigger.py`'s `proc-arm` branch has carried
# in prose since it was written: "wrap ONLY the arming form, never its enclosing clause: the
# `else` sibling is the game's own other outcome and must stay free". Climbing outward suppresses
# `patrolScript` too, which no row derived and no spec scoped -- the wall-shaped failure this
# file's `test_stage_match_is_structural` already refuses elsewhere. The innermost `if` whose
# branch holds the arming is the game's own arming condition; when it cannot be strengthened, the
# answer is to wrap the arming STATEMENT (the shape `arm-event` and `proc-arm` both ship), not to
# gate a wider scope.
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


# ⭐ P5, 2026-08-20 FOURTH REVIEW. The one fork spelling the R2/N2 rules do not test between
# them: the arming sits in an INNER `if`'s TEST. `_depth1_else` is only ever applied to the `if`
# the scan settled on, `fork_arms` excludes `if` deliberately (an `else` is DIVERTED into, not
# withheld, which is a different failure), and the "pos is inside this test" case skipped the
# candidate with `continue` -- so an OUTER `if` found earlier in the scan stayed `best` and the
# demand landed there. That is the outward climb the docstring forbids in the same breath, and
# it walls the inner fork's BOTH arms.
#
# An arming evaluated while a test runs cannot be held by that test without duplicating it, and
# it cannot be held by any ENCLOSING test either -- suppressing it changes the value the test
# computes, so the hold decides which branch runs instead of whether the arming fires.
ARM_IN_A_TEST = """(instance rm300 of Rm
\t(method (init)
\t\t(super init:)
\t\t(if (== global5 1)
\t\t\t(if (theGuard setScript: ambushScript)
\t\t\t\t(foo)
\t\t\telse
\t\t\t\t(bar)
\t\t\t)
\t\t)
\t)
)
"""


def test_an_arming_inside_a_test_is_not_held_by_an_outer_one():
    print("\n-- P5: an arming in an `if`'s TEST has no test to be conjoined onto --")
    pos = ARM_IN_A_TEST.index("setScript: ambushScript")
    span = P._enclosing_if_test(ARM_IN_A_TEST, pos)
    check("an arming in an inner `if`'s TEST does not return the OUTER `if`'s test",
          span is None,
          detail="span=%r -> %r. Conjoining there withholds the whole inner fork, so a player "
                 "who cannot pay gets neither `(foo)` nor `(bar)` -- and suppressing an arming "
                 "the test EVALUATES decides which branch runs, which is not what a hold is "
                 "for." % (span, span and ARM_IN_A_TEST[span[0]:span[1]]))

    out, n, why = P._place_capture_arm(ARM_IN_A_TEST, "ambushScript", "rm300", "(gEgo has: 24)")
    check("...and the applier refuses rather than walling the fork",
          why is not None and n == 0 and out == ARM_IN_A_TEST,
          detail="n=%r why=%r\n%s" % (n, why, out))


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
    check("...and the search does NOT climb outward past the fork to a wider scope",
          span is None,
          detail="span=%r -> %r. `(not (proc0_12 41))` withholds the ambush, but it also "
                 "withholds `patrolScript`, which no row derived -- the game's own other "
                 "outcome. The innermost arming `if` is the only site this function may "
                 "strengthen; when it has an else, the caller wraps the STATEMENT instead."
                 % (span, span and NESTED_ELSE_ARM[span[0]:span[1]]))

    # ...and that is what the applier does with it: the ambush alone is held, and the sibling
    # the game arms on the other side of the fork is left exactly as it was.
    out, n, why = P._place_capture_arm(NESTED_ELSE_ARM, "ambushScript", "rm300",
                                       "(gEgo has: 24)")
    between = out[out.index("else"):out.index("setScript: ambushScript")] if why is None else ""
    check("the applier holds the arming STATEMENT and leaves the else sibling free",
          why is None and n == 1
          and "(and (not (proc0_12 41))" not in out          # the outer scope is untouched
          and "(if (gEgo has: 24)" in between                # the hold is inside the else
          and "\t\t\t\t(theGuard setScript: patrolScript)\n" in out,   # the sibling is stock
          detail="n=%r why=%r\n%s" % (n, why, out))


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


# ...and the fourth construct, which the 2026-08-20 review's minor list named: SCI's said and
# menu specs are `'...'`, and they are the only non-code form in this corpus that really does
# carry parens (`'(get,take)/lamp'` is a grouped alternation). Measured across the five source
# trees: 3,100 of them in code position on LSL2 and KQ4, ZERO unbalanced -- so this fixture is
# synthetic, the `test_deletion_soundness` doctrine (a game states a failure mode only if it
# happens to have one). The `"` branch `_skip_noncode` carries instead is DEAD on all five trees:
# every double quote in the corpus is inside a `{...}` message, which is consumed first.
SAID_IF = """(instance rm300 of Rm
\t(method (handleEvent param1)
\t\t(if (not (proc0_12 41))
\t\t\t(if (Said 'open/door(gate')
\t\t\t\t(proc0_29 12)
\t\t\t)
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

    pos = SAID_IF.index("setScript: ambushScript")
    span = P._enclosing_if_test(SAID_IF, pos)
    check("...and past a said spec, the one non-code form that really carries parens",
          span is not None and SAID_IF[span[0]:span[1]] == "(not (proc0_12 41))",
          detail="span=%r -> %r -- `'open/door(gate'` shifts every span computed after it"
                 % (span, span and SAID_IF[span[0]:span[1]]))


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

# ...and a spawn with no arming around it.
#
# ⚠️ RE-DERIVED 2026-08-20 (R2). This used to assert a WHOLE REFUSAL, on the doctrine that
# holding the guarded sites and leaving this one open is a claim of coverage the patch does not
# have. The doctrine is right and the assertion was the wrong way to satisfy it: once the
# applier can wrap an arming STATEMENT -- which R2 forces it to grow anyway, for the `(if ...
# else ...)` it must never conjoin onto -- the bare spawn is HELD, and full coverage beats a
# refusal at the same claim. What must never happen is the third thing: one site held, one open,
# `applied: True`. So the invariant is stated directly below, and refusal is only one way to
# meet it.
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
    check("EVERY spawn is held -- the bare one gets a wrap of its own, never left open",
          why3 is None and n3 == 2 and out3.count("softlock-guard") == 2
          and "(and (== global5 1) %s)" % DEMAND in out3
          and out3.index("(if %s" % DEMAND) < out3.index("(theCat posn: 103 115 init:)"),
          detail="n=%r why=%r held %d of 2 spawns. One site held and one open with "
                 "`applied: True` is findings #4 and #8 exactly.\n%s"
                 % (n3, why3, out3.count("softlock-guard"), out3))
    check("...and the file still balances after the mixed edit",
          out3.count("(") == out3.count(")"), detail=out3)

    out4, n4, why4 = place(SPAWNER, "proc550_16", ["theRat"], DEMAND)
    check("a host the procedure never inits is a refusal, not a guess",
          why4 is not None and n4 == 0 and out4 == SPAWNER, detail="why=%r" % (why4,))

    # THE INLINE MARKER MUST NOT EAT THE REST OF ITS LINE. `; softlock-guard` is a line comment,
    # so conjoining onto a one-line `(if <test> <arming>)` comments out the arming, the closing
    # parens and everything after them -- `applied: True`, and the file no longer compiles.
    # Measured 2026-08-20: 562 one-line `(if ...)` forms across the corpus's five source trees,
    # none of them containing an arming TODAY, which is the only reason this has never shipped.
    one_line = "(procedure (proc550_16)\n\t(if (== global5 1) (theCat posn: 91 172 init:))\n)\n"
    out5, n5, why5 = place(one_line, "proc550_16", ["theCat"], DEMAND)
    check("a ONE-LINE arming `if` is not commented out by the marker",
          why5 is None and n5 == 1 and out5.count("(") == out5.count(")")
          and out5.index("softlock-guard") < out5.index("(theCat posn:")
          and "\n" in out5[out5.index("softlock-guard"):out5.index("(theCat posn:")],
          detail="n=%r why=%r -- everything after `; softlock-guard` on that line is a "
                 "comment:\n%s" % (n5, why5, out5))


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


# === THE 2026-08-20 REVIEW: what the first round of applier fixes still got wrong ==============
#
# A second contextless review, same mandate, over the cures themselves. Three of its findings are
# defects introduced or left standing BY THAT ROUND, which is the argument for running the review
# on the fix and not only on the feature.

# R1. `_skip_noncode` was wired into `_balanced_span` and NOT into the scan that feeds it:
# `_enclosing_if_test` still enumerates candidates with a raw `finditer` over the whole file. An
# `(if` inside a message string is picked as the arming, the demand is written INTO the message,
# the arming is not held, the file stops balancing -- and the row says `applied: True`.
MESSAGE_IF = """(instance rm300 of Rm
\t(method (init)
\t\t(if (not (proc0_12 41))
\t\t\t(Print {you wonder (if (the guard saw you})
\t\t\t(theGuard setScript: ambushScript)
\t\t)
\t)
)
"""

# ...the same shape as a spawn procedure. Spelled out rather than derived from MESSAGE_IF by
# string surgery: the 2026-08-20 red built it with two `.replace` calls that dropped the
# `(method` line and left its two closing parens behind, so the fixture the fuse applier was
# measured against did not itself balance and could not have told a good edit from a bad one.
MESSAGE_IF_SPAWNER = """(procedure (proc550_16)
\t(if (not (proc0_12 41))
\t\t(Print {you wonder (if (the guard saw you})
\t\t(theCat posn: 91 172 init:)
\t)
)
"""

MESSAGE_TEXT = "{you wonder (if (the guard saw you}"


def test_an_if_inside_a_message_is_not_an_arming():
    print("\n-- the candidate scan must skip strings too, not just the span walk (R1) --")
    # ⚠️ RE-DERIVED 2026-08-20. The red as first written asked for `out.count("(") ==
    # out.count(")")` and for the marker to land after the last `}`. Neither can hold: the
    # fixture's message carries two unmatched `(` BY DESIGN, so the raw counts are 10/8 before
    # any edit and 10/8 after a perfect one; and the arming `(if` sits BEFORE the message, so a
    # correct hold lands before the `}`, not after it. What the fix actually has to deliver is
    # three things, and they are what is asked here: the message comes through byte-identical,
    # the CODE still balances, and the demand lands on the real arming test.
    for nm, fn, args, arming in (
            ("capture-arm", getattr(P, "_place_capture_arm", None),
             (MESSAGE_IF, "ambushScript", "rm300", "(gEgo has: 24)"), "(not (proc0_12 41))"),
            ("fuse-arm", getattr(P, "_place_fuse_arm", None),
             (MESSAGE_IF_SPAWNER, "proc550_16", ["theCat"], "(gEgo has: 24)"),
             "(not (proc0_12 41))")):
        if fn is None:
            check("%s: the applier exists" % nm, False)
            continue
        src = args[0]
        out, n, why = fn(*args)
        o, c = code_parens(out)
        check("%s: an `(if` inside a message text is never the arming" % nm,
              MESSAGE_TEXT in out and o == c and why is None
              and "(and %s (gEgo has: 24))" % arming in out,
              detail="n=%r why=%r code parens %d/%d (stock %r) -- the demand was written INSIDE "
                     "the message, so nothing is held and the source no longer compiles, while "
                     "the placement row reports applied=True:\n%s"
                     % (n, why, o, c, code_parens(src), out))


# R2. A demand conjoined onto the test of an `(if T ... else B)` does not merely withhold the
# arming -- it DIVERTS CONTROL INTO B. F1 asked whether `pos` sat in the else branch; it never
# asked whether the `if` HAS one. Here the else arms the very death the row exists to prevent,
# so a player who cannot pay meets Mordack instead of the cat.
ELSE_BODY_SPAWNER = """(procedure (proc550_16)
\t(if (!= global332 7)
\t\t(theCat posn: 91 172 init:)
\telse
\t\t(theWizard posn: 10 10 init: setScript: theWizardScript)
\t)
)
"""

ELSE_BODY_ARM = """(instance theHenchMan of Actor
\t(method (init)
\t\t(super init:)
\t\t(if (!= global332 7)
\t\t\t(self setScript: theHenchManScript)
\t\telse
\t\t\t(self setScript: theWizardScript)
\t\t)
\t)
)
"""


def test_a_hold_never_diverts_into_an_else_branch():
    print("\n-- conjoining onto an `if` that HAS an else diverts control into it (R2) --")
    place = getattr(P, "_place_fuse_arm", None)
    if place is None:
        check("the fuse-arm applier exists", False)
        return
    out, n, why = place(ELSE_BODY_SPAWNER, "proc550_16", ["theCat"], "(gEgo has: 24)")
    check("fuse-arm: the demand is NOT conjoined onto a test whose else runs instead",
          why is not None or "(and (!= global332 7) (gEgo has: 24))" not in out,
          detail="n=%r why=%r -- failing the demand no longer withholds the encounter, it "
                 "spawns `theWizardScript`, which is the committed death this row exists to "
                 "prevent. A hold that arms the death is worse than no hold.\n%s"
                 % (n, why, out))

    cap = getattr(P, "_place_capture_arm", None)
    out2, n2, why2 = cap(ELSE_BODY_ARM, "theHenchManScript", "theHenchMan", "(gEgo has: 24)")
    check("capture-arm: the same, on the arming shape it owns",
          why2 is not None or "(and (!= global332 7) (gEgo has: 24))" not in out2,
          detail="n=%r why=%r\n%s" % (n2, why2, out2))


# R3. `_place_fuse_arm` enumerates spawn sites as `init:` sends to the host object, but the
# ARMING of a machine is `setScript: <machine>` -- `init:` is a proxy that is right on KQ5 only
# because `theCat::init` happens to do the setScript itself. A procedure that arms the same
# machine both ways gets one site held and one left open, `applied: True sites=1`. That is
# findings #4 and #8's shape, which this file's own opening docstring exists to prevent. Note
# the two appliers shipped in ONE commit with opposite definitions of "the arming site".
MIXED_SPAWNER = """(procedure (proc550_16)
\t(if (== global11 57)
\t\t(theCat posn: 91 172 init:)
\t)
\t(if (== global11 58)
\t\t(theCat setScript: theCatScript)
\t)
)
"""


def test_every_spelling_of_the_arming_is_held():
    print("\n-- an arming spelled `setScript:` is an arming too (R3) --")
    place = getattr(P, "_place_fuse_arm", None)
    if place is None:
        check("the fuse-arm applier exists", False)
        return
    out, n, why = place(MIXED_SPAWNER, "proc550_16", ["theCat"], "(gEgo has: 24)",
                        machine="theCatScript") \
        if "machine" in getattr(place, "__code__").co_varnames else place(
            MIXED_SPAWNER, "proc550_16", ["theCat"], "(gEgo has: 24)")
    check("both armings of the same machine are held, or the applier refuses whole",
          (why is not None and n == 0) or out.count("softlock-guard") == 2,
          detail="n=%r why=%r held %d of 2 armings -- the unheld one is a spawn the player "
                 "walks straight into while the row claims the encounter is guarded.\n%s"
                 % (n, why, out.count("softlock-guard"), out))


# R1, GENERALISED -- and this half is NOT latent.
#
# The 2026-08-20 review's hand-off list said a next reviewer should take "the OTHER raw-text
# scanners ... R1 is a property of 'scan raw text for a candidate, then span from it'". Measured
# across the five source trees, one of them really does misfire TODAY: `trigger._find_region`
# takes its region from `re.search(header_re, text)`, first match wins, and KQ6's and LB2's
# `WriteFeature.sc` is a SOURCE-CODE GENERATOR whose message strings are themselves SCI source --
# `{ \t(method (doVerb theVerb)\0d\n\t\t(switch theVerb\0d\n}`. That message contains the first
# `(method (doVerb` in the file, so `_find_region` returns a 560-byte "region" that starts in the
# middle of a string, and every span computed inside it is arithmetic on text that is not code.
#
# Census of the whole family, five trees: `(instance|class` 6,356 matches / 0 in non-code;
# `(procedure (` 328 / 0; `setScript:` 2,192 / 0; `(if` 11,073 / 0; `(cond` 1,676 / 0;
# `newRoom:` 763 / 0; `put: <n>` 340 / 0 -- and `(method (` 7,747 / **2**, which are these.
# ⛔ FIVE SOURCE TREES, and `kq5` is spelled the way `config.sweep_config` finds it. Both loops
# below used to name four, so every corpus figure this file printed was a four-tree figure while
# reading as a five-tree one (2026-08-20 third review, N3).
CORPUS = ("LSL2", "KQ4", "KQ6", "dagger", "kq5")


WRITEFEATURE = """(instance WriteFeature of Code
\t(method (doit param1)
\t\t(Format
\t\t\t@temp0
\t\t\t{ \\t(method (doVerb theVerb)\\0d\\n\\t\\t(switch theVerb\\0d\\n}
\t\t)
\t)

\t(method (doVerb theVerb)
\t\t(theGuard setScript: ambushScript)
\t)
)
"""


def test_a_region_never_starts_inside_a_message():
    print("\n-- trigger._find_region: the region is code, not the text of a message --")
    import trigger as T
    span = T._find_region(WRITEFEATURE, r"\(method\s+\(doVerb\b")
    body = WRITEFEATURE[span[0]:span[1]] if span else ""
    check("the real `doVerb` method is the region, not the one quoted in a message",
          span is not None and body.startswith("(method (doVerb theVerb)")
          and "setScript: ambushScript" in body,
          detail="span=%r -> %r -- the first raw match is inside the `{...}`, so the region "
                 "starts mid-string and every span computed inside it is arithmetic on text "
                 "that is not code." % (span, body[:80]))

    import os as _os
    import re as _re
    import config
    import patcher as _P
    bad = []
    for name in CORPUS:
        cfg = config.by_name(name)
        if cfg is None or not _os.path.isdir(cfg.src_dir):
            continue
        for fn in sorted(_os.listdir(cfg.src_dir)):
            if not fn.endswith(".sc"):
                continue
            text = open(_os.path.join(cfg.src_dir, fn), errors="replace").read()
            spans = _P._noncode_spans(text)
            for (s, e) in spans:
                for hm in _re.finditer(r"\((?:method|procedure)\s+\((\w+)", text[s:e]):
                    got = T._find_region(text, r"\(%s\s+\(%s\b"
                                         % (hm.group(0)[1:].split()[0], hm.group(1)))
                    if got and s <= got[0] < e:
                        bad.append("%s/%s @%d %s" % (name, fn, got[0], hm.group(1)))
    check("...and no header quoted in any corpus message is ever taken as a region",
          not bad,
          detail="regions taken from inside a string: %r" % (bad,))

    # THE REST OF THE FAMILY, as a census rather than as a claim. Some of these scanners are
    # still raw (the arm-event / arm-clause `setScript:` searches, the clause-head walk), and
    # they are safe today for one reason only: nothing they look for is ever written inside a
    # message in these five games. That is a fact about the corpus, so it is measured here
    # rather than asserted in a docstring -- the day a new game writes one, this says so BEFORE
    # the placement built on it ships.
    #
    # ⛔ THE TRIPWIRE COULD NOT FIRE FOR THE REASON IT NAMED (2026-08-20 third review, N3). The
    # family omitted `(method (` -- THE ONE PATTERN IN THIS CORPUS WITH HITS, named in the
    # comment three lines above it -- and both loops here omitted KQ5, so every "five source
    # trees" figure this file has ever printed was a four-tree figure. Both fixed; the family
    # is now split, because a pattern that HAS non-code matches is not a failure by itself --
    # it is a requirement that every scanner reading it be code-filtered, which is what the
    # `WriteFeature` checks above and `test_a_dispatch_region_is_code` below assert.
    import bisect as _bi
    fam = {"setScript:": r"setScript:\s*\w+", "(if": r"\(if", "(cond": r"\(cond\b",
           "newRoom:": r"newRoom:", "put: <n>": r"put:\s*\d+",
           "(method (": r"\(method\s+\(", "(procedure (": r"\(procedure\s+\(",
           "(instance|class": r"\((?:instance|class)\s+\w+"}
    # Patterns KNOWN to be written inside a message in this corpus, with the reader that proves
    # it. Every scanner reading one of these goes through `sexpr.code_finditer`/`code_search`.
    QUOTED = {"(method (": "KQ6 + LB2 WriteFeature.sc, which GENERATES SCI source"}
    counts = {k: [0, 0] for k in fam}
    seen_trees = set()
    for name in CORPUS:
        cfg = config.by_name(name)
        if cfg is None or not _os.path.isdir(cfg.src_dir):
            continue
        seen_trees.add(name)
        for fn in sorted(_os.listdir(cfg.src_dir)):
            if not fn.endswith(".sc"):
                continue
            text = open(_os.path.join(cfg.src_dir, fn), errors="replace").read()
            spans = _P._noncode_spans(text)
            starts = [s for (s, _e) in spans]
            for k, pat in fam.items():
                for m in _re.finditer(pat, text):
                    i = _bi.bisect_right(starts, m.start()) - 1
                    counts[k][1] += 1
                    if i >= 0 and m.start() < spans[i][1]:
                        counts[k][0] += 1
    hot = {k: v for k, v in counts.items() if v[0] and k not in QUOTED}
    check("the still-raw scanners have nothing to trip over in this corpus",
          not hot,
          detail="matches inside non-code: %r (of %r). One of these scanners now reads text "
                 "that is not code; give it `sexpr.code_finditer` the way `_find_region` got "
                 "`code_search`." % (hot, {k: v[1] for k, v in counts.items()}))
    check("...and the corpus still writes the patterns we already know it quotes",
          all(counts[k][0] for k in QUOTED),
          detail="counted %r. A KNOWN-quoted pattern with zero hits means this census stopped "
                 "reading the files it thinks it reads -- which is exactly how `(method (` and "
                 "KQ5 went missing from it. %r" % ({k: counts[k] for k in QUOTED}, QUOTED))
    check("...over all five source trees, not four",
          len(seen_trees) == len(CORPUS),
          detail="read %r of %r. Every 'five source trees' figure this file prints is a "
                 "%d-tree figure." % (sorted(seen_trees), list(CORPUS), len(seen_trees)))


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
    USER has already play-tested, so this is DECLARED rather than made silently.

    ⛔ AND IT IS NOT A KQ5 SHIPPING HAZARD [USER, play, 2026-08-20]. Play-confirmed: prop the
    grate with the iron bar, tug it, nothing happens and nothing crashes -- the ambush needs an
    UNEQUIPPED arrival at rm54, and our own boat guard demands the Iron_Bar (30) and the
    Fishhook (31) at all three of `boatRegion`'s `leave` armings, so `theHenchMan::init` never
    runs there. This red is about the APPLIER, for the next game whose refusal IS reachable;
    the declaration used to read as though a shipped patch could crash, which it cannot."""
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


def is_code(text, idx):
    """True when offset `idx` in `text` is CODE -- not inside a comment or a quoted form.

    The question every assertion below about "did the edit keep X" has to ask. `X in out` is
    not that question: a `;` line comment leaves every byte after it in the file, perfectly
    greppable, and completely gone from the program."""
    import bisect
    spans = P._noncode_spans(text)
    starts = [s for (s, _e) in spans]
    i = bisect.bisect_right(starts, idx) - 1
    return not (i >= 0 and idx < spans[i][1])


# ⭐ N1, 2026-08-20 THIRD REVIEW. `; softlock-guard` IS A LINE COMMENT -- and the fix for that
# went into `_conjoin_marked` only, twenty lines from `_wrap_statement`, which is the emitter R2
# routes to whenever the conjoin is refused. R2 made that the COMMON path: 774 of the corpus's
# 780 one-line `(if ...)` forms carry a depth-1 `else`, and every one of them is now disqualified
# from the conjoin and handed here. Measured 2026-08-20 across all five source trees.
#
# The failure is not a broken build -- that would be the lucky case. When the eaten text happens
# to balance, the file still compiles and an arming, an assignment or the game's own other
# outcome has been silently DELETED, with the placement row reporting `applied: True`.
TAIL_SIBLING = """(procedure (proc550_16)
\t(theCat init:) (theRat init:)
)
"""

# ...and R2's own fallback shape: nothing may be conjoined onto this `if`, so the arming
# statement inside it is wrapped -- in the middle of a line whose remainder is the else.
ONE_LINE_FORK = """(procedure (proc550_16)
\t(if (== global5 1) (theCat posn: 91 172 init:) else (theRat init:))
)
"""

# The other half of N1: `_arming_statement_span` returns the INNERMOST balanced form, which is
# routinely an expression in VALUE position. Wrapping `(theCat init: yourself:)` where the game
# wrote `(= [local0 0] (theCat init: yourself:))` does not withhold the arming, it changes what
# is assigned -- and `(if ...)` in an argument slot is not the same program. 76 `init:` sends
# corpus-wide have text after them on their line; the value-position spelling is KQ6's and LB2's.
VALUE_POSITION_ARM = """(procedure (proc550_16)
\t(= [local0 0] (theCat init: yourself:))
)
"""


# The travel-dispatch applier's own copy of R1's shape: it picks the doVerb method with a raw
# first-match-wins `re.search`, and `(method (` is THE pattern this corpus writes inside a
# message. The fixture is KQ6's magic map with a `WriteFeature`-style source generator standing
# before it -- one whose quoted text carries a whole cond arm, so the raw scan does not merely
# miss the real method, it computes an edit span inside the string.
DISPATCH_SRC = """(instance mistIsle of Feature
\t(properties
\t\ttpRoom 550
\t)
)

(instance sourceWriter of Code
\t(method (doit)
\t\t(Format @temp0 {\\t(method (doVerb theVerb)\\0d\\n\\t\\t(cond\\0d\\n\\t\\t\\t((== theVerb 5)\\0d\\n})
\t)
)

(instance pullOutMapScr of Script
\t(method (doVerb param1)
\t\t(cond
\t\t\t((== param1 5)
\t\t\t\t(global2 newRoom: (local8 tpRoom:))
\t\t\t)
\t\t)
\t)
)
"""


def test_a_dispatch_region_is_code():
    """N3's other half: `(method (` is read RAW by a second applier, not just `_find_region`."""
    print("\n-- patcher._guard_travel_dispatch: the doVerb it guards is code --")
    import shutil as _sh
    import tempfile as _tf
    dest = _tf.mkdtemp(prefix="sgdispatch")
    try:
        os.makedirs(os.path.join(dest, "src"))
        path = os.path.join(dest, "src", "pullOutMapScr.sc")
        open(path, "w").write(DISPATCH_SRC)
        row = P._guard_travel_dispatch(
            dest, {"to_room": 550, "condition": "(gEgo has: 24)"}, {}, set())
        out = open(path).read()
        quoted = DISPATCH_SRC[DISPATCH_SRC.index("{"):DISPATCH_SRC.index("}") + 1]
        check("the guard lands on the real doVerb arm, not the one quoted in a message",
              row is not None and row.get("applied") and row.get("sites") == 1
              and quoted in out and code_parens(out)[0] == code_parens(out)[1]
              and "softlock-guard" in out
              and is_code(out, out.index("softlock-guard") - 40),
              detail="row=%r\nmessage preserved=%r code parens=%r\n%s"
                     % (row, quoted in out, code_parens(out), out))
    finally:
        _sh.rmtree(dest, ignore_errors=True)


def test_form_chain_is_the_nesting_and_nothing_else():
    """The walk `statement_span`, `fork_arms` and `_enclosing_form` all rest on.

    ⛔ REGRESSION GUARD, and it earned it immediately. The first cut closed each chain level at
    the first `)` that returned the scan to that DEPTH -- but a SIBLING that opens and closes
    after a level has already closed returns to the same depth, so the level's end was
    overwritten with the sibling's. `(a (b (c) (d)) (e))` reported `(b (c) (d)) (e)` as the form
    at offset 3, and the two appliers then computed overlapping holds and refused whole."""
    print("\n-- sexpr.form_chain: innermost first, and each form ends where IT ends --")
    import sexpr as S
    t = "(a (b (c) (d)) (e))"
    for pos, want in ((0, ["(a (b (c) (d)) (e))"]),
                      (3, ["(b (c) (d))", "(a (b (c) (d)) (e))"]),
                      (6, ["(c)", "(b (c) (d))", "(a (b (c) (d)) (e))"]),
                      (10, ["(d)", "(b (c) (d))", "(a (b (c) (d)) (e))"]),
                      (15, ["(e)", "(a (b (c) (d)) (e))"])):
        got = [t[a:b] for (a, b) in S.form_chain(t, pos)]
        check("form_chain at %d is the nesting, innermost first" % pos, got == want,
              detail="got %r, want %r -- a sibling after the close must not extend the form"
                     % (got, want))
    # ...and a `(` inside a message opens nothing
    m = "(a {a ( message} (b))"
    got = [m[x:y] for (x, y) in S.form_chain(m, m.index("(b)"))]
    check("form_chain: a paren inside a message is not a form",
          got == ["(b)", m], detail="got %r" % (got,))


def test_statement_span_climbs_out_of_value_positions_only():
    """N1b's walk, on the spellings a `cond` clause test actually takes.

    ⛔ REGRESSION GUARD. The first cut decided "am I a clause?" from the PARENT's head, which
    reads `((> a b) ...)` and `(57 ...)` correctly and KQ5's own `(local2 (= local2 0) (self
    setScript: bringCedric))` as a SEND -- so the walk climbed out of the clause, past the
    `cond`, and returned the whole fork. Measured: `kq5/src/rm046.sc`, the one emitted file
    that moved, with the guard wrapping 70 lines instead of one send."""
    print("\n-- sexpr.statement_span: a clause test can be anything, and often is --")
    import sexpr as S
    T = """(method (doit)
\t(cond
\t\t(local2
\t\t\t(= local2 0)
\t\t\t(self setScript: bringCedric)
\t\t)
\t\t((> a b) (theRat init:))
\t\t(else (foo))
\t)
)"""
    for probe, want in (("(self setScript:", "(self setScript: bringCedric)"),
                        ("(theRat init:)", "(theRat init:)"),
                        ("(foo)", "(foo)")):
        span = S.statement_span(T, T.index(probe))
        got = T[span[0]:span[1]] if span else None
        check("statement_span: a clause body is a statement (%s)" % probe.strip("("),
              got == want, detail="got %r, want %r" % (got, want))
    SW = "(method (doit) (switch (self kind:) (5 (theCat init:)) (6 (bar))))"
    span = S.statement_span(SW, SW.index("(theCat"))
    check("statement_span: a switch CASE body is a statement",
          span and SW[span[0]:span[1]] == "(theCat init:)",
          detail="got %r" % (span and SW[span[0]:span[1]],))
    check("statement_span: the switch VALUE is not -- evaluating it CHOOSES the branch",
          S.statement_span(SW, SW.index("(self kind:)")) is None,
          detail="got %r" % (S.statement_span(SW, SW.index("(self kind:)")),))
    V = "(procedure (p)\n\t(= [local0 0] (theCat init: yourself:))\n)"
    span = S.statement_span(V, V.index("(theCat"))
    check("statement_span: an argument climbs to the assignment that stores it",
          span and V[span[0]:span[1]] == "(= [local0 0] (theCat init: yourself:))",
          detail="got %r" % (span and V[span[0]:span[1]],))
    TEST = "(procedure (p)\n\t(if (not (self init: param1)) (foo))\n)"
    check("statement_span: an arming inside a TEST has no statement of its own",
          S.statement_span(TEST, TEST.index("(self init:")) is None,
          detail="got %r -- holding it would duplicate the test"
                 % (S.statement_span(TEST, TEST.index("(self init:")),))


def test_mark_line_asks_whether_code_is_at_risk():
    print("\n-- sexpr.mark_line: what a `;` can destroy is CODE, not bytes --")
    import sexpr as S
    push = "  ; M\n\t"
    for tail, want, why in (
            ("", "  ; M", "nothing follows"),
            ("   ", "  ; M", "whitespace only"),
            ("  ; already a comment", "  ; M", "a comment cannot be destroyed by a comment"),
            (" (theRat init:)", push, "a statement"),
            (" {a message}", push, "a message argument"),
            (" 'said/spec'", push, "a Said spec")):
        got = S.mark_line("(a)%s\n" % tail, 3, "  ; M")
        check("mark_line: %s" % why, got == want, detail="tail=%r -> %r, want %r"
                                                         % (tail, got, want))
    # LB2's rm520, the corpus's one live instance: two act-flip rows conjoin onto the SAME
    # head, so the second row's marker is spliced in front of the first row's. Pushing there
    # would move the bytes of a play-confirmed patch to protect a comment.
    check("mark_line: a second marker rides the first one's line, as LB2 ships it",
          S.mark_line("((and X Y))  ; softlock-guard: hold the act flip\n", 11,
                      "  ; softlock-guard: hold the act flip") ==
          "  ; softlock-guard: hold the act flip")


def test_the_marker_never_eats_the_line():
    print("\n-- N1: a `;` marker must not comment out the rest of its line --")
    out, n, why = P._place_fuse_arm(TAIL_SIBLING, "proc550_16", ["theCat"], DEMAND)
    check("a sibling statement on the arming's own line survives the hold",
          why is None and n == 1 and is_code(out, out.index("(theRat init:)")),
          detail="n=%r why=%r -- `(theRat init:)` is still in the file and no longer in the "
                 "program: everything after `; softlock-guard` on that line is a comment.\n%s"
                 % (n, why, out))

    out2, n2, why2 = P._place_fuse_arm(ONE_LINE_FORK, "proc550_16", ["theCat"], DEMAND)
    check("R2's fallback on a one-line `(if ... else ...)` keeps the else",
          why2 is None and n2 == 1
          and is_code(out2, out2.index("(theRat init:)"))
          and code_parens(out2)[0] == code_parens(out2)[1],
          detail="n=%r why=%r code parens %r -- R2 disqualifies this `if` from the conjoin and "
                 "hands it to the statement wrap, whose marker then eats `else (theRat "
                 "init:))`. The file does not compile.\n%s"
                 % (n2, why2, code_parens(out2), out2))

    out3, n3, why3 = P._place_fuse_arm(VALUE_POSITION_ARM, "proc550_16", ["theCat"], DEMAND)
    i_if = out3.index("(if ") if "(if " in out3 else len(out3)
    check("an arming in VALUE position is held as a statement, not rewritten in place",
          why3 is None and n3 == 1
          and i_if < out3.index("(= [local0 0]")
          and code_parens(out3)[0] == code_parens(out3)[1],
          detail="n=%r why=%r code parens %r -- the hold went INSIDE `(= [local0 0] ...)`, so "
                 "the assignment now stores the value of an `if` and the closing paren of the "
                 "assignment is inside the marker's comment. The arming statement is the "
                 "assignment, which is what the stock no-spawn path also skips.\n%s"
                 % (n3, why3, code_parens(out3), out3))


# ⭐ N2, 2026-08-20 THIRD REVIEW. R2's doctrine -- "the game's own other outcome must stay free"
# -- is enforced for the `else` SPELLING alone. `_depth1_else` looks for the four letters `else`
# and nothing else, so a `cond` or a `switch` standing between the arming and the `if` is
# invisible: the search widens straight past the fork it should have stopped at, and the demand
# lands on the `if` that holds the WHOLE fork. A player who cannot pay then gets neither arm --
# the wall R2's own docstring forbids, reached by a different spelling of the same shape.
COND_FORK = """(procedure (proc550_16)
\t(if (> (Random 0 100) 20)
\t\t(cond
\t\t\t((> global11 5)
\t\t\t\t(theCat init:)
\t\t\t)
\t\t\t(else
\t\t\t\t(theRat init:)
\t\t\t)
\t\t)
\t)
)
"""

SWITCH_FORK = """(procedure (proc550_16)
\t(if (> (Random 0 100) 20)
\t\t(switch global11
\t\t\t(57
\t\t\t\t(theCat init:)
\t\t\t)
\t\t\t(58
\t\t\t\t(theRat init:)
\t\t\t)
\t\t)
\t)
)
"""


def test_a_fork_between_the_if_and_the_arming_is_not_climbed_past():
    print("\n-- N2: a `cond`/`switch` fork is a fork, whatever it is spelled --")
    for name, src in (("cond", COND_FORK), ("switch", SWITCH_FORK)):
        span = P._enclosing_if_test(src, src.index("(theCat init:)"))
        check("a `%s` arm's arming does not return the outer `if`'s test" % name,
              span is None,
              detail="span=%r -> %r. Conjoining there withholds the WHOLE %s, so the player "
                     "who cannot pay gets neither the cat nor the rat -- and the rat is the "
                     "game's own other outcome, which no row derived and no spec scoped."
                     % (span, span and src[span[0]:span[1]], name))

        out, n, why = P._place_fuse_arm(src, "proc550_16", ["theCat"], DEMAND)
        held = None
        if why is None and "(if %s" % DEMAND in out:
            hs = out.index("(if %s" % DEMAND)
            held = out[hs:P._balanced_span(out, hs)]
        check("...and the applier holds the arming alone, leaving the sibling arm free (%s)"
              % name,
              why is None and n == 1 and held is not None
              and "(theCat init:)" in held and "(theRat init:)" not in held,
              detail="n=%r why=%r\nheld: %r\n%s" % (n, why, held, out))


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
    test_an_arming_inside_a_test_is_not_held_by_an_outer_one()
    test_balanced_span_ignores_strings_and_comments()
    test_fuse_arm_holds_the_if_that_spawns()
    test_capture_arm_creates_its_own_hold()
    test_an_if_inside_a_message_is_not_an_arming()
    test_a_hold_never_diverts_into_an_else_branch()
    test_every_spelling_of_the_arming_is_held()
    test_a_region_never_starts_inside_a_message()
    test_a_refused_arming_does_not_orphan_its_host()
    test_form_chain_is_the_nesting_and_nothing_else()
    test_statement_span_climbs_out_of_value_positions_only()
    test_mark_line_asks_whether_code_is_at_risk()
    test_a_dispatch_region_is_code()
    test_the_marker_never_eats_the_line()
    test_a_fork_between_the_if_and_the_arming_is_not_climbed_past()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed"
          + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
