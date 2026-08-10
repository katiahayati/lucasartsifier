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
precondition (see the wearingGown mechanism pins below), so it moved to NEVER_STRANDABLE. This
file currently declares NO red; the outstanding false positive (`skeletonKey`) fails the
suspicion check on purpose until its blame fix lands.

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
    # Real for a DIFFERENT reason than we catch it by: pressPass spans acts 1->2 (that is the
    # stranding), but what fires is `dangerous_sinks` on the three `put: 6` sites (Main, rm300,
    # rm335) with the item still `has:`-checked at 250/300/335. Kept in this column because the
    # verdict "pressPass is missable and matters" is right.
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
    ids = ({c["item"] for c in s.analyze()} | {j["item"] for j in s.joint_strandings()}
           | {r["item"] for r in s.resource_exhaustion()} | {d["item"] for d in s.dangerous_sinks()}
           | {r["item"] for r in s.register_flip_strandings()} | {t["item"] for t in s.toll_strandings()}
           | {f["item"] for f in s.fatal_uses()} | {r["item"] for r in s.register_strandings()})
    caught = {s.g.item_name(i) for i in ids}

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

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"  ruled safe pending play test (§9): {sorted(SAFE_RULED)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
