"""LB2 (Laura Bow 2, `dagger`) stranding ORACLE -- the third enumerated ground truth.

The oracle it enforces is `docs/LB2-ORACLE.md`, re-derived 2026-08-06 from the game source plus
six walkthrough/hint sources (`docs/refs/lb2/`). Same two rules as KQ4 and KQ6:

  * A DROP from EXPECTED_CAUGHT is a REGRESSION -> STOP and confirm before touching the list.
  * An ADDITION is treated with SUSPICION -> confirm. It may be a real new catch to promote out of
    KNOWN_GAPS, or a false positive.

WHY THIS FILE EXISTS, given `test_watched_surface` already freezes LB2's surface. The watched
surface answers "did anything move?"; it cannot answer "is what we emit RIGHT?", because it was
refreshed from our own output. This file is the other half: the verdicts here come from the game's
scripts and Sierra's hint file, not from a previous run of ours. When LB2's act modelling lands,
the watched surface will report the change and THIS file will say whether the change was the one
we wanted.

✅ THE DELIBERATE RED THIS FILE CARRIED (`the act-boundary carries are caught`) WAS PROMOTED
2026-08-10: all four real carries are caught and live in EXPECTED_CAUGHT, and the fifth row,
eveningGown, was RULED *"act 2 gate, not a softlock"* -- the gown is the act-1 break's own
precondition (see the wearingGown mechanism pins below), so it moved to NEVER_STRANDABLE. The
`skeletonKey` false positive that used to trip the suspicion check was closed the same day
(§7ad: a hands-on wait with the Script clock running is pre-emptable).

✅ THE STREET SEAL WAS DECLARED RED AND PROMOTED THE SAME DAY (2026-08-10). Ground truth [user,
§7z]: *"the outside of the museum is not reachable once the museum acts start"* -- the model
walked the street at acts 1-5, and the "positional, census-#1" diagnosis turned out to be only
the last link of a chain whose other links were derivable: the departing-init rule, the
dead-letter nav rule, and relational lowering over a register's own value universe (§7ag). The
check below is now a permanent green pin; the file again declares NO red.

⚠️⚠️ THE EXPLANATION THAT USED TO SIT HERE WAS REFUTED. Read this before writing another one. It
said: *the act counter is modelled and the act STRUCTURE is not; ordering the counter changed no
verdict because the act gates what rooms PUT IN THEMSELVES rather than their doors; until an
act-gated `init:` on a door means "this edge is not there in this state", no act boundary can be a
frontier.* Every observation in it was true when written and the CONCLUSION was still wrong -- there
are ZERO act-gated door inits corpus-wide (§7q/§7r), so the remedy it demanded does not exist to be
built. What actually closed cheese and snakeOil was letting `register_strandings` walk the JOINT
projections (§7y): act 5's two exits kill you on arrival, so the way out is the disjunction
`12 != 420 OR 123 != 5`, and a detector iterating one register at a time lets each alternative
through in the projection that cannot see the other. **This file's DIAGNOSIS has now been wrong
three times while its VERDICT columns stayed right. That is the argument for the structure below:
the columns come from the game, and the notes must come with the measurements they rest on.**

THE STRUCTURAL NOTES BELOW ARE THE POINT OF THIS FILE AS MUCH AS THE ITEM COLUMNS. A red test can
outlive its diagnosis -- this one's first version blamed the orphaned act write, which was true
when written and fixed hours later -- so the notes print the measurements the RED's explanation
rests on, and the explanation must be re-read whenever they move.

⚠️ AND A CORRECTED NUMBER, because a red test protecting a stale diagnosis is its own failure mode
(see memory `kq6-wedding-fuse-is-kq4-clock-class`). This file first said "0 of 193 edges carry
global123". That used `edge_demands`, the ITEM view. The REGISTER view -- `s._emeta`, which is what
movement actually consults -- carries an act requirement on 35 of 193 edges, all five act-break
destinations included. The structural check below reads `_emeta`, not `edge_demands`.

Provenance is recorded per row, because it differs: the five ending items are read out of
`rm750`'s own selector, the carries are cross-checked source-vs-walkthrough, and the three
formerly-CONTESTED rows were source-checked at the user's request and RULED SAFE 2026-08-10 --
pending the play test recorded in docs/LB2-ORACLE.md §9 (the act-5 chase may be tighter in play
than in the scripts).
"""
import os
import sys

import config
import missability as M

# --- The oracle -------------------------------------------------------------------------------

# A -- REAL, AND WE CATCH IT. A drop here is a regression.
EXPECTED_CAUGHT = {
    # The four-way ending selector in rm750.sc:318-380 tests exactly these five with `has:`.
    # Read out of the game; every walkthrough's 13-item "conviction list" is WRONG about which
    # ones the game actually checks. Caught because rm750 is terminal, so `rm26->rm750` -- the
    # act-6 break -- is a genuine one-way frontier.
    "wireCutters",       # has: 10
    "daggerOfRa",        # has: 11
    "bifocals",          # has: 26
    "redHair",           # has: 27
    "grapes",            # has: 31
    # pressPass spans acts 1->2, and since the 2026-08-10 surface (blessed row by row) it is
    # caught FOR THAT REASON: `analyze` flags it needed at rm250 past the act-1->2 frontier
    # edges. The `dangerous_sinks` row on the three `put: 6` sites -- the wrong-reason catch the
    # old comment here described -- retired in the same blessed diff. The mechanism pin below
    # holds the new, correct shape.
    "pressPass",
    # The four act-boundary carries, ⭐ PROMOTED FROM KNOWN_GAPS 2026-08-10 -- each was a declared
    # RED until its cause landed (§7s: the act register could run backwards; §7y: the act-5 walls
    # are deaths on entry and `register_strandings` walks the joint projections). From here on a
    # drop is a regression, which is the point of the promotion.
    "snakeOil",          # act 3 rm630 -> acts 4 and 5. And it is a COUNTER, not just a `has:`:
                         # global150 (init 4 in Main, refilled to 4 at rm610 but only while the
                         # vat's cel < 3), and rm730's act-5 cobra nest tests `(== global150 0)`
                         # -> sThrowBottle -> `put: 14`, DESTROYING it. ⚠️ The row we catch is the
                         # ITEM carry; the ruled-in-scope empty-bottle-at-act-5 death (enter act 5
                         # with global150 == 0) has NO detector yet -- docs/LB2-ORACLE.md §5a, §8.
    "cheese",            # act 3 rm650 -> act 5 rm740; rm650 is act 3/4 only
    "snakeLasso",        # act 3 rm640 -> act 5 rm700 (the mummy-case hook)
    "smellingSalts",     # act 4 rm525 -> act 5 rm720 (revive Steve)
}

# B -- REAL, AND WE MISS IT. ✅ EMPTY SINCE 2026-08-10 -- the four real act-boundary carries are
# all CAUGHT (promoted into EXPECTED_CAUGHT above, where a drop is a loud regression), and the
# fifth row, eveningGown, was RULED not a softlock at all -- see NEVER_STRANDABLE. The KNOWN_RED
# check this column fed is deleted, per the promotion half of the run_tests contract: a closed gap
# that stays listed as red is how a real fix gets landed, forgotten, and undone.
KNOWN_GAPS = set()

# C -- ✅ RULED SAFE 2026-08-10 (formerly CONTESTED since 2026-07-26). The walkthroughs called
# these fatal carries; the user delegated a source check (*"should be checked"*), every one
# resolved to the respawn idiom AT THE POINT OF USE with the game's own act-5 chase costume branch
# (`view 426`) proving mid-chase re-acquisition is designed for, and the user then ruled: *"let's
# mark those safe."* NOT in ALLOWED -- flagging one of these is now a false positive, which is the
# whole point of the column move.
#
# ⚠️ [USER, same ruling] *"let's remember to put them in a play test plan later. The walkthroughs
# I've seen have you get them in earlier acts and I suspect that's because the act 5 chase is very
# tight."* So the safety of all three rests on a SOURCE reading of act-5 re-acquisition under the
# chase clock, and that is exactly the kind of claim a play test settles. The plan is recorded in
# docs/LB2-ORACLE.md §9 (PLAY-TEST PLAN); do not silently drop it.
SAFE_RULED = {
    "workBoot",          # rm720:46 re-places it, NO act test; rm720 IS the act-5 use room (verb
                         # 23 on steve -> `put: 12` + sGetUp); both sGetBoot armings plain takes.
    "wire",              # sourced AND used at rm430; wireEnd inits acts 4+5 (`not flag44` = not
                         # already cut); sGetThatWire dresses the ego in the act-5 running view
                         # 426; the use (verb 44 -> sWireItShut) is act-5-only. The strandable
                         # link is the wireCutters, already column A.
    "dinoBone",          # rm480:79 respawn guard, NO act test; NEVER consumed (zero `put: 18`);
                         # uses rm500 (<=act4 by its own guard), rm600, rm650 -- same museum block.
}
CONTESTED = set()        # empty since 2026-08-10; kept because the checks below reference it

# D -- OUT OF SCOPE by the user's 2026-07-26 "gate on ITEMS only" ruling. Flagging one is not
# wrong exactly, but their ABSENCE is correct behaviour and must not be filed as a gap.
# magnifier / pippin_sPad were in the old §5 carry list; measured 2026-08-06, neither has a
# downstream `has:` use site at all -- their need runs through evidence examination and the riddle
# UI respectively, which is the layer the ruling excludes.
OUT_OF_SCOPE = {
    "magnifier", "pippin_sPad",
    "pocketWatch", "garter", "ankhMedallion", "watney_sFile",
    "warthogHairs", "carbonPaper", "yvette_sShoe",
}

# D'' -- CANNOT BE STRANDED, EVER. Flagging one of these is a FALSE POSITIVE, not a promotion
# candidate, and the check below is a real assertion about the game rather than a scoring rule.
#
# [USER GROUND TRUTH 2026-08-10] *"the notebook gets granted during a cutscene at the very
# beginning. There's no way to not have it in the game."* An item the opening cutscene hands you
# on a path every player takes has no state in which you lack it, so no seal can strand it and no
# remedy should ever demand it.
#
# ⚠️ THIS WAS A LIVE TRAP AND IT SPRANG. The variadic-`get:` read LANDED 2026-08-10 and did
# exactly what this check was written to catch: `notebook` gained sources at rm29/rm100/rm220
# (rm220's is the very cutscene above) and was flagged. Two things had to be true for that, and
# only one of them was the source read:
#
#   * the intro is SKIPPABLE -- `intro::handleEvent` (script 92, a Rgn live in rooms 100..220)
#     claims ESC and runs `sFadeToBlack` -> `newRoom: 26` -- so rm110..rm220 really do have edges
#     to the act break that bypass rm220's grant. The model was right about that;
#   * ...and the notebook looked REQUIRED at rm300, which it is not. `rm300`'s bar door arms
#     `sEnterBar` from verb 4, verb 6 AND verb 14, and 14 is the notebook's `message` -- a
#     SYNONYM for "talk to the doorman". Reading each machine entry on its own made one arm of
#     that fork a requirement of the room.
#
# Cured at the second point, where the fault was: `missability`'s `required` now reads a
# machine's entry guards through the intersection of `_own_required` over every entry, so an item
# only SOME armings demand is not a gate. Corpus-neutral -- LSL2, KQ4 and KQ6 snapshots
# byte-identical -- and on LB2 it also drops `daggerOfRa`/`wireCutters` from `required@460`, where
# `sCutRope` is armed by verb 21 (wireCutters) OR verb 22 (daggerOfRa) and neither is individually
# faced. Both items stay caught on rm750's ending selector.
#
# See [[commit-rule-and-red-tests]]: a green check that asserts something true is the point.
NEVER_STRANDABLE = {
    "notebook",          # opening cutscene, rm220 `(global0 get: -1 2)` -- unavoidable
    # [USER RULING 2026-08-10] *"evening gown: act 2 gate, not a softlock."* The derived mechanism
    # (pinned green below): the ACT 1 -> ACT 2 break itself demands `wearingGown`, and the only
    # act-1 writer of that property costs the gown -- so the gown is the boundary's own
    # precondition, not a carry across it, and no reachable state loses access to it (rm270 gives
    # it unconditionally; rm250/rm270/rm320 are one strongly-connected act-1 block). Flagging it
    # would mean a fabricated seal or a lost source -- an FP, not a promotion. §7ab.
    "eveningGown",
}

# D' -- IN SCOPE, BUT NOT DEMANDED [user ruling, 2026-08-09: "I don't mind catching it"].
# waterGlass sat in OUT_OF_SCOPE on the stated ground that it had no `has:` use site. That reason
# was FACTUALLY WRONG (docs/LB2-ORACLE.md §7u.5): LB2's use sites are VERB-DISPATCHED via the
# inventory item's `message` property -- waterGlass is `message 38`, and rm510/560/600/610 declare
# `listenVerb 38` on their doors -- so grepping `has: N` cannot see them. And eavesdropping is not
# dialogue flavour: listening drives `global111`, a promoted counter that gates room content (§7v).
#
# ⚠️ BUT IT DOES NOT GATE AN ACT TRANSITION, which is the question that decides the column
# [measured 2026-08-09, §7x -- do not restate this from the §7v summary, which only said "the act
# break writes it"]. `actBreak.sc`'s switch is on `global123` ALONE; it never reads `global111`. The
# traffic runs the other way and it ERASES listening progress: the act-3->4 arm does an
# unconditional `(= global111 11)`, and `triggerAndClock.sc:45` forces `15` at 3:00. The act-4->5
# break is gated on `(and (== global123 4) (global0 has: 31))` -- grapes, already column A. The one
# place listening touches MOVEMENT is `rm510.sc:123` `(if (proc999_5 global111 0 6 10 14) (eastDoor
# locked: 1))` -- `proc999_5` is OneOf (`System.sc:81`) -- and both of those forced writes land
# outside that set, so the door cannot stay locked across an act.
#
# Hence ALLOWED, not EXPECTED: catching it is welcome, missing it is not a gap to chase. Anything
# whose need runs through the excluded evidence layer but which the model may legitimately reach
# through a real use site belongs here rather than in either column.
ALLOWED_NOT_DEMANDED = {
    "waterGlass",        # message 38; listenVerb on the rm510/560/600/610 doors -> global111
}

# Anything the model may flag without the run counting as a surprise.
ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS | CONTESTED | ALLOWED_NOT_DEMANDED

# --- THE MECHANISM PINS [user ruling 2026-08-09: "pin whole deserialized objects, not names"] --
# The name-set checks stay as the coarse gate; these rows are the churn-engine insurance. LB2
# twice counted a false positive that happened to NAME an oracle item as a win (snakeLasso at
# rm700 cost two sessions of planning -- memory `oracle-must-pin-the-mechanism`), because
# `caught` is a flat union over eight detectors and the mechanism was never checked. So every
# column-A item pins the FULL set of detector rows that catch it, in the shapes `snapshot.py`
# freezes where one exists (a row here can be eyeballed against the watched surface). Two rules,
# the oracle's own: a pinned row DROPPING or CHANGING is a regression -> STOP and confirm; a row
# APPEARING is suspicion -> confirm, then re-pin with the user's OK.
#
# Provenance: hand-checked against the game 2026-08-10, the day the 38-row surface diff was
# blessed row by row. The joint seal `(12, 123)=(26, 5)` is "standing on the act-break card with
# the act counter at 5" -- act 5's street exits kill you on arrival, so the way out of the pair
# is the disjunction neither scalar projection can see (§7y). `(250, 5)` is the same seal seen
# from rm250. Source room 29 in the analyze rows is the inventory pseudo-room every item lists.
MECHANISM_ROWS = {
    # The five ending items: rm750's own selector, rm26->rm750 the genuine one-way frontier.
    # ⭐ RE-PINNED 2026-08-10 WITH THE STREET SEAL (§7ag): the joint-seal WITNESSES moved out of
    # the sealed street -- `(250, 5)` was "standing in the street at act 5", a state the game
    # never has, and the seal replaced it with real act-4/5 standing rooms (rm454, rm520) --
    # and wireCutters' still-needed list gained rm435 (the wire-cut cutscene). Confirmed
    # row-by-row against the game the day the seal landed.
    "wireCutters": {
        "analyze: need@rm750 sources=[29, 640] frontier=rm26->rm750",
        "register_strandings: reg(12, 123)=(26, 5)->[435, 500, 750]",
        "register_strandings: reg(12, 123)=(520, 5)->[750]",
    },
    "daggerOfRa": {
        "analyze: need@rm750 sources=[29, 620] frontier=rm26->rm750",
        "register_strandings: reg(12, 123)=(26, 5)->[500, 750]",
        "register_strandings: reg(12, 123)=(520, 5)->[750]",
    },
    "bifocals": {
        "analyze: need@rm750 sources=[29, 500] frontier=rm26->rm750",
        "register_strandings: reg(12, 123)=(454, 5)->[750]",
    },
    "redHair": {
        "analyze: need@rm750 sources=[29, 500] frontier=rm26->rm750",
        "register_strandings: reg(12, 123)=(454, 5)->[750]",
    },
    "grapes": {
        "analyze: need@rm750 sources=[29, 525] frontier=rm26->rm750",
        # ...and the act-4->5 break itself demands the grapes (`(and (== global123 4)
        # (global0 has: 31))`), which is why the scalar 123=5 row exists for it too.
        "register_strandings: reg123=5->[520, 750]",
        "register_strandings: reg(12, 123)=(26, 5)->[750]",
        "register_strandings: reg(12, 123)=(520, 5)->[750]",
    },
    # pressPass: THE STREET SEAL GAVE IT ITS TRUE MECHANISM (2026-08-10, §7ag). The register
    # rows are the act-1->2 carry itself: cross into act 2 without the pass and rm335 -- the
    # fundraiser door, which still `has:`-checks it -- is sealed off from the pass's only
    # source (rm235, act-1 street). The joint witnesses are the crossing states (the intro-skip
    # room 110 and the break card at act 2; rm330 standing at act 3); the scalar 2 and 5 rows
    # are the flat projection of the same stranding. The analyze row is the older, coarser
    # spelling of the same fact and rides along.
    # 2026-08-10 (need retirement, §7ai): rm26->rm420 AND rm26->rm355 LEFT the analyze
    # frontier -- each crossing's own act commit leaves both need rooms dead
    # (`crossing_retires_need`): rm250 is room-dead past act 1 (the street seal), and rm335's
    # one need site is the sGiveInvite arming, whose `123==2` condition the delegate rule
    # carries in from the doorman's guarded init (`extract.delegate_slots` +
    # `required_guards`). Demanding the pass at either break would have WALLED it -- the pass
    # is surrendered at the act-2 door, a required story step. rm26->rm330 stays: (335, act 2)
    # is live past that crossing, and its wrap is how the real act-1->2 carry is enforced.
    # ⭐ THREE ROWS RETIRED 2026-08-14 (the pre-flip reachability tightening), and the USER's
    # ruling the same day says they SHOULD go: *"the press pass in LB2 is not a real stranding:
    # you can't even get the cab to go anywhere without it, so you're definitely not reaching
    # the act break"* -- the pass is an act-1 GATE, the eveningGown class. `reg(12,123)=(330,3)`,
    # `reg123=2` and `reg123=5` each rested on a pre-flip state no pass-less player can occupy,
    # so the flip was never what stranded the pass; the tightening reads those as arrivals.
    # ⚠️ The two joint rows below SURVIVE and, by that same ruling, are also not real strandings
    # -- they are the standing §7am family, and retiring them needs the possession proof
    # ("the crossing implies the item is already held", hops A/C/D in the memory), not this
    # change. They stay pinned as the honest statement of where the model still over-claims.
    "pressPass": {
        "analyze: need@rm250 sources=[29, 235] "
        "frontier=rm210->rm250|rm26->rm330|rm280->rm250",
        "register_strandings: reg(12, 123)=(110, 1)->[335]",
        "register_strandings: reg(12, 123)=(110, 2)->[335]",
    },
    # ⚠️ THE VALUE IN A SURVIVING ROW'S NAME IS A LABEL, NOT A CLAIM. `_collapse_flips` merges
    # every row whose SEALED REGION is identical -- the pass is seen stranded from ~24 prevRoom
    # values, in two region classes -- and keeps whichever member it met first. `(26, 2)` was
    # that member for one class until the tightening retired it; `(110, 1)`, an equivalent
    # member of the same class, now carries the label. Measured pre-collapse the day it moved:
    # both classes still say `flips=[26] needed=[335]`, i.e. the same two facts as before.
    # The four act-boundary carries (§7s counter monotonicity + §7y joint projections).
    "snakeOil": {"register_strandings: reg(12, 123)=(26, 5)->[730]"},
    "cheese": {"register_strandings: reg(12, 123)=(26, 5)->[740]"},
    "snakeLasso": {"register_strandings: reg(12, 123)=(26, 5)->[700]"},
    "smellingSalts": {
        "register_strandings: reg123=5->[720]",
        "register_strandings: reg(12, 123)=(26, 5)->[720]",
    },
}

# The eight detectors the flat `caught` union reads, and how each row serializes. analyze and
# register_strandings carry every LB2 row today and get the snapshot shapes; the rest are empty
# on LB2, so their serializer is the whole row -- a first row from one of them should show its
# entire self, because a detector's first rows on a new game are unreviewed output, not results.
DETECTORS = ("analyze", "joint_strandings", "resource_exhaustion", "dangerous_sinks",
             "register_flip_strandings", "toll_strandings", "fatal_uses", "register_strandings",
             # ownedby_death_folds joined 2026-08-14 (the KQ5 phase-1 build): zero rows on
             # LB2, watched here so one appearing is a suspicion, not a silent addition.
             "ownedby_death_folds")


def _mech_row(det, r):
    if det == "analyze":
        return "analyze: need@rm%s sources=%s frontier=%s" % (
            r["need_room"], r["source_rooms"], "|".join(r["frontier_edges"]))
    if det == "register_strandings":
        return "register_strandings: reg%s=%s->%s" % (
            r["register"], r["value"], r["still_needed_at"])
    return "%s: %r" % (det, {k: v for k, v in r.items() if k not in ("item", "item_name")})

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_lb2_ground_truth: the LB2 act-structure stranding oracle ===")
    cfg = config.by_name("dagger")
    if cfg is None or not os.path.exists(cfg.ir_path):
        print("  (skip: no LB2 IR -- build/sweep/dagger)")
        return True
    s = M.load(cfg=cfg)
    # One pass over the eight detectors, keeping WHOLE ROWS: `caught` (the flat name union the
    # coarse checks read) and the attribution table both come from the same fetch, so "caught"
    # and "caught for a visible reason" cannot drift apart again.
    rows_by_item = {}
    for det in DETECTORS:
        for r in getattr(s, det)():
            name = r.get("item_name") or s.g.item_name(r["item"])
            rows_by_item.setdefault(name, set()).add(_mech_row(det, r))
    caught = set(rows_by_item)

    # THE ATTRIBUTION TABLE, printed on every run [memory `oracle-must-pin-the-mechanism`]:
    # "caught for the wrong reason" must be visible in the run that does it, not archaeology.
    print("  -- attribution: every detector row, by item --")
    for name in sorted(rows_by_item):
        for row in sorted(rows_by_item[name]):
            print("    %-14s %s" % (name, row))

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(missing)} -- STOP. These are read out of rm750's own ending selector "
          f"(or, for pressPass, off its three `put: 6` sites). Confirm with the user before "
          f"touching EXPECTED_CAUGHT; see docs/LB2-ORACLE.md §5.")

    surprises = caught - ALLOWED
    check("no UNEXPECTED item flagged (suspicion)", not surprises,
          f"NEW: {sorted(surprises)} -- not on the oracle's list. If it is real, promote it with "
          f"the user's OK; if not, it is a false positive. Either way, confirm.")

    out_of_scope_hits = caught & OUT_OF_SCOPE
    check("nothing OUT OF SCOPE by the items-only ruling is flagged", not out_of_scope_hits,
          f"FLAGGED: {sorted(out_of_scope_hits)} -- the 2026-07-26 ruling puts the evidence layer "
          f"out of scope for the Laura Bow games. Their absence is correct; flagging one means a "
          f"requirement is leaking in through examination/dialogue state.")

    unstrandable = caught & NEVER_STRANDABLE
    check("nothing the game GIVES you unavoidably is flagged", not unstrandable,
          f"FLAGGED: {sorted(unstrandable)} -- user ground truth 2026-08-10: the opening cutscene "
          f"hands these over on the only path into the game, so there is no state in which you "
          f"lack one and nothing can strand it. This is a FALSE POSITIVE, not a promotion "
          f"candidate. The likely cause is a new source read that treats a cutscene grant as an "
          f"acquisition you might miss (the variadic `get:` read does exactly this).")

    # --- THE MECHANISM PINS (MECHANISM_ROWS above) --------------------------------------------
    # Row-level equality per column-A item. This is where a false positive that NAMES an oracle
    # item stops scoring as a win: the name checks above cannot tell rm700's fatal_uses FP from
    # the real rm700 carry row, and this can.
    for name in sorted(EXPECTED_CAUGHT):
        want, got = MECHANISM_ROWS.get(name, set()), rows_by_item.get(name, set())
        check("mechanism pinned: %s" % name, want == got,
              "PINNED ROW MISSING: %s | UNPINNED ROW PRESENT: %s. Either is a mechanism change: "
              "confirm what moved against the game (an FP naming the right item is the churn "
              "engine's exact shape), then re-pin with the user's OK."
              % (sorted(want - got), sorted(got - want)))

    # --- the structural facts the whole diagnosis rests on ------------------------------------
    # Not verdicts about items: the measurements that explain the RED below, pinned so that
    # "someone modelled the act" cannot happen silently either. Read off `_emeta` -- the REGISTER
    # view movement actually consults -- because `edge_demands` answers a different question and
    # reading the wrong one is how this file's first diagnosis came out wrong.
    ACT = 123
    n_edges = sum(len(v) for v in s.edges.values())
    act_edges = sum(1 for metas in s._emeta.values()
                    for (req, sets, _alts) in metas if ACT in req or ACT in sets)
    print(f"  [note] {act_edges} of {n_edges} edges carry an act (global{ACT}) requirement")
    check("the act-break room is still the only way between acts",
          sorted(s.edges.get(26, ())) and set(s.edges.get(26, ())) >= {230, 330, 355, 420, 750},
          f"rm26 out-edges are {sorted(s.edges.get(26, ()))}; expected at least the five literal "
          f"destinations of actBreak's switch. 510/610 are legitimately absent -- act 3's "
          f"destination is an `If`-valued newRoom: and is still dropped (docs/LB2-ORACLE.md §7b).")

    # THE ORDERING, which is the thing that is actually broken. `_rstep` is where an ordered
    # register transition lives; `_inroom` is the permissive "this value is available here".
    # The act break belongs entirely in the first and is entirely in the second.
    rstep, inroom = s._rstep.get(ACT, {}), s._inroom.get(ACT, {})
    ordered = sorted(rstep.get(26, ()))
    free = sorted(inroom.get(26, ()))
    print(f"  [note] act steps at the act-break card rm26: ordered={ordered} free={free}")

    # --- THE ACT 1 -> ACT 2 GATE IS AN EGO PROPERTY, AND THE GOWN IS ITS PRICE -----------------
    # Pinned as a MECHANISM, not as an item name (memory `oracle-must-pin-the-mechanism`): the
    # register that stands for `ego.wearingGown`, the edge that demands it, and the machine whose
    # arming pays for it. Every part is looked up structurally -- the synthetic register index is
    # allocation-dependent and must never be written down as a number -- so this survives a
    # renumbering and fails only if the modelling really goes.
    #
    # WHY IT IS HERE: this is what the ego-property store bought, and its worth is not an item
    # verdict (nothing moved), so nothing else in this suite would notice it disappearing. It is
    # also the counter-evidence for the RED below: the model can now see the whole chain
    # gown -> wear -> cross, which is what lets it say, on the game's own terms, that the item is
    # a precondition of the act break rather than a carry across it.
    wg = next((gi for gi, key in (getattr(s.em.ir, "_obj_prop_index", None) or {}).items()
               if key[1] == "wearingGown"), None)
    check("the act-1 break is gated on the wearingGown ego property", wg is not None
          and any(req.get(wg) == {1} for (req, _s, _a) in s._emeta.get((250, 26), ())),
          f"wearingGown register = {wg}; rm250->rm26 metas = {s._emeta.get((250, 26))}. The game "
          f"spells this `rm250.sc:71` -- `(and (== global12 300) (global0 wearingGown:))` picks "
          f"`sACTBREAK`, whose state 10 is `newRoom: 26`. Losing it means the ego-property store "
          f"(vocab.derive_global_props / _introduced_unused) stopped reaching the ego, or "
          f"lower_obj_props stopped splitting the chained write that sets it.")
    payers = [(i["room"], i.get("inst"), sorted(_o for K, eg in i.get("entries", ())
                                                for _o in M._own_required(eg)))
              for i in s.em.machines
              for K, paths in i["states"].items()
              for (g, w, gg, c, tr) in paths if any(x[0] == wg and x[1] == 1 for x in w)]
    gown = next((i for i in range(64) if s.g.item_name(i) == "eveningGown"), None)
    check("...and the only act-1 writer of it costs the evening gown",
          any(room == 320 and gown in own for room, _inst, own in payers),
          f"machines writing wearingGown:=1 and what their entries demand: {payers}. Expected "
          f"rm320's `sLauraChanges` (the speakeasy restroom) to demand own({gown}). The other "
          f"writers are act-4+ museum rooms re-asserting it after a cutscene, and Main's debug "
          f"proc, which no reachable room calls.")

    # --- THE STREET SEAL ✅ PROMOTED 2026-08-10, same day it was declared red (§7ag) ----------
    # USER: *"the outside of the museum is not reachable once the museum acts start."* The check
    # asserts that truth; it was declared red because the seal looked positional (`sTaxiLeave`
    # drives the taxi to x=369, off the 320-wide pic) -- and the positional reading was only the
    # last step of a chain every other link of which was derivable. THREE derivations closed it,
    # each general, each measured byte-identical on LSL2/KQ4/KQ6:
    #   * DEPARTING INIT (`extract._object_departures`): an init whose own branch arms a handsOff
    #     script whose terminal literal MoveTo parks the object off-pic yields no interactive
    #     presence -- the player never gets a click window. Drops the arrival-taxi arm, so the
    #     taxi's owner reduces to the act gate `123 < 2` (rm330:158).
    #   * DEAD-LETTER NAV (`polygons.dead_nav_exits`): rm330's `south 250` trigger zone lies
    #     beyond the init polygon's lower boundary (y<=169 vs y~189), so the free nav edge is
    #     removed by provenance. North is NEVER claimed -- the engine tests the ego's RECT
    #     against the horizon and the ego's height is unmodelled; a horizon-band first cut
    #     killed rm290's live north and five KQ6 norths, all false.
    #   * RELATIONAL LOWERING (`guard_reqs` + edge_meta's domains): `(< global123 2)` over the
    #     register's own value universe {0..6} is exactly {0, 1}, the same completeness the
    #     `!=`-with-domain case already trusted -- the flat reading had dropped the literal
    #     whole, which is the §NEXT engine debt's first bullet paid down.
    STREET = (250, 260, 270, 300, 310, 320)
    reach = s._walk(ACT, frozenset())
    leaks = {r: sorted(v for (rm, v) in reach if rm == r and v >= 2)
             for r in STREET if any(rm == r and v >= 2 for (rm, v) in reach)}
    check("the street block is sealed from act 2 on", not leaks,
          f"street rooms the act projection reaches past act 1: {leaks}. The seal rests on the "
          f"three derivations above -- losing any one reopens the street and, with it, the "
          f"pressPass register rows and the (454/520, 5) joint witnesses pinned in "
          f"MECHANISM_ROWS.")

    # --- THE FORMER DELIBERATE RED, ✅ PROMOTED 2026-08-10 --------------------------------------
    # "The act-boundary carries are caught" was declared in tools/run_tests.py KNOWN_RED from this
    # file's first version. Its five rows were THREE causes, closed in sequence (§7s counter
    # monotonicity; §7y joint projections), and the last row, eveningGown, was RULED not a
    # softlock: *"act 2 gate, not a softlock"* [user, 2026-08-10] -- the mechanism pins above are
    # the evidence, and the row now lives in NEVER_STRANDABLE. The four real carries moved to
    # EXPECTED_CAUGHT, so the DROP check at the top now guards what this red used to describe.
    # (Historic diagnoses this check carried and refuted along the way -- the act-gated door
    # `init:` that measured to zero sites, the `_source_live` credit -- are preserved in
    # docs/LB2-ORACLE.md §7q/§7r/§7t and the git history of this file, not here.)

    # --- THE EMPTY BOTTLE AT THE ACT-5 BOUNDARY [ruled in scope 2026-08-09] -------------------
    # "You should have enough snake oil left before entering act 5 to not die because of it in
    # act 5" -- entering act 5 with `global150 == 0` IS the stranding, and it is NOT the caught
    # snakeOil row (that is the ITEM carry; this is the register). Pinned as a MECHANISM per
    # [[oracle-must-pin-the-mechanism]]: the demand is rm730's cobra pass (sSprinkleOil and
    # sRepelSnakes both presuppose 150 != 0; the 150 == 0 arm throws the bottle away), the only
    # raise is rm610's vat (`= global150 4`), and the joint (12,123) projection proves rm610
    # unreachable once act 5 begins.
    rows = (s.register_value_strandings() if hasattr(s, "register_value_strandings") else [])
    oil = [r for r in rows
           if r.get("reg") == 150 and 0 in r.get("bad", ())
           and 730 in r.get("demanded_at", ()) and 610 in r.get("raise_rooms", ())
           and 123 in (r["register"] if isinstance(r["register"], tuple) else (r["register"],))]
    check("the empty-bottle act-5 crossing is caught (register-value stranding)", bool(oil),
          f"rows={rows!r:.400}. The detector must derive: crossing the act seal with reg 150 == 0 "
          f"strands, because a use site past the seal (rm730) accepts only 150 == 4, the sole "
          f"raise (rm610) is sealed off, and 0 is attainable at the crossing (spends at "
          f"rm520/rm610, the sDumpIt pour-out, wasteful shakes on the pipe/drain).")

    safe_hits = caught & SAFE_RULED
    check("nothing RULED SAFE (the 2026-08-10 trio) is flagged", not safe_hits,
          f"FLAGGED: {sorted(safe_hits)} -- these were source-checked and ruled safe (respawn at "
          f"the point of use, act-5 chase costume branches). Flagging one means a source was lost "
          f"or a seal was fabricated. If a PLAY TEST (docs/LB2-ORACLE.md §9) refutes the source "
          f"reading, move the row back with the user's sign-off; nothing else may.")


    # ⭐ N4's TRIPWIRE, ASKED OF THIS GAME TOO (2026-08-20 fourth review, P6). `_falsifies` picks
    # the PERMISSIVE reading when a chain's writes leave a register either way, and that choice
    # is parked rather than derived -- so a game that actually asks the question has to say so
    # before the hold built on it ships. The assertion lived in KQ5's ground truth and nowhere
    # else, which made it a claim about one game instead of about the rule.
    _div, _fired, _shapes = M.n4_tripwire()
    print(f"  [n4] falsification questions asked: {_fired}, divergent: {len(_div)}")
    check("LB2 asks no divergent falsification question", not _div,
          f"divergent: {_div!r} (shapes asked: {_shapes!r}). The demand this game ships rests "
          f"on a reading of `chain_writes` that was CHOSEN, not derived -- see "
          f"`missability._falsifies`, N4. The USER decides which way it reads before this "
          f"game's hold is trusted.")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"  ruled safe pending play test (§9): {sorted(SAFE_RULED)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
