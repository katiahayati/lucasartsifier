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

## GATE-AWARE MOVEMENT GRAPH — DONE (2026-07-20). Sweep = 16/16, zero FP.

Replaced the guard-ignoring room graph with a **product over (room, gCurrentStatus)** plus an
**item dimension**. Both overfit rules the user flagged are now RETIRED, not re-tuned:

- **`_sealed` (one-way-edge heuristic) — retired.** Derived replacement: when asking whether item
  I is re-obtainable you are by definition in a state without I, so every edge guarded on own(I)
  is false along that walk. `reobtainable_rooms` overridden in `IrSccReach`.
- **Cutscene splice — retired and deleted.** It was actively harmful: splicing rm83 fabricated an
  rm82 -> rm92 edge reconnecting the volcano to the island hub, which HID the Ashes/Sand
  stranding. The ticket FP it papered over had a real root cause (below).

Four bugs it exposed and fixed:
1. **Register-gated composition.** rm82 sets gCurrentStatus 14/15 and dumps you in rm152, whose
   exit to rm52 requires status 7. The guard-ignoring graph composed them anyway -> mega-SCC
   welding volcano to airport -> hid the Pamphlet, caused the ticket FP.
2. **Unguarded duplicate edges shadowing guarded ones.** `edge_meta` did not apply the
   `machine_delivered` filter `build_maps` does, so rm57 -> rm58 had a free variant beside the
   real own(ticket) machine EXIT. THIS was the Airline_Ticket FP.
3. **Entry guards never reached their exits.** A gate armed by a `Said` handler
   (`throw ash` -> changeState 8) exits many states later carrying no own(). `entry_alts`
   propagates entry guards forward along ADVANCE/JUMP/SETSTATE to the EXIT.
4. **Disjunctive requirements (the long-standing gap).** Entry guards are alternatives, not a
   conjunction. Intersecting gives "free", unioning gives "needs both" — both wrong. `entry_alts`
   keeps a DNF; `blocked()` fails an edge only when EVERY alternative needs a banned item.

**`disjunctive_groups` / `group_strandings`** then catch what no per-item sweep can see: rm81 past
the vine chasm is armed by `throw ash` (30) OR `throw sand` (31), so each looks re-obtainable via
its sibling — but both sources (rm75/77) are back across a one-way crossing. Losing either is
survivable; losing both is the softlock. Reported as a group row.

Score vs the user's walkthrough list: **15 single items + 1 disjunctive group = 16/16, ZERO false
positives.** Airline_Ticket / Bikini_Bottom / Soap correctly NOT flagged; Spinach_Dip still
correctly treated as a trap. Tests 20+32+25+20 green.

### Deviations to confirm with the user (NOT acted on)
- **Stout_Stick (28)** — used only in rm72, PRE-chasm; source rm71, also pre-chasm. Intra-jungle,
  so not a stranding. The user suspected exactly this. No longer flagged.
- **Vine (29)** — used at rm79 (the chasm throw itself), source rm74, both pre-chasm. Same shape.
  No longer flagged. Neither item was on the user's enumerated list; both were flagged by the OLD
  `_sealed` rule, and I had been scoring them as true positives on the assumption the list was
  incomplete. Flagging this explicitly rather than silently re-scoring.

### TRAP rule re-derived from GOAL-REACHABILITY — DONE (2026-07-20)
The death special-case is gone. `hopeful()` asks whether the goal is still reachable after a use:
DEATH is False, EXIT inherits its destination room's prospects, PARK inherits THIS room's (control
returns to the player), and ADVANCE/JUMP/SETSTATE resolve through a backward fixpoint over the
machine (`goal_reaching`). An item is a TRAP only if EVERY own()-guarded use is hopeless.

This **subsumes** the old rule (death is one way to be hopeless) and generalizes it: a use that
merely strands you in a region with no route to the goal now counts too, with no death involved —
untestable under the old formulation. It also removed a SECOND copy of the death special-case that
was sitting in the per-use requirement pass. `_death_reachable` is deleted.

Both the "only-EVER death-bound" wrinkle and the Grotesque_Gulp regression it was patched for fall
out for free: the Gulp has a fatal use AND winnable ones, so it stays required; Spinach_Dip is
hopeless everywhere, so it stays a trap. Sweep unchanged at 16/16 zero FP; tests 20+32+25+29.

### Gating registers are now DISCOVERED, not named — DONE (2026-07-21)
`_STATUS_REG = 101` is gone. `gating_registers()` derives the set from the criterion the product
is built on: an inconsistent composition needs an edge that SETS R and an edge that REQUIRES R, so
a register earns promotion iff it is **compared in a movement guard AND written**. Purely
structural — on LSL2 it rediscovers gCurrentStatus (101) as the widest gater (18 observed values)
plus 18 others, with no game knowledge.

**Projections, not a joint product.** Promoting all 19 jointly explodes past **4,000,000**
reachable states (aborted at 19s) because the flags are near-independent and multiply. The same 19
as INDEPENDENT projections cost **3,679 states total**, and the sweep runs in 0.5s. This is sound
and monotone: a genuinely walkable path is walkable in every projection, so intersecting the
per-projection answers can only remove spurious movement, never invent it — each register added
can only sharpen the result. That is what lets us honour "promote everything, never judge a
variable irrelevant" at linear rather than exponential cost.

Only positive `== v` atoms are used; `!=` and relational ops are ignored, which is the PERMISSIVE
direction (we never block movement the game allows). Making those exact needs the value-partition
abstraction (observed constants as singletons plus the gaps between them) — worth doing only if a
game turns up that gates movement relationally.

Sweep unchanged at 16/16 zero FP. Tests 20+32+25+35.

## GUARD SYNTHESIS (the 'prevent' half) — STARTED 2026-07-21, `src/guards.py`

The patch condition is derived from the WINNING REGION, never from "this item is mentioned
nearby" — that distinction is the entire reason `patch.py` is disabled.

    guard(gate) = OR over the HOPEFUL paths of that gate, of their path condition,
                  keeping item literals, positive AND negative

`hopeful` is the same goal-reachability predicate the TRAP rule uses, so a branch that kills you
or strands you contributes nothing, while a surviving branch contributes exactly its own()s.

**Acid test — rm138, the edge whose patch broke LSL2.** The lift carries the full ordered `cond`
including negations, so the derived guard is:

    (and (gEgo has: 8) (not (gEgo has: 13)) (or (gEgo has: 11) (gEgo has: 12)))

i.e. need the Grotesque_Gulp, take Sewing_Kit OR Fruit, and **must NOT carry the Spinach_Dip**.
The shipped guard was `(and has:11 has:12 has:13 has:14)`. The derived guard FORBIDS the very item
the old one REQUIRED — same edge, opposite conclusion, because the rule is now semantic. All three
defects in `DISABLED_WHY` (fatal item forced, OR-alternatives ANDed, validator sharing the core)
are addressed by one mechanism plus an independent oracle.

`absorb_ordering` removes the negations an ordered `cond` leaves behind (`(A & !B) | B == A | B`,
dropping a negative only when that item is positive in a sibling HOPEFUL alternative) — so
"tested later" collapses while "carrying this loses" survives.

Four survival gates on LSL2: rm70 (Knife), rm82 s7 (Airsick_Bag), rm82 s9 (Matches), rm138 (above).

**PLACEMENT: each literal is enforced at the last edge where it is still SATISFIABLE**, not at the
gate. A positive literal needs the item still obtainable; a NEGATIVE literal needs it still
droppable — guarding `!own(dip)` at the raft would convert a death into a permanent wall, since
disposal is ship-only. Derived frontier for the dip: **rm131 -> rm138** (boarding the raft from the
deck where "throw bread overboard" works, +2 score), which is exactly where the user said it
belongs. `drops` — declared since the first version but never populated — is now filled from
handler and machine drops, which is what makes this computable.

### Guard synthesis — next
1. **Filter death-room frontiers.** rm10->rm90, rm35->rm95/96 surfaced as frontiers but are deaths,
   not commits; screen them with `goal_reaching_rooms`.
2. **Emit specs per literal at its own frontier** (JSON), with the two safety preconditions as hard
   refusals: positive literal must be obtainable before the edge, negative must be droppable before
   it. A guard that cannot be satisfied is strictly worse than the softlock.
3. **Validate with a DIFFERENT engine than the detector** — the exact lesson of `DISABLED_WHY`.
   Ladder: structural self-check -> re-run the sweep on the guarded model (softlock gone, no NEW
   strandings) -> nuXmv winnability -> boot in ScummVM.
4. **Then** source emission via the existing `trigger.py` controllable-trigger placement (guard the
   handler that STARTS the cutscene, never the `newRoom` at its tail — guarding the tail crashes
   the game).

**Seam to verify before touching game files:** analysis runs on the sci-tools JSON IR, while
`trigger.py`/`patch_trigger.py` rewrite the EricOakford source tree — two different decompilations.
Item/room numbering probably corresponds; "probably" is how the last patch shipped.

### Still open
- **Validate the discovery on KQ4** — this is the first piece built to be cross-game by
  construction, and it has still only ever run on LSL2.

## Revisit later (flagged by the user)
The **cutscene splice** that fixed the Airline_Ticket FP may be overfit special-casing — it
needed three guards, each added only after the sweep collapsed to 0/17, fixes exactly one case,
and is validated on one game. It may also be a *proxy* for the gate-aware graph fix. See the
`cutscene-summarization` memory for the full concern and what to check before trusting it.

## After COI
The missability sweep (turn "required" into "actually a softlock"), then re-enable a *safe*
patcher (never force a fatal item — the Spinach_Dip trap). Auto-discovery of start/goal is a
parallel nicety. Oracle-hardening TODOs and KQ4 item-property state remain.
