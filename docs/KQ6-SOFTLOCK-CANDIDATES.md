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
| **tinderbox** | B1 carry-IN | **YES** | ✗ MISS | required, judged reachable — src rm280, needed rm340/370/390/406. (The old "no source" note is FIXED: the pawn-shop `owner:` trade now resolves.) |
| **teacup** | B3 carry-IN / water carry-OUT | **YES** (long path) | ✗ MISS | required, judged reachable — src rm470/480, needed rm230/340/470/660 |
| **mirror** | B3 carry-IN | **YES** | ✗ MISS | required, judged reachable — src rm540/605/740, needed rm280/340/690/740 |
| **handkerchief** | B3 → B4 carry-OUT | **YES** | ✗ MISS | **not required** — src rm630, no use captured at all. The one miss that is NOT the reachability shape; see task #8 |
| **dagger** | B1 → B4 carry-OUT | **YES** | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm440/470, needed rm800 |
| **vizier's letter** | inside B4 | **no, as an item** | ✓ correct to skip | the real lock is the **skeletonKey**, and that IS caught (frontier rm155→rm200 …, src rm640, needed rm820) |
| **befriending Jollo** | inside B4 | **YES, indirectly** | ✗ MISS | `huntersLamp` is required, judged reachable — src rm470/520, needed rm230/480/540/580. Previously recorded as caught; it is not |
| **nightingale** | B4 carry-IN (short) | **YES** (short path) | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm280, needed rm850. The pawn-shop source now resolves |
| **peppermint leaf** | B4 carry-IN (short) | **uncertain** | ✗ MISS | required, judged reachable — src rm390/740/750, needed rm280/340/510/750 |
| **4 island treasures** | best ending | **not by our rule** | — | they gate the BEST ending, not winnability |
| **skull** | B2 carry-down | **YES** | ✗ MISS | required, judged reachable — src rm415/470, needed rm340/420/580. (The old "nothing demands it" note is FIXED: it has uses now.) |
| **shield** | B2 carry-down → B1 out | **YES** | ✓ **CAUGHT** | src rm408, needed rm510 |
| **old coins** | B2 carry-down → B3 | **YES** | ✓ **CAUGHT** as `deadMansCoin` | frontier rm340→rm155; src rm430/605, needed rm660 (Charon). The old "recorded use rm800/rm870 looks wrong" worry is RESOLVED |
| **mint** | B4 carry-IN | **YES** (user) | ✓ **CAUGHT** | frontier rm220→rm730 / rm230→rm710; src rm280, needed rm750 |
| **old lamp** | many uses, traded away | **likely** | ✗ MISS | same item as the Jollo row (`huntersLamp`) — required, judged reachable |
| **coal** | → egg → reach B3 | **likely** | ✗ MISS | required, judged reachable — src rm490/560, needed rm490 |
| **clothes** | B4 entry (short) | **NO** | ✓ correct to skip | only needed outside the castle, to get in |
| **red scarf** | B1 carry-IN | **YES** | ✓ **CAUGHT** | frontier rm340→rm370/405/440; src rm490, needed rm370/440 |
| **brick** | B1 carry-IN | **YES** | ✗ MISS | required, judged reachable — src rm510, needed rm370/420 |
| **hole-in-the-wall** | B1 carry-IN | **YES** | ✗ MISS | required, judged reachable — src rm230/400/405/…, needed rm230/370/407 |

**Tally: 7 caught, 10 missed, 3 correctly skipped.** The old table read "7 of 14" because it merged
brick / hole-in-the-wall / red scarf into ONE row and filed `skeletonKey` under the vizier's letter.
Splitting them changes the denominator, not the numerator -- the seven caught items are the same
seven the tool prints. Denominator moved deliberately and is called out here rather than quietly.

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

**Real softlocks identified: 14.** We catch **7** — dagger, shield, old coins, handkerchief,
skeletonKey, mint, old lamp (+ coal, likely). We miss **7**: teacup, mirror, nightingale, skull,
and the catacombs carry-IN four (tinderbox, brick, hole-in-the-wall, red scarf).

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
