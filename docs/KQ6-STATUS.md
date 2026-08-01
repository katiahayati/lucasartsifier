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

## Detection — 18 requirement units, oracle 16/16

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

## Patching — this half is NOT done

| | |
|---|---|
| guard specs | 19 total — **15 emitted, 4 refused** |
| the 4 refusals | all pocket **exit** guards (fill the cup at rm155→200, hold up the mirror at rm670→660) |
| sink remedies | 3 emitted — delete the mint, peppermint and huntersLamp destroy-verbs |
| `verify()` | fixed 7 + 1 group · **NEW 0** · **remaining 3** |
| remaining | `handkerchief`, `nightingale`, `skeletonKey` |

**`python -m pipeline <kq6> --report` therefore exits 1.** It fails at stage 3 (DERIVE), because
`pipeline.main` treats a non-empty `remaining` as a failure. End-to-end KQ6 is red, and that is
an accurate report of the state rather than a bug in the reporting.

**Why the 3 remain, and why that is correct.** `guards.unholdable_at` drops them from the castle
doors because you cannot be holding them when you cross: the handkerchief and the skeleton key
exist only inside the Realm of the Dead, and reaching the short door costs Beauty's clothes,
which rm580's Druids burn; the nightingale IS the paint brush after three trades, so the long
door cannot demand both. Detection is right. There is nowhere to put the guard. Demanding them
anyway would not close a softlock — it would wall the route, which this project holds to be worse.

**Why the 4 exit guards are refused.** In-room register writes are modelled permissively, so no
crossing ever *commits* the flag: the walk believes the pocket can be re-entered with its seal
clear and the flag set on a second visit. Refusing is the safe direction — placing the guard
anyway would seal in a player who cannot comply where it sits. Pinned RED in `test_toll`.

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

1. **Place the 3 remaining guards.** Needs a per-route notion of need — "which of two winning
   routes are you on" — which nothing in the model can express today. See `SCI11-PATCHING-PLAN.md`.
2. **Commit-modelling for in-room register writes**, which is what makes all 4 exit guards
   placeable and closes the teacup's second half.
3. **Room locals in the machine model** — 3rd recorded instance of the gap (`liftTapestry`'s L1,
   `huntersLamp`'s rm520 `doit`, rm690's `lord::doVerb`).
