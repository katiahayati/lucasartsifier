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

## After COI
The missability sweep (turn "required" into "actually a softlock"), then re-enable a *safe*
patcher (never force a fatal item — the Spinach_Dip trap). Auto-discovery of start/goal is a
parallel nicety. Oracle-hardening TODOs and KQ4 item-property state remain.
