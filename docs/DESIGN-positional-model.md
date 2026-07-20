# Positional model + forced doit (the "no more special-case gate rules" design)

**Decided 2026-07-19 with the user.** Replaces the hand-coded `doit_death_gates` disguise
rule with a general model from which the disguise (and every coordinate-based gate/death)
falls out automatically. Only PIC control-map lookups (`onControl`) stay resource-bound.

## The core idea

A "gate" is a room where death/lock is reachable and exactly one state makes it unreachable.
That escape condition IS the requirement. It falls out of ordinary reachability IF two things
are modeled that we currently drop:

1. **Consistent position.** Today each positional test (`inRect`, `edgeHit`, `posn`) is an
   *independent* opaque coin, so the solver can be "at the east edge" and "not in the rect"
   simultaneously — a phantom crossing that skips the hazard. Fix: give the ego ONE free
   (opaque) `(x,y)` per room and DERIVE the predicates from it:
   - `(inRect a b c d)` -> `x>=a & x<=c & y>=b & y<=d`
   - `(edgeHit)==N`     -> the ego is at edge N: east `x>=~316`, west `x<=~4`, north
     `y<=~horizon`, south `y>=~186` (screen 320x190, menu bar at top).
   - `(posn: ...)` compares, `inRect` variants -> same, over `(x,y)`.
   `x,y` stay free (a free player choice), but ONE consistent choice, so
   `crossing east (x>=316) => inRect (316∈[86,333])` unavoidably.

2. **Forced doit.** `doit` runs every game cycle automatically — its effects are NOT the
   player's option. Today we model them as optional player actions, so the solver can walk
   into the danger rect and simply *not* trigger the henchmen. Fix: emit `doit` effects as
   FORCED next-state updates (applied whenever their guard holds, respecting `cond`
   first-match), not action-gated. Then `(inRect & henchStatus==0)` FORCES `henchStatus:=1`
   -> henchScript -> death. Motion/Chase completions are already cues (ADVANCE), so "the
   enemy reaches you" needs no geometry.

## Two passes (reuse IC3)

- **Pass 1 — deaths**: the `gCurrentStatus:=1001` writes already in the AST (incl. rm82's
  switch and the now-position-bound ones). Gives the alive-reachable region.
- **Pass 2 — winnability** over that region (`goal & !dead`), positions opaque-but-consistent.
  Softlocks = reachable-alive states that can't reach the goal; requirements = pin-off/recheck.

The current merged `!(goal & !dead)` already excludes death-paths, so the split is mainly a
clarity/efficiency refinement; the CORRECTNESS enablers are (1) consistent position and
(2) forced doit.

## Why this gets the disguise with NO special rule

Winning requires crossing rm47 (`east 48`) => reaching `x>=316` => `inRect` (unavoidable, one
`x`) => forced doit sets `henchStatus:=1` if `henchStatus==0` => henchScript => death. So a
win must have `henchStatus==8`, i.e. `gBodyWaxed & egoView==151` (the init derivation), i.e.
the disguise. Pin the disguise items off -> unwinnable -> REQUIRED. No over-require, no hand
rule. => DELETE `_doit_death_gates`.

## Residue = `onControl` only

`(onControl: $0004)` is a lookup into the PIC control bitmap — not a function of `(x,y)` we
can derive. That's rm82's forward elevator. Handle those as DECLARED gates (like
`goal_rooms`); ScummVM-in-the-loop is the eventual "never declare again" endgame. Cel
bounding boxes (door footprint, catch radius) are NOT load-bearing once motion-completions
are cues and outcomes are scripted flags.

## Build order

1. Positional layer: `atom()`/`_send_atom` recognize `inRect`/`edgeHit`/`posn` -> a `POS`
   guard; emitter declares free `x,y` IVARs and `gexpr` renders `POS` over them. `onControl`
   stays opaque (later: declared).
2. Forced doit: emit doit-sourced effects as forced next-state updates.
3. Delete `_doit_death_gates`; keep test_everything.py green; re-point the disguise test at
   "winning forces henchStatus!=0" instead of the hand rule.
4. (Deferred, on approval) end-to-end: base winnable + disguise items REQUIRED.
