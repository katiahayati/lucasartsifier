# KQ6's goal: the credits are not the win

Until now KQ6's goal was **discovered** as `{94, 205}`. Both are terminals you survive, so
`anchors.discover_goal`'s primary rule (terminal + reachable + never fatal) accepted them. Both are
wrong, and the way they are wrong is worse than a miss: **rm94 is satisfied by losing**, so every
"is X still required?" question on this game was being answered against a goal that defeat reaches.

* **rm205** is the sail-home ending, entered once from `rm100.sc:278`.
* **rm94** is the CREDITS. Its only in-edge is `rm740`'s own `cue`, and that `cue` is *ungated*:

      (method (cue)
          (if (== global90 2) (global2 setScript: (ScriptID 52)) else (global2 newRoom: 94)))

  `global90` is the speech/text mode global and script 52 is `sCredits`; both branches are the
  credits, the test only picks talkie vs text. rm740 runs one of three ending scripts and the
  credits follow **any** of them.

| script | file | meaning |
|---|---|---|
| 741 | `earlyGuest` | you arrived before the wedding |
| 742 | `vizierWedding` | the vizier marries Cassima — **you lost** |
| 743 | `alexWedding` | you marry Cassima — **the win** |

## How the win is armed

One test, `rm740.sc:205`:

    (if (== global12 180)            ; global12 is prevRoom
        ...                          ; <- nested developer-cheat Print prompts
        (super init: &rest)
        (proc740_10)
        (self setScript: (ScriptID 743 0))     ; rm740.sc:288  -- alexWedding, THE WIN
    else
        ...
        (if ((ScriptID 80 0) tstFlag: 709 2)
            (self setScript: (ScriptID 742 0)) ; vizierWedding -- you lost
        else
            (self setScript: (ScriptID 741 0)) ; earlyGuest
        ))

An earlier reading called line 288 part of the developer cheat. It is not. The cheat is the block
of `(and global100 (FileIO 10 {g}) (Print ...))` prompts *nested inside* the same branch, and the
`(== global12 99)` menu at `rm740.sc:175` is a separate debug affordance that merely **forces**
`global12` to 180 so a tester can preview the win. Line 288 runs on the plain condition.

## Why the goal can be a room after all

`global12 == 180` means "you came from rm180". Chasing that back:

    rm750  vizier's chamber
      |  vizier doVerb -> (global2 setScript: (ScriptID 755 0))       startFight
      v
    startFight state 40 -> (global2 newRoom: 180)                     startFight.sc:295
      |
    rm180  the kiss cutscene  (sKissStuff, states 0..38)
      |  state 38 -> (global2 newRoom: 740)                           rm180.sc:230
      v
    rm740 with global12 == 180  ->  alexWedding

`newRoom: 180` occurs exactly once game-wide, and rm180's only scripted exit is `newRoom: 740`. So
**reaching rm180 is necessary and sufficient for `alexWedding`**, and the goal is expressible as a
room: `goal_rooms = frozenset({180})` (declared in `config.KQ6`).

This corrects the earlier conclusion that KQ6's win/lose split was "three scripts inside one room"
and therefore inexpressible. It is three scripts inside one room, but the *discriminator* is a
distinct room upstream.

## What the correction bought, measured: nothing yet

Full `snapshot.py KQ6` before and after is byte-identical apart from the `goal_rooms` field itself.
Ten softlock items, one group, the same edge/gate specs and sinks.

The reason is structural and worth stating exactly, because it is the next piece of work.
`goal_reaching_rooms` is a backward walk in the guard-ignoring room graph, and

    |goal_reaching({94, 205})| = 85
    |goal_reaching({180})|     = 83        difference: exactly {94, 205}

because **rm180, rm740, rm750 and rm790 all sit in one 18-room SCC** covering the whole castle
endgame:

    rm740 --(positional, onControl $4000)--> rm790 --> rm750 --(fight)--> rm180 --> rm740

That cycle is genuine, not an extraction artefact: `rm740.sc:363` is the only `newRoom: 790` from
the wedding hall, rm790 is the only way into rm750, and so walking out of the wedding hall is the
**only** route to the vizier's chamber. Cutting the 740->790 edge as an experiment collapses
`goal_reaching({180})` to 3 rooms — which is wrong, not better.

So at room granularity the win and the loss are genuinely the same place, and no room-set goal can
separate them. What separates them is *which script rm740 arms on entry*, which depends on two
pieces of state:

1. **`global12` (prevRoom)** — modelled. `_emeta` already carries `{12: 180}` on the rm180->rm740
   edge and `{12: 730}` on rm730->rm740.
2. **flag 709 bit 2 in bank `(ScriptID 80 0)`** — "the wedding has started", set at
   `rm880.sc:1505`, tested at 60+ sites across rm710/720/730/740/840/850/880. **Not modelled.**
   This is the bit-array flag store, #2 on the modelling-gap census. rm740's positional exit to
   rm790 is additionally guarded by `(cond (script 0) ...)` — it opens only once the room's ending
   script has disposed, and `earlyGuest` disposes while the ending path does not.

The honest statement of the limitation: **the goal is now correct, and the model still cannot use
it**, because the state that makes the goal reachable-or-not is not in the model. Fixing the flag
store is what would make the corrected goal bite, and the payoff would be that
`rm730 -> rm740 with flag 709:2 set` becomes a goal-losing crossing — the real KQ6 endgame
point of no return.

## Deriving it instead of declaring it — `anchors._resolve_pass_through`

The goal is **derived**, not declared. `config.KQ6.goal_rooms` is empty like every other game's.

**Why `discover_goal` used to get it wrong.** Its primary rule — terminal, reachable, never fatal —
is satisfied by rm94, so the `_tests_achievement` fallback (the rule that got KQ4 right) never ran.
And even if it had, it works on ROOMS, and all three of KQ6's endings live in rm740.

**The idea: a terminal you can only arrive at one way is not where the outcome is decided.**

> A terminal with a **single predecessor** tells you nothing its predecessor does not — you cannot
> arrive any other way, so reaching it *is* reaching the predecessor. Where the outcome is really
> decided is a branch, and a branch is **rival machines**: two or more armed in the same room whose
> entry conditions CONTRADICT, so at most one can run. If the achievement test *separates* those
> rivals — some ask what the player is carrying and some do not — it has identified the win, and
> the goal is that machine. If every rival tests achievement, or none does, it has said nothing and
> the terminal stands.

Every clause is structural and each is pinned by its own synthetic case in `test_anchors`:

| clause | what it rules out | pinned by |
|---|---|---|
| single predecessor | a terminal reached two ways is itself a choice | "a terminal with more than one predecessor is untouched" |
| rivals *contradict* | co-existing handlers are not alternatives | "one machine is not a branch, so the terminal stands" |
| the test must *separate* | a signal that fires on everything is not a signal | "rivals that ALL test achievement leave the terminal alone" |
| entry names a room | otherwise there is no room-set goal to return | "a winner not gated on prevRoom is left as-is" |

Applied to the three oracle games:

| game | terminal | predecessor | rivals? | result |
|---|---|---|---|---|
| LSL2 | rm86 | rm178 | one machine, no contradiction | **rm86**, unchanged |
| KQ4 | rm694 | rm693 | one machine (`egoActions`), no contradiction | **rm694**, unchanged |
| KQ6 | rm94 | rm740 | `alexWedding` vs `vizierWedding` | **rm180** |
| KQ6 | rm205 | rm100 | no achievement-testing rival | dropped in favour of rm180 |

**An earlier draft of this rule was overfit and was rewritten.** It said "the predecessor hosts ≥2
machines and *exactly one* tests achievement". Three things were wrong with that, and the user
called it before it was built:

* The "≥2 machines" clause existed to stop KQ4 moving — rm693 *does* have an achievement-testing
  machine — and a clause whose justification is "it protects the answer we already like" is fitted
  to that answer. Replaced by **contradiction**, which is what makes two machines alternatives
  rather than co-residents, and which excludes rm693 for a reason about rm693.
* "*Exactly* one" is a count, and it breaks the moment a game has both a good and a best ending
  (KQ6 nearly does — `alexWedding` branches on flag 15 eleven times). Replaced by "**some** do and
  some do not", which returns a set and degrades gracefully.
* `OWN`-in-guard is not a specific signal — it fires on KQ4's `egoActions`, which is not an ending
  at all. It is only meaningful *between rivals*, which is now the only place it is asked.

**The achievement signal moves from rooms to machines unchanged.** Of the ten machines in rm740,
exactly one has an `OWN` predicate anywhere in its guards or entries:

    script=743  inst='alexWedding'   OWN-in-guard=True     <- (global0 has: 39), the royal ring
    script=742  inst='vizierWedding' OWN-in-guard=False
    ...all eight others                False

matching the source: `alexWedding` has 1 `has:`, 11 flag reads and 2 `tstFlag`s; `vizierWedding` 0
`has:` and 2 flag reads; `earlyGuest` none of any. Same shape as KQ4's rm694-vs-rm692.

**Turning the winning machine back into a room.** The entries are extracted verbatim:

    alexWedding    entry state 0:  12 == 180
    vizierWedding  entry state 0:  AND(NOT(12 == 180), NOT(12 == 790), 338 != 0)

Register 12 is the prevRoom register — `extract.prev_room_global` derives 12 for LSL2, KQ4 *and*
KQ6 — so `prevRoom == 180` is `goal_rooms = {180}`. The two entries also contradict on the first
conjunct, which is the rival test.

### What is still provisional

* **The achievement signal has two independent confirmations, and one of them is this game.** KQ4's
  rm694-vs-rm692 is the only case the rule was not designed against. LSL2 never exercises it — its
  goal comes from the primary rule. A fourth game is what would settle it.
* **A win gated on a FLAG has no room-set equivalent** and is deliberately left alone. That is not a
  gap in this rule but in the type of `goal_rooms`; see TODO 6.1, where the goal becomes a
  predicate. KQ6 fitting the existing type is luck.
* **`_mutually_exclusive` is sound but incomplete** — it only catches a conjunct asserted in one
  guard and negated in the other. A branch written as `(switch global12 (180 ...) (790 ...))` with
  no negation would be missed, leaving the terminal in place rather than inventing a branch.

## Also observed while measuring

`anchors.movement_edges` gives rm180 an out-edge to rm820 that the room does not have. It comes
from a machine of **script 80 (`rgCastle`, the castle region)** attributed to room 180 — rm180 is a
`KQ6Room` and does not `(use rgCastle)`. Region machines appear to be attributed more widely than
the region's membership. Harmless here (extra edges over-approximate reachability, the safe
direction, and rm180's real exit to rm740 is present), but it inflates castle connectivity and is
worth a look when the flag store is done.
