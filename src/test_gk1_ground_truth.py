"""GK1 (Gabriel Knight: Sins of the Fathers, SCI32) stranding ORACLE -- the first SCI2 title.

Same contract as `test_kq6_ground_truth`: columns of requirement UNITS, a DROP from
EXPECTED_CAUGHT is a regression (STOP and confirm), an ADDITION is a suspicion (confirm), a
CONFIRMED_SAFE name being flagged is a false positive. Every row's provenance is inline; ALL of it
was script-derived and UNVALIDATED by play when written (2026-08-27, autonomous run). Since then
the USER has play-confirmed the R5 and R2+R3 guards (v5, 2026-11-16). USER policy 2026-11-16: a
false positive that gets no guard is not a concern, and must not be made a failing check. See docs/GK1-SOFTLOCK-CANDIDATES.md for the derivations, file:line each.

What GK1 adds to the corpus: a DAY-structured game (`global123`, 1..10) whose point of no return is
the day counter itself, not a room edge. Its four real dead ends are all "the day advanced past the
only window" or "you walked into the finale without X". R1 (the day-5 window) was RETIRED on
2026-09-02 as this oracle's own false positive (see EXPECTED_CAUGHT); R2 and R3 are caught; the
reds below name the remaining gaps; `tools/run_tests.py` KNOWN_RED carries the reasons.
"""
import os
import sys

import config
import missability as M


def _unit(x):
    return frozenset({x}) if isinstance(x, str) else frozenset(x)


def _units(xs):
    return {_unit(x) for x in xs}


def _names(units):
    return {n for u in units for n in u}


# ⛔ R1 RETIRED 2026-09-02 (docs GK1 §1.37): VoodooCode1's "day-5 window" was a FALSE POSITIVE
# of this oracle, derived 2026-08-27 on the premise "no day-2/3/4 gate names item 32" -- a
# `grep "has: 32"` that missed a demand spelled as a doVerb MESSAGE. Both day-4 endings
# (theMapPrint's day-4 arm, the bookstore re-check) require flag 248; flag 248 is raised in
# play only by Magentia's full show (`sFullShow@290` state 4) in the arm `register == 40`, and
# 40 is VoodooCode1's message -- SHOWING HER THE TOMB SKETCH. The other setter is
# `debugHandler`'s jump-to-day catch-up (script 99), called from nowhere. So day 4 cannot end
# without the sketch; every day-5 player holds it; the day-5 flip strands nothing. The 2026-08-28
# "catch" stood on Grace's go-home ending day 4 for free -- the leak the once-only proof closes.
# R5 -- DERIVED BY THE TOOL 2026-09-02 (docs GK1 §1.38), the doomed-arming rule's first payoff:
# the bayou ritual clearing (rm480, `bayouRitual`) kills a player who has not USED the croc
# mask -- `roomScript` state 5 arms `killGabe` on the ego unless flag 216 is set, and 216 is
# raised only by `maskAction` in the maze (rm490, verb 31 with the mask) -- with nothing to do
# about it on that screen. "You walked into the finale without X." The tool reads it as an
# EDGE stranding of the mask at rm490->rm480: the maskless crosser's world is dead, so the
# mask is "unobtainable past the edge and still needed". The guard it yields (`has: 21`) is
# necessary, not sufficient -- a player holding the mask unused dies too; the exact guard is
# flag 216.
EXPECTED_CAUGHT = _units({
    "crocMask",             # R5: use the mask in the maze before the ritual clearing
})

# REAL per the scripts, MISSED by the tool. Each is a declared RED below with its mechanism.
KNOWN_GAPS = _units({
    "rod",                  # R2: must be DEPOSITED in the left confessional (rm455.sc:828 ->
                            # flag 280) before Grace's room, which has no exit (sHRoom8.sc);
    ("signalDev", "signalDev2"),
                            # R2: ...together with either signal device (rm455.sc:818 -> 281);
                            # 280 & 281 -> 351 (sHRoom6.sc:131) or EndGame.sc:637 kills you.
    "BoarGuise",            # R3: Mosely's disguise, demanded in Grace's room (sHRoom8.sc:690)
    "WolfGuise",            # R3: Gabriel's, demanded there too (sHRoom8.sc:1050); every
                            # combination lacking them ends in sDJKills -> newRoom: 770.
})

# Flagging one of these is a FALSE POSITIVE (script evidence, no user ruling yet).
CONFIRMED_SAFE = {
    "VoodooCode1",          # R1 retired (above): necessarily held by day 5
    "sLakePatter",  # dangerous_sinks said giving it to the artist (neJackson.sc:1355) strands
                    # its use at Magentia's (rm290 verb 23). The give is REQUIRED -- it is the
                    # day-2 gate's flag 231 (theMapPrint.sc:237) -- and no `has: 31` exists
                    # anywhere; the Magentia site is flavour. ✅ NO LONGER FLAGGED since
                    # 2026-08-31: the travel-movie fan (docs §1.17) removed the phantom rm290
                    # demand the row rested on. Kept -- it is ground truth, not a suppression.
    "reconVeve",    # register_strandings says the day counter reaching 10 strands it for
                    # rm200/rm205/rm340. It is never consumed (no `put: 38` in the tree) and
                    # every demand is day-3/4 gated (theMapPrint.sc:251, rm340.sc:1151) --
                    # dead after the flip the row is built on. A flip that kills the DEMAND
                    # is not a stranding; the detector does not check that.
}

# USER RULING 2026-08-27: the knife-on-Malia row is OUT of scope. `fatal_uses` flags stabbing
# Malia during the throw-the-talisman window (EndGame.sc:1994-2001, `local7` -> sDaggerOnMalia
# -> 770). KQ6's skull was ruled IN because throwing it WASTES it for later ("the problem with
# the skull is you waste it for later"); the knife is not consumed -- the stab is a death you
# restore from, preventable on its own screen. A plain on-screen death: a false positive here.
# ...and the register rows that later joined it (reg12=720 with the travel-movie fan,
# reg759=1 with the hounfour scene fan) are the forced-knife class: day 7 cannot end without
# the knife (rm540.sc:299-307, tile1.sc:497) and no `put: 64` exists, so the post-flip player
# holds it wherever the flip lands them.
CONFIRMED_SAFE.add("knife")

# sVoodooCode (33): register_strandings on synthetic flag 246 (formerly 247; the tomb-writing
# room's dispose, rm302.sc:149-154). Writing on the tomb REQUIRES holding both sketches
# (rm300.sc:952 `(has: 32) (has: 33)`), neither is ever consumed (no `put: 32/33`), so the player
# who can flip the seal holds the item. Still flagged 2026-08-28 because the model reaches rm302
# through the interrogation screen's return-to-sender edge `50->302` (guarded `prev == 302`)
# without the priced crossing `300->302` -- a return edge should carry its origin's entry cost.
CONFIRMED_SAFE.add("sVoodooCode")

# oil (22): the edge rows at `rm372->rm750` and `rm455->rm800` say crossing into the finale
# strands it while rm460 "still needs" it. DERIVED FALSE POSITIVE, and the same class as
# reconVeve and braceMold -- the site that still needs it is the site that CONSUMES it:
# `napoleon.sc` `useTheOil` state 0 is `(global0 put: 22)` (`:601`), the only `put: 22` in the
# tree, armed from the oilTeller topic at rm460. And nothing anywhere demands the flag it
# raises: `(proc13_0 258)` occurs four times and all four are inside `napoleon.sc` itself,
# choosing Sam's dialogue variant -- NO `endDay` arm asks for it (`theMapPrint.sc:231-278`
# lists days 2-5 and 258 is in none of them), so the oil is not required to end any day, or to
# win. Its need site is a day-3/4 bar scene, dead by the day-9/10 crossings the rows are built
# on; a walkthrough corroborates the era (after Germany, day 10 returns only to St George's
# Books and St Louis Cathedral) but the derivation above is the evidence.
CONFIRMED_SAFE.add("oil")

# braceMold (40): register_strandings at the day-4/6/7 flips, appearing 2026-08-30 with the
# return-to-sender pricing (docs §1.15) -- which is right about the SOURCE (`rm280.sc:794`, and
# day 4 shuts Cazaunoux's house) and wrong about the player. The mold's only need site is
# `napoleon.sc` doVerb 43 -> `showMold`, which `put: 40`s it at state 4 (`:838`) and raises flag
# 256 at state 9 (`:858`, the only non-debug setter); day 3's `endDay` arm demands
# `(proc13_0 256)` (`theMapPrint.sc:249-256`). So day 3 cannot END without having shown the mold,
# and the site that "still needs" it is the one that consumed it. Same class as reconVeve -- the
# flip's own precondition demands the item -- one register further up: `_wbranch[(498,460,1)]`
# already costs braceMold, and the day-3 branch of the flag-15 write never inherits it.
CONFIRMED_SAFE.add("braceMold")

# talisman (69): the case-(c) trap round's `[rod, talisman]` carry-in row at rm455->rm800 --
# PROVED FP FROM THE SCRIPTS, 2026-09-01, both halves the forced class:
#   * the talisman is granted by BOTH Africa-exit cutscenes (`get: 69` immediately before
#     `newRoom: 216` -- rm720.sc:1040, :1285) and Africa (700<->710<->720, +death) has no other
#     exit, so day 10 cannot arrive without it;
#   * the rod is required to LEAVE Africa at all: `keyWorks` -- the only opener of the wall
#     into rm720 -- is armed exclusively from `rodCode`'s success arm (rm710.sc:2303-2328), and
#     rodCode answers only the rod's verb 76; no `put: 60` exists before the 455 deposit
#     itself.
# The row's guard (has: 60/69 at the elevator) therefore guards two items every player holds.
# ⛔ NOTE: this row puts `rod` in the caught set FOR THE WRONG MECHANISM -- R2's pin (rod AND
# the signal-device pair, the DEPOSIT) stays authoritative; the elevator return is open while
# flag 351 is clear (sHRoom6.sc:395-400 refuses verb 8 only under 351), so the deposit stays
# fixable until Grace's room, exactly as R2 records.
CONFIRMED_SAFE.add("talisman")

ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS

# Item ids ARE the inventory `add:` order (GKInvItem.sc:93). Pinned because the tool got all 81
# wrong on its first run (declaration order; the `(ScriptID 24 N)` entries were unresolvable and
# `bookTribe` is declared but never added) -- the QFG1 lesson, again.
ITEM_IDS = {32: "VoodooCode1", 60: "rod", 64: "knife", 69: "talisman", 78: "BoarGuise",
            79: "WolfGuise", 80: "hounfourKey", 18: "tracker", 19: "signalDev", 38: "reconVeve",
            0: "phoEnvelope"}

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_gk1_ground_truth: the GK1 / SCI32 stranding oracle ===")
    cfg = config.by_name("gk1")
    if cfg is None or not os.path.exists(cfg.ir_path):
        print("  (skip: no GK1 IR under build/sweep/gk1)")
        return True
    s = M.load(cfg=cfg)

    # --- anchors: the day-1 boot and the credits, derived (see GK1-SOFTLOCK-CANDIDATES §0) -----
    check("start is the engine root (speed test 17, which sets day 1)", s.em.cfg.start_room == 17,
          f"start_room = {s.em.cfg.start_room}")
    check("goal is the WIN credits (680), not the opening credits (180)",
          set(s.em.cfg.goal_rooms) == {680}, f"goal_rooms = {sorted(s.em.cfg.goal_rooms)}")
    check("the hounfour (800, a Room CLASS) is a room", 800 in set(s.em.rooms),
          f"rooms lack 800; sample = {sorted(s.em.rooms)[-6:]}")
    import anchors as A
    deadly = A.death_rooms(s.em)
    check("deaths are modelled: every newRoom: 770 host is a death room",
          {260, 480, 500, 710, 800, 899} <= deadly, f"death rooms = {sorted(deadly)}")
    names = {i: s.g.item_name(i) for i in ITEM_IDS}
    check("item ids follow the inventory add: order (knife=64, rod=60, VoodooCode1=32 ...)",
          all(names[i] == nm for i, nm in ITEM_IDS.items()),
          f"got {names}")

    # --- the caught set, every detector, in units ---------------------------------------------
    caught = set()
    for e in s.edge_strandings():
        caught |= {_unit(s.g.item_name(i)) for i in e["items"]}
        caught |= {frozenset(s.g.item_name(i) for i in g) for g in e["groups"]}
    for r in s.group_strandings():
        caught.add(frozenset(s.g.item_name(i) for i in r["items"]))
    rows_by_det = {}
    for det, rows in (("joint", s.joint_strandings()), ("exhaustion", s.resource_exhaustion()),
                      ("dangerous_sinks", s.dangerous_sinks()),
                      ("register_flip", s.register_flip_strandings()),
                      ("fatal_uses", s.fatal_uses()), ("toll", s.toll_strandings()),
                      ("register_strandings", s.register_strandings()),
                      ("scene_carryins", s.scene_carryins()),
                      ("ownedby_death_folds", s.ownedby_death_folds())):
        rows_by_det[det] = rows
        for r in rows:
            if "item_group" in r:      # an ALTERNATIVES row: the set is the unit
                caught.add(frozenset(s.g.item_name(i) for i in r["item_group"]))
            else:
                caught.add(_unit(s.g.item_name(r["item"])))
    caught_names = _names(caught)
    print("  -- attribution: every detector row, by item --")
    for det, rows in rows_by_det.items():
        for r in rows:
            extra = {k: r[k] for k in ("register", "value", "pattern", "room", "at_room",
                                      "need_room", "still_needed_at") if k in r}
            nm_ = s.g.item_name(r["item"]) if "item" in r else r["item_name"]
            print(f"     {det:22s} {nm_:14s} {extra}")
    for e in s.edge_strandings():
        print(f"     {'edge':22s} {[s.g.item_name(i) for i in e['items']]} "
              f"{[[s.g.item_name(i) for i in g] for g in e['groups']]}")

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(sorted(u) for u in missing)} -- STOP and confirm.")
    surprises = caught - ALLOWED
    check("no UNEXPECTED unit flagged (suspicion)", not surprises,
          f"NEW: {sorted(sorted(u) for u in surprises)} -- promote with the user's OK or record "
          f"the false positive.")
    check("a safe item is not flagged", not (caught_names & CONFIRMED_SAFE),
          f"FLAGGED: {sorted(caught_names & CONFIRMED_SAFE)}")

    # --- THE FOUR GAPS, each a RED naming its mechanism -----------------------------------------
    # R1: the day counter is the point of no return. VoodooCode1's source is armed under
    # (< global123 5) and its demand under day >= 5 in the SAME room; the counter only ever
    # `++`s (rm370.sc:174 etc.), so no literal "flip" exists for register_strandings to key on.
    # MECHANISM-PINNED ([[oracle-must-pin-the-mechanism]]): the row must be a register_strandings
    # row on the DAY COUNTER (register 123) flipping to 5. Measured 2026-08-27 after the counter
    # fixes (increment seeds, relational domains, presence on flat pickups): VoodooCode1 IS
    # named -- but on synthetic flag 247 (the "wrong message written" hide), a coincidence that
    # names the right item for the wrong reason. The day-5 flip still finds the `theInView`
    # pickup inside the inset live, because its `(== view 3022)` is object-property state.
    r1 = [r for r in rows_by_det["register_strandings"]
          if s.g.item_name(r["item"]) == "VoodooCode1" and r.get("register") == 123]
    # R1 RETIRED (see EXPECTED_CAUGHT): the correct answer is NO day-flip row for the sketch.
    check("R1 (retired): VoodooCode1 is NOT reported at any day flip -- day 4 cannot end without it",
          not r1,
          f"register_strandings rows for VoodooCode1: "
          f"{[(r.get('register'), r.get('value')) for r in rows_by_det['register_strandings'] if s.g.item_name(r['item']) == 'VoodooCode1']} "
          f"-- the check wants NO row on the day counter (any value) -- the 5->6/6->7 rows are the flag-65 phantom, docs GK1 1.39; the inset's `theInView` site (rm300.sc:1368, "
          f"`(== view 3022)`) stays live because object-property state is not modelled")
    # R2/R3: the hounfour's twelve scenes are `Script`s inside ONE room (800) and Grace's room
    # (sHRoom8) is entered by an intra-room scene switch, so the one-way door is invisible.
    check("R2: the confessional deposit (rod + a signal device -> flags 280/281 -> 351) is caught",
          _unit("rod") in caught and _unit(("signalDev", "signalDev2")) in caught,
          "the point of no return is sHRoom8.sc:71 inside room 800; the model has no intra-room "
          "scene boundary to hang a carry-in on")
    check("R5: the croc mask is caught at the maze->ritual crossing (rm490->rm480)",
          any(e["from_room"] == 490 and e["to_room"] == 480 and 21 in e["items"]
              for e in s.edge_strandings()),
          "no edge_strandings row 490->480 naming item 21; the maskless arrival at bayouRitual "
          "arms killGabe (state 5) and the doomed-arming rule must make that path a DEATH")
    check("R3: the two guises are caught as carry-ins to Grace's room",
          _unit("BoarGuise") in caught and _unit("WolfGuise") in caught,
          "same intra-room boundary as R2")
    # --- THE GUARDS (2026-11-14): what the patch DEMANDS, pinned beside what the detectors find.
    # Detection was right for two months while every shipped guard was wrong: the ritual
    # crossing asked for the mask ITEM (the ritual tests that it was WORN, and the tattoo),
    # the elevator asked for the rod (spent by the very deposit it protects) and for veve papers
    # the artist keeps on day 2, and Grace's room -- the real point of no return -- had no
    # guard at all. An oracle that pins only item names cannot see any of that
    # ([[oracle-must-pin-the-mechanism]]).
    import guards as G
    specs = G.guard_specs(s)
    by_edge = {(sp["from_room"], sp["to_room"]): sp for sp in specs if sp["site"] == "edge"}
    g5 = by_edge.get((490, 480), {})
    check("R5 guard: the ritual crossing demands the FLAGS the ritual tests (216 mask worn, "
          "299 tattoo painted), not possession of the mask",
          g5.get("condition") == "(and (proc13_0 216) (proc13_0 299))" and not g5.get("refused"),
          f"condition = {g5.get('condition')!r}, refused = {g5.get('refused')}")
    scn = [sp for sp in specs if sp["site"] == "scene"]
    check("R2+R3 guard: ONE scene spec refuses Grace's room (script 808, sHRoom8) until both "
          "guises are held and the deposit flag 351 is set",
          len(scn) == 1 and scn[0]["script"] == 808 and scn[0]["machine"] == "sHRoom8"
          and scn[0]["condition"] == "(and (gEgo has: 78) (gEgo has: 79) (proc13_0 351))"
          and not scn[0]["refused"],
          f"scene specs = {[(sp.get('script'), sp.get('machine'), sp.get('condition'), sp.get('refused')) for sp in scn]}")
    gel = (by_edge.get((455, 800), {}).get("condition") or "")
    check("the confessional elevator demands neither the rod (the deposit spends it) nor a "
          "veve paper (the artist keeps them on day 2)",
          not any("has: %d)" % i in gel for i in (60, 15, 16, 31)),
          f"rm455->rm800 condition = {gel!r}")

    # R4: a FLAG stranding through the conversation system. Flag 44's only writer is a Teller
    # topic (hartridge.sc:257) reachable only while day < 4 (rm270.sc:200); day 4's gate needs
    # it transitively (crash.sc:66-84 -> rm450.sc:674 -> rm450.sc:421 -> theMapPrint.sc:265).
    regs = {(r.get("register"), r.get("value")) for r in rows_by_det["register_strandings"]}
    fbase = getattr(getattr(s.em, "ir", None), "flag_synth_base", None)
    flag44 = fbase + 44 if fbase is not None else None
    # R4 is a CLOSURE-ARM finding (docs GK1 1.29, 1.44-1.46): the day-4 crosser without flag 44
    # cannot end day 4 (its `endDay` arm needs the tattoo trace, which needs Crash's topic, which
    # needs Cazaunoux's, which needs flag 44), while the unconstrained crosser can. The flat arm
    # cannot see that go-home spends flag 65; `producible_seal` asks the closure arm's own
    # question for this one crossing in seconds (the whole detector takes an hour on GK1).
    seal = s.producible_seal(123, 4, 370, flag44, 0) if flag44 is not None else None
    check("R4: flag 44 (Cazaunoux topic 54 -> Crash's 'Voodoo Hounfour') is caught as a stranding",
          flag44 is not None and (any(r == flag44 for (r, _v) in regs) or seal is True),
          f"closure arm for the day-4 crossing carrying flag 44 = 0: {seal!r} (None = nobody crosses, "
          f"False = not a seal, True = dead end); register_strandings registers = {sorted(regs, key=str)}; flag44 synthetic = {flag44}. The "
          f"Teller topic dispatch is lowered (vocab.lower_teller_cases) and the topic-said array "
          f"(global182, proc50_5..8) is a lowered store since 848ec35 (docs GK1 1.42); the flat arm "
          f"still cannot see that go-home SPENDS flag 65 (1.29) -- the closure arm can")

    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
