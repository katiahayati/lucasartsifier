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
import sys

import config
import missability as M

# --- The oracle -------------------------------------------------------------------------------

# Confirmed ground-truth softlock items the model catches TODAY. A drop here = regression.
EXPECTED_CAUGHT = {
    "Peacock_Feather",   # tickle the whale to escape; caught at edge rm31->rm44 (has:8)
    "Golden_Bridle",     # island behind the one-time whale; caught via joint (g12 x g183)
    "Obsidian_Scarab",   # crypt/graveyard required items; user-confirmed enumerated GT
    "Magic_Hen",         # carried into the ending; rm45->rm690 + joint
    "Magic_Fruit",       # required for the victory ending; rm45->rm690 + joint (+ sink)
}

# Confirmed/firmly-stated ground truth we do NOT yet catch. Listed so a NEW catch of one of these is
# recognised as a WIN (promote it into EXPECTED_CAUGHT with the user's OK), not flagged as suspicious.
KNOWN_GAPS = {
    "Dead_Fish",         # user fact #4: needed on the island past the whale; free rm31->43 gap
}

# The user's uncertain candidates + the item-property/resource class. Not enforced, but allowed to
# appear without tripping the suspicion alarm -- they are on the user's radar already.
SUSPECTED_OR_RESOURCE = {
    "Wiggly_Worm", "Gold_Ball", "Small_Crown", "Frog", "Diamond_Pouch", "Talisman",
    "Cupid_s_Bow", "Shovel",
}

ALLOWED = EXPECTED_CAUGHT | KNOWN_GAPS | SUSPECTED_OR_RESOURCE

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_kq4_ground_truth: the user's enumerated stranding oracle ===")
    if not (config.KQ4.ir_path and __import__("os").path.exists(config.KQ4.ir_path)):
        print("  (skip: no KQ4 IR)")
        return True
    s = M.load(cfg=config.KQ4)
    caught = {s.g.item_name(i)
              for i in ({c["item"] for c in s.analyze()} | {j["item"] for j in s.joint_strandings()})}

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

    promoted = caught & KNOWN_GAPS
    if promoted:
        print(f"  [note] a KNOWN GAP is now being caught: {sorted(promoted)} -- if the user confirms "
              f"it is correct, promote it from KNOWN_GAPS into EXPECTED_CAUGHT.")

    print(f"\n  caught now: {sorted(caught)}")
    print(f"  still-missed ground truth: {sorted(KNOWN_GAPS - caught)}")
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
