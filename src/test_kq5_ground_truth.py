"""KQ5 (King's Quest V, `kq5`) stranding ORACLE -- the fourth enumerated ground truth.

The oracle it enforces is `docs/KQ5-ORACLE.md`, derived 2026-08-14 from the game source plus
three independent walkthroughs (gamerwalkthroughs, walkthroughking, the Telltale dead-ends
thread), tiered with the game source winning. Same two rules as KQ4, KQ6 and LB2:

  * A DROP from EXPECTED_CAUGHT is a REGRESSION -> STOP and confirm before touching the list.
  * An ADDITION is treated with SUSPICION -> confirm: real new catch or false positive.

KQ5's structure, in one paragraph (the long form is the oracle doc): the world is a mostly
backtrackable SCC, so the softlocks are pockets, windows and slots. The temple is a consumed-
opener toll pocket (caught). The sail rm49->650/654 permanently loses the beach {48,49,50,90},
demanding the Shell (the hermit heals Cedric) and the Fishhook (fishes the Moldy_Cheese for
Mordack's machine) be carried across (both caught). The cat scene (rm6) and dog scene (rm12) are
exchange slots over one throwable pool {Shoe 8, Stick 16, Leg_of_Lamb 19, Fish 5}; a successful
cat throw is recorded as `put: <item> 6` in the ownedBy store, read by rm86's kidnapped-arrival
fork -- `rescue` (which still demands the Hammer) vs `yourStuck` (an unpreventable timed death).
Flag 83 closes the cat window ON ARMING, not on success -- the one-shot-window class. The four
deliberate REDs below are that complex plus the fortune teller's needle slot and the witch
region's worn-amulet fold; each is a real assertion that flips green when its detector lands,
per the promotion contract in tools/run_tests.py.
"""
import os
import sys

import config
import missability as M

# --- The oracle -------------------------------------------------------------------------------

# A -- REAL, AND WE CATCH IT. A drop here is a regression.
EXPECTED_CAUGHT = {
    # The temple toll pocket: rm214->rm18 behind the Staff(7), which the door consumes
    # (`put: 7 214`); the bottle and coin are inside the one-visit pocket. Golden since July.
    "Brass_Bottle",
    "Gold_Coin",
    # The sail: rm49->650/654 is the beach region's one-way frontier. Shell used at rm46 (the
    # hermit scene branches on `has: 23`); Fishhook used at rm67 (`lookInMseHole` -> the cheese).
    # First caught 2026-08-14, the day KQ5 was re-measured on the post-KQ6/LB2 engine.
    "Shell",
    "Fishhook",
    # Rope on the branch at rm30 kills you (the ledge is the survivable target; walkthrough-
    # confirmed "the branch is too weak"). fatal_uses' row names the machine.
    "Rope",
}

# B -- REAL, PARTIALLY CAUGHT: the sink rows name the right sites (spending a pool item at the
# dog starves the cat scene) but are blind to the disjunction -- fatal only when it empties the
# pool with the cat window still open. Their PRESENCE is expected; their SHAPE is pinned below;
# the full window detection is the KNOWN GAP red further down.
ALLOWED_PARTIAL = {"Shoe", "Stick"}

# C -- OPEN RULING: the peas are a counted consumable spelled as the ITEM'S OWN `cel` property
# (castle.sc increments `((global9 at: 24) cel:)` per throw) -- the item-property store, which
# does not exist yet. The 13 exhaustion rows are its coarse shadow; tolerated, not demanded.
ALLOWED_OPEN = {"Bag_of_Peas"}

# F -- FALSE POSITIVE TO CURE, savior-condemned with a NEW POLARITY: Dink inits only while
# `own(34)` holds, so hugScript's unsurvivable arming carries the tambourine in its ENTRY guard
# (the monster's existence condition) rather than a branch -- and giving the tambourine
# (`giveTamboScript`, `put: 34`, drops the Hairpin) is the escape from that very machine.
# Holding it there is mandatory for progress, so the row's advice is unfollowable. The dedicated
# red below owns this; the item sits in ALLOWED so the suspicion check does not double-count it.
FP_EMITTED = {"Tambourine"}

ALLOWED = EXPECTED_CAUGHT | ALLOWED_PARTIAL | ALLOWED_OPEN | FP_EMITTED

# --- MECHANISM PINS [[oracle-must-pin-the-mechanism]]: every column-A item pins its FULL row
# set, so an FP that happens to NAME an oracle item cannot score as the catch.
MECHANISM_ROWS = {
    "Brass_Bottle": {
        "toll_strandings: {'pattern': 'one-visit-toll-pocket', 'toll_item': 7, "
        "'toll_item_name': 'Staff', 'toll_reg': None, 'toll_edge': [214, 18], "
        "'pocket': [18], 'source_rooms': [18]}",
    },
    "Gold_Coin": {
        "toll_strandings: {'pattern': 'one-visit-toll-pocket', 'toll_item': 7, "
        "'toll_item_name': 'Staff', 'toll_reg': None, 'toll_edge': [214, 18], "
        "'pocket': [18], 'source_rooms': [18]}",
    },
    "Shell": {"analyze: need@rm46 sources=[49] frontier=rm49->rm650|rm49->rm654"},
    "Fishhook": {"analyze: need@rm67 sources=[90] frontier=rm49->rm650|rm49->rm654"},
    "Rope": {"fatal_uses: {'room': 30, 'machine': 'ropeOnBranch', 'states': [0]}"},
    # The partial catches are pinned too -- if the disjunction-aware cure changes their shape,
    # that is a mechanism change to confirm, not silent churn.
    "Shoe": {
        "dangerous_sinks: {'room': 12, 'script': 12, 'dest': 12, 'at_room': 12, "
        "'still_needed_at': [6]}",
    },
    "Stick": {
        "dangerous_sinks: {'room': 12, 'script': 12, 'dest': 12, 'at_room': 12, "
        "'still_needed_at': [6]}",
    },
}

DETECTORS = ("analyze", "joint_strandings", "resource_exhaustion", "dangerous_sinks",
             "register_flip_strandings", "toll_strandings", "fatal_uses", "register_strandings")

# The throwable pool (rm6's cat handlers and rm86's rescue fork agree on exactly these four).
POOL = {"Shoe", "Stick", "Leg_of_Lamb", "Fish"}


def _mech_row(det, r):
    if det == "analyze":
        return "analyze: need@rm%s sources=%s frontier=%s" % (
            r["need_room"], r["source_rooms"], "|".join(r["frontier_edges"]))
    if det == "register_strandings":
        return "register_strandings: reg%s=%s->%s" % (
            r["register"], r["value"], r["still_needed_at"])
    return "%s: %r" % (det, {k: v for k, v in r.items() if k not in ("item", "item_name")})


PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}"
          + (f"\n      {detail}" if detail and not cond else ""))


def run():
    print("=== test_kq5_ground_truth: the KQ5 pocket/window/slot stranding oracle ===")
    cfg = config.by_name("kq5")
    if cfg is None or not os.path.exists(cfg.ir_path):
        print("  (skip: no KQ5 IR -- build/sweep/kq5)")
        return True
    s = M.load(cfg=cfg)

    rows_by_item = {}
    raw_rows = []                      # (item_name, det, row) for the structural reds below
    for det in DETECTORS:
        for r in getattr(s, det)():
            name = r.get("item_name") or s.g.item_name(r["item"])
            rows_by_item.setdefault(name, set()).add(_mech_row(det, r))
            raw_rows.append((name, det, r))
    caught = set(rows_by_item)

    print("  -- attribution: every detector row, by item --")
    for name in sorted(rows_by_item):
        for row in sorted(rows_by_item[name]):
            print("    %-14s %s" % (name, row))

    missing = EXPECTED_CAUGHT - caught
    check("no confirmed softlock has DROPPED (regression)", not missing,
          f"DROPPED: {sorted(missing)} -- STOP. Confirm with the user before touching "
          f"EXPECTED_CAUGHT; see docs/KQ5-ORACLE.md.")

    surprises = caught - ALLOWED
    check("no UNEXPECTED item flagged (suspicion)", not surprises,
          f"NEW: {sorted(surprises)} -- not on the oracle's list. Real -> promote with the "
          f"user's OK; not -> false positive. Either way, confirm.")

    for name in sorted(MECHANISM_ROWS):
        want, got = MECHANISM_ROWS[name], rows_by_item.get(name, set())
        check("mechanism pinned: %s" % name, want == got,
              "PINNED ROW MISSING: %s | UNPINNED ROW PRESENT: %s. A mechanism change: confirm "
              "against the game, then re-pin with the user's OK."
              % (sorted(want - got), sorted(got - want)))

    # --- structural fact the whole rm86 complex rests on: the basement exit is modelled -------
    # The gate arrived silently via the KQ6/LB2-era machinery (measured 2026-08-14): free iff
    # prevRoom != 85, else own(Hammer). Pinned green so "someone un-models the basement" is loud.
    metas = s._emeta.get((86, 28), ())
    hammer_alt = any(22 in alt for (_req, _sets, alts) in metas for alt in alts)
    prev_free = any(85 not in _req.get(12, {85}) and not any(alts0 for alts0 in alts if alts0)
                    for (_req, _sets, alts) in metas) or \
                any(12 in _req and 85 not in _req[12] for (_req, _sets, _alts) in metas)
    check("the basement exit rm86->rm28 carries the kidnap fork (own(22) vs prev!=85)",
          hammer_alt and prev_free,
          f"metas={metas!r} -- expected one alternative demanding own(22) and one free under "
          f"prevRoom != 85. If this moved, the handler-latch/machine-exit composition regressed.")

    # --- THE DELIBERATE REDS: real, missed, and declared -------------------------------------
    # Each is a live assertion that flips green the day its detector lands; tools/run_tests.py
    # KNOWN_RED carries the justification and the promotion contract does the rest.

    hammer_rows = [n for (n, _d, _r) in raw_rows if n == "Hammer"]
    check("🔴 KNOWN GAP (KQ5): the inn-cellar corral demands the Hammer", bool(hammer_rows),
          "No detector emits a row for the (rm86, prev=85) trap even though the exit gate is "
          "modelled (the green pin above). Needs the (room, register-value) trapped-state walk "
          "-- docs/KQ5-ORACLE.md §2.")

    def _rooms_mentioned(r):
        out = {x for x in (r.get("still_needed_at") or ()) if isinstance(x, int)}
        if isinstance(r.get("need_room"), int):
            out.add(r["need_room"])
        return out

    window_rows = [n for (n, _d, r) in raw_rows if n in POOL and 86 in _rooms_mentioned(r)]
    check("🔴 KNOWN GAP (KQ5): the cat-scene window reaches the kidnap read", bool(window_rows),
          "No row ties a pool item to rm86's rescue fork. The one-shot window (flag 83 set on "
          "ARMING; producers `put: <item> 6` all guarded on the window) is the class -- "
          "docs/KQ5-ORACLE.md §1.")

    needle_rows = [n for (n, _d, _r) in raw_rows if n == "Golden_Needle"]
    check("🔴 KNOWN GAP (KQ5): the fortune teller's needle substitution is caught",
          bool(needle_rows),
          "rm13 accepts Gold_Coin(11) OR Golden_Needle(3) in the amulet slot (`put: 3 13`); "
          "paying with the needle starves the tailor->cloak chain. Exchange-slot class -- "
          "docs/KQ5-ORACLE.md §6.")

    lamb_rows = [n for (n, _d, _r) in raw_rows if n == "Leg_of_Lamb"]
    check("🔴 KNOWN GAP (KQ5): the roc's-nest lamb fold is caught", bool(lamb_rows),
          "rm42 state 6: `owner(19)==34` (lamb fed to the eagle) -> newRoom 43; anything else "
          "-> proc0_26 death -- and the eagle also EATS the pie without earning the rescue. "
          "Throwing the lamb at the cat or dog is therefore fatal at rm42. The SAME "
          "init-fork-on-an-ownedBy-value death fold as rm86's -- phase 1 of the window plan "
          "should flip this red and the corral red together. docs/KQ5-ORACLE.md §1a.")

    amulet_rows = [n for (n, _d, _r) in raw_rows if n == "Amulet"]
    check("🔴 KNOWN GAP (KQ5): the witch-region worn-amulet death fold is caught",
          bool(amulet_rows),
          "witchRegion.sc survives the fireball only under `(and (has: 27) flag84)`; the fold "
          "lives in a REGION script, outside the current death-fold scope -- "
          "docs/KQ5-ORACLE.md §7.")

    tambo_fatal = [r for (n, d, r) in raw_rows if n == "Tambourine" and d == "fatal_uses"]
    check("🔴 KNOWN FP (KQ5): fatal_uses does not condemn the tambourine", not tambo_fatal,
          "hugScript's arming carries own(34) because Dink EXISTS only while you hold the "
          "tambourine, and giving it is the escape -- the sixth savior-condemned correction, "
          "new polarity (the item rides the arming guard, not a branch). Cure the detector; "
          "do not edit this oracle row.")

    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
