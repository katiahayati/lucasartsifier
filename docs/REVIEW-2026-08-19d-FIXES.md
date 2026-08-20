# The 2026-08-19d contextless review — fix plan and scoreboard

A single contextless agent review critiqued the two features shipped on 2026-08-19d (the castle
cat's `fuse_death_armings` and the henchman's `capture_fold_armings`) on three axes:
derivability, overfitting, correctness. It found **15 findings**, including two latent
CRITICALS in the new patcher appliers and a real derivability defect in the fuse classification.

⚠️ **None of this breaks the shipped KQ5 patch** (v17, play-verified). The criticals are LATENT
— KQ5's sites happen to be the shapes the buggy code handles. Everything else is derivability
and generality: rules that are right on KQ5 for reasons the code does not establish.

**Discipline** ([[commit-rule-and-red-tests]]): every fix gets a test that goes **RED on the
committed code first**, asserting the CORRECT behaviour — never the bug as the expected value.
Latent findings get synthetic fixtures, because a game states the failure mode only if the game
happens to have one (the `test_deletion_soundness.py` doctrine).

**Regression floor** ([[measure-regressions-full-surface]]): LSL2 + KQ4 + KQ6 goldens and the
LB2 watched surface must stay byte-identical on the FULL `snapshot.py` surface (placements
included), and KQ5's two shipped conditions must not move — they are play-confirmed:

    fuse-arm    (and (proc0_12 63) (gEgo has: 24) (or (proc0_12 62) (gEgo has: 37)))
    capture-arm (or (and (not (proc0_12 96)) (== ((gInv at: 25) owner:) 57))
                    (and (gEgo has: 24) (not (== ((gInv at: 24) cel:) 4))))

---

## Order of work

1. **the two text criticals + tests for both appliers** (F1, F2, F14) — safety, and cheapest
2. **rebuild the fuse classification on the DECREMENT** and delete the self-re-arm special case
   (F4, F3)
3. **the soundness trio + the anti-wall gate** (F7, F8, F9, F10, F11)
4. **the nits and the story** (F5, F6, F12, F13, F15, and docs/KQ5-ORACLE.md §23)

---

## Scoreboard

| # | Finding | Where | Test | Status |
|---|---------|-------|------|--------|
| F1 | `_enclosing_if_test` ignores the `else` branch — an arming in the else INVERTS the guard | `patcher.py` | `test_patch_text` | ⬜ |
| F2 | `fuse-arm` wraps the FIRST `(if` in the procedure, not the one containing the spawn | `patcher.py` | `test_patch_text` | ⬜ |
| F3 | the "clock" docstring is FALSE about what the code tests (`local8`, not `local5`; `GetTime` never reaches the spine) | `missability.py` | (with F4) | ⬜ |
| F4 | `cds` is "every register compared nonzero", NOT the countdown — root cause of the self-re-arm overfit clause | `missability.py` | `test_fuse_classification` | ⬜ |
| F5 | `capture-arm` only lands because an UNRELATED spec edited the site first | `patcher.py` | `test_patch_text` | ⬜ |
| F6 | the wrap sits inside `init` after `(super init:)` — a refused arming leaves the object cast-resident with `script == 0` | `patcher.py` | `test_patch_text` | ⬜ |
| F7 | neither new remedy has an ANTI-WALL gate, unlike its sibling `fold_carryins` | `guards.py` | `test_fuse_classification` | ⬜ |
| F8 | `_fold_disarmed` reads the entry DISJUNCTION conjunctively; and only tests `folds[R][0]` | `missability.py` | `test_deletion_soundness` | ⬜ |
| F9 | cannot tell LIGHTING a fuse from TOPPING ONE UP | `missability.py` | `test_fuse_classification` | ⬜ |
| F10 | the fixpoint is right for a reason the game does not implement; `price()` never checks whether a chain write FALSIFIES the continuation's arming | `missability.py` + §23 | `test_fuse_classification` | ⬜ |
| F11 | discharging is applied to NEGATIVE flag demands too — an unsatisfiable alternative reads as free | `missability.py` | `test_deletion_soundness` | ⬜ |
| F12 | `if (a for a in ...) and not alts:` — a generator is always truthy | `guards.py` | `test_fuse_classification` | ⬜ |
| F13 | `procs[0]` under-guards a second spawning procedure; `emitted` key is cross-room while `demand_alts` is per-room | `missability.py` | `test_fuse_classification` | ⬜ |
| F14 | neither applier nor `_enclosing_if_test` has ANY test | `test_patch_text` | — | ⬜ |
| F15 | dropped non-flag `context`; polarity-blind `_entry_rooms`; `_balanced_span` has no string handling; no memoisation; game-wide `fuse`/`death` | both | mixed | ⬜ |

## What the review ENDORSED (do not undo)

The shared `_Escapes` refactor; conditions written in the GAME'S OWN spelling rather than a
project alias; and the `fuse-arm` PLACEMENT — a refusal indistinguishable from the stock 20%
no-spawn roll, "strictly better than the `capture-arm` placement it shipped alongside".
