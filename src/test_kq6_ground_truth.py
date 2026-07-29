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

FOUR columns, because "real softlock" and "we should flag it" are not the same question:
EXPECTED_CAUGHT (real, and we catch it) · KNOWN_GAPS (real, and we miss it) · CONFIRMED_SAFE
(re-obtainable -- flagging one is a false positive) · LONG_ENDING_ONLY (gates the long ending, not
the win itself -- deliberately not caught under the current goal).

The goal changed under this test on 2026-07-28 and the verdicts did not move: it used to be the
discovered `{94, 205}` (the CREDITS, which roll after the vizier's wedding too, so LOSING reached
it) and is now the declared `{180}`, the post-fight kiss cutscene that is the only way to arrive at
rm740 with prevRoom 180 and so the only thing that arms `alexWedding`. See docs/KQ6-GOAL.md. The
long ending is a variant of that same win, gated on flag 15 inside `alexWedding`, so this column
means the same thing it always did.

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
    "peppermint",       # the short path's other castle carry-in. Promoted 2026-07-28 with the
                        # user's sign-off, once the phantom developer hand-outs stopped giving it
                        # sources at rm740/rm750 -- frontier rm220->rm730 / rm230->rm710, the B4
                        # boundary its oracle row predicted, plus a dangerous sink at rm180.
    # DANGEROUS ACTIONS -- not boundary crossings. Both promoted 2026-07-28 with the user's sign-off.
    "huntersLamp",      # trade the old lamp to the peddler and he LEAVES (flag 12, one writer,
                        # never cleared). `rm580::init` wants it to cast rain instead of caging
                        # you: (if (and (has: 19) (== global161 15)) makeRain else inTheCage).
    "skull",            # throwing it into rm420's gears is a move the game invites and it looks
                        # like the solution -- the gears eat it and state 24 re-arms `sqwishEm`.
                        # User: "that's exactly the kind of bad use we need to prevent."
}

# Real per the oracle and still missed. NOT failures -- the live TODO list, reported at the end of
# the run so a promotion is noticed. **EMPTY as of 2026-07-28**: every item the oracle calls real is
# caught. Kept, with its reporting, because the next KQ6 finding lands here first.
KNOWN_GAPS = set()

# GATES THE LONG ENDING, NOT WINNABILITY -- deliberately NOT caught, and not a gap.
#
# Our question is "can you still reach the credits", and KQ6 has two castle entrances that are the
# game's two paths: rm220->rm730 on the disguise (short) and rm230->rm710 on the magic paint
# (long). An item needed only for the long path therefore does not make the game unwinnable, and
# the model is right not to flag it.
#
#   teaCup: user, 2026-07-28, two rulings the same day and the second one narrows the first.
#     First: "it's required for the long ending and we should not let you leave the realm of the
#     dead without it." Then: "the tea cup is only needed outside the castle to get in" -- which is
#     the same argument that put `clothes` in CONFIRMED_SAFE. What that argument does NOT cover is
#     the Styx water: you draw it at rm660 during the Realm's single visit, and flag 58 is a hard
#     conjunct on mixing the paint (`KqInv.sc:2136` arms `mixPaintScr` under
#     `(and flag68 flag58 (not flag22))`). So if this ever becomes a softlock the boundary is the
#     REALM EXIT, not the castle entrance. Parked by the user -- "we'll really figure it out later".
#
# Same class as the four island treasures, which gate the BEST ending (docs/KQ6-SOFTLOCK-CANDIDATES).
# In ALLOWED, so catching one is a question rather than a hard failure -- but it IS a question:
# under the current goal (rm180 = `alexWedding` armed) it should not fire, so if it does, the goal
# or the path model has moved.
LONG_ENDING_ONLY = {"teaCup"}

# CONFIRMED SAFE -- flagging one of these is a false positive, not a promotion.
#   shield: user, 2026-07-27, after testing -- "you were completely right and I was completely
#     wrong. Yes you can go back to either level of the catacombs." It is re-obtainable.
#   clothes: only needed OUTSIDE the castle, to get in.
#   coal: settled 2026-07-28 from docs/KQ6-ITEM-ORACLE.md rows 6 and 10. Coal is given to the White
#     Queen on the Isle of Mists in exchange for the spoiled EGG, and it is the egg that is carried
#     into the Realm. Coal itself never crosses a boundary -- source rm560, every use at rm490,
#     both on the open map -- so it was a KNOWN_GAP by association with a chain it does not travel.
CONFIRMED_SAFE = {"shield", "clothes", "coal"}

ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS | LONG_ENDING_ONLY

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

    # THE GOAL, pinned here because every verdict below is measured against it and because it was
    # wrong for the whole life of this file until 2026-07-29: discovery returned rm94, the CREDITS,
    # which roll after the vizier's wedding too, so LOSING satisfied it. It is DERIVED, not
    # declared -- `anchors._resolve_pass_through` reads rm740's rival endings. rm180 is the
    # post-fight kiss, the only way to enter rm740 with prevRoom 180 and so the only thing that
    # arms `alexWedding`. See docs/KQ6-GOAL.md; the derivation is flagged PROVISIONAL there.
    check("the goal is the WIN, not the credits", set(s.em.cfg.goal_rooms) == {180},
          f"goal_rooms = {sorted(s.em.cfg.goal_rooms)}; expected {{180}}. If this became "
          f"{{94, 205}} the pass-through rule stopped firing and defeat satisfies the goal again.")

    cands = s.analyze()
    ids = ({c["item"] for c in cands} | {j["item"] for j in s.joint_strandings()}
           | {r["item"] for r in s.resource_exhaustion()} | {d["item"] for d in s.dangerous_sinks()}
           | {r["item"] for r in s.register_flip_strandings()}
           | {f["item"] for f in s.fatal_uses()})
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

    check("a LONG-ENDING-only item is not flagged as unwinnable",
          not (caught & LONG_ENDING_ONLY),
          f"FLAGGED: {sorted(caught & LONG_ENDING_ONLY)} -- these gate the long ending, not the "
          f"win itself, so under the current goal (rm180) they should not fire. If one does, the "
          f"goal or the two-castle-entrance path model has moved; do not just promote it.")

    # THE TWO CASTLE DOORS. rm220->rm730 is the servant-girl disguise (short route) and
    # rm230->rm710 is the magic paint (long route); both are one-way into the same terminal castle,
    # so both are real commitment points. But the Realm of the Dead is gated on flag 14, the ONLY
    # room that writes flag 14 is rm580 (the Druids), and rm580's escape BURNS Beauty's clothes --
    # which the short door requires. So the handkerchief and the skeleton key, which exist only
    # inside the Realm, can never be in hand at that door, and demanding them there would WALL the
    # short route rather than close a softlock. A drop here is not a cosmetic regression.
    import guards as G
    doors = {(sp["from_room"], sp["to_room"]): sp for sp in G.guard_specs(s)
             if sp["site"] == "edge" and (sp["from_room"], sp["to_room"]) in {(220, 730), (230, 710)}}
    short_door = doors.get((220, 730))
    realm_only = {"handkerchief", "skeletonKey"}
    check("the SHORT castle door does not demand the Realm-only items",
          short_door and not (realm_only & {s.g.item_name(i) for i in short_door["items"]}),
          repr(short_door and sorted(s.g.item_name(i) for i in short_door["items"])))
    check("...and it says WHY they were dropped, rather than dropping them silently",
          short_door and set(short_door.get("dropped_incompatible", ())) and
          realm_only <= {s.g.item_name(i) for i in short_door.get("dropped_incompatible", ())},
          repr(short_door and short_door.get("dropped_why")))
    # RED, and the mechanism is now known (2026-07-28) -- do NOT "fix" this by narrowing the guard.
    # `nightingale` is the SHORT route's way past the castle guard dogs; the long route has Jollo
    # win them over instead. Three things stand between us and deriving that, measured in order:
    #   1. We have no notion of NECESSITY here. Banning the bird loses 0 rooms and the goal stays
    #      reachable -- as it does for the handkerchief and the mint. Every KQ6 finding rests on
    #      `edge_strandings`' proxy ("there is a USE SITE past the edge"), so "required to win"
    #      cannot be the discriminator without deleting all fourteen. RE-MEASURED 2026-07-28 after
    #      the goal was corrected from the credits to rm180 (`alexWedding`): still 0 rooms lost,
    #      for all ten flagged items. The old goal being satisfied by DEFEAT was not what was
    #      holding this up -- rm180/740/750/790 sit in one 18-room SCC, so no room-set goal can
    #      separate the win from the loss here. See docs/KQ6-GOAL.md.
    #   2. The use site cannot be split by state either: it is `doVerb 37` on `floor`, a
    #      NewFeature cast UNCONDITIONALLY, so both product copies of rm850 carry it.
    #   3. The dogs are not a flag-gated door. `spotEgoScr` is a REGION property (rgCastle:132
    #      `(if spotEgoScr (global2 setScript: spotEgoScr 0 param1))`) and the guards spot you
    #      POSITIONALLY -- the LSL2 rm47 henchmen shape. And capture is survivable: you escape
    #      twice (Jollo, then the skeleton key) and only the THIRD capture ends the game, so the
    #      bird's necessity rests on a three-strikes COUNTER we do not model.
    # Modelling the bit-array flag store (329 sites, inert on LSL2/KQ4/Dagger) is worth doing on
    # its own merits but was MEASURED not to deliver this. See docs/SCI11-PATCHING-PLAN.md 6.4.
    long_door = doors.get((230, 710))
    check("the LONG castle door does not demand the short route's items",
          long_door and not ({"mint", "nightingale"} &
                             {s.g.item_name(i) for i in long_door["items"]}),
          repr(long_door and sorted(s.g.item_name(i) for i in long_door["items"])))

    promoted = caught & KNOWN_GAPS
    if promoted:
        print(f"  [note] a KNOWN GAP is now being caught: {sorted(promoted)} -- if the user "
              f"confirms it is correct, promote it from KNOWN_GAPS into EXPECTED_CAUGHT.")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"  long-ending-only (deliberately not caught): {sorted(LONG_ENDING_ONLY)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
