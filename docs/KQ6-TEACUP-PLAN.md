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
* KQ6: the 14 stay caught, **no new item**, `test_kq6_ground_truth` 13/13. flag 22 becoming promoted
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

## 7. What each step buys, if you want to stop early

| stop after | teaCup | other value |
|---|---|---|
| Step 1 | still not caught | the whole inventory-`doVerb` effect class stops being dropped: flag 22 gets a writer, `hair`/`cassimaHair` get uses, and the 5th/6th arming-scope gaps stop compounding |
| Step 1 + 2 | **caught**, at the Realm entrance, for the right reason | endings become first-class; `mint` at the long door (the last open castle-guard question) becomes answerable |
| + Step 3 | patchable | the first register-valued edge guard |
