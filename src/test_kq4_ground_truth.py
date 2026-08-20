"""KQ4 stranding-item ORACLE -- the user's enumerated ground truth, mechanically pinned.

The Peacock_Feather softlock has been re-discovered and silently re-lost 2-3 times. This test makes
that failure mode LOUD. It is deliberately NOT a full-surface golden (KQ4 is still under development,
so its guard specs / placements are expected to move); it pins ONLY the item-level ground truth the
user has enumerated and confirmed.

Two rules, from the user (2026-07-22):
  * A DROP from the currently-caught set is a REGRESSION -> STOP and confirm with the user before
    "fixing" the test. This is precisely the feather-regression we keep hitting.
  * An ADDITION (a new item flagged) is treated with SUSPICION -> confirm with the user. It might be
    a genuinely-new correct catch (e.g. Dead_Fish finally landing) that should be promoted into
    EXPECTED_CAUGHT with the user's OK, or it might be a false positive.

So: update EXPECTED_CAUGHT only deliberately, with the user's sign-off -- never to make a red test
green on your own. See memory `kq4-stranding-ground-truth`.
"""
import os
import sys

import config
import missability as M

# --- The oracle -------------------------------------------------------------------------------

# Confirmed ground-truth softlock items the model catches TODAY (across ALL detectors: edge/joint
# strandings, resource exhaustion, dangerous sinks). A drop here = regression.
EXPECTED_CAUGHT = {
    "Peacock_Feather",   # tickle the whale to escape; caught at edge rm31->rm44 (has:8)
    "Golden_Bridle",     # island behind the one-time whale; caught via joint (g12 x g183)
    # Obsidian_Scarab: RECLASSIFIED 2026-07-23 (user-confirmed via play-test). It is REQUIRED (dig
    # the cemeteries) but freely REOBTAINABLE -- a fresh scarab is tossed by the witch at rm57
    # (g109>2, holding the glass-eye, not owning the scarab). So it is missable-but-not-stranding,
    # NOT a softlock. Its earlier "catch" was a phantom: has:7 leaked out of the nightfall trigger's
    # OR-branch and gated the endgame gate (fixed by _own_required). Do NOT re-add without evidence
    # the reobtainment is gone. See memory kq4-stranding-ground-truth.
    "Magic_Hen",         # carried into the ending; rm45->rm690 + joint
    "Magic_Fruit",       # required for the victory ending; rm45->rm690 + joint (+ sink)
    "Cupid_s_Bow",       # waste the arrows -> can't kill Lolotte; caught via resource_exhaustion
    "Shovel",            # breaks after wrong digs; caught via resource_exhaustion
    "Dead_Fish",         # needed on the island past the one-time whale; caught via joint
                         # (deliverability: source rm95 can't reach need rm43 once the whale is spent)
    "Diamond_Pouch",     # dwarves' door rm22->54 shuts at night; caught via register_flip_strandings
    "Fishing_Pole",      # shanty door rm7->42 shuts at night (same class-2 trap); user-confirmed GT
}

# Confirmed/firmly-stated ground truth we do NOT yet catch. (Empty -- all known KQ4 ground truth is
# now caught; Diamond_Pouch + Fishing_Pole promoted 2026-07-22 via the class-2 nightfall detector.)
KNOWN_GAPS = set()

# The user (2026-07-22) assessed the remaining candidates from their old list as NOT gated -- i.e.
# probably NOT softlocks: Wiggly_Worm, Gold_Ball, Small_Crown, Frog, Talisman. They are deliberately
# NOT in ALLOWED, so if the model ever flags one it trips the suspicion alarm (confirm with the user).
ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_kq4_ground_truth: the user's enumerated stranding oracle ===")
    if not (config.KQ4.ir_path and os.path.exists(config.KQ4.ir_path)):
        print("  (skip: no KQ4 IR)")
        return True
    s = M.load(cfg=config.KQ4)
    # "caught" = flagged by ANY detector: edge/joint strandings, resource exhaustion, dangerous sinks.
    ids = ({c["item"] for c in s.analyze()} | {j["item"] for j in s.joint_strandings()}
           | {r["item"] for r in s.resource_exhaustion()} | {d["item"] for d in s.dangerous_sinks()}
           | {r["item"] for r in s.register_flip_strandings()})
    caught = {s.g.item_name(i) for i in ids}

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(missing)} -- STOP. A ground-truth KQ4 softlock is no longer flagged. "
          f"This is the feather-regression failure mode. Confirm with the user before touching "
          f"EXPECTED_CAUGHT (see memory kq4-stranding-ground-truth).")

    surprises = caught - ALLOWED
    check("no UNEXPECTED item flagged (suspicion)", not surprises,
          f"NEW: {sorted(surprises)} -- an item not on the ground-truth list is being flagged. "
          f"Treat with suspicion: if it is a real catch, add it to EXPECTED_CAUGHT with the user's "
          f"OK; if not, it may be a false positive. Either way, confirm with the user.")

    # The class-2 nightfall detector must be LSL2-safe BY DERIVATION, not by luck: LSL2's g127 has
    # the opposite shape (its safe value 0 is the pervasive one), so it is not a free-running trap
    # and seals nothing. Pin that here so the derivation can't silently start firing on LSL2.
    if os.path.exists(config.LSL2.ir_path):
        lsl2 = M.load(cfg=config.LSL2)
        check("class-2 detector is empty on LSL2 (g127 is not a trap -- derived, not dodged)",
              lsl2.free_running_traps() == {} and lsl2.register_flip_strandings() == [],
              f"free_running_traps={lsl2.free_running_traps()} register_flips="
              f"{[r['item_name'] for r in lsl2.register_flip_strandings()]}")

    promoted = caught & KNOWN_GAPS
    if promoted:
        print(f"  [note] a KNOWN GAP is now being caught: {sorted(promoted)} -- if the user confirms "
              f"it is correct, promote it from KNOWN_GAPS into EXPECTED_CAUGHT.")


    # ⭐ N4's TRIPWIRE, ASKED OF THIS GAME TOO (2026-08-20 fourth review, P6). `_falsifies` picks
    # the PERMISSIVE reading when a chain's writes leave a register either way, and that choice
    # is parked rather than derived -- so a game that actually asks the question has to say so
    # before the hold built on it ships. The assertion lived in KQ5's ground truth and nowhere
    # else, which made it a claim about one game instead of about the rule.
    _div, _fired, _shapes = M.n4_tripwire()
    print(f"  [n4] falsification questions asked: {_fired}, divergent: {len(_div)}")
    check("KQ4 (and the LSL2 cross-check) asks no divergent falsification question", not _div,
          f"divergent: {_div!r} (shapes asked: {_shapes!r}). The demand this game ships rests "
          f"on a reading of `chain_writes` that was CHOSEN, not derived -- see "
          f"`missability._falsifies`, N4. The USER decides which way it reads before this "
          f"game's hold is trusted.")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
