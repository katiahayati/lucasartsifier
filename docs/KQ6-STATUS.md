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
caught set and the snapshot surface with it. No guard spec exists for the letter yet.

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
| guard specs | 15 total — **13 emitted, 2 refused** (14 edge + 1 `action`) |
| the 2 refusals | the `flag == 0` half-questions (demand the mirror flag CLEAR) — they pair with no entrance guard and would close no softlock; refused with the reason stated |
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

**KQ6: 13 applied / 16, 8 scripts compiled and written as SCI1.1 loose patches** (the three
register-valued exit guards landed 2026-08-01: rm670 as `edge-exit`, rm680 ×2 as `arm-event` —
⚠️ the kind Dagger shows can be misplaced; not yet played). The first patch
set this project has produced for anything but LSL2:

```
0.SCR   + 0.HEP    Main          mint + peppermint destroy-verbs deleted
220.SCR + 220.HEP  rm220         castle short door
230.SCR + 230.HEP  rm230         castle long door
340.SCR + 340.HEP  rm340         Realm entry (155), sacred-water flyer (370),
                                 catacombs entrance (405), lair (440)
420.SCR + 420.HEP  rm420         the skull into the gears -- refused
660.SCR + 660.HEP  rm660         Charon's crossing
670.SCR + 670.HEP  rm670         exit guard: the mirror must have been shown
680.SCR + 680.HEP  rm680         exit guards: cup filled + mirror shown (Realm boundary)
```

With `--emit-unclosed`, `pipeline` on KQ6 now **exits 0** and emits the set above while listing
the 3 route-need items as open; without the flag it still exits 1, which remains the honest
default.

"10 applied / 19" counts placement ROWS — the 2 **applied** sink remedies (mint, peppermint)
plus 8 guard placements. The third sink remedy — huntersLamp — is emitted as a spec but REFUSED
at apply time: the clause it would edit also moves item 25 (the lamp you receive), i.e. it is a
TRADE, and live play showed that deleting the disposal hands the player both sides of it. That
refusal is general (any sink whose clause moves another item), not a lamp rule.

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
file gets `(use Print)` added when it does not already have it. **Compiles 336/341** — the 5 that
do not are decompiler-dialect issues in scripts we do not edit.

| still skipped | reason |
|---|---|
| `rm420->rm435` | holeInTheWall's tighter nested demand at the last crossing before the one-way drop — a maze edge with no call site; its demand is already covered by the capture guard (the oracle's redundancy doctrine, minus the redundant copy) |
| `rm640->rm650` | the Realm carry-out guard (handkerchief + skeletonKey) — same no-trigger seam; the finding it closes is real and `verify` counts it closed in the model |

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

**Mostly not yet played.** Structural validity is not runtime validity, and the LSL2 history is
unambiguous about that. The one edit that HAS seen live play — the lampTradeScr destroy-verb
deletion — handed the player both lamps, which is where the trade refusal above came from.
Everything else has not been loaded by ScummVM. (Deprioritised by the user 2026-08-01: play the
set only after the placement details settle.)

Frozen from here on: LSL2's placements are in its golden (12/12 applied, all `True`, and
**byte-identical through every commit in this work**); KQ6's and Dagger's are printed and asserted
by `test_sci11_patch.py`.

---

## Three caveats on "18/18"

A perfect score against our own oracle is the shape a fitted result takes, so state the limits:

1. **`ALLOWED == EXPECTED_CAUGHT` exactly.** Both other columns are empty, so "no unexpected
   unit" and "no dropped unit" are the same assertion seen twice. The score means the tool and
   the oracle agree — not that KQ6 is covered.
2. **Mixed provenance.** The catacombs four, the mirror, the shield ruling, the gauntlet and the
   teacup boundary are user-tested in-game. The rest are walkthrough- or script-derived by us.
3. **The gauntlet is caught for a reason the game does not have.** We keep it because
   `issueChallenge` writes an incidental register (which death message you get). The real link
   runs through a room LOCAL gating `lord::doVerb 13`, which we do not model at all. Right
   verdict, wrong reason, and pinned RED so it cannot look better founded than it is.

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

---

## Open work, in rough order of value

(1 and 2 of the old list LANDED — commitment 2026-08-01, the last three guards 2026-08-02. The
"per-route notion of need" turned out unnecessary: carry-out placement + two stranding-row rules
closed all three without expressing routes at all.)

1. **Room locals: wire the fifth store.** The representation exists
   (`vocab.derive_room_locals` / `lower_room_locals`) and is deliberately unwired; three
   consumers need reset-aware semantics first — `_reg_cost` (0 is start-of-VISIT, not free, for
   a reset register), `render_register` (bound the flag block), `death_traps` (re-entry is not
   an escape). Measured wired-in it loses KQ4's whale items and KQ6's huntersLamp.
2. **The two no-trigger placement skips** (`rm420->rm435`, `rm640->rm650`) — the trigger seam
   for maze/realm edges with no `newRoom` call site.
3. **Settle the rm640→rm650 vs rm680→rm155 divergence** with the guard oracle (is the Realm
   interior really one-way past rm650?) — an in-game question.
4. **register_strandings' prevRoom degeneracy** — derive PLOT-state registers; pinned RED.
5. **Play the patch set in ScummVM** — deliberately last (user, 2026-08-01).
