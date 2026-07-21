# sierra_softlock — project state & roadmap

## The goal (true north)
Two halves, generalizing beyond LSL2 to SCI games:
1. **Detect** which items-lost / actions-taken can strand the player in an unwinnable
   (walking-dead) state.
2. **Prevent** them by auto-generating a verified patch to the game (re-grant the item,
   add a guard, block the fatal action).

## Pipeline
`sci-tools` decompile → JSON IR → `extract2` (guards/effects/edges) → `machine2`/`compile2`
(lift changeState scripts to state machines) → `smv_emit3` (operational SMV model) → **nuXmv**
(winnability & requirements) → *patcher (DISABLED)*. Plus the **control-map oracle**
(`control_oracle.py`, `sci_gfx.py`): derives positional gates from PIC/VIEW art.

## Where we are, against the goal

**Detection front-end — strong and now much sounder.** Proven required-to-win:
Parachute, Knife, Grotesque_Gulp (raft), Airline_Ticket, the bikini disguise (control oracle),
and the bomb (Matches + Hair_Rejuvenator) gating the volcano (34s UNSAT). Soundness holes
closed: dropped `or`-guards, indirect `newRoom`, `setScript` capture, local-compare guards,
init atomicity, guard trees, and — 2026-07-20 — the **carried-cue fix** that revealed the
endgame was silently DEAD in the model (rm84 s79 false PARK) and un-deadened it.

**Two gaps stand between us and the goal:**
- **Missability pass — UNBUILT.** Everything above proves an item is *needed*. A softlock is
  *needed AND irreversibly missable* (a reachable state where the item can no longer be
  obtained but is still required). We have requirements, not missability. This is the "which
  action/loss actually causes the lock" question — the core detection deliverable still owed.
  Airline_Ticket is the cautionary case: required but re-obtainable ⇒ not a softlock.
- **Patcher — DISABLED.** The "prevent" half isn't operational. Groundwork exists
  (`trigger.py`/`patch_trigger.py` guard auto-placement) but `patch.py` stays off, and there's
  a known landmine: the Spinach_Dip patch *breaks* LSL2 by forcing a fatal item.

**Cross-cutting blocker: TRACTABILITY.** Requirement queries work when shallow and local
(bomb: 34s). Anything targeting the deep `room=178` goal — base-winnability, a full
requirements sweep under the tight goal, and by extension the whole missability sweep — times
out (~120-step witnesses; ~1600 free opaque inputs; position ints). **COI / model reduction is
the lever that unblocks all of it, and is the prerequisite for the missability sweep.**

## COI / model-reduction plan (the next build)
Goal: make deep, target-directed queries tractable so the missability sweep becomes possible.
1. **Measure the baseline** — what nuXmv already does (built-in COI, BMC bounds, engines,
   reorder) on the deep queries, before building anything. Empirical.
2. **Linear-chain compression** (safe, high-impact) — collapse maximal runs of effect-free
   unconditional single-path ADVANCE states (e.g. rm84's 81-state cutscene) into one hop.
   Attacks depth directly; sound (intermediate states unobserved, no branching, no effects).
3. **Query-directed room slice** (the real COI) — for a given target + pins, keep only rooms on
   a start→target path (plus item-acquisition rooms), collapse the rest; drop their machines,
   edges, opaques, position uses. Over-approximate (keep a superset) so it stays sound.
4. **Opaque / position pruning** — drop opaque booleans and posx/posy used only by dropped
   transitions.
5. **Validate** — re-run the decisive queries on the reduced model: positively confirm base
   reaches `g_148==100` (closing today's non-vacuity gap), and re-confirm bomb / disguise /
   parachute REQUIRED (soundness regression check vs the full model).
6. **Wire in** — make the slice automatic per query so `winnable()`, the requirements sweep,
   and the missability sweep all use it.

## COI — empirical findings (2026-07-20)
- **Compression (depth lever) WORKS.** rm84's 81-state cutscene → ~4 hops; the UNSAT/
  requirement direction went 34s → **5s (~7×)** and stayed sound (bomb still REQUIRED). This
  is the direction the missability sweep lives in, so it's the win that matters.
- **Room-corridor slicing (width lever) is INEFFECTIVE on LSL2.** The map is one big SCC:
  the sound (guard-ignoring) start→target corridor keeps **83 of 101 rooms** for the volcano
  (84 for rm178). It drops almost nothing, so the ~1522 opaque free inputs + position IVARs
  (the real width) stay. Classic COI can't unblock the positive SAT direction here.
- **Consequence:** the deep POSITIVE direction (base reaches the volcano; base winnable to
  178) stays intractable. But it is NOT on the critical path — the missability sweep uses
  fast UNSAT/requirement queries (compression-accelerated), and non-vacuity holds structurally.
- **Opaque ELIMINATION (the real width lever, exact) DONE.** The ~1522 opaques are INDEPENDENT
  fresh free inputs, so a guard `real & f(opaques)` is enabled exactly when `real` holds (f is
  always satisfiable). Existentially projecting them out (`_permissive` -> OPAQUE sentinel;
  `_gx` drops it in AND, absorbs OR to TRUE, keeps it under NOT via De Morgan; public `gexpr`
  maps a surviving OPAQUE to TRUE) gives a model reachability-IDENTICAL to the free-input
  encoding but with **0 free booleans** (was ~1522). Real guards (disguise g_131 & g_102==151,
  the bomb latch, rects) untouched. Tests 32+25 green. Room-independent, so it dodges the
  dense-SCC problem that killed the room slice.
- **Still open (smaller):** position abstraction (posx/posy 0..319/0..189 -> band booleans) --
  only ~17 input bits vs the 1522 opaque bits just removed, so likely second-order.

## Class-2 detector: FLAG point-of-no-return (task list, ACTIVE)

State: the room-gate sweep (`missability.py`) is **16/17 with ZERO false positives** vs the
user's walkthrough. The single remaining miss is the **Pamphlet**, which is not a room-gate
stranding at all — it's a FLAG point of no return: giving the Pamphlet to your seatmate sets
`gBoreStatus=255` (irreversible), which kills the drink-service source of the **Airsick_Bag**.
Same PONR idea as Class 1 but in flag space instead of room space.

1. **Characterize the mechanism concretely** — how does `gBoreStatus=255` actually block the
   Airsick_Bag acquisition in rm62? Is the source guarded on the flag, or mediated by the
   `boreScript` machine? This grounds the detector; do NOT design before reading it.
2. **Detect irreversible flag SETs** — globals written `G:=V` with no path that resets G to a
   value restoring what it gated. (Start with "never written again"; refine if needed.)
3. **Detect flag-gated item sources** — for each item, extract the global conditions on each of
   its acquisition guards, so we know which flag-values kill which sources.
4. **Combine into the softlock rule** — a REACHABLE irreversible `G:=V` that falsifies **every**
   source of a still-needed item ⇒ flag-PONR softlock. Reuse the existing goal-aware/required
   machinery so it reports in the same shape as the room-gate strandings.
5. **Validate against ground truth** — the Pamphlet MUST be caught, and the existing 16 TP /
   0 FP must not regress. (Every graph change so far that skipped this step broke the sweep.)
6. **Note for later, not now** — the same machinery generalizes to *required actions/flags*
   (KQ5: throw the shoe to save the mouse, else the inn basement is unwinnable): a required
   flag-VALUE that becomes unreachable. Tabled by the user.

## Revisit later (flagged by the user)
The **cutscene splice** that fixed the Airline_Ticket FP may be overfit special-casing — it
needed three guards, each added only after the sweep collapsed to 0/17, fixes exactly one case,
and is validated on one game. It may also be a *proxy* for the gate-aware graph fix. See the
`cutscene-summarization` memory for the full concern and what to check before trusting it.

## After COI
The missability sweep (turn "required" into "actually a softlock"), then re-enable a *safe*
patcher (never force a fatal item — the Spinach_Dip trap). Auto-discovery of start/goal is a
parallel nicety. Oracle-hardening TODOs and KQ4 item-property state remain.
