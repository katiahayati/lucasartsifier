# The KQ6 catacombs: why the carry-in items are not required, and the plan

## STATUS 2026-07-28 — Steps 1, 2, 2b and 3 are LANDED

Commits `ac6bad5`, `f4b0c2b`, `9db2d52`. **LSL2 and KQ4 byte-identical on the full snapshot
surface (placements included) through every one; 269 checks green; Dagger, SQ3 and KQ5 all still
load and report unchanged.** KQ6's softlock list has NOT moved yet (still the same 7) and the
sections below say exactly what is holding each remaining item.

| step | what landed | effect on KQ6 |
|---|---|---|
| 1 | `cast_conditions` / `cast_guard`: an object the room inits only under a condition is only then in the cast, and a machine armed from its methods inherits that | `rm340 -> rm440` now carries flag 1 — the lair's first free entrance is shut |
| 2 | a NAMED maze room speaks for its own cell; `_dir_table` + `_repurposed_dirs` read the direction table and the room's own re-purposed edges out of the game | the invented `117 -> 133` descent is gone; upper and lower levels separate, the trapdoor is the only way down, rm420 is a cut vertex |
| 2b | `_listed_pseudo_rooms`: a pseudo-room can be named for a LIST of coordinates | rm411 has cells, so it stops inheriting "reaches every maze room" — the lair's second free entrance is shut |
| 3 | `state_musts` splits its node by the machine's LOCALS; `_rstep` writes keep their preconditions; a machine armed inside a PROCEDURE inherits its call sites | `sm.at(18, g) = {seenSecretLatch: {1}}` (was `{0,1}`); `holeOnWall` now carries `own(18)` |

**What is still holding each item, measured:**

* **holeInTheWall** — the chain reaches `seenSecretLatch`, but that is written by `lookInHole`,
  armed from the hole ACTOR, and the actor is init'ed two ways: one carrying a clean
  `holeWall == N` (from `holeOnWall`, which now costs the hole) and one carrying
  `holeCoords == <this cell>`, which is a comparison between two REGISTERS and renders opaque.
  An OR with an opaque arm says nothing. Closing it needs `holeCoords` to carry its non-constant
  write — "a register written with a computed value still records THAT it was written, and at what
  cost" — which is a real modelling addition, not a tweak.
* **brick / tinderbox / rm411** — Step 5, and it needs one piece the plan did not name: the
  `setScript:` RECEIVER. `sqwishEm` (fatal) and `useBrick` (`own(2)`) / `throwSkull` (`own(11)`)
  are all `(global2 setScript: ...)`, i.e. they compete for the ROOM's script slot, which is why
  the player's action pre-empts the timer. `holeOnWall` is `(global0 setScript: ...)` — the EGO's
  slot — and is lifted into every maze room, so without the receiver every room looks escapable
  with the hole and the rule is neutered. Recording the receiver is small; it is just not free.
  Also measured: **`lightItUp`, the tinderbox's escape, is not lifted as a machine at all**, so
  rm406 has no escape to find yet.
* **rm411** is the cheapest of the three and needs no escape logic: `dieAlready`'s single entry
  requires `173 == 0`, so leaving rm411 requires `173 == 1` and the level merge disappears. It is
  blocked only by the same receiver question (`holeOnWall` is lifted into rm411 and would look
  like an escape).



Measured 2026-07-28 on `sci1-doverb-capture` @ `59b511a`, working tree clean, LSL2 golden and the
KQ4 oracle both green. Every number below came from a probe run today, not from a previous note.

**Baseline.** KQ6 reports 7 softlocks: `deadMansCoin, dagger, mint, mirror, nightingale, scarf,
skeletonKey`. Of the four catacombs carry-ins the user has confirmed as real
(`brick(2), holeInTheWall(18), tinderBox(48), scarf(41)`), only the **scarf** is caught.

The scarf is caught for the right reason and it shows the shape the other three should have: every
exit from the catacombs is gated on flag 1 (minotaur dead), flag 1 is written only in rm440, and
that write costs `own(41)` — so banning the scarf turns the catacombs into a trap and
`reobtainable_rooms(41)` excludes all thirteen rooms. For the other three,
`reobtainable_rooms` still contains the whole maze.

---

## The diagnosis

### 1. The lair has three ways in, and the model lets you take all three for free

`rm440` is where flag 1 is set, so everything hangs off who can get in.

| in-edge | model | game |
|---|---|---|
| `rm340 -> rm440` | `req={}` — **free** | armed twice, `doit` under `(and (== onControl 512) (proc913_0 1))` and `minoOpening::doVerb 5` |
| `rm411 -> rm440` | `req={}` — **free** | rm411 is not adjacent to the lair at all |
| `rm409 -> rm440` | `req={397:{2}, 426:{1}}` — correctly gated | the secret door behind the tapestry |

* **`rm340 -> rm440`.** The `doit` arming *does* carry the flag (`goToLair`'s first entry is
  `GAnd([..., GAnd([opaque(), 172!=0])])` — flag 1 survived `onControl` going opaque). The second
  arming, `minoOpening`'s `doVerb`, is `opaque()`, and one unconditional-looking alternative makes
  the whole disjunction vacuous. But `minoOpening` is not always in the cast — `rm340.sc:60`:

      (if (proc913_0 1) (= local2 23) (minoOpening init:) else (= local2 20))

  It is `init:`ed **only when the minotaur is dead**. We already have the rule "an object the room
  never inits is not in the cast" (`ca5637e`); this is the same rule with a condition instead of a
  constant.

* **`rm411 -> rm440`.** rm411 is the maze's generic **corridor** room — `LBRoom::calcRoom` returns
  `-411` for the seven cells `{65,103,112,130,165,183,230}`, which are not in script 400's
  `(room, coord)` table. With no cell, `extract._splice_dispatcher` falls back to
  `set(dests) - {r}`: *the permissive union over every maze room*, the lair included.

* **`rm409 -> rm440`** is gated, but the gate is free to open: `_rstep[426] = {409: {(0,1)}}`, i.e.
  `hiddenDoorOpen := 1` costs nothing. Two reasons upstream — `holeOnWall` (the shared script 404
  helper, present in every maze room) has an entry of `None` (unconditional), and `liftTapestry`'s
  `seenSecretLatch -> L1 -> hiddenDoorOpen` link still passes through a local that `state_musts`
  merges away.

### 2. The hole-in-the-wall has a "source" in every room of the maze

    sources[18] = [230, 400, 405, 406, 407, 408, 409, 410, 411, 415, 420, 425, 430, 435, 440, 480]

`n404.sc:567` is `(global0 setLoop: -1 get: 18)` — taking the hole back off the wall — and script
404 is called from every maze room, so the model believes the hole is freshly obtainable
throughout the catacombs. It is a **take-back**, conditional on `holeCoords == labCoords`, i.e. on
having carried the hole in and put it up. Same shape as the brick, which rm420 tests explicitly:
`(if (= local0 (== ((global9 at: 2) owner:) global11)) ...)`.

While that stands, no amount of sealing the pocket can strand the hole.

### 3. The brick and the tinderbox are a *different class*: deaths an item cancels

Both deaths are already lifted, with correct entries — what is missing is the **cancellation**.

| room | death machine | entry | the action that cancels it |
|---|---|---|---|
| rm420 | `sqwishEm` (crushing ceiling) | `None` (unconditional, from `walkIn` state 9) | `useBrick`, entry `own(2)` |
| rm406 | `timerMinotaurKillEgo` | `12==435 AND NOT flag1` (you fell from rm435, minotaur alive) | `lightItUp`, armed from `egoDoTinderBoxCode::doVerb 20` = `own(tinderBox)` |
| rm407 | `emptyHandedDeath` | includes `NOT own(18)` — spelled inline by the game | (the game states it directly) |

The SCI fact that ties them together: **`(global2 setScript: X)` replaces whatever script the room
is running.** `walkIn` arms `sqwishEm`; `useBrick`, armed from a `doVerb` that requires the brick,
seizes the same slot and the crush never reaches state 9. Two machines racing for one slot, and the
player's action pre-empts the timer. Our lift models them as unrelated, so the death fires
regardless and the item that prevents it is invisible.

rm407 is the control case: the game happens to spell its condition inline (`(not (global0 has: 18))`),
and that entry *is* captured — which is why the hole is the one of the three within reach today.

### 4. The maze grid IS a blocker, and it invents exactly one edge

I first measured our recovered grid (72 cells, 146 directed edges, two asymmetric: `117->133` and
`197->181`) and concluded no named room was unavoidable, so the grid could be parked. **The user
refuted that** — asked whether you can reach the tapestry without entering the crushing-ceiling
room and without falling into the dark, the answer was *"no you cannot"*. Chasing the contradiction
found a real defect, and the game's own data then reproduced the ruling exactly.

**A named maze room is not generic, and `LBRoom::makeDoors` is not its authority.** Cell 117 is
rm405, the entrance. The generic table says its south side is open (117 is in the `bottomBlock`
negated list), and we emit a descent `117 -> 133 -> 149` into the lower level. rm405's own script
does something else entirely:

    (method (init) ... (proc402_2)                 ; NOT proc403_2, the table's layout for cell 117
       ((ScriptID 30 7) addToPic:)                 ; topDoor  -> north
       ((ScriptID 30 5) addToPic:)                 ; leftDoor -> west
       (door addToPic:) (lBlock addToPic:) (rBlock addToPic:))
    (method (doit) (cond ((global2 script:))
       ((== (global0 edgeHit:) 3)                  ; the SOUTH edge of the screen...
          ((ScriptID 30 0) prevEdgeHit: 3)
          (global2 setScript: walkOut))))          ; ...leaves the catacombs: newRoom 340

So rm405 picks its own polygon layout, draws its own door set, and its south edge is the way *out*.
The descent we emit does not exist. Drop that one edge and the game's structure falls out:

| | before | after |
|---|---|---|
| cells reachable from rm405 by walking | 72 (both levels) | **35 (upper only)** |
| rm409 (tapestry) walkable from rm405 | yes | **no** |
| the only descent | 117->133, or rm435's trapdoor | **rm435's trapFloor -> rm406 only** |
| cut cells rm405 -> rm435 | — | **rm420 (crusher), rm408, rm410** |

That is the user's ruling, derived: you cannot get to the lower level except by falling into the
dark room (tinderbox), and you cannot reach the trapdoor without passing the crushing ceiling
(brick). The door art and the polygon layouts agree perfectly on every *generic* cell — I checked
that `makePolys`' groupings match the four door lists exactly — so the art is a faithful proxy
everywhere except the twelve named rooms, which override it.

**And rm411 must be split per cell.** Measured: with the corrected grid but rm411 kept as one node
its seven cells straddle the drop (65/103/112 upper, 130/165/183/230 lower), lower -> rm411 -> upper
leaks, and the hole is *not* caught. Drop or split rm411 and it is. So the corridor room is
load-bearing, not a detail.

### 5. A joint projection is NOT needed — measured

The concern was that per-register projections are independent, so a chain of gates over *different*
registers is never enforced jointly. Real in general, but it does not bite here: with the three
lair in-edges fixed and the hole banned, projection 173 alone has **zero** states at rm440, so the
intersection already excludes it. A hand-rolled joint walk over `{173, 426, 397, 12}` agrees exactly
(rm440 unreachable, flag 1 unsettable) and is unchanged with no ban, so the model is not
over-sealed either.

Note also that the lair (cell 182) is not reachable in the grid at all: it is only ever entered
through the secret door, which is why the polygon gate on `rm409 -> rm440` is the right and only
script-level model of it.

---

## The plan

Each step is a general SCI rule, not a KQ6 patch. Standing gate after **every** step: LSL2 golden
byte-identical (`test_golden`) and the KQ4 oracle green (`test_kq4_ground_truth`), plus the full
snapshot surface for both, per `measure-regressions-full-surface`. Both are green as of today.

### Step 1 — a conditional `init:` rides onto every interaction with that object
Generalises `ca5637e` ("an object the room never inits is not in the cast") from a constant to a
condition: an object's `doVerb`/handler armings inherit the path condition under which the room
`init:`s it. Never-inited is the `C = false` special case of the same rule.

Fixes `rm340 -> rm440` (minoOpening), and is the natural home for the hole's take-back too
(`theHole` is inited only when `holeCoords == labCoords`).

Adding a condition *removes* movement, which is the unsafe direction, so keep `_inherit_arming`'s
discipline: OR over all init sites, only descend the `seq` of the room's own `init`, and leave the
object alone if any site is unconditional.

### Step 2 — a NAMED maze room supplies its own exits; the generic door table does not
`_maze_reach` reads `LBRoom::makeDoors` for every cell, including the twelve that are real rooms
with their own scripts. Where a named room's script disagrees, the script wins. Derivable with no
room named: a named room's `init` explicitly `addToPic:`s the door objects it has (script 30
exports 5/6/7 = left/right/top) and calls its own `proc40x_y` layout, and its `doit` names its own
`edgeHit`/`onControl` exits. Read those; fall back to the table only for cells that reach
`initPseudoRoom`.

For rm405 that deletes exactly one edge, `117 -> 133`, and with it the phantom second descent.

### Step 2b — rm411 must be split per cell, and the cell-less fallback must be empty
Two related defects in `_splice_dispatcher`:
* **The permissive-union fallback.** A maze room with no recovered cell gets `set(dests) - {r}` —
  every maze room, lair included. That is where `rm411 -> rm440` comes from. A room we cannot place
  should contribute *no* maze edges rather than all of them.
* **rm411's cells are recoverable and must not be merged.** `calcRoom`'s
  `(if (proc999_5 temp1 65 103 112 130 165 183 230) (return -411))` is the same membership-test
  shape `_maze_reach` already parses. But collapsing the seven into one node re-joins the levels
  (65/103/112 are upper, 130/165/183/230 lower) — **measured: with rm411 merged the hole is not
  caught; with it split or dropped, it is.** So rm411 needs one node per cell, which is the small,
  scoped version of the positional model (`rLab labCoords` is the real state; it is written with
  computed values, which is why `derive_obj_props` cannot see it).

### Step 3 — opening the secret door must cost the hole
Two links, upstream first:
* `holeOnWall`'s unconditional entry in script 404 — likely the same `cue`/conditional-init shape as
  Step 1, so check whether Step 1 already closes it before writing anything new.
* `liftTapestry`'s `seenSecretLatch -> L1 -> hiddenDoorOpen`. The known dead end: tracking locals in
  `state_musts`' forward walk does **not** work, because musts attach to a STATE and both branches
  reach st18, so the merge unions the value away before the local can discriminate. The fix is
  per-PATH musts where `_own_fixpoint` consumes them. Do not re-add local tracking on its own.

### Step 4 — an acquisition guarded by "the item is already here" is not a source
A `get:` whose path condition tests `LOC(item) == this room` is a take-back of something you
dropped; it cannot be a *first* acquisition. We already carry LOC atoms (`_loc_placed_required`).
Both spellings appear in KQ6: `holeCoords == labCoords` and `((global9 at: 2) owner:) == global11`.

**Measured payoff of Steps 1–4** (applied as data edits to the live model): the hole is **CAUGHT**,
7 -> 8 softlocks, nothing lost — both with the current grid and with the corrected one. Staged,
each step is load-bearing: without Step 3 the lower level stays escapable with the hole banned,
without Step 4 the phantom sources keep it re-obtainable no matter what, and with rm411 merged into
one node the catch disappears again.

### Step 5 — an item-gated action that pre-empts a death script
The mechanism in section 3. A death machine's `DEATH` transition should carry `NOT (OR of the
item-gated armings that can seize the same room-script slot)`. This is the "dangerous ACTIONS"
class the LSL2 oracle already names, and it is squarely inside the one rule: the death is
preventable from its own screen *only if you already hold the item*.

**Step 2 is a prerequisite for this one.** On the current grid rm420 and rm406 are avoidable, so
making their deaths conditional buys nothing — you would just walk around them. On the corrected
grid rm420 is a cut vertex and the trapdoor fall into rm406 is the only descent, so the death
gates land on rooms you must pass.

Expected: the **brick** then falls out of the existing edge detector — with the brick banned rm420
becomes a death sink, so it leaves `reobtainable_rooms(2)` while the rooms around it stay, which is
exactly the frontier shape `edge_strandings` looks for.

The **tinderbox** is the harder one and should not be assumed: its death is gated on `prev == 435`,
so only *one entry into* rm406 is fatal, while `reobtainable_rooms` and `_need_rooms` compare at
ROOM level even though the underlying walk is state-level. On the corrected grid that entry is the
only one, which may be enough on its own — measure before building anything.

---

## Answered by the user, 2026-07-28

> *Can you reach the tapestry room without entering the crushing-ceiling room and without falling
> into the dark?* — **"no you cannot."**

Recorded as ground truth, and it is now **derived from the game's own data** rather than merely
believed: delete rm405's invented south descent and the trapdoor becomes the only way down while
rm420 becomes a cut vertex on the way to it. That agreement in both directions — the ruling
predicting a defect, the corrected data reproducing the ruling — is the strongest validation the
maze model has had.

It also cost me a wrong conclusion, worth recording: I measured our grid, found no named room
unavoidable, and wrote "the grid is not the blocker". The measurement was right about *our* grid
and wrong about the game, because I checked our transcription for internal consistency (the door
lists agree with `makePolys` perfectly) and never asked whether the twelve named rooms opt out of
the generic scheme. Internal consistency is not fidelity.
