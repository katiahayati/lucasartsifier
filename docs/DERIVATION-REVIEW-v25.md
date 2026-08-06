# Derivation review at the v25 milestone

A single-pass review of `src/` against the standing rule: everything derived, not
hand-analyzed; no clause whose only justification is protecting an answer we already like
(see the memory notes `right-level-of-generality` / `clause-that-protects-a-known-answer`).
Run at `3ef73de` (finding #17 closed, v25 installable, findings backlog empty).

## Verdict

Clean. No game-name branches, no `if room == N` logic, no hardcoded item/global/room
numbers in live code. Every KQ6/LSL2/KQ4 literal that greps up in `src/` sits in a comment
or docstring as a motivating instance. The newest code (v24/v25) is some of the cleanest.

What was checked and found sound:

- **config.py** — paths + display name only; start/goal/death/debug all empty so the
  derivations run; `sweep_config` means a new title needs zero code.
- **anchors.py** — the historically fitted clauses are gone: the `cand*2 >= wide` magic
  ratio is now the structural "prefer the candidate only if it costs nothing" rule (no
  threshold), rivals are defined by contradicting entry conditions rather than a machine
  count, and the achievement signal's two-game confirmation is labeled PROVISIONAL.
- **`vocab.derive_mask_globals` (sixth store)** — shape-derived; any unrecognizable site
  (call arg, copy-read, switch head, arithmetic) refuses the whole global. The corpus
  census (exactly KQ6 g161) is a measurement, not an input.
- **`guards.sink_survival_carryins` + the flag-74 waiver** — "success consumes compliance"
  is read entirely off the machine's own modeled writes; the latch must be a one-way
  boolean nothing clears; no latch → the register half refuses rather than walls. Safe
  failure direction throughout.
- **`missability.fatal_uses` / `dangerous_sinks` / `register_strandings`** — each historical
  correction is encoded as a structural principle (`_survivable` vs `doomed`, blame =
  intersection over lethal entries, the causality conjunct), not a per-item exemption.
- **SCI1.1 death derivation** — dialog = non-Game object offering both `restart:` and
  `restore:`; death proc = public proc reaching such a dialog. Engine shape, no constants.
- **KNOWN_RED discipline** — promotion trail intact; both remaining reds are the
  documented deliberate ones.

## Watch items (minor; none blocks R13)

1. **`patcher._guard_travel_dispatch` wraps every bare literal-verb cond arm**
   (patcher.py, the `(== param1 <lit>)` match), on the implicit claim that any such arm of
   a dispatch class is a travel commit. Verified against the real `pullOutMapScr.sc`: it
   works because the non-travel arms are all spelled `(and (== param1 ...) ...)`, which the
   anchored regex skips — but that claim is confirmed on one instance. A future dispatch
   class with a bare `((== param1 1) look...)` arm would get its look verb refused when
   unready — an over-block, never a wall (the guard discriminates by destination). Fix
   when it matters: pin with a synthetic test, or require the wrapped arm's body to reach
   the `newRoom:` dispatch.
2. **Latch value 1** — `guards._one_way_set` demands `vals == {1}` and the latch detection
   checks `v == 1`. Asserts "success latches are boolean TRUE"; the BOOL_GLOBALS
   restriction makes that the store's idiom, and a nonconforming game degrades to refusal
   (safe). Noting that the literal states an idiom, not a derived fact.
3. **Silent compute caps** — `compile.PATH_CAP`/`COUNTER_CAP`, the joint bound
   (`size > 4000 or len(want) >= 8` in missability), and the `len(visited) > 4000` walk
   bound all `continue` silently. Documented deliberate unsoundnesses, but a joint dropped
   by the budget is invisible in the output surface. A one-line dropped-joint count in the
   report would align them with the no-silent-caps doctrine.
4. **Allocation order is register identity** — bitten twice (prop flags; the mask store
   mid-sequence stealing 489/490). Documented at the load site and test-pinned, but it
   remains an implicit invariant across five lowering passes. If a seventh store lands,
   keyed register identities ((store, key) tuples resolved to indices in one final pass)
   would retire the bug class.
5. **`extract._EGO = {0}` / `_CURROOM = 11` template defaults** — derived first, defaults
   only for a game with no derivable Game loop, documented. Fine as is.
