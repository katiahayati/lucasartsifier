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

⚠️ ONE CHECK HERE IS DELIBERATELY RED and is declared in `tools/run_tests.py`'s KNOWN_RED:
`the act-boundary carries are caught`. **4 of the 5 are now closed, and the survivor is not an act
gap at all**: `eveningGown` has no source in the model because `get:` is VARIADIC and we read one
argument (§7o). It stays RED because a KNOWN_GAPS row that quietly passes is how a limitation gets
forgotten -- and it will need RENAMING when the variadic read lands, because by then the name will
describe nothing that is red.

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
`rm750`'s own selector, the carries are cross-checked source-vs-walkthrough, and three rows are
CONTESTED -- the source contradicts every walkthrough and the user has not ruled yet
(docs/LB2-ORACLE.md §8).
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
    # verdict "pressPass is missable and matters" is right; see KNOWN_GAPS for the carry itself.
    "pressPass",
}

# B -- REAL, AND WE MISS IT. Each is obtained in one act and needed in a later one, with no source
# in the later act. These are what the RED check below is about.
KNOWN_GAPS = {
    "snakeOil",          # act 3 rm630 -> acts 4 and 5. And it is a COUNTER, not just a `has:`:
                         # global150 (init 4 in Main, refilled to 4 at rm610 but only while the
                         # vat's cel < 3), and rm730's act-5 cobra nest tests `(== global150 0)`
                         # -> sThrowBottle -> `put: 14`, DESTROYING it. Source + Sierra's hint
                         # file + the Let's Play all agree. docs/LB2-ORACLE.md §5a.
    "cheese",            # act 3 rm650 -> act 5 rm740; rm650 is act 3/4 only
    "snakeLasso",        # act 3 rm640 -> act 5 rm700 (the mummy-case hook)
    "smellingSalts",     # act 4 rm525 -> act 5 rm720 (revive Steve)
    "eveningGown",       # act 1 -> act 2; also has NO extracted `get:` site, so the source end is
                         # unmodelled too (one of the 3 items of 36 with no source)
}

# C -- CONTESTED. The walkthroughs call these fatal carries; the game source shows a second source
# in the act that needs them. Our own authority order says the source wins, which would move them
# to SAFE -- but they are in the list this project has carried since 2026-07-26, so they are
# reported and NOT reclassified until the user rules. docs/LB2-ORACLE.md §5 column C, §8 item 1.
CONTESTED = {
    "workBoot",          # rm720:46 `(if (not (has: 12)) (boot init: ...))` + its own sGetBoot at
                         # rm720:770 -- and rm720 IS the act-5 room where the boot is used
    "wire",              # rm430's wireEnd inits under `(or (> global123 3) ...)` and sGetThatWire
                         # has an explicit `(== global123 5)` branch -- cuttable in act 5
    "dinoBone",          # rm480:79 `(if (not (has: 18)) (bone init: stopUpd:))`, no act test on
                         # that line; whether rm480 is reachable in act 4 needs the act partition
}

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

    # --- THE DELIBERATE RED -------------------------------------------------------------------
    # Declared in tools/run_tests.py KNOWN_RED. Going green here is a PROMOTION, not a pass.
    still_missed = KNOWN_GAPS - caught
    check("🔴 KNOWN GAP (LB2): the act-boundary carries are caught", not still_missed,
          f"MISSED: {sorted(still_missed)}. 4 of 5 are CLOSED (docs/LB2-ORACLE.md §7s, §7y). The "
          f"survivor is `eveningGown`, and BOTH BLOCKERS THIS NOTE USED TO NAME ARE GONE -- the "
          f"variadic `get:` read landed (it has its real source, rm270) and so did the ego-property "
          f"store (`wearingGown`). What the model now says, derived end to end:\n      "
          f"  * `rm250 -> rm26` (the ACT 1 -> ACT 2 break) demands the wearingGown register == 1, "
          f"from `rm250.sc:71` `(and (== global12 300) (global0 wearingGown:)) -> sACTBREAK`;\n      "
          f"  * the only act-1 writer of that register is `sLauraChanges` at rm320 (the speakeasy "
          f"restroom), whose every entry demands own(32) -- the gown itself.\n      "
          f"So the gown is not a CARRY across the act boundary at all: it is the boundary's own "
          f"precondition, and the model is right that you cannot cross without it. It is also not "
          f"strandable -- rm270 gives it unconditionally, rm250 re-places the laundry ticket while "
          f"you hold neither ticket nor gown nor gown-worn, and rm250/rm270/rm320 are one "
          f"strongly-connected act-1 block, so no reachable state loses access. Sierra's own hint "
          f"file agrees: 'pick up an evening gown at Lo Fat's Laundry then put it on at the "
          f"speakeasy' is listed as one of the five things that END ACT 1.\n      "
          f"⚠️ THIS ROW THEREFORE LOOKS LIKE THE THREE `CONTESTED` ONES -- the source contradicts "
          f"the walkthrough reading it came from -- and it is NOT reclassified here. Report and "
          f"ask; enumerated ground truth is never flipped to make a change look good. "
          f"docs/LB2-ORACLE.md §7ab.\n      "
          f"⚠️ THE PREVIOUS TEXT HERE IS REFUTED, twice over, and is kept nowhere but this note so "
          f"a stale diagnosis cannot outlive its fix. It said the gap 'goes green when an act-gated "
          f"`init:` on a door means THIS EDGE IS NOT THERE' -- measured, there are ZERO such sites "
          f"corpus-wide (§7q/§7r) -- and it credited `reobtainable_rooms._source_live`, which is "
          f"inert here. What actually closed cheese and snakeOil was letting `register_strandings` "
          f"walk the JOINT projections (§7y): act 5's two exits kill you on entry, so the way out "
          f"is the disjunction `12 != 420 OR 123 != 5`, and each alternative passed freely in the "
          f"scalar projection that could not see the other.")

    promoted = caught & CONTESTED
    if promoted:
        print(f"  [note] a CONTESTED item is now flagged: {sorted(promoted)} -- the source says it "
              f"is re-obtainable in the act that needs it. Do not promote without the user's "
              f"ruling (docs/LB2-ORACLE.md §8 item 1).")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(still_missed)}")
    print(f"  contested, awaiting a ruling: {sorted(CONTESTED)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
