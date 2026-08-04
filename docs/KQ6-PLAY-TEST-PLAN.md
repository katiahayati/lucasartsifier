# KQ6 patched-build play-test plan

Written 2026-08-03 from the shipped spec set (`build/kq6_patch_v6/patch`, 13 scripts,
341/341 compiled). Every row below is generated from the live specs, not from memory:
reproduce the table with `python3 src/snapshot.py KQ6 --placements`.

**Install**: copy `build/kq6_patch_v6/patch/*` into a COPY of the game folder.
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

⚠️ **Use the HIDE path, not the caught path.** rm880 has two outcomes: get caught →
jail → wedding cartoon → DEATH (stock behavior, out of the hold's scope — a death is
a reload, and it is preventable in-room, so the guard deliberately does not touch it;
field-confirmed 2026-08-03, one run burned on it). The wrapped write lives in the
SURVIVING scene: when warned, **hide** (the `hideEgo` flow) and let
`watchGuardsComeBack` play to completion — its state 8 is the world-seal.
- **PREVENT**: hide-and-watch WITHOUT the letter, survive the scene. Expected: the
  scene plays normally but the world does not seal — the letter must still be
  obtainable afterwards, and rm730/rm870 must still accept showing it.
- **ALLOW**: hide-and-watch WITH the letter. Expected: wedding state advances exactly
  as stock.
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
| 2026-08-03 | rm880 | caught→jail→wedding→death when entering with no plot state | stock death, out of scope; plan A1 amended to the hide path |
| 2026-08-03 | rm230 | hand-click on the painted door BEFORE the spell shows our refusal instead of the stock "won't open" line | cosmetic over-wrap: the guard wraps the whole verb-5 cond clause (deliberate — siblings must not fire ahead of a refusal), which also captures the pre-spell else-arm. Fix direction if ever wanted: wrap only the arming branch when sibling arms are UNPRODUCTIVE (message-only) — the `_clause_productive` question again. Not fixed mid-play-pass; the wrapper is play-validated on LSL2 and re-cutting it re-cuts every guard. |
