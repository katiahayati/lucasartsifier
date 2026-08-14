# Contextless review of merge 0b50d32 (v1.0-lb2), 2026-08-13

Reviewer: fresh-context agent, full diff + surrounding code read, four docstring
census claims re-executed against the shipped IRs. Sections as commissioned:
generalizability / derivation-vs-declaration / hacking-overfit / correctness /
code debt. Verbatim report below.

## 1. GENERALIZABILITY

Verified-general (spot-checked): derive_mask_accessors (re-ran: LSL2/KQ4/KQ6 empty,
LB2 exactly {124}); polygons.dead_nav_exits (re-measured: KQ6 zero, LB2 rm330-south
+ rm240-east); _newroom_override_edges, death_screen_rooms, derive_global_props,
lower_property_case_labels, counter-monotonicity, joint projections, Vocab99x.cpp
species fix — all engine-general with honest refusal directions.

Flags, most severe first:
1. polygons.py:293 — margin_ew, margin_s = 40, 6 hand-picked pixel constants in
   src/; margin_s=6 claims to know the engine's south handoff band. Wrong band on
   some game => false seal, deletion direction.
2. guard_flip_interceptor + demand forwarding — shape generalized from ONE instance;
   census lives in a memory note, not a probe; route regex admits two spellings.
   LB2-only by construction today; next game's differently-spelled interceptor
   silently falls to REFUSED.
3. guards._stage_spelling — escape hatch built to admit exactly LB2's global123;
   safety rests on a hand-maintained enumeration of store indexes (Debt #2).
4. trigger.arming_contexts '"state" in dtxt' — spelling assumption over decompiled
   text (fails toward refusal, low harm).
5. Depth caps range(6)/depth>=4 arbitrary; fail toward refusal, acceptable.

## 2. DERIVATION vs DECLARATION

Two "MEASURED" docstring claims do NOT reproduce (re-ran both):
1. extract.py:480 delegate_slots census says KQ6 {actions, curIcon}; ACTUAL
   {actions, client, curIcon} — `client` ubiquitous; recorded census stale for a
   slot it never mentions.
2. vocab.py:552 derive_control_selectors says LSL2/KQ4 {}; ACTUAL both return
   {'init': 'take'} (KQ6/LB2 too). Behavior unaffected; the justifying measurement
   is false.

Answer-protecting shapes:
3. snapshot.py:56 — register_value_strandings key joins the surface only when rows
   exist, stated reason "would move two goldens" — the project's own overfit tell.
   Honest alternative: re-bless goldens with an empty key once, with sign-off.
4. missability.py:2114 _death_values — fires only on "exactly one trap row naming
   exactly one register" = exactly KQ6 flag 44; stops firing silently if KQ6's
   death proc grows a second survival alternative.
5. Preempt rule and complementary-fork rule: single-instance calibration of
   deletion-side filters (see Correctness #3/#5).

Clean: no oracle-sourced guard ships in src/. Reclassifications carry quoted user
rulings and live in test/oracle files. Retraction discipline = the doctrine working.

## 3. HACKING / OVERFIT

1. guard_flip_interceptor wraps the FIRST matching arm and returns — two arms
   pinning the same stage (or a doit twin) leave a bypass. The project's own
   "one wrapped door of an N-door commitment is a bypass" lesson not applied.
2. Stage matching is whitespace-normalized SUBSTRING containment, not structural —
   a head embedding the stage inside (or ...) still matches.
3. _forward_demand_to_hold is order-dependent (scans in-progress `out` for the
   host); nothing pins guard_specs order.
4. Forwarding re-wraps already-rewritten text (nested (and ...) layers).
5. trigger.arming_contexts: hand-rolled parser + depth-1 regex; handsOff/hide
   detection matches comments/strings; misclassification runs both ways.
6. Seven-store lowering cascade: mutation-in-place, "allocation order IS register
   identity" invariant increasingly expensive.
7. Vocab99x.cpp fix is the OPPOSITE of a hack — sound, general, permutation-gated.
   Nit: reloads every script resource per SpeciesTable::Load.

## 4. CORRECTNESS

1. guards.py:608-621 — demand-forwarding "sole producer" proof HOLE: `others`
   checks only in-room writes; `hosts` only edges out of the pocket. An edge write
   reg:=w with a non-pocket source is never considered => player reaches the pocket
   at stage w without crossing the hold; surface still says covered/forwarded.
   Claimed-coverage error, deletion-side. Latent today (LB2 123:=5 sole producer).
2. vocab.py:2719/2822 — lower_mask_accessors husks reader bodies UNCONDITIONALLY
   while non-literal read calls are merely "skipped": a skipped call now reads
   constant-0, modelling "unmodelled" as "false" => can delete edges/requirements.
   Honest move: refuse the whole store when any read call is unresolvable.
3. missability.py:1443 — preempt rule deletes fatal_uses rows without checking the
   same-slot competitor is ARMABLE (item/cast/register-gated competitor still lets
   the player die; row deleted anyway).
4. missability.py:528-532 — entry-guard intersection dissolves requirements on the
   word of entries that may never fire; _via_latch (missability.py:3430) already
   embodies the correction, not applied here; feeds required -> frontiers ->
   crossing_retires_need (fewer needs => more retirements).
5. missability.py:1466 — complementary-fork escape is state-keyed, cannot attribute
   the handoff to an arm; a state whose lethal arm both hands off and exits reads
   survivable. Deletes death findings.
6. extract.py:522 — _object_departures ignores intra-case branches: a CONDITIONAL
   terminal off-pic MoveTo departs the object unconditionally, violating the
   "strict in the keeping direction" contract; seal-fabricating direction.
7. Minor: derive_control_selectors restore-overwrite asymmetry; _global_instances
   permissive on int-assigned globals; _cutscene_delivers parse-failure fallback is
   the known-bad in-place gate (the play-caught shape), not neutral.

## 5. CODE DEBT

1. _crossing_reach is a declared hand-mirror of _psucc's edge clause — no shared
   helper, no test pinning them in step (verified currently in agreement).
2. _stage_spelling's hand enumeration of store index attributes; item-bit store has
   no index attribute; no test pins the enumeration.
3. patcher placement flow outgrown coherence (4-level decision tree, mutable
   seen/dctx); LB2 deferral/forwarding rewrites have NO direct unit test.
4. Dead code: _defer_triage_site `handled` unreachable branch.
5. Near-duplicates: _collapse_flips/_collapse_value_flips; polygons._room_object vs
   extract._room_object; block-span parsers in trigger.py vs patcher.py.
6. register_flip_frontier allocates `groups` it never fills; snapshot never runs
   the chooser feasibility gate (mode plumbing may be retracted by pipeline).
7. lower_property_case_labels inline __import__("sys") print; _skipped_deaths
   module-global mutable state (cleared per build, same as BOOL_GLOBALS).

## Verdict

This merge largely upholds the project's derivation discipline, and in places
exemplifies it: every new mechanism argues its shape from the engine's own class
table or the game's own step relation, states which direction it refuses in, and
ships with a corpus census — two of which re-ran and reproduced exactly — alongside
an honesty apparatus (mechanism pins, never-skip goldens, loud retractions,
play-confirmation records) most analysis projects never build. The failures are at
the edges of that discipline rather than against its center: two docstring censuses
no longer reproduce, several deletion-side filters were calibrated on single
instances and have constructible failure modes the calibration cannot see, the
forwarding proof's "sole producer" check does not check what its comment claims,
the mask-accessor husking quietly converts "unmodelled" into "modelled false," and
the text-rewrite patcher layer is accumulating fragility faster than its tests.
None of these is an oracle leak — the doctrine's cardinal sin is genuinely absent —
but the deletion-side soundness holes (Correctness #1-#4) deserve RED TESTS before
the next game exercises them, because each one fails silent and green.
