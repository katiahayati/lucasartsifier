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

## Getting around: the game's OWN debug mode (no external debugger needed)

Type `praise lord` in the parser -- `Main.sc:1000` XOR-toggles `global100` and every `newRoom`
then enables locale 5 (`rm5.sc`), the debug console:

| command | effect |
|---|---|
| `tp` | "Teleport to:" prompt, any room number |
| `get <noun>` | `moveTo: ego` -- gives the item |
| `pitch <noun>` | `moveTo: -1` -- DESTROYS it (use this to test a refusal) |

`pitch`'s `moveTo: -1` is the same permanent destruction the `ownedBy` analysis flagged, which is
exactly why barfing into the Airsick_Bag was a softlock.

**Making the cruise ship appear at rm26.** `rm26.init` draws pic 126 (ship) only when ego holds
BOTH item 3 (Cruise_Ticket) and item 10 (Onklunk); otherwise pic 26, an empty dock. It is checked
at ROOM INIT, so acquire both BEFORE entering:

    praise lord
    get onklunk
    get ticket
    tp        -> 26

### TRAP: turn debug OFF before testing rm82
`rm82.sc:83` is `(if global100 (global0 get: 27 get: 21 get: 19))` -- debug mode hands you the
Airsick_Bag, Hair_Rejuvenator and Matches for free, silently masking whether the sink fixes
worked. Toggle it off (`praise lord` again) before any volcano test. This global is also why the
analyser filters debug-gated acquisitions; otherwise it would conclude the bomb needs nothing.

## Refusal message

The guards answer with **`NotNow`** = `proc0_15` = script 0 message 134, **"Not now!"**.

In this decompilation Main's procedures are numbered, so the family is `proc0_N` -> message N+119
(dumped from the game's own `text.000`):

| proc | msg | text |
|---|---|---|
| proc0_15 | 134 | **Not now!**  <- the standard refusal |
| proc0_16 | 135 | You're not close enough. |
| proc0_17 | 136 | You already took it. |
| proc0_19 | 138 | You can't do that here; at least, not now. |
| proc0_20 | 139 | You don't have it. |

The first build used `proc0_20`, which **lies**: reported from live play at rm26, "give passport to
man" answered "you don't have it" while the player was holding the passport -- what they lacked was
something else, needed later. A refusal that misdescribes the reason sends the player hunting for
the wrong item. Fixed to `proc0_15`.

## Live results
**All gates confirmed working in the real game** (user play-test, 2026-07-21): rm26 ship, rm38 raft
incl. the Spinach_Dip prohibition, rm57 boarding, rm63 jump, rm79 chasm. Two wording defects were
found and fixed (below); no gate misbehaved.

**rm47 -> rm48 is now guarded too** (Knife/Matches/Flower). It has no `newRoom:` call to wrap --
it is a ROOM-PROPERTY exit (`east 48`), walked off-screen and handled by the engine -- so it uses
the game's own idiom for closing an exit, `(global2 east: 0)` at room init, as rm15/rm42/rm74/rm77
do. Silent by nature: a closed edge behaves as a wall, with no refusal text. Re-evaluated on every
entry, so it opens as soon as the player holds the three items.

### Wording defects found in play (both fixed)
1. Refusal said "You don't have it." while the player WAS holding the item they used -- fixed to
   `NotNow`.
2. The sink remedy deleted the consumption but left the clause's message claiming the item was
   gone: "You carefully pour your bottle ... on the padlock", "You dump the bottle ... on the ice",
   "You do so and immediately discard the now-soiled airsick bag". Since those acts are
   irreversible, no "you thought better of it" retraction is honest; it needs an explicit joke,
   which suits this game: **"Just kidding! You hold on to it because you still need it."**
