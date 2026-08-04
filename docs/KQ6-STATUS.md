# KQ6 — where we actually stand

**Recomputed from scratch 2026-07-31** on branch `sci11-gates`. Every number below came out of a
single clean `missability.load(config.KQ6)` run with every detector called, not from a previous
session's notes. Reproduce with `python3 src/test_kq6_ground_truth.py` (verdicts) and
`python3 src/snapshot.py KQ6` (full surface).

**This file is the single live source for KQ6 status.** The plan documents that got us here are
in `docs/archive/` — they record how each conclusion was reached and several carry numbers that
were true when written and are not now. If this file and one of them disagree, this file wins.

---

## The model

| | |
|---|---|
| anchors | start **rm99** → goal **rm180**, both DERIVED (`anchors.discover`), nothing declared |
| rooms | 86 known, **81 reachable** from the start |
| structure | 15 strongly-connected components, 93 gating registers, 94 projections |
| machines | 642 room machines + **344** from the always-live icon-bar scope |
| icon-bar scope | scripts `{84, 90, 96, 97, 101, 907, 915}`, derived via `vocab.inventory_scripts` |
| registers that scope writes | `{4, 194, 231, 301, 388}` — 194 is flag 22, the mixed magic paint |
| exchange slots | exactly one: `{brush, flute, nightingale, tinderBox}` @ rm280, the pawn counter |

The goal is **rm180**, not rm94. rm94 is the credits, which roll after the vizier's wedding too,
so for a long time the goal was satisfied by *losing*. See `KQ6-GOAL.md`.

---

## Detection — 19 requirement units, oracle 16/16

**The 19th (2026-08-02): the `letter`**, user-confirmed the day `register_strandings` turned
causal — flag 166's flip is a point of no return past which the vizier's letter's source is
unreachable, while rm730/rm870 still demand showing it. The flip detector joined the oracle's
caught set and the snapshot surface with it. Its guard spec landed the same day: `guard_specs`
now consumes the causal flips into the same `register-write` remedy as KQ4's nightfall — hold
the flip until the letter is in hand — and the patcher places it on both `(ScriptID 80 0)
setFlag: 709 2` sites (rm740, rm880), split out of their chained sends so the scenes still play,
matching the exact receiver (rm710/720's `(ScriptID 81 0)` writes the same word/mask for a
different region and must not be touched).
⚠️ Flag 166 is "the wedding has started", the game's central plot branch — this guard has NOT
been play-tested and goes first when the ScummVM pass runs. (The hold was briefly PARTIAL on
disk — rm880 was one of the 5 decompiler-dialect compile failures — until 2026-08-03, when all
five fell: see "the compile wall" below. Both sites ship now.)

`test_kq6_ground_truth` passes all 16 checks. `KNOWN_GAPS` is empty and `LONG_ENDING_ONLY` is
empty, so every unit the oracle calls real is caught and nothing outside the oracle is flagged.

**Which detector carries which verdict** — this is the thing that kept getting lost, because a
flattened item list cannot show it:

| detector | rows | units it carries |
|---|---|---|
| `edge_strandings` | 11 | brick, dagger, deadMansCoin, handkerchief, holeInTheWall, mirror (×2 edges), nightingale, scarf, skeletonKey, tinderBox |
| `group_strandings` | 1 | `(mint \| peppermint)` @ rm750 — the genie's rival solutions |
| `toll_strandings` | 8 | carry-**out**: handkerchief, skeletonKey (rm340→155), sacredWater (rm370→380)<br>carry-**in**: deadMansCoin, mirror, teaCup (rm340→155), gauntlet, mirror (rm660→670) |
| `dangerous_sinks` | 3 | **mint, peppermint** (Main's generic `doVerb`; first fatal witness rm180), huntersLamp (rm240) |
| `fatal_uses` | 1 | skull @ rm420 `throwSkull` |
| `joint_strandings` | 0 | — |
| `register_flip_strandings` | 0 | — |
| `resource_exhaustion` | 0 | — |

Note `mint` and `peppermint` reach the caught set **as singletons only via `dangerous_sinks`** —
eating them on the wrong object destroys them, and past rm180 the pawn shop is unreachable. As a
requirement *unit* they appear only as the disjunction. Both facts are real and they are not the
same fact.

---

## Patching — every finding is CLOSED (2026-08-02)

| | |
|---|---|
| guard specs | 19 total — **16 emitted, 3 refused** (17 edge + 1 `action` + 1 `register-write`) |
| the 3 refusals | the `reg == 0` half-questions (demand the mirror flag CLEAR ×2; demand rm690's gauntlet latch CLEAR — the reg536 row is NEW with the fifth store, 2026-08-02) — they pair with no entrance guard and would close no softlock; refused with the reason stated |
| the catacombs | **collapsed 2026-08-01**: the brick joined the capture guards (rm340→370/405/440 demand all FOUR carry-ins), and the 8 `rm*→rm420` wall-guards are GONE — see below |
| sink remedies | 3 emitted — mint + peppermint applied; huntersLamp refused at apply (a TRADE) |
| fatal uses | 1 emitted — refuse `throwSkull` at rm420 |
| `verify()` | fixed **10 + 1 group** · **NEW 0** · **remaining 0** |

**`python -m pipeline <kq6> --report` exits 0.** The last three closed 2026-08-02, each by a
principle already in the codebase rather than a route oracle:

* **handkerchief + skeletonKey** are carry-OUTs of the Realm toll pocket, so the demand belongs
  at the pocket's exit frontier: `pocket_carryout_frontier` (the item twin of
  `_settable_frontier`, same committed walk) places both at **rm640→rm650** — the last crossing
  after which their sources are unreachable. ✅ **Divergence with the guard oracle SETTLED in the
  engine's favor, user-tested in-game 2026-08-02**: "you can go 640→650, but not the other way
  back" (the knight's room; the rm640 ticket taker keeps your ticket). The oracle's old row-4
  site (rm680→rm155) presumed a walk-back that does not exist; the oracle is corrected.
* **the wrong-door stranding rows** (all six) died to two rules `edge_strandings` now applies to
  its own output: an edge that ITSELF demands an item cannot strand it ("forced, not missable" —
  the toll detector's own rule), and an edge where the item CANNOT BE HELD cannot strand it
  (`unholdable_at`, the same call that already shapes the specs). Both filters are
  **singleton-only**: on groups the forced-filter fires exactly once corpus-wide — deleting
  LSL2's play-validated rm79→rm80 raft guard — and that baseline is ruled untouchable.

**The exit guards PLACE now (2026-08-01).** The placement walk commits what is genuinely
committed: an **unconditional entry write** (`em.init_writes`, unconditional by construction)
forces its value on arrival, and a **consumed item toll** cannot prove compliance through a
second crossing (the row itself established the payment is unrecoverable). Both are true game
facts, no register or item is named, and every detection walk stays permissive. Result: the
cup-filled flag (58) is demanded at **rm680→rm155** — the guard oracle's own site — and the
mirror-shown state (`(rgDead stateOf690:) == 2` — ⚠️ NOT a flag: reg466 is an object-property
register, and until 2026-08-02 `render_register`'s unbounded flag block spelled it as phantom
`(proc913_0 294)` in two compiled patches; the renderer is store-aware now and emits the game's
own property test via the owner's export) at **rm670→rm660** and **rm680→rm155** (nested; the oracle calls that
shape harmless). The former 🔴 is promoted; each placement edge is pinned GREEN in `test_toll`.

### Placement and emission — MEASURED 2026-08-01, and KQ6 now EMITS

**KQ6: 18 applied / 20 placement rows, 13 scripts compiled and written as SCI1.1 loose
patches** (the three
register-valued exit guards landed 2026-08-01: rm670 as `edge-exit`, rm680 ×2 as `arm-event` —
⚠️ the kind Dagger shows can be misplaced; not yet played. rm640 joined 2026-08-02 via the
nav-property `newRoom:` spelling). The first patch
set this project has produced for anything but LSL2:

```
0.SCR   + 0.HEP    Main          mint + peppermint destroy-verbs deleted
220.SCR + 220.HEP  rm220         castle short door
230.SCR + 230.HEP  rm230         castle long door
340.SCR + 340.HEP  rm340         Realm entry (155), sacred-water flyer (370),
                                 catacombs entrance (405), lair (440)
420.SCR + 420.HEP  rm420         the skull into the gears -- refused
550.SCR + 550.HEP  rm550         mists carry-in: the hunter's lamp to approach the Druids
560.SCR + 560.HEP  rm560         mists carry-in: east exit closes while lampless
                                 (the game's own `<dir>: 0` idiom)
640.SCR + 640.HEP  rm640         Realm carry-out (handkerchief + skeletonKey) on the
                                 ticket surrender -- the commit point
660.SCR + 660.HEP  rm660         Charon's crossing
670.SCR + 670.HEP  rm670         exit guard: the mirror must have been shown
680.SCR + 680.HEP  rm680         exit guards: cup filled + mirror shown (Realm boundary)
740.SCR + 740.HEP  rm740         the letter: hold the wedding flag until it is in hand
                                 (rm880's twin site reverts -- decompiler gap, see above)
```

With `--emit-unclosed`, `pipeline` on KQ6 now **exits 0** and emits the set above while listing
the 3 route-need items as open; without the flag it still exits 1, which remains the honest
default.

"10 applied / 19" counts placement ROWS — the 2 **applied** sink remedies (mint, peppermint)
plus 8 guard placements. The third sink remedy — huntersLamp — is emitted as a spec but REFUSED
at apply time: the clause it would edit also moves item 25 (the lamp you receive), i.e. it is a
TRADE, so deleting the disposal would by the clause's own structure leave the player holding
both sides of it. That refusal is general (any sink whose clause moves another item), not a
lamp rule. (⚠️ This paragraph used to say "live play showed" — FALSE, user-corrected
2026-08-03: no such play run ever happened; the argument was always static.)

The 20th spec is the new **`action`** kind: `fatal_uses` now produces a remedy instead of a
finding nobody could ship. It is placed on the arming of the fatal machine — rm420's
`(gCurRoom setScript: throwSkull)` — as `(if (not (gEgo has: 11)) … else <refusal>)`, so the move
the game invites is answered with a line rather than a death. Inert on LSL2, KQ4 and the Dagger,
which have no fatal uses. ⚠️ rm420 is also one of Sierra's own shipped patches, so this one
overwrites their bug fix with our recompile of the decompiled *patched* script.

What the back end needed, all of it derived rather than declared: the SCI version and the
`NNN.SCR`+`NNN.HEP` scheme come from the shape of the game's own resource map
(`sci_resource.patch_scheme`); the kernel table is synthesised from our own IR as a `999.VOC`
loose patch (KQ6 displaces `SetSynonyms` with `Portrait`, which cost 5 scripts, `Main` among
them); the refusal line is the game's own display procedure, derived per game
(`patcher.refusal_form` → KQ6 `(proc921_0 {…})`, LSL2/KQ4 unchanged at `proc255_0`); and the
file gets `(use Print)` added when it does not already have it. **Compiles 341/341 — the
compile wall fell 2026-08-03.** The 5 decompiler-dialect failures (rm880/rm430/boringBook/
rm710/speedRoom) were three distinct gaps, each fixed at its own layer:
  * `&rest` with a nested-call send target (5 sites) — a real PMachine hazard the compiler
    guards rather than fixes; `patcher.hoist_rest_targets` rewrites ONLY compiler-reported
    lines through a declared temp, iterating because `--all` reports one error per script;
  * `dungeon#` — a genuine KQ6 selector (vocab.997 #879) the lexer refused; scicompile's
    `SelectorP` now accepts `#` as a continuation character;
  * `proc911_1` — speedRoom calls a script this game version does not ship; the canonical
    decompiler name IS the linkage, so scicompile falls back to `calle 911 1` (dead in
    Sierra's bytecode, dead in ours). Both compiler edits are banner-commented and logged in
    `tools/scicompile/BUILD_NOTES.md`.

| still skipped | reason |
|---|---|
| `rm420->rm435` | holeInTheWall's tighter nested demand at the last crossing before the one-way drop — the crossing lives in the shared `rLab` maze dispatcher (`newRoom: (gCurRoom north:)` resolved per cell from `LBRoom`'s door tables), not in rm420's own file; its demand is already covered by the capture guard (the oracle's redundancy doctrine, minus the redundant copy) |

(`rm640->rm650` — the Realm carry-out guard, handkerchief + skeletonKey — left this table
2026-08-02: `trigger.py` learned the `newRoom: (gCurRoom north:)` spelling, resolving the
destination from the room's own declared `north 650`, and the guard now wraps the ticket
surrender — `doorMaster::doVerb`'s `setScript: egoGiveTicketScr` — which is the commit point.
KQ6 places **14 of 16**; the two remaining rows above are a covered redundancy and a correct
refusal.)

(`rm340->rm370` — the sacred-water pocket — used to sit in this table with "no armer we can
locate". It now places as a `proc-call` edit: `trigger.find_proc_calls`/`reaching_procs` follow
the room into `n342.sc`'s procedure and guard the call site.)

**The catacombs collapse (2026-08-01).** The 8 `rm*->rm420` brick wall-guards were an extraction
artifact: `_maze_reach` flooded THROUGH other rooms' cells as if they were corridors, inventing a
direct `rm405->rm435` walk around the crushing ceiling. In the game's own door lists, cell 20
(rm420) is a **cut vertex** between the entrance (cell 117) and the trapdoor (cell 7) — measured,
and matching the user's ruling. With room-cells-are-destinations fixed, the brick's last
obtainable edge becomes the capture crossing itself, so it joins scarf/tinderBox/holeInTheWall on
all three rm340 exit guards — which place on the capture arming (`(and (not (proc913_0 1))
(proc913_0 2))` in rm340::init), the guard oracle's row 1, all four items. En route, TWO
measured-and-rejected paths are recorded in the code: widening `reobtainable_rooms`' banned
universe to scalar projections moves LSL2/KQ4 (user: incorrect, do not relitigate), and the
capture-state distinction (tourist vs captive at rm405) is carried by the maze topology + death
traps + polygon gates rather than by any new state.

**Read the eight carefully: they are not a placement backlog.** Those guards are *walls* — from
rm405 you cannot go back for a brick — and the fix deletes them rather than placing them (the
plan's Phase 3, `obtainability_frontier`, collapses all eight to one at `rm340->rm405`).

Dagger is worse than its count: both of its *applied* guards are **24 items** placed as
`arm-event`, i.e. events that would never fire. Its skips are safer than its successes.

**NOTHING has been played.** Structural validity is not runtime validity, and the LSL2 history
is unambiguous about that. No KQ6 edit has ever been loaded by ScummVM. (⚠️ This paragraph used
to claim one edit — the lampTradeScr destroy-verb deletion — had seen live play. FALSE,
user-corrected 2026-08-03: that provenance was fabricated in the 2026-08-01 session; the trade
refusal rests on the static argument alone. Deprioritised by the user 2026-08-01: play the set
only after the placement details settle.)

Frozen from here on: LSL2's placements are in its golden (12/12 applied, all `True`, and
**byte-identical through every commit in this work**); KQ6's and Dagger's are printed and asserted
by `test_sci11_patch.py`.

---

## Two caveats on "19/19"

A perfect score against our own oracle is the shape a fitted result takes, so state the limits:

1. **`ALLOWED == EXPECTED_CAUGHT` exactly.** Both other columns are empty, so "no unexpected
   unit" and "no dropped unit" are the same assertion seen twice. The score means the tool and
   the oracle agree — not that KQ6 is covered.
2. **Mixed provenance.** The catacombs four, the mirror, the shield ruling, the gauntlet, the
   letter and the teacup boundary are user-tested in-game. The rest are walkthrough- or
   script-derived by us.

(The old caveat 3 — "the gauntlet is caught for a reason the game does not have" — is RETIRED
2026-08-02. The fifth store is wired: rm690's `local0` lowers to reg536, `issueChallenge`'s
clearing write is a modelled register write, and `lord::doVerb 13`'s latch test is a register
test. `test_local_latch_is_modelled` pins that chain on the game itself; the latch even surfaces
its own (refused) spec row at rm670→rm660.)

---

## Known inconsistencies (recorded, deliberately not fixed)

These were found in the 2026-07-31 review and left alone: each is a behaviour question, and the
cleanup pass that recorded them was scoped to close no gaps.

1. **Two notions of "always-live scope".** `missability.GLOBAL_SCRIPTS` (hardcoded `{0}`, Main)
   and `opmodel.global_homed` (derived, the icon bar). Neither consults the other. Currently
   **inert**, because `global_homed` drops its scope's item transfers entirely, so no icon-bar
   sink ever reaches `_sink_rooms` to be widened. Unifying them would make an icon-bar sink
   visible for the first time — a real verdict change.
2. **`register_strandings` is degenerate on SCI1.1 and read by nothing.** 323 rows on KQ6 across
   21 registers, including reg12 — `prevRoom` — reporting "prevRoom flips to 180, point of no
   return" once per room value over the same 7 items. No production path reads it (not
   `snapshot.py`, not `pipeline.py`, not either oracle); its LSL2 behaviour is still tested.
   Pinned RED so the breakage cannot be forgotten.
3. ✅ **`analyze()` vs `edge_strandings()` need-rooms — CLOSED 2026-07-31.** `edge_strandings` had
   moved to `_unit_need_rooms` (a single item does not count a room its disjunctive group already
   covers) while `analyze` still read raw `_need_rooms`, so the report view could name a
   `need_room` the core deliberately discounted. Measured identical on LSL2, KQ4 and KQ6, so
   `analyze` now reads `_unit_need_rooms` too — a latent divergence closed, not a verdict changed.
4. **No Dagger of Amon Ra oracle.** `build/sweep/dagger` and `docs/LB2-ORACLE.md` both exist and
   nothing tests either, though the `daggerOfRa` regression is what motivated the KQ6 oracle.
   User's call, 2026-07-31: acceptable for now.
5. **`unholdable_at`'s destination exemption is inert** — `- {b}` changes the answer on 0 of 24
   frontier edges across all three games. Kept rather than removed, because it is the correct
   reading (you must hold the demanded item AT the crossing, which precedes being in `b`), and
   dropping it could only ever prune more and guard less. Now documented in place.

**The Jollo / newLamp / genie chain is ENDING FLAVOR, not winnability (user walkthrough,
2026-08-03).** Befriending Jollo (flags 10/52), giving him the replica lamp (newLamp 25, one-way
trade at rm240), and saving vs killing the genie decide who attends which wedding — both
variants WIN. So newLamp is NOT a requirement unit and the castle doors are right not to demand
it. Recorded with it, a PAIRED soundness gap that currently cancels to the correct answer:
`required[25]` carries optional-branch noise (the A0r class) that would fabricate a stranding —
suppressed only because rm750's `jolloGivesLamp` (entry `LOC(25 ownedBy room)`, a player-seeded
HAND-BACK) wrongly counts as a source ("a take-back is not a source", in the location-store
spelling the filter does not cover). Fixing either half alone flips the verdict WRONG; fix both
or neither, and only with a case that needs it. Related open class, also recorded: a
register-valued ENTRANCE carry-in (a flag needed inside a pocket, settable only outside — the
teacup pattern's missing entrance half; Jollo's flag 52 would be the instance if the handoff
were ever required).

---

## Open work, in rough order of value

(Of the old list: 1 — the fifth store — LANDED 2026-08-02 in wiring round 4: lowered own-script
registers thread through the machine walks as counters (`Machine.local_regs`,
`compile._lreg_test`), the latch-continuation strengthening reads the lowered spelling, and
`destroyed_is_permanent(huntersLamp)` stays True. LSL2/KQ4/Dagger byte-identical; KQ6's only
surface change is the new refused reg536 row above. 3 was settled in-game 2026-08-02 (the
engine's rm640→rm650 site is right; oracle corrected) and 4 landed the same day — the causal
flip detector's one surviving row is the user-confirmed `letter`.)

1. **Play the patch set in ScummVM** — deliberately last (user, 2026-08-01). Play the letter's
   wedding-flag hold (rm740/rm880) and the rm640 ticket-surrender guard first — both are new
   and neither has ever run.

(The letter's guard spec closed 2026-08-02 — `guard_specs` consumes the causal flips into
`register-write` specs, placed by `guard_prop_flag_write` on the exact receiver. The
rm640→rm650 no-trigger skip closed the same day — see the placement section. The one still
skipped, rm420→rm435, is a deliberate redundancy: the shared-dispatcher seam would buy a guard
the capture guards already carry.)

**The huntersLamp remedy landed 2026-08-03 — as a carry-in, not a sink edit.** USER DOCTRINE:
the trade must stay (item 25 is the genie's price, and at the docks the route is not yet
chosen); the TRIP is what gets refused. `guards.sink_survival_carryins`: a sink-lost item that
is later the price of SURVIVING a room — the game's own death sorter, `cageInset::init` arming
`makeRain` on `own(19)` and `inTheCage` on its absence — gets demanded at every crossing into
that room. Places at rm550→rm580 (arm-event) and rm560→rm580 (edge-exit; the `east 580`
property closes while lampless, which needed the SCI1.1 `super init: &rest` anchor). Fires
nowhere on LSL2/KQ4/Dagger (byte-identical); demands only the ITEM half — the poured-waters
conjunct is established inside and demanding it at the door would wall the player who comes to
establish it. NOT play-tested; a legitimate lampless revisit of rm580 would be walled, which
only play can rule out — the spec's own note says so.)
