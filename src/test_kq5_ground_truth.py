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
Flag 83 closes the cat window ON ARMING, not on success -- the one-shot-window class.

⛔ KQ5 IS NOT A FINISHED ORACLE, and no run of this file should be reported as though it were.
Four of the fifteen scorecard rows are still MISSED with a declared red apiece, one is a false
positive we emit and have not cured (the tambourine; the Wand's was cured 2026-08-15, see below),
and several verdicts are open on their own terms (the peas
consumable waits on the item-property store; the locket window, the mountains' cold death and
the Hammer's crystal site are unverified against the source). The checks below passing means
the catches we HAVE are still there and still caught for the stated mechanism -- nothing more.

Two builds landed 2026-08-14. Phase 1, `ownedby_death_folds` (an arrival forks on an owner
value and the losing arm is a death the player cannot dodge), retired the kidnap-read, lamb-fold
and pie reds. Phase 2, item-banned fetch walks in `register_strandings`, retired the Hammer red.
Their rows are mechanism-pinned below. STILL RED: the two window-closure halves (phase 3 -- flag
83 closes on arming, flag 36's writer needs the fish), the fortune teller's needle slot, the
region-scope amulet fold, and the tambourine false positive.

A third build landed 2026-08-15: `missability._unrefusable_grants`, which retired the WAND false
positive. A room that hands you an item in `init` under nothing but `not (has: X)` is a handout
you cannot decline, so `_reach_without` stops there -- KQ5's rm1 does exactly that with Crispin's
wand. The full snapshot surface of LSL2, KQ4, KQ6 and LB2 is byte-identical across it.
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
    # ⛔ SHELL LEFT THIS LIST 2026-08-15, on the USER'S OWN RULING (2026-08-14): "you can sail
    # from the hermit island to the harpy island again to get the shell" -- re-obtainable, so not
    # a stranding. Its old row rested on the phantom cartoon edges (see below); it is not a
    # dropped catch, it is a false positive that went away with its cause.
    #
    # THE FISHHOOK: source rm90, used at rm67 (`lookInMseHole` -> the Moldy_Cheese), and you
    # cannot go back for it -- USER 2026-08-14, "once you are in mordack's lair you can't get back
    # out to get the fishhook". First caught 2026-08-14; RE-PINNED 2026-08-15 with the USER'S OK
    # after three defects were cured together (docs/KQ5-ORACLE.md §8). The old pin named the
    # frontier `rm49->rm650|rm49->rm654`, and those rooms DO NOT EXIST: 650/654 are Cedric's CD
    # view numbers, which reached the room universe through a temp-scope bug. The real frontier is
    # the hermit island's crossing to the far shore.
    "Fishhook",
    # ✅ PROMOTED 2026-08-15, USER-RULED REAL, all five: the model could not have emitted ANY of
    # these before, because one poisoned register projection (`global322`, an object-valued
    # scratch slot) emptied `_reach_without` for every item and `analyze()` returned zero rows for
    # all of KQ5 -- see `missability._object_valued_globals`. Two frontiers carry them:
    #   * rm40->rm41 is THE ROC carrying you off, KQ5's real point of no return -- Harp (rm9 ->
    #     needed rm90), Beeswax (rm24 -> rm44) and Crystal (rm38 -> rm52) must cross it;
    #   * rm44/45/46->rm113 is the hermit island's crossing to the far shore -- Iron_Bar
    #     (rm44 -> rm54) shares it with the Fishhook.
    # The Locket (rm42, the roc's nest -> needed rm57, Cassima's cell) crosses rm42->rm43.
    "Harp",
    "Beeswax",
    "Crystal",
    "Locket",
    "Iron_Bar",
    # Rope on the branch at rm30 kills you (the ledge is the survivable target; walkthrough-
    # confirmed "the branch is too weak"). fatal_uses' row names the machine.
    "Rope",
    # ✅ PROMOTED 2026-08-14 (phase 1, `ownedby_death_folds`): arrivals that fork on an OWNER
    # VALUE with an unpreventable death on the losing arm. Three softlocks flipped together:
    #   * the POOL at the kidnap read -- rm86's `yourStuck` (pure-timer death) arms unless
    #     some throwable's owner is 6, so all four pool items carry the rm86 demand under
    #     prev == 85 (Shoe and Stick keep their sink rows too; Leg_of_Lamb and Fish join here);
    #   * the roc's-nest lamb fold -- rm42 `hatch` state 6 forks on owner(19) == 34, the
    #     losing arm hidden behind a `(++ state)` skip the transition model now reads;
    #   * the pie at the yeti's door -- rm35 arriving from rm36 with the yeti unfed is the
    #     scripted `killEgo` kill (the rm36 chase itself makes no claim: a `Chase` state is a
    #     race the player can decline by leaving, which is what keeps KQ4's rm49 dog row out).
    "Leg_of_Lamb",
    "Fish",
    "Pie",
    # ✅ PROMOTED 2026-08-14 (phase 2): register_strandings' fetch walks now BAN the item they
    # fetch (`_psucc`'s own parachute discipline, applied to the source test) -- from
    # (rm86, prev==85) the only exit prices own(Hammer), so the permissive walk's "still
    # obtainable" dissolved and the kidnap corral emits its row: reg12=85, flip room 86,
    # needed at 86 (the cellar door). The row's context is exactly patch B's demand.
    "Hammer",
    # ✅ PROMOTED 2026-08-15 from the WALKTHROUGHS, at the user's instruction to check them.
    # gamerwalkthroughs.com/kings-quest-5: "Pick up the Fish and then walk up the stairs" -- on
    # Mordack's island, BEFORE the castle -- then "Keep going back and forth until you see a cat.
    # Throw Fish at the cat and then use the Bag on the cat to catch it"; the Fandom and eristic
    # walkthroughs add "from here on out, if you see the cat, you must throw the fish to him".
    # Source-confirmed: castle.sc, the REGION live in every castle room, dispatches
    # `(37 (= global332 2) (setScript: theThrowFishScript))` and `(24 ... theCat setScript: ...)`.
    # Measured: the source rm51 is NOT in the castle-side set {55..67, 124, 612, 670..673, 683},
    # and rm54's three exits are one-way, so walking up those stairs fishless is unrecoverable.
    # The same class as the Fishhook, one room over. Its rm683 carry-in row is NOT this catch --
    # see the declared red below.
    "Cat_Fish",
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
#
# ✅ THE WAND LEFT THIS SET 2026-08-15, CURED -- see the green pin below and docs/KQ5-ORACLE.md
# §10. It had been emitted since before the oracle existed. The cure is NOT the never-strandable
# class this file used to propose (a class shaped to protect a known answer, and refuted by the
# source: rm66's machine tray really does take the wand, it just hands it straight back), but
# `missability._unrefusable_grants` -- rm1's `init` gives Crispin's wand to anyone who does not
# have it, so no state past rm1 lacks it, and `_reach_without` no longer walks through it.
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
    "Fishhook": {"analyze: need@rm67 sources=[90] frontier=rm44->rm113|rm45->rm113|"
                 "rm46->rm113|rm46->rm661|rm660->rm663"},
    "Harp": {"analyze: need@rm90 sources=[9] frontier=rm40->rm41"},
    "Beeswax": {"analyze: need@rm44 sources=[24] frontier=rm40->rm41"},
    "Crystal": {"analyze: need@rm52 sources=[38] frontier=rm40->rm41"},
    "Locket": {"analyze: need@rm57 sources=[42] frontier=rm42->rm43"},
    "Iron_Bar": {"analyze: need@rm54 sources=[44] frontier=rm44->rm113|rm45->rm113|"
                 "rm46->rm113|rm46->rm661|rm660->rm663"},
    # ONE row now, and it is the catch: carry the fish up the castle stairs or the cat wins.
    # ✅ RE-PINNED 2026-08-16 -- the second row, the rm683 carry-in toll, is GONE with the FP it
    # belonged to (see the promoted red below). It was pinned because it was emitted, not because
    # it was right. [[oracle-must-pin-the-mechanism]]
    "Cat_Fish": {
        "analyze: need@rm57 sources=[51] frontier=rm54->rm55|rm54->rm59|rm54->rm67",
    },
    "Rope": {"fatal_uses: {'room': 30, 'machine': 'ropeOnBranch', 'states': [0]}"},
    # The three phase-1 catches, pinned to their fold rows. The rm86 row is ONE fact stated
    # for each pool member: the demand is the disjunction (`demand_group`), the context is
    # the kidnap arrival (prev == 85).
    "Leg_of_Lamb": {
        # RE-PINNED 2026-08-15 with the USER'S OK: both fold rows are unchanged and this row is
        # ADDITIVE -- the lamb's source is the inn cupboard (rm28, in town) and the nest that
        # demands it is rm42, so the roc carries you across the boundary between them.
        "analyze: need@rm42 sources=[28] frontier=rm40->rm41",
        "ownedby_death_folds: {'dest': 34, 'need_room': 42, 'machine': 'hatch', 'state': 6, "
        "'pattern': 'state-fork', 'demand_group': [(19, 34)], 'context': {}}",
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
    },
    "Fish": {
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
    },
    "Pie": {
        # RE-PINNED 2026-08-15 with the USER'S OK: the fold row is unchanged and this one is
        # ADDITIVE -- Main's `proc0_21` inventory dispatch EATS the pie (`put: 2 1`), a room-0
        # scope the model widens to wherever you are standing, and the yeti at rm36 still needs
        # it. Same fact as the confirmed pie ruling, seen from the sink side.
        "dangerous_sinks: {'room': 0, 'script': 0, 'dest': 1, 'at_room': 38, "
        "'still_needed_at': [36]}",
        "ownedby_death_folds: {'dest': 36, 'need_room': 35, 'machine': 'killEgo', "
        "'state': None, 'pattern': 'entry-fold', 'demand_group': [(2, 36)], "
        "'context': {12: 36}}",
    },
    "Hammer": {
        "register_strandings: reg12=85->[86]",
    },
    # The partial catches are pinned too -- if the disjunction-aware cure changes their shape,
    # that is a mechanism change to confirm, not silent churn. Since phase 1 they also carry
    # their rm86 fold rows.
    "Shoe": {
        "dangerous_sinks: {'room': 12, 'script': 12, 'dest': 12, 'at_room': 12, "
        "'still_needed_at': [6]}",
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
    },
    "Stick": {
        "dangerous_sinks: {'room': 12, 'script': 12, 'dest': 12, 'at_room': 12, "
        "'still_needed_at': [6]}",
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
    },
}

DETECTORS = ("analyze", "joint_strandings", "resource_exhaustion", "dangerous_sinks",
             "register_flip_strandings", "toll_strandings", "fatal_uses", "register_strandings",
             "ownedby_death_folds")

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

    # ✅ PROMOTED 2026-08-14 (phase 2) -- "the inn-cellar corral demands the Hammer" is GREEN:
    # the fetch walks ban the item they fetch, so the (rm86, prev==85) trap's own(22)-priced
    # exit no longer vouches for the Hammer's obtainability. The row's SHAPE is the assertion:
    # the flip is the kidnap edge and the need site is the cellar itself.
    hammer_rows = [r for (n, d, r) in raw_rows
                   if n == "Hammer" and d == "register_strandings"]
    check("the kidnap corral demands the Hammer (reg12=85 seals rm86)",
          any(r.get("register") == 12 and r.get("value") == 85
              and r.get("flip_rooms") == [86] and r.get("still_needed_at") == [86]
              for r in hammer_rows),
          f"rows={hammer_rows!r} -- expected the prev==85 flip at rm86 demanding the Hammer "
          f"at the cellar door. docs/KQ5-ORACLE.md §2.")

    # THE ROW SURVIVES BECAUSE THE CELLAR HAS TWO ARRIVALS, and that is the whole discipline
    # separating it from the rows the same build DELETED on KQ6. `register_strandings` compares
    # the post-flip player with the PRE-flip one, and for a positional register the pre-flip
    # state is a different arrival rather than an earlier moment -- so it only means something
    # when that other arrival is a state a hammer-less player can actually occupy. rm86 is
    # enterable normally (prev == 28) as well as by the kidnap, so such a player exists and can
    # still walk out to the Hammer's source; KQ6's rm155 is enterable only from rm340 or by
    # coming back OUT of the sealed Realm, so no mirror-less player is ever there and those
    # rows are arrivals, owned by the toll detector. Pinned here because it is the clause's
    # only live instance in the corpus.
    prev_states = s._pstates.get(12) or set()
    check("the cellar's pre-flip arrival exists and is not the kidnap (prev==28)",
          (86, 28) in prev_states,
          f"states at rm86: {sorted(v for (r, v) in prev_states if r == 86)} -- the row above "
          f"rests on a normal arrival existing beside the kidnap one.")

    # ...AND THE DEMAND LANDS ON THE KIDNAP CROSSING ONLY (guards.register_flip_frontier's
    # `land` clause). Every edge out of rm85 writes `prev := 85` -- that is what leaving rm85
    # means -- so without the clause the Hammer's demand would ride each of them, walling the
    # ordinary ways out of the room. Only the arrival the walk measured as sealing carries it.
    import guards as G
    front = {e: sorted(rec["items"]) for e, rec in G.register_flip_frontier(s).items()
             if 22 in rec["items"]}
    check("the Hammer demand rides only the crossing that strands it",
          all(b == 86 for (_a, b) in front),
          f"frontier edges carrying the Hammer: {front} -- an edge that writes prev==85 while "
          f"arriving somewhere other than the cellar enters no seal.")

    def _rooms_mentioned(r):
        out = {x for x in (r.get("still_needed_at") or ()) if isinstance(x, int)}
        if isinstance(r.get("need_room"), int):
            out.add(r["need_room"])
        return out

    # ✅ PROMOTED 2026-08-14 (phase 1) -- "the cat-scene window reaches the kidnap read",
    # "the roc's-nest lamb fold is caught" and "the eagle's pie swallow strands the yeti's
    # counter-item" are GREEN: `ownedby_death_folds` states the demand at each fold site and
    # the mechanism pins above freeze the rows. The rm86 rows must keep their full pool
    # disjunction and the kidnap context -- that is the fact patch B consumes.
    window_rows = [r for (n, _d, r) in raw_rows if n in POOL and 86 in _rooms_mentioned(r)]
    check("the cat-scene bank is demanded at the kidnap read (all four pool items, prev==85)",
          {n for (n, _d, r) in raw_rows if n in POOL and 86 in _rooms_mentioned(r)} == POOL
          and all(r.get("context") == {12: 85} for r in window_rows
                  if r.get("machine") == "yourStuck"),
          "the rm86 fold rows lost a pool member or their kidnap context -- "
          "docs/KQ5-ORACLE.md §1.")

    needle_rows = [n for (n, _d, _r) in raw_rows if n == "Golden_Needle"]
    check("🔴 KNOWN GAP (KQ5): the fortune teller's needle substitution is caught",
          bool(needle_rows),
          "rm13 accepts Gold_Coin(11) OR Golden_Needle(3) in the amulet slot (`put: 3 13`); "
          "paying with the needle starves the tailor->cloak chain. Exchange-slot class -- "
          "docs/KQ5-ORACLE.md §6.")

    # --- the phase-3 halves, declared red the day phase 1 landed: the fold rows above state
    # the DEMAND; that each demand's producers sit inside a one-shot window is not yet a row.
    fish_bees = [n for (n, _d, r) in raw_rows if n == "Fish" and 11 in _rooms_mentioned(r)]
    check("🔴 KNOWN GAP (KQ5): the bees' flag-36 window closure is caught", bool(fish_bees),
          "flag 36's only writer is bearScript (exists only while `has: 5`); the hive arms "
          "deathByBees under not-flag36 -- no row ties the Fish to rm11's honeycomb chain. "
          "Phase 3 (window closure: a demanded value whose every producer is guarded on a "
          "flag the producers' own trigger sets). docs/KQ5-ORACLE.md §1a.")

    window_closed = [r for (n, _d, r) in raw_rows if n in POOL
                     and r.get("pattern") == "window-closure"]
    check("🔴 KNOWN GAP (KQ5): the cat window's closure on arming is caught",
          bool(window_closed),
          "flag 83 is set the moment the chase STARTS (rm006::doit), so every producer of "
          "`owner == 6` is behind a window that closes on arming, win or lose -- the rm86 "
          "demand rows exist (green above) but no row states the window. Phase 3; also the "
          "site patch A holds. docs/KQ5-ORACLE.md §1.")

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

    # ✅ PROMOTED 2026-08-16 (was 🔴 KNOWN FP), and it took test_toll.py's two KQ5 assertions
    # green with it, exactly as the red predicted. rm683 is `cdCassimaToon`, a CD cutscene that
    # tests NO item at all; the own(37)/own(24) demands were attributed there because `castle.sc`
    # is the region live in all 16 castle rooms and `theCat` had no presence condition to narrow
    # it -- the cat's bagged arm is `(and (== global332 7) (== global338 gCurRoom))`, and one
    # disjunct nothing could read freed the whole OR.
    #
    # The cure is `extract.room_valued_globals`: a global whose every write is a literal or the
    # current-room global holds a ROOM, so `(== gX gCurRoom)` lowers to the disjunction over the
    # rooms it can hold. Deriving those rooms needs a LEAST fixpoint based at false -- the machine
    # that writes global338 is armed from the cat's own handler, so a greatest fixpoint keeps
    # rm683 alive by self-reference. Measured g338 -> {57,58,59,60,61,63,64}.
    #
    # The assertion stays live: it is the shape of the FP, and a shape change should be loud.
    toon_carryins = [(n, r) for (n, d, r) in raw_rows
                     if d == "toll_strandings" and r.get("toll_edge") == [57, 683]]
    check("no carry-in demand rides the rm57->rm683 cutscene",
          not toon_carryins,
          "REGRESSION: a requirement is being broadcast into a cutscene room again. rm683 has no "
          "item test in it; the demand can only have come from castle.sc, the region live in "
          f"every castle room. Rows: {toon_carryins}. Check that `room_valued_globals` still "
          "derives global338, and that theCat's presence condition still reads as seven rooms.")

    # ✅ PROMOTED 2026-08-15 (was 🔴 KNOWN FP). The Wand is unstrandable, and the reason is NOT
    # the one this test used to give: rm066's machine tray IS a real spend -- `putCWandScript`
    # (rm066:132) lays Crispin's wand down, the owner becomes the room, and it stays there while
    # you walk the castle. What makes it safe is that the drop and the re-get are the SAME room
    # (`cWand` verb 3 -> `getCWandScript`, rm066:903/260, re-armed from the owner check on every
    # entry), and that every wandless path into rm124 is a DEATH rather than a walking-dead state
    # (`battle.sc:84` sets flag 55, `mordOneScript` state 13 runs `proc0_26`). USER RE-AFFIRMED
    # the FP ruling against that mechanism on 2026-08-15; the 15-second grab window in rm066 is
    # preventable on its own screen and is deliberately NOT promoted. docs/KQ5-ORACLE.md §10.
    #
    # ⛔ The two `entry_musts` cures of 2026-08-15 stay dead (both make KQ6's rm230
    # `removeHoleScr` a second source and break an enforced KQ6 fact). What landed instead is
    # `missability._unrefusable_grants`: rm001.sc:78 hands the wand over in `init` under nothing
    # but `not (has: 28)`, so `_reach_without(28)` stops there. Measured corpus-wide -- LSL2,
    # KQ4, KQ6 and LB2 byte-identical on the FULL snapshot surface, placements included.
    wand_rows = [r for (n, d, r) in raw_rows if n == "Wand"]
    check("no detector demands the Wand (unrefusable rm1 grant)", not wand_rows,
          "REGRESSION: the Wand is back. It is granted at rm099/rm001/cdIntro10 and the one "
          "site that takes it (rm066's machine tray) hands it back in the same room, so no "
          "crossing can strand it -- USER-RULED 2026-08-14 and re-affirmed 2026-08-15. Rows: "
          f"{wand_rows}. Check `_unrefusable_grants` still sees rm1's init grant.")

    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    ok = run()
    sys.exit(0 if ok else 1)
