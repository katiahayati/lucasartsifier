# KQ6 softlock candidates — consolidated, with verdicts

Sources: the user's manual notes (2026-07-24 and 2026-07-26), the Steam Full-Game walkthrough
(231/231, **long path**), the-spoiler.com / gamerwalkthroughs, and our extraction (model column re-derived at `f8145ae`, 2026-07-27).
Where they disagree the user wins, then the walkthrough, then the model.

**The rule**: a candidate is REAL iff, once you cross the boundary, something you still need has
become unobtainable. The four boundaries: **B1** enter the catacombs (no exit until the minotaur
dies) · **B2** catacombs upper→lower (hard one-way) · **B3** the Realm of the Dead (one visit) ·
**B4** the castle (terminal).

## The verdicts

**Model column re-derived 2026-07-27 against the live run** (`f8145ae`). The previous column was
written at `1f6e33a`, BEFORE the two systemic item-numbering fixes, and had drifted badly: it
claimed handkerchief / old lamp / coal were caught (they are not) and that nightingale and scarf
were missed (they are). Treat the "real?" column as the oracle -- it is user- and
walkthrough-derived and did not move -- and this column as a measurement with a date on it.

Every row now carries the item's ACTUAL extracted state, one of:
`FLAGGED` · `required, judged reachable` (we know the item, its source and its use -- we simply
believe you can go back) · `not required` · `no source`.

| candidate | where it binds | real? | model (2026-07-27) | state |
|---|---|---|---|---|
| **tinderbox** | B1 carry-IN | **YES** | ✓ **CAUGHT 2026-07-28** | frontier rm340→rm370/405/440; src rm280, needed rm340/370/390/406. The dark room is the only descent, and the death there is cancelled only by lighting it |
| **teacup** | B3 carry-IN / water carry-OUT | **YES** (long path) | ✗ MISS | required, judged reachable — src rm470/480, needed rm230/340/470/660 |
| **mirror** | B3 carry-IN | **YES** | ✓ **CAUGHT 2026-07-27** | frontier rm155→rm600 / rm680→rm690 (the realm entry, and the step into the Lord's chamber); src rm540/605/740, needed rm690 |
| **handkerchief** | B3 → B4 carry-OUT | **YES** | ✗ MISS | **not required** — src rm630, no use captured at all. The one miss that is NOT the reachability shape; see task #8 |
| **dagger** | B1 → B4 carry-OUT | **YES** | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm440/470, needed rm800 |
| **vizier's letter** | inside B4 | **no, as an item** | ✓ correct to skip | the real lock is the **skeletonKey**, and that IS caught (frontier rm155→rm200 …, src rm640, needed rm820) |
| **befriending Jollo** | inside B4 | **YES, indirectly** | ✗ MISS | `huntersLamp` is required, judged reachable — src rm470/520, needed rm230/480/540/580. Previously recorded as caught; it is not |
| **nightingale** | B4 carry-IN (short) | **YES** (short path) | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm280, needed rm850. The pawn-shop source now resolves |
| **peppermint leaf** | B4 carry-IN (short) | **uncertain** | ✗ MISS | required, judged reachable — src rm390/740/750, needed rm280/340/510/750 |
| **4 island treasures** | best ending | **not by our rule** | — | they gate the BEST ending, not winnability |
| **skull** | B2 carry-down | **YES** | ✗ MISS | required, judged reachable — src rm415/470, needed rm340/420/580. (The old "nothing demands it" note is FIXED: it has uses now.) |
| **shield** | B2 carry-down → B1 out | **NO** — user-corrected 2026-07-27 | ✓ **correct to skip** | src rm408 (UPPER catacombs), needed rm510. Both rm340 entrances reopen once the minotaur is dead, so it is re-obtainable; see "the shield" below |
| **old coins** | B2 carry-down → B3 | **YES** | ✓ **CAUGHT** as `deadMansCoin` | frontier **rm155→rm600 / rm670→rm660** (the realm entry and Charon's toll — was rm340→rm155); src rm430/605, needed rm660 |
| **mint** | B4 carry-IN | **YES** (user) | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm280, needed rm750 |
| **old lamp** | many uses, traded away | **likely** | ✗ MISS | same item as the Jollo row (`huntersLamp`) — required, judged reachable |
| **coal** | → egg → reach B3 | **likely** | ✗ MISS | required, judged reachable — src rm490/560, needed rm490 |
| **clothes** | B4 entry (short) | **NO** | ✓ correct to skip | only needed outside the castle, to get in |
| **red scarf** | B1 carry-IN | **YES** | ✓ **CAUGHT** | frontier rm340→rm370/405/440; src rm490, needed rm370/440 |
| **brick** | B1 carry-IN | **YES** | ✓ **CAUGHT 2026-07-28** | frontier = every way into rm420 (the crushing ceiling, a cut vertex on the only descent); src rm510, needed rm370/420 |
| **hole-in-the-wall** | B1 carry-IN | **YES** | ✓ **CAUGHT 2026-07-28** | frontier rm340→rm370/405/440; src **rm480 only** — the sixteen maze "sources" were take-backs of a hole you put up yourself |

**⭐ TALLY AS OF `c340e1a` (2026-07-28): 10 caught of 15 real, 5 missed, 5 correctly skipped.**
`brick, dagger, deadMansCoin, holeInTheWall, mint, mirror, nightingale, scarf, skeletonKey,
tinderBox`. The **entire B1 carry-IN class is now closed** — all four items you must bring into the
catacombs strand at the entrance (the brick at the crusher, which is a cut vertex on the way in).
Still missed: `teacup, handkerchief, huntersLamp/old lamp, skull, peppermint` — each root-caused in
the next section. **`coal` left the denominator**: it buys the egg, and it is the egg that crosses
into the Realm. Mechanisms in `KQ6-CATACOMBS-PLAN.md`; pinned by `src/test_kq6_ground_truth.py`,
which is where this table's verdicts are now enforced rather than merely recorded.

The per-row "model" column above is a MEASUREMENT dated 2026-07-27 and is now stale for the six
rows that moved; the tally and the root-cause section below are the live reading.

**Tally (2026-07-27, superseded): 7 caught, 10 missed, 3 correctly skipped.** The old table read "7 of 14" because it merged
brick / hole-in-the-wall / red scarf into ONE row and filed `skeletonKey` under the vizier's letter.
Splitting them changes the denominator, not the numerator -- the seven caught items are the same
seven the tool prints. Denominator moved deliberately and is called out here rather than quietly.

**As of `6e31547` (2026-07-27, later the same day) it is 7 caught of 13 real, 6 missed, 4 correctly
skipped** — the seven the tool prints (`dagger, deadMansCoin, mint, mirror, nightingale, scarf,
skeletonKey`). Both ends of that moved for the right reason, each confirmed in-game by the user:
the **mirror** was ADDED (rm690 takes the walk icon away, so you cannot leave the Lord of the Dead
without holding it up), and the **shield** was REMOVED and the oracle's own verdict corrected —
it is re-obtainable, so the denominator drops 14 → 13 and the shield joins the "correctly skipped"
column. Two of the seven are also caught for better reasons than before: `deadMansCoin`'s frontier
is now the realm entry and Charon's toll rather than the transit room, and `skeletonKey` is
additionally reported as

    toll skeletonKey behind flag187 at rm[340,155]
         pocket=[155,600,630,640,650,660,670,680,690]

which is the Realm of the Dead, named as a region, for the right reason: flag 15 is set on arrival
at rm600 and the entry demands it clear.

## ⭐ UPDATE 2026-07-28 (`43f1944`): 11 CAUGHT — handkerchief in, and the lamp is CONFIRMED REAL

**handkerchief CAUGHT and promoted** (user sign-off). Cause (B) below was right: `opmodel` was
missing `extract`'s fourth script scope. Fixed by counting `init:` on a cross-script object as a
home, not only `setScript:` — `enterDungeon.changeState` sends `init:` to `(ScriptID 822 boyGhost)`,
and script 822 holds the handkerchief's only use. 183 of KQ6's 341 scripts had no home; now 174.
The same rule was in two places: the MACHINE pass used `armed_rooms`, the HANDLER pass did not.

**⚠️ USER RULING — the lamp trade is ONE-WAY, and I nearly mis-generalised it.**
*"you cannot trade it again because the peddler leaves. this is not the pawn shop, it's the lamp
peddler."* The PAWN SHOP (rm280, script 283) is a generic re-tradeable exchange over
`[48 3 14 27]` — which is why the NIGHTINGALE is safe. The LAMP PEDDLER is a different NPC in a
different room and the lamp is not in that table. Verified:

    rm240.sc:112         (if (and ... (not (proc913_0 12))) ((ScriptID 241 0) init:))
    lampTradeScr.sc:192  (proc913_1 12)      ; one writer, never cleared -- he is gone

So **huntersLamp is a real softlock of the DANGEROUS-ACTION class**, not a boundary crossing.

**Why it still misses**, measured: `rm520.init` casts `theHuntersLamp` only under
`((gInv at: 19) owner:) == gCurRoomNum`, and `getLamp` has TWO entries — the LOC-gated doVerb, and
rm520's `doit` gated on `local1`. The second is SCI's APPROACH IDIOM (doVerb sets `local1` and
starts the ego walking; `doit` fires on arrival), i.e. a CONTINUATION of the same action, exactly
what `_drop_continuation_entries` says about a `cue`. Needs two stacked rules, both general, both
touching machine entries: (a) a handler effect inherits the CAST condition of the object whose
method it is in; (b) an entry gated on a room local inherits the condition of whoever writes it.

## THE FIVE REMAINING MISSES, ROOT-CAUSED 2026-07-28 (`c340e1a`) — 4 of them still open

Every one was checked against the scripts and against `docs/KQ6-ITEM-ORACLE.md`, item by item, to
answer "is this actually a miss?". **All five are real misses**, `coal` was NOT and has been
demoted, and the causes reduce to three mechanisms — none of which is the detector being wrong
about reachability.

| item | where you get it (verified) | where you use it (verified) | cause of the miss |
|---|---|---|---|
| **peppermint** | rm390 `getLeaf`, Sacred Mountain cave | rm270 clown · rm510 the genie eats it · rm750 give-genie; destroyed at rm510/rm750 | **(A) phantom debug sources.** Kill them and it is CAUGHT at `rm220->rm730 / rm230->rm710`, the B4 boundary the oracle predicted |
| **handkerchief** | rm630, inside the Realm | `boyGhostScript.sc:75/93 has: 17`, `:484 put: 17 820` | **(B) script scope.** `required[17]` is EMPTY — we capture no use at all |
| **huntersLamp** | rm520 `getLamp` | rm230 spellBook · rm580 makeRain; **traded away** at `lampTradeScr.sc:404 (global0 put: 19)` — no destination, i.e. destroyed | **(B) script scope**, on the LOSS rather than the use: `drops[19]` is empty, so nothing can strand |
| **skull** | rm415 `getSkull`, upper catacombs | rm280 · rm420 `throwSkull` (which SPENDS it: `put: 11 global11`) · rm580 `getEmbers`, itself gated on a BIT in the skull's own `state:` | **(C) judged reachable**, plus a dangerous-ACTION shape: throwing the skull at the crusher instead of using the brick spends the vessel the oracle needs for B3 |
| **teaCup** | rm480 `getBottle` (script 483) | **rm660 `riverStyx::doVerb 44 -> getWaterScr`** (Styx water, inside the Realm) · rm230 magic-paint chain · rm470 | **(C) judged reachable.** Sources clean up under (A) but the Realm seal still does not bite for it |
| ~~coal~~ | rm560 `getCoal` | every use at rm490 (knightBlock, coalQueenTalk, coalToQueen, queensLeave) | **NOT A MISS.** Oracle rows 6 and 10: coal buys the spoiled EGG from the White Queen, and it is the EGG that crosses into the Realm. Demoted to CONFIRMED_SAFE |

### (A) KQ6 has a developer cheat we do not recognise

`Main.sc:521` sets `global100` from a file-existence probe for a developer marker:

    (if (FileIO 10 @temp0) (= global100 1) else (= global100 0))

It gates debug key handlers, a memory-fragmentation dialog, and **item hand-outs**. `rm470.sc:117`:

    (if (and global100 (== global12 99) (FileIO 10 {g}))
        (global0 get: 49 get: 46 get: 19 get: 11 get: 8))     ; five items at once

`global12 == 99` is prevRoom == the intro room (`Main::init` ends `(self newRoom: 99)`), so this is
unreachable in play. rm740 and rm750 carry the same shape; rm490 has a `prev == 99` + counter
variant that hands over coal. **`vocab.derive_debug` returns `{}` for KQ6** — it looks for the `^=`
debug-checkbox idiom, and KQ6 uses a FileIO probe. This is exactly the LSL2 rm82 landmine that
`config.debug_globals` exists for.

**Measured experiment (NOT committed):** pinning `global100` as a debug global gives

    softlocks 10 -> 12: + peppermint (correct), + royalRing (a FALSE POSITIVE)
    teaCup [470,480] -> [480]      skull [415,470] -> [415]
    huntersLamp [470,520] -> [520] peppermint [390,740,750] -> [390]

so it is **not a clean win** and must not be landed until the `royalRing` FP is understood. I did
not isolate which effect of the debug gate surfaces the ring — the gate also filters debug-gated
REGISTER writes, not only acquisitions.

**`royalRing` is a false positive, settled two ways.** Oracle row 39: *"safe (reclaimable w/
pearl)"* (row 30: the pearl buys it back from the pawn shop). And the script shows how we are
fooled — `alexWedding.sc` (script 743, the rm740 wedding scene) state 6:

    (cond ((proc999_5 ((global9 at: 39) owner:) 140 210)  (= state 10) (say ... 3 ...))
          ((global0 has: 39)                              (= state 10) (say ... 4 ...))
          (else                                           (say ... 2 1 ...)))

It chooses **which line is spoken**, and the ring being AT rm140 or rm210 (given to the guards, or
to Sing Sing) satisfies it as well as holding it. Both branches continue. `_own_positive` sees the
bare `has: 39` arm and reads a requirement out of a narrative branch.

### (B) `opmodel` is missing `extract`'s FOURTH script scope

`extract.scriptid_refs` walks scripts loaded by `(ScriptID N)`; `opmodel`'s targets are only
region / room / armed-by-proc-call. **132 of KQ6's 341 scripts are walked.** Two of the misses live
in the gap:

* `boyGhostScript` is **script 822**, referenced by `rm820.init` and `enterDungeon.changeState`.
  `extract` reaches it, `opmodel` does not, so its machine is never lifted and the handkerchief's
  only use never becomes a requirement.
* `lampTradeScr` is **script 11**, referenced from **script 241** (`lampSeller.doVerb`) — which is
  itself not a room, so `scriptid_refs` (which scans room scripts and Main only) never even sees
  it. Two hops out, and neither walker arrives.

This is a [[same-rule-two-places]] bug and it is general: every SCI1.1 title keeps real state in
these scripts.

### The guard we emit, and why it is NOT the emergency I first called it

    edge rm220->rm730: (and (gEgo has: 8) (gEgo has: 23) (gEgo has: 27) (gEgo has: 44))
    edge rm230->rm710: (and (gEgo has: 8) (gEgo has: 23) (gEgo has: 27) (gEgo has: 44))

I read this as possibly unsatisfiable — a Realm-only `skeletonKey(44)` conjoined with a
`nightingale(27)` the long path trades away. **⚠️ CORRECTION 2026-07-29: that worry was RIGHT about
the nightingale, and the measurement below is the mistake.** Both halves, re-judged:

* <s>The nightingale is a genuine castle-interior item (`rm850.sc:594 put: 27 850` releases the
  bird; `rm880` branches on whether the guards took it to rm730), and it is **freely
  re-obtainable**: the pawn shop is a generic exchange over a four-item table
  (`counterInset.sc:23` `[local1 21] = [48 3 14 27 ...]`), and `rm280::init` re-inits each shelf
  item whenever the shop owns it. Trade it for the flute, use the flute, trade back.</s>
  **Every fact in that bullet is true and the conclusion does not follow.** I read the four-item
  table as evidence of *freedom* — you can always trade back — and it is the opposite: `itemTradeScr`
  loops over exactly that table and REFUSES to deal while you hold any member
  (`counterInset.sc:236`), so **at most one of `{tinderBox, brush, flute, nightingale}` can be in
  your hands at a time**. The long door demands the `brush`, so it can never demand the bird too:
  `(and (has: 3) (has: 27))` is unsatisfiable, and that guard **walled** the long route.
  This is now derived — `missability.exchange_slots`, applied by `guards.unholdable_at` — and it is
  what closed the last red assertion in `test_kq6_ground_truth.py`.
* The skeletonKey demand is right in kind — **user ruling 2026-07-28**: *"Preventing you from
  leaving the realm without it is the right thing."*

**Lesson.** "The shop re-inits each shelf item whenever it owns it" is a fact about the SHOP's
stock, and I read it as a fact about the PLAYER's inventory. One statement moves one item; a
four-way exchange table is a slot, not a supply.

What IS wrong is **placement**. The model has two distinct castle entrances and they are the game's
two paths — `rm220->rm730` alts `{clothes(5)}` (the disguise) and `rm230->rm710` alts
`{brush(3), teaCup(46)}` (the magic paint) — and we stamp the identical conjunction on both. A
Realm-only literal belongs at the Realm's EXIT (`rm680->rm155`), the last edge where you can still
comply, which is what `guards.py` claims to do. The user has explicitly deprioritised this behind
detection work. See memory `path-forcing-guards`.

### Next moves, in the agreed order
1. **`opmodel`'s fourth script scope** — clean bug, two known payoffs, general across SCI1.1.
2. **Guard placement** — push route-limited literals back to the last compliant edge.
3. **Derive the FileIO-probe debug global** — held until the `royalRing` FP is understood.

## THE REALM IS NOW MODELLED AS A ONE-WAY POCKET (2026-07-27)

All three of its guards were already extracted and none of them reached the model. They do now:

| edge | guard | meaning |
|---|---|---|
| rm155→rm600 | `prev == 340` | you fly to the realm only from the Sacred Mountain |
| rm155→rm200 | `prev != 340` | the same transit room's other destination |
| rm340→rm155 | `flag14 & flag4 & not flag15` | and only once — rm600's init sets flag 15 forever |
| rm680→rm155 | `prev != 670` | **the only way out**, taken only if you re-entered rm680 from rm690 |

`rm690→rm680` is `holdUpMirror`, which needs `own(24)`. So "solve the level or stay" is spelled,
in the game's own scripts, as a previous-room test — which is why modelling `prev` was the unlock.

**✅ RESOLVED 2026-07-27 — the mirror is CAUGHT.** rm690 declared `south 680` and our model walked
it, reaching the escape cutscene having never held up the mirror. **User ruling: "once you're in
front of the lord of the dead you can't walk away."** The game says so in rm690's init —
`(global69 disable: 0)`, and `Main.sc:545` declares `walkIconItem: icon0`, so that is the WALK
icon. A room that takes walking away has no walk-off exits. Exactly one room in eight games loses
an edge to this rule. The teacup is still missed, but its realm use (Styx water, flag 58) is
flavour — see the teaCup red-herring note in [[kq6-softlock-ground-truth]].

## THE SHIELD — NOT a softlock, and the drop was correct

**User ruling 2026-07-27, after testing in ScummVM: "you were completely right and I was completely
wrong. Yes you can go back to either level of the catacombs."** So the shield is re-obtainable and
its disappearance from our findings is a CORRECTION, not a miss. The oracle's "real?" column moves
YES → NO with the user's sign-off.

The two ways back in, both from rm340 and both open once the minotaur is dead (flag 1):
* **colour 4, x≈68..114** (the cave mouth) → `newRoom: 405` — the **UPPER** level, where the shield
  is. Our geometry PREDICTED this becomes walkable at exactly that band when flag 1 is set, and
  that it is unreachable (0 of 948 cells) while the minotaur lives. The prediction was confirmed
  in-game.
* **colour 9, x≈3..49** (far left) → `goToLair` → rm440 — the **LOWER** level; the script gates
  this one itself, `(and (== onControl 512) (proc913_0 1))`.

The guards do not seal anything: rm350's only conditional is flag 2 (a first-visit cutscene that
hides the icon bar), its bottom edge always returns to rm340, and rm340's toss-in
`(and (not (proc913_0 1)) (proc913_0 2))` cannot fire once the minotaur is dead.

**The levels, from the game's own table** (`LBRoom.sc:22`, sign-tagged (room, coord) pairs on a
16-wide grid, `row = coord/16`): UPPER rows 0–7 = rm430(1) rm435(7) rm420(20) **rm408(51)**
rm425(66) rm410(68) rm415(71) rm405(117); LOWER rows 9–11 = rm406(152) rm407(180) rm409(181)
**rm440(182)**. The shield is UPPER; the minotaur is LOWER; the drop between them is one-way — and
`maze_reach` already models that correctly (rm406/rm407 reach only lower rooms). Upper access is
then restored through the SURFACE, `rm440 → rm340 → rm405`, which is exactly what the game does.
**Do not "fix" that edge** — it was briefly on the list to remove and would have been a fabricated
seal.

<details><summary>The three refuted hypotheses, kept so they are not re-tried</summary>

Each was a plausible mechanism, and each was killed by measurement:

1. **`theDoor` as an LSL2-rm82-style prop-gate.** Its cel switches on flag 3 (set at rm380 just
   before `flyToBeach`), so it looked like the entrance sealing behind you. Measured: the control-4
   region is 3,663 px and the door's footprint covers at most 1,484 of them — and covers MORE with
   flag 3 clear (1,484) than set (214). It is also `signal 28688`, which includes
   `kSignalIgnoreActor`, so it never blocked the ego at all.
2. **The entrance closing after the minotaur dies.** Measured the opposite: colour 4 is UNREACHABLE
   while the minotaur lives and WALKABLE once it is dead. (Finding this needed a real `polygons.py`
   fix — `_proc_polygons` was UNIONING a helper's branches, and `proc343_0` IS the flag-1 fork.)
3. **"The upper level is unreachable once you descend."** Refuted by the user's own retest.

</details>

The chain that made the shield look re-obtainable, all of which turned out to be right:

1. rm300 (the Sacred Mountain beach) declares no exits and picks its north in `init`:
   `(if (proc913_0 157) (self north: 340) else (self north: 320))`. We only read the assignment
   spelling of that, not the send spelling, so **rm300 had no way up the mountain at all** and the
   whole cluster hung off the start room. Now it does.
2. rm340→rm405 — the drop into the catacombs — is FREE, and the game does not gate it either:
   `((== (global0 onControl: 1) 16) (global2 newRoom: 405))` in rm340's `doit`. No flag test.
3. So the model walks rm510 → rm520 → rm500 → rm300 → rm340 → rm405 → rm408 and re-collects the
   shield.

**There is no seal — measured, so nobody re-checks:**

* rm405's obstacle polygons keep two layouts differing on flag 1, but what they gate is the way
  OUT: `south` (edgeHit 3, the walk back to rm340) opens only once the minotaur is dead. That is
  B1's "no exit until the minotaur dies", already derived. It says nothing about coming back in.
* `rm405 → rm408` is a free grid edge, correctly — the upper level really is freely walkable once
  you are in it.
* rm340's two layouts differ on flag 1 in the permissive direction: the cave mouth OPENS.

**A note on `onControl` for whoever reads this next.** The re-entry test is
`rm340::doit ((== (gEgo onControl: 1) 16) → newRoom 405)`, and we still render `onControl` OPAQUE,
which is permissive — so this edge reads as free. Here that happens to be the RIGHT answer, but by
luck rather than by modelling, and it remains the **#1 gap in the corpus-wide census**
([[modeling-gap-census]]). What this episode adds is that the geometry needed to decide such a
question now EXISTS: the SCI1.1 resource reader and the control-plane renderer answered "can the
ego stand on colour 4, and when" correctly and in advance of the in-game test. See
`docs/SCI1.1-SEMANTICS.md`.

## THE DIAGNOSIS: NINE OF THE TEN MISSES ARE ONE MECHANISM

This is the useful result of the re-derivation, and it contradicts the old "each remaining miss
needs 2-3 mechanisms STACKED" note.

**Nine of the ten are `required, judged reachable`.** Not one of them is missing an item, a source,
or a use. The whole detection pipeline already works on them; the ONLY thing wrong is that the
movement graph believes you can walk back and re-collect. Ask it for the return path and it prints
one, every time:

    brick    rm370 -> rm510:  rm370->rm300->rm500->rm520->rm510
    skull    rm340 -> rm470:  rm340->rm300->rm450->rm470
    teacup   rm690 -> rm540:  rm690->rm680->rm155->rm200->rm210->rm240->rm250->rm540
    coal     rm490 -> rm560:  rm490->rm480->rm470->rm450->rm550->rm560

### …but "one mechanism" was too clean. Measured 2026-07-27, same day.

The shared STATE is real (nine items, all `required, judged reachable`). The claim that one fix
closes them was an inference from that state, and walking the actual return edges breaks it into
at least two classes:

**Class 1 — a scripted escape whose arming guard we dropped.** `rm370 -> rm300` is the
`flyToBeach` cutscene, and our guard for it is:

    GOr(kids=[None, None])

Two arming sites (`toBeachTXT` and the saved-Celeste cutscene), neither condition modelled. An OR
of two unknowns is unknown, and unknown is permissive, so the escape reads as free. This is a
DROPPED-GUARD bug of the familiar kind, not a new mechanism.

**Class 2 — the return path is genuinely walkable, and the seal is somewhere else entirely.**
`rm510 <-> rm540` and `rm500 -> rm520` are real two-way map connections (`north`/`south` room
properties), and in the real game you CAN walk back from rm370 to fetch the brick — the game
bounces you to the beach precisely so you can. The softlock is that it does so **only once**: the
one-warning gate sets flag 2, and every later arrival at rm340 throws you in with no item check.
That is a one-time EVENT changing a later room's behaviour, not a region that seals room access.

So the brick / hole-in-the-wall / tinderbox class is NOT the same mechanism as LB2's act counter,
and #14 as originally written ("state that seals ROOM ACCESS") only describes part of the problem.
Splitting it is the next step; do not treat the nine as one fix.

⚠️ This paragraph replaced a confident "one mechanism accounts for 19 of the 22 known misses across
both games" written earlier the same day. It was wrong in the same way the column above was wrong —
an inference stated as a measurement. The nine sharing a STATE is measured; the nine sharing a
CAUSE was not.

## THE CAPTURE IS A ONE-WARNING GATE, IN TWO ROOMS (user 2026-07-26, verified)

I first read only rm370 and wrongly concluded the game protects you. It does not -- it gives you
exactly one pass. The mechanism spans TWO rooms, which is why half of it is easy to miss:

**rm370 -- the gate, first visit.** `(proc913_1 2)` sets flag 2 ("caught at the gate") FIRST, then:

    (cond ((and (has: brick) (has: holeInTheWall) (has: tinderBox) (has: scarf))
              (setScript: toLabyrinth))              ; into the catacombs now
          ((== global90 2) (setScript: toBeachCD))
          (else            (setScript: toBeachTXT))) ; one free pass -> the beach

**rm340 -- every later arrival.** `rm340.sc:116`:

    ((and (not (proc913_0 1)) (proc913_0 2))      ; minotaur alive AND you were caught before
        ... (proc342_2))                           ; -> tossEmIn -> newRoom 405

`n342.sc` contains **no `has:` checks whatsoever**. So the second time you set foot on the Sacred
Mountain you are thrown in whatever you are carrying. The item check exists only on the FIRST
visit; flag 2 is set regardless of whether you passed it.

So all four ARE softlocks, and the scarf is the sharpest: without it `scarfOnMino` is never set, the
minotaur never dies, flag 173 is never set, and every one of the three exits we now gate stays
shut. Enter without it and the game is over.

## Score

⚠️ **STALE — this paragraph is the pre-`2f75dff` count and its item list is wrong** (it credits
shield, handkerchief and old lamp as caught; the first was caught until `ca5637e`, the other two
never were). Kept only because the table above records how the denominator moved. **The live score
is the table: 6 caught, 11 missed, 3 correctly skipped, at `ca5637e`.**

<s>**Real softlocks identified: 14.** We catch **7** — dagger, shield, old coins, handkerchief,
skeletonKey, mint, old lamp (+ coal, likely). We miss **7**: teacup, mirror, nightingale, skull,
and the catacombs carry-IN four (tinderbox, brick, hole-in-the-wall, red scarf).</s>

## The misses have exactly three causes

1. **No source for pawn-shop trades** — tinderbox, nightingale (also brush). The shop hands an item
   over with an `owner:` WRITE, not `get:`; we model the location store's read side only. One fix,
   three items, and it is the last of the oracle's original four root causes still open.
2. **B3 (the realm's one-visit seal) is unmodelled** — teacup, mirror. Flag 15 is set on arrival at
   rm600 and never cleared, and the rm340 entry tests `not flag 15`. The realm's carry-OUTs
   (handkerchief, skeletonKey) are caught anyway because B4 does the work; only the carry-INs need
   B3 itself.
3. **The use is recorded in the wrong room** — narrower than first thought, now that rm370 turns
   out to be a real gate rather than a mis-attribution. What remains genuinely suspect: **skull**
   (recorded rm340/rm420; real use is filling it with amber at the Isle of Mists), **handkerchief**
   (recorded rm230/rm407; real use is the castle boy-ghost) and **old coins** (recorded
   rm800/rm870; real use is paying Charon at rm660). The latter two we currently catch for the
   wrong reason, so fixing this both adds skull and makes two existing catches trustworthy.
