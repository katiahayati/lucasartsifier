# King's Quest V — validation oracle

Our first SCI1 (not 1.1) validation game. Derived 2026-08-14 from the game source plus three
independent walkthroughs, in that order of authority: **the game source wins**, then the
walkthroughs, then the user's earlier in-game rulings recorded in memory, then me. Every claim
below is tagged with its tier; a row resting on tier 3 alone says so.

| tier | source |
|---|---|
| 1 | our decompilation, `build/kq5/ir/src` (reachable as `build/sweep/kq5/src`) |
| 2 | the user's in-game rulings (2026-07-24/27: pie and cloak re-obtainable, temple one-visit) |
| 3 | `gamerwalkthroughs.com/kings-quest-5` (the original ground-truth source) |
| 3 | `walkthroughking.com/text/kingsquest5.aspx` |
| 3 | Telltale community "dead-ends in king's quest" thread (the only source that enumerates KQ5 dead ends as dead ends) |

Anchors, all derived (`anchors.discover`): start rm48, goals {652, 673}, death signal g401.
Two `state_musts` degradations (walkThruBoy, walkThruW3) existed at 20000 steps; the cap raise is
measured separately.

The world is a mostly-backtrackable SCC, so most items are re-obtainable and NOT strandings
(tier 2: the pie and the cloak themselves are safe). KQ5's softlocks are **pockets, windows, and
slots**: a one-visit pocket behind a consumed opener, one-shot event windows whose outcome is read
much later, a one-way sail, and consumers that accept the wrong item from a shared pool.

---

## 1. The throwable pool — two required scenes drawing on one set of items (tier 1)

The single most important structure in KQ5, and no walkthrough states it: the cat scene and the
dog scene are **slots over one shared pool of throwables**, and a later room decides life or death
by *which room ended up owning one of them*.

**The pool:** Shoe(8), Stick(16), Leg_of_Lamb(19), Fish(5). Note the lamb is obtained in the
mountains — normally *after* both scenes — and the fish is normally spent on the bear to get the
stick, so in practice the pool at decision time is {Shoe, Stick}.

**The cat scene (rm6).** `rm006::init` places the cat and the rat only while
`(and (or (has: 8) (has: 16)) (not flag83))` — the encounter *already waits for the player to
hold a throwable*, which is exactly the hold shape we would otherwise have to patch in.
`rm006::doit` — the window-closing write:

    ((and (global5 contains: rat) (> (global0 x:) 290) (> (global0 y:) 142))
        (User canControl: 0) ... (proc0_9 83) ... (self setScript: catAndMouse))

**Flag 83 is set the moment the chase STARTS, not when it is won** — the one-shot window closes
on arming, regardless of outcome. Inside the chase, the cat's and catStrip's `handleEvent`
accept any of the four pool items; a successful throw does `(= local1 1) (global0 put: <item> 6)`
— **the "mouse saved" fact is the ownedBy store: some pool item's owner == 6.** There is no
dedicated flag. If the cat's `Chase` motion completes first (`local0` set), throws are refused
("too late") and the mouse is disposed.

**The dog scene (rm12).** Same shape: armed by `(and (or (has: 8) (has: 16)) (not flag106))`,
accepts Stick(16), Shoe(8), Leg_of_Lamb(19) — each `put: <item> 12` — and repays via the ants
(the golden needle in the haystack, → tailor → cloak). Flag 106 likewise marks the scene done.

**The read (rm86, the inn cellar — kidnapped arrival only):** `rm086::init` under
`(== global12 85)`:

    (if (or (== ((global9 at: 8) owner:) 6) (== ((global9 at: 16) owner:) 6)
            (== ((global9 at: 19) owner:) 6) (== ((global9 at: 5) owner:) 6))
        (self setScript: rescue)
    else
        (self setScript: yourStuck))

`yourStuck` is 55 cycles + 7 seconds, then `proc0_26` — **death with nothing to do**: a true
walking-dead by the one rule, whose cause is a timed, one-shot window many rooms and hours
earlier. `rescue` (the mouse chews you free) then still demands the Hammer: its no-hammer arm
parks into `walkingDead` (60 seconds, `proc0_26`).

**Verdicts:**
- *Miss the cat window (never arm it, or lose the race) then enter the inn's back room* —
  **TRUE softlock (death class), the worst in the game.** Tier 1 end to end.
- *Spend your last cat-compatible throwable at the dog* — **TRUE, but conditional**: fatal only
  when it leaves the pool empty for the cat with the window still open. The shipped
  `dangerous_sinks` rows (Shoe@rm12, Stick@rm12) name the right sites and are blind to the
  disjunction; they over-warn, they do not under-warn.
- *Skip the dog scene* — needle chain lost (→ no cloak). The cloak-need is tier 3 only
  ("when you start to shiver wear the cloak"); the freeze-death mechanism is not yet
  source-verified. **Open: verify the mountains' cold-death read.**

### 1a. The pool is wider than the two scenes — the Lamb and the Fish have their own consumers (tier 1, verified 2026-08-14 at the user's prompting)

The cat and dog scenes accepting four items is not generosity, it is a trap surface:

- **Leg_of_Lamb(19): sole source rm28 (the inn's cupboard — `openCup` tests `owner == 28`), in
  town, so it IS in the pool at cat/dog time. Its required consumer is the roc's nest:**
  `rm042` state 6 branches on `(== ((global9 at: 19) owner:) 34)` — lamb fed to the eagle →
  `newRoom: 43` (the rescue); *anything else* → states 8–11 → `proc0_26`, death. **And the
  else covers the pie**: `rm034`'s eagle accepts Pie(2) too (`put: 2 34`), `feedEagle` differs
  only in the throw animation (`local36` picks loop 9 vs 8), and the begging scene disarms on
  either feed (`(and (!= owner(19) 34) (!= owner(2) 34))`) — so **feeding the pie silences the
  eagle's visible need, wastes the pie (the yeti's item), and still leaves rm42 fatal.**
  Verdicts: *throw the lamb at the cat or dog* → TRUE softlock (death at rm42) — note the
  cat throw still banks the rm86 rescue while dooming rm42, a genuine cross-slot web.
  Detected today: nothing — but rm42's fork is the SAME init-fork-on-an-ownedBy-value death
  fold as rm86's, so phase 1 of the window plan should surface the lamb for free. Declared
  red in the test.
- **Pie(2) to the eagle → the yeti (tier 1 end to end, user-confirmed 2026-08-14: "I don't
  think you can reobtain the pie after you feed it to the eagle").** The pie's SOLE source is
  `bakeShop.sc` — the bakery, in town, behind the one-way forest. rm36 is the yeti: a `Chase`
  into `proc0_26` death whose counter is throwing the pie (`put: 2 36`). Feed the pie to the
  eagle post-forest and the yeti is unsurvivable. This REFINES, not flips, the July "pie
  re-obtainable, safe" ruling — that one scoped to town reachability (the rm29 misclick
  question); the bakery cannot be reached from the mountains. **TRUE softlock, declared red.**
- **Fish(5) → the bear → the BEES (tier 1, closed 2026-08-14; the user's "get rid of the
  bear to save... the bees maybe?" was the right memory).** rm11 is the anthill-and-beehive
  room. The bear inits only while `(global0 has: 5)`; throwing the fish (`put: 5 11`) runs
  `bearScript`, whose state 13 is the ONLY writer of **flag 36**; and both `rm011::doit` and
  `getWax` arm **`deathByBees`** (`proc0_26 263`) on the hive control while
  `¬flag36 ∧ ¬bear-present`. So arriving fishless (or having wasted the fish on the cat —
  `put: 5 6` is accepted) makes flag 36 unsettable and every honeycomb (`get: 17`) approach
  fatal → no beeswax → the boat. **Fish-at-cat is a TRUE walking dead, declared red.** (The
  earlier "overlay semantics" caveat is moot — the flag-36 gate decides it.)

## 2. The kidnap corral (rm85 → rm86) (tier 1)

`rm085::doit`: walking north past a spoken warning (`(not local0)` arm, ego bounced to y=148)
and then continuing (`y < 150`) arms `attack`, which ends in `newRoom: 86` — the kidnap. The
model already carries the sound gate on the way out: `_emeta[(86,28)]` = free iff
`prevRoom != 85`, else `own(22)` (Hammer). Surviving the kidnap therefore requires **two things
banked in advance**: a pool item owned by rm6 (§1) and the Hammer(22).

The Hammer does double duty (tier 1 for the inn door via flag 80; tier 3 for prying the Crystal
in the ice castle — **open: verify the crystal site**). The Rope(20) is *sourced inside rm86*
(`getRope`; on a non-kidnapped revisit the prop re-inits while `owner == 86`), and the rope is
needed at the cliffs (§4) — so the kidnap pocket is not only survivable-with-preparation, it is
**mandatory**.

**Verdict:** entering rm85's back area without the banked throw, or without the Hammer, is a
TRUE softlock (death class). Detected today: **no row** — the trapped state is
(room 86, prev = 85), and no detector walks (room, register-value) states. The gate itself is
modeled; only the walk is missing.

## 3. The sail (rm49 → 650/654) — the classic "board the boat unprepared" (tier 1 + 3)

Sailing loses the beach region {48, 49, 50, 90} permanently (raw room graph). Two carries are
demanded on the far side:

- **Shell(23)** — sole source rm49; used at rm46: the hermit scene branches on `(has: 23)`
  (tier 1), and tier 3 agrees loudly ("give him the shell so that he can hear you", Cedric's
  rescue; the Telltale thread: failing to save Cedric gets you zapped by Mordack before the end).
- **Fishhook(31)** — sole source rm90; used at rm67 (`lookInMseHole`): fishes up the
  **Moldy_Cheese(32)**, without which Mordack's machine cannot be powered (tier 1 for the hook →
  cheese site; tier 3 for the machine).

**Verdict: both TRUE softlocks, both DETECTED** (`analyze()`, missing-prereq-before-gate), with
edge specs already emitted: `rm49→rm650/654: (and (has: 23) (has: 31))`. These two rows are
KQ5's Shell/Fishhook headline and the first automatic catch of this class in this game.

## 4. Fatal uses (tier 1 + 3)

- **Rope@rm30 (`ropeOnBranch`) — TRUE.** Tier 3: throw the rope onto the pointed rock ledge,
  *not* the branch; "the branch is too weak." The branch arm is an unsurvivable machine; the
  detector's row and its `action_spec` guard `(not (has: 20))` name the right site.
- **Tambourine@rm55 (`hugScript`) — FALSE POSITIVE, savior-condemned variant.** Dink is only
  initialized while `own(34)` holds, so the hug-death's arming context carries `own(34)` — but
  giving the tambourine (`giveTamboScript`, `put: 34`, drops the Hairpin) is the *escape* from
  that very machine, and holding the tambourine there is mandatory for progress. This is the
  sixth member of the family the five `fatal_uses` corrections were built for, with a new
  polarity: the item rides the arming guard (the monster's existence condition) rather than a
  branch. **Do not ship; cure in the detector, not the oracle.**

## 5. The temple toll (tier 1 + 2, golden since July)

rm214 → rm18 behind the Staff(7) which breaks (`put: 7 214`); Brass_Bottle(6) and Gold_Coin(11)
inside; one visit. **DETECTED** (`toll_strandings`), unchanged.

## 6. The fortune teller's slot (rm13) — the substitution dead end (tier 1 + 3)

`rm013`'s give-handler accepts **Gold_Coin(11) or Golden_Needle(3)** for the Amulet —
`put: 11 13` / `put: 3 13`, refused once the amulet is owned. Tier 3 (Telltale thread): paying
with the needle makes the game unwinnable (the needle's real consumer is the tailor → cloak).
This is a pure **exchange-slot** hazard: two items competing for one slot, one of them demanded
elsewhere. **Verdict: TRUE (tier 3 on the consequence; tier 1 on both puts). Not detected.**

## 7. The witch and the worn amulet (tier 1) — and the region-script gap

`witchRegion.sc`: surviving the witch's fireball requires `(and (has: 27) (proc0_12 84))` —
**"worn" is flag 84**, an ordinary bit-store register our flag lowering already models; there is
no own/worn extraction gap. What keeps this out of the surface is that the death fold lives in a
**region script**, not a room. The dark forest is one-way on entry (tier 3: "you won't be able
to get out again the way you came"; **open: verify the one-way mechanism in source**), the
amulet's sole source is rm13 (§6). **Verdict: entering the dark forest without the amulet
(or without wearing it) is a TRUE softlock (death class). Not detected; blocked on the
region-script scope.**

## 8. The roc's nest locket (tier 3) — the second one-shot window

A few seconds to grab the Locket(25) in the nest; it is later given to Cassima, who opens the
cell escape (the hairpin/pickLock machinery of rm55 is tier 1). Same class as the cat window:
a timed one-shot scene whose token is read at a later life-or-death site. **Open: source-verify
the nest scene's window write and the cell's read before promoting this row.**

## 9. Bag of Peas (tier 1 mechanism, verdict open)

`castle.sc` (the Mordack castle region script): a throw does `put: 24`, sets flag 63, then
**increments the peas item's own `cel`** — `((global9 at: 24) cel: (+ 1 ...))` — and re-`get`s
the bag. The peas are a **counted consumable spelled as an inventory item's view state**, spent
against `theHenchMan` and `theCat`. This is the item-property store (the known third-store gap:
[[item-property-state-not-modelled]]), so the 13 `resource_exhaustion` rows are the coarse
shadow of a mechanism the model cannot yet count. **Verdict open until that store exists; the
rows should collapse either way.**

---

## Scorecard (2026-08-14)

| # | softlock | mechanism | status |
|---|---|---|---|
| 1 | temple pocket | consumed-opener toll | **CAUGHT** (toll) |
| 2 | Shell past the sail | one-way edge, carry demanded | **CAUGHT** (analyze + spec) |
| 3 | Fishhook past the sail | one-way edge, carry demanded | **CAUGHT** (analyze + spec) |
| 4 | cat window missed → inn death | one-shot window → ownedBy read → death | **CAUGHT** (phase 1: `ownedby_death_folds`, all four pool items demanded at rm86 under prev==85); the WINDOW half (flag 83 closes on arming) stays a declared red for phase 3 |
| 5 | pool starved at the dog | exchange slots over one pool | PARTIAL (`dangerous_sinks`, disjunction-blind) |
| 6 | kidnap without Hammer | (room, prev-value) trap; gate modeled | MISSED (no state walker; phase 2) |
| 7 | rope on the branch | fatal use | **CAUGHT** (fatal_uses) |
| 8 | tambourine near Dink | — | FP to cure (savior-condemned, arming polarity) |
| 9 | needle to the fortune teller | exchange slot | MISSED |
| 10 | forest without worn amulet | region-script death fold, flag 84 | MISSED (region scope) |
| 11 | locket window missed | one-shot window (tier 3) | MISSED, unverified |
| 12 | peas exhaustion | consumable | OPEN (13 noisy rows) |
| 13 | lamb to the cat/dog → roc's nest death | exchange slots + ownedBy death fold (rm42) | **CAUGHT** (phase 1: rm42 `hatch` state-6 fork — its death chain sits behind a `(++ state)` skip the transition model now reads — plus the rm86 pool row) |
| 14 | pie to the eagle → yeti unsurvivable | slot swallow + chase-death counter-item | **CAUGHT** (phase 1: rm35 `killEgo` entry fold, prev==36 — the yeti kill continuing across the edge. The rm36 chase itself makes no claim: a `Chase` state is a race the player can decline by leaving, the refinement that keeps KQ4's rm49 dog — flee-able in play — out of the surface) |
| 15 | fish to the cat → flag 36 unsettable → bees | exchange slot + sole-writer window (rm11) | **CAUGHT on the demand half** (phase 1: the rm86 pool row names the Fish); the bees' flag-36 window closure stays a declared red for phase 3 |

**Phase 1 (2026-08-14, `missability.ownedby_death_folds`):** an arrival that forks on an owner
value, whose losing arm cannot be survived (`_room_unavoidable` — `_survivable` with
pre-emption, the classifier `fatal_uses` answers to), demands the value at the room's entry.
Rows carry the full demand disjunction and the readable arming context (`prev == 85` / `36`),
which is what phases 2–3 and patch B consume. Measured corpus-wide: LSL2/KQ4 byte-identical
plus the new empty snapshot key (goldens re-blessed key-by-key), KQ6/LB2 zero rows, KQ5 moved
by pure addition.

Nothing in this file is a guard source ([[derived-only-no-declared-specs]]): it validates, it
never feeds the patcher.
