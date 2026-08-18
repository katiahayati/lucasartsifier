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
The MARKET landed 2026-08-17b (`missability.market_squeezes`, §6a/§6b/§6c: the squeeze, the
Heart and the lamb promoted together -- one matching question, with scarcity read
consumer-relatively so the eagle past the roc counts every lamb as the last one). The known
acquisition looseness remains -- the cupboard, the Coin and the Marionette all read restockable
because their pickups' owner-gating is not modeled -- but it is measured to move NO verdict:
every consumer it could waive is either town-side (where re-fetching is real) or constrained
through a token that is scarce anyway. Column F -- false positives we emit -- is EMPTY as of 2026-08-17:
the Wand's was cured 2026-08-15, the witch amulet's verdict was corrected 2026-08-16b, and the
tambourine's went with the snake gate below. Several verdicts are open on their own terms (the peas
consumable waits on the item-property store; the locket window, the mountains' cold death and
the Hammer's crystal site are unverified against the source). The checks below passing means
the catches we HAVE are still there and still caught for the stated mechanism -- nothing more.

Two builds landed 2026-08-14. Phase 1, `ownedby_death_folds` (an arrival forks on an owner
value and the losing arm is a death the player cannot dodge), retired the kidnap-read, lamb-fold
and pie reds. Phase 2, item-banned fetch walks in `register_strandings`, retired the Hammer red.
Their rows are mechanism-pinned below. Phase 3 landed 2026-08-16b as `window_closures` (with
`extract.feature_adders`), retiring the cat-window red. The bees' half of phase 3 turned out NOT
to be a window at all -- flag 36's writer needs the fish IN HAND, so an item spent elsewhere shuts
it, which is a SINK -- and closed 2026-08-17 as `dangerous_sinks Fish@rm6 -> [11]` (§16).

⭐ THE POSITIONAL GAP IS OPEN ON KQ5 (2026-08-17). `missability._apply_hazard_gates` reads a
`doit` branch that bounds the ego's DISTANCE to a stationary object and arms a death nobody
survives, and bars the screen exits that object's radius seals -- proven over the room's own
obstacle polygons, which KQ5 spells as named `Polygon` instances (`polygons.instance_polygons`,
84 sites in 67 rooms that used to read as open floor). One gate in the corpus: rm2's snake.

⭐ THE WITCH AMULET IS NOT A SOFTLOCK (USER-RULED 2026-08-16b) -- you need it, but rm19 is one
screen into the forest and you can walk back to rm13 for another. Its red demanded the wrong row
and is rebuilt as two green pins: the DEMAND reaches all seven forest rooms, and no detector
claims a stranding.

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
    #     prev == 85. That row is the catch for ALL FOUR, and for Shoe and Stick it is the ONLY
    #     one -- see the 2026-08-16b ruling below;
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
    # ✅ PROMOTED 2026-08-16b, USER-RULED, out of the old column B. Shoe and Stick are the SAFE
    # ammunition -- one source each (`rm015` bootInSand, `rm011` getStick), no other consumer --
    # and they are caught by the rm86 pool demand above and by nothing else, which is now their
    # whole pinned mechanism.
    #
    # ⛔ THE ROWS THAT USED TO SIT BESIDE IT WERE FALSE POSITIVES, and this is the ruling that
    # says so. `dangerous_sinks` claimed "spending the Shoe at the dog leaves it needed at the
    # cat". USER 2026-08-16b: *"you can't skip the bear... use your shoe on the dog, that's okay,
    # finish the bear, get the stick, and use that on the cat."* Source agrees and says why the
    # pool cannot be starved at all: `rm006.sc:112` inits the cat and the rat only under
    # `(or (has: 8) (has: 16))`, and flag 83 -- the window -- is set by `rm006::doit` only once
    # the rat is on screen. Walk into rm6 empty-handed and the scene does not start, so nothing
    # is spent and nothing closes; come back with the Stick and it is still waiting. The
    # encounter IS the hold we would otherwise have to patch in. The rows went with commit
    # f623aa2 (the dog's throw arms `throwStick`, so it was never a "consumption that
    # accomplishes nothing"), and their going is a CURE, not a coverage loss.
    "Shoe",
    "Stick",
    # ✅ PROMOTED 2026-08-17b, USER-RULED across two sessions, caught by `market_squeezes`. The
    # town is a five-token MARKET with zero slack -- gypsy {3,11} -> Amulet, tailor {3,9,11} ->
    # Cloak, toy maker (+12) -> Sled, baker (+4) -> Pie, princess {9 alone} -> Harp -- and the
    # USER confirmed every product is required (*"the cloak is needed"*, 2026-08-17b; the harp,
    # sled and pie were already enumerated). So a payment is fatal exactly when the residual
    # market has no perfect matching:
    #   * the SQUEEZE (USER 2026-08-17: "you CAN ... waste your gold on the toy maker and the
    #     cloak"): the needle or the gold coin at the toy maker or the baker;
    #   * the HEART (USER 2026-08-17: "you need the heart for something else, so that would be
    #     a sink too"): the heart at ANY shop starves the princess, the Harp's sole source.
    # ⚠️ With the Cloak required, the needle/coin rows are ONE-payment dead ends -- the old §6
    # "any single payment survives" claim rested on the heart covering the tailor, which the
    # heart ruling itself removed. The USER-PLAYED pair (needle->gypsy, coin->tailor) emits
    # nothing, as it must.
    "Golden_Needle",
    "Heart",
}

# C -- OPEN RULING: the peas are a counted consumable spelled as the ITEM'S OWN `cel` property
# (castle.sc increments `((global9 at: 24) cel:)` per throw) -- the item-property store, which
# does not exist yet. The 13 exhaustion rows are its coarse shadow; tolerated, not demanded.
ALLOWED_OPEN = {"Bag_of_Peas"}

# F -- FALSE POSITIVES WE EMIT. ✅ EMPTY SINCE 2026-08-16b: the Tambourine was the last one and
# it is CURED. Dink inits only while `own(34)` holds, so hugScript's unsurvivable arming carried
# the tambourine as the monster's EXISTENCE CONDITION rather than as anything the player did --
# and giving it (`giveTamboScript`, `put: 34`, drops the Hairpin) is the escape from that very
# machine. `fatal_uses` now blames `entry_site` (what the arming site required) instead of the
# entry guard the strengthening passes had grown; KQ6's skull, whose own() comes from
# `theGears doVerb 51` at the site, is untouched. docs/KQ5-ORACLE.md §14.
#
# ✅ THE WAND LEFT THIS SET 2026-08-15, CURED -- see the green pin below and docs/KQ5-ORACLE.md
# §10. It had been emitted since before the oracle existed. The cure is NOT the never-strandable
# class this file used to propose (a class shaped to protect a known answer, and refuted by the
# source: rm66's machine tray really does take the wand, it just hands it straight back), but
# `missability._unrefusable_grants` -- rm1's `init` gives Crispin's wand to anyone who does not
# have it, so no state past rm1 lacks it, and `_reach_without` no longer walks through it.
FP_EMITTED = set()

ALLOWED = EXPECTED_CAUGHT | ALLOWED_OPEN | FP_EMITTED     # column B is empty since 2026-08-16b

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
        # ✅ THE MARKET, added 2026-08-17b: spend the gold coin at the toy maker or the baker
        # and the gypsy-tailor-princess triangle {3, 9, 11} is down to two tokens for three
        # required purchases. The toll row above is what makes the coin single-copy at all --
        # `rm018::init` would restock it, but the temple ate the Staff.
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 5, 'script': 204, "
        "'inst': 'getSled', 'pays': ['getSled'], 'starves': [5, 9, 13], "
        "'starved_accepts': [3, 9, 11]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 206, 'script': 206, "
        "'inst': 'getPie', 'pays': ['getPie'], 'starves': [5, 9, 13], "
        "'starved_accepts': [3, 9, 11]}",
    },
    # ✅ ADDED 2026-08-17b with the market. The needle's two rows mirror the gold coin's --
    # either token at the toy maker or the baker starves the triangle -- and they exist at all
    # only because the ants' repayment is owner-gated (`searchHay` state 5 demands the needle
    # still in the hay), so a spent needle is gone for good.
    "Golden_Needle": {
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 5, 'script': 204, "
        "'inst': 'getSled', 'pays': ['getSled'], 'starves': [5, 9, 13], "
        "'starved_accepts': [3, 9, 11]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 206, 'script': 206, "
        "'inst': 'getPie', 'pays': ['getPie'], 'starves': [5, 9, 13], "
        "'starved_accepts': [3, 9, 11]}",
    },
    # ✅ ADDED 2026-08-17b with the market. The heart at ANY shop starves the princess -- her
    # slot takes item 9 and nothing else (`rm009.sc:936/990`), she is the Harp's sole source,
    # and the Harp is required at rm90/92/682 past the roc. Derived by reading (c2): the Harp's
    # one acquisition guard demands owner(Heart) in {9, 21} -- paid to her, or still at the
    # witch's house -- so a shop's counter is a value it can never come back from.
    "Heart": {
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 5, 'script': 203, "
        "'inst': 'soldCloak', 'pays': ['soldCloak'], 'starves': [9], 'starved_accepts': [9]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 5, 'script': 204, "
        "'inst': 'getSled', 'pays': ['getSled'], 'starves': [9], 'starved_accepts': [9]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 206, 'script': 206, "
        "'inst': 'getPie', 'pays': ['getPie'], 'starves': [9], 'starved_accepts': [9]}",
    },
    "Fishhook": {"analyze: need@rm67 sources=[90] frontier=rm44->rm113|rm45->rm113|"
                 "rm46->rm113|rm46->rm661|rm660->rm663"},
    "Harp": {"analyze: need@rm90 sources=[9] frontier=rm40->rm41"},
    "Beeswax": {"analyze: need@rm44 sources=[24] frontier=rm40->rm41"},
    "Crystal": {"analyze: need@rm52 sources=[38] frontier=rm40->rm41"},
    "Locket": {
        "analyze: need@rm57 sources=[42] frontier=rm42->rm43",
        # ✅ THE DUNGEON-HOLE FOLD, USER-CONFIRMED IN GAME 2026-08-18b ("if you don't give the
        # locket... cassima doesn't come and you die") -- scorecard row 11's read half. The
        # henchman capture drops you in rm67; `henchCaught` st8 forks on the GIVEN locket
        # (owner(25)==57) -- moveStone (Cassima's rescue) vs dieScumScript (30-60s pure timer
        # into proc0_26). The arms commit by ARMING SIBLINGS, so the delegated-fork matcher
        # reads the fork out of handoff[(henchCaught, 8)]: complementary-guarded armings, one
        # unavoidable. The context is the fold's own residue conjunct: flag 96 (register 498)
        # CLEAR -- with it set, the capture kills regardless of the locket (the second-capture
        # question, verdict pending).
        "ownedby_death_folds: {'dest': 57, 'need_room': 67, 'machine': 'henchCaught', "
        "'state': 8, 'pattern': 'state-fork', 'demand_group': [(25, 57)], "
        "'context': {498: 0}}",
    },
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
        # ✅ THE WINDOW, added 2026-08-16b by `window_closures`: the fold row above says the
        # bank is DEMANDED at the kidnap; this one says the only way to fill it shuts by
        # itself. Two closers, both real -- flag 83 (reg 485) goes up as the chase ARMS, and
        # rm6's `local0` (reg 565) when you LOSE the race and the throws answer "too late".
        "window_closures: {'pattern': 'window-closure', 'dest': 6, 'need_room': 86, "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'producer_rooms': [6], "
        "'closes_on': [(485, 1), (565, 1)], 'flip_rooms': [6]}",
        # ✅ THE MARKET, added 2026-08-17b with consumer-relative scarcity: any spend of the
        # lamb away from the eagle starves the rm42 fold, whose surviving arm demands
        # owner(19) == 34 and which sits past the roc where no lamb can be re-fetched
        # (rm42 is outside `reobtainable_rooms(19)` -- the same fact the analyze row above
        # rests on). Three spends exist: Main's EAT verb (the second bite destroys it), the
        # cat (put: 19 6 -- it also BANKS the kidnap rescue, which is why `pays` credits the
        # rm86 bank while the row still condemns the throw), and the dog (put: 19 12).
        # The cat/dog rows are oracle §1a's "throw the lamb at the cat or dog -> rm42 death",
        # a TRUE softlock declared there since 2026-08-14 and caught here for the first time.
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 0, 'script': 0, "
        "'inst': None, 'pays': [], 'starves': [42], 'starved_accepts': [19]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 6, 'script': 6, "
        "'inst': None, 'pays': ['6', '6'], 'starves': [42], 'starved_accepts': [19]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 12, 'script': 12, "
        "'inst': None, 'pays': [], 'starves': [42], 'starved_accepts': [19]}",
    },
    "Fish": {
        # ✅ THE BEES, added 2026-08-17 (§16). The Fish is the one pool member whose OTHER
        # consumer takes nothing else -- the bear at rm11 exists only while `has: 5` and its
        # `bearScript` is flag 36's sole writer, so `put: 5 6` at the cat makes every hive
        # approach `deathByBees` and the honeycomb -> beeswax -> boat chain unreachable. That
        # this row exists while Shoe@rm6 and Stick@rm6 do NOT is the whole content of the
        # consumer-scoped rescue; see the pins on those two items.
        "dangerous_sinks: {'room': 6, 'script': 6, 'dest': 6, 'at_room': 6, "
        "'still_needed_at': [11]}",
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
        # ✅ THE WINDOW, added 2026-08-16b by `window_closures`: the fold row above says the
        # bank is DEMANDED at the kidnap; this one says the only way to fill it shuts by
        # itself. Two closers, both real -- flag 83 (reg 485) goes up as the chase ARMS, and
        # rm6's `local0` (reg 565) when you LOSE the race and the throws answer "too late".
        "window_closures: {'pattern': 'window-closure', 'dest': 6, 'need_room': 86, "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'producer_rooms': [6], "
        "'closes_on': [(485, 1), (565, 1)], 'flip_rooms': [6]}",
    },
    "Pie": {
        # RE-PINNED 2026-08-15 with the USER'S OK: the fold row is unchanged and this one is
        # ADDITIVE -- Main's `proc0_21` inventory dispatch EATS the pie (`put: 2 1`), a room-0
        # scope the model widens to wherever you are standing, and the yeti at rm36 still needs
        # it. Same fact as the confirmed pie ruling, seen from the sink side.
        #
        # ⚠️ RE-PINNED AGAIN 2026-08-17, `at_room` 38 -> 1, by the consumer-scoped rescue (§16),
        # and the move is a STRENGTHENING. The old row started at rm38 because the eagle's group
        # {Pie, Leg_of_Lamb} excused every earlier room -- "eat the pie, the eagle still takes the
        # lamb" -- which is true of the EAGLE and says nothing about the YETI, whose counter-item
        # is the pie and nothing else. Read at the consumer, rm34's rescue applies to rm34 alone
        # and rm36's need survives from the first room you can eat it in.
        "dangerous_sinks: {'room': 0, 'script': 0, 'dest': 1, 'at_room': 1, "
        "'still_needed_at': [36]}",
        # ...and the same fact at the site the walkthroughs warn about: feeding the pie to the
        # eagle (`put: 2 34`) is a real trade, so `pure_sinks` never saw it and only the owner
        # graph can tell that rm34 does not give it back. Scorecard row 14, caught a second way --
        # the rm35 `killEgo` entry fold below catches the consequence, this catches the act.
        "dangerous_sinks: {'room': 34, 'script': 34, 'dest': 34, 'at_room': 34, "
        "'still_needed_at': [36]}",
        "ownedby_death_folds: {'dest': 36, 'need_room': 35, 'machine': 'killEgo', "
        "'state': None, 'pattern': 'entry-fold', 'demand_group': [(2, 36)], "
        "'context': {12: 36}}",
        # ✅ THE MARKET, added 2026-08-17b: the rm35 fold IS a consumer (the yeti must be
        # thrown the pie), so eating the pie or feeding it to the eagle starves him -- the
        # same two facts the dangerous_sinks rows above state, derived from the matching side.
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 0, 'script': 0, "
        "'inst': None, 'pays': [], 'starves': [35, 36], 'starved_accepts': [2]}",
        "market_squeezes: {'pattern': 'market-squeeze', 'at_room': 34, 'script': 34, "
        "'inst': None, 'pays': [], 'starves': [35, 36], 'starved_accepts': [2]}",
    },
    "Hammer": {
        "register_strandings: reg12=85->[86]",
    },
    # ✅ RE-PINNED 2026-08-16b with the USER'S RULING: ONE row each, the rm86 pool demand. The
    # `dangerous_sinks {'room': 12, ..., 'still_needed_at': [6]}` row that used to sit beside it
    # was a FALSE POSITIVE and is pinned OUT -- see the EXPECTED_CAUGHT note above. A single row
    # here is the assertion that it stays out.
    "Shoe": {
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
        # ✅ THE WINDOW, added 2026-08-16b by `window_closures`: the fold row above says the
        # bank is DEMANDED at the kidnap; this one says the only way to fill it shuts by
        # itself. Two closers, both real -- flag 83 (reg 485) goes up as the chase ARMS, and
        # rm6's `local0` (reg 565) when you LOSE the race and the throws answer "too late".
        "window_closures: {'pattern': 'window-closure', 'dest': 6, 'need_room': 86, "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'producer_rooms': [6], "
        "'closes_on': [(485, 1), (565, 1)], 'flip_rooms': [6]}",
    },
    "Stick": {
        "ownedby_death_folds: {'dest': 6, 'need_room': 86, 'machine': 'yourStuck', "
        "'state': None, 'pattern': 'entry-fold', "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'context': {12: 85}}",
        # ✅ THE WINDOW, added 2026-08-16b by `window_closures`: the fold row above says the
        # bank is DEMANDED at the kidnap; this one says the only way to fill it shuts by
        # itself. Two closers, both real -- flag 83 (reg 485) goes up as the chase ARMS, and
        # rm6's `local0` (reg 565) when you LOSE the race and the throws answer "too late".
        "window_closures: {'pattern': 'window-closure', 'dest': 6, 'need_room': 86, "
        "'demand_group': [(5, 6), (8, 6), (16, 6), (19, 6)], 'producer_rooms': [6], "
        "'closes_on': [(485, 1), (565, 1)], 'flip_rooms': [6]}",
    },
}

DETECTORS = ("analyze", "joint_strandings", "resource_exhaustion", "dangerous_sinks",
             "register_flip_strandings", "toll_strandings", "fatal_uses", "register_strandings",
             "ownedby_death_folds", "window_closures", "market_squeezes")

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

    # --- THE SNAKE IS THE TOWN GATE, and it is a POSITIONAL death (docs/KQ5-ORACLE.md §15) ----
    # ✅ PROMOTED 2026-08-17. This was the last entry in column F: `analyze` claimed the
    # Tambourine could be left behind at the roc (`need@rm55 sources=[13] frontier=rm40->rm41`),
    # and the USER refuted it -- "you can't go outside of the town unless you use the tambourine
    # on the snake." All four of rm2's exits read FREE because the snake blocks by KILLING YOU
    # AT A DISTANCE rather than by guarding an edge. `_apply_hazard_gates` closes that, and the
    # three pins below are the three separate things that have to be true, so a regression says
    # WHICH one broke rather than only that the FP came back.
    gates = [g for g in getattr(s, "hazard_gates", ())]
    check("the snake gates the road out of town (rm2 east -> rm29, on flag 47)",
          gates == [{"room": 2, "edge": "east", "dst": 29, "hazard": "snake", "at": (298, 64),
                     "radius": 30, "machine": ["strike"], "req": {449: [1]}}],
          f"hazard_gates={gates!r} -- expected exactly the snake's disc sealing rm2's east "
          f"handoff, demanding flag 47 (register 449). More rows than this is a new claim to "
          f"check against the game; fewer is the FP coming back.")

    # ...AND THE DEMAND IS THE TAMBOURINE, which is the user's ruling in the model's own terms.
    # The gate names a FLAG, not an item; that it reduces to the tambourine is `_reg_cost`'s
    # answer, derived from the only write of flag 47 (`snake handleEvent 4`, item 34, and
    # crucially NO `put:` -- charming it does not consume it, which is why everyone past the
    # gate still has one).
    check("leaving town eastward costs the Tambourine",
          s._reg_cost(449, {1}) == frozenset({34}),
          f"_reg_cost(449,{{1}})={s._reg_cost(449, {1})!r} -- expected the tambourine alone. "
          f"If this widened, the flag has acquired a second writer the oracle has not seen.")

    # ...AND THE GEOMETRY IS READ AT ALL. KQ5 states its obstacle layouts as named `Polygon`
    # INSTANCES filled from local arrays, a spelling `polygons.py` could not read until this
    # build -- 84 `addObstacle:` sites in 67 rooms, all invisible, so every KQ5 room looked
    # like open floor. Pinned because the gate above is silently unprovable without it.
    import polygons as PG
    _polys = [p for _pc, ps in PG.room_obstacles(s.em.ir, s.em.ir.scripts[2]) for p in ps]
    check("rm2's obstacle layout is read (the Polygon-instance spelling)",
          len(_polys) == 5 and all(t == 2 and len(pts) >= 4 for (t, pts) in _polys),
          f"rm2 polygons={_polys!r} -- expected the five BARRED polygons rm002 hands the "
          f"pathfinder. With none of them the east handoff is reachable around the snake.")

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
    # ⭐ NON-VACUOUS since 2026-08-18: this check passed for months on an EMPTY front -- a
    # prev-room register never appears in an edge's own req, so `flip_edges`' req test could
    # not see the structural exclusion (standing in rm85, prev != 85 by construction) and the
    # Hammer's demand reached no edge at all (`reg12=85 [REFUSED] ... UNENFORCED`). The prev
    # branch in flip_edges is the cure; this pin now demands the crossing be PRESENT.
    check("the Hammer demand rides exactly the kidnap crossing rm85->rm86",
          front == {(85, 86): [22]},
          f"frontier edges carrying the Hammer: {front} -- an edge that writes prev==85 while "
          f"arriving somewhere other than the cellar enters no seal, and an EMPTY front means "
          f"the demand is enforced nowhere (the pre-2026-08-18 state).")

    # ✅ PATCH B, added 2026-08-18 (`guards.fold_carryins` + the prev branch in
    # `register_flip_frontier.flip_edges`). The kidnap is MANDATORY (the Rope is sourced inside
    # rm86), so no gate may live in the cellar -- but the entry-fold's context {12: 85} names
    # the one crossing that arms the losing fork, and BOTH demands ride it as ONE guard: the
    # Hammer (the flip frontier's item) and the banked throwable (the fold's owner group, in
    # rm086's own spelling). A-BEFORE-B is derived, not remembered: the bank's producers sit
    # behind the window flag 83 closes, so the carry-in requires a PLACEABLE window remedy for
    # the same group and refuses without one (test: break the window remedy and this spec must
    # flip to refused, not silently wall the kidnap).
    all_specs = G.guard_specs(s)
    kidnap_spec = [sp for sp in all_specs if sp["site"] == "edge"
                   and sp.get("from_room") == 85 and sp.get("to_room") == 86]
    want_cond = ("(and (gEgo has: 22) (or (== ((gInv at: 5) owner:) 6) "
                 "(== ((gInv at: 8) owner:) 6) (== ((gInv at: 16) owner:) 6) "
                 "(== ((gInv at: 19) owner:) 6)))")
    check("the kidnap crossing demands Hammer AND a banked throwable in one guard",
          len(kidnap_spec) == 1 and kidnap_spec[0]["condition"] == want_cond
          and not kidnap_spec[0]["refused"],
          f"specs={kidnap_spec!r} -- expected exactly one placeable rm85->rm86 edge spec "
          f"conjoining (has 22) with the rm086-spelled bank disjunction.")

    # ...and the SAME derivation's second catch: rm35's killEgo entry-fold (context {12: 36},
    # the scripted kill when you flee the yeti unfed) puts `owner(Pie) == 36` on rm36->rm35.
    # The feed site is rm36 itself, so the demand is satisfiable at the refusal moment; a
    # pie-less player was doomed in rm36 either way, so the guard defers and never walls.
    yeti_spec = [sp for sp in all_specs if sp["site"] == "edge"
                 and sp.get("from_room") == 36 and sp.get("to_room") == 35]
    check("the yeti fold's demand rides rm36->rm35 (feed the yeti before crossing)",
          len(yeti_spec) == 1 and yeti_spec[0]["condition"] == "(== ((gInv at: 2) owner:) 36)"
          and not yeti_spec[0]["refused"],
          f"specs={yeti_spec!r} -- the killEgo fold names prev==36, so its demand belongs on "
          f"that crossing and nowhere else.")

    # ✅ THE TEMPLE'S GUARD, added 2026-08-18 (USER: \"we absolutely 100% need to do the temple
    # pocket\"). The toll rows (rm214->rm18, Staff spent on the door) had been detected since
    # phase 1 with NO guard emitted: `_carryout_frontier` refused every pocket whose exits name
    # no register (\"no seal to judge in\"), which is the REGISTER-toll spelling. An ITEM toll is
    # its own seal -- the spent Staff is exactly the toll-edge deletion `csucc` already
    # performs -- so the committed walk runs in the prev dimension and the teacup's exit half
    # finally ships for KQ5: leave the temple only with the loot the door will never again
    # open onto.
    temple_spec = [sp for sp in all_specs if sp["site"] == "edge"
                   and sp.get("from_room") == 18 and sp.get("to_room") == 214]
    check("the temple pocket's exit demands both treasures (carry-out, item-toll seal)",
          len(temple_spec) == 1
          and temple_spec[0]["condition"] == "(and (gEgo has: 6) (gEgo has: 11))"
          and not temple_spec[0]["refused"],
          f"specs={temple_spec!r} -- expected exactly one placeable rm18->rm214 edge spec "
          f"demanding Brass_Bottle(6) AND Gold_Coin(11); an empty list is the pre-2026-08-18 "
          f"state (detected, unguarded).")

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

    # ✅ REWRITTEN 2026-08-17, USER-RULED -- this red, like the witch amulet's, DEMANDED THE WRONG
    # ROW. It asserted that some detector flags the Golden_Needle, on the tier-3 claim that paying
    # the gypsy with it makes the game unwinnable "because the needle's real consumer is the
    # tailor". The source refutes the reason -- `tailorShop.sc:143-151` takes Golden_Needle(3),
    # Gold_Coin(11) OR Heart(9) -- and the USER refuted the verdict IN THE GAME, in two steps:
    # the gypsy takes the needle, and the tailor then sells the cloak for the gold coin. So a row
    # here would be a FALSE POSITIVE, and emitting nothing is the correct answer.
    #
    # What KQ5 actually has is a FIVE-TOKEN MARKET over four purchases, and the model reads all of
    # it: gypsy{3,11} -> Amulet, tailor{3,9,11} -> Cloak, toyMaker{3,9,11,12} -> Sled,
    # baker{3,4,9,11} -> Pie. Every token is reachable before the amulet is needed (the Gold_Coin's
    # temple, rm18, is a short walk from town via rm14/15 -> rm212/213 -> rm214), so a perfect
    # assignment survives ANY single payment.
    #
    # ⚠️ The hazard that IS in this family needs TWO wrong payments: spend both 3 and 11 away from
    # the gypsy and her slot has nothing left to read, because the Heart is two screens into the
    # forest the amulet opens. That is a Hall deficiency over the market, no single-spend detector
    # can state it, and it is recorded in docs/KQ5-ORACLE.md §6 as an OPEN MECHANISM rather than as
    # a missed catch. The pins below are therefore the two facts that ARE true: the model reads the
    # market as four alternative-sets, and no detector strands a token.
    MARKET = {13: {3, 11}, 206: {3, 4, 9, 11}}
    groups = s.disjunctive_groups()
    at5 = {frozenset(g) for g in groups.get(5, ())}
    check("the shop slots are read as alternatives, not as shopping lists",
          all(frozenset(v) in {frozenset(g) for g in groups.get(r, ())}
              for r, v in MARKET.items())
          and {frozenset({3, 9, 11}), frozenset({3, 9, 11, 12})} <= at5,
          "groups at rm5/rm13/rm206 = %r -- expected the gypsy's {3,11}, the tailor's {3,9,11}, "
          "the toy maker's {3,9,11,12} and the baker's {3,4,9,11}. If one collapsed, either "
          "`_own_required` or the by-state bucketing in `disjunctive_groups` regressed. "
          "docs/KQ5-ORACLE.md §6." % (
              {r: sorted(map(sorted, groups.get(r, ()))) for r in (5, 13, 206)},))
    # ⛔ SCOPED TO THE TWO TOKENS THE USER ACTUALLY RULED ON, and the scoping is load-bearing.
    # An earlier draft of this pin covered all five tokens, which would have frozen a REAL
    # limitation green: the Heart is not interchangeable at all (see the pin below), so a
    # dangerous_sinks row naming it is a CATCH, not a false positive.
    TOKENS = ("Golden_Needle", "Gold_Coin")
    token_sinks = [(n, r.get("at_room")) for (n, d, r) in raw_rows
                   if n in TOKENS and d == "dangerous_sinks"]
    check("neither the needle nor the gold coin is condemned by a SINGLE payment", not token_sinks,
          f"rows={token_sinks} -- USER-RULED 2026-08-17, in the game: the gypsy takes the needle "
          f"AND the tailor then sells the cloak for the gold coin, so no one payment strands you. "
          f"A `dangerous_sinks` row on either is the false positive this red used to demand. "
          f"(The market rows below are a DIFFERENT claim and must not arrive here: they name the "
          f"SITE -- the toy maker or the baker -- while this pin protects the played pair, which "
          f"the market correctly leaves silent.)")

    # ✅ BOTH REDS PROMOTED 2026-08-17b -- the Heart's and the squeeze's -- by ONE detector,
    # `missability.market_squeezes`, because they were never two problems. The USER's framing,
    # verbatim: *"the 3 vendors and the gypsy each accepting some payments that can starve other
    # merchants, when everything you get from the merchants is required."* Every required
    # consumer must be assigned a DISTINCT one-copy token it accepts, so a payment is fatal
    # exactly when the residual market has no perfect matching:
    #   * the HEART at any shop starves the princess (her slot takes item 9 alone,
    #     `rm009.sc:936/990`; she is the Harp's sole source) -- the old Heart red;
    #   * the NEEDLE or the GOLD COIN at the toy maker or the baker leaves {3, 9, 11} two
    #     tokens for three purchases (gypsy, tailor, princess) -- the old squeeze red,
    #     SHARPENED: with the Cloak required (USER 2026-08-17b: "the cloak is needed"), these
    #     are ONE-payment dead ends. The old "needs TWO payments" framing rested on the heart
    #     covering the tailor, which the Heart ruling itself removed.
    # The rows are pinned per-item in MECHANISM_ROWS; the checks here are the two game-facing
    # facts and the silences that keep the detector honest.
    #
    # ⛔ The Heart red's declared mechanism -- "needs `destroying_sinks` to walk
    # `machine_moves`" -- was WRONG, and building it was measured twice and rejected twice
    # (19 FPs on 2026-08-17; 8 KQ6 rows + 2 LB2 rows with shipped placements on a 2026-08-17b
    # re-measure -- and KQ6 is GOLDEN). The market states the same three Heart facts with zero
    # movement on any other game. [[re-derive-a-reds-premise]], applied to a red's cure.
    squeezes = {(n, r["at_room"], r.get("inst")) for (n, d, r) in raw_rows
                if d == "market_squeezes"}
    check("the market squeeze is caught: needle/gold coin at the toy maker or baker",
          {("Golden_Needle", 5, "getSled"), ("Golden_Needle", 206, "getPie"),
           ("Gold_Coin", 5, "getSled"), ("Gold_Coin", 206, "getPie")} <= squeezes,
          f"rows={sorted(squeezes)} -- USER-CONFIRMED 2026-08-17 (\"you CAN ... waste your gold "
          f"on the toy maker and the cloak\") and sharpened 2026-08-17b by the cloak ruling. "
          f"docs/KQ5-ORACLE.md §6a.")
    check("the Heart at any shop is condemned by the princess it starves",
          {("Heart", 5, "soldCloak"), ("Heart", 5, "getSled"),
           ("Heart", 206, "getPie")} <= squeezes,
          f"rows={sorted(squeezes)} -- USER 2026-08-17: *\"you need the heart for something "
          f"else, so that would be a sink too\"*. The princess is the Harp's sole source. "
          f"docs/KQ5-ORACLE.md §6b.")
    # ...and the SILENCES, each one a user ruling the matching must keep honoring: the played
    # pair (needle->gypsy, coin->tailor), the heart to the princess, and the SHOE AND STICK
    # anywhere (the 2026-08-16b ruling: the safe ammunition -- each scene accepts the other's,
    # and the pool's competing consumers never outnumber it). ⛔ Deliberately NOT "no rows at
    # rm6/rm12": the LAMB thrown there is §1a's true softlock and its rows are pinned above --
    # the pool-safety ruling names items, not rooms.
    bad_silence = [t for t in squeezes
                   if t[1] in (13, 9)                       # paying the gypsy or the princess
                   or t[0] in ("Shoe", "Stick", "Fish")     # the pool's rescued members
                   or (t[0], t[2]) in {("Golden_Needle", "soldCloak"),
                                       ("Gold_Coin", "soldCloak")}]
    check("every user-ruled safe play stays silent (gypsy, tailor's 3/11, princess, Shoe/Stick)",
          not bad_silence,
          f"rows={bad_silence} -- a market row landed on a payment the USER ruled or played "
          f"safe: needle->gypsy and coin->tailor are THE winning pair (2026-08-17), the "
          f"heart->princess is the intended move, and the Shoe/Stick keep their rescue "
          f"(2026-08-16b; the Fish's condemnation belongs to dangerous_sinks, not here). "
          f"A row here is the false-positive family the distinct-token matching exists to "
          f"prevent.")

    # ✅ PROMOTED 2026-08-17b, and by REFUTING the red's stated cure rather than building it
    # ([[re-derive-a-reds-premise]], third time this arc). The red prescribed owner-gating the
    # cupboard acquisition; the true fact is cheaper and stronger: SCARCITY IS CONSUMER-
    # RELATIVE. The eagle's fold sits at rm42, past the roc, and `reobtainable_rooms(19)`
    # excludes rm42 -- so to the one consumer that matters, EVERY lamb is the last lamb,
    # restockable cupboard or not. `_market` now waives a consumer's pressure only for a token
    # re-suppliable FROM ITS OWN ROOMS; the cat's bank (rm6/86, in town) keeps its waiver and
    # the pool stays safe. Three rows landed, pinned in MECHANISM_ROWS: the EAT verb and the
    # cat and dog throws -- the latter two being §1a's lamb-at-the-cat TRUE softlock, declared
    # in the oracle since 2026-08-14 and never before caught.
    lamb_market = {(r["at_room"], tuple(r["starves"])) for (n, d, r) in raw_rows
                   if n == "Leg_of_Lamb" and d == "market_squeezes"}
    check("spending the lamb anywhere but the eagle is condemned (eat, cat, dog -> rm42)",
          lamb_market == {(0, (42,)), (6, (42,)), (12, (42,))},
          f"rows={sorted(lamb_market)} -- expected the EAT verb (rm0) and the cat (rm6) and "
          f"dog (rm12) throws, each starving the rm42 fold. USER-ruled 2026-08-17b (\"you need "
          f"both the pie and the lamb\"); the throws are oracle §1a. If the rm6/rm12 rows "
          f"vanished, check that the eagle's consumer still constrains -- its waiver must fail "
          f"because rm42 cannot re-fetch, NOT because the cupboard reads owner-gated.")
    # ...and the lamb TO the eagle stays silent: the spend that establishes owner(19) == 34 is
    # the fold's own satisfaction, recognized by DESTINATION (no machine identity needed).
    check("feeding the lamb to the eagle is not condemned",
          not [r for (n, d, r) in raw_rows if n == "Leg_of_Lamb"
               and d == "market_squeezes" and r["at_room"] == 34],
          "a market row condemns the lamb AT the eagle -- the intended move. The "
          "satisfaction-by-destination read regressed. docs/KQ5-ORACLE.md §6c.")

    # ✅ PROMOTED 2026-08-17 -- "the bees' flag-36 window closure is caught" is GREEN. The Fish is
    # the one throwable whose OTHER consumer accepts nothing else: `rm011::init` puts the bear in
    # the cast only under `has: 5`, the bear takes item 5 alone, `bearScript` state 13 is flag 36's
    # only writer, and both `rm011::doit` and `getWax` arm `deathByBees` under not-flag36 -- so a
    # fishless rm11 makes the honeycomb -> beeswax -> boat chain fatal. Three derivations, none of
    # which moves anything alone (docs/KQ5-ORACLE.md §16): a trade to a ROOM is a destruction when
    # the item cannot come back (`drop_is_permanent` over the item's owner graph, with `put: X -1`
    # as its degenerate case); `disjunctive_groups` grouped BY STATE and read with `_own_required`,
    # which derives the play-tested pool asymmetry; and the disjunctive rescue read at the
    # CONSUMER, which is what keeps the Shoe and the Stick excused while the Fish is not.
    fish_bees = [r for (n, _d, r) in raw_rows if n == "Fish" and 11 in _rooms_mentioned(r)]
    check("the Fish spent at the cat is condemned by the bear that still needs it",
          any(r.get("at_room") == 6 and r.get("still_needed_at") == [11] for r in fish_bees),
          "no dangerous_sinks row ties `put: 5 6` to rm11 -- docs/KQ5-ORACLE.md §16.")

    # ...and the other side of the same coin, which is the assertion that stops §16 becoming the
    # FP the user retired in 2026-08-16b: the Shoe and the Stick are spent in exactly the same
    # statement shape, and each scene accepts the other's ammunition, so neither may be condemned.
    check("the Shoe and the Stick keep their disjunctive rescue at both scenes",
          not [r for (n, _d, r) in raw_rows
               if n in ("Shoe", "Stick") and _d == "dangerous_sinks"],
          "a throwable with a live alternative at its consumer was condemned -- the rm12 sink "
          "rows the USER ruled false positives on 2026-08-16b are back.")

    # ✅ THE FISH'S REMEDY, added 2026-08-18. The §16 row above states the disease; the cure is
    # a market-case refusal of the fish's OWN dispatch case in rm006's two handlers, because the
    # retraction is UNSOUND here, not merely unplaceable: `put: 5 6` IS the bank the kidnap fork
    # reads, so withholding it would advance the scene while unfilling what it claims to fill.
    # `market_remedies` extends to impure dangerous sinks on the row's own fatality proof (a
    # winning line never contains a losing move, so the refusal cannot wall -- and the scene
    # arms only under a non-refused pool member in hand, `rm006.sc:112`). TRADES stay excluded:
    # a clause that also GETs is the matching's territory (KQ6's lamp peddler, user-ruled
    # working-as-designed, pins the exclusion through its frozen empty market_specs key).
    fish_market = [r for r in G.market_remedies(s)
                   if r["script"] == 6 and r["item"] == 5]
    check("the fish's spend at the cat is refused in its own dispatch case",
          len(fish_market) == 1 and fish_market[0]["machine"] is None
          and fish_market[0]["anchor"] == r"put:\s*5\b" and not fish_market[0]["refused"],
          f"rows={fish_market!r} -- expected exactly one unrefused market row wrapping the "
          f"fish's case (anchor `put: 5`) in script 6; the pure-sink retraction cannot hold "
          f"an impure spend and must not try.")

    # ✅ PROMOTED 2026-08-16b (phase 3, `missability.window_closures`). The fold rows say the bank
    # is DEMANDED at the kidnap; these say the only way to fill it shuts by itself. A producer is
    # read through `guard_reqs` against the register being flipped -- rm6 stays walkable forever,
    # what stops being possible is the THROW -- and a row needs every producer dead at that value.
    # Both closers are pinned above: flag 83 (reg 485) goes up as the chase ARMS, rm6's `local0`
    # (reg 565) when you LOSE the race. It took `extract.feature_adders` with it: three of the
    # seven `put: <item> 6` sites live on `catStrip`, which reaches the cast only through
    # `(gGame setFeatures: catStrip)`, and without that cast event they carry none of the scene's
    # arming and three producers look alive at flag 83 = 1.
    window_closed = [r for (n, _d, r) in raw_rows if n in POOL
                     and r.get("pattern") == "window-closure"]
    check("the cat window's closure on arming is caught",
          {n for (n, _d, r) in raw_rows if n in POOL and r.get("pattern") == "window-closure"}
          == POOL and all(r.get("need_room") == 86 for r in window_closed),
          f"rows={window_closed!r} -- expected one window-closure row per pool member, all "
          f"naming the kidnap read at rm86. flag 83 is set the moment the chase STARTS "
          f"(rm006::doit), so every producer of `owner == 6` sits behind a window that closes "
          f"on arming, win or lose. docs/KQ5-ORACLE.md §1.")

    # ✅ THE REMEDY, added 2026-08-18 (`guards.window_remedies`, the cat-window patch). The
    # closure rows above state the disease; this pins the cure byte-exactly, because every
    # field is a decision someone argued for: V is the CONSUMER'S OWN reading of the bank
    # (rm086's `(== ((gInv at: X) owner:) 6)` disjunction, all four pool members); flag 83 is
    # the one DURABLE closer and its raise is held (set proc + test proc are the flag
    # derivation's own names); rm6's local0 is PER-VISIT (entry reset 0 != closing 1 -- losing
    # the race only shuts the window until you walk back in); and `refused` is EMPTY -- every
    # closer accounted for, so the spec ships. The two-clause shape is the USER's
    # (2026-08-14, clause 2 ruled REQUIRED: ⛔ a patched chase must NEVER replay after
    # success -- the strengthened read is what enforces it).
    wr = G.window_remedies(s)
    want_spec = {
        "site": "window", "need_room": 86, "items": [5, 8, 16, 19], "banked_at": [6],
        "producer_rooms": [6],
        "condition": "(or (== ((gInv at: 5) owner:) 6) (== ((gInv at: 8) owner:) 6) "
                     "(== ((gInv at: 16) owner:) 6) (== ((gInv at: 19) owner:) 6))",
        "holds": [{"register": 485, "trap": 1, "flag": 83,
                   "set_proc": "proc0_9", "test_proc": "proc0_12"}],
        "self_resetting": [[565, "local0 of script 6 resets to 0 on entry"]],
    }
    got_spec = [{k: v for k, v in sp.items() if k in want_spec} for sp in wr]
    check("the cat window's remedy derives whole: hold flag 83 until banked, "
          "local0 self-resets, nothing refused",
          got_spec == [want_spec] and not wr[0]["refused"] if wr else False,
          f"specs={wr!r} -- expected exactly one placeable window spec. A lost hold replays "
          f"nothing but leaves losing terminal; a lost self-resetting entry means local0 "
          f"stopped being per-visit; a REFUSED spec ships no patch at all.")

    # ✅ REWRITTEN 2026-08-16b, USER-RULED -- this red demanded the WRONG ROW. It asserted that
    # some detector flags the Amulet, on the oracle's old verdict that entering the dark forest
    # without it is a softlock. USER: *"on rm19 you can get back out. I don't think you can get
    # more than 1 screen into the forest, but that's fine. so you need the amulet but it's not a
    # stranding."* Measured agreement: from rm19, 98 of 100 reachable rooms are still reachable,
    # rm13 (the fortune teller) among them, and rm680 -- the amulet handover -- is entered only
    # from rm13. A stranding row would be a FALSE POSITIVE.
    #
    # So the pin is the pair of facts that ARE true: the demand reaches the forest, and no row
    # claims a stranding. The first half is what `(+= state 4)` bought (docs/KQ5-ORACLE.md §13):
    # `zapHim` state 4 survives on `(and (has: 27) flag84)` by skipping the death chain, and with
    # that bump unread BOTH arms fell into state 8's `proc0_26` -- the fork was not a fork and the
    # amulet was demanded nowhere.
    WITCH_ROOMS = {19, 20, 21, 22, 24, 25, 26}
    amulet_rows = [n for (n, _d, _r) in raw_rows if n == "Amulet"]
    check("the worn-amulet fireball fork demands the Amulet in every forest room",
          WITCH_ROOMS <= set(s.required.get(27, ())),
          f"required[27] = {sorted(s.required.get(27, ()))} -- expected all of "
          f"{sorted(WITCH_ROOMS)}. If this shrank, check that `(+= state N)` is still read as a "
          f"relative setstate in BOTH compile._interp and machine._op_leaf: unread, zapHim's "
          f"surviving arm stops skipping the death chain and the fork stops being a fork.")
    check("no detector claims the Amulet is STRANDED", not amulet_rows,
          f"rows={amulet_rows} -- the amulet is REQUIRED in the forest and re-obtainable from "
          f"it (rm13 is 1 screen away; USER-RULED 2026-08-16b). A row here is a false positive "
          f"to investigate, not a catch. docs/KQ5-ORACLE.md §7.")

    # ✅ PROMOTED 2026-08-16b (was 🔴 KNOWN FP) -- the sixth savior-condemned correction. The row
    # was not merely noise: the tool SHIPPED `action_specs: Tambourine@rm55: (not (has: 34))`,
    # a patch refusing the player the item that gets them out of rm55 alive. `fatal_uses` now
    # blames what the arming SITE required (`Machine.entry_site`), not what `_chain_entries` and
    # `_inherit_local_continuations` had grown onto the entry guard -- so an item that reached the
    # arming as Dink's existence condition is no longer read as a use. The assertion stays live:
    # this is the family that keeps producing new polarities.
    tambo_fatal = [r for (n, d, r) in raw_rows if n == "Tambourine" and d == "fatal_uses"]
    check("fatal_uses does not condemn the tambourine", not tambo_fatal,
          f"REGRESSION, and a dangerous one -- rows={tambo_fatal}. Dink EXISTS only while you "
          f"hold the tambourine and giving it is the escape, so a row here becomes a patch that "
          f"withholds the item that saves the player. Check that fatal_uses still reads "
          f"`entry_site` rather than `entries`. docs/KQ5-ORACLE.md §14.")

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
