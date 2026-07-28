"""KQ6 stranding-item ORACLE -- the SCI1.1 twin of `test_kq4_ground_truth`.

KQ6 is the title the SCI1.1 work is validated on, and its catacombs findings have now been
rediscovered and re-lost more than once (the hole-in-the-wall's first piece was implemented and
reverted TWICE, and `daggerOfRa` silently vanished from the Dagger of Amon Ra between two commits
with nothing to notice it). This test makes that failure mode loud.

Deliberately NOT a full-surface golden: KQ6 is under active development, so guard specs and
placements are expected to move. It pins ONLY the item-level verdicts, plus the two structural
facts the catacombs work rests on.

Same two rules as the KQ4 oracle, from the user:
  * A DROP from EXPECTED_CAUGHT is a REGRESSION -> STOP and confirm before touching the list.
  * An ADDITION is treated with SUSPICION -> confirm. It may be a real new catch to promote out of
    KNOWN_GAPS, or a false positive.

Provenance differs per item and is recorded inline, because it matters how much weight each
carries: some are in-game user rulings, the rest are walkthrough-derived. See memory
`kq6-softlock-ground-truth` and `docs/KQ6-SOFTLOCK-CANDIDATES.md`.
"""
import os
import sys

import config
import missability as M

# --- The oracle -------------------------------------------------------------------------------

EXPECTED_CAUGHT = {
    # THE FOUR CATACOMBS CARRY-INS. User, 2026-07-27: "No, you cannot complete the labyrinth
    # without those items." The catacombs have no exit until the minotaur is dead, so anything you
    # need in there must be carried in.
    "scarf",            # show it to the minotaur -- the only thing that sets `scarfOnMino`
    "brick",            # rm420's crushing ceiling; a cut vertex on the only way down
    "tinderBox",        # rm406 is pitch dark, and the trapdoor fall into it is the only descent
    "holeInTheWall",    # put it up, spy on the minotaur, learn where the secret door is
    # THE REALM OF THE DEAD (one visit; flag 15 is set on arrival and never cleared).
    "mirror",           # user-confirmed in-game: you cannot walk away from the Lord of the Dead,
                        # and holding up the mirror is the only way out of rm690
    "deadMansCoin",     # Charon's toll, consumed at the crossing
    "skeletonKey",      # obtained inside; opens the chest that holds the vizier's letter
    "handkerchief",     # obtained at rm630 (the mother ghost), needed at rm820 in the endgame
                        # dungeon -- a B3 carry-OUT. Promoted 2026-07-28 with the user's sign-off.
                        # NOTE (user): its GUARD placement is part of the endgame path-forcing
                        # split and is deliberately left to the gater -- see [[path-forcing-guards]].
    # THE CASTLE (terminal).
    "dagger",           # Celeste's, taken from the catacombs and needed at rm800
    "mint",             # user-listed castle carry-in
    "nightingale",      # the short path's castle carry-in
}

# Real per the oracle, still missed. NOT failures -- they are the live TODO list, reported at the
# end of the run so a promotion is noticed. See docs/KQ6-SOFTLOCK-CANDIDATES.md for each row's
# measured state.
KNOWN_GAPS = {
    "teaCup",           # B3 carry-in / Styx-water carry-out, long path
    "huntersLamp",      # the old lamp -- traded away, and befriending Jollo depends on it
    "skull",            # B2 carry-down, AND the vessel for the B3 carry-in (amber + egg + hair)
    "peppermint",       # castle carry-in, short path; the oracle itself calls this one uncertain
}

# CONFIRMED SAFE -- flagging one of these is a false positive, not a promotion.
#   shield: user, 2026-07-27, after testing -- "you were completely right and I was completely
#     wrong. Yes you can go back to either level of the catacombs." It is re-obtainable.
#   clothes: only needed OUTSIDE the castle, to get in.
#   coal: settled 2026-07-28 from docs/KQ6-ITEM-ORACLE.md rows 6 and 10. Coal is given to the White
#     Queen on the Isle of Mists in exchange for the spoiled EGG, and it is the egg that is carried
#     into the Realm. Coal itself never crosses a boundary -- source rm560, every use at rm490,
#     both on the open map -- so it was a KNOWN_GAP by association with a chain it does not travel.
CONFIRMED_SAFE = {"shield", "clothes", "coal"}

ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_kq6_ground_truth: the KQ6 / SCI1.1 stranding oracle ===")
    if not (config.KQ6.ir_path and os.path.exists(config.KQ6.ir_path)):
        print("  (skip: no KQ6 IR)")
        return True
    s = M.load(cfg=config.KQ6)
    cands = s.analyze()
    ids = ({c["item"] for c in cands} | {j["item"] for j in s.joint_strandings()}
           | {r["item"] for r in s.resource_exhaustion()} | {d["item"] for d in s.dangerous_sinks()}
           | {r["item"] for r in s.register_flip_strandings()})
    caught = {s.g.item_name(i) for i in ids}

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(missing)} -- STOP. Confirm with the user before touching "
          f"EXPECTED_CAUGHT (see memory kq6-softlock-ground-truth).")

    surprises = caught - ALLOWED
    check("no UNEXPECTED item flagged (suspicion)", not surprises,
          f"NEW: {sorted(surprises)} -- an item not on the oracle is being flagged. If it is real, "
          f"promote it with the user's OK; if not, it is a false positive. Either way, confirm.")

    check("a re-obtainable item is not flagged (the shield ruling)",
          not (caught & CONFIRMED_SAFE),
          f"FLAGGED: {sorted(caught & CONFIRMED_SAFE)} -- the user tested these and they are safe.")

    # THE TWO STRUCTURAL FACTS the catacombs work rests on, pinned so a drop names its own cause
    # rather than showing up only as a missing item.
    #
    # 1. The hole-in-the-wall's only SOURCE is where the game first hands it to you. Sierra writes
    #    "take it back off the wall" with the same `get:` as "pick it up", in a shared script that
    #    every maze room loads, so the model used to believe the hole was freshly obtainable in all
    #    thirteen catacombs rooms -- inside the very trap it is needed to escape.
    hole = next((i for i in s.sources if s.g.item_name(i) == "holeInTheWall"), None)
    check("the hole-in-the-wall has ONE source, and it is not inside the maze",
          hole is not None and sorted(s.sources[hole]) == [480],
          f"sources={sorted(s.sources.get(hole, ())) if hole is not None else None} -- a take-back "
          f"is being counted as a first acquisition (see build_maps' source filter).")

    # 2. All four carry-ins strand at the SAME frontier: the way into the catacombs. That is what
    #    makes them one class rather than four coincidences, and it is the shape a carry-IN must
    #    have -- the boundary is the entrance, not the room the item is used in.
    fronts = {s.g.item_name(c["item"]): set(c.get("frontier_edges") or ())
              for c in cands if s.g.item_name(c["item"]) in
              ("scarf", "brick", "tinderBox", "holeInTheWall")}
    entry = {"rm340->rm370", "rm340->rm405", "rm340->rm440"}
    check("the carry-ins strand at the catacombs ENTRANCE, not inside",
          all(entry <= fronts.get(it, set()) for it in ("scarf", "tinderBox", "holeInTheWall")),
          repr(fronts))
    # The brick is the exception and correctly so: with the grid corrected, rm420 (the crushing
    # ceiling) is a cut vertex INSIDE the maze, so its frontier is every way into that room.
    check("...except the brick, whose frontier is the crusher it is used in",
          fronts.get("brick") and all(e.endswith("->rm420") for e in fronts["brick"]),
          repr(fronts.get("brick")))

    promoted = caught & KNOWN_GAPS
    if promoted:
        print(f"  [note] a KNOWN GAP is now being caught: {sorted(promoted)} -- if the user "
              f"confirms it is correct, promote it from KNOWN_GAPS into EXPECTED_CAUGHT.")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
