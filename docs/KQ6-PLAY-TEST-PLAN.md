# KQ6 patched-build play-test plan

Written 2026-08-03 from the shipped spec set; current build **v12** (2026-08-04,
`build/kq6_patch_v12/patch`, 14 scripts, 341/341 compiled — rm320's entry-frontier arm-gate
joined). Every row below is generated from the live specs, not from memory:
reproduce the table with `python3 src/snapshot.py KQ6 --placements`.

**Install**: copy `build/kq6_patch_v12/patch/*` into a COPY of the game folder.
**Revert**: delete those files — the game's own resources are never touched.
**Method**: save (F5) immediately before each test point; every PREVENT test needs its
ALLOW twin — a guard that blocks the softlock but also blocks the legitimate path is a
worse bug than the softlock. Watch for hangs and handsOff-stuck states after every
refusal: the LSL2 history says refusal-time hangs are the #1 runtime defect class.

## The items

| # | name | | # | name |
|---|---|---|---|---|
| 2 | brick | | 23 | mint |
| 7 | deadMansCoin | | 24 | mirror |
| 8 | dagger | | 27 | nightingale |
| 11 | skull | | 31 | peppermint |
| 15 | gauntlet | | 41 | scarf |
| 17 | handkerchief | | 44 | skeletonKey |
| 18 | holeInTheWall | | 46 | teaCup |
| 19 | huntersLamp | | 48 | tinderBox |
| 20 | letter | | | |

## A. The two new, highest-risk guards — play these first

### A1. The wedding hold (register-write, flag 166) — rm740 + rm880
Holds the "wedding has started" flip until the **letter (20)** is in hand. The flip's
two writers are wrapped: rm880's guards-return cutscene and rm740's twin site.

**STOCK short-route flow (user-documented from play, 2026-08-04):** enter the vizier's room
(rm880); the vizier's room is freely re-enterable (the nail fetch is fine) — the one death is
CROSSING THE GUARD POST letterless, and it is a FAIR death (the letter is still obtainable from
that screen: walk back in and take it — the LSL2 rm47 disguise class, correctly unguarded;
user-corrected 2026-08-04). With the
letter: give Cassima (rm870) the dagger → guards-away state arms → hide from the guard dogs
again → leaving the hiding place starts the wedding. So on the SHORT route the letter is
design-mandatory pre-wedding; our hold's PREVENT case is reachable only by breaking that
sequence (or on the long route, where the seal is the parked treasure-corral gap).

⚠️ **Use the HIDE path, not the caught path.** rm880 has two outcomes: get caught →
jail → wedding cartoon → DEATH (stock behavior, out of the hold's scope — a death is
a reload, and it is preventable in-room, so the guard deliberately does not touch it;
field-confirmed 2026-08-03, one run burned on it). The wrapped write lives in the
SURVIVING scene: when warned, **hide** (the `hideEgo` flow) and let
`watchGuardsComeBack` play to completion — its state 8 is the world-seal.
- **NO MANUAL FLAG-SETTING** (user ruling 2026-08-04): a state the game's own sequence
  never produces is not evidence — do not console-set 710/711 to reach a case. Flag
  READS as assertions are fine; writes are not.
- **ALLOW**: hide-and-watch WITH the letter — ✅ VERIFIED 2026-08-04: the patched short
  route plays identically to stock through the wedding.
- **PREVENT**: unreachable by real play on the SHORT route — stock design forces
  letter-before-wedding (see the flow above). The letterless-wedding case exists only
  on the LONG route via the treasure corral, which remains the PARKED gap (finding #3).
  ⚠️ 2026-08-04: the forced-escort derivation designed for it was MEASURED AND REFUTED
  before implementation (reg378's only reader is the corral's own one-shot latch; the
  containment is guard-actor patrol + region-object properties, stores the model does
  not carry). The gap is pinned RED in `test_toll`. USER RULING 2026-08-04: ACCEPTED as a
  shipped limitation, deprioritized — castle-scope reload, and Saladin's proof demand tells
  the player what is missing. Player workaround unchanged: letter before treasure door.
- rm740's wedding scene is the twin writer — repeat both cases there.
- ⚠️ This is the game's central plot branch. Verify BOTH endings still trigger their
  correct wedding (alexWedding vs vizierWedding at rm740) after the hold has fired.
- Defect watch: guards visibly "returned" but castle behaves as if they hadn't.

### A2. The mists carry-in — rm550→rm580 and rm560→rm580, huntersLamp (19)
Sailing to the Isle of the Mists and approaching the Druids' bonfire (rm580) demands
the lamp; the trade itself is untouched.
- **PREVENT (550→580)**: trade the lamp at the docks (rm240), sail to the mists,
  walk toward rm580 from rm550. Expected: the crossing's cutscene does not arm; no
  capture, no death. You must be able to walk away and finish the SHORT ending.
- **PREVENT (560→580)**: same but via rm560's east edge. Expected: the east exit is
  closed (a wall, silent — the game's own idiom); rm560's other exits still work.
- **ALLOW**: carry the lamp in. Expected: capture happens, cage inset opens, and with
  the waters poured `makeRain` fires exactly as stock. Pour-the-waters flow must be
  untouched — the guard demands only the lamp, never the waters.
- **REVISIT question (the one only play can answer)**: after the Druid business is
  done and the lamp traded, does the long route ever need to RE-ENTER rm580? If yes,
  the guard walls it — report immediately.
- **NEGATIVE**: the lamp trade at rm240 must work at any time, before or after the
  mists; the peddler scene must be byte-normal.

## B. Boundary guards (edge refusals with the game's own refusal line)

| edge | demands | PREVENT: arrive without → expect refusal line, no move, no hang | ALLOW: with all → normal crossing |
|---|---|---|---|
| rm220→rm730 (castle short door) | dagger 8 + mirror 24 + nightingale 27 + (mint 23 \| peppermint 31) | try the short door missing each item in turn | full set crosses |
| rm230→rm710 (castle long door) | dagger 8 + handkerchief 17 + mirror 24 + skeletonKey 44 + (mint 23 \| peppermint 31) | as above; ALSO: after the Druids burn Beauty's clothes, the SHORT door items must NOT be demanded here | full set crosses |
| rm340→rm155 (Realm flight) | deadMansCoin 7 + skull 11 + mirror 24 + teaCup 46 | board the nightMare without each | full set flies |
| rm340→rm370 (Lady Celeste's flyer) | brick 2 + holeInTheWall 18 + scarf 41 + tinderBox 48 | the catacombs four, demanded before the one-visit spring | full set proceeds |
| rm320→rm340 (cliff ascent, v12 arm-gate) | same four, ONLY in capture stage (tribute paid, not yet seized) | solve the ascent puzzle in capture stage without the four → the climb does NOT arm (⚠️ silent — confirm no hang, controls stay live, and down-climb still works) | pre-tribute climbs are untouched at any inventory; in capture stage with the four, the ascent runs as stock and the in-room capture then proceeds with all items |
| rm340→rm405 (catacombs capture) | same four | climb/be seized without them — the CAPTURE arming is gated, so the guards must not throw you in | capture proceeds |
| rm340→rm440 (lair) | same four | as above | as above |
| rm640→rm650 (knight's room, ticket surrender) | handkerchief 17 + skeletonKey 44 | give the ticket without them → refusal, ticket KEPT | with both, surrender + crossing normal; confirm 650→640 return really is impossible (one-way, user-confirmed) |
| rm660→rm670 (Charon's crossing) | gauntlet 15 + mirror 24 | attempt the crossing without each | normal |
| rm550→rm580 / rm560→rm580 | huntersLamp 19 | see A2 | see A2 |

(rm420→rm435 has a spec but deliberately NO on-disk guard — its demand is covered by
the rm340 capture guards. Nothing to test beyond B's rm340 rows.)

## C. Exit guards (register-valued; the commitment pattern)

| edge | demands | PREVENT | ALLOW |
|---|---|---|---|
| rm680→rm155 (Realm boundary out) | cup filled (flag 58) AND mirror shown (`(ScriptID 70 0) stateOf690:` == 2) | try to leave with an empty cup, or without having shown Death the mirror → held in, but rm660/670 must remain reachable so you can still comply | filled + shown → normal exit |
| rm670→rm660 (back through Charon) | mirror shown == 2 | leave rm670 before the rm690 business → held | after holdUpMirror → normal |

⚠️ These are `arm-event`/`edge-exit` placements — the kind that can misplace silently
(Dagger's lesson). If a PREVENT case walks through unimpeded, the guard is misplaced:
report which edge, don't improvise.

## D. Action refusals and sink deletions

| site | test |
|---|---|
| rm420, `throwSkull` | Holding the **skull (11)**: throw it into the gears → REFUSAL LINE, skull kept, no death. Without the skull the option must behave as stock. The machinery puzzle must still be solvable the intended way. ⚠️ rm420 overwrites Sierra's own shipped patch — regression-test the whole room (crushing ceiling, brick business). |
| Main, mint 23 / peppermint 31 | The destroy-verbs are DELETED: using mint/peppermint on a wrong object must no longer destroy them (the action just doesn't consume). Feeding the genie's need at rm750 with either must still work. |
| rm240, huntersLamp | NOT patched (deliberate): the trade is normal, the peddler leaves, no second trade. Protection is A2. |

## E. Winnability (the LSL2 bar: prevented softlocks AND a finishable game)

1. **Short ending, full run**: start → win at rm180 through the short castle door.
   No guard may fire on a correctly-played run.
2. **Long ending, full run**: waters → mists (lamp) → Beauty's clothes burn →
   long door → win. Same rule.
3. **Deliberate-loss probes** along the way: at each guard in B, save, drop/omit the
   demanded item, confirm the refusal, restore, continue. One pass can cover most rows.
4. **The vizier's wedding (losing end)** must still be reachable — we guard
   softlocks, not defeats.

## Reporting

Per defect: room, what you did, expected vs got, and a save right before. The three
findings that most change the code: a guard that HANGS (controllability bug), a guard
that fires on a legitimate path (over-block — B/C twins), and a PREVENT that walks
through (misplacement). "Findings identical to stock" is also a result — say it.

## Findings log (live)

| date | room | finding | verdict |
|---|---|---|---|
| 2026-08-04 | rm640 | **FINDING #7 (real, FIXED): the ticket refusal hangs — dead controls.** The clause-wrapper recognised only `cond` clauses; SCI1.1 verb dispatch is a SWITCH, so the wrap fell back to the bare `setScript` and let `(global1 handsOff:)` fire before the refusal. Fix: `_enclosing_clause_body` now recognises switch cases and wraps the whole case, so control-stealing siblings sit inside the guard. Re-test the ticket refusal in v11. | fixed, re-test |
| 2026-08-04 | rm340 | **FINDING #6 (same root as #5): the Celeste walk-out hangs.** Leaving the catacombs with Lady Celeste (a cutscene arrival into rm340) hit the same init refusal — "Not yet!", exit anyway, hang. No item demand belongs on that path at all (the shield is deliberately unflagged: re-obtainable, the standing shield ruling). Fixed by removing the init refusals. Re-test the Celeste exit in v11. | fixed, re-test |
| 2026-08-04 | rm340 | **FINDING #5 (real, FIXED): refusing an arrival commit hangs.** Without the catacombs four, the capture wraps fired "Not yet!" inside rm340::init — but the seizure was already half-armed, the walk to the guards' room happened anyway, and leaving it hung the game. With items the capture was fine. Fix (user-prescribed): re-site the refusal to the controllable crossings INTO rm340 — the cliff climb — stage-conditioned with the game's own arming test (`(or (not (and (not (proc913_0 1)) (proc913_0 2))) <the four>)`), the in-room capture is restored to stock and `_also_place_capture` is retired (all its sites were this hazard class). ⚠️ The entry re-site itself broke twice in one night (garbage stage text from an edited file; interior returns wrapped against the compliance doctrine) and was DORMANT in v11 — the three capture rows shipped UNPLACED. **RE-SITE LANDED 2026-08-04 (v12)**: the site list is the MODEL's pocket frontier (`guards.commit_entry_frontier` — `reach_avoiding` keeps interior returns out by construction), the stage comes from the PRISTINE init's same-script proc-call clause heads with prev-room heads dropped (what survives is exactly the capture-arm test), and the wrap is a no-else arm-gate on rm320's cue arming of `nextCliffUp`: `(if (or (not (and (not (proc913_0 1)) (proc913_0 2))) <the four>) (setScript: nextCliffUp))`. ⚠️ SILENT-WALL RISK flagged for play: in capture stage without the four, the ascent simply does not arm — see the new B row. The three controllable rm340 exits (cave mouth, lair, nightMare) remain guarded. | fixed in v12, re-test |
| 2026-08-03 | rm220 | **FINDING #4 (real, FIXED): the short door's guard had a bypass** — `wearClothingScr` arms from egoDoVerbCode::doVerb AND guardHut::doVerb (clothes used on the HUT), and placement wrapped only the first controllable arming. Fix: `trigger.find_all_armings` + apply-time sweep — a machine with N controllable armings gets N wraps, extras reported on the row (`also_wrapped`). Corpus-wide effect: exactly rm220 (1→2 guards). **Play-verified fixed 2026-08-03: both armings gate properly (v7).** | fixed+verified |
| 2026-08-03 | rm880 | caught→jail→wedding→death when entering with no plot state | stock death, out of scope; plan A1 amended to the hide path |
| 2026-08-03 | rm710/840 | **FINDING #3 (real, PARKED by user ruling): the LONG route's letter seal is the TREASURE DISCOVERY, and it is unguarded.** Playing treasures-before-letter posts guards at the secret entrance — actor-blocking, permanent even after the dungeon reset clears reg337 — and the wedding then demands the letter you can no longer fetch. The rm880 hold covers the SHORT route only; rm740's held write fires after the funnel has sealed. The engine cannot derive this (the control-map gap: the seal is actors, not registers; and the tempting causality fix — "a capture clear is not a reversal" — would be overfit, since reg337 genuinely clears). USER RULING 2026-08-03: no declared/oracle-sourced specs — everything stays derived, this stays a KNOWN GAP until the control map is modeled. Workaround for players: get the letter before opening the treasure door. | parked |
| 2026-08-03 | rm230 | hand-click on the painted door BEFORE the spell shows our refusal instead of the stock "won't open" line | cosmetic over-wrap: the guard wraps the whole verb-5 cond clause (deliberate — siblings must not fire ahead of a refusal), which also captures the pre-spell else-arm. Fix direction if ever wanted: wrap only the arming branch when sibling arms are UNPRODUCTIVE (message-only) — the `_clause_productive` question again. Not fixed mid-play-pass; the wrapper is play-validated on LSL2 and re-cutting it re-cuts every guard. |
