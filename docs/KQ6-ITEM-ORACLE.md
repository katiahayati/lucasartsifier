# KQ6 item oracle — source, use, and stranding verdict

**Ground truth** = the Steam "Full Game" walkthrough (231/231, long path):
<https://steamcommunity.com/sharedfiles/filedetails/?id=3624813856>, plus its two catacombs maps.
**Model** = our extraction at commit `c7a98a6`. Item numbers are the inventory-LIST index (what
`get:`/`has:`/`at:` use) — see that commit; the numbers were always right, the names were not.

Not user-confirmed. Where the model and the walkthrough disagree, the walkthrough wins and the
row is flagged **GAP**.

## 1. The irreversible boundaries (what makes anything a stranding)

| # | boundary | shape | modelled? |
|---|---|---|---|
| B1 | **Enter the catacombs** (2nd visit to the Sacred Mountain → captured → thrown in) | can't leave until the minotaur is dead | entry yes, exit gate **no** (`rm440→340` is behind `onControl`) |
| B2 | **Catacombs upper → lower** ("You'll fall") | **hard one-way**, no climb back | **yes** — grid recovered, upper 72 cells / lower 37, no return |
| B3 | **Realm of the Dead** | one visit only (proc913 flag 15 set on arrival) | **no** — entry seal not attached |
| B4 | **Enter the castle** (magic-paint door) | terminal; the islands are gone | **yes** — structural sink |

The catacombs also contain a **pit** (rm411) and the walkthrough's floor trap; both are deaths,
not strandings.

## 2. Every item

Zones: `CROWN` 200–290 · `SACRED` 340–390 · `CAT-L1` 405/408/410/415/420/425/430/435 ·
`CAT-L2` 406/407/409 · `LAIR` 440 · `WONDER` 450–490 · `BEAST` 500–540 · `MISTS` 550–580 ·
`REALM` 600–690 · `CASTLE` 700–880.

| # | item | source (walkthrough) | use (walkthrough) | model src | verdict |
|---|---|---|---|---|---|
| 0 | map | pawn the royal ring (pawn shop) | travel between isles | 280 | required, not strandable (never lost) |
| 1 | boringBook | book shop, small table | on the oyster → pearl | 270 | safe |
| 2 | brick | **BEAST**, north past the gardener | **thrown into the wheels, CAT-L1** | 510 ✓ | **CARRY-IN to B1** |
| 3 | brush | pawn shop (trade tinderbox) | magic paint → castle door | — **GAP: no source** | **CARRY-IN to B4** |
| 4 | hair (black) | touch the ribbon | into the skull with the egg | 0,580 | carry-in to B3 |
| 5 | clothes | guard disguise | worn to pass in the castle | 540 | model says **SOFTLOCK** |
| 6 | coal | **MISTS** | give to the White Queen → egg | 490,560 ✓ | safe |
| 7 | deadMansCoin (old coins) | **CAT-L1** | pay Charon, **REALM** | 430=CAT-L1 ✓ | **STRANDING — B2 carry-down + B1 carry-out.** model ✓ |
| 8 | dagger | **LAIR** (Lady Celeste) | give to Cassima, **CASTLE** 850 | 440=LAIR ✓ | **STRANDING — carry out of B1 into B4.** model ✓ |
| 9 | coin | CROWN beach box | pawn → nightingale + mint | 200 ✓ | safe |
| 10 | egg (spoiled) | White Queen, **WONDER** | into the skull | 490 ✓ | carry-in to B3 |
| 11 | skull | **CAT-L1** | fill with amber at **MISTS**, + egg + hair → reach B3 | 415=CAT-L1 ✓ | **STRANDING — B2 carry-down.** model **MISSES** (its `required` is 340/420, not MISTS) |
| 12 | feather | **SACRED** | on the teacup → magic paint | 300 | carry-in to B4 |
| 13 | flower | SACRED | 1st gnome | 300 ✓ | safe |
| 14 | flute | pawn shop (trade nightingale) | play at the WONDER gate → hole-in-the-wall | 480 | safe (re-tradeable) |
| 15 | gauntlet | **REALM**, dead knight | challenge the Lord of the Dead (inside) | 650 ✓ | used inside — safe |
| 16 | cassimaHair | — | — | 0 | not in walkthrough |
| 17 | handkerchief | **REALM**, ghost woman | give to the boy ghost, **CASTLE** | 630 ✓ | **STRANDING — B3 carry-out.** model **MISSES** (no `required` captured) |
| 18 | holeInTheWall | **WONDER** gate, while the plants dance | placed on the wall, **CAT-L2** (spy room) | 230,407 — **GAP** | **CARRY-IN to B1** |
| 19 | huntersLamp (old lamp) | **BEAST**, boiling pond (needs lettuce) | baby tears, fountain water, sacred water; → beggar for newLamp | 470,520 ✓ | model says **SOFTLOCK** |
| 20 | letter | Alhazred's chest, **CASTLE** (needs skeletonKey) | show Saladin; give Cassima | 781 ✓ | obtained and used inside B4 — safe |
| 21 | lettuce | WONDER (picked up) | thrown in the boiling pond → old lamp | — **GAP: `get:` is in `n483`, a non-room script we never walk** | safe (melts = timer) |
| 22 | milk | WONDER, dogwood tree | to the baby-tears plants | 470,480 ✓ | safe |
| 23 | mint | pawn-shop jar | 3rd gnome; **and needed INSIDE THE CASTLE at the end** (user) | 280 ✓ | **STRANDING — B4 carry-in.** model ✓ |
| 24 | mirror | BEAST | on the Lord of the Dead, **REALM** | 540 ✓ | **CARRY-IN to B3** |
| 25 | newLamp | beggar (trade old lamp) | give to Jollo, **CASTLE** | 750 | **CARRY-IN to B4** |
| 26 | nail | CASTLE | inside | 880 | safe |
| 27 | nightingale | pawn shop (buy w/ coin) | lure Sing Sing; 2nd gnome; trade → flute | — **GAP: no source** | safe |
| 28 | ticket | **REALM**, Queen Allaria | show the skeleton (inside) | 600 ✓ | used inside — safe |
| 29 | participle | BEAST (sentence on the creature) | to the bookworm → rare book | 500 ✓ | safe |
| 30 | pearl | oyster, WONDER | to the pawn shop → reclaim royal ring | 280 | safe |
| 31 | peppermint | **SACRED cave** | *(no use given in this guide)* | 390 ✓ | **verify** |
| 32 | note | Cassima's warning, CROWN | narrative | 210 ✓ | safe |
| 33 | potion | WONDER gate table | drink → fake death (pawn shop) | — **GAP: `get:` is in `n483`** | safe |
| 34 | rabbitFoot | ferryman | 4th gnome | 290 ✓ | safe |
| 35 | ribbon | Sing Sing cut-scene | touch → black hair | 210 ✓ | safe |
| 36 | riddleBook (rare book) | bookworm (give participle) | trade Ali → spellBook | 460 ✓ | safe |
| 37 | ring (Beast's) | BEAST | give to Beauty | 540 ✓ | safe |
| 38 | rose | BEAST garden | to Beauty; to Sing Sing | 510 ✓ | safe (a 2nd rose exists) |
| 39 | royalRing | CROWN beach | guards; Jollo; pawn → map; to Sing Sing | 200 ✓ | safe (reclaimable w/ pearl) |
| 40 | sacredWater | SACRED / Celeste | poured into the old lamp | 380 ✓ | verify |
| 41 | scarf (red) | **WONDER**, the two Queens | shown to the **Minotaur** | 490 ✓ | **CARRY-IN to B1** |
| 42 | scythe | MISTS | clear the path, BEAST | 560 ✓ | safe |
| 43 | shield | **CAT-L1** | vs the archer, **BEAST** 510 | 408=CAT-L1 ✓ | **STRANDING — B2 carry-down + B1 carry-out.** model ✓ |
| 44 | skeletonKey | **REALM**, dancing bones | unlock Alhazred's chest, **CASTLE** 820 | 640 ✓ | **STRANDING — B3 carry-out.** model ✓ |
| 45 | spellBook | Ali (trade rare book) | Make Rain / Magic Paint / Charm | 270 ✓ | **CARRY-IN to B4** |
| 46 | teaCup | WONDER chair | mud; **Styx water (REALM)**; + feather → magic paint | 470 ✓ | **STRANDING — B3 carry-out** (the Styx fill). model **MISSES** |
| 47 | poem | book-shop page | give to Sing Sing | 270 ✓ | safe |
| 48 | tinderBox | pawn shop (trade flute) | light the cave; light after the fall, **CAT-L2** | — **GAP: no source** | **CARRY-IN to B1** |
| 49 | tomato | WONDER | to bump-on-a-log | 470 ✓ | safe |
| 50 | sentence | WONDER sea | on the dangling creature | 450 ✓ | safe |
| 51 | ink | CROWN trash can | 5th gnome | 240 ✓ | safe |

## 3. Strandings, by boundary

**B2 — catacombs upper → lower (the hard one-way).** Obtained on L1, needed after:
**old coins (7)**, **shield (43)**, **skull (11)**. Descend without them and they are gone.
Model catches 7 and 43; **misses 11 (skull)** because its use at the Isle of Mists is not captured.

**B1 — carry INTO the catacombs** (needed inside, obtainable only outside):
**tinderbox (48)** — light after the fall, or the minotaur kills you in the dark;
**brick (2)** — the wheel trap; **hole-in-the-wall (18)** — find the lair;
**red scarf (41)** — defeat the minotaur. Also **carry OUT**: the **dagger (8)** from Lady Celeste.

**B3 — Realm of the Dead (one visit).** Carry IN: **mirror (24)**, black **hair (4)**, **egg (10)**,
**skull (11)**. Carry OUT: **skeleton key (44)** ✓ caught, **handkerchief (17)** ✗ missed,
**teacup + Styx water (46)** ✗ missed.

**B4 — the castle (terminal).** Everything used inside must come in: **brush (3)**, **feather (12)**
+ **teacup (46)** (magic paint), **spellBook (45)**, **newLamp (25)**, **dagger (8)**,
**skeletonKey (44)**, **handkerchief (17)**.

## 4. Model scorecard against this table

**Caught (7):** clothes, dagger, deadMansCoin, huntersLamp, mint, shield, skeletonKey.
**Confirmed correct:** dagger, deadMansCoin, shield, skeletonKey — 4 of the 7 are real
strandings at a real boundary.
**Missed (should fire):** skull (B2), handkerchief (B3), teacup/Styx (B3), and the whole
carry-IN class (tinderbox, brick, hole-in-the-wall, scarf) because B1's exit gate is unmodelled.
**mint is NOT a false positive** (user, 2026-07-25): it is needed inside the castle at the
end, so it is a genuine B4 carry-in and the model is right. My "suspect FP" call was wrong -- I
judged it from the walkthrough's gnome puzzle alone and never checked the endgame.
**Unverified:** clothes, huntersLamp.

**Root causes of the misses, in priority order:**
1. **B1's exit gate** (`rm440→340` needs the minotaur dead) is behind `onControl` → the catacombs
   are not a pocket → no carry-IN stranding can fire. Biggest single win.
2. **Missing sources — TWO distinct mechanisms**, not one (my first grouping was wrong;
   lettuce is not a trade):
   a. **`get:` inside a non-room, non-region script.** `lettuce` and `potion` are picked up in
      `n483`, a helper script we never walk. Same root as the cutscene-script gap, but for
      ACQUISITIONS: `armed_rooms` lifted such scripts' MACHINES and not their handler `get:` sites.
   b. **Acquisition by `owner:` WRITE rather than `get:`.** `tinderBox` has no `get:`/`put:`
      anywhere -- only `owner:` reads -- so the pawn-shop trade hands it over through the
      item-location store's write side, which we do not treat as a source.
3. **Missing uses** — handkerchief and teacup have no `required` at all.
4. **B3's entry seal** (flag 15) unattached → the realm is not one-visit → its carry-outs cannot
   strand except where another boundary does the work (skeletonKey fires via B4).
