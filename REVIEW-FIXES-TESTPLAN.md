# Code-review fixes — test plan

From the xhigh review of the promotion work (commits 9da6ffb, 22acbc2, eab8c65).
Discipline: **each test must go RED on the current committed code first** (confirming
it catches the bug), then GREEN after the fix. Never encode the bug as the expected
value — assert the CORRECT behaviour. Tests land in `src/_check_core.py` unless noted.

Several bugs have **no game-level symptom on LSL2/KQ4 today** (they don't drop a room
yet), so their tests are unit/invariant/mechanism-level, not "is it winnable". That is
exactly why they are dangerous: latent, in the miss-a-softlock or invent-a-softlock
directions.

---

## Tier 1 — real soundness holes (miss a real softlock)

### #1  closure.py:426 — liveness masks a register read only in a non-promoted setter guard
- **Correct behaviour / invariant:** a promoted register must be TRACKED (unmasked) at
  every room where ANY guard reads it — including the guards of non-promoted flag /
  state-local SETs (`m.sets`, applied in closure step 3).
- **Test (invariant, the valuable one):** promote `gCurrentStatus`; compute
  `read_rooms` = every room where `gCurrentStatus` appears in ANY guard source (edge,
  machine, exit/self writes, acquire, AND `m.sets` setter guards); assert
  `reg_track['gCurrentStatus'] ⊇ read_rooms`. Generalises: guards future masking bugs.
- **Anchor test:** assert the specific setter-rooms (e.g. rm102, `doorIsOpen` gated on
  `gCurrentStatus==N`) are in `reg_track['gCurrentStatus']`.
- Red now (setter-guard rooms masked); green after adding setter guards to `gen`.

### #2  discover:76 + model.py:807 — one empty `()` form silently disables the whole feature
- **Correct behaviour:** discovery must never silently no-op; the room-local feature
  must be ON for both games.
- **Test (a) unit:** `_has_progress` on a form containing an empty `()` returns a bool,
  does NOT raise `IndexError`.
- **Test (b) e2e "feature is ON":** `assert 'henchStatus' in load_game().state_locals`
  (LSL2) and a known local for KQ4. Any silent degrade to `frozenset()` fails this.
- Fix also: replace the bare `except Exception -> frozenset()` with something that
  surfaces the failure (log/raise) rather than passing tests with the feature off.
- Red now (latent: empty-form path); green after the guard + non-silent handling.

### #3  closure.py:294 — `auto` budget promotes 2-value noise, excludes the real gates
- **Correct behaviour:** the `auto` selection must include the real mode registers.
- **Test:** run `auto` selection for LSL2; assert chosen ⊇
  `{gCurrentStatus, gIslandStatus, gBombStatus, gWearingSunscreen}`.
- Red now (budget eaten by 2-value registers); green after fix (prioritise discovered
  gate-registers, or — since scoping removed the perf reason for the cap — make
  `auto` = all candidates).

---

## Tier 2 — false-positive direction (invent a stranding) + collisions

### #4  closure.py:199 — state-locals not zero-seeded, so `(== local 0)` reads FALSE
- **Correct behaviour:** every register/state-local has its default `0` in the seeded
  value-set, so `(== knifeHere 0)` is satisfiable in the initial state.
- **Test:** `eval3` of `(== knifeHere 0)` against the INITIAL flag state is NOT `F`
  (must be T or U). Equivalently assert `0` present in the local's seeded value-set.
- Red now (0 absent → provably false); green after seeding state-locals with 0.

### #5  discover:120 — same-named locals in different rooms merged into one register
- **Depends on the fix design** (qualify locals by script number). Bring the scoping
  design to the user BEFORE writing this test.
- **Test (once fix agreed):** `seenMessage` in script 31 vs script 80 resolve to
  DISTINCT register keys; their value-sets do not pool.

### #6  discover:77 — KQ4 death detection always FALSE (parsed `Sym` vs config `str`)
- **Correct behaviour:** `(= dead TRUE)` is recognised as a death (progress) for KQ4.
- **Test (unit):** `_has_progress` on parsed `(= dead TRUE)` with
  `death_sig=("dead","TRUE")` returns `True` (mirror `is_death_write`'s
  `str().strip()` compare).
- **Test (e2e):** KQ4 discovery surfaces a local that lives only in a death-only
  instance.
- Red now (Sym != str); green after str-compare.

---

## Tier 3 — leakage / minor

### #7  model.py:556 — room-local SET effects leak into global-only downstream analyses
- **Test:** no room-local (`henchStatus`, `knifeHere`) appears in
  `analyze.derived_maps` / `irreversible_globals` for LSL2.
- Red now (leak); green after excluding locals there.

### #8  closure.py:982 — masked-but-reachable value dropped from reported achievable-set
- Low priority (reporting). **Test:** a masked-but-reachable value still appears in
  `.flags[reg]`.

### #9  discover:117 — `_MECHANICAL` hand-list may drop a genuinely-gating local
- No clean test (heuristic smell). Address by shrinking the hand-list, not pinning it.

---

## Order to implement
1. #1 (invariant) and #2 (feature-ON) — the miss-a-softlock direction, invisible today.
2. #6 (KQ4 death), #3 (auto budget) — generalisation-path correctness.
3. #4 (zero-seed), #7 (leakage) — quick, clear.
4. #5 (name collision) — needs the scoping-fix design discussion first.
5. #8 — optional. #9 — not a test.
