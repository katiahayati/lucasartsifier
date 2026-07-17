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

    # The `st is None` activator bug conjured these out of walk-out-on-control exits
    # that live in doit/handleEvent and have no activator at all.
    for item in ("Lottery_Ticket", "Dollar_Bill", "Wad_O__Dough"):
        check_not_in(f"no phantom {item} strand", (11, 101, item), strands)
    check("no phantom strandings from doit-exits",
          {s for s in strands if s[1] in (101, 114, 125)}, set())

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
    check("the crater's debug hand-out of the bomb is dead",
          any(rm == 82 and C.holds_tree(gd, r.items, r.flags) for rm, gd in m.acq[21]),
          False)
    # The Hair_Rejuvenator's REAL source is rm151 (the barber's chair, off rm51), and it
    # is gone the moment you board the plane. That much the model gets right; what it
    # cannot see is that you NEED it -- see lsl2-bomb-has-no-script-level-gate.
    check("rejuvenator unobtainable past the plane gate",
          21 in C.closure(m, 58, frozenset(r.items) - {21}).items, False)

    # The raft machine must be lifted and trusted, else none of the above is real.
    check("raft exit rm138->rm42 is machine-owned", (138, 42) in m.machine_edges, True)
    check("raft models `day` as a bounded counter",
          m.machines[138]["rm138Script"].counters, {"day": (-1, 10)})

    print("\nKQ4")
    g2, m2, r2, goals2, total2, strands2 = run(config.KQ4)
    check("SANITY: shipped game is winnable", bool(r2.rooms & goals2), True)
    check("rooms reached", len(r2.rooms), 88)
    # `(ego setScript: tickle)` sits INSIDE `(if (ego has: iFeather) ...)`, so the
    # feather gates the machine's ENTRY. Scanning for the setScript symbol without
    # its guard hands you the whale's exit for free.
    check_in("derives the whale (rm31->44 iFeather)", (31, 44, "iFeather"), strands2)

    print()
    if FAILS:
        print(f"FAILED ({len(FAILS)}): {', '.join(FAILS)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
