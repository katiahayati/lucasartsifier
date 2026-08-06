# KQ6 patched-build play-test plan

Written 2026-08-03 from the shipped spec set; current build **v18** (2026-08-04,
`build/kq6_patch_v18/patch`, 15 scripts, 341/341 compiled — the cliff guard is the up-step
"Not yet!" refusal in rCliffs (finding #9), with rm320's cue arm-gate as backstop; the v13
rm300 re-route is retired (finding #10) and the stock shortcut is back). Every row below is
generated from the live specs, not from memory:
reproduce the table with `python3 src/snapshot.py KQ6 --placements`.

**Install**: DELETE any previous patch files from the game copy first (a stale set was found
live on 2026-08-04: 11/425/460/470.* from Aug 1), then copy `build/kq6_patch_v18/patch/*` in.
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
  walk toward rm580 from rm550. Expected (v18, finding #13): walking onto the trail says
  "Not yet!" ONCE and a small turn-back script walks Alexander a few steps south, then
  returns control. Approach again → same again. Down/side movement unaffected.
  (History, one guard, three findings: v15's arm-gate HUNG — un-gated handsOff sibling,
  #11; v16's in-clause refusal MACHINE-GUNNED — a doit clause re-fires every cycle, #12;
  v17's silent gate let Alex WALK OFF THE SCREEN — the zone was the wall, #13. The fix is
  the game's own guard-post idiom: decline = turn back, injected as `sgTurnBack`, armed
  under `(not (gCurRoom script:))` so it fires once per approach.)
  ✅ PLAY-VERIFIED 2026-08-04 (user, v18): "it wooooooorked" — message once, turn-back,
  control returned.
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
| cliff rock-stepping (v14 refusal — the primary gate now) | same four, ONLY in capture stage (tribute paid, not yet seized) | step onto the first rock (free), try to step UP again → "Not yet!" refusal, ego keeps controls, step back down works. All four up-step clauses are wrapped (`RockStep::handleEvent` → `takeStep`); `stepDown` and `takeFirstStep` untouched. Applies on both rm300 and rm320 faces (shared code) | pre-tribute climbs untouched; in stage with the four, stepping is stock |
| rm320→rm340 (cue arm-gate, v12 — now the BACKSTOP) | same | if anything reaches the ascent cue without stepping (the cheat path), the ascent silently does not arm | with the four, ascent arms as stock |
| rm300→rm340 (solved-puzzles shortcut) | — | **v15: the shortcut is STOCK again** (the v13 nav re-route retired by play feedback: whoever passes the step guard has already been vetted, and re-imposing the full climb on them was pure cost). Coverage: the shortcut route's own base wall is RockStep-stepped, so the step refusal fires there | after any allowed climb of rm300's face, stepping off the top jumps straight to the summit, exactly as stock |
| rm340→rm405 (catacombs capture) | same four | climb/be seized without them — the CAPTURE arming is gated, so the guards must not throw you in | capture proceeds |
| rm340→rm440 (lair) | same four | as above | as above |

✅ **THE WHOLE CATACOMBS FLOW PLAY-VERIFIED 2026-08-04 (user, v15)**: refusal on the climb
without the four; with them the capture, the traversal, and the EXIT all run stock; and the
post-catacombs re-climb and re-entry work — no over-block, and the finding #5/#6 hang sites
(the arrival commit, the Celeste walk-out) are clean in live play.
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

## RETEST QUEUE — 2026-08-05, v22 (the wedding-fuse hold; 80.SCR/80.HEP new)

**The console-ready version of this queue — exact commands, no flag arithmetic (ScummVM's
`sf`/`cf`/`tf` know KQ6's flag base) — is `docs/KQ6-RETEST-V22-CONSOLE-SHEET.md`. Play from
that sheet; this table is the log-side record.**

Everything below is OPEN; ✅ rows from the findings log are not repeated. Console state is
for exercising a guard — E-row verdicts stay honest (no writes). Shared recipes:
**items** `send ?ego get <N>` / `put <N> 0` (numbers in "The items" above; letter = 20);
**global flags** flag N → word `g(137+N/16)`, mask `$8000 >> (N mod 16)` — read `vv g <w>`,
write the OR'd value back (worked: flag 58 → g140 mask 32; flag 25 → g138 mask 64;
flags 1/2 → g137 masks 16384/8192); **region flags** are object properties — sends resolve
only in loaded segments, so run `send ?rgCastle …` while standing in a castle room, and
after `room <N>` close the console and let the room draw first (`room` only writes the
pending-room global). Wedding setup block (letterless, fuse lit):
`send ?rgCastle setFlag 709 32768` (ghost boy) · `setFlag 710 256` (Cassima) ·
`setFlag 711 512` (armed) · `weddingRemind 10`. Reads:
`send ?rgCastle weddingRemind` / `weddingMusicCount` / `tstFlag 709 2`.

| # | test | why open | state | do → expect |
|---|---|---|---|---|
| R1 | wedding: resume on pickup | hold ✅ 2026-08-05; "not stuck forever" unproven | rm710 + wedding block, letterless | wait 30s (held) → `send ?ego get 20` → music ≤10s by itself; escalation/corral/Saladin stock |
| R2 | wedding: with-letter stock path | intended route must equal stock | wedding block + `get 20` first | 710 panel (ALIZEBU) → browse 770 → exit → music ~instant, count jumps 2, fast corral |
| R3 | wedding: treasures-FIRST trace (finding #3's own) | #3 observed permanent guard-posting — that was the (now-frozen) escalation | wedding block, letterless | browse 770 FIRST, exit (still no music) → 720 lever still opens (dodge roving dogs — they must stay transient, no permanent post) → fetch letter at 781 → music on pickup |
| R4 | Charon v20 (cup conjunct joined the verified wrap) | v19 wrap verified, then changed | walk 650→660; `get 7 15 24 46`; cup empty | board → refusal names the cup, no hang; fill at Styx (game's verb) → board crosses; also `put 15 0` → refusal; restore, `put 24 0` → refusal |
| R5 | Realm interior stock (v20 removed 670/680 guards) | v19 arm-events HUNG the win ride | continue R4 complete | 670→680→690 mirror win → wonDeadScript plays, ride back, zero refusals/hangs past Charon |
| R6 | mists lampless approach (v18 turn-back) | #11→#12→#13, final form never played | `room 550`; `put 19 0` | north trail → ONE message + ~35px walk-back, controls live; repeat → same; rm560 east edge silently shut; `get 19` → both normal |
| R7 | mists lampless REVISIT (recorded over-block risk) | flag-14 chain may REQUIRE a lampless 580 return | rain done (flag 25: g138 \|64) + lamp traded at 240 | 550→580 → our refusal; then confirm the mare still shows at rm340 when due. If a required revisit is walled → OVER-BLOCK finding |
| R8 | cliff ALLOW + down-climb | refusal ✅; pass-through never played | `vv g 144 30`; g137 := (v\|8192)&~16384; `get 2 18 41 48` | rocks climb stock (no refusal), down-steps always free, summit shortcut stock |
| R9 | catacombs captures 340→405/440 | gated capture arming unplayed both ways | same flags/items as R8; WALK into rm340 (arming reads the approach — don't teleport in) | without the four → guards must NOT seize; with all four → capture proceeds |
| R10 | castle doors 220→730 / 230→710 | `[W]` guards, never played | short: `get 8 24 27 23`; long: `get 8 17 24 44 23` | each item `put` in turn → refusal, no move; full set crosses; long door must NOT demand the nightingale |
| R11 | rm420 throwSkull + room regression | unplayed; we overwrite Sierra's own patch | `room 420`; `get 11` | throw at gears → refusal, skull kept, alive; ceiling/brick business fully stock |
| R12 | mint/peppermint deletions | unplayed | `get 23`, `get 31` | wrong-object use no longer consumes; rm750 genie feed still works (fold into R13) |
| R13 | E-rows: both wins + THE DEFEAT | final bar; and E.4 is the doctrine the old fuse-skip protected — v22 changed that behavior, so prove the loss survives | none — honest runs | short win; long win; and with letter fetched, let the wedding complete → the losing end (rm94 credits) must still be reachable |

## Reporting

Per defect: room, what you did, expected vs got, and a save right before. The three
findings that most change the code: a guard that HANGS (controllability bug), a guard
that fires on a legitimate path (over-block — B/C twins), and a PREVENT that walks
through (misplacement). "Findings identical to stock" is also a result — say it.

## Findings log (live)

| date | room | finding | verdict |
|---|---|---|---|
| 2026-08-05 | rm550 | **NOT a defect, and it RETIRES the A2 over-block risk: druids on the mists shore of a "fresh" game = leaked flag 25.** Flag 25 is "visited the mists and LEFT" (`rMist::dispose`, rMist.sc:42), and the shore ambush (rm550.sc:282, 25 ∧ ¬14) is the game's FORCED-REVISIT mechanic — its `captured` script ends in a direct `newRoom: 580`, bypassing the trail crossing the lamp guard wraps. So the required lampless 580 return is delivered by carry, never by the guarded walk: the recorded over-block risk is structurally moot (R7 re-aimed at confirming the carry + flag 14). The user's fresh game had flag 25 from the test session (an earlier `sf 25`, or a restart from inside a mists room); `tf 25`/`cf 25` on fresh starts. | environment + measurement; R7 rewritten |
| 2026-08-05 | rm680 | **NOT a v22 defect: hang after the Lord of the Dead challenge = a STALE v19 `680.SCR`** (finding #15's exact signature — v20 fixed it by *removing* 670/680 from the set, so a copy-over upgrade kept the hanging file). Clean delete-then-copy install resolved it, user-confirmed. Second bite of this trap (first: 2026-08-04, Aug-1 leftovers); the retest sheet now leads with `rm -f *.SCR *.HEP *.VOC` + the authoritative v22 list. | environment, fixed; R5 (interior stock) still to run deliberately on the clean install |
| 2026-08-04 | rm550 | **FINDING #13 (real, FIXED in v18): the v17 silent gate let Alex walk off the screen.** The control zone was the only thing that ever stopped the northward walk — with the crossing un-armed and no message, nothing bounded the motion. Fix: the declined positional crossing now behaves like the game's own guard-post: an injected `sgTurnBack` script (message once → walk the ego ~35px back along the crossing's own dominant axis, derived from the crossing script's first motion target → hands on), armed in the clause's else under `(not (gCurRoom script:))` — once per approach structurally, no loop, no walk-off, no hang. Falls back to the v17 silent gate when no refusal line or motion target derives. | fixed in v18, re-test A2 |
| 2026-08-04 | rm550 | **FINDING #12 (real, FIXED in v17): the v16 positional refusal MACHINE-GUNS.** Play: "Not yet!" keeps firing without ever clearing, and it doesn't interrupt Alex's walk. A doit clause re-evaluates every game cycle while the ego stands on the control zone — there is no once-per-action moment to hang a refusal on, and nothing in the wrap stops the ego's motion. Fix: positional armings get a new placement kind, `arm-clause` — the WHOLE clause gated with NO else (`handsOff` inside, so no finding-#11 hang; no message, so no loop). Lampless, the trail is a silent wall, exactly rm560's east-edge idiom one screen over. Refusal-with-message on a doit crossing needs turn-back motion machinery (stop + walk the ego off the zone) — deferred; candidates recorded with the lite-mode musing. ⚠️ Same latent hazard noted for the `direct` positional refusals (rm340's cave mouth): its PREVENT case has not been exercised in play — if an item can be absent post-catacombs, it would loop the same way. | fixed in v17, re-test A2 |
| 2026-08-04 | rm550 | **FINDING #11 (real, FIXED in v16): the mists carry-in guard HANGS.** Lampless approach to rm580: the crossing is armed from rm550's doit — `(cond (… (global1 handsOff:) (setScript: walkNorthScript)))` — and the arm-event wrap gated only the bare `setScript`, so the un-gated `handsOff` sibling fired and controls never returned. Root cause one level down: the clause is POSITIONAL (the player walked onto the trail), but rm550 HOISTS the `onControl` read into a temp, and the positional classifier only read the inline spelling — so a player move was classified as an adversarial event. Fix: `analyze_room` tracks onControl-derived variables per method (`octx`), positional armings are now refusal-bearing `setscript` placements (the whole clause wraps, `handsOff` inside the guard, "Not yet!" in the else — the same doctrine the direct-positional `newRoom` case always had). | fixed in v16, re-test A2 |
| 2026-08-04 | rm300 | **FINDING #10 (UX, FIXED in v15): the v13 nav re-route taxed vetted players.** Stock gives repeat climbers a shortcut (climb screen 1, jump to the summit); the re-route made everyone climb the whole cliff again. With the v14 step refusal in place the re-route protects nobody — an itemless capture-stage player is refused on the base wall's own rocks — so `_guard_arrival_entries` now treats nav-assign as a LAST resort, applied only when no chain refusal landed. rm300 reverts to stock (300.SCR leaves the patch set). | ✅ PLAY-VERIFIED 2026-08-04 (user: "it woooooorks") — shortcut back to stock |
| 2026-08-04 | rm320 | **FINDING #9 (UX, FIXED in v14): the arm-gate is a silent dead-end.** Play: the re-routed climb goes up two screens of faces and then "it just... stops" — the flagged silent-wall risk, confirmed as bad as feared. Fix (user-designed): refuse at the STEPPING, the true controllable moment. `trigger.find_cue_chain_armings` reads the delivering cue case off the room's cue method (case 1 → `nextCliffUp`), finds the chain that cues it in the room's `(use ...)` files (`nextScreenUp` ← `takeStep`), and walks the armings back to the controllable handler — `RockStep::handleEvent`, where `wrap_all_armings_in_source` wraps ALL FOUR up-step clauses with a "Not yet!" refusal (one wrap is a bypass — finding #4's lesson, third appearance). Down-chains cue 0/-1 and never enter the walk, so descent cannot be caught. `takeFirstStep` (ground → rock 1) is outside the chain and stays free: the refusal comes at the first continuation step, one rock up. The v12/v13 gates remain as backstops. New emitted file: 21.SCR/HEP (rCliffs). | ✅ PLAY-VERIFIED 2026-08-04: PREVENT ("it guards the second step", user-accepted) and ALLOW (with the four, the climb and capture proceed) |
| 2026-08-04 | rm300 | **FINDING #8 (real, FIXED): the v12 cliff gate had a bypass — the solved-puzzles shortcut.** With nothing in hand and the capture stage armed (g137=$2E00: flag 1 clear, flag 2 set), the climb went straight to the summit and the winged ones threw the player in. Root cause: flag 157 (set on every rm340 arrival) makes `rm300::init` point its `north` at 340, and the region's step-completion exits via `newRoom: (global2 north:)` — a crossing with no `newRoom:` in rm300's own file, so the frontier room silently got no wrap (the model's frontier {300, 320} was right; the placement covered only rm320 — and the capture stage REQUIRES a repeat climb, so the guarded route was exactly the one the stage never uses). Fix: `trigger.find_nav_assign` — the shortcut ASSIGNMENT is gated, `(if <or not-stage items> (self north: 340) else (self north: 320))`, so a non-compliant climb takes the game's own long way into rm320, where the cue-gate refuses; an assignment has no scene, so no hang class. Plus: a frontier room with no wrap now marks the row `entry-frontier-PARTIAL` — a bypass can never again ship silently. Re-test with v13: same save, climb → expect routing through the upper faces and the ascent refusing to arm. Also found in the same session: the install had stale Aug-1 patches (11/425/460/470.*) alongside v12 — delete old files when installing. | fixed in v13, re-test |
| 2026-08-04 | rm640 | **FINDING #7 (real, FIXED): the ticket refusal hangs — dead controls.** The clause-wrapper recognised only `cond` clauses; SCI1.1 verb dispatch is a SWITCH, so the wrap fell back to the bare `setScript` and let `(global1 handsOff:)` fire before the refusal. Fix: `_enclosing_clause_body` now recognises switch cases and wraps the whole case, so control-stealing siblings sit inside the guard. Re-test the ticket refusal in v11. | fixed, re-test |
| 2026-08-04 | rm340 | **FINDING #6 (same root as #5): the Celeste walk-out hangs.** Leaving the catacombs with Lady Celeste (a cutscene arrival into rm340) hit the same init refusal — "Not yet!", exit anyway, hang. No item demand belongs on that path at all (the shield is deliberately unflagged: re-obtainable, the standing shield ruling). Fixed by removing the init refusals. Re-test the Celeste exit in v11. | fixed, re-test |
| 2026-08-04 | rm340 | **FINDING #5 (real, FIXED): refusing an arrival commit hangs.** Without the catacombs four, the capture wraps fired "Not yet!" inside rm340::init — but the seizure was already half-armed, the walk to the guards' room happened anyway, and leaving it hung the game. With items the capture was fine. Fix (user-prescribed): re-site the refusal to the controllable crossings INTO rm340 — the cliff climb — stage-conditioned with the game's own arming test (`(or (not (and (not (proc913_0 1)) (proc913_0 2))) <the four>)`), the in-room capture is restored to stock and `_also_place_capture` is retired (all its sites were this hazard class). ⚠️ The entry re-site itself broke twice in one night (garbage stage text from an edited file; interior returns wrapped against the compliance doctrine) and was DORMANT in v11 — the three capture rows shipped UNPLACED. **RE-SITE LANDED 2026-08-04 (v12)**: the site list is the MODEL's pocket frontier (`guards.commit_entry_frontier` — `reach_avoiding` keeps interior returns out by construction), the stage comes from the PRISTINE init's same-script proc-call clause heads with prev-room heads dropped (what survives is exactly the capture-arm test), and the wrap is a no-else arm-gate on rm320's cue arming of `nextCliffUp`: `(if (or (not (and (not (proc913_0 1)) (proc913_0 2))) <the four>) (setScript: nextCliffUp))`. ⚠️ SILENT-WALL RISK flagged for play: in capture stage without the four, the ascent simply does not arm — see the new B row. The three controllable rm340 exits (cave mouth, lair, nightMare) remain guarded. | fixed in v12, re-test |
| 2026-08-03 | rm220 | **FINDING #4 (real, FIXED): the short door's guard had a bypass** — `wearClothingScr` arms from egoDoVerbCode::doVerb AND guardHut::doVerb (clothes used on the HUT), and placement wrapped only the first controllable arming. Fix: `trigger.find_all_armings` + apply-time sweep — a machine with N controllable armings gets N wraps, extras reported on the row (`also_wrapped`). Corpus-wide effect: exactly rm220 (1→2 guards). **Play-verified fixed 2026-08-03: both armings gate properly (v7).** | fixed+verified |
| 2026-08-03 | rm880 | caught→jail→wedding→death when entering with no plot state | stock death, out of scope; plan A1 amended to the hide path |
| 2026-08-03 | rm710/840 | **FINDING #3 (real, PARKED by user ruling): the LONG route's letter seal is the TREASURE DISCOVERY, and it is unguarded.** Playing treasures-before-letter posts guards at the secret entrance — actor-blocking, permanent even after the dungeon reset clears reg337 — and the wedding then demands the letter you can no longer fetch. The rm880 hold covers the SHORT route only; rm740's held write fires after the funnel has sealed. The engine cannot derive this (the control-map gap: the seal is actors, not registers; and the tempting causality fix — "a capture clear is not a reversal" — would be overfit, since reg337 genuinely clears). USER RULING 2026-08-03: no declared/oracle-sourced specs — everything stays derived, this stays a KNOWN GAP until the control map is modeled. Workaround for players: get the letter before opening the treasure door. | parked |
| 2026-08-03 | rm230 | hand-click on the painted door BEFORE the spell shows our refusal instead of the stock "won't open" line | cosmetic over-wrap: the guard wraps the whole verb-5 cond clause (deliberate — siblings must not fire ahead of a refusal), which also captures the pre-spell else-arm. Fix direction if ever wanted: wrap only the arming branch when sibling arms are UNPRODUCTIVE (message-only) — the `_clause_productive` question again. Not fixed mid-play-pass; the wrapper is play-validated on LSL2 and re-cutting it re-cuts every guard. |
