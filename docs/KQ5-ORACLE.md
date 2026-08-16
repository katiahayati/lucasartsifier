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

Anchors, all derived (`anchors.discover`): start **rm99** (the boot/speed-test room, whose own
`cond` sends you to rm1 = Crispin's cottage or to the title screen), goals **{119, 673}**, death
signal g401. ⛔ The "start rm48, goals {652,673}" recorded on 2026-08-14 is superseded: 650/654
were Cedric's CD *view* numbers reaching the room universe through a temp-scope bug, and rm48 was
a cluster no engine entry reaches. 119 is the title screen and is terminal only because
`kq5Title` exits via `newRoom: (if local0 1 else 100)`, a computed conditional the extractor does
not resolve — a known gap, not a goal. The `state_musts` degradations are gone (saturation fix).

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

**⭐ THE POOL IS ASYMMETRIC — PLAY-CONFIRMED IN THE STOCK GAME, USER 2026-08-16.** The dog
**refuses the Fish(5)**: *"that wouldn't divert the dog's attention"* (`rm012.sc:672`, the
`else` arm, message 280 — no `put:`, the item stays in inventory). So the two scenes do not
draw on the same set after all:

| | Shoe 8 | Stick 16 | Leg_of_Lamb 19 | Fish 5 |
|---|---|---|---|---|
| cat (rm6) | ✅ +4 pts | ✅ +4 pts | ✅ silent | ✅ silent |
| dog (rm12) | ✅ | ✅ | ✅ | ❌ refused |
| arms either scene | ✅ | ✅ | ❌ | ❌ |

Three facts follow, and they are the reason this section matters more than its size suggests:

1. **The Fish's only competing consumer is the bear (rm11), not the dog.** So "spending the
   Fish at the cat strands you" is a SINGLE-ITEM claim — nothing else can cover the rm11 need.
   The Shoe and the Stick have no competing consumer at all, which is what makes them the safe
   ammunition and their old rm12 sink rows false positives (see the verdicts). ⛔ A
   `Fish@rm6 → still needed at [11]` row was reported on 2026-08-15 as the gain the cast-gating
   fix would bring, and **it does not exist**: it was an artifact of half that fix, naming a
   true item for a false reason. The fish-at-cat walking dead is still stated only through the
   rm86 fold row and the bees' declared red (§1a).
2. **The scenes arm on {8,16} but accept {8,16,19,5}.** Sierra guaranteed a safe option is in
   hand before either encounter can start, then let the player improvise a fatal one. The
   trap springs only on cleverness — and, read the other way, **the arming is why the pool
   cannot be starved**: an empty-handed visit does not start the scene, so the window is still
   open when you come back armed.
3. **Only the safe throws score.** `proc0_27 4` fires for Shoe and Stick; Leg_of_Lamb and Fish
   award nothing and are otherwise identical — same animation, same rescued mouse, same
   `put: <item> 6`. The score is the only in-game tell that you just spent the wrong item,
   and it is a tell you would have to be watching the counter to notice.

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
- *Spend the Shoe or the Stick at the dog* — ⭐ **NOT A SOFTLOCK. USER-RULED 2026-08-16b**, and
  the earlier "TRUE, but conditional" verdict here is **WITHDRAWN**: *"you can't skip the bear…
  use your shoe on the dog, that's okay, finish the bear, get the stick, and use that on the cat.
  it's not a softlock."* **The pool cannot be starved, and the source says why:** `rm006.sc:112`
  inits the cat and the rat only under `(or (has: 8) (has: 16))`, and flag 83 — the window — is
  set by `rm006::doit` only once the rat is on screen. Walk into rm6 empty-handed and the scene
  does not start: nothing is spent, nothing closes, and it is still waiting when you come back
  with the Stick. **The encounter IS the hold we would otherwise have to patch in.** The two
  `dangerous_sinks` rows Shoe@rm12 / Stick@rm12 were therefore FALSE POSITIVES; they went with
  `f623aa2` (the dog's throw arms `throwStick`, so it was never a "consumption that accomplishes
  nothing"), and their going is a CURE. Both items are pinned to their rm86 pool-demand row alone
  and sit in `EXPECTED_CAUGHT`. **The genuinely dangerous throws are the other two** — the Lamb
  at either scene (demanded at rm42) and the Fish at the cat (demanded at rm11); neither has a
  sink row at its spend site, and each is caught elsewhere (§1a, and the bees' declared red).
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
TRUE softlock (death class). **CAUGHT since 2026-08-14 (phase 2)**: the throw half by the
rm86 fold rows (§1, phase 1), the Hammer half by `register_strandings` once its fetch walks
banned the item they fetch — the trapped state (room 86, prev = 85) had always been walkable;
the permissive source test was crossing the own(Hammer)-priced exit while judging the
Hammer obtainable. Row: reg12=85, flip room 86, needed at 86. The row's hold-form spec is
REFUSED by derivation (prev is only written by crossings, so there is no free-running write
to hold); its enforcement site is the kidnap crossing itself — patch B's commit-interceptor
at rm85's warn-and-bounce.

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

## 10. The Wand — the one place that DOES take it from you, and why it still cannot strand you (2026-08-15, derived)

USER 2026-08-14 ruled the Wand a false positive on the ground that "you start the game with the
wand, so you always have it", and USER 2026-08-15 re-affirmed that ruling against the mechanism
below. The ruling stands. The *reason* recorded for it did not survive the source, and this
section replaces it: **"the one `put: 28` re-`get`s it 128 lines later, a use animation" is
wrong.** It is a real spend, the wand really does leave inventory, and it really does stay
where you left it across room exits. Three separate facts make it unstrandable anyway.

**What it is.** `KQInv` element #28 is Crispin's wand, dead weight until the endgame. Granted at
`cdIntro10.sc:547` and `rm099.sc:127` (the boot room's `global322` arm, which then sends you to
rm1) — and, the fact the model is missing, **re-granted unconditionally in `rm001.sc:78`'s
`init`**: `(if (not (global0 has: 28)) (global0 get: 28))`. Entering room 1 without the wand is
not a state you can leave room 1 in.

**The site that takes it.** Exactly one in 211 scripts. `rm066.sc:132`, `putCWandScript`:
`(global0 put: 28 global11)` lays Crispin's wand on the machine tray in Mordack's laboratory.
The wand's owner becomes the room, and `rm066.sc:55` re-inits the `cWand` prop iff
`(== ((global9 at: 28) owner:) global11)` — the same *"is it still there?"* owner-store check the
temple catch rests on (§8). It persists there while you walk the castle.

**Why it is a round trip, not a loss.**
1. **Drop and re-get are the same room.** `cWand`'s verb-3 handler (`rm066.sc:903`) runs
   `getCWandScript` → `get: 28` (`rm066.sc:260`), and the prop re-arms from the owner check on
   every entry. rm65↔rm66 is a free walk (`rm065` enters on a control colour, rm66's west edge
   returns).
2. **Every wandless path into the endgame is a DEATH, not a walking-dead state.** All four
   `newRoom: 124` in the game are inside rm066. `battle.sc:84` sets flag 55 on
   `(or (not (proc0_12 60)) (not (global0 has: 28)))`, and `mordOneScript` state 13 under flag 55
   does `(= global330 318) (proc0_26)` — `Main.sc:757`, the Restore/Restart/Quit box. Mordack
   catching you anywhere else in the castle is death too (`castle.sc:1583/1681`, message 657).
   There is no "captured, wand left behind, game continues".
3. **The trap that exists is a timer on that same screen.** Both wands on the trays plus the
   cheese sets flag 60 and `local52 = 15`; rm066's `doit` cond takes the timer branch, which
   **shadows the edge-exit branch below it**, and `User canControl: 0` — for fifteen seconds you
   cannot walk out, you can only click the wand. At zero, `newRoom: 124` and the wandless death
   above. This is the walkthroughs' "quickly take Crispin's wand and Mordack will appear"
   (StrategyWiki, thecomputershow). Preventable on its own screen by the single click the game
   just prompted — the same refinement that keeps KQ4's rm49 dog and KQ5's rm36 yeti chase out of
   the surface — so it is NOT promoted. Recorded here so the next session does not rediscover it
   as a candidate.

**What the detector says, and where the cure is not.** Measured 2026-08-15:
`sources[28] = {1, 99, 659}`, `drops[28] = {66}`, `required[28] = {66, 124}`, and two `analyze`
`missing-prereq-before-gate` rows (need@rm66 and need@rm124) whose frontier is `rm40->rm41`, the
roc. Both say "carry the Wand across the roc": true, and unfailable — the sources are all on the
near side, and the only drop site is on the far side *and is the need room*. The model believes
you can arrive wandless only because `_reach_without(28)` returns all 100 rooms: the banned walk
assumes **you can decline rm1's handout**. `source_guards[28][1]` is exactly `GNot(own(28))`,
emitted by the room object itself, which is the signature of a grant you cannot refuse.

⛔ The cure is therefore NOT the never-strandable class this doc used to propose (a class shaped
to protect a known answer, and refuted by fact 2 above: something *does* durably take it), and
NOT `entry_musts` (two cures died there 2026-08-15; both make KQ6's `removeHoleScr` a second
source and break an enforced fact). It is one general principle — **a source you cannot decline
is not optional**, so `_reach_without` must not propagate through a room whose entry hands the
item over under a guard entailing `¬own(X)`.

**SHIPPED 2026-08-15** as `missability._unrefusable_grants` + a `barrier` argument to `_walk`,
fed by a new `Acq.method` recorded in `extract.py` (the emitting method, which is what separates
a handout from a pickup). Strict on both halves — the method must run with no player input
(`init`/`doit`), and the guard's whole conjunct spine must be the idempotence check itself —
because the failure direction is LOST FINDINGS: a barrier shrinks `_reach_without`, and a room
dropped from it is a room no detector will judge. **Measured twice.** First simulated in the
product under a deliberately looser reading (any site whose guard merely *entails* `¬own`, any
method), which barriers 8 KQ4 sites, 4 KQ6, 2 LB2 and KQ5's own Amulet and Elf_Shoes: inert
everywhere. Then built and re-measured against pre-change baselines — the FULL `snapshot.py`
surface, placements included, is **byte-identical on LSL2, KQ4, KQ6 and LB2**, and KQ5 moves by
exactly two lines:

```diff
-  "rm40->rm41: (and ... (gEgo has: 21) (gEgo has: 28) (gEgo has: 34) ...)",
+  "rm40->rm41: (and ... (gEgo has: 21)                (gEgo has: 34) ...)",
   "Locket",
-  "Wand",
```

---

## Scorecard (2026-08-14)

⛔ **This is a work in progress, not a finished oracle.** Four rows are MISSED with a declared
red apiece, one is a false positive we still emit, and rows 9–12 rest on tier-3 or open
verdicts. Two builds landed on 2026-08-14 (phase 1: owner-value death folds; phase 2:
item-banned fetch walks) and the remaining phases are unbuilt. A passing test run means the
catches listed as CAUGHT are still caught for the mechanism stated — it does not mean KQ5 is
covered.

| # | softlock | mechanism | status |
|---|---|---|---|
| 1 | temple pocket | consumed-opener toll | **CAUGHT** (toll) |
| 2 | ~~Shell past the sail~~ | — | **RETIRED 2026-08-15, not a softlock.** USER 2026-08-14: "you can sail from the hermit island to the harpy island again to get the shell." Its old row rested on the phantom cartoon edges of §8; the row went when its cause did |
| 3 | Fishhook past the castle crossing | one-way edge, carry demanded | **CAUGHT** (analyze + spec). ⛔ The frontier is `rm44/45/46->rm113`, the hermit island's crossing to the far shore — NOT the old "sail rm49->650/654", whose rooms never existed (650/654 are Cedric's CD view numbers, which reached the room universe through a temp-scope bug). Re-pinned 2026-08-15 |
| 3b | Cat_Fish up the castle stairs | one-way edge, carry demanded | **CAUGHT 2026-08-15** (analyze). Walkthrough: "Pick up the Fish and then walk up the stairs", then "Throw Fish at the cat and then use the Bag on the cat to catch it" — and "from here on out, if you see the cat, you must throw the fish to him". `castle.sc` (the region live in every castle room) dispatches `(37 → theThrowFishScript)` and `(24 → sack the cat)`. Source rm51 is outside the castle-side set and rm54's three exits are one-way |
| 3c | roc point of no return | one-way edge, carry demanded | **CAUGHT 2026-08-15** (analyze). `rm40->rm41` is the roc carrying Graham off — KQ5's real point of no return. Harp (rm9 → rm90), Beeswax (rm24 → rm44) and Crystal (rm38 → rm52) must cross it; Iron_Bar (rm44 → rm54) rides the Fishhook's frontier; the Locket (rm42, the nest → rm57, Cassima's cell) crosses `rm42->rm43`. All five USER-RULED REAL 2026-08-15 |
| 4 | cat window missed → inn death | one-shot window → ownedBy read → death | **CAUGHT, BOTH HALVES.** Phase 1 (`ownedby_death_folds`) demands the banked throw at rm86 under prev==85; **phase 3 (`window_closures`, 2026-08-16b) states the window** — every producer of `owner == 6` is dead once flag 83 (reg 485) or rm6's `local0` (reg 565) flips, and rm86 is still ahead. Four rows, one per pool member. See §12 |
| 5 | ~~pool starved at the dog~~ | — | ⭐ **NOT A SOFTLOCK — USER-RULED 2026-08-16b, row withdrawn.** Both scenes wait for ammunition (`rm006.sc:112`), so an empty-handed visit spends nothing and closes nothing: Shoe on the dog → clear the bear → Stick on the cat. The two `dangerous_sinks` rows were FPs and went with `f623aa2`; Shoe and Stick are pinned to the rm86 pool demand alone. The real trap in this family is throwing the **Lamb or the Fish**, rows 13 and 15 |
| 6 | kidnap without Hammer | (room, prev-value) trap; gate modeled | **CAUGHT** (phase 2: `register_strandings` with item-banned fetch walks — the permissive walk was assuming the hammer to fetch the hammer; row reg12=85, flip rm86, needed at rm86) |
| 7 | rope on the branch | fatal use | **CAUGHT** (fatal_uses) |
| 8 | tambourine near Dink | — | FP to cure (savior-condemned, arming polarity) |
| 9 | needle to the fortune teller | exchange slot | MISSED |
| 10 | forest without worn amulet | region-script death fold, flag 84 | MISSED (region scope) |
| 11 | locket window missed | one-shot window (tier 3) | MISSED, unverified |
| 12 | peas exhaustion | consumable | OPEN (13 noisy rows). Note the emptied bag is REQUIRED — the walkthrough sacks the cat with it — so the peas are not pure flavour |
| 12b | rm57->rm683 carry-in | requirement broadcast into a cutscene | **FP, CURED 2026-08-16 (§11).** rm683 is `cdCassimaToon`, a CD cutscene that tests no item at all; the own(37)/own(24) demands landed there because `castle.sc` is the region live in all 16 castle rooms and `theCat` had no presence condition. `extract.room_valued_globals` reads the cat's bagged arm `(== global338 gCurRoom)` — the bagged cat is where you bagged it — and the presence narrows to seven rooms. Flipped `test_toll.py`'s two KQ5 assertions with it, as declared |
| 12c | the Wand, anywhere | — | **FP, CURED 2026-08-15 (§10).** USER 2026-08-14, re-affirmed 2026-08-15: "you start the game with the wand, so you always have it." ⛔ The old reason was wrong — rm066's machine tray *does* take it (`putCWandScript`, `put: 28 gCurRoom`, and it stays there) — but the drop and the re-get are the same room and every wandless path into rm124 is a death. Cured by `_unrefusable_grants` (rm1's `init` grant), NOT by the never-strandable class this row used to propose |
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

## §8. Why none of this could be seen before 2026-08-15 — three defects under one symptom

The [[session-2026-08-14d-handoff]] pinned KQ5's phantom connectivity on `cartoonCode`
(script 763), the CD ending montage: one `cond` whose arms are `(proc999_5 gCurRoom <rooms>)`,
one cartoon per place you can be standing, each closing with a real `newRoom:`. Thirteen rooms
call it, so rm57 — Cassima's cell, inside Mordack's castle — acquired exits to the village, the
elf, the ice queen and the ending, and no part of the castle was one-way. That reading of the
symptom was right. The cause was two levels deeper, and the fix it proposed is a **no-op alone**
(measured).

1. **KQ5's IR was stale.** Emitted before our sci-tools fork learned to serialize the export
   table, so **0 of its 211 scripts had `exports`** (LSL2 105/118, KQ4 147/159, KQ6 270/341,
   LB2 191/255). `ir.script_id_target` therefore returned None for *every* `(ScriptID N M)` in
   the game, and `extract._scriptid_scope` took its documented permissive fallback: seed EVERY
   object of the target script with the call site's guard. Rebuilding takes ~2s and the `.sc`
   output is **byte-identical** — the rebuild adds exports and nothing else.
2. **Mention propagation was room-blind.** `_scriptid_scope` propagates a seeded object's
   condition to the siblings it MENTIONS, copying that condition unchanged. A mention is a CALL
   SITE with a path condition; where every site demands another `gCurRoom`, nothing in this room
   reaches the sibling. Now `extract._object_mentions(sc, room)`, conservative: drop only where
   the streaming walk accounted for every mention and all of them exclude this room.
   ⛔ Fixes 1 and 2 are both required and neither works alone — with 1 only the toons re-enter
   through mentions; with 2 only, `present` holds None and the propagation path is never taken.
3. **The real blocker: `global322` was promoted as a mode register.** `edge_meta` reads
   `!=`/relational demands against `reg_vals` as EXACT, on the stated ground that it is "the set
   of values the MODEL can ever produce". KQ5 stores `polyList15`, `actor_1` and `cedric` in
   global322 — values the model cannot represent — so its universe `{0,50,100,200}` was
   incomplete. rm099, the boot room, branches on the bare truthiness
   `(if global322 (gEgo get: 28) (gCurRoom newRoom: 1))`, which lowered to `∈ {50,100,200}`
   while the start state holds 0, **so in that projection the walk could never leave the start
   room**. `_reach_without` and `reobtainable_rooms` both INTERSECT over projections, so that one
   dead projection emptied both for every item: `_reach_without(X) = {99,119}` for all X, and
   **`analyze()` returned zero rows for all of KQ5 and could not have returned any.** Cured in
   `missability.gating_registers` via `_object_valued_globals`. Measured inert elsewhere: LSL2
   (8), KQ4 (10), KQ6 (26) and LB2 (20) all store objects in globals and none is promoted.

**The regression that cure exposed, and its own cure.** Dropping the poisoned projection took
`toll_strandings` 5 → 0 and lost the temple — because the temple catch had been *resting on the
degenerate projection*, exactly as the Shell's catch rested on the phantom edges. `build_maps`
records a machine `get:` under the state's path condition and drops the machine's ENTRY guard as
"an item cost (`entry_musts`)". True of its `own(…)` conjuncts; **false of its owner-store (LOC)
conjuncts**, which `entry_musts` never absorbs. `rm017.init` inits the staff prop under
`(== ((gInv at: 7) owner:) 17)` — what `_loc_placed_required` already calls the *"is it still
there?"* check and correctly discounts for the REQUIREMENT question. For a SOURCE's liveness it
is the whole answer: rm214's door breaks the Staff with `put: 7 214`, which moves the owner and
kills the site. `_entry_owner_conjuncts` puts the conjunct back into `source_guards`;
`_spend_exhausts_sources` consumes it in `toll_strandings`. The temple returns for the right
reason — and the Wand's toll row does not.

**Corpus gate:** the full `snapshot.py` surface is BYTE-IDENTICAL on LSL2, KQ4, KQ6 and LB2;
only KQ5 moves.

## §11. The bagged cat's room — how the wedding-cutscene carry-in was cured (2026-08-16, derived)

**What the tool said about the game.** "Before you may walk from Mordack's hall (rm57) into the
cutscene where Cassima takes the locket (rm683), you must be carrying the Bag of Peas and the
Cat Fish." Emitted as a patch guard, `rm57->rm683: (and (has 24) (has 37))`. It is not merely
wrong, it is backwards: both items are destroyed by the cat puzzle (`put:` with one argument sets
the owner to −1, `User.sc:175`), the fish's source rm51 lies past rm54's one-way stairs, and the
bag's cupboard prop re-inits only while its owner is still 56 — **so the guard is unsatisfiable
for exactly the player who solved the puzzle as designed, and satisfiable only for one who never
met the cat.** rm683 is `cdCassimaToon`; grep it for `has:`, `get:` or `put:` and there is
nothing. There is no input during it at all.

**Where the demand came from.** `castle.sc` is the REGION live in all 16 castle rooms, and
`theCat` lives in it. Its handler answers the fish with `theThrowFishScript` and the pea bag with
the bagging script, so those two acts were attributed to every room the region serves — rm683
included — and `toll_strandings` then demanded the items be carried in.

**Why four earlier fixes each measured as zero.** The demand rested on a CONJUNCTION of four
gaps, so any partial fix moved nothing and read as a dead end (2026-08-15b filed one that way).
Three of them landed on 2026-08-16 as `f623aa2` and `1799f90`: handler walks and machine
`changeState:` entries now carry the object's cast condition (only the `setScript:` scan did),
`_curroom_demand` reads a `GAnd` by intersecting its readable kids, `req()` will not file a
requirement in a room the site guard excludes, and an object init'ed across scripts by export
index (`((ScriptID 550 3) init:)` — the henchman, Mordack) finally has a presence condition.
None of it moved the row, because the union of presences was dominated by `theCat`, whose own
presence condition still read "always".

**The fourth gap, and the actual cure.** The cat has two ways into the cast. `proc550_16` places
it inside a `switch gCurRoom`, which the model already reads. The other is

    (if (and (== global332 7) (== global338 global11))          ; castle.sc:154
        (theCat init: ignoreActors: 0 setScript: catInBag))

— "the bagged cat is sitting in the room where you bagged it". `_cmp_atom` had no reading for a
global compared against another global, so that arm was opaque, and **one unreadable disjunct
frees the whole OR**.

`extract.room_valued_globals` gives it one. A global every write of which is a literal or the
current-room global holds a ROOM, so `(== gX gCurRoom)` lowers to the disjunction over the rooms
it can hold — the same move `_oneof_atom` makes for a membership test. Deriving those rooms has
three parts, and the third is the interesting one:

1. **Classify.** One write we cannot read (a computed value, a `++`) and the global is not
   enumerable; the compare stays opaque. The failure direction is "we learn nothing", never "we
   exclude a room the player can stand in".
2. **Attribute** each `= gX gCurRoom` write to the rooms it can RUN in — the value it writes IS
   the room it runs in. A procedure's rooms are its CALL SITES' (`proc550_16` is called only from
   rm60, rm61 and rm63); a room script's are its own; anything else runs where the OBJECT is,
   which is its presence condition, and a `changeState` also where the machine can be ARMED.
3. **Least fixpoint, based at false.** `global338`'s third writer is `theBagCatScript` state 3,
   and that machine is armed from the cat's own handler — whose presence condition contains the
   arm being derived. A greatest fixpoint keeps rm683 alive by self-reference. Starting from "the
   compare is never true" settles in one round.

Measured: **g338 → {57, 58, 59, 60, 61, 63, 64}**, rm683 excluded. The `rm57->rm683` toll rows
and their patch guard are gone, the peas' exhaustion rows narrow to the rooms the cat and the
henchman are actually in, and every other KQ5 row is unmoved. `Bag_of_Peas` leaves
`softlock_items`; it was there only on the FP (row 12 of the scorecard, verdict still open).

**Corpus gate.** LSL2, KQ4, KQ6 and LB2 are BYTE-IDENTICAL on the full snapshot surface,
placements included. Two of them spell the idiom themselves and still do not move — KQ4's
`global124` is which of rooms 20/26/27 the unicorn was randomised into, LB2's `global571` covers
seven rooms — which is the evidence that the rule is general rather than shaped around KQ5.
LSL2 and KQ6 have no candidate at all: their only global compared against the current room is the
pending-room one, written from another variable and so not enumerable.

## §12. The cat window — stating the closure, not just the demand (2026-08-16b, derived)

**What the tool said, and what it left out.** Phase 1 gave the demand: *arriving in the inn
cellar from the kidnap, some throwable must be owned by room 6, or `yourStuck` is a pure-timer
death you cannot act against.* True, and useless on its own — it does not say that the only way
to satisfy it shuts by itself, hours earlier and half the map away. That is the half a player
actually loses the game to, and it is the game's worst softlock.

**The mechanism, in one read of `rm006.sc`.** The cat and the rat are placed only while
`(and (or (has: 8) (has: 16)) (not (proc0_12 83)))`; `rm006::doit` sets flag 83 the moment the
chase STARTS — not when it is won — and the throws that bank `put: <item> 6` all sit inside it.
There is a second closer: lose the race and `catAndMouse` state 1 sets `local0`, after which
every throw answers "too late" (`proc0_29 215`). Both are one-way.

**`missability.window_closures`.** For each `ownedby_death_folds` demand, collect the producers of
any member of its group and ask whether some reachable register flip kills *all* of them while the
room that reads the demand is still ahead.

The conjunct that makes it work — and the one a room-reachability test structurally cannot supply
— is **producer liveness**. rm6 stays walkable for the whole game; what stops being possible is
the throw. So each producer is read through `guard_reqs` against the register being flipped: a
site whose own guard needs that register to be anything but `w` is dead in the post-flip world,
and a row needs EVERY producer dead. One survivor and there is no closure, which is what keeps
this from firing on ordinary plot advances. The remaining three conjuncts are
`register_strandings`' own, unchanged in meaning: the flip must be reachable (`_flip_seeds`), the
pre-flip player must have been able to do what the post-flip one cannot (causality), and the goal
must still be reachable (else it is a dead end, a different finding).

Measured: **4 rows, one per pool member**, `need_room` 86, `closes_on [(485, 1), (565, 1)]` —
flag 83 and rm6's `local0`.

**⚠️ It needed a second derivation to see anything at all: `extract.feature_adders`.** Three of
the seven `put: <item> 6` sites live on `catStrip`, which never appears in an `init:` — it joins
the cast through `(gGame setFeatures: catStrip)` inside the chase's own state 0. Read without that
cast event those three carry none of the scene's arming, three producers look alive at flag 83 = 1,
and there is no closure to find. `setFeatures` is derived off the class table in three structural
steps (a class that forwards `handleEvent:` to the elements of a collection → the globals holding
an instance of one → any method that `add:`s a parameter to such a holder), the same discipline as
`init_selectors`. Corpus: KQ5 89 call sites, QFG-VGA 26, KQ4 derives the selector with ZERO sites,
LSL2/KQ6/LB2 derive none (SCI1.1 uses `addToPic`, already read). Byte-identical everywhere.

**⛔ The bees are NOT this build.** Row 15's closure is a different axis: flag 36's only producer
is `bearScript`, armed under `own(5)`, so what closes that window is an ITEM being spent
elsewhere, not a register flipping. It pairs with row 9 (the fortune teller's slot), and a
prototype of that pairing re-created the Shoe@rm12 false positive this oracle just retired — see
§1's verdicts. Left red on purpose.
