# TODO

One line each. `src/examples.py` is the live catalogue (red until the gaps below close);
`REVIEW-FIXES-TESTPLAN.md` has the test-per-fix detail for the code-review items.

## Open examples (turn `src/examples.py` green)
- [ ] **Disguise gate (rm47)** — model the henchStatus / `doit`-edgeHit / actor-chase death-gate so crossing the KGB beach requires the bikini+wax.
- [ ] **Bomb (rm82)** — the gate lives in the PIC control map (a binary resource we don't read); either parse control maps or declare it an explicit input boundary.
- [ ] **KQ4 arrow count** — model item-property state (the bow's `loop` = arrow count) so Lolotte's minimum-arrows requirement binds.

## Code-review worklist (verified findings; write the pinning test first, see REVIEW-FIXES-TESTPLAN.md)
- [ ] **Liveness setter-guard gap** (closure.py) — `gen` misses non-promoted flag-setter guards, so a register read only there is masked → gate opens free → missed requirement.
- [ ] **Silent feature-disable** (discover:76 + model:807) — an empty `()` throws IndexError, a bare `except` empties `state_locals`, and every room-local reverts to opaque with no signal.
- [ ] **`auto` budget** (closure) — greedily fills on 2-value noise and excludes the real mode registers (gCurrentStatus, gIslandStatus, …); make `auto` = all candidates.
- [ ] **state-locals not zero-seeded** (closure) — `(== knifeHere 0)` reads provably-false though 0 is the start value → risk of a false stranding.
- [ ] **Same-named room-locals merged** (discover) — scope local names by script so `seenMessage`@31 ≠ `seenMessage`@80.
- [ ] **KQ4 death detection** (discover:77) — `(= dead TRUE)` compares a Sym to the str "TRUE" and is always false → KQ4 death-only locals stay opaque.
- [ ] **SET-effect leakage** (model:556) — room-local writes leak into `analyze.derived_maps`/`irreversible_globals` (global-only analyses).

## Engine / performance
- [ ] **Combined promote-all is slow at full scale** — the joint state space of high-cardinality registers (gCurrentStatus 24 vals × gCurrentEgoView × …); relational/cluster the independent registers, or accept the runtime.
- [ ] **Flip promotion ON by default** — promote the self-checked clean set once combined is fast + correct.

## Next phase
- [ ] **Backpropagation / patcher (Phase 6)** — given a detected requirement, place guards at the transition points that would strand it (handle consumables/counters), and prove the patch can't break winnability. Human-decision gate; the patcher is disabled because it once forced the fatal Spinach_Dip.

## Parked
- [ ] **Unfair/forced deaths** — LSL2 boat timers etc. are deaths not softlocks; deferred second pass to flag them.
- [ ] **sci-tools front-end** — adopt sluicebox's decompiler front-end to unify the two-tree seam and generalize extraction to any SCI game.
