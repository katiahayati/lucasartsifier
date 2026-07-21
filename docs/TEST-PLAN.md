# LSL2 softlock patch — test plan

**Install:** `cp build/patch/script.* <copy-of-game>/`  ·  **Revert:** delete those files.
8 files: `script.026 038 047 057 063 079 081 600`.  Regenerate: `python -m patcher`.

## Item numbers

| # | item | # | item | # | item |
|---|---|---|---|---|---|
| 1 | Dollar_Bill | 11 | Fruit | 22 | Suitcase |
| 2 | Lottery_Ticket | 12 | Sewing_Kit | 23 | Airline_Ticket |
| 3 | Cruise_Ticket | 13 | **Spinach_Dip** (must NOT carry) | 24 | Parachute |
| 4 | Million_Dollar_Bill | 14 | Wig | 25 | Bobby_Pin |
| 5 | Swimsuit | 15 | Bikini_Top | 26 | Pamphlet |
| 6 | Wad_O_Dough | 16 | Bikini_Bottom | 27 | Airsick_Bag |
| 7 | Passport | 17 | Knife | 28 | Stout_Stick |
| 8 | Grotesque_Gulp | 18 | Soap | 29 | Vine |
| 9 | Sunscreen | 19 | Matches | 30 | Ashes |
| 10 | Onklunk | 20 | Flower | 31 | Sand |

## Getting around

`praise lord` toggles debug mode — **then change rooms once** for the console to attach.

| command | effect |
|---|---|
| `tp` | "Teleport to:" prompt, any room number |
| `get <noun>` | gives the item |
| `pitch <noun>` | **destroys** it — use this to set up a refusal test |

**Ship at rm26** needs items **3 + 10** held *before* entry (checked in `rm26.init`; otherwise you
get the empty-dock picture).

**⚠ Turn debug OFF before any rm82 test** — `rm82.sc:83` hands you items **27, 21, 19** whenever
`global100` is set, silently masking whether the sink fixes worked.

---

## A. Guards — must REFUSE when an item is missing

Refusal is `NotNow` → **"Not now!"**. Nothing should animate or score before it.

| # | room | → | required items | trigger action | status |
|---|---|---|---|---|---|
| A1 | rm26 | 27 | **5** Swimsuit, **8** Gulp, **9** Sunscreen | board the ship | ✅ |
| A2 | rm38 | 131 | **11** Fruit, **12** Kit, **14** Wig, **15** Bikini_Top, **and NOT 13** | leave for the end sequence | ✅ |
| A3 | rm47 | 48 | **17** Knife, **19** Matches, **20** Flower | walk EAST off-screen | ⬜ **untested** |
| A4 | rm57 | 58 | **21** Rejuvenator, **24** Chute, **25** Pin, **26** Pamphlet | give ticket to agent | ✅ |
| A5 | rm63 | 64 | **27** Airsick_Bag | pull cord / jump | ✅ |
| A6 | rm79 | 80 | **30** Ashes **OR** **31** Sand | `throw vine` across chasm | ✅ |

**A3 is new and never played — and it is a SILENT WALL, not a message.** rm47's exit is a room
property (`east 48`), so the patch does `(global2 east: 0)` at room init, the idiom rm15/rm42/rm74/
rm77 already use. Lacking 17/19/20, walking east should simply do nothing; with all three it should
work normally. Re-checked on every entry, so `pitch` an item, leave, come back to re-test.

**A6 disjunction** — **31** only → allow. **30** only → allow. Neither → refuse.
*(If it demands both, the OR broke.)*

**A2 prohibition** — holding **13** plus 11/12/14/15 → refuse. `throw bread overboard` (+2) → allows.

## B. Sinks — the item must SURVIVE

Each prints its original message, then **"Just kidding! You hold on to it because you still need it."**

| # | room(s) | type this | item | status |
|---|---|---|---|---|
| B1 | rm63 | `pour rejuvenator on bolt` | **21** | ⬜ re-test (wording fixed) |
| B2 | rm81 | `drop rejuvenator` | **21** | ⬜ re-test (wording fixed) |
| B3 | rm61 / 62 / 63 | `barf` (or `use bag`) | **27** | ⬜ re-test (wording fixed) |

Check inventory after each. The score penalty (−5 / −5 / −2) still applies — you did do the silly thing.

## C. Regression — must not brick normal play (MOST IMPORTANT)

A guard that always refuses is worse than the bug. Holding the **correct** items, every row in A
must still work normally:

| # | check |
|---|---|
| C1 | rm26→27 with 5, 8, 9 |
| C2 | rm38→131 with 11, 12, 14, 15 and **not** 13 |
| C3 | rm47→48 with 17, 19, 20 — walk east, must pass |
| C4 | rm57→58 with 21, 24, 25, 26 |
| C5 | rm63→64 with 27 |
| C6 | rm79→80 with 30 or 31 |
| **C7** | **rm82 volcano still accepts the bomb: 19 + 21 + 27, debug OFF** — the payoff for B1–B3 |

## D. Smoke

Boot, load, walk, save/restore. A script error entering **26, 38, 47, 57, 63, 79, 81, 61/62/63**
points at that room's patch — revert just that `script.NNN` to isolate.

---

### Status
A1, A2, A4, A5, A6 confirmed in live play. Outstanding: **A3** (new silent wall), **B1–B3**
(re-test after the wording fix), and all of **C**.

Two defects were found by playing, both fixed: the refusal said "You don't have it." while the
player held the item (→ `NotNow` = `proc0_15` = msg 134), and the sink remedy left the game claiming
a still-held item was gone (→ the "Just kidding!" retraction, since "you thought better of it"
cannot honestly follow "you carefully pour your bottle on the padlock").

### Reference: refusal messages (script 0, `proc0_N` → message N+119)
| proc | text |
|---|---|
| proc0_15 | **Not now!** ← used by our guards |
| proc0_16 | You're not close enough. |
| proc0_17 | You already took it. |
| proc0_19 | You can't do that here; at least, not now. |
| proc0_20 | You don't have it. |
