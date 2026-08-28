# Gabriel Knight: Sins of the Fathers (GK1, SCI2/SCI32) — softlock candidates

Status: **UNVALIDATED by play.** Every row below is derived from the decompiled scripts under
`build/sweep/gk1/src` (sci-tools fork, json-ir @ 3895bc1; 212/212 scripts, 3,395/3,395 functions
decompiled). Walkthroughs were LEADS only ([[tcrf-page-carried-prompt-injection]]: a page is data);
each claim was re-grepped in the scripts. The USER has not ruled on any of it (2026-08-27, autonomous
run per [[session-2026-08-27-handoff-gk1]]).

## 0. How GK1 is built (what the model has to read)

* **Day counter** `global123` (1..10). Advanced at `(++ global123)`: `rm370.sc:72,174,231,633,740`
  (the bookshop start/end-of-day machine), `bayouRitual.sc:890/911` (day 6→7), `rm550.sc:533`
  (7→8), `rm500.sc:191` (8→9); `rm750.sc:105/118` pin 9 and 10 on the flights.
* **Day-end gates** are in ONE place — `theMapPrint.sc:231-278 endDay` (days 2-5), duplicated at
  `bookstore.sc:215-247` for the come-back-from-a-conversation path. Day 1 ends on Grace's topic 49
  alone (`grace.sc:141-146` → flag 15). Days 6-10 end from cutscenes (bayou ritual, chapel ritual,
  Gerde's card, the snake mound, the finale).

      day 2: flags 107 231 232 72
      day 3: flags 265 21 256  + has reconVeve_(38) + has wolfPhone(8)
      day 4: flags 447 248 36 227 + has tatooTrace(26) + has braceRep_(41)
      day 5: flags 73 16

* **Flags**: `proc13_0/1/2 N` = test/set/clear on the bit array in `global127` (`n013.sc`); the
  interrogation script adds `proc50_1..4` on the SAME array and `proc50_5..8` on a SECOND array
  (`global182`, "topic already said"). `(gEgo getPoints: N pts)` ALSO sets flag N (`GKEgo.sc:110-116`),
  and a Teller icon sets flag `79 + iconValue` (`GKTeller.sc:123-125`). 353 flags, ~1,900 ops.
* **Inventory**: `(global0 has:/get:/put: N)`, N = position in `GKInventory`'s `add:` list
  (`GKInvItem.sc:93`); 81 items, 26-51 of script 24 (`tile1.sc`) referenced by export. The id map
  is in `test_gk1_ground_truth.py`. ⛔ [[qfg1-softlock-ground-truth]]: ids = `add:` order.
* **Travel**: two maps (`rm200` city, `rm205` greater New Orleans); each icon does
  `(global2 cue: <room>)`, the room's `cue` arms `chgRoom` with the number as `register`, and
  `chgRoom` ends `(global2 newRoom: register)`. The interrogation screen (`rm50`) returns with
  `(global2 newRoom: global12)` (prevRoom). Death = `(global2 newRoom: 770)` into `deathRm`, whose
  dialog offers Restore / Quit(`(= global4 1)`) / Restart(`newRoom: 93`).
* **Endings**: WIN = `rm670` → `creditRm_680` (`EndGame.sc:1046/1569/1607`); `creditRm_180` is the
  OPENING credits (`openingCartoon.sc:237` → `creditRm_180.sc:193` starts day 1). There is no loss
  room: every failure is `newRoom: 770`.

## 1. Rows

Columns follow `test_kq6_ground_truth`: **A** real & caught · **B** real & missed (KNOWN_GAPS) ·
**C** confirmed safe (flagging = FP) · **D** deaths/forced losses outside the item model.
"Real" here means: the game's own scripts let the player pass a point of no return without the
thing, and a later site demands it — [[one-rule-death-is-in-scope]]: a forced death that is not
preventable from its own screen counts.

### 1.1 REAL, script-derived

| # | item / state | closing transition | later demand | mechanism (file:line) |
|---|---|---|---|---|
| R1 | **VoodooCode1** (32) — the FIRST tomb-marking sketch | day 4→5: `rm300.sc:121` inits `message1` only while `(< global123 5)`; `get: 32` exists only at `rm300.sc:1119/1368` (both `message1`) | day 5+: writing on Laveau's tomb needs `(and (not 246) (proc13_0 249) (has: 32) (has: 33))` — `rm300.sc:952,1104,1160,1347`; flag 249 = "compared both sketches", set only inside the two items' own `doVerb` (`tile1.sc:829/874`) | Without flag 246 (`rm302.sc:149/152`) the bayou HUD is torn down (`bayouMaze.sc:1560-1567,1707`), `maskAction` is never installed (`bayouMaze.sc:1700`), flag 216 is never set (`bayouMaze.sc:1899`) and the day-6 ritual is an unconditional `killGabe` → `newRoom: 770` (`bayouRitual.sc:158-166,938`). No day-2/3/4 gate names item 32 or any flag that needs it (§0 table; `grep "has: 32"` → rm300 only). |
| R2 | **rod (60) + a signal device (19/20) DEPOSITED in the left confessional** (flags 280, 281) | entering Grace's room: `sHRoom8.sc:71` sets `timeForCeremony`, and `sHRoom8` has NO exit script (its only `newRoom` is 770 at `:272`; `Hounfour.sc:175-178` routes to 899) | `EndGame.sc:637`: `(if (proc13_0 351) sPart2 else sDrJohnPunchGrace)` → `newRoom: 770` (`:1733`) | 351 is set ONLY at `sHRoom6.sc:131-132` under `(and 280 281)` when riding the elevator down; 280/281 set ONLY at `rm455.sc:818/828` (verbs 60/76 on the bench, after flag 272). The community's "leave the transmitter and the snake staff in the confessional" dead end — script-exact: the item is `signalDev_`/`signalDev2_` (19/20, verb 60), NOT `tracker` (18, verb 45, given to Mosely at `rm220.sc:1204`). Recoverable until Grace's room: `sHRoom6.sc:392-400` + `Hounfour.sc:179-181` ride back up. |
| R4 | **flag 44** — Cazaunoux's topic 54 "Real Voodoo Queens" (`hartridge.sc:256-257`, the ONLY setter) = global interrogation topic 8 "Voodoo Hounfour" (`GKTeller.sc:80-83`: global topic n shows iff flag 36+n) | day 3→4: Cazaunoux's house shuts `(>= global123 4)` (`rm270.sc:200,217,845`), and `rm270` is the only way into `rm280` (`rm270.sc:243/258`) | day 4's gate needs `tatooTrace` (26) ← `sTraceTattoo` ← `deadCrash` inset ← flag 74 (`rm450.sc:674`) ← Crash's topic 8 answering with case 42 `(proc50_3 74)` (`crash.sc:66-84`, only setter of 74) ← flag 44 | Day 3's own gate (§0) never asks: flag 256 forces ONE Cazaunoux interrogation (the bracelet, topics 8→59 or 61 → flag 67, `hartridge.sc:226/275`) but topic 54 hangs off a different branch — 50 (needs Hartridge's topic 6 said, `hartridge.sc:171-172`, `:63-67`) → 37 → 54. Skip it on day 3 and Crash never dies on day 4; the day never ends. The shipped debug catch-up lists 44 among day-3 flags (`debugHandler.sc:317`). ⚠️ Caveat: topic numbers 1-15 are the global band (`Interrogation::prep`, `GKTeller.sc:118-125`); the message resource was not read, so a local Crash topic 8 is assumed absent. |
| R3 | **BoarGuise (78) + WolfGuise (79)** held on entering Grace's room | same door as R2 | `sHRoom8.sc:331-357`: every combination lacking 366 (Gabriel robed, `:400`, only via WolfGuise verb 120 `:1050-1060`) or — with Mosely present (351) — 365 (Mosely robed, `:692`, only via BoarGuise verb 121 `:690-695`) ends in `sDJKills` → `newRoom: 770` (`:263-265`), on a 20-second timer (`:117,361-363`) | Both guises are made in the storeroom `sHRoom7` (`:378-410` masks, `:455-490` robes) and never lost before the door (`put: 78/79` only at `sHRoom8.sc:693/1053`). |

### 1.2 REFUTED by the scripts (walkthrough / agent leads that do not hold)

| lead | why it is not a lock |
|---|---|
| "Day 9 needs the **knife** (64) and Germany→Africa (`rm500.sc:189-193`) has no item guard" | Day 7 cannot end without it: `readTheScroll` state 7 (`rm540.sc:299-307`) demands `(Germany egoCutHimself:)`, written only at `rm540.sc:400` by `cutEgo`, reached only through verb 101 (`rm540.sc:585-590,1163-1176`) — and `message 101` belongs to the knife alone (`tile1.sc:497`). No `put: 64` exists anywhere. FORCED. |
| "Crash never spawns without **flag 314** (day-4-only, `neJackson.sc:213/662`), so day 5's flag 73 ← 51 ← Crash topic 36 is unreachable" | Day 4's gate needs `tatooTrace` (26): its sole source `sTraceTattoo` (`rm450.sc:401,421`) is armed by the `deadCrash` inset (`rm450.sc:1166/1311`, under flag 322), which `sDoInset` opens only under flag 74 (`rm450.sc:674`), and 74 is set only by Crash's own topic 42 (`crash.sc:82`), which needs Crash present (`rm450.sc:57-63`: flag 314 or 74). FORCED. |
| "Day 1 ends with zero item checks" — sketchbook, clay, scale, photocopy, glass, tweezers all skippable | True but harmless: every source survives (bookstore `has:`-gated respawns `bookstore.sc:186-192`; rm390 sketchbook has no day guard; rm470's clay/scale/pattern init unconditionally `rm470.sc:194-216`; the lake icon flag 64 is never cleared). Score loss only. |
| Day-5 evidence handed to Mosely (notes 45, clipping 9, reconVeve 38, twoScales 25) is consumed | No `put:` for any of them in the tree; `showMoselyPaper/Other` only set flags (`rm240.sc:1804-1980`). |
| The Day-6 tracker placed in the sekey madoule strands the day-10 tracker | Three devices come from one pickup (`bookshelf.sc:619 get: 18 19 20`); the coffin consumes exactly one of 19/20 (`rm260.sc:1050`); day 10 wants `tracker` 18 (`rm220.sc:1204`). |
| Day-7 ritual consumables (pot 61, salt 65, scroll 63) are gone afterwards | Nothing demands them later (`has: 61/65/63` → rm530/rm510 only). |
| The credit card is spent on day 8 | `giveTheCard` (`rm510.sc:839-911`) has no `put:`; the only sink is `rm220.sc:1429` (day 10). |
| Africa: rod lost / tiles misplaced / talisman lost | Rod respawns until taken (`rm710.sc:2110-2112`), no `put: 60` in Africa; tiles are freely retrievable (`rm710.sc:1606-1748,1885-1981`); talisman is re-granted at `EndGame.sc:200`. |

### 1.3 LATENT (not counted)

* `rm470.sc:1686-1692`: flag 402 ("pattern copied") is set BEFORE `copyThePattern` grants
  `sLakePatter` (31) at state 5; an abort between them loses the day-2 requirement 231
  (`neJackson.sc:1352`, sole consumer, `get: 31` sole source). The script runs `handsOff`, so no
  normal input aborts it. Same shape, benign: `rm230.sc:169-171` flag 61 before `getPhotos`.

### 1.4 Deaths with a prior-screen cause (D) — informational

* Day-6 bayou: no mask / wrong answer → `killGabe` (R1 is the cross-day version).
* Day-5 museum snake (`rm260.sc:156-160`, `:1496-1499`): pure reaction test, no earlier cause.
* Day-9 mummies, wolf keyhole (`rm710.sc:750-795`), Dr John's key window (`sHRoom2.sc:551-556`,
  repeatable via `Hounfour.sc:429-431`), three wrong drum phrases (`sCeremonialRoom.sc:381-390`).

## 1.5 The tool's verdict (first legible surface, 2026-08-27, `snapshot.py gk1`)

| tool row | reading | verdict |
|---|---|---|
| `dangerous_sinks sLakePatter@rm410 -> 1 room` (+ `market_specs`, edge specs `rm200/rm50->rm290: (has: 31)`) | giving the lake pattern to the artist (`neJackson.sc:1355`) strands its use at Magentia's (rm290, verb 23) | **FP** — the give IS the day-2 gate (flag 231); no `has: 31` exists; the Magentia site is flavour |
| `register_strandings reconVeve@reg123=10 / reg475=1 -> [200, 205, 340]` (+ `rm200/rm205->rm372: (has: 38)` specs) | the day counter reaching 10 strands reconVeve for the map's day-3 gate and Hartridge | **FP** — never consumed (no `put: 38`); every demand is day-3/4 gated and dead after the flip. Detector defect: a flip that also kills the DEMAND is not a stranding |
| `fatal_uses knife@rm899/sDaggerOnMalia` (+ action spec, placement) | stabbing Malia during the throw-the-talisman window is death | **FP — USER RULING 2026-08-27**: KQ6's skull counted because throwing it *wastes it for later*; the knife is not consumed, the stab is a death you restore from, preventable on its own screen |
| R1 VoodooCode1 | — | **MISSED** (red) — the day counter is a `++` register with range guards; no literal flip to key on |
| R2 rod + signal device deposit, R3 guises | — | **MISSED** (reds) — the hounfour's scenes are `Script`s inside room 800; Grace's room is an intra-room switch |
| R4 flag 44 | — | **MISSED** (red) — Teller/Interrogation topic dispatch unmodelled |

Coverage: **0 of 4 real rows caught; 3 FP rows (knife ruled out by the USER).**

## 2. What the model needs that GK1 introduces (SCI32 shapes) — see the commit log on `gk1`

1. A room declared as a **Room subclass with nothing beneath it** (`class Hounfour of Room`, 800).
2. A death dialog that spells Restart as a `newRoom:` into the restart room and offers **Quit**
   (`(= global4 1)`) beside `restore:`; a death SCREEN whose room `init` arms the dialog script.
3. `newRoom: register` — the destination rides `setScript:`'s third argument through a method
   parameter (the maps, `rm200`/`rm205`).
4. A global assigned from a **script-patch existence test** (`global110` ← `(FileIO 10 "99.scr")`)
   gating the debug handler — environment, pinned like a debug toggle. The SAME idiom turned out to
   be live in LB2 (`Main.sc:987`, `10.scr` → `global110`, gating `Main.sc:1234`), whose debug path
   had never been pinned: LB2's watched surface gains `debug_globals: [110]` and nothing else moves.
   KQ6's `(FileIO 10 <Format'd resource name>)` → `global100` is a CD/floppy test and is NOT pinned
   (measured: pinning it moved the gated KQ6 surface).
5. The death screen is not an engine entry; the intro's pass-through CHAIN is discounted like its root.
6. Still OPEN: flags set through the `getPoints:` METHOD wrapper (4 flags have no other writer:
   159 169 176 393); the SECOND flag array (`global182`, `proc50_5..8`) — topic-said bits that gate
   Teller topics; Teller `79+iconValue` arithmetic flags; the Hounfour's twelve scenes are
   `Script`s inside ONE room (800), so R2/R3's point of no return is intra-room.

## 3. Provenance

Day-range derivations by five parallel read-only agents over the scripts (2026-08-27), each
claim re-grepped here before entering §1; walkthrough leads from walkthroughking.com,
adventuregamers.com (Tom Hayes' guide, facts only), gameboomers.com, the Steam point-list thread and
the GK Omnipedia "Dead end" page.
