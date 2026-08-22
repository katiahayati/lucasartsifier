# The Quest for Glory blow-up: measured, 2026-08-21

The README's *Future work* has said since the first release that "QFG games have SO MUCH going
on that the analyzer cannot complete", guessing the cure is "abstracting away from player stats,
combat, and health consumables". This is what a measurement says instead.

Everything here comes from probes run against the decompiled IR already under
`build/sweep/qfg{1,2,vga}/`. **No file in `src/` was changed**, no patch was built, and the five
gating titles were only read. Every run was capped (`ulimit -v`, `nice`, `timeout`) so nothing
could swap the machine. The comparator throughout is KQ6 — same engine generation, a *larger*
script tree, 40s cold.

> ⚠️ A first pass of this analysis over-counted by a factor of ~10⁵ on some titles: its path
> estimator descended into leaf nodes, while `compile._paths_of` returns exactly one path for a
> leaf and never looks inside it. The numbers below are from the corrected estimator, validated
> against the real enumeration on KQ6 (predicted 9,776 / measured 9,822) and KQ5 (predicted 0
> bodies over `PATH_CAP` / measured 0, max 936).

## 1. It is not a state explosion

At the point the movement model is assembled, QFG-VGA is the same order as KQ6 on every
dimension the state space is made of:

| | KQ6 | QFG-VGA |
|---|---:|---:|
| rooms | 86 | 120 |
| items | 47 | 44 |
| gating registers (`gating_registers`) | 130 | 253 |
| register value domains, summed | 440 | 721 |
| widest single register domain | 89 | 121 |

Twice the registers does not make a title unbuildable. "State explosion" names the wrong object.

## 2. What explodes is the LEAF-PATH enumeration in cutscene bodies — and only under inlining

`compile._paths_of` enumerates every straight-line path through a machine state body, and
`opmodel._machine_info` runs it on each body **after** splicing in the bodies of the procedures
that body calls (`_inline_calls`, depth ≤ 6, across scripts).

Leaf paths summed over every machine state body of each title, with the pipeline's own lowering
applied, counted arithmetically so nothing has to be materialised:

| title | bodies | paths, no inlining | paths, as the emitter inlines | amplification | bodies over `PATH_CAP` (4,000) |
|---|---:|---:|---:|---:|---:|
| LSL2 | 1,800 | 2,228 | 2,452 | ×1.1 | 0 |
| KQ4 | 1,706 | 2,420 | 2,584 | ×1.1 | 0 |
| KQ5 | 4,563 | 5,624 | 16,611 | ×3.0 | 0 |
| KQ6 | 6,810 | 8,697 | 9,776 | ×1.1 | 0 |
| LB2 | 2,506 | 3,831 | 4,337 | ×1.1 | 0 |
| **QFG1** | 3,172 | 12,745 | **650,517,831,659** | **×51,041,022** | **26** |
| **QFG2** | 4,164 | 268,101 | **1,958,488,525,783** | **×7,305,040** | **114** |
| **QFG-VGA** | 4,365 | 18,334 | **1,008,847,644,218** | **×55,026,052** | **157** |

Read the two path columns side by side. **Uninlined, QFG-VGA is KQ6-scale** — 18,334 paths, one
body over the cap. The entire blow-up is created by one step, and the five titles we build pay
between ×1.1 and ×3 for that same step.

Why there and not on KQ6 — QFG is written through procedures to a degree no other title
approaches. Resolved procedure call sites:

| lsl2 | kq4 | kq6 | dagger | qfg1 | qfg2 | qfg-vga |
|---:|---:|---:|---:|---:|---:|---:|
| 3,131 | 3,535 | 2,054 | 1,783 | **9,022** | **7,461** | **5,058** |

…and the procedures are wide where KQ6's are not. Leaf paths in a procedure's own body, with
nested calls inlined: KQ6's 158 procedures top out at **32**, none over 1,000; QFG-VGA's 237 top
out at **30,188,315,015**, with 14 over 1,000 and 8 over 100,000.

## 3. Which procedures — leave-one-out

Suppress one procedure from inlining (its call becomes one opaque step) and recount every body.
QFG-VGA, baseline 1.009 × 10¹² over 157 over-cap bodies:

| suppressed | own width | call sites | total after | bodies > 4k |
|---|---:|---:|---:|---:|
| — *(baseline)* | | | 1,008,847,644,218 | 157 |
| `proc814_15` — **the skill check** | 394,560 | 70 | **167,346,226** | 150 |
| `proc814_17` — **stamina drain** | 2,054 | 10 | **176,262,058** | 151 |
| `proc7_0` — rest / time passage | 29,367,280 | 7 | 1,008,700,807,823 | 152 |
| `proc814_3` — turn-to-face helper | 192 | **344** | 1,001,595,449,663 | **20** |
| `proc0_3` — hands-on / restore control | 48 | **441** | 1,001,709,951,571 | **36** |
| **top 14 together** | | | **2,503,072** | **3** |

Two different jobs. `proc814_15` and `proc814_17` own the **depth** — either one alone takes the
title from 10¹² to ~10⁸, a 6,000× drop, because they are two links of the same chain (the check
calls the drain). `proc814_3` and `proc0_3` own the **breadth** — tiny bodies called from 344 and
441 sites, and suppressing either takes the over-cap population from 157 to 20 and 36.

`proc814_15` is QFG's skill check, and its siblings are the stat mutators:

```
(procedure (proc814_15 param1 param2 param3 ...)          ; (skill, difficulty, bonus)
    (if (not (= temp0 [global125 param1])) (return 0))     ; global125 = the hero's skill array
    (if param2 (if (>= param1 5) (proc814_17 (/ param2 10)))     ; stamina cost
        else   (if (>= param1 5) (proc814_17 (Random 1 6))) ...)
    (if (>= (localproc_0 4 1) (Random 1 200)) (+= temp0 (Random 1 20)))   ; luck
    (= temp3 (<= param2 temp0))                            ; the roll
    ...
    (proc814_16 param1 (/ temp2 temp1))                    ; ...and the skill GOES UP for trying
    (return temp3))
```

`proc814_16` raises the skill (`+= [global125 param1] (Random 1 3)`, capped at 100), `proc814_17`
drains stamina, `proc814_19` health, `proc814_24` casts a spell (mana check → skill check → mana
drain).

The same routine is the top amplifier in the other two titles, line for line: QFG1 `proc0_30`
(reached for spells through `proc0_41`, 54 and 62 call sites) over `[global139 n]`, and QFG2
`proc2_7` (62 call sites) over `[global571 n]`. Suppressing QFG1's takes it from 6.5 × 10¹¹ to
3.6 × 10¹⁰; suppressing QFG2's takes it from 1.96 × 10¹² to 1.0 × 10¹².

## 4. Combat or adventure? Both, and not where the README guessed

* **Deepest is combat and skill use.** The top bodies are `flameDart` (rm14, saturated at the
  10¹² counting cap), `sThrowDagger` (rm73, 7.3 × 10⁹), `egoThrust` (`closeCombat`, 1.4 × 10⁹),
  then `egoBlock`/`egoDodge`/`egoParry`, `castOpen`, `sThrowRock`. Script 215 (`closeCombat`)
  alone is 1.39 × 10⁹.
* **Broadest is the adventure rooms.** The 157 over-cap bodies sit in **52 scripts**, and only
  **7** of them are in a named combat/arena/spell script and **2** in the sleep scripts. The
  other **148 are ordinary room scripts** — rm54 (13 bodies), rm73 (9), rm93 (9), rm84 (9), rm16
  (7), rm40 (6), rm170 (6), rm67 (6). That is a statement about where the code LIVES, not about
  two separable systems: rm73's hot body is `sThrowDagger`, rm54's is `sThrowRock`, rm14's is
  `flameDart`, rm40's is `sleeper`. The RPG layer has no script of its own to carve out.
* **The skill check is called from adventure code more than from combat code.** Its 72 call
  sites: 17 in combat/encounter/spell scripts (`egoFight` 8, `closeCombat` 4, `Encounter` 2,
  `castDazzle` 2, `dartScript` 1), **47 in ordinary room scripts**, 8 in engine scripts. In QFG
  the adventure verbs *are* skill rolls: rm54 decides a puzzle on `(proc814_15 9 10 0)`, rm13 on
  `(proc814_15 9 0 global175)`, rm54 again on `(proc814_15 11 30 0)`.
* **The rest/recovery clock is the other RPG contributor.** `proc7_2` (sleep 1/3/6/… hours) →
  `proc8_0` (advance the day, restore stamina/health/mana) gives `sleeper` (rm40), `goToSleep`
  (rm10), `sGoSleep` (rm83), `SleepAllNight` and rm302 29,367,280 paths each.
* **Two of the four top amplifiers are not RPG at all.** `proc814_3` (turn-to-face, two switches
  over the ego's loop) and `proc0_3` (hands-on: re-enable the icon bar and the cursor at the end
  of a cutscene) are plain presentation code, and between them they own most of the breadth.

So the README's plan — abstract away stats, combat and consumables — removes the deepest bodies
and still leaves ~20-36 over-cap bodies behind two ubiquitous helpers. The RPG layer *is* the
largest single cause, and it is **not a separable subsystem**: it is spread through the adventure
rooms because in QFG climbing, throwing, sneaking and haggling are skill rolls.

## 5. …and the stats never become state anyway

`[global125 <skill>]` is an indexed global — a `ComplexVariable`. `extract.atom` has no reading
for it, so every stat comparison lands as `Pred("OPAQUE")`. Predicate kinds in the guard trees
the emitter hands downstream (leaf paths truncated to 300 per state, so these are lower bounds):

| guard predicate | KQ6 | QFG-VGA |
|---|---:|---:|
| `OPAQUE` | 6,530 | **1,382,121** |
| `CMP` | 3,919 | 777,074 |
| `OWN` (what softlock detection reads) | 112 | 2,925 |

About two thirds of QFG's guard predicates are conditions the analysis has already decided it
cannot interpret. The enumeration pays in full to fan out branches it cannot read — which is why
"abstract the stats away as state" aims at the wrong half. They are *already* abstracted away as
state. It is their **code** that is being enumerated.

## 6. Where the process actually dies — three walls, in order

Measured on QFG-VGA, each wall reached only after the previous one was worked around in the probe.

1. **`compile._seq`, `MemoryError` at ~60s.** `PATH_CAP` is tested *after* the product is built:
   `nxt` is filled with `len(res) × len(subs)` lists and only then does `if len(res) > PATH_CAP:
   break` fire. With `res` at the cap and a wide `cond`/`switch` sub-body that is one
   multi-billion-element allocation. `_paths_of(f)` is also re-evaluated once per prefix inside
   the inner loop, so a wide sub-path list is rebuilt up to `PATH_CAP` times.
2. **`opmodel._machine_info`, `MemoryError`**, building `Step` objects and their guard trees
   (`extract.atom`) for the enumerated paths.
3. **`missability.edge_meta` → `state_musts`** — the wall that never OOMs, it just does not
   finish. With paths truncated to 300 per state (well below the real cap) the emitter builds in
   59s and then:

   | | KQ6 | QFG-VGA |
   |---|---:|---:|
   | machine paths | 10,191 | 167,674 |
   | guard nodes over those paths | 39,373 | 4,298,740 |
   | mean guard size | 3.9 | 25.6 |
   | `_own_positive` + `guard_reqs` over every edge and exit | <0.1s | <0.1s |
   | **`state_musts` over every machine** | **1.8s** | **697.5s** |
   | `entry_alts` / `entry_reqs` | 0.1 / 0.2s | 2.0 / 0.1s |

   `edge_meta` calls `state_musts` **twice per machine** (once to fill `_musts`, once as `sm`),
   so that is ~23 minutes of a truncated build. The hot machine is `forestRegion`'s `walkIn`
   (script 804) at ~9s per instance.

   The cause is not the guard walk itself — `guard_reqs` over all 3,414 machine exits, all 253 registers at once, is under 0.1s.
   It is `state_musts`'s inner loop, `for R in regs: required_values(g, R)`, where
   `required_values` is `guard_reqs(guard, (reg,))`: **a full walk of the guard tree per
   register**, 253 walks per path on QFG against 130 on KQ6, over guards 6.6× larger, on 16×
   more paths. That is exactly the cost `guard_reqs` documents itself as avoiding ("One walk of
   the guard tree for ALL the registers … walking it once per register made edge_meta 19x
   slower"), re-introduced by its own single-register wrapper.

## 7. What to do about it, in payoff order

Not implemented. None of it is safe to land without the usual full-surface regression
measurement on LSL2/KQ4/KQ5/KQ6/LB2.

1. **Bound the inliner, not the enumerator.** Refuse to inline a procedure whose body's leaf-path
   count exceeds a threshold; leave the call as one opaque step. Measured: suppressing the top 14
   takes QFG-VGA from 1.009 × 10¹² to 2,503,072 and its over-cap bodies from 157 to 3. On the
   five titles we build the whole inlining step is worth ×1.1–×3, so a threshold anywhere above
   a few thousand cannot move them. Soundness is the permissive direction the codebase already
   prefers, and for the skill-check family nothing readable is lost — those branches are already
   `OPAQUE`.
2. **Enforce `PATH_CAP` inside `_seq`'s product**, and hoist `_paths_of(f)` out of the prefix
   loop. Pure bug fix; no title we build reaches the cap (max product width: LSL2 3, KQ5 936,
   KQ6 579), so it cannot move any golden.
3. **One guard walk per path in `state_musts`** — `guard_reqs(g, regs)` once instead of
   `required_values(g, R)` per register — and hoist the duplicated `state_musts` call in
   `edge_meta`. Pure speedup, no semantic change, and it is paid by every title today.

None of these is QFG-specific, which is the point: 1 and 2 are latent on any title written
through wide shared procedures, and 3 is a cost we already pay everywhere.

---

# 8. A derived answer: "this subtree cannot discriminate"

Added 2026-08-21, after the analysis above. The question that prompted it: *is there a way to
cleanly derive that we don't care about the skill check, without caps or hand-declarations?*

There is, and it does not mention QFG, a procedure, a stat, or a number.

## 8.1 The derivation

Ask the interpreter what it keeps. `compile._interp` folds a path into a `Step`, and it records
exactly six kinds of thing:

* an exit (`newRoom:`), a self-`changeState:`, or a `state`/timer property write
* an item transfer (`extract.item_transfers`)
* a cue arm (`_count_cues_send`, a timer property, or a `(procN ... self)` call)
* a constant write to a plain global
* a local/temp/global counter op
* and, from a TEST, whatever `_ctr_or(node, pol, atom(node))` yields

Everything else in a path — every send it does not recognise, every assignment to something it
does not model — falls through all of `_interp`'s branches and contributes **nothing**.

So: **a subtree containing none of those produces the same `Step` on every path through it.**
Its paths differ only in `Pred("OPAQUE")` conjuncts, and nothing downstream reads more than
their PRESENCE — `missability._has_opaque` asks a boolean, `opmodel` projects opaques out of a
conjunction and treats an opaque disjunct as satisfiable. One path can therefore stand for all
of them, carrying one opaque marker so `_has_opaque` sees exactly what it saw before.

That is the whole rule. It is a property of `_interp`, not of Quest for Glory, and it needs no
threshold: a subtree either can discriminate or it cannot.

## 8.2 It has to be derived from `_interp`, not from something that looks like it

The first version of this predicate asked `extract.atom(test)` — a reasonable-looking stand-in
for "can we read this test". It cost **KQ5 its market squeeze**: the Golden_Needle and Gold_Coin
`starves rm[5, 9, 13]` rows, and the `getSled`/`getPie` sink rows with them.

`_interp` does not append `atom(node)`. It appends `_ctr_or(node, pol, atom(node))`, and
`_ctr_or` turns a Local/Temp-vs-literal comparison into a `("CTR", …)` atom that the machine
walk resolves **concretely**. Those are the machine-internal latches — a shop slot, a
which-branch-did-we-take flag — and calling them unreadable collapsed exactly the branches that
discriminate. Asking the composition instead restores every row.

The lesson is the project's own: derive the predicate from the consumer's code, and measure. A
plausible predicate and the real one differed by one function call and by one shipped finding.

## 8.3 Measured — the five gating titles do not move

`snapshot.py <game> --no-placements`, stock against the rule installed at runtime, cold models
both sides (`SOFTLOCK_NO_MODEL_CACHE=1`):

| title | `_paths_of` calls collapsed | full analysis surface |
|---|---:|---|
| LSL2 | 6,763 / 18,329 | **byte-identical** |
| KQ4 | 11,690 / 38,525 | **byte-identical** |
| KQ5 | 45,141 / 124,649 | **byte-identical** |
| KQ6 | 28,564 / 107,951 | **byte-identical** |
| LB2 | 27,027 / 121,908 | **byte-identical** |

Between a fifth and a third of every title's path enumeration is provably redundant work, and
removing it moves nothing.

## 8.4 Measured — what it does to QFG

Leaf paths summed over all machine state bodies, with the rule and without:

| title | without | with the rule | reduction | bodies over `PATH_CAP` |
|---|---:|---:|---:|---:|
| LSL2 | 2,452 | 2,370 | ×1.0 | 0 → 0 |
| KQ4 | 2,584 | 2,438 | ×1.1 | 0 → 0 |
| KQ5 | 16,611 | 8,845 | ×1.9 | 0 → 0 |
| KQ6 | 9,776 | 8,374 | ×1.2 | 0 → 0 |
| LB2 | 4,337 | 3,490 | ×1.2 | 0 → 0 |
| **QFG1** | 650,517,831,659 | **270,508** | ×2,404,900 | 26 → 5 |
| **QFG-VGA** | 1,008,847,644,218 | **65,208** | ×15,471,225 | 157 → 2 |
| QFG2 | 1,958,488,525,783 | 105,139,402,192 | ×19 | 114 → 48 |

QFG-VGA and QFG1 land at KQ6 scale. **QFG2 does not**, and the residue is one body: `bedSleep`
state 1 in `bedroom.sc` (script 101) at 1.05 × 10¹¹, the "how long do you wish to sleep?" dialog,
whose arms call `proc2_6` (662M paths) and `proc2_5` — the day/time advance. Everything else in
QFG2 falls to ≤ 3.3M.

That residue is a **different** problem and should not be solved with this rule. Its fan-out is
over things `_interp` genuinely records: a long sequence of independent guarded register writes,
whose product really does have 10¹¹ combinations. The shape that fixes it is representing a
state's contribution as a set of guarded assignments rather than as an enumeration of their
combinations — a change to what a `Step` IS, not to which paths are worth walking. Not attempted
here.

## 8.5 QFG-VGA now completes — and that is NOT a clean bill of health

With the rule installed and **no cap, no truncation**, `snapshot.py qfgvga --no-placements` ran
to completion for the first time: **~42 minutes, 1.5 GB peak**, 615,731 of 1,385,411 `_paths_of`
calls collapsed. The three walls of §6 are all gone — `_seq` never blows up, `_machine_info`
holds at 800 MB, and `edge_meta` returns.

`state_musts` is what is left: **495.0s** for all 1,246 machines (against 697.5s on the truncated
build and KQ6's 1.8s), and `edge_meta` still calls it twice per machine — about 16 of the 42
minutes. That is §7's third item, untouched here; fixing it should take the run well under ten
minutes.

⚠️ **The result it produced is not usable, and the reason is anchors, not paths.** What it
derived:

```
start_room  2      = noticeRoom            (the copyright notice screen)
goal_rooms  425 430 435 440 445 450 455 460 465 601
                   = minotaurArena, saurusArena, mantrayArena, cheetaurArena,
                     goblinArena, trollArena, ogreArena, dragonArena,
                     brigandArena, and CharSave
softlock_items  []
```

The ten "victory rooms" are the **combat arenas** and the character-save screen. `anchors.discover`
looks for rooms that are terminal, reachable and never fatal; QFG's arenas are entered as SCRIPTS
through `(ScriptID global279 0)` rather than by `newRoom:`, so nothing the model sees ever leaves
them, and they read as terminal. **`softlock_items: []` therefore says nothing about Quest for
Glory** — every requirement question is answered against goal reachability, and this goal set is
wrong. Reporting it as "QFG has no softlocks" would be the exact mistake the codebase already
refuses for an EMPTY goal set (`missability._build` raises there); a WRONG one is not currently
caught at all.

So the blow-up is solved and the next problem is visible behind it: anchoring a title whose
end-game lives in script-armed arenas. That is its own derivation, not a variation on this one.

## 8.6 Status

The rule is a probe (`_paths_of` patched at runtime), **not a change to `src/`**. What it has
earned: five byte-identical analysis surfaces, and a QFG-VGA run that finishes. What it has not:
the placement half of the snapshot, `tools/run_tests.py`, a QFG2 answer (§8.4), and any claim
whatever about QFG's actual softlocks (§8.5).
