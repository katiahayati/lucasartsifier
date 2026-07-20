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

## Open validation
The 900s-timeout run gave no verdict (base winnability alone > 900s, and the *before*-gate
baseline also didn't finish in ~15-20 min -> it's the engine's inherent cost, not the gate).
op_base.py (base-only, timeout 2400s) is staged; the full run is task #16 (after the above).
