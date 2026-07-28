# KQ6: the last four — plan, and what it delivered

## ⭐ OUTCOME: **11 -> 13 caught**, LSL2 and KQ4 BYTE-IDENTICAL (full snapshot, placements included)

`brick, dagger, deadMansCoin, handkerchief, holeInTheWall, huntersLamp, mint, mirror, nightingale,
peppermint, scarf, skeletonKey, tinderBox`. Nothing dropped; **no `royalRing` false positive**.

| step | change | result |
|---|---|---|
| 1 | `prev == R` is unsatisfiable when R is not a predecessor | all four phantom debug sources die; **peppermint CAUGHT**; `destroyed_is_permanent` flips True for the lamp and the skull |
| 2 | an entry gated on a room LOCAL inherits its writer's condition | `getLamp`'s continuation entry carries `LOC(19 ownedBy room)`; `destroyed_is_permanent(19)` False -> True |
| 3 | `setScript: <script number>` resolves to `(ScriptID N)` export 0 | the spelling now resolves; **not sufficient for the teaCup** — see below |
| 4 | a `put:` to NOWHERE is a sink candidate whatever else its clause does | **huntersLamp CAUGHT**: `rm240 -> still needed at rm580` |

**Still missed: `skull` and `teaCup`**, each for a reason that is *not* a capture bug — both are
written up at the bottom. `skull` needs one more rule; `teaCup` is blocked on a scope decision
that is the user's to make.

## The plan as written (measurements below are from before the work)

Live score at `a148cc8`: **11 caught of 15**, `test_kq6_ground_truth.py` green (6/6).
Missed: `huntersLamp`, `skull`, `peppermint`, `teaCup`.

Everything below is MEASURED on today's tree, not carried over from the handoff. Two of the
handoff's claims about these four turned out to be stale, and both changed the plan — see
"corrections" at the end.

## The headline: the four misses have ONE shared root cause, and killing it is free

Every one of the four has a **phantom source from KQ6's developer hand-out**, and the extracted
guard makes the cure obvious:

    rm470 item=19 (huntersLamp)  guard = GAnd([100!=0, 12==99, opaque()])
    rm470 item=11 (skull)        guard = GAnd([100!=0, 12==99, opaque()])
    rm470 item=46 (teaCup)       guard = GAnd([100!=0, 12==99, opaque()])
    rm740 item=31 (peppermint)   guard = GAnd([12==99, 100!=0, opaque()])
    rm750 item=31 (peppermint)   guard = GAnd([100!=0, 12==99, opaque()])

`global12` is **prevRoom** — the register the Realm-of-the-Dead seal is built on — and it is
already tracked (`12` is the first entry in `s.regs`). `99` is the intro room `Main::init` ends
with (`(self newRoom: 99)`). **`prev == 99` is unsatisfiable at rm470/740/750**: nothing in the
room graph edges out of rm99 into them.

So the rule is not a debug heuristic at all:

> **An acquisition whose guard is unsatisfiable given the reachable values of a register we
> already track is not a source.**

No `config.debug_globals` pin, no new concept, no game named. This is the same principle
`build_maps` already applies with "a take-back is not a first acquisition" — a `get:` is only a
source if you can actually stand there and have it fire.

### …and this is strictly better than pinning `global100`, which is what I nearly did

Re-measured today with `debug_globals={100}` (the handoff's experiment, re-run because the fourth
script scope and the `destroyed_is_permanent` fix both landed after it):

    CAUGHT: the 11, + peppermint (correct), + royalRing (FALSE POSITIVE)
    sources: lamp [470,520]->[520]  teaCup [470,480]->[480]
             skull [415,470]->[415]  peppermint [390,740,750]->[390]

**The FP is fully explained, and the prevRoom route does not have it.** The royalRing hand-out at
rm740 is a different site:

    rm740 item=39 (royalRing)    guard = GAnd([12==180, GAnd([100!=0, opaque()])])

`rm740.sc:205` opens `(if (== global12 180) ...)` — a legitimate branch — and the debug
"Which ring?" dialog (`rm740.sc:261`) sits *inside* it. Pinning `global100` deletes that source
too, royalRing loses its only modelled source, and it strands at the castle boundary. Under the
prevRoom rule `12 == 180` is satisfiable, the source survives, and **royalRing never appears**.

That also means the `alexWedding` narrative-branch story in `KQ6-SOFTLOCK-CANDIDATES.md` is not
what produces the FP. It may still be a latent `_own_positive` bug worth its own look, but it is
**not on this critical path** and must not be used to justify delaying the fix.

## What each item needs, after that

| item | after the prevRoom rule | still needs |
|---|---|---|
| **peppermint** | **CAUGHT** — frontier `rm220->rm730 / rm230->rm710`, exactly the B4 boundary the oracle predicted, *and* a `dangerous_sink` at rm180 | nothing. **User: report the finding, do NOT promote until they have seen it** |
| **skull** | `destroyed_is_permanent(11)` flips **False -> True** | one thing: machine-borne drops must reach `pure_sinks` |
| **huntersLamp** | sources `[520]`, drop captured (`drops[19]={240}`, `handler_drops` has `240 sc11 item19 dest=-1`) | one thing: the local-continuation entry rule |
| **teaCup** | sources `[480]` | **`setScript: <script number>` is unresolved**, which severs the chain in the middle |

### 1. `prev == R` is unsatisfiable when R is not a predecessor  *(unblocks all four)*

Cheapest sound form, no fixpoint needed: prev's possible values at a room are decided by the ROOM
GRAPH, not by items, so compute each room's predecessor set structurally and treat a
`CMP(prevReg == R)` conjunct as FALSE when `R` is not among them. Apply it in `build_maps`' source
filter, next to the take-back rule.

Risk: LOW for KQ6 (strictly weaker than the `global100` experiment, which dropped nothing).
LSL2/KQ4 must be measured — they have their own prev-like registers.

### 2. Machine-borne drops must reach `pure_sinks`  *(the skull)*

`pure_sinks` iterates `self.em.handler_drops` only. `throwSkull`'s
`rm420.sc:681 (global0 put: 11 global11)` lives in a `changeState` body, so it is a MACHINE drop
(`throwSkull.drops == {11}`) and `dangerous_sinks` can never see it. With #1 landed,
`destroyed_is_permanent(11)` is already True and skull's uses `[280,420,580]` include rm580
downstream of rm420 — so the finding falls out the moment the drop is visible.

**Verified in the scripts that the throw is irreversible:** `rm420::init` re-casts `theBrick` from
its owner (`(== ((global9 at: 2) owner:) global11)`) but **never re-casts `theSkull`** — it is only
`init:`ed inside the `throwSkull` cutscene itself. Throw it and it lies in rm420 with nothing to
pick it up.

**⚠️ This is the risky one.** `real_uses`' docstring is explicit that `dangerous_sinks` reproduces
the `v1.0-lsl2` tag EXACTLY (Matches / Hair_Rejuvenator / Parachute / Airsick_Bag) and that the
split is load-bearing. Do not land without the full snapshot diff on LSL2 **and** KQ4 and a
user sign-off if anything moves.

Design note: `throwSkull` is not literally a *pure* sink — it also escapes the crusher, so the
clause "does something". The honest framing is the **dangerous-ACTION** class already named in
`kq6-catacombs-diagnosis`: rm420 is a death trap with two escapes, `useBrick` (own 2) and
`throwSkull` (own 11), and only one of them costs you the game. `death_traps` already computes
that competitor set (`Machine.entry_recv`), so the pieces exist.

### 3. A continuation entry gated on a room LOCAL inherits its writer's condition  *(the lamp)*

Measured `getLamp` entries:

    [0] GAnd([opaque(), 185!=0, LOC(19 ownedBy room)])           armer None, entry_locals {('L',1):1}
    [1] GAnd([<bravePond's entry>, CTR(('L',1) != 0)])           armer ('bravePond', 5)

**Entry [0] already carries the cast condition** — so the handoff's rule (a) ("a handler effect
inherits the CAST condition of the object whose method it is in") is *already done* for machine
entries. It is missing only in `opmodel.handler_locals`, which records
`520 520 ('L',1) 1 GAnd([opaque(), 185!=0])`, and that is a different consumer. **Do not build
rule (a).**

Only entry [1] blocks `destroyed_is_permanent(19)`. It is `bravePond` state 5 resuming the action
you started: `theHuntersLamp::doVerb 5` sets `local1 := 1` and arms `getLamp`; walking to the lamp
crosses the pond control area, `rm520::doit` pre-empts with `setScript: bravePond`, and
`bravePond` state 5 re-arms `getLamp` iff `local1`. That is SCI's approach/interrupt idiom, the
exact shape `_drop_continuation_entries` already recognises for `cue`:

> **An arming that fires only because a local another arming set says so is a CONTINUATION of that
> arming, and inherits its condition.**

The writer and its full guard are already to hand inside `machine.py`: `m.entry_locals[0]` records
`{('L',1): 1}` against `m.entries[0]`, which carries the `LOC` test. So this is a within-machine
rule, not a cross-pass one.

**Measured caveat, so nobody re-tries the shortcut:** I simulated this rule alone (data edit) and
`destroyed_is_permanent(19)` stayed **False** — because the rm470 phantom source was still there
and contributes an unconditional acquisition. **#1 must land before #3, or #3 looks like it
does not work.** That is the same staging trap the tinderbox/joint work hit.

### 4. `setScript: <script number>` is a spelling we resolve ZERO of  *(the teaCup)*

**✅ USER RULING 2026-07-28:** *"it's required for the long ending and we should not let you leave
the realm of the dead without it."* This settles the contradiction between
`kq6-softlock-ground-truth` ("a RED HERRING… optional/flavor") and `KQ6-ITEM-ORACLE.md` row 46
("STRANDING — B3 carry-out"). **The oracle row is right; the red-herring note is RETRACTED.**

**And the game enforces it — the whole chain is in the scripts:**

    teaCup(46) carried INTO the Realm
      -> rm660 riverStyx::doVerb 44 -> getWaterScr        entry GAnd([own(46), NOT flag58])
      -> flag 58                                          rm660.sc:361
      -> KqInv verb 30: (and flag68 flag58 (not flag22))
             -> (global2 setScript: 915) = mixPaintScr    KqInv.sc:2136
      -> flag 22                                          mixPaintScr.sc:71 (and put: 12, the feather)
      -> rm230 castleWall::onMe wants flag22 + has:3 (brush) + has:46
      -> the long path's castle entrance, rm230 -> rm710

Flag 58 is a **hard conjunct** on arming the paint, not flavour. (Its appearances in `KqInv.sc`'s
other verbs and at `rm230::doVerb 44` only pick which line is spoken — that is what made it *look*
like flavour, and reading only those is how the red-herring note happened.) The Realm is already
modelled as a one-visit pocket on flag 15, so leaving without the fill is unrecoverable.

**THE BLOCKER IS A NEW, GENERAL CAPTURE GAP.** `mixPaintScr` is script 915 and it is armed
`(global2 setScript: 915)` — a bare script NUMBER. `machine._setscript_target` handles exactly
three spellings (`Obj`, `(Obj new:)`, `(ScriptID s n)`) and returns `None` for an integer. So
**`mixPaintScr` has no entry at all**, flag 22's write is unconditional, and the chain is severed
in the middle. Whatever we do to the Realm seal cannot reach the teacup until this is fixed.

**The semantics are DERIVED from KQ6's own class table, not assumed** — `KQ6Room::setScript`
(`KQ6Room.sc:168`) spells it out:

    (method (setScript param1 &tmp temp0)
      (cond ((IsObject param1) (super setScript: param1 &rest))
            ...
            (else (super setScript: (ScriptID param1) &rest))))    ; a NUMBER means (ScriptID N)

i.e. `setScript: N` ≡ `setScript: (ScriptID N)` ≡ export 0 of script N. Same
"resolve the alias through the class table" discipline as `init_selectors`
([[derived-vocabulary-not-catalogue]]).

**Measured across the corpus, and the golden risk is ZERO:**

| game | `setScript: <int>` | of which `setScript: 0` (a CLEAR, not a target) |
|---|---|---|
| KQ4 | 77 | **77 — all of them** |
| LSL2 | 0 | — |
| KQ6 | 95 | 61 |
| QFG-VGA | 184 | — |
| Dagger | 33 | — |

So **LSL2 and KQ4 cannot move**: LSL2 has none, and every one of KQ4's is `setScript: 0`. ~34 real
targets in KQ6 (scripts 915, 130, 190, 88, 97, 96, 90, 101, 93, 92, …). `0` must keep meaning
"clear the slot" — that is the `(if param1 ...)` guard in `Actor::setScript`.

**Also check while in here:** `KqInv.sc` is the inventory script — not a room, not a region, not
armed-by-proc-call. It may need the same scope treatment scripts 822 and 11 needed
(`4780f88`). Measure whether its machines are lifted before assuming the arming site is visible.

After that, the requirement has to travel `flag22 -> flag58 -> own(46)@rm660` — two hops of the
`_own_fixpoint` shape ("a write guarded by S == v inherits whatever every way of making S equal v
requires"), which already exists. Whether it carries across two flags is the thing to measure once
the arming resolves; do not assume it.

## Order, and the regression gate

1. **#1 prevRoom-unsatisfiable sources** — unblocks everything, no FP, no new concept.
2. **#3 the continuation-local rule** — closes `huntersLamp`, the one item the user has confirmed.
3. **#4 `setScript: <script number>`** — the teaCup's blocker; zero golden risk by measurement,
   and it is a corpus-wide capture gap worth having regardless.
4. **#2 machine drops into the sink pass** — closes `skull`; highest golden risk, land last.

Gate on every step, per `measure-regressions-full-surface`: full `snapshot.py` diff (items + specs
+ **placements**) for LSL2 **and** KQ4, all `src/test_*.py`, and KQ5 / Camelot / SQ3 / TCB / Dagger
unchanged. Batch at most two runs per shell call (600s tool timeout).

Promotions to `EXPECTED_CAUGHT` need the user's OK first — `dont-flip-enumerated-ground-truth`.

## Corrections to the handoff, both measured

* **"the lamp needs TWO stacked rules (a) and (b)."** Rule (a) is already done where it matters;
  `getLamp`'s doVerb entry carries `LOC(19 ownedBy room)` today. Only (b) is missing, and #1 must
  precede it.
* **"pinning `global100` is not a clean win because of the `royalRing` FP."** True of pinning the
  global; **not** true of the prevRoom route, and the guards show exactly why (`12==99` vs
  `12==180`). The FP was never about `alexWedding`'s narrative branch.

## ✅ THE SKULL IS RE-FILED — user ruling 2026-07-28, then double-checked as they asked

*"I believe it's needed OUTSIDE the catacombs, and is re-obtainable, but should not be wasted on
the throwSkull spend. So I think it's a dangerous sink but pls double check where it's used."*

**Double-checked in the scripts. Every part of that is right.** The old **B2 carry-down** filing is
wrong and is retracted: it contradicted the user's own shield ruling, since `rm415` is coord 71,
row 4 — **the UPPER catacombs, the same level as the shield's rm408** — and *"yes you can go back
to either level of the catacombs."*

| | where | inside the catacombs? |
|---|---|---|
| source | `rm415.sc:269` `(get: 11)`, cast under `((gInv at: 11) owner:) == gCurRoomNum` | UPPER — **re-enterable** |
| fill with embers | `rm580` `getEmbers` (Isle of Mists), sets `state: (| state $000c)` | no |
| **the use** | `nightMare.sc:35` `proc344_1`: `(if (& ((gInv at: 11) state:) $0008) (setScript: catchNiteMare) else (setScript: coldEmbers))` — catching the nightmare at rm340 is how you reach the Realm | no |
| also | `openBook.sc:296/391` reads the same state, for points | no |
| **the spend** | `rm420.sc:681` `throwSkull` → `(put: 11 global11)` | yes — **irreversible** |

**Why the spend is irreversible, verified:** `rm420::init` re-casts `theBrick` from its owner
(`(== ((gInv at: 2) owner:) global11)`), but it **never re-casts `theSkull`** — that object is only
`init:`ed inside the `throwSkull` cutscene itself. Throw it and it lies in rm420 with nothing to
pick it up. And failing the nightmare is *not* the hazard: `coldEmbers` is a retryable miss.

So the shape is exactly the **dangerous ACTION** the user named — rm420 is a death trap with two
escapes, `useBrick` (own 2) and `throwSkull` (own 11), and only one of them costs you the game.
That is `dangerous_sinks`, which is why #2 (machine drops) is the fix and not a boundary rule.
Correct the row's reason in `KQ6-ITEM-ORACLE.md` and in `kq6-softlock-ground-truth`.

## WHAT THE TWO REMAINING MISSES ACTUALLY NEED (measured after the four steps)

### `skull` — one more rule, and it has a false-positive trap in it

After step 1, `destroyed_is_permanent(11)` is **True** and `sources[11] == [415]`, so everything the
finding needs is in place except the candidate itself. The spend is a MACHINE drop:

    throwSkull    sc420 rm420  drops skull      ; rm420.sc:681 (gEgo put: 11 gCurRoomNum)
    catchNiteMare sc344 rm340  drops skull      ; nightMare.sc:571/662 (gEgo put: 11 340)

`pure_sinks` reads `em.handler_drops` only, so neither is a candidate, and step 4's second
admission path deliberately does not help: it admits only `put:` with NO destination, and both of
these put the skull into a ROOM.

**Widening step 4 to room destinations is the obvious next move and it is a trap.** By the same
test — the room is not among the item's sources, and every acquisition is location-gated — BOTH
sites qualify, and `catchNiteMare` is the cutscene where catching the nightmare *succeeds*. Putting
the skull down there is the intended outcome, so flagging it would be a false positive, and the
model cannot tell the two apart on drop shape alone: what separates them is that one is an ESCAPE
FROM A DEATH TRAP with a cheaper alternative.

That distinction already exists in the codebase. `death_traps` computes rm420's competing escapes —
`useBrick` (own 2) and `throwSkull` (own 11), via `Machine.entry_recv` — so the rule to write is
**"an escape that spends an item still needed downstream, where a competing escape does not"**, not
"a machine drop is a sink". Left undone deliberately rather than shipped as the wider rule.

### `teaCup` — TWO blockers, and the second one is a scope decision, not a bug

**Blocker A: the inventory script has no home.** Step 3 made `setScript: 915` resolvable, but
measured afterwards:

    machines sc915: []        armed_rooms[915]: None
    armed_rooms[907]: None    907 is a room? False   a region? False

`mixPaintScr` is armed from `KqInv.sc:2136`, and `KqInv` is **script 907** — the inventory. It is
not a room, not a region, and nothing arms it, so `opmodel` never walks it and the arming site does
not exist in the model. The honest fix is that an inventory item's `doVerb` runs in EVERY room, the
same global scope `Main` has (`missability.GLOBAL_SCRIPTS`). It would be inert on the goldens by
construction -- LSL2 and KQ4 declare their items in script 0, which is already a global scope -- but
lifting a 2,000-line script into ~87 rooms has a real blast radius and was not attempted blind.

**Blocker B, and it is the one that matters: under our goal, the teacup is an ALTERNATIVE.**
Measured: `goal_rooms = {94, 205}`, and `required[teaCup]`, `required[brush]` and
`required[clothes]` are **all three empty**. The castle has two entrances and they are the game's
two paths:

    rm220 -> rm730    the disguise  (clothes)          -- the SHORT ending
    rm230 -> rm710    the magic paint (brush + teaCup) -- the LONG ending

The user's ruling was explicitly scoped: *"it's required for the long ending."* Our winnability
question is "can you still reach the credits", and the short path reaches them — so even with the
whole Styx-water chain modelled, the teacup comes out as one arm of a disjunction, exactly as
`clothes` and `brush` already do, and no amount of capture work changes that. It is the same class
as the "4 island treasures gate the BEST ending, not winnability" row this file already carries.

**So the teacup needs a decision first: does an ending we can still reach count as winning?** The
user's *"we should not let you leave the realm of the dead without it"* reads as no — that the long
ending is the target — but that reclassifies the goal for the whole game, so it is asked, not
assumed. If the answer is that the long ending is the goal, blocker A becomes worth paying for and
the chain is otherwise fully understood.
