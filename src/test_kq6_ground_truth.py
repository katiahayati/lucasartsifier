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
#
# EVERY COLUMN IS A SET OF REQUIREMENT **UNITS**, because that is what the tool produces.
# `edge_strandings` speaks in units -- an `items` entry is a singleton, a `groups` entry is a
# DISJUNCTION of rival solutions -- and `group_strandings` emits nothing else. This file used to
# flatten all of that to a set of item NAMES, which cost real information twice over:
#
#   * A unit that CHANGES SHAPE could only ever surface as a DROP. When the genie's third solution
#     (the lamp Jollo hands back) lands, `{mint, peppermint}` becomes `{mint, peppermint, newLamp}`
#     -- strictly more correct, and the flattened oracle would have screamed regression.
#   * It hid which DETECTOR is carrying a verdict. Measured: KQ6 emits `{mint, peppermint}` as an
#     edge unit and NO singleton `{mint}` edge unit at all. The names `mint` and `peppermint`
#     reached the old flat `caught` set only via `dangerous_sinks` -- so the oracle's claim to catch
#     them as B4 carry-ins was being carried by a different finding class than the comment says.
#
# Write a singleton as a plain string and a disjunction as a tuple; `_unit` normalises both.
# Shape changes are therefore LOUD: they show up as a drop AND an addition, naming both shapes.

def _unit(x):
    """One requirement UNIT: a single item, or a disjunction of rival solutions to one puzzle."""
    return frozenset({x}) if isinstance(x, str) else frozenset(x)


def _units(xs):
    return {_unit(x) for x in xs}


def _names(units):
    """Every item name any unit mentions -- the flat view, kept for the SAFE rules below."""
    return {n for u in units for n in u}


EXPECTED_CAUGHT = _units({
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
    "nightingale",      # the short path's castle carry-in
    ("mint", "peppermint"),
                        # RIVAL SOLUTIONS to rm750's genie, and this is the unit the edge detector
                        # actually emits -- `giveGenieMint` has entries [own(mint), own(peppermint)].
                        # The walkthroughs agree ("you can also defeat Shamir by giving him some
                        # mint leaves"). ⚠️ KNOWN INCOMPLETE: the genie has a THIRD solution,
                        # `useLamp` (doVerb 92), which is invisible because the lamp's `message`
                        # property is REWRITTEN at run time -- `jolloGivesLamp:99` sets item 25's
                        # message from 57 to 92 when Jollo hands it back, and
                        # `vocab.doverb_item_messages` reads only the declared value. When that is
                        # fixed this unit becomes {mint, peppermint, newLamp} and will surface here
                        # as a DROP plus an ADDITION, which is the point of comparing units.
    "mint",             # user-listed castle carry-in. Reached as a SINGLETON only via
    "peppermint",       # `dangerous_sinks` (a wasteful consumption), NOT via the edge detector --
                        # which the old flattened oracle could not show. Both promoted 2026-07-28
                        # with the user's sign-off; peppermint once the phantom developer hand-outs
                        # stopped giving it sources at rm740/rm750.
    # DANGEROUS ACTIONS -- not boundary crossings. Both promoted 2026-07-28 with the user's sign-off.
    "huntersLamp",      # trade the old lamp to the peddler and he LEAVES (flag 12, one writer,
                        # never cleared). `rm580::init` wants it to cast rain instead of caging
                        # you: (if (and (has: 19) (== global161 15)) makeRain else inTheCage).
    "skull",            # throwing it into rm420's gears is a move the game invites and it looks
                        # like the solution -- the gears eat it and state 24 re-arms `sqwishEm`.
                        # User: "that's exactly the kind of bad use we need to prevent."
})

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
LONG_ENDING_ONLY = _units({"teaCup"})

# CONFIRMED SAFE -- flagging one of these is a false positive, not a promotion.
#   shield: user, 2026-07-27, after testing -- "you were completely right and I was completely
#     wrong. Yes you can go back to either level of the catacombs." It is re-obtainable.
#   clothes: only needed OUTSIDE the castle, to get in.
#   coal: settled 2026-07-28 from docs/KQ6-ITEM-ORACLE.md rows 6 and 10. Coal is given to the White
#     Queen on the Isle of Mists in exchange for the spoiled EGG, and it is the egg that is carried
#     into the Realm. Coal itself never crosses a boundary -- source rm560, every use at rm490,
#     both on the open map -- so it was a KNOWN_GAP by association with a chain it does not travel.
#
# NAMES, not units, and deliberately: the DROP/ADDITION rules ask "is this the same requirement",
# where shape matters, but "is a safe item being flagged" asks whether it is MENTIONED AT ALL. An
# item the user tested and cleared has no business inside a disjunction either. Same reading is
# applied to LONG_ENDING_ONLY below.
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

    # EVERY UNIT the tool emits, read in the shape each detector speaks. `edge_strandings` is used
    # directly rather than through `analyze()` because `analyze()` is the per-(item, need-component)
    # REPORT view and drops the groups on the floor -- which is how a disjunction became invisible
    # to this file in the first place. The flattened name set is identical either way (measured).
    caught = set()
    for e in s.edge_strandings():
        caught |= {_unit(s.g.item_name(i)) for i in e["items"]}
        caught |= {frozenset(s.g.item_name(i) for i in g) for g in e["groups"]}
    for r in s.group_strandings():
        caught.add(frozenset(s.g.item_name(i) for i in r["items"]))
    for rows in (s.joint_strandings(), s.resource_exhaustion(), s.dangerous_sinks(),
                 s.register_flip_strandings(), s.fatal_uses()):
        caught |= {_unit(s.g.item_name(r["item"])) for r in rows}
    caught_names = _names(caught)

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(sorted(u) for u in missing)} -- STOP. Confirm with the user before "
          f"touching EXPECTED_CAUGHT (see memory kq6-softlock-ground-truth). If the same items "
          f"appear under ADDITIONS below, the unit CHANGED SHAPE rather than vanishing -- still a "
          f"ruling, not a rubber stamp.")

    surprises = caught - ALLOWED
    check("no UNEXPECTED unit flagged (suspicion)", not surprises,
          f"NEW: {sorted(sorted(u) for u in surprises)} -- a requirement not on the oracle is being "
          f"flagged. If it is real, promote it with the user's OK; if not, it is a false positive. "
          f"Either way, confirm.")

    check("a re-obtainable item is not flagged (the shield ruling)",
          not (caught_names & CONFIRMED_SAFE),
          f"FLAGGED: {sorted(caught_names & CONFIRMED_SAFE)} -- the user tested these and they are "
          f"safe. By NAME, so hiding one inside a disjunction does not get it past this check.")

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
              for c in s.analyze() if s.g.item_name(c["item"]) in
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
          not (caught_names & _names(LONG_ENDING_ONLY)),
          f"FLAGGED: {sorted(caught_names & _names(LONG_ENDING_ONLY))} -- these gate the long "
          f"ending, not the win itself, so under the current goal (rm180) they should not fire. If "
          f"one does, the goal or the two-castle-entrance path model has moved; do not just "
          f"promote it. By NAME, for the same reason as CONFIRMED_SAFE.")

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
    # ...and the LONG door is the SAME class of error, by a different mechanism. It used to demand
    # `nightingale`, which the user ruled optional on that route (2026-07-29). It is stronger than
    # optional: the bird is IMPOSSIBLE there. The paint brush that opens this door is the bird
    # after three trades over the pawn-shop counter -- bird -> flute -> tinderbox -> brush -- and
    # rm280's `itemTradeScr` refuses to hand over any of the four while you hold one of them. So
    # demanding the bird here WALLED the route, exactly as the Realm items walled the short one.
    #
    # Three earlier readings of this, all superseded, kept only so nobody re-derives them:
    #   * "We have no notion of NECESSITY." True and still true -- banning the bird loses 0 rooms
    #     and the goal stays reachable -- but it was never the question. This is an EXCLUSION, and
    #     exclusions do not need necessity.
    #   * "The use site cannot be split by state." Also true: `doVerb 37` on `floor` is a
    #     NewFeature cast unconditionally, rm850 carries flag-15 = [0, 1] under BOTH doors (rm730
    #     and rm710 are mutually reachable once inside), and the long route reaches rm850 on its
    #     own path, 230 -> 710 -> 720 -> 800 -> 810 -> 781 -> 850. Splitting the use site was the
    #     wrong lever; the door's OWN demand was the lever.
    #   * "It rests on a three-strikes capture counter we do not model." That is about why the bird
    #     is needed on the SHORT route, which the oracle already asserts and which nothing here
    #     has to derive.
    long_door = doors.get((230, 710))
    check("the LONG castle door does not demand the short route's items",
          long_door and not ({"mint", "nightingale"} &
                             {s.g.item_name(i) for i in long_door["items"]}),
          repr(long_door and sorted(s.g.item_name(i) for i in long_door["items"])))
    check("...and it too says WHY, naming the trade rather than just dropping the item",
          long_door and {"nightingale"} <= {s.g.item_name(i) for i in
                                            long_door.get("dropped_incompatible", ())},
          repr(long_door and long_door.get("dropped_why")))

    # THE EXCHANGE SLOT itself, pinned separately from the guard it fixes: the guard could come
    # right for some other reason and this fact would still be the thing we believe. All four are
    # sourced ONLY at the pawn shop and dropped there too, which is what makes the set a counter's
    # stock rather than four coincidences.
    slots = {frozenset(s.g.item_name(i) for i in S): R for (S, R) in s.exchange_slots()}
    check("the pawn shop's four traded items are ONE exchange slot",
          slots == {frozenset({"brush", "flute", "nightingale", "tinderBox"}): 280},
          f"exchange_slots = {slots} -- expected exactly the pawn counter's stock at rm280. "
          f"A drop means the menu, the single-counter test or the refusal guard stopped being "
          f"seen; an ADDITION means the rule is over-grouping (see missability.exchange_slots, "
          f"which measured 13 OR-of-own guard sets in KQ6 of which only this one is a menu).")

    promoted = caught & KNOWN_GAPS
    if promoted:
        print(f"  [note] a KNOWN GAP is now being caught: {sorted(sorted(u) for u in promoted)} -- "
              f"if the user confirms it is correct, promote it from KNOWN_GAPS into "
              f"EXPECTED_CAUGHT.")

    def show(units):
        return sorted(next(iter(u)) if len(u) == 1 else "(" + " | ".join(sorted(u)) + ")"
                      for u in units)

    print(f"\n  caught now ({len(caught)} units): {show(caught)}")
    print(f"  still-missed ground truth: {show(KNOWN_GAPS - caught)}")
    print(f"  long-ending-only (deliberately not caught): {show(LONG_ENDING_ONLY)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
