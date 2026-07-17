"""Regression check for the semantic core, across BOTH games.

Every assertion here is something we got wrong at least once. The two that matter
most are the sanity checks: a shipped game is winnable, so if the model says
otherwise the model is wrong -- and every attempt to make the core more precise
has failed here first (the state-machine lift dropped LSL2 to 28/100 rooms before
the trust gate went in).

    python3 src/_check_core.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
import config                                              # noqa: E402
import closure as C                                        # noqa: E402
from model import load_game                                # noqa: E402
from analyze import is_room                                # noqa: E402

FAILS = []


def check(name, got, want):
    ok = got == want
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}: {got!r}" +
          ("" if ok else f"   (expected {want!r})"))
    if not ok:
        FAILS.append(name)


def check_in(name, needle, hay):
    ok = needle in hay
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"   (missing from {hay!r})"))
    if not ok:
        FAILS.append(name)


def check_not_in(name, needle, hay):
    ok = needle not in hay
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}" + ("" if ok else f"   (unexpectedly present)"))
    if not ok:
        FAILS.append(name)


def run(cfg):
    config.ACTIVE = cfg
    # analyze reads through to the live config, but closure bound CFG at import.
    C.CFG = cfg
    g = load_game(cfg.src_dir)
    m = C.FixModel(g)
    r = C.closure(m, cfg.start_room)
    goals = set(cfg.goal_rooms)
    total = len([n for n in g.scripts if is_room(g, n)])
    strands = {(s["from_room"], s["to_room"], s["item_name"])
               for s in C.strandings(m, cfg.start_room, goals)}
    return g, m, r, goals, total, strands


def main():
    print("LSL2")
    g, m, r, goals, total, strands = run(config.LSL2)
    check("SANITY: shipped game is winnable", bool(r.rooms & goals), True)
    # 85/100, and the 15 we don't reach are the RIGHT 15: rm200/300/400/401/500/600/700
    # are region controllers (not walkable), rm5/7/8/9/10 are the pre-game and
    # copy-protection screens, rm44/rm45 are orphans no `newRoom` targets at all, and
    # rm99 is Main-only. This was 69 before the state-machine lift -- the old activator
    # heuristic (conjoin the entry guard onto the GOTO) was OVER-constraining real edges.
    check("rooms reached", len(r.rooms), 85)
    check("rooms total", total, 100)

    # The raft gauntlet, DERIVED -- this is the whole point of machine.py. Both are
    # real LSL2 dead-ends: board the cruise without them and the lifeboat's day loop
    # (rm138 states 3..7, exit at day>=9) can never reach its exit.
    check_in("derives the Sunscreen strand (rm26->27)", (26, 27, "Sunscreen"), strands)
    check_in("derives the Grotesque_Gulp strand (rm26->27)",
             (26, 27, "Grotesque_Gulp"), strands)
    # The Wig's frontier is rm38->rm131 (boarding the LIFEBOAT), not rm26->rm27
    # (boarding the ship): the Wig is obtainable on the ship itself, so at rm27 you
    # can still go get it. Needs zero-init to appear at all -- day 4 asks
    # `(if gWearingWig ...)`, and without the item nothing can ever set that global.
    check_in("derives the Wig strand (rm38->131)", (38, 131, "Wig"), strands)

    # The `st is None` activator bug. Assert the INVARIANT, not a downstream symptom.
    #
    # The old assertions checked that no stranding was REPORTED on those edges, which
    # cannot catch the regression: restore the bug and `strandings` returns nothing at
    # all, because sanity collapses first and there is no reachable goal to strand you
    # from. Four green ticks guarding the exact bug their commit existed to prevent.
    #
    # So test the thing itself: a GOTO in doit/handleEvent (`st is None`) is a direct
    # player action, has no activator, and must carry NO `own(...)` from one. rm101's
    # exit is `(& (gEgo onControl:) $0008) -> (newRoom: 11)` in rm101Script:doit; the
    # bug welded a Said-branch's `(gEgo has: 2)` onto it and made rm101 a sink without
    # the Lottery_Ticket. This fails the moment that returns.
    from analyze import edge_requirements                       # noqa: PLC0415
    ereq = edge_requirements(g)
    for a, b, item in ((101, 11, "Lottery_Ticket"), (114, 14, "Dollar_Bill"),
                       (125, 25, "Wad_O__Dough")):
        check(f"rm{a}->rm{b} (a doit exit) carries no activator OWN guard",
              sorted(C.own_atoms(ereq.get((a, b)))), [])

    # Fruit and Sewing_Kit are ALTERNATIVES on day 6 -- removing either alone must
    # NOT strand you. (The syntactic path ANDs them, which is how the shipped patch
    # ended up demanding all four lifeboat items.)
    check("Fruit alone does not strand", {s for s in strands if s[2] == "Fruit"}, set())
    check("Sewing_Kit alone does not strand",
          {s for s in strands if s[2] == "Sewing_Kit"}, set())

    # ...but lacking BOTH is a real dead-end, and only the CNF query can say so. This
    # is the whole point of minimal blocking sets: a disjunction is invisible to a
    # one-item-at-a-time question.
    reqs = {(e["from_room"], e["to_room"]): e for e in C.requirements(m)}
    lifeboat = reqs.get((38, 131))
    check("rm38->131 is a frontier", lifeboat is not None, True)
    if lifeboat:
        cl = {tuple(c["item_names"]) for c in lifeboat["clauses"]}
        check_in("day 6 needs Fruit OR Sewing_Kit", ("Fruit", "Sewing_Kit"), cl)
        check_in("day 4 needs the Wig outright", ("Wig",), cl)
        # The Spinach_Dip is FATAL, so it belongs to NO blocking set: lacking it does
        # not lose -- holding it does. The old syntactic guard demanded it and made
        # the game unwinnable. This assertion is that bug's headstone.
        check("the fatal Spinach_Dip is in no clause",
              any("Spinach_Dip" in c["item_names"] for c in lifeboat["clauses"]), False)
        check("the guard is CNF, not a flat conjunction", lifeboat["guard_sexpr"],
              "(and (gEgo has: 14) (or (gEgo has: 11) (gEgo has: 12)))")

    # The glacier: rm79->rm80 is a ONE-WAY vine swing across a chasm (rm79:178
    # `((not (gEgo has: 29)) ; Vine`), and rm80 has no back-edge. Sand's source is
    # rm75 and Ashes' is rm77 -- both on the NEAR side -- so you must carry one
    # across to melt the ice. Needs BOTH the strict cue model (rm81's machine would
    # otherwise walk from entry 0 straight to its exit, ignoring the sand guard) and
    # no `++` poisoning. Invisible to a one-item-at-a-time query either way.
    glacier = reqs.get((79, 80))
    check("rm79->80 (the vine swing) is a frontier", glacier is not None, True)
    if glacier:
        check_in("crossing the chasm needs Sand OR Ashes", ("Ashes", "Sand"),
                 {tuple(c["item_names"]) for c in glacier["clauses"]})

    # QA scaffolding must stay OFF. rm82 (the volcano crater) contains
    # `(if gDebugging (gEgo get: 27 get: 21 get: 19))` -- the whole bomb, handed to you
    # in the room you need it -- and rm75 has `(if gForceAtest (= gIslandStatus 105))`,
    # the end state. If either ever goes live, every endgame finding silently dies.
    check("gDebugging pinned off", sorted(r.flags.get("gDebugging", [])), [0])
    check("gForceAtest pinned off", sorted(r.flags.get("gForceAtest", [])), [0])
    # `m.acq` is a defaultdict(list): `m.acq[21]` on a missing key returns [] rather
    # than raising, `any([])` is False, and this prints 'ok' while the model has lost
    # every source of the Hair_Rejuvenator -- which would silently delete the finding
    # the next assertion depends on. Pin the sites first, so the check can only pass
    # for the reason it claims. (It also mutated the model by inserting the key.)
    acq21 = dict(m.acq).get(21, [])
    check("the Hair_Rejuvenator has its real source (rm151, the barber)",
          sorted({rm for rm, _ in acq21}), [82, 151])
    check("the crater's debug hand-out of the bomb is dead",
          any(rm == 82 and C.holds_tree(gd, r.items, r.flags) for rm, gd in acq21),
          False)
    # The Hair_Rejuvenator's REAL source is rm151 (the barber's chair, off rm51), and it
    # is gone the moment you board the plane. That much the model gets right; what it
    # cannot see is that you NEED it -- see lsl2-bomb-has-no-script-level-gate.
    check("rejuvenator unobtainable past the plane gate",
          21 in C.closure(m, 58, frozenset(r.items) - {21}).items, False)

    # The raft machine must be lifted and trusted, else none of the above is real.
    check("raft exit rm138->rm42 is machine-owned", (138, 42) in m.machine_edges, True)
    from machine import machines_of                              # noqa: PLC0415
    check("raft models `day` as a bounded counter",
          machines_of(g, 138)["rm138Script"].counters, {"day": (-1, 10)})
    # Phase 3: the raft's guard is COMPILED, once, not re-run per closure. And it says
    # the thing the monotone fixpoint cannot: of the 18 assignments that get you off the
    # raft, the Spinach_Dip is held in ZERO, so `¬own(13)` is IN the guard. `_atom3`
    # answers UNKNOWN for `(not (ego has: X))` by design, so `requirements()` can never
    # state a trap item -- only the compiled guard can.
    raft = m.machine_guards.get((138, 42))
    check("the raft's guard is compiled, not run", raft is not None, True)
    from model import GOr, GAnd, GNot, Pred                      # noqa: PLC0415
    def _forbids(tree, item):
        """EVERY way off the raft must forbid `item` -- structural, not a string match."""
        terms = tree.kids if isinstance(tree, GOr) else [tree]
        return all(any(isinstance(k, GNot) and isinstance(k.kid, Pred)
                       and k.kid.kind == "OWN" and k.kid.var == item
                       for k in (t.kids if isinstance(t, GAnd) else [t]))
                   for t in terms)
    check("the compiled guard FORBIDS the fatal Spinach_Dip", _forbids(raft, 13), True)

    # Phase 4 register promotion is OFF by default (it makes requirements() ~200x
    # slower; Phase 5's job to afford it). But the MECHANISM is exercised here in one
    # cheap closure, because it fixes a real bug: a register write and a same-room edge
    # are one trigger, and splitting them made rm79 unreachable once gIslandStatus went
    # concrete. `FixModel.promote()` turns it on for the test.
    check("promotion is OFF by default", sorted(m.promoted), [])
    mp = C.FixModel(g).promote(["gIslandStatus"])
    rp = C.closure(mp, config.LSL2.start_room)
    check("promote(gIslandStatus): all rooms still reachable (rm79 fix)",
          len(rp.rooms), len(r.rooms))
    check("promote(gIslandStatus): the register climbs past the endgame chain",
          max(v for v in rp.flags.get("gIslandStatus", [0]) if isinstance(v, int)) >= 104,
          True)
    check("leaving rm77 applies the gIslandStatus:=2 write",
          any(reg == "gIslandStatus" and v == 2
              for reg, v, _g in mp.room_reg_writes.get(77, [])), True)

    # SET effects inside a machine state inherit their TRIGGER guard, exactly as GOTOs
    # do. rm64's `(= gCurrentStatus 10)` -- the parachute survival write, in state 2
    # behind `gWearingParachute==1` -- was recorded UNCONDITIONAL, so the model
    # survived the plane jump without the chute. (Necessary for the parachute, not yet
    # sufficient: rm65 also writes its own survival value, and edge_reg_effect couples
    # only same-register writes.)
    p64 = [g for rm, v, g in m.sets["gCurrentStatus"] if rm == 64 and v == 10]
    check("rm64's survival write carries its gWearingParachute trigger guard",
          any("gWearingParachute" in str(g) for g in p64), True)
    check("...and still REQUIRES the Grotesque_Gulp", 8 in C.own_atoms(raft), True)

    # Pin the headline metric. The README claimed "0 un-modelled machine exits, KQ4
    # has 1" for three commits after the strict walk made it 10 and 5, because nothing
    # asserted it and only run.py printed the truth. A number in prose that no test
    # holds is a number that drifts.
    # Phase 3 moved these from (33, 10). The fallbacks went UP because the trust gate
    # got HONEST: `control_exits` used to run every atom as UNKNOWN, which lets the walk
    # take both branches of one condition at once -- an inconsistent world. Enumeration
    # asks "is there a CONSISTENT assignment that delivers this exit?", and for 10 of
    # them there is not. They were trusted on a fiction; they now fall back to the flat
    # edge, which is the safe direction.
    check("LSL2 machine exits: trusted / fallback",
          (len(m.machine_edges), len(m.machine_untrusted)), (23, 20))

    print("\nKQ4")
    g2, m2, r2, goals2, total2, strands2 = run(config.KQ4)
    check("SANITY: shipped game is winnable", bool(r2.rooms & goals2), True)
    # 89, not 88. It was 88 because the machine cache keyed on the instance NAME, and
    # KQ4 reuses names across rooms: `doDoor` exists in rm80 (exits to 92) and rm87
    # (exits to 84). They shared a key, rm80 was closed first, rm87 read back rm80's
    # answer, and rm84 was DELETED from the game -- a fabricated dead end. This
    # assertion pinned the bug in as ground truth, so the correct fix turned the suite
    # red. A test that encodes the bug is worse than no test.
    check("rooms reached", len(r2.rooms), 89)
    check("rm84 is reachable (the doDoor cache collision)", 84 in r2.rooms, True)
    # The cache-key collision that deleted rm84 is now IMPOSSIBLE rather than fixed:
    # Phase 3 compiled the machines out of the runtime, so there is no cache to key and
    # no per-closure re-interpretation to key it for. Assert the absence, because that
    # is the actual guarantee -- a whole bug class, not one bug.
    for lbl, mm in (("LSL2", m), ("KQ4", m2)):
        check(f"{lbl}: no machine cache exists to collide", hasattr(mm, "_mcache"), False)
        check(f"{lbl}: no machines in the runtime model", hasattr(mm, "machines"), False)
    # `(ego setScript: tickle)` sits INSIDE `(if (ego has: iFeather) ...)`, so the
    # feather gates the machine's ENTRY. Scanning for the setScript symbol without
    # its guard hands you the whale's exit for free.
    check_in("derives the whale (rm31->44 iFeather)", (31, 44, "iFeather"), strands2)
    # rm78's `jump` is `(-- jumpNum)` then `(if (== jumpNum -1) (newRoom: 77))`. When
    # path conditions were evaluated against the state's ENTRY counter store, the test
    # demanded jumpNum==-1 on entry, which is unreachable -- so the machine delivered
    # NO exit and (78,77) fell back. Ops now carry TESTs in source order.
    check("rm78->rm77 is trusted (the test sees the decrement before it)",
          (78, 77) in m2.machine_edges, True)
    check("KQ4 machine exits: trusted / fallback",
          (len(m2.machine_edges), len(m2.machine_untrusted)), (37, 7))
    # KQ4's death write is `(= dead TRUE)` -- a Sym, not an int. Requiring an int
    # literal meant machine.py produced 0 DEATH sinks for KQ4 against LSL2's 41, so
    # KQ4 machines walked straight THROUGH their death states and handed out every
    # exit downstream as if you had survived.
    from machine import all_machines                             # noqa: PLC0415
    n_death = sum(1 for ms in all_machines(g2).values() for mm in ms.values()
                  for ps in mm.states.values() for p in ps for k, _ in p if k == "DEATH")
    check("KQ4 machines have DEATH sinks (the write is `dead TRUE`, a Sym)",
          n_death > 0, True)

    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
