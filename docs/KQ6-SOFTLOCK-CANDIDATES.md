# KQ6 softlock candidates — consolidated, with verdicts

Sources: the user's manual notes (2026-07-24 and 2026-07-26), the Steam Full-Game walkthrough
(231/231, **long path**), the-spoiler.com / gamerwalkthroughs, and our extraction at `1f6e33a`.
Where they disagree the user wins, then the walkthrough, then the model.

**The rule**: a candidate is REAL iff, once you cross the boundary, something you still need has
become unobtainable. The four boundaries: **B1** enter the catacombs (no exit until the minotaur
dies) · **B2** catacombs upper→lower (hard one-way) · **B3** the Realm of the Dead (one visit) ·
**B4** the castle (terminal).

## The verdicts

| candidate | where it binds | real? | model | why |
|---|---|---|---|---|
| **tinderbox** | B1 carry-IN | **YES** | ✗ MISS | requirement IS captured (rm406, lower catacombs — "you'll fall, light it") but the item has **no source**: it is a pawn-shop TRADE, handed over by an `owner:` write rather than `get:` |
| **teacup** | B3 carry-IN / water carry-OUT | **YES** (long path) | ✗ MISS | **B3 is unmodelled** — the realm's one-visit flag-15 seal is not attached, so you appear able to go back for it |
| **mirror** | B3 carry-IN | **YES** | ✗ MISS | same — B3 unmodelled. Without it the Lord of the Dead kills you and the realm has no other non-death exit |
| **handkerchief** | B3 → B4 carry-OUT | **YES** | ✓ **CAUGHT** | caught via B4 (castle terminal), not B3. ⚠ its recorded use is rm230/rm407, which looks wrong — right answer, possibly wrong reason |
| **dagger** | B1 → B4 carry-OUT | **YES** | ✓ **CAUGHT** | Lady Celeste's, from the lair; required rm850 (Cassima). Attribution correct |
| **vizier's letter** | inside B4 | **no, as an item** | ✓ correct to skip | obtained *and* used inside the castle (rm781→rm850). The real lock is the **skeletonKey** needed to open the chest — which we DO catch |
| **befriending Jollo** | inside B4 | **YES, indirectly** | ✓ **CAUGHT** as `huntersLamp` | Jollo wants the *new* lamp, which you get by trading the **old lamp** to the beggar outside. We flag the old lamp |
| **nightingale** | B4 carry-IN (short) | **YES** (short path) | ✗ MISS | **no source** — pawn-shop trade, same cause as the tinderbox |
| **peppermint leaf** | B4 carry-IN (short) | **uncertain** | ✗ not flagged | source rm390 (Sacred Mtn cave). Real only if rm390 stops being reachable after the catacombs; needs a check |
| **4 island treasures** | best ending | **not by our rule** | — | they gate the BEST ending, not winnability. Our goal is the ending (rm94), so missing them is not a softlock unless you want "best ending" as the goal |
| **skull** | B2 carry-down | **YES** | ✗ MISS | source rm415 (upper catacombs) ✓ but its real use — filling with amber at the Isle of Mists — is not captured, so nothing demands it |
| **shield** | B2 carry-down → B1 out | **YES** | ✓ **CAUGHT** | upper catacombs → the archer at rm510. Clean |
| **old coins** | B2 carry-down → B3 | **YES** | ✓ **CAUGHT** | upper catacombs → Charon. ⚠ recorded use is rm800/rm870 (castle), which looks wrong |
| **mint** | B4 carry-IN | **YES** (user) | ✓ **CAUGHT** | needed inside the castle at the end — user-confirmed 2026-07-26 |
| **old lamp** | many uses, traded away | **likely** | ✓ CAUGHT | baby tears, fountain water, sacred water, then traded to the beggar |
| **coal** | → egg → reach B3 | **likely** | ✓ CAUGHT | coal→White Queen→spoiled egg→the skull concoction that reaches the realm. Unconfirmed |
| **clothes** | B4 entry (short) | **NO** | ✓ correct to skip | user 2026-07-26: only needed *outside*, to get in. Beauty gives them (rm540); worn at rm220 → rm730 |
| **brick, hole-in-the-wall, red scarf** | B1 carry-IN | **YES** | ✗ MISS | sources fine, but their uses record as rm370 rather than inside the catacombs, so no boundary demands them |

## Score

**Real softlocks identified: 14.** We currently catch **7** of them — dagger, shield, old coins,
handkerchief, skeletonKey, mint, old lamp (+ coal, likely). We miss **7**: tinderbox, teacup,
mirror, nightingale, skull, brick, hole-in-the-wall, red scarf.

## The misses have exactly three causes

1. **No source for pawn-shop trades** — tinderbox, nightingale (also brush). The shop hands an item
   over with an `owner:` WRITE, not `get:`; we model the location store's read side only. One fix,
   three items, and it is the last of the oracle's original four root causes still open.
2. **B3 (the realm's one-visit seal) is unmodelled** — teacup, mirror. Flag 15 is set on arrival at
   rm600 and never cleared, and the rm340 entry tests `not flag 15`. The realm's carry-OUTs
   (handkerchief, skeletonKey) are caught anyway because B4 does the work; only the carry-INs need
   B3 itself.
3. **The use is recorded in the wrong room** — skull (real use: Isle of Mists), brick /
   hole-in-the-wall / scarf (real use: inside the catacombs), and the two suspicious attributions
   flagged above. These all land on rm370, which is the room whose machine *arms* the catacombs
   sequence — so a use inside the armed cutscene is being credited to the arming room.

That third one is a single mechanism too, and it would fix four items plus repair two we currently
get for the wrong reason.
