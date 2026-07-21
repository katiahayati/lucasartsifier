# LSL2 softlock patch — test plan

**Install:** `cp build/patch/script.* <copy-of-game>/`  ·  **Revert:** delete those files.
7 files: `script.026 038 057 063 079 081 600`.

## Item numbers

| # | item | # | item | # | item |
|---|---|---|---|---|---|
| 5 | Swimsuit | 14 | Wig | 26 | Pamphlet |
| 8 | Grotesque_Gulp | 15 | Bikini_Top | 27 | Airsick_Bag |
| 9 | Sunscreen | 21 | Hair_Rejuvenator | 30 | Ashes |
| 11 | Fruit | 24 | Parachute | 31 | Sand |
| 12 | Sewing_Kit | 25 | Bobby_Pin | | |
| 13 | **Spinach_Dip** (must NOT be carried) | | | | |

## A. Guards — must REFUSE when an item is missing

Refusal is the game's own "you don't have that" (`proc0_20`). **Nothing should hang or animate
before the refusal** — that's the specific bug this placement avoids.

| script | at | leaving to | requires | trigger action |
|---|---|---|---|---|
| 026 | rm26 | rm27 | 5, 8, 9 | boarding the cruise ship |
| 038 | rm38 | rm131 | 11, 12, 14, 15 **and NOT 13** | leaving for the ship's end sequence |
| 057 | rm57 | rm58 | 21, 24, 25, 26 | **give ticket to agent** |
| 063 | rm63 | rm64 | 27 | pull cord / jump |
| 079 | rm79 | rm80 | 30 **or** 31 | `throw vine` across the chasm |

**A1 (the flagship):** rm57, holding ticket but **drop 26 (Pamphlet)** → give ticket → must refuse.
**A2 (disjunction):** rm79 with **31 only** → must ALLOW. With **30 only** → must ALLOW.
With neither → must refuse. *(If it demands both, the OR broke.)*
**A3 (prohibition):** rm38 holding **13** plus 11/12/14/15 → must refuse. Ditch the dip
(`throw bread overboard`, +2 points) → must now allow.

## B. Sinks — the item must SURVIVE the action

| script | room | type | item | expected |
|---|---|---|---|---|
| 063 | rm63 | `pour rejuvenator on bolt` | 21 | message + −5 points, **still have 21** |
| 081 | rm81 | `drop rejuvenator` | 21 | message + −5 points, **still have 21** |
| 600 | rm61/62/63 | `barf` (or `use bag`) | 27 | message + −2 points, **still have 27** |

Check inventory after each. Before the patch, the item vanished.

## C. Regression — the patch must not brick normal play (MOST IMPORTANT)

A guard that always refuses is worse than the bug. With the **correct** items held, every
transition in table A must still work normally:

- rm26→27 holding 5, 8, 9
- rm38→131 holding 11, 12, 14, 15 and **not** 13
- rm57→58 holding 21, 24, 25, 26
- rm63→64 holding 27
- rm79→80 holding 30 or 31

Also: rm82 (volcano) must still accept the bomb — items **19 + 21 + 27**. This is the payoff for
the three sink fixes; all three items previously had a way to be destroyed en route.

## D. Smoke

Boot, load a save, walk around, save/restore. Any script error on entering
**26, 38, 57, 63, 79, 81, 61/62/63** points at the patch for that room — revert just that
`script.NNN` to isolate.

---
Not yet executed by anyone. Structural verification so far: 117/118 scripts compile, patch headers
`82 00`, each sink exactly −12 bytes vs an unpatched control build, and the analysis says these
guards close every detected softlock while creating none.
