# Control-map oracle: engine integration notes

Running log of wiring the PIC/VIEW control-map oracle into the main (JSON-IR /
`smv_emit3.OpEmitter`) engine. See also memories `pic-control-plane-oracle`,
`engine-architecture-json-ir-is-main`, `lsl2-bomb-has-no-script-level-gate`.

## Architecture (confirmed 2026-07-19, user-corrected)
- **Main engine = the JSON-IR / operational chain**: `ir.py` -> `extract2.py` ->
  `machine2.py` -> `compile2.py` -> **`smv_emit3.py` (OpEmitter, drives nuXmv itself)**.
  The oracle (`control_oracle.py`, `sci_gfx.py`) reads `ir.py`, so it's in the right chain.
- **Legacy (to branch off)**: `closure.py`, `machine.py`, `smv_emit.py`, `smv_emit2.py`,
  `nuxmv_engine.py`, `examples.py`, `_check_core.py`. I initially mistook these for
  canonical because the existing harnesses run on them; they are legacy.
- **RIGHT winnability test**: `smv_emit3.winnable(em, pin_items_off=())`,
  `em = OpEmitter(ir, config.LSL2, is_death)`, `is_death = lambda gi,v: gi==101 and v==1001`.
  SLOW: base winnability is >900s (was ~700s per earlier notes; the extra tracked latch adds
  load). Run in the background with a big timeout; performance is acceptable if it finishes.

## What the oracle derives (no declarations)
For rm82: `control_oracle.find_gates(cfg, ir)` reads PIC 82 control plane + VIEW 715 cel
footprints + the AST/machine and returns:
`{room:82, control_bit:$0004, gated_room:83, opener_states:[(rm82Script,16)], opener_latch:(L,3,1)}`
i.e. *reaching room 83 (via the onControl-$0004 elevator) requires L3==1 (`causedEruption`),
which only the bomb sets in state 16, because the `aDoor` Prop (VIEW 715, solid by its own
`isExtra`/`ignoreActors` flags) covers the elevator floor until then.*

## Wiring point
`OpEmitter._apply_control_gates()` (smv_emit3.py, called right after `_doit_death_gates` in
`_collect`, before domain finalization): ANDs `('CTR', latch_key, '==', val)` onto the
machine `EXIT`-to-`gated_room` transition, and seeds `loc_vals` so the latch local gets a
tracked domain. Confirmed in the emitted SMV:
`action=… & room=82 & ms_82_rm82Script=21 & (c_82_L_3 = 1) : 83;`

## Generality status of the oracle heuristics
- [FIXED #1] entry seed: now `_entry_seed` derives ego's arrival area from the `(gEgo posn:)`
  in init (snapped to nearest walkable) + a band on each screen edge the room can exit by;
  floor-band only as fallback. rm82 unchanged; no new false positives across the sweep.
- [TODO #2] cel[0]=closed / cel[-1]=open assumption (door could animate the other way).
- [TODO #3] `_gated_room` follows linear state->state+1 (ignores JUMP/SETSTATE).
- [TODO #4] latch must be a co-located persistent write in the opener state.

## Plan / task log (tasks #13-#16)
1. #13 small fast tests for the rm82 gate (structural + synthetic) -- IN PROGRESS.
2. #14 add the rm47 crossing-gate to the oracle + tests (proven replacement for
   `_doit_death_gates`'s assumed rm47 disguise gate).
3. #15 remove cruft: delete `_doit_death_gates`; branch off the legacy engine.
4. #16 long nuXmv run: base stays winnable + bomb (19,21) & disguise items REQUIRED.

## Status at commit a03cafe (2026-07-19)
- #13 rm82 gate tests: DONE (test_control_oracle.py, 31 pass).
- #14 rm47 crossing-gate: DONE. `crossing_forces_rect` proves east forces the rect, west
  does not; gate keyed on henchStatus (L2)!=0; only 47->48 gated, 47->42 FREE.
- #15 cruft removal: DONE. `_doit_death_gates` (+ _scan_doit_hazard/_cs_effects/_find_ctr_eq)
  DELETED (user: not the right thing, over-gates, doesn't work). Legacy engine moved to
  branch `legacy-engine` and removed from here (closure/machine/smv_emit/smv_emit2/
  nuxmv_engine/examples/_check_core/coverage). JSON-IR chain self-contained; test_everything
  disguise check repointed onto the oracle (25 pass).
  - KNOWN REGRESSION (red/TODO): rm50 airport metal detector (non-positional doit-reactive
    death) is now ungated. Disguise still REQUIRED via rm47, so the item conclusion holds;
    a general non-positional reactive-death detector is future work.
- #16 long operational nuXmv validation: RUNNING (op_val.py: base winnable + Matches(19)/
  Hair_Rejuvenator(21)/Bikini_Bottom(16) REQUIRED). ~15min+/query; result pending.

## Disguise requirement fix (task #17, 2026-07-20)
The rm47 crossing-gate was PLACED right (47->48 is on the critical path) but the gate was
WRONG: `henchStatus != 0` is also satisfied by the ARMED value henchStatus==1, and the death
from arming isn't forced -> the model could arm-and-cross without the disguise. Worse, the
`henchStatus:=8` (disguised) init write is DROPPED by extraction, so henchStatus can never be
8 -> gating on `==8` would break base. FIX: gate 47->48 on the DISGUISE CONDITION itself --
the guard of the init write `(if (and gBodyWaxed (== egoView 151)) (= henchStatus 8))`, i.e.
`GAnd([gBodyWaxed!=0, egoView==151])`. This is over persistent GLOBALS; `egoView==151` is
item-gated via the captured bikini chain (`egoView:=150` requires own(15)&own(16);
`egoView:=151` requires egoView==150), so it makes the bikini items required, and it can't be
met by arming. `control_oracle._disguise_condition` derives it from the init write;
`_apply_control_gates` prefers gate['safe_guard'] over the old `!= bad`. Tests updated (32+25
green). Validation (op_disguise.py) running: base winnable + Bikini_Bottom(16)/Bikini_Top(15)
REQUIRED.

## Disguise VALIDATED (task #17, 2026-07-20)
op_disguise.py (old goal): **Bikini_Bottom(16) REQUIRED=True, Bikini_Top(15) REQUIRED=True**
(pin off -> unwinnable, ~440s each). The disguise-condition gate WORKS. Caveat: base-winnable
timed out at 3200s (IC3 finds the UNSAT/unwinnable proofs fast but the deep winning path slow);
op_final.py re-confirms base under a bigger timeout.

## Endgame refactor (task #18, 2026-07-20)
goal_rooms tightened {75,76,77,78,178} -> {178} (the ending; rm75/76/77/rm78-room are
walk-reachable BEFORE the wedding). The gIslandStatus chain is CAPTURED and correct:
100(rm84 volcano) -> 102(rm85) -> 103(rm92) -> 104(rm75) -> 105(rm77/78) -> wedding -> 178;
rm78's ->178 delivery is gated on gIslandStatus==105 (machine entry (1,==105); state 0 parks).

CORRECTION: I first called the volcano "bypassable via the rm90-93 tangle" -- WRONG, from
over-trusting guard-IGNORING graph reachability. The model preserves the chain: rm92Script
state 15 = EXIT 93 (intro) and state 22 = EXIT 85 (volcano), so state 28 (gIslandStatus:=103)
is reachable ONLY via state 23 (the ==102 entry) <- rm85 <- rm92 state 16 <- gIslandStatus==100
<- rm84 <- rm82->83 (the bomb prop-gate). So the whole chain GENUINELY requires the volcano,
and the goal tightening should be SUFFICIENT to make the bomb REQUIRED. (gForceAtest was a red
herring -- init 0, never written, so pinned.) op_bomb.py confirms Matches/Hair_Rejuvenator
REQUIRED under the tightened goal. Lesson (again): guard-ignoring reachability is misleading;
the gIslandStatus gates are what make the volcano necessary, and they're invisible to a plain
edge BFS.

## Remaining oracle-hardening TODOs (generality #2-#4, still single-example)
- cel[0]=closed / cel[-1]=open (door could animate the other way).
- `_gated_room` follows linear state->state+1 (ignores JUMP/SETSTATE).
- latch must be a co-located persistent write in the opener state.

## Open validation
The 900s-timeout run gave no verdict (base winnability alone > 900s, and the *before*-gate
baseline also didn't finish in ~15-20 min -> it's the engine's inherent cost, not the gate).
op_base.py (base-only, timeout 2400s) is staged; the full run is task #16 (after the above).

## Validation under the tightened goal: INTRACTABLE (2026-07-20, op_bomb.py)
Result of the full requirement/base run under goal={178}, timeout=6000s each:
- Matches(19) REQUIRED: **timed out at 6000s (no verdict)**.
- Hair_Rejuvenator(21) REQUIRED: **timed out at 6000s (no verdict)**.
- BASE winnable: **no verdict** -- `check_invar_ic3` reached BMC bound 109 in 5662s without a
  proof or a counterexample.
So the goal-tightening is NOT yet validated. Under the *old, looser* goal the disguise items
proved REQUIRED in ~440s because those were fast UNSAT proofs; tightening to {178} pushed the
winning path to 110+ transitions, and nuXmv can neither find that deep counterexample nor close
the inductive invariant. Consequence: base-winnability under {178} is currently UNPROVEN, which
makes any "REQUIRED under {178}" result vacuous until base is re-established. This is a
tractability wall, not (as far as we know) a modeling break.

### Path forward -- decompose the bomb proof at the volcano waypoint
Don't prove "reach rm178 without the bomb" (deep, intractable). The bomb's necessity is LOCAL:
Matches+Hair_Rejuvenator -> causedEruption (L3) -> gates rm82->83 -> rm84 sets gIslandStatus:=100.
Structurally (already verified) rm178 is reachable only through gIslandStatus 100->102->103->
104->105 (rm92 states 15/22 are EXITs, so state 28 is only via the ==102 entry). So prove the
SHALLOW waypoints instead:
1. base: `room=84` (or gIslandStatus==100) is reachable  -- shallow, should be fast.
2. bomb pinned off: `room=84` / gIslandStatus==100 is UNREACHABLE  -- shallow UNSAT => bomb
   required to reach the volcano, hence required for {178} by the forced gIslandStatus chain.
This sidesteps the 110-step unroll entirely. Same trick applies to re-confirming base: prove the
volcano waypoint reachable shallowly, then argue the 84->178 tail as the forced linear chain
(or per-gIslandStatus-step shallow queries) rather than one deep EF.

## ms-domain silent-drop fix (2026-07-20)
op_bomb.py's log carried `Warning: cannot assign value K to variable ms_<r>_<script>` for 6
machines (rm101/151/152/15/54 + boreScript rm62). Cause: each machine's TOP state does an
ADVANCE, targeting K_max+1, one past the declared range `min(states) .. max(states)`; nuXmv
silently DROPS the out-of-range next() write. Characterized with tools/.../probe_dom.py:
all 6 are ADVANCE-off-the-end to a handler-less state (no delivery/write/get there), and NONE
are on the endgame path (82/83/84/85/92/78/77/75 clean) -- so the bomb/disguise/endgame
conclusions are unaffected. Still fixed on principle (never drop a write silently): `_render`
now widens each ms domain to cover every value the machine can be ASSIGNED (ADVANCE/JUMP/
SETSTATE/arrival targets), making the off-the-end target an explicit absorbing no-op state.
0 out-of-range assignments after the fix; test_control_oracle (32) + test_everything (25) green.
