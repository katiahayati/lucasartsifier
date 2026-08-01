# KQ6: closing the teaCup — measured state and the plan

**Everything below was re-measured on `sci11-gates` @ `dbdfbb7`, 2026-07-31. No figure is carried
over from a handoff or a memory; where a recorded claim did not reproduce, it is corrected inline
and the correction says what was measured instead.**

Baseline at HEAD: `test_kq6_ground_truth` **13 passed, 0 failed**, 15 units caught,
`still-missed ground truth: []`, `teaCup` deliberately not caught.

---

## 1. The chain, as the game writes it

| # | site | condition | effect |
|---|---|---|---|
| 1 | `rm480` | — | `teaCup` (item 46) picked up — its **only** source |
| 2 | `rm470 getOoze` | `own(46) ∧ ¬flag68 ∧ own(49) ∧ reg443` | **flag 68** := 1 — the mud. *Also wants the cup.* |
| 3 | `rm660 getWaterScr` | `own(46) ∧ ¬flag58` | **flag 58** := 1 — the Styx water. **rm660 is inside the Realm of the Dead.** |
| 4 | `KqInv.sc:2136`, `doVerb 30` | `flag68 ∧ flag58 ∧ ¬flag22` | `(gCurRoom setScript: 915)` → `mixPaintScr` → **flag 22** := 1 (paint mixed) |
| 5 | `rm230 castleWall::doVerb 44` | `¬flag23 ∧ flag22 ∧ own(3 brush) ∧ own(46)` | `paintWallScr` → **flag 23** := 1 (wall painted) |
| 6 | `rm230 magicDoor::doVerb 28` | `¬flag24` | `setScript: (ScriptID 190)` (`openBook`) → `(gCurRoom notify:)` → `enchantDoorScr` → **flag 24** := 1 |
| 7 | `rm230 magicDoor::doVerb 5` | `flag24` | `openDoorScr` → `newRoom: 710` — **the long door** |

The Realm is entered once (`rm600.sc:71` sets flag 15, never cleared; the prevRoom seal is already
modelled), so step 3 has exactly one opportunity. Register = flag + 172 throughout.

---

## 2. What the model already has right

* `sources[46] == [480]`, `drops[46] == []`.
* `getWaterScr @rm660` entry `GAnd([own(46), ¬reg230])` → writes `reg230` (flag 58). **The Styx fill
  is fully modelled.**
* `paintWallScr @rm230` entry `GAnd([own(46), ¬reg195, reg194, own(3)])`.
* `openDoorScr @rm230` entry `GAnd([opaque, reg196, GOr([reg195, <the paintWallScr clause>])])`,
  state 10 `EXIT → 710`.
* `edge_demands(230, 710) == {3, 46}` — brush and teaCup.
* `required[46] == [230, 340, 470, 660]`, decomposing exactly as §1 predicts
  (`paintWallScr@230`, `offerItem@340` (a dropped entry), `getOoze`+`teaParty@470`,
  `getWaterScr@660`).
  ⚠️ **Correction to `kq6-softlock-ground-truth`**, which records `required[teaCup] == []` and "it
  is not captured at all". That is stale — the item-level requirement is captured now.
* **The guard the finding wants already exists at the right boundary**:
  `rm340 -> rm155 : (and (gEgo has: 7) (gEgo has: 24))` — Charon's coin and the mirror, the Realm
  entrance. The teaCup belongs on this guard, next to them.

---

## 3. Blocker A — flag 22 has no writer. This is the capture blocker.

`reg 194` (flag 22, "the paint is mixed") has an **empty domain** and is **not promoted**. Its only
writer is `mixPaintScr` (script 915), armed from `KqInv` (script 907), and
`armed_rooms[907] is None`: an SCI1 inventory item's `doVerb` has **no arming site anywhere**,
because the **icon bar** dispatches it.

**Consequence: an EMPTY teaCup satisfies the long door.** The model demands the cup at rm230 but
never the water, and the cup is re-obtainable from rm480 (the catacombs are re-enterable, per the
shield ruling), so nothing strands.

**Re-measured today** with a temporary probe (`armed_rooms[907] = all 86 rooms`, since reverted —
the tree is clean):

* the chain completes: flag 22 promoted, dom `[0,1]`; `mixPaintScr` lifted with entry
  `own(12) ∧ flag68 ∧ flag58 ∧ ¬flag22`.
* the teaCup **is** flagged, at edge `rm340 -> rm155` — **the right boundary**.
* and the analysis is destroyed exactly as `inventory-script-scope-gap` recorded on 2026-07-30:
  **14 items → 45**. `deadMansCoin`, `handkerchief` and `skeletonKey` DROP; `clothes`, `shield` and
  `coal` (all CONFIRMED_SAFE) are flagged; ~28 more join them. The `rm340->rm155` finding names
  **45 items**, i.e. the whole inventory.

So the boundary is right and the mechanism is wrong, for the reason already recorded: attributing an
always-available action per room converts an **availability** into a **universal requirement**.

---

## 4. Blocker B — the `notify` arming gap is real, but NOT on the teaCup's path (correction)

`enchantDoorScr`'s entry is `None` — ungated — because `(gCurRoom notify:)` from `openBook`
(script 190) is an arming spelling we do not follow. flag 24 is therefore free in the model.

`inventory-script-scope-gap` says *"the teaCup needs BOTH"*. **Measured today, it does not.**
`openDoorScr`'s entry is

    flag24 ∧ ( flag23 ∨ (own(46) ∧ ¬flag23 ∧ flag22 ∧ own(3)) )

flag 24 is a **conjunct alongside** the paint disjunction, not an alternative to it, and **both arms
of that disjunction cost flag 22** — flag 23's only writer is `paintWallScr`, whose own entry
requires flag 22. A free flag 24 costs us the spell-book requirement; it does not open the door
without the water. Fix `notify` on its own merits (it is the 6th in the arming-spelling family), not
for the teaCup.

---

## 5. Blocker C — necessity. **No capture work catches the teaCup under `goal = {180}`.**

The castle has two entrances and they are the game's two paths:

    rm220 -> rm730   the disguise    own(clothes)                      -- the SHORT ending
    rm230 -> rm710   the magic paint own(brush) ∧ own(teaCup) ∧ flag22 -- the LONG ending

Both reach rm180. So even with §3 fixed, the long door is one arm of a disjunction and refusing the
paint costs a *worse ending*, not the game. This is not a modelling defect; it is the answer to the
question we are currently asking.

**The exclusivity mechanism is real and in the scripts, and it does not rescue us either.**
`rm580 makeRain` state 11 does `(global0 put: 5 580)` — the Druids burn Beauty's clothes on the
*survival* branch — and the only `get: 5` in the game is `rm540 beautyScript` state 20, a one-time
story cutscene reached by `rm250`'s `newRoom: 540`. Every route into the Realm passes rm580
(`reg186`/flag 14 has exactly one writer room, `_inroom[186] == {580: [1]}`). So **long route ⇒ no
clothes ⇒ the short door is physically shut.** The model does not see it: `beautyScript`'s entry is
`prevRoom == 250` and 250→540 reads as a repeatable edge, so `destroyed_is_permanent(5) == False`
and `reobtainable_rooms(5)` is the whole open map.

But repairing that gets the teaCup only at a price: the finding it produces lands on **`clothes`**
("burned at rm580, still needed at rm220"), and `clothes` is CONFIRMED_SAFE by user ruling. To
suppress that you would have to make the detectors ask *"can I still reach the goal"* rather than
*"is this item still obtainable where it is used"* — a semantics change across `dangerous_sinks`
and friends. Recorded as a real improvement; **not the cheap route to the teaCup.**

**Conclusion: the teaCup can only be closed by making the ENDING first-class.** Flag 15 (`reg 187`)
is the discriminator, is already promoted, and is written at `rm600.sc:71` (Realm entry) and
`rm710.sc:222` (the long door's basement). The two endings are distinct product states
`(180, 187=1)` and `(180, 187=0)`.

---

## 6. The plan

### Step 1 — GLOBAL (icon-bar) SCOPE, derived. Prerequisite; lands and ships alone.

> **A script that declares the game's inventory-item instances is dispatched by the icon bar, so it
> runs in every room and belongs to none.**

Derived from the same `Vocabulary.store_class` species walk `vocab.item_names` already does — no
script number is named. **Inert on the goldens by construction**: LSL2 and KQ4 declare their items
in script 0, which is *already* the global scope (`opmodel.MAIN_SCRIPT` → room 0,
`missability.GLOBAL_SCRIPTS`). KQ6 yields 907, Dagger 15.

Split what that scope contributes, which is the whole content of the fix:

* **KEEP — effects and their costs.** The register write and its
  `cheapest((gi, room, v), _own_positive(g) | entry_musts)` cost must be available in *every*
  reachable room. That is a fourth `GLOBAL_SCRIPTS` widening site, matching the one `_sink_rooms`
  already has for Main's `put:`s.
* **SUPPRESS — per-room `required`.** `build_maps`' `req(guard, room)` must not fire for a machine
  or handler lifted from the global scope: an action available everywhere is not evidence about any
  room. Homing to pseudo-room 0 (as Main already is) gets this for free — but audit every consumer
  of `required` for room 0 before relying on that instead of an explicit scope tag on the machine.

**Acceptance (do not land without all of it):**
* LSL2 + KQ4 **byte-identical** on the full snapshot surface *including placements*, baselines taken
  from a `git worktree` at `dbdfbb7` — not from the live tree after editing it.
* Dagger, SQ3, Camelot, TCB unmoved, or every move explained.
* KQ6: the 14 stay caught, **no new item**, `test_kq6_ground_truth` 13/13. <!-- STALE: 18 units
  and 16/16 as of 2026-07-31; see ../KQ6-STATUS.md --> flag 22 becoming promoted
  adds a register to the projection, so guard specs *may* move — every move explained, none accepted
  on the grounds that the item list did not change.
* Positive checks that the fix did something: `mixPaintScr` lifted with its real entry, flag 22
  dom `[0,1]`, and `hair` / `cassimaHair` gain the uses they currently have none of.
* A test pinning the derivation itself: the global scope resolves to 0 on LSL2/KQ4, 907 on KQ6,
  15 on Dagger — read from the class table, not asserted by number.

### Step 2 — make the ENDING first-class. **This is a scope decision and it is the user's.**

Three shapes, in the order I would rank them:

1. **Per-ending goals (recommended).** Derive the ending discriminator the same way
   `anchors._resolve_pass_through` already derives rm180 — `alexWedding` branches on flag 15 eleven
   times — and make `goal_rooms` a set of **product states**. Run the reachability question once per
   ending and union the findings, each tagged with the endings it gates. An item that gates *every*
   ending is a hard softlock; one that gates *some* is ending-restricting. `LONG_ENDING_ONLY` stops
   being a hand-written column and becomes a **produced label**. No existing verdict drops: each of
   the 14 is caught under at least one goal.
2. **Switch the goal to the long ending.** One line, and it makes the teaCup required immediately —
   but it silently reclassifies the whole game, and any short-route-only requirement drops out of
   EXPECTED_CAUGHT. Needs a ruling and a re-measured verdict list before, not after.
3. **Model the clothes exclusivity (§5).** Independently correct and it would make the teaCup a
   *hard* softlock rather than an ending-only one — but it needs a one-time-cutscene-arrival rule
   *and* goal-aware `required`, and it puts `clothes` (CONFIRMED_SAFE) back in play. A separate
   piece of work, not a route to the teaCup.

### Step 3 — the guard, once it is caught

Two guards, and the model already knows both boundaries:

* `rm340 -> rm155` (Realm entrance) — add `(gEgo has: 46)` to the existing
  `(and (gEgo has: 7) (gEgo has: 24))`. Safe by the §5 argument the codebase already applies at the
  castle doors: it cannot wall the short route, because the short route never crosses it.
* `rm680 -> rm155` (Realm **exit**) — demand flag 58. Entering with the cup does not guarantee
  filling it, and this is the boundary the user's own ruling named
  (*"we should not let you leave the realm of the dead without it"*). This one needs a
  **register-valued** edge guard, which `guard_specs` does not emit today.

### Step 4 — the oracle

`teaCup` moves out of `LONG_ENDING_ONLY`. The `check("a LONG-ENDING-only item is not flagged")`
assertion is then asserting known-wrong behaviour and must be **replaced, not deleted**: pin the
finding's shape — item 46 at `rm340->rm155` (and flag 58 at `rm680->rm155`) — so the surviving
clause has its own test. Whatever the column becomes after Step 2, it must be *produced* by the
tool, not enumerated in the test file.

---

---

## ✅ STEP 1 IS DONE — `44234bc`, and it cost one extra fix

**Measured:** LSL2 + KQ4 **byte-identical** on the full snapshot surface *including placements*
(baseline from a `git worktree` at `dbdfbb7`); Dagger identical; the whole suite green, 317 checks,
`test_scopes` 77 → 91. KQ6's 14 verdicts unchanged and **flag 22 now has a writer**
(`_rstep[194]` in 86 rooms, entry `own(12) ∧ flag68 ∧ flag58 ∧ ¬flag22`).

KQ6's snapshot moved **one line**, and it is an improvement:

    - rm340->rm155: (and (gEgo has: 7) (gEgo has: 24))
    + rm340->rm155: (and (gEgo has: 7) (gEgo has: 11) (gEgo has: 24))

Item 11 is the **skull** — you catch the nightmare with the ember-filled skull, and that is the only
way into the Realm. It comes from the second fix, below.

### What the scope contributes, and the four consumers that proved it
The rule landed as `vocab.inventory_scripts` (derived from the item class table: LSL2 {0}, KQ4 {0},
KQ6 {907}, Dagger {15}, QFG-VGA {206}) plus a **separate `global_machines` list** that only the
register build reads. The separation is the whole design, and it was arrived at by breaking things:
leaving those machines in `em.machines` cost, one consumer at a time, `required` (five confirmed
softlocks, a 45-item guard), `sources`/`drops` (the feather gained 86 destruction sites), machine
EXITs (two fabricated ways out of the pitch-dark rm406) and `death_traps` (an inventory action read
as an ESCAPE from a trap, so the tinderbox stopped being needed to survive the dark).

### The extra fix: half a bit-store can only ever block
Surfaced, not caused, by the scope work. `rm580.sc:322` sets the skull's ember bits through SCI's
cache-the-handle idiom — `(= temp0 (gInv at: 11))` then `(temp0 state: (| (temp0 state:) $000c))` —
and with `temp0` unresolved that **set** was invisible while the matching **clear**
(`(self state: (& (self state:) $fff7))`, written inside the item's own method) was captured. A
register whose only modelled write is the value every read REJECTS cannot open anything, so
promoting it fabricates a seal: `catchNiteMare`, the only way into the Realm, became unreachable.
Fixed in both halves of the pair — `derive_item_bit_flags` and `lower_item_bit_flags` — or the
discovery and the lowering disagree about what a bit is.

## 8. Step 2, measured: the discriminator DERIVES, the goal plumbing does not exist yet

The derivation the user chose is confirmed available, and it needs no new concept.
`anchors._resolve_pass_through` already picks the WINNING machine out of the rivals at a terminal's
predecessor. Measured at the machines reachable from each game's goal room:

    KQ6  rm740  alexWedding   (the WIN)  branches on regs {182, 187}
    KQ6  rm740  vizierWedding (the LOSS) branches on regs {182}
    LSL2 rm86                            -- no rival machines at all
    KQ4  rm694                           -- no rival machines at all

> **The ending discriminator is the register the WINNER branches on that its RIVAL never mentions.**

Winner minus rival is exactly `{187}` = flag 15 = "you entered the Realm of the Dead and revived the
King and Queen" — the difference the walkthroughs describe. Register 182 is shared machinery and is
correctly excluded. **Inert on the goldens by construction**: neither LSL2 nor KQ4 has rival endings,
so both derive nothing.

### What is NOT built, and the two obstacles — both real, neither guessed

1. **`goal_ok` is computed before the projections exist.** `build_maps` calls
   `goal_reaching_rooms(edges, cfg.goal_rooms)`, a FLAT backward reachability, and it runs inside
   `build_maps` — before `IrSccReach.__init__` has built `_inroom`/`_rstep`/`_pstates`. Asking "from
   which rooms can I still reach rm180 **with flag 15 set**" is a backward walk in the flag-15
   projection, which is the shape `reobtainable_rooms` already uses — but it cannot be called from
   where `goal_ok` is needed. Either the goal walk moves after the projection build, or the
   projection build moves before `build_maps`. That ordering is the actual work.
2. **⚠️ The long-ending goal makes the SHORT DOOR a dead end, and that is the documented wall
   hazard.** From inside the castle by `rm220->rm730`, nothing writes flag 15 (its writers are
   rm600, rm710, and the rm740 debug branch), so under goal `(180, 187=1)` every room past the short
   door can never reach the goal. That is *true* — the short route really does forgo the good ending
   — but our detectors report ITEMS, and a whole route going dark is not an item stranding. It has to
   be reported as what it is (a point of no return that costs an ending) or it will come out as
   noise, or as a guard that WALLS the short route. See [[path-forcing-guards]] and §5 of
   `kq6-castle-two-doors`: *"never convert a softlock into a wall."*

**Recommended order for Step 2:** land the discriminator derivation together with obstacle 1 (so it
has a real consumer the moment it exists), then run the long-ending analysis and *look at the raw
findings* before deciding how obstacle 2 is reported. Do not emit guards from the per-ending run
until that reading has happened.

### A cheaper alternative found while measuring — worth a decision before building the above
The teacup does not actually need the goal to change to be *caught*; it needs the model to notice
that **flag 58 becomes permanently unsettable when you leave the Realm**, and that its cost is
`own(teaCup)` (`getWaterScr`'s entry). That is a REGISTER stranding, a class the codebase already
has two detectors for (`register_strandings`, `register_flip_strandings`), and it reports "you can
no longer take the long route" without reclassifying what winning means for the whole game. It
would land the teacup at the right boundary with the right reason, and it does not touch the goal.
It is a smaller build than per-ending goals and it does not carry obstacle 2 — but it also does not
give the per-ending split the mint and the castle guards still want, so it is a genuine trade rather
than a shortcut. **Not built; recorded because it was measured, not assumed.**

## 7. What each step buys, if you want to stop early

| stop after | teaCup | other value |
|---|---|---|
| Step 1 | still not caught | the whole inventory-`doVerb` effect class stops being dropped: flag 22 gets a writer, `hair`/`cassimaHair` get uses, and the 5th/6th arming-scope gaps stop compounding |
| Step 1 + 2 | **caught**, at the Realm entrance, for the right reason | endings become first-class; `mint` at the long door (the last open castle-guard question) becomes answerable |
| + Step 3 | patchable | the first register-valued edge guard |

---

## 9. Fix (1) attempted and PARKED — `docs/archive/one-shot-sources.WIP.patch`

> **Correction, 2026-07-31.** This heading said "not committed". It *is* committed, and has been
> since the branch work; it sits beside this file in `docs/archive/`. It is still a parked
> attempt rather than an applied fix — a `.patch` file, not something in effect.

**What the gap turned out to be, and it is not what §5 said.** The model already has the latch. It
was never a missing one-time-cutscene rule:

    rm540::init  (cond ((== prev 250)   ... beautyScript)     ; the wedding -> the clothes
                       ((not flag46)    ... beastScript))     ; the Beast   -> the RING
    beastScript  st21  flag46 := 1  +  (gEgo get: 37)         ; ...and it sets its own latch

Measured: `beastScript`'s entry is `¬(prev==250) ∧ ¬flag46`, state 21 writes flag 46, and flag 46
(reg 218) is a promoted register. All correct. The chain is
**ring (one-shot) → spent at rm250 → arrive rm540 with prev==250 → clothes**, so the clothes really
do have exactly one acquisition.

**The gap is one level down**: `reobtainable_rooms` seeds its backward walk from every state whose
ROOM is a source room, so the acquisition's own guard never gets a say.

> A source room you can walk back to is not a source you can use again.

The patch adds `source_reqs(em, regs, edges)` — per (item, room), the register requirements of each
acquisition SITE, using the same site filters `build_maps` applies — and `_src_fires`, which seeds
only from states that satisfy one of them. **LSL2 and KQ4 stay byte-identical.**

### Why it is parked, two reasons and the second is the important one

1. **It has a real defect.** `source_reqs` calls `guard_reqs` on a whole entry guard, and an entry
   can be a DISJUNCTION. `freeCeleste`'s (the dagger) is
   `(opaque ∧ flag258 ∧ ¬flag1) ∨ ¬CTR(L2≠0)` — the second arm constrains nothing, so the entry
   requires nothing of flag 1, but the single call reads `{flag1: {0}}`. That is why KQ6 gained 13
   `has: 8` guards on edges deeper into the catacombs, which would WALL the maze against the shield
   ruling. `edge_meta` gets this right by emitting one ROW per alternative; `source_reqs` must split
   the DNF the same way. Fixable, and not yet fixed.
2. **⚠️ EVEN CORRECT, IT DOES NOT CLOSE THE TEACUP.** Measured with the patch applied:
   `reobtainable_rooms(clothes)` is unchanged at 60, `destroyed_is_permanent(clothes)` is still
   False, and KQ6 still catches the same 14. **The reason is structural, not a bug:**
   `reobtainable_rooms` bans ONE item, and the clothes' unavailability is a CHAIN —

       to re-get the clothes you must re-arrive at rm540 from rm250
       to do that you must give Beauty the RING
       and the ring was spent doing exactly that, and is one-shot

   Banning `clothes` leaves the ring available, so the walk happily re-runs the whole sequence.
   Seeing the truth needs the ban to propagate through **what a re-acquisition COSTS** — the
   fixpoint shape `_own_fixpoint` already has for registers, applied to items. That, not the latch,
   is the real remaining work for the teacup on this route.

**So the route is still right and still cheaper than a goal change — but it is two fixes deep, not
one.** The patch is kept because its first half (`source_reqs`) is correct and golden-inert; it
needs the DNF split before it can land on its own merits.
