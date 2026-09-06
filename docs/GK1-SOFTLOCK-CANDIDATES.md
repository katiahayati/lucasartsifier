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

### 1.6 Round 2 — the day counter as a point of no return (2026-08-27, later)

Three general fixes in `missability.py`, measured LSL2/KQ4/KQ6/KQ5 byte-identical, LB2 moved
(mechanism pins only — see §1.7):
1. `_flip_seeds` reads `_rstep` — an ordered step `frm -> w` (what a fanned `(++ G)` becomes) IS
   a write into `w`. The day-5 flip at rm370 now seeds (it never had).
2. `_source_live` hands `structural_reqs` the projection's domain, so `(< global123 5)` on a
   pickup site answers (it constrained nothing without one).
3. flat-extractor pickups carry the emitting object's presence (`cast_guard`), as the handler
   walk already did — `message1`'s `get: 32` now knows `123<5`.

Result on R1: VoodooCode1 IS named by `register_strandings` — but on synthetic flag 247 ("wrong
message written"), not on the day counter, so the pinned check stays RED. The day-5 flip still
finds one live source: `theInView` inside the inset (`rm300.sc:1368`), whose `(== view 3022)`
is object-property state set from the inset machine's `register` — the census's gap #3. Two new
rows are FPs of one shape, "the flip's own precondition demands the item": `sVoodooCode@flag247`
(writing on the tomb needs both sketches) and `reconVeve@reg123=4` (day 3 cannot end without
it — `theMapPrint.sc:251` — but that gate writes flag 15 from `IconMap::endDay`, a METHOD called
by send from rm200/rm205, which the walkers do not follow, so flag 15 has no visible writer,
is not a gating register, and the day advance costs nothing in the model). The general cure is
following sends to game-defined methods the way procedure calls are inlined; not built.

**Correction after measuring (same day):** flag 15 IS a gating register (synthetic 257 — the
death flag takes 241, flags start at 242) with writers at rm200/rm205/rm210 (the map scripts are
ScriptID-scoped into their rooms, so `endDay` is walked). The real cause is the COST model:
`_inroom_own[(15, room, 1)]` is the INTERSECTION of the own-costs of every branch that writes it
in that room, and `endDay`'s day-2 branch costs no item — so the day-3 branch's `has: 38` and
the day-4 branch's `has: 26/41` are intersected away and every day advance is free. The day
counter's projection (register 123) cannot see that its own flip at rm370 needs flag 15; only a
JOINT projection of the counter with the flags that gate its advance would — the LB2 pressPass
shape exactly ([[lb2-pending-ruling-presspass-relocation]]). Counting conditional `init` writes
in `gating_registers` was measured inert and kept for the principle.

### 1.7 What moved on an existing game (row-accounted)

* **LB2** (watched tier, declared red, awaiting the USER): the pressPass relocation (14 rows,
  from the qfg1 cherry-pick) + `debug_globals: [110]` + **the counter fixes**: `bifocals`,
  `daggerOfRa`, `redHair`, `wireCutters` each gain a `register_strandings reg123=5 -> [750]`
  row (the act-5 flip strands the finale's carry-ins — a second mechanism for four items the
  oracle already had in column A; no verdict moved), `pressPass` reg123=1/4/5 rows in place of
  =2, and the write specs those imply. 21 rows in all.
* LSL2, KQ4, KQ6, KQ5: byte-identical throughout.

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

### 1.8 Round 3 (2026-08-28, autonomous) — the day system prevents SOME strandings, sneakily not all

The USER's framing for this round. `endDay`'s per-day arms (§0) are what prevents a stranding:
day 3 cannot end without reconVeve + wolfPhone, day 4 not without tatooTrace + braceRep; day 5's
arm asks for neither sketch, so the first tomb sketch (R1) is what the day system does NOT protect.
The model had to learn to tell those apart. Every step measured on the six snapshots (baselines
from a detached worktree at 7642461); goldens byte-identical unless stated.

1. **A fanned counter drops its contradictory branches** (`compile._fan_globals`, same test as
   `_fan_exit`). `graceComeOut` state 101 does `(++ global123)` then `(switch global123 …)`, and the
   post-increment switch arm conjoined onto the pre-increment fan made every branch contradictory;
   `structural_reqs` read the empty intersection as "unconstrained", the write landed free, and the
   counter-monotonicity rule turned it into `(u, v)` for every `u ≤ v` — the day could jump 1→8 in
   rm370. Now `_rstep[123][370]` is exactly the seven consecutive steps.
2. **A self-redirect is not a way in** (`machine._floor_self_redirects`): `(self changeState: 99)` in
   the machine's OWN handleEvent inherits the arming disjunction (third spelling of the arming floor;
   `_drop_continuation_entries` is the second). graceComeOut's state-101 day advance now needs flag 15.
3. **A flip the item-less player cannot make strands nothing** (`register_strandings._flip_live`):
   the flip state must be live under the ban in every projection tracking the register. Sound for
   this detector's claim; losing the item AFTER the flip is a sink, the sink detectors' business.
4. **The joint projection of a counter with the flag gating its advance** (`_gate_joints`,
   `_wbranch`, `_psucc_joint`): per-branch write records (deps, cost, same-state co-writes, read
   with the registers' domains), a joint built only for a register that COUNTS whose ordered step is
   armed under B while B's write is conditioned on the counter (3-cycles through the counter too),
   and exact joint successors (branch deps enforced, co-writes atomic — rm370 clears 15 and
   advances the day in one state). ⛔ Measured without the "counts" qualifier: LSL2 grew flag-pair
   joints and the Vine surfaced (19 golden lines), KQ6 grew `(165,166)`; with it, both identical.
   GK1 joints: `(123,257)`, `(123,257,263)`, `(123,257,507)`.
5. **A crossing is a register writer** (`_reg_cost` indexes `_emeta` sets): `prevRoom == 302` cost
   nothing, so the banned walk took the interrogation screen's return edge `50→302` into the tomb-
   writing room without the priced crossing `300→302`.
6. **A flip-killed demand is not a demand** (`register_strandings` reads needs per site via
   `_need_live`): reconVeve's `still_needed_at` loses `endDay`'s day-3 arm (rm200/205) after day 4.
7. **A conversation topic is a guarded handler** (`vocab.lower_teller_cases`, SCI32 `Teller`):
   `showCases` pairs and the `addGlobals` band (topics 1–15 iff flag 36+n) become path conditions on
   the `(switch iconValue (K …))` arms — 278 arms in 24 tellers. Keyed on the property the root
   `showCases` RETURNS (`iconValue`, derived). Inert on SCI0/SCI1.1 by construction.
8. **A negated flag test lowers as `Not`** (`derive_flags` op `ntest`): `proc50_1` is
   `(not (& word bit))`; as `test` it inverted every "not yet said" topic condition.
9. **The object-local property store** (`vocab.derive_obj_locals`/`lower_obj_locals`, the EIGHTH
   store; LAST allocating, so earlier stores' numbering is untouched): a room script's own instance's
   property written with a constant and read back, reset to its declared value on reload through the
   room-local channel. GK1: 14 registers (theInView.view among them); KQ4 2, KQ6 3, KQ5 29, LB2 4,
   LSL2 0. With it: `switch register` arms are VALUED (`ir.control_shape`), a `register`-valued write
   `(theInView view: register)` is SYMBOLIC and resolved by `compile._fan_globals` / the walk's
   counters (dropped when unpinned), and `_source_live` asks `_locals_reachable`: a room-local
   register the site guard pins must be producible in THIS visit by a write branch whose deps the
   projection state satisfies.
10. ⛔ **Reverted**: promoting (to a fixpoint) every register compared in the guard of a promoted
    register's write moved LSL2 by 196 lines. Flag 65 (Grace's "go home" token) therefore stays
    unpromoted.

**What moved on existing games (row-accounted):** LSL2, KQ4, KQ6, KQ5 byte-identical at every kept
step. **LB2 (watched, declared red): 15 lines** — `grapes@reg123=5` loses need-room 520 (the act-4
exit interceptor is dead at act 5); pressPass loses `reg(12,123)=(110,2)`, `(330,3)`, `reg123=4`,
`reg123=5` and the two guard specs those implied (`reg123=4: (has: 6)`, has:6 in the reg123=5
spec) — the rm335 need site is `global123==2` (dead at 3–5), and the (110,2) seed's pass-less walk
reaches rm335 only at act 3. `pressPass@reg(12,123)=(26,2)` and `reg123=1` remain, so the item is
still CAUGHT. This is the retirement [[lb2-pass-necessary-for-act1]] said would come "when the
measurement lands"; the re-pin is the USER's.

**GK1 after the round:** reconVeve still flagged at the day-4 flip — the surviving leak is Grace's
"go home" topic 49 (`(proc50_3 15)` under flag 65): flag 65 is re-raised by rm470's four cutscenes,
whose once-only gate (flag 11, set alongside 65) does not reach their write branches, so in the model
Grace can end day 3. `still_needed_at` now `[50, 340]` (rm50 = Grace's topic 50 `(has: 38)`).
VoodooCode1/sVoodooCode at flag 246 REMAIN: step 5 does not reach them -- `prev == 302` is produced by LEAVING 302 (free); what the return edge `50->302` really presupposes is having ENTERED 302 (priced at both sketches), a two-step fact the register-cost index cannot express. Open: a return-to-sender edge should carry its origin room's entry cost. **R1 CAUGHT** — `VoodooCode1@reg123=5 -> [240, 260, 300]` (and the joint rows), once the inset's If-valued arming `(if (proc13_0 394) 3025 else 3024)` was split into two armings (a register-less arming was consistent with every `switch register` arm and diluted the 3022 arm's day<5 inheritance) and machine states' `get:`s joined the co-grant table (the gift certificate's `(get: 5 getPoints: 122 1)` had surfaced as a new row). R2/R3/R4 unchanged (scenes; the
flag-stranding detector R4 needs is not built — the Teller lowering now makes Crash's topic 8 a
`flag 44` site, so the writer/use chain is visible).

**Round-3 closing measurements (2026-08-28, later).** Two cuts to the eighth store, both derived,
no catalogue: (a) a property the class library writes through its `client` (`cel`, `loop`, `x`,
`y`, `heading`… — `vocab._client_written_selectors`) is NOT the script's store on an object the
script hands to the engine (`setCycle:`/`setMotion:`/`setScaler:`/`setLooper:`); (b) a property an
ANCESTOR class assigns on `self` (`register`, `seconds`, `cycles` — `_library_self_written`) is the
library's. Without (a) KQ5 lowered 29 animation registers and `register_strandings` went from 20.8 s
to 1249 s (profiled, 3 rows either way); without (b) `register` itself would have been lowered and
the carried-local reading broken. Census after both: GK1 3 (theInView.view, credit.view,
drJohn.noun), KQ4 0, KQ6 13, KQ5 5, LB2 1, LSL2 0. Gate joints: a triple only where no pair closes
the cycle (KQ5's flag 331 now counts and had filled the 8-joint cap with permutations). Final
surfaces (s10 + the KQ5 re-time): LSL2/KQ4/KQ6/KQ5 byte-identical, LB2 15 lines, GK1 38 lines.
⚠️ PERF DEBT: KQ5's snapshot is 634 s (baseline 244 s) — its new counter's projection and the
`_flip_at` walks (`scratchpad/prof_kq5b.log` vs `prof_kq5_base.log`); GK1 269 s.

## §1.9 Round 4 (2026-08-28, later still): R4's chain, three model fixes, one detector REVERTED

R4 stays a **declared RED** — not caught. What this round bought is the chain, script-verified end
to end, and three model fixes that make it expressible; the detector attempt built on top of them
was measured, found to be an FP factory, and reverted. Reported the way it happened, not the way it
was hoped.

### R4's chain, as the model now sees it
`tatooTrace` (item 26) is required at rm200/205/210 and its only source is rm450, handed over by
`sTraceTattoo`. Reading down:

1. `sTraceTattoo` is armed from `myShirt::doVerb` and `chest::doVerb` (`rm450.sc:1147,1264`), both
   objects `init:`ed by `deadCrash::init` — an `Inset` armed by `sDoInset` under flag 74
   (`rm450.sc:674`).
2. Flag 74's only writer is Crash's Teller arm 42 (`crash.sc:81-84`), which is not a topic anyone
   can pick: arm 8 selects it (`(= iconValue (cond ((proc50_5 280) 42) ...))`, `crash.sc:68-80`).
3. Arm 8 is offered by flag 44 or flag 47 (the global band, `GKTeller.sc:80-83`). Flag 44's only
   setter is a Teller topic in `hartridge.sc:257`; flag 47's is day 5's opening — behind the very
   gate the trace unlocks.
4. Which character's Teller runs on the interrogation screen (rm50) is `global178`
   (`interrogation.sc:192-238`: `(switch global178 (12 ((ScriptID 1055 1) init:)) ...)`), and
   `global178 := 12` is written only in rm280 — Cazaunoux's house, reached only through rm270,
   whose `knockOnDoor` cutscene branches on `(>= global123 4)` and never reaches its
   `newRoom: 280` states on day 4+ (`rm270.sc:199-262`).

Every link of that is now in the model **except the last**: the edge `270->280` still carries only
`req={808: [1]}` (`local4`, the state's own guard) and no day requirement, so rm280 — and with it
flag 44 — reads as reachable on day 4. Measured, not assumed: with the day counter joined to the
subject register, `(rm50, (day 4, subject 12))` is still a reachable product state.

### Why the edge misses the day, isolated to one line
`state_musts` is the right machinery and `edge_meta` already applies it to machine EXITs
(`sm.at(K, g)`), so the gap was inside the walk. Two causes, one fixed:

* **FIXED — the walk read guards with no domain.** `guard_reqs` turns `(>= G 4)` into a value set
  only when told the register's domain; without one a relational path condition constrains nothing
  (its documented rule). So every `if <counter is past K>` inside every machine in the corpus was
  invisible to this walk. `state_musts` now takes `dom`, passed by `edge_meta` alone (the movement
  reading; the domain-less branch-table callers pass nothing, the `_wbranch`/`_wbranch_dom`
  discipline). Measured on `knockOnDoor`: state 7's musts go `{}` -> `123 in {0,1,2,3}`.
* **OPEN — the walk stops at a PARK.** State 7 waits (`setCycle: End self`), and states 8-11 past
  it come back `{}` with the constraint gone. It is not a rogue entry: `knockOnDoor` has exactly
  one entry, `(0, opaque())`. A PARK is "wait for a cue", and the cue advances carrying everything
  the path established — so a walk that ends at one loses every fact established before a wait,
  which in a Sierra cutscene is most of them. `compile.carry_cues` converts PARK -> ADVANCE at
  build time and did not convert this one. **This is the next thing to look at, and it is general,
  not GK1's.**

### The three model fixes that stand (all derived, all measured)
1. `extract.cast_conditions` — **what an object inits is present only when the object is.** An
   `init:` sent from inside another object's method runs only when that object does; read from an
   empty path condition its inits were unconditional, so the presence the function derived stopped
   at the parent. Iterated to a bounded fixpoint, the same casts/entries recursion
   `MachineBuilder.prime` already iterates; round 0 reproduces the old answer exactly and a round
   can only narrow. GK1: `deadCrash`'s cast condition now carries flag 74, and `sTraceTattoo`'s
   entry guard inherits it.
2. `vocab.lower_teller_cases._lower_followup_arms` — **a follow-up arm runs only after the arm that
   selected it.** A Teller re-dispatches after each message and an arm assigns the next
   `iconValue`; an arm the menu never offers inherits the disjunction of the path conditions under
   which other arms assign its value, processed in dependency order to a fixpoint. Permissive
   wherever it cannot read (an unreadable assignment is a source of every unoffered arm; an
   unconditional source leaves the arm free; a cycle stays unconditional; an object whose icon
   property is assigned from another script is skipped). GK1: 278 -> 308 arms lowered, and arm 42's
   flag-74 write is now conditioned on flag 44 or flag 47. Inert on the SCI0/SCI1.1 corpus by
   construction (no `showCases` protocol).
3. `state_musts(dom)` above.

### REVERTED, with the measurement that killed it
A `register_value_strandings` **carry-up**: when the sealed region does write the demanded
register, ask (per write branch, disjunction-split, at the flipped value) whether every live write
is itself blocked by a register the seal froze, and report that register instead. Supporting parts:
`chain_registers` (registers one hop up a write chain, recorded in the branch tables without being
promoted — promotion itself was re-measured and re-rejected: +7 registers, **196 LSL2 golden lines**,
and `softlock_items` LOST the Swimsuit, Sunscreen, Wig, Bikini_Top, Knife, Bobby_Pin and Pamphlet,
oracle rows all), `_split_or`, and a third `_wbranch_or` table.

**Measured on GK1: 23 rows, every one a carry, and R4 not among them.** The rows rest on the weak
half of the test — a register with no projection is judged "carried across wrong" from
`reach_avoiding(writer_rooms)` alone, i.e. "the player could reach the flip without entering a room
that writes it", which is almost always true for a flag with one writer. Reverted whole rather than
filtered: an allow-list over 23 rows would be a clause protecting a known answer, and the FP shape
is the design, not an accident. The reverted code is NOT in git (it was reverted before the commit); the only copy is
`/tmp/claude-1001/-home-hayati-coding-sierra-softlock/f07bccf3-faa5-4127-a635-bc03a3216c6e/scratchpad/missability_carryup.py.bak`,
which lives in an EPHEMERAL session scratchpad. It is kept for archaeology only — the description
above is the thing to rebuild from, and the conclusion is that it should not be rebuilt as-is.

### Surfaces (s11 vs the s10 baseline, all six games)
**LSL2, KQ4, KQ6, KQ5 and LB2 byte-identical.** GK1 moved 13 lines, all joint-row churn on rows
already reported: four `VoodooCode1@reg(123,257,263|507)` triple-joint rows and four `reconVeve`
triples retire, `reconVeve@reg(123,257)=(7,0)` becomes `(0,0)`. **`softlock_items` is unchanged**
(`sLakePatter, VoodooCode1, sVoodooCode, reconVeve, knife`) and **R1 is still caught** —
`VoodooCode1@reg123=5 -> [240, 260, 300]`, the oracle-pinned row. No coverage change anywhere.
Times: LSL2 37s, KQ4 81s, KQ6 102s, KQ5 612s, LB2 53s, GK1 241s (KQ5 634s -> 612s, GK1 269s -> 241s).

## §1.10 Round 5 (2026-08-28b): the PARK cure — a wait is not an ending

Round 4 left one isolated blocker under R4: `state_musts` stopped at every PARK, so nothing a
Sierra cutscene establishes before its first wait reached the states after it. This round closes
that. **All six surfaces are byte-identical**, which is the honest headline: the model now knows
things it did not, and no detector reads them yet — the remaining GK1 blocker is named in §1.10.3.

### 1.10.1 A PARK was two different things spelled one way
A state that arms no cue we can count compiles to `PARK`. That covers two situations the model
could not tell apart:

* **a WAIT** — the state handed off to something that will cue it back. GK1 `knockOnDoor` state 7
  is `(madamTeller doVerb: 11)`, a conversation; when it ends, the cue lands on state 8 exactly as
  an `ADVANCE` would.
* **an ENDING** — the Script is gone and no cue can reach it.

The musts walk needs them apart, and the split is derivable, because an object holds exactly ONE
Script at a time (`extract.script_slot`, now the single spelling of that key, shared with
`machine._arm_events` where it already lived). A Script stops running when its own slot is emptied
or handed on — three spellings, one fact (`compile._ends_script`):

| spelling | sites: GK1 / KQ6 / LB2 / KQ5 / KQ4 / LSL2 |
|---|---|
| `(self dispose:)` | 567 / 624 / 439 / 129 / 11 / 13 |
| `(client setScript: …)` — `client` IS the holder | 0 / 0 / 0 / 227 / 25 / 5 |
| `(<host> setScript: …)` — the same slot, named; `host` ∈ this machine's `entry_recv` | — |

`_interp` now emits `("END",)` where the step would otherwise PARK (a path that ALSO arms a cue
keeps its `ADVANCE`: dropping a fall-through is the tight direction and that case is unmeasured),
`carry_cues` will not flip an END back to `ADVANCE` (a carried cue fires into a disposed script and
is lost) and `missability._after` reads an END exactly as it reads a PARK (control returns to the
player, in this room). `state_musts` crosses a PARK and stops at an END.

### 1.10.2 Both halves or neither — measured twice, and the second one was a golden regression
* **GK1 `knockOnDoor`** (`rm270.sc:199-262`), three readings of the same machine: stopping at every
  PARK leaves states 8-13 with `{}`; crossing every PARK is **worse than stopping**, because state
  5's `(>= global123 4)` branch ends with `(self dispose:)` and its `123 in {4..10}` then merged
  into the day<4 spine and dissolved even the constraint state 7 already had; crossing a PARK and
  stopping at an END carries `123 in {0,1,2,3}` to both `newRoom: 280` exits.
* **KQ6 `minotaurCharging`** — the third spelling is not completeness, it is the fight. With only
  `dispose`/`client` reading, state 8's no-scarf arm `(global2 setScript: hornSwaggled 0 register)`
  PARKed, the walk crossed it into state 9, and register 443 (the scarf on the minotaur) merged to
  `{0,1}` at state 13. Measured on the full surface: **the red scarf LEFT `softlock_items`**,
  rm340's three exit guards lost `has: 41`, and two rm340 placements went. rm440 arms
  `minotaurCharging` into `global2` (`minoTrigger.sc:81`), so the gored branch hands the room away
  and never reaches state 9 — reading `entry_recv` as the host restores KQ6 byte-for-byte.

A third correctness point, and it cost a whole rebuild to find: **`_records` is `_interp`'s twin**.
A node `_records` does not keep is collapsed by `_paths_of` before the interpreter can see it, so
teaching `_interp` to read `(self dispose:)` changed nothing at all until `_records` agreed.
`test_discrimination` now pins that both halves consult `_ends_script`, and its LSL2/KQ4
differential passes each machine's `entry_recv` so the reading is actually exercised.

### 1.10.3 ⭐ THE NEXT THING — the machine's gate is bypassed by its own flat edge
The day requirement now rides GK1's `270->280` machine rows:

```
req={808: [1]}                        <- flat cs_edge, via knockOnDoor   FREE
req={808: [1]}                        <- flat cs_edge, via knockOnDoor   FREE
req={808: [1], 123: [0, 1, 2, 3]}     <- machine EXIT, state 9
req={808: [],  123: [0, 1, 2, 3]}     <- machine EXIT, state 11 (contradictory: local4 is false
                                         on every path that reaches 11, so that exit is dead)
```

`_emeta` rows are alternatives, so the two free rows keep the house open on day 4 and **nothing
moved**. They are not suppressed because `machine_delivered` says knockOnDoor does not deliver 280
— and `machine_delivered` comes from `compile_machine`'s walk, **which has the same PARK-stop
defect this round fixed in the musts walk**. So the model publishes an exit from a state it
simultaneously declares unreachable, and `edge_meta`'s own comment names the consequence
("keeping both as separate rows makes the flat one a free bypass of the gate").

Census of that gap, one row per machine that publishes an exit its own walk cannot reach:
LSL2 **1** (rm47 `henchScript` -> 96), KQ4 **4**, KQ6 **9 pairs / 11 machines**, GK1 **18 pairs, 12
of them published as a free flat row**. Crossing a PARK in `compile_machine`'s walk is the same
one-line change with the same END guard — but it changes edge GUARDS on four golden titles, so it
is measured on its own and parked if any golden moves.

### 1.10.4 The delivery half — and the two links R4 has left
Two more one-line readings, both the SAME defect as 1.10.1 in the OTHER walk, the one whose exits
become `machine_delivered`:

1. **`compile_machine`'s walk crosses a PARK too** (and stops at an END). Without it the model
   published an exit from a state it simultaneously declared unreachable, and `edge_meta` left the
   flat cs_edge carrying the same `newRoom` statement standing as a free alternative.
2. **A wait costs that walk its LOCALS.** The seed (`local_regs`, "the script reloads on room
   entry, so a local starts at its declared reset") is a fact about ROOM ENTRY, and a PARK hands
   control back to the room whose handlers own the same storage. GK1 rm270 is the case and it is
   not a corner: state 7 waits on `(madamTeller doVerb: 11)`, the Teller's own `cue` does
   `(= local4 1)` (`rm270.sc:544,554`), and states 8-11 branch on local4 — so carrying the seed
   across the wait made `local4 != 0` decidably false and `_lreg_test` pruned BOTH `newRoom: 280`
   paths. The register the ARMING selected is kept: it is a property of this Script, which no
   handler in the room can reach.

Result — `270->280` is now gated, the free rows are gone:
```
req={808: [1], 123: [0, 1, 2, 3]}     machine EXIT, state 9
req={808: [],  123: [0, 1, 2, 3]}     machine EXIT, state 11 (dead: local4 is false on every
                                      path that reaches 11, so that exit contradicts itself)
```

**Surfaces: LSL2, KQ4, KQ6, KQ5 and GK1 byte-identical; LB2 moves 2 rows** — `bifocals` and
`redHair`'s act-5 joint rows change prev-room from rm454 to rm480. LB2 gains **20**
`machine_delivered` pairs (rm455->454 among them, plus `18->{230,355,420}` and eleven `*->26`), so
arriving at 454 is a gated machine edge now instead of a free flat one. Same items, same mechanism,
same need room [750]; only the prevRoom in the joint moved. Declared in KNOWN_RED (21 -> 25 rows).

#### R4 is still a declared RED, and its remaining links are now NAMED
The day gate holds and rm280 is sealed at day 4 **as far as `270->280` goes**. Measured, two links
remain, and neither is new — both are open items this project already carries:

* **The return edge `50->280` is unpriced.** `_emeta[(50,280)]` is `{12: [280], 178: [...]}` — a
  `newRoom: <prevRoom>` return. Any projection that does not track prevRoom crosses it freely, so
  the day-4 player "returns" to rm280 without ever having been there. **This is the same gap that
  keeps `sVoodooCode` an FP** (the `50->302` return edge, §1.8): *a return-to-sender edge should
  carry its origin room's entry cost*. One fix, an FP killed and a red unblocked.
  Simulated in the product (entry cost conjoined onto the return row): rm280 does close, and
  `braceMold@reg123=4 -> [460]` (source rm280) appears — three new rows, plausibly the same
  day-cannot-end-without-it FP class as `reconVeve`'s, so the fix needs the `_flip_live` reading
  measured with it, not after.
* **The acquisition's own register demand is never asked in the post-flip world.**
  `tatooTrace`'s source is rm450 and rm450 stays reachable; what dies is the ACQUISITION, armed
  under flag 74. `register_strandings._live_srcs` already refuses a source whose guard is dead
  **at the walked value of R** (`_source_live`), but flag 74 is a different register, so in the
  R=123 projection it is simply unconstrained. `register_value_strandings` is the detector shaped
  for this and returns nothing, because its conjunct 3 ("no write past the flip puts S into the
  accepted set") sees flag 74's write site at rm50 as reachable — the write is gated by flag 44,
  one hop further up. That hop is exactly the reverted carry-up (1.9), and the conclusion there
  stands: not as-is. What is new is that the hop is now the ONLY modelling question left in the
  chain, and the joint machinery (`_gate_joints`) is the shape that can answer it — but R4's
  dependency is a CHAIN (123 -> rm280 -> 178 -> flag 44 -> flag 74), not the mutual cycle
  `_gate_joints` selects on.

## §1.11 The reconVeve FALSE POSITIVE, diagnosed to the line (2026-08-28c)

`reconVeve@reg123=4 -> [50, 340]` is a declared FP: the day-4 flip cannot strand reconVeve because
**day 3 does not end without it**. Nailed down, no code changed.

### The game
`theMapPrint::endDay` (`theMapPrint.sc:230-275`) switches on the day and each arm demands that
day's evidence:
```
(3 (if (and (proc13_0 265) (proc13_0 21) (proc13_0 256)
            (global0 has: 38)      ; reconVeve
            (global0 has: 8))  (proc13_1 15) (return 1)))
(4 (if (and (proc13_0 447) (proc13_0 248) (proc13_0 36) (proc13_0 227)
            (global0 has: 26)      ; tatooTrace -- R4's item
            (global0 has: 41)) (proc13_1 15) (return 1)))
```
`bookstore.sc:211-243` re-checks the same conditions on entry from rm50 for days 2, 4 and 5 —
**not day 3**. So day 3's only exit is the arm that demands reconVeve.

### What the model has, and where it loses it
The three `endDay` sites are priced correctly — `_wbranch[(flag15, rm200|205|210, 1)]` carries
`{123:[3], …} cost=[8, 38]` and `{123:[4], …} cost=[26, 41]`. But there is a **fourth** writer:

```
rm50 -> flag15 := 1 :  deps={178: [2]}  cost=[]        <- FREE, no day, no items
```

That is Grace's Teller topic 49, "go home" (`grace.sc:141-146`):
`(49 (proc50_3 15) (proc50_4 65) (global0 getPoints: 130 2 1) (self doVerb:))`, offered under
`(proc50_2 65)` (`grace.sc:49-50`). ⚠️ `proc50_1..4` and `proc13_0..2` are the SAME bit array —
both index `global127` (`interrogation.sc:31-49` vs `n013.sc:17-35`) — so topic 49 really does
raise the day-end flag. Only `proc50_5..8` are the separate topic-said array (`global182`).

**The model HAS the offering condition and throws it away.** `em.handler_writes` for that site is
```
GAnd([GAnd([178==2, 11==50]), 307!=0])          ; 307 = flag 65
```
`lower_teller_cases` lowered it correctly. It is `_wbranch`'s `deps` that keeps only PROMOTED
registers, and **flag 65 is not promoted**: `gating_registers` requires "compared in a MOVEMENT
guard AND written", and flag 65 is compared only in a `showCases` offering condition. Measured:
`flag65 (reg 307) promoted=False`, and no movement guard anywhere compares it.

### The fix is a promotion, and its size is measured
Blanket write-chain promotion is closed — twice measured, 196 LSL2 golden lines and 7 lost oracle
items (`gating_registers`' own comment). But the NARROW rule is a different animal:

> promote R iff R is compared in the guard of a write to a promoted S, **where S gates an ORDERED
> STEP of a COUNTER** — the `_gate_joints` structure, which already earns its keep on the ground
> that "the flag gating its ADVANCE is a claim about a point of no return".

Sized against the real post-promotion tables (`_counters`, `_rstep`, `_wbranch`):

| | LSL2 | KQ4 | KQ6 | KQ5 | LB2 | GK1 |
|---|---|---|---|---|---|---|
| new registers | **0** | **0** | **0** | +2 | **0** | +5 |

GK1's five are `[11, 18, 307, 314, 689]` — **307 is flag 65**. Inert on three goldens and on LB2;
the whole risk is KQ5's +2.

### ⛔ AND IT NEEDS A SECOND PASS — five promotion-time approximations all failed
`gating_registers` runs BEFORE `_rstep`/`_wbranch`/`_counters` exist, and the rule needs the
counter test. Every attempt to approximate that test from raw writes missed in one direction or
the other, measured:
* counter = "3+ distinct written values" → 6-14 counters/game, and GK1's flag 65 not reached at all;
* + entry guards folded in → LSL2 **+6**, KQ4 +4 (near the +7 that cost 196 lines);
* counter = "has 2+ (v-1 -> v) steps" → GK1 correct (+5 incl. 307) but LSL2 **+8**;
* + the real `all(t == f+1)` test, disqualifying unconditional writes → GK1's counter VANISHES;
* + treating unconditional writes as `_inroom` (the real semantics) → GK1's counter still missing.

The honest reading: the monotonicity test genuinely needs the built step tables, so this wants a
**second pass** — promote, build the tables, apply the narrow rule with the real `_counters`,
rebuild — not a cleverer early approximation. Given that promotion has broken the goldens twice,
that pass deserves its own measured round.

## §1.12 A conversation topic is a MOVE (2026-08-29, the USER's reframe)

> *"this is an sci2 new idiom, the conversation tree. we're trying to shoehorn it into the
> previous worldview, which is too narrow. either we need to widen the worldview, or it would be
> ok to have SCI2 handling that understands conversation trees and corresponding registers."*

That is the right diagnosis of §1.11. `gating_registers` promotes a register iff a MOVEMENT guard
compares it — rooms, doors, machine exits — which is SCI0/SCI1's complete answer to how a game
advances. SCI32 put a **second graph beside the room graph**, and GK1 runs much of its plot on it.
Asking Grace to go home ends the day exactly as walking out of a room would; the flag that puts
that topic on the menu gates progress as surely as a lock gates a corridor. Reading only the room
graph is not a conservative simplification here — it is the wrong worldview.

So: **a topic offering IS a movement guard.** `vocab.topic_gate_tests` yields the condition of
every lowered topic (the `If` wrappers `lower_teller_cases` builds are tagged where they are
built), and `_movement_guards` yields them beside edges, exits and entries.

GK1: **214 → 249 promoted registers.** Flag 65 lands (Grace's "go home") and so does **flag 44**
(Crash's "Voodoo Hounfour" — R4's blocked link). The day-end write at rm50 goes
`deps={178:[2]} cost=[]` → `deps={178:[2], 307:[1]}`.

**Surfaces: LSL2, KQ4, KQ6, KQ5, GK1 byte-identical; LB2 unchanged from its already-declared 4
rows. Suite 878/13/0/0.** Inert on SCI0/SCI1.1 **by construction** — no `showCases` protocol means
no tagged node — which is the property §1.11's candidate rule was straining to buy by measurement.

### ⛔ What was rejected on the way, and why it mattered
§1.11's narrow promotion (one hop up the write chain, but only off the gate of a counter's ordered
step) measured well — 0 new registers on LSL2/KQ4/KQ6/LB2, +2 KQ5, +5 GK1 including flag 65. It was
still **a clause protecting a known answer**: nothing about "a counter's gate" explains why a
conversation flag matters, and it only ever pointed at flag 65 because that is where I started
from. It also needed a second build pass (the counter test wants tables that exist only after
promotion; five promotion-time approximations were measured and every one missed, LSL2 +6/+8 too
loose or GK1's counter vanishing entirely). The right rule is shorter, needs no second pass, and
says something true about the game.

### ⭐ NEXT — and the next question is about the GAME, not the model
`reconVeve@reg123=4` does **not** retire yet. The day-end branch now demands flag 65, but flag 65's
own writers are still free: `_wbranch[(flag65, rm470, 1)]` has **14 branches**, one carrying
`{253: [0]}` (flag 11, the once-only gate) and thirteen with **empty deps**. Every one is inside
`afterTheCloseUp` (`rm470.sc:329-557`), armed under `(== global12 471)` — returning from the
magnifying-glass close-up — and gated internally by locals (`local5`) and by which sub-scene ran.
rm470's first-visit cutscene is a different script (472, armed under `(not (proc13_0 11))`).

So the open question is not "how do we model the gate" but **"is flag 65 genuinely once-only?"** —
i.e. can the player re-enter rm471, come back, and be offered "go home" again on a later day? If
yes, `reconVeve`'s row may not be a false positive at all and the declared red is wrong in its
VERDICT, not just its cure ([[re-derive-a-reds-premise]]). That wants a play-check or a ruling
before any more model work.

## §1.13 reconVeve IS a false positive — proved from the scripts (2026-08-30)

§1.12 left the question "is flag 65 once-only?" as something that might need a play-check. It does
not. The scripts settle it, exhaustively.

**Every setter of flag 15 (the day-end flag) in the whole game — 8 sites:**
| site | when |
|---|---|
| `theMapPrint.sc:241,254,268,274` | `endDay`'s arms: days **2, 3, 4, 5** |
| `bookstore.sc:218,231,242` | re-check on entry from rm50: days **5, 4, 2** |
| `grace.sc:142` | Grace's topic 49, "go home" — **any day, needs flag 65** |

**There is no day-1 arm anywhere.** So the day 1 → 2 advance can only come from Grace's topic 49.

**Flag 65's only clearer is `grace.sc:143`** — topic 49 itself, one line after it raises flag 15.
So taking "go home" spends it.

**Flag 65's setters** are all inside `theOpeningCartoon` (script 472, armed at rm470 under
`(not (proc13_0 11))`) and rm470's day-1 cutscenes `afterTheCloseUp` / `takeTheBody` / `takeOff` /
`putBodyAway`. Each of those also raises flag 11, and `rm471::init` raises it too (`rm471.sc:36`).
**Nothing in the game ever clears flag 11** — no `proc13_2 11`, no toggle; the only other setter is
`debugHandler.sc:253`, the excluded debug class. And rm471's sole entrance is `theOpeningCartoon`
(`newRoom: 471` at its states 24 and 102, nowhere else in the corpus), so `afterTheCloseUp`'s
`(== global12 471)` arming can fire exactly once.

**Therefore:** to be on day 3 you must have ended day 1; ending day 1 spends flag 65; flag 65 can
never be re-raised. On day 3 "go home" is not on Grace's menu, day 3's only ending is `endDay`'s
day-3 arm, and that arm demands `(global0 has: 38)` — reconVeve. **The declared red is right in its
verdict: `reconVeve@reg123=4` is a false positive.**

### The model gap, located exactly
The model already has every piece: `470->471` is gated `253: [0]` (flag 11 clear), the day-3 arm is
priced `cost=[8, 38]`, and since §1.12 the rm50 branch is priced `deps={178:[2], 307:[1]}`. What it
cannot see is that **flag 65 is SPENT to make the first day advance** — so it believes a day-3
player may still be holding it. That is a joint question, `(123, 307)`: measured, the model says
flag 65 can be 1 at every day 0-10.

`_gate_joints` is the right machinery and it already supports the three-register form. It declines
`(123, 257, 307)` for TWO reasons, not one: the `continue` added as a KQ5 performance fix
(`6239d2c`, "a triple only where no pair closes the cycle"), AND the triple's own condition
`A in writes_dep[C]`, which fails because flag 65's writers are conditioned on flag 11 and prevRoom,
never on the day. See §1.14 for what happened when the joint was built anyway.

## §1.14 The one-shot-enabler joint: BUILT, MEASURED, REVERTED (2026-08-30)

§1.13 said the model needs to see that flag 65 is spent to advance day 1. That is true, and a
three-register joint is not enough to see it. Built and reverted the same session; recorded so it
is not rebuilt as-is.

**The rule tried.** A counter `A` whose ordered step is gated by `B`, plus any `C` that a write of
`B` DEMANDS and that the same room writes OUT of the demanded values — raising `B` SPENDS `C`, so
whether `C` is still available is a question about how far `A` has come. Added after the existing
selection, through the same `_add`, so no current joint could be displaced.

**Census** (with the qualifier that the enabler must have been EARNED — a demand for `C`'s start
value 0 is a demand that nothing be done, and without it KQ5 yields eleven triples and LB2 eight,
the permutation shape the cap exists to refuse):

| | LSL2 | KQ4 | KQ6 | KQ5 | LB2 | GK1 |
|---|---|---|---|---|---|---|
| one-shot triples | 0 | 0 | 0 | 7+ | 4 | **1** — `(123, 257, 307)` |
| joints already held (cap 8) | 0 | 0 | 1 | **7** | 3 | 1 |

**It built, and it did not work.** `gk1 joints: [(123, 257), (123, 257, 307)]`, and the walk still
says flag 65 can be 1 on every day 0-10. `reconVeve` did not retire — it gained **two more rows**
on the new joint (`reg(123,257,307)=(0,0,0)` and `(4,0,0)`).

**Why — and this is the useful part.** Re-raising flag 65 needs rm470 *arrived at from rm471*, and
`470->471` is gated `253: [0]` — flag 11 clear. Measured: **flag 11 is written only to 1**, at
rm470 and rm471, and never back; and **13 of the 14 flag-65 raise branches never mention it** (they
carry `{12: [471]}` or nothing). So the projection needs a FOURTH register, and `_gate_joints` is
bounded to three by construction.

Reverted rather than shipped: with the FP still standing, the triple is two noise rows on GK1 and
joint budget spent on LB2/KQ5 for nothing.

### ⭐ What this actually points at: MONOTONE LATCHES
Flag 11 is written to exactly one value and never back. That is not a state a product has to
track — it is a fact about the register: `flag 11 == 0` holds only until the first write, and every
site that raises flag 65 also raises flag 11. So "flag 65 can be raised at most once" is derivable
WITHOUT a four-way product, from monotonicity plus co-writes. The model has no notion of a
write that can happen at most once, and that — not a wider joint — is what `reconVeve` needs.
Same family as the R4 chain's remaining link, which is also "this can never be made true again".

## §1.15 RETURN-TO-SENDER: the conversation screen was a free door into every room (2026-08-30)

§1.10.4 left two named links under R4. This round closes the first one, and it is the older of
the two open items — the same gap §1.8 recorded under `sVoodooCode`.

### The game
GK1 holds its conversations in a room of their own. Talking to anyone leaves the map for the
interrogation screen (rm50); when the conversation ends, `newRoom: <prevRoom>` puts you back where
you were. Twenty of GK1's rooms are reached that way, and the model read every one of those
returns as an ordinary edge `50 -> X`. So the day-4 player walks into a conversation from anywhere
and "returns" to Cazaunoux's house — a house day 4 shut (`rm270.sc:200,217,845`, and rm270 is the
only way into rm280) and which they may never have entered. Two rounds of work put the day
requirement on `270->280`; the return walked around it.

### The rule, and why it is forced by the guard
An edge `a -> b` whose requirement pins the previous-room register to exactly `{b}` can be taken
ONLY by a player who came to `a` directly from `b`. So they satisfied some way into `b` at that
moment, and any register that neither room can write still holds the value it held then —
and therefore still satisfies whatever **every non-return way into `b`** demanded of it. Conjoin
those demands onto the return (`missability._return_to_sender`, called at the end of `edge_meta`).

Three qualifiers, each derived, and the first one is load-bearing:

1. **Only registers NEITHER ROOM writes**, nor any arrival at `b` sets on the way in. The window
   opens when the player last *entered* `b`, not when they left it — they stood in `b` first and
   in `a` second — so `b`'s own writes count, its `init` among them (it runs after the entry guard
   was tested). Measured without this qualifier: `50->240` gained `flag 16 == 0` from `230->240`,
   and rm240 is exactly where flag 16 is raised. That single unsound conjunct invented two
   softlock items (`badge`, `tracker`) and a `register_value_strandings` row.
2. **Only destinations with a non-return arrival.** A room whose only way in is the return asserts
   nothing about itself; nor does the start room.
3. **The necessary reading over those arrivals** — a register survives only if every arrival
   constrains it, and then its allowed values are the union. The same merge `_merged` and `chain`
   already apply in `edge_meta`.

### Census, and what moves
| | LSL2 | KQ4 | KQ6 | KQ5 | LB2 | GK1 |
|---|---|---|---|---|---|---|
| return-to-sender edges | 1 | 2 | 0 | 0 | 5 | **30** |
| edges actually constrained | 0 | 0 | 0 | 0 | 0 | **4** |

The other titles' destinations have no other way in, or their arrivals share no requirement.
The four GK1 edges and what each gains, all from the destination's single other arrival:

```
50->280  += 123 in {0,1,2,3}        <- 270->280   Cazaunoux's house, shut on day 4
50->340  += 123 in {0,1,2,3,4,5}    <- 330->340
50->240  += 785 == 1                <- 230->240   (its 258 == 0 is withdrawn by qualifier 1)
50->720  += 864 == 1, 867 == 0      <- 710->720
```

### ⛔ AND IT ADDS A FALSE POSITIVE — `braceMold`, proved from the scripts
GK1's surface gains one `softlock_items` entry and twelve `register_strandings` rows. The rows on
`VoodooCode1` and `reconVeve` are refinements of rows already reported (day 6 joins day 5/7; the
need room 340 drops out at days 6-7 because rm340 now closes). The new item is **`braceMold` (40)
at `reg123 = 4/6/7`, and it is a FALSE POSITIVE**:

* braceMold's only source is `rm280.sc:794` (`get: 40`) — Cazaunoux's house, which day 4 shuts.
  That much the row has right, and it is why the row appears only now.
* Its only need site is `napoleon.sc` `doVerb: 43` → `showMold`, which **`put: 40`s it at state 4**
  (`napoleon.sc:838`) and raises flag 256 at state 9 (`:858` — the only non-debug setter).
* Day 3's `endDay` arm demands `(proc13_0 256)` (`theMapPrint.sc:249-256`).

So day 3 cannot end without having shown the mold, which requires holding it; a day-4 player has
already spent it, and the site that "still needs" it is the very one that consumed it. Recorded in
`CONFIRMED_SAFE` with this evidence, and declared in KNOWN_RED — **not** cured by a clause
([[clause-that-protects-a-known-answer]]).

### ⭐ WHAT IT POINTS AT — a THIRD specimen of one FP class, and it is measurable
`_flip_live` already refuses a flip whose own precondition demands the item. It misses all three
of GK1's FPs, and two of them for the SAME reason: **a write branch's cost is its own
`_own_positive`, never the chained cost of the registers it depends on.** `_own_fixpoint` does
exactly that propagation for `_inroom_own`; `_wbranch` — the table `_psucc_joint` reads — does not.

| FP | what the flip really demands | where the model loses it |
|---|---|---|
| `braceMold@reg123=4` | day 3's arm needs flag 256, and `_wbranch[(498,460,1)]` **already costs `braceMold`** | the day-3 branch of `(257,200,1)` carries `deps={…,498:[1]}` and cost `[wolfPhone, reconVeve]` — it never inherits `value_cost(498,1)` |
| `sVoodooCode@reg488=1` | writing on the tomb needs both sketches (`rm300.sc:952`) | `_wbranch[(488,302,1)]` cost is **empty**: the demand is at rm300 where the scene is armed, the write is at rm302 inside it, and the cost does not cross the `newRoom` |
| `reconVeve@reg123=4` | day 3's arm needs reconVeve — but topic 49 ends the day for free | needs the one-shot reading of flag 65 (§1.14), not a cost |

One hop of `_own_fixpoint`'s own composition, applied to the branch table, retires the first.
The second is the same question asked across a room boundary. Both are cost-model work, and both
are cheaper than the monotone-latch mechanism §1.14 asks for — which only the third needs.

### R4 is still RED, and its remaining link is now the ONLY one
With rm280 sealed at day 4, R4's chain is intact in the model except for the carry-up:
`register_value_strandings`' conjunct 3 sees flag 74's write site (rm50) as reachable, and the
write is gated by flag 44 (`(178==10) AND (flag 44 OR flag 47)` — measured on the raw guard), whose
own producer is `178 == 12`, written only at rm280. The reverted carry-up (§1.9) is the right
shape; the measurement that killed it was the weak half — for a register with no projection it
asked `reach_avoiding(writer_rooms)` ("could you have skipped it"), which is nearly always true.
Two things are new since:
* **flags 44, 47 and 74 are all promoted registers now** (§1.12, the topic-as-move round), so that
  weak half need not fire for R4's chain at all — the strong `(r, v) in _pstates[T]` reading applies.
* `_region_writes` must filter the write's VALUE to the accepted set. It does not; for `T = 178`
  with `acc = {12}` it counts every other topic's write as a live way to produce topic 12.

⚠️ **And R4's PIN needs re-deriving before it is built for** ([[re-derive-a-reds-premise]]). The
check reads `rows_by_det["register_strandings"]` for a row whose `register` is flag 44 — but in
that detector `register` is the FLIP, and its rows are about ITEMS, so the check as written asks
"is some item stranded by flag 44 flipping", which is not R4. R4's mechanism is a register-VALUE
stranding: `register_value_strandings`, whose rows carry the stranded register as `reg` and the
flip as `register`. That detector is not in `rows_by_det` at all. ⛔ The VERDICT (R4 is real and
missed) is ground truth and unaffected; only the mechanism spelling is this project's own, and
re-pinning it is a bless — it waits for the USER.

### Measured (real build, not the simulation)
**LSL2, KQ4, KQ6, LB2 and KQ5 byte-identical** on the full snapshot surface; the GK1 surface from
the rebuilt model is identical to the product simulation, so the source derives the same
restriction. Times: LSL2 38s, KQ4 81s, KQ6 105s, LB2 56s, KQ5 508s, GK1 248s.
Suite **887 passed / 13 known-red / 0 unexpected / 0 crashed** (2313s) — the +9 over 878 are this
round's own unit checks (`test_prev_return` Part 4), and the failing set is exactly the declared
one. GK1's surface delta, in full: `softlock_items` gains `braceMold`; `register_strandings` gains
twelve rows (six `braceMold`, three `VoodooCode1`/`reconVeve` at day 6, and `reconVeve`'s days 6-7
lose need-room 340); `edge_specs` `rm200/rm205->rm372` and three `register_write_specs` gain
`has: 40`. No coverage change: R1 is still caught on the day-5 flip, nothing dropped.

## §1.16 Branch-cost chaining, and the ONE blocker all three GK1 FPs share (2026-08-30)

§1.15 named the cost-model gap and predicted it would retire `braceMold`. **It does not**, and
the measurement is the useful part: it says all three of GK1's day-counter false positives are
now blocked by exactly one thing.

### The change: the fold's composition, asked of the per-branch table
`_own_fixpoint` lets an item requirement flow along a chain of registers into `_inroom_own` — the
per-(register, room, value) FOLD. `_wbranch`, the per-BRANCH table `_psucc_joint` reads, kept each
branch's own `_own_positive` and never inherited what the registers its own guard names cost. Same
principle, one table short of applied ([[same-rule-two-places]]). `_value_cost` and
`_chain_branch_costs` are now module level so the two readings cannot drift.

It lands exactly where predicted — `endDay`'s day-3 arm goes from
`[wolfPhone, reconVeve]` to `[wolfPhone, oil, reconVeve, braceMold]`, and the day-4 arm picks up
five more — and **the GK1 surface does not move at all.** Nor does any other:

| | LSL2 | KQ4 | KQ6 | KQ5 | LB2 | GK1 |
|---|---|---|---|---|---|---|
| branches that gain a cost | 4 | 2 | 106 | 50 | 0 | 37 |
| surface | identical | identical | identical | identical | identical | identical |

Kept anyway, for the principle and because it is a prerequisite that is invisible on its own: the
`braceMold` row needs this AND the once-only reading of flag 65 to retire, and measuring the two
together would confound them. Same standing as the conditional-`init` channel in `_build_product`.

### Why the surface does not move, and this is the finding
With `braceMold` banned, the joint walk still reaches `flag 15 == 1` on day 3 — **at room 50**.
That is Grace's topic 49: `_wbranch[(257, 50, 1)]`, `deps={178: [2], 307: [1]}`, cost `[]`. The
free day-end goes around every cost the arms carry. So:

| FP | with §1.15 + §1.16 in place, what is left |
|---|---|
| `reconVeve@reg123=4` | the topic-49 route |
| `braceMold@reg123=4` | the topic-49 route |
| `sVoodooCode@reg488=1` | the arming cost not crossing `rm300 -> rm302` (unrelated) |

**Two of the three now share ONE blocker**, and it is the one §1.13 proved from the scripts and
§1.14 named: flag 65 is spent to advance day 1 and can never be re-raised.

### One more thing the model is missing on that very branch
`_wbranch[(257, 50, 1)]` and `_wbranch[(307, 50, 0)]` carry **the same `deps`** — they are the two
lines of topic 49 (`grace.sc:142` raises flag 15, `:143` clears flag 65) — and both record
`co = frozenset()`. `_own_fixpoint` records co-writes only for MACHINE state bodies; a handler
that writes two registers under one guard files two independent branches. So the model cannot see
that ending the day this way SPENDS flag 65, which is half of §1.13's proof. That is a small,
derivable fix, and it is the first half of the once-only mechanism.

### ⛔ MEASURED AND NOT BUILT: the router generalisation
`_return_to_sender` is the case `p == b` of a wider shape — an edge `a -> b` gated `prev == p` for
any single `p`, where the same argument prices it by `p`'s entry condition. Censused on GK1:
53 routed alternatives, 30 of them returns and **23 genuine routers, of which zero constrain
anything.** `205 -> 470` (the opening cartoon, `prev == 750`) is the one that would have mattered,
and it fails on the soundness qualifier — rm750 writes the day counter itself. Recorded so it is
not built speculatively; `p == b` is the case that pays, because `nec[b]` is then about the
destination itself.

## §1.17 The travel movie was severed: a cross-script global destination (2026-08-31)

Chasing the §1.16 blocker turned up a genuine model bug, older than this round and independent
of it. The once-only simulation kept "re-raising" flag 65 at rm470 on any day, and the trace ran
through `205->470` — an edge whose only alternatives demand `prev == 750`. Asking how the REAL
day-1 player enters the crime scene at all exposed the answer: **in the model, they don't.** The
scalar prevRoom projection had rooms 470, 471 and 750 flatly unreachable — an invented seal, the
under-approximating direction, the one that fabricates.

### The game
GK1 travels by map. Each icon's `cue` does `(global2 cue: <room>)`, the map's dispatch
(`rm205.sc:204-219`, rm200 likewise) either goes directly (`newRoom: register`) or — the FIRST
time — stores the destination (`(= global175 register)`), raises flag 449 and plays the travel
movie in **rm372**, whose state 4 exits `(global2 newRoom: global175)`. `global175` is assigned
nowhere else in the game.

### The gap
`extract.var_room_values` resolves an indirect destination by scanning THE SITE'S OWN script —
exact for a local, and a deliberate narrowing for a global. rm372's script never assigns
global175, so the scan answered `{}` and the exit was silently dropped: every map destination
lost its first-visit edge. The map machines' own `newRoom: register` fan was fine (that is
`_script_prop_values`, the arming-parameter flow), which is why the world still LOOKED connected
— the direct-travel alternatives carried it, mostly under guards no honest first-time player
satisfies.

### The fix — one rule in `var_room_values`, no sentinel needed
A GLOBAL whose script-local scan is empty falls back to a game-wide assignment scan, one hop
deep: a literal RHS is a destination; an RHS that is a Script's arming property (`register`)
inherits that script's `_script_prop_values` — the very resolver the routing machine itself is
fanned with. Unlike the `PREV_DEST` case this needs no deferred expansion: assignments are
static, and the whole IR is in hand at extraction.

Two boundaries, both derived:
* **The engine's PENDING and CURRENT room registers are excluded**, for the reason the PREVIOUS
  one already returns a sentinel: they are written by the `Game::newRoom` plumbing from every
  room change, so the game-wide scan would fan the engine loop's own dispatch over every room
  ever named.
* **Cross-script values carry no guard.** A path condition is a fact about its own script's
  moment — rm205's dispatch runs under "flag 449 clear" and raises flag 449 on the very path
  that leads to rm372, so carrying it would seal the new edge at birth.

Corpus census (the `newRoom: <Variable>` sweep, all six games): every other empty-global site is
the engine's pending register in the `Rm` base class; every empty `Parameter`/`Temp` site is a
`newRoom`-method override passing its argument to `super` — plumbing, correctly edge-free. **One
site in the corpus resolves: GK1's rm372 — to 19 rooms, not 7**, because BOTH maps write
global175 (rm200's twelve destinations and rm205's eight, minus overlap). Pinned at unit level in
`test_prev_return` Part 1b.

### ⛔ AND THE TEST EXPOSED A SECOND BUG: the per-IR memos were keyed on `id(ir)`
Inserting Part 1b's synthetic IR made Part 2's — a test that had passed for days — fail: every
per-IR memo in `extract` (`_ROOM_SPECIES`, `_PREV_G`, ten others) was keyed on `id(ir)`, a memo
entry outlives its IR, and `id()` is only unique among LIVE objects. The freed test IR's id was
reused by the next test's IR, which was then served the dead game's room species. The same
hazard sat under any tool that loads IRs serially in one process. All twelve memos now pin the
IR in a side registry when they mint its key — a pinned object's id can never be reused. (Keying
on the IR object itself was tried first and is wrong here: the unit harnesses hand these
derivations `SimpleNamespace` stand-ins, which are unhashable — caught by
`test_deletion_soundness`.) The leak is the model cache's own policy: a process that holds
models holds their IRs anyway.

### §1.17 measured (real rebuild, all six games)
**LSL2, KQ4, KQ6, LB2, KQ5 byte-identical.** GK1 moves, and it is a COVERAGE change in both
directions:

* **`sLakePatter` LEAVES `softlock_items`** — the declared-FP `dangerous_sinks` row retires,
  with its market spec and the two REFUSED `rm200/rm50->rm290 (has: 31)` edge specs. Probed:
  `required[31]` no longer lists rm290 at all — the phantom Magentia demand died with the
  dishonest wiring. An FP retired by structure, not by a clause.
* **The ENDGAME becomes analyzable.** The fan includes the airport (750 is a map icon), so the
  finale region — rm700/710/720/899 — is reachable in the prevRoom projection for the first
  time (`_pstates[12]` covered none of it before). The guard surface follows: the day-end
  demands relocate from the rm372 chokepoint (`rm200/205->rm372`, now 19-way) to the real ones
  (`rm750->rm700` gains `has: 32,38,40,64`; `rm720->rm50` and `rm800->rm899` gain `has: 64`),
  and the placements move with them (`Hounfour` arm-event, rm720 setscript).
* **One new row, an FP of the documented flip-precondition class**: `knife@reg12=720 -> [720]`
  (flip room 50, source rm510). Day 7 cannot end without the knife (`readTheScroll` demands
  `egoCutHimself`, written only by `cutEgo` via the knife's own verb — `rm540.sc:299-307`,
  `tile1.sc:497` — and no `put: 64` exists), so the day-9 player at rm720 holds it; the
  prevRoom projection cannot see the day chain. Declared under knife's existing
  CONFIRMED_SAFE entry.
* R1 unmoved: `VoodooCode1@reg123=5` and the whole §1.15/§1.16 row set stand.

Times: LSL2 37s, KQ4 80s, KQ6 99s, LB2 52s, KQ5 633s, GK1 242s.

## §1.18 The carry-up re-measured, and R4 diagnosed to a CYCLE (2026-08-31, later)

The narrowed carry-up — the two fixes §1.15 named: STRONG-ONLY (a carry onto a register with no
projection is refused; every register in R4's chain is promoted now) and the VALUE FILTER in
`_region_writes` — was rebuilt as a product simulation and measured on GK1.

### ⛔ The revert's verdict stands, more decisively than before
**9,740 rows.** The strong half does not tame the shape: prevRoom "seals" dominate (every room
crossing seeds a flip; `reg12=210` alone carries 291 rows), and the long tail is day-8/9 endgame
seals stranding cutscene armings — true statements about missable CONTENT, not item softlocks.
The 2026-08-28 conclusion ("the FP shape is the design, not an accident") survives its second
measurement with both named fixes applied. Do not rebuild this detector shape a third time.

One row in the flood is genuinely interesting — `seal reg257=0: reg123 must be [4] for
sTraceTattoo@rm450 carried-from reg564` — the day-advance itself as the seal, carrying one hop of
R4's chain (the trace's arming flag 322 is producible only at day 4).

### ⭐ R4's remaining gap, diagnosed exactly: a CYCLIC day-gate
The flag-44 row still does not form, and chasing the last blocker bottomed out the whole chain:

* flag 74's write needs `178==10 AND (flag 44 OR flag 47)` (the OR split lands per-branch);
* flag 44 is dead post-flip (its write needs `178==12`, produced only at rm280, sealed);
* **flag 47 is NOT dead post-flip — it is the day-5 opening.** Its writers run after day 4 ends;
  day 4 ends only with the trace (`has: 26`); the trace needs flag 74. **74 → 47 → day 5 → the
  trace → 74.** An acyclic chase (the carry-up's `_carry_up`, any depth) can never see a freeze
  that holds only around a cycle; each link individually looks fixable.

The mechanism that CAN see it: a least-fixpoint PRODUCIBLE-SET over the branch tables within the
sealed region — seed with what the flip can carry, iterate region write branches whose deps are
already producible, and read "flag 74 never enters the set". Two prerequisites surfaced today,
each measured:

1. **Armer-chain inheritance in the branch tables** (`_own_fixpoint`, shipped this round): a
   machine armed from another machine's changeState inherits the armer's musts at the arming
   state — `edge_meta` composes exactly this (`chain`) onto exits, the branch tables did not.
   Measured on the target case: NOT sufficient alone — `startOfDay5`'s own musts are empty (its
   day-5 fact lives in its ENTRY reqs, which the chain does not fold in), and `getTheVeve` also
   has a DIRECT arming (flag-73/own(9)-gated), so the necessary reading over its entries honestly
   drops the day pin. The er-fold (armer entry reqs folded necessarily over the armer's own
   entries, recursively) is the named remainder.
2. **The 178-carry**: `(370, 178==12)` is permissively reachable, so a producible-set seeded from
   carried values would call flag 44 fixable. The real fact is Teller-script SCOPE — script 1055's
   handlers run at rm50 only while the Cazaunoux Teller is ACTIVE, and activation happens at
   rm280 — the same scope family as [[inventory-script-scope-gap]]. Without it, any post-flip
   producibility reading of flag 44 is permissive-open.

Neither is small. R4 stays a declared RED with, for the first time, its full remaining mechanism
named end to end: producible-set fixpoint + er-fold chaining + Teller-activation scope.

### Measured — and then the er-fold BUILT the same day
The armer-chain inheritance alone (armer musts only): all six byte-identical — inert on its own
target case, because `startOfDay5`'s musts are empty; its day-5 fact is entry-side.

**So the er-fold was built** (prerequisite 1 complete): `F(m)` — what every arming of `m`
necessarily established — to a bounded fixpoint over the armer graph. A direct entry contributes
its guard's necessary reading; a chained entry contributes the armer's `entry_reqs` at the arming
state ∧ its `state_musts` there ∧ `F(armer)`; across entries the fold is necessary (one
unconstrained way in and the fact is gone — `getTheVeve`'s direct flag-73 arming honestly keeps
the day pin off its branches, the negative control). Census before building: KQ6 22 all-chained
machines gain armer entry facts, GK1 25, KQ5 16, LB2 8, KQ4 2. Verified at the table: LB2's
`sORileyComes` write `(418,454,1)` now carries `{123:[5]}` — the act-5 pin through the chain.

**All six games byte-identical again** (LSL2 37s, KQ4 79s, KQ6 61s, LB2 32s, KQ5 627s, GK1
145s): the enrichment is real at the branch level and no verdict rests on it yet — the
producible-set fixpoint (the R4 mechanism above) is its intended consumer. `edge_meta`'s own
`chain` still folds musts only; teaching it `F` is the remaining half of the same rule, parked
until a measured case needs it ([[same-rule-two-places]], flagged there).

## §1.19 An exit carries the writes its path established (2026-08-31, later)

Following §1.18's prerequisite 2 to its root closed most of it and found the day's FOURTH
sighting of the walk/table split.

### The recon that shrank the problem
The "Teller-activation scope" fear was overstated: the interrogation protocol is ALREADY edge
sets. rm50's dispatch (`interrogation.sc:93-110`) switches on `global178`, and the talk sites
write the subject before their `newRoom: 50` — 20 of rm50's 24 in-edge alternatives carried
`sets{178: subject}` (rm280's carries `sets178=12` exactly, which is flag 44's whole activation
story). The four that did not — rm300/310/380/460 — were one gap in three costumes.

### The gap
`compile_machine`'s walk ACCUMULATES writes along each path (`nw`) into its cumulative exits —
and the published per-state rows (`opmodel._machine_info`'s `states`, the table `edge_meta` and
every detector read) never did. A cutscene that decides early and pays off late shipped its exit
without its own effects: `interrogateGranny` writes the subject at state 1 (`rm380.sc:587`) and
exits at state 2 with `writes=[]`.

### The fix — `compile.acc_entry_writes`, one consumer
A dataflow to a fixpoint over the state graph: IN[K] = the register writes EVERY route to K has
performed (necessary merge — a value routes disagree on drops; an entry state seeds empty; a
`(++ G)` kills G; a symbolic write is skipped). Transitions mirror `compile_machine`'s walk.
⛔ A PARK CLEARS THE ACCUMULATOR — deliberately more conservative than `compile_machine`, which
keeps `nw` across waits: an arrival value is FORCED on whoever crosses the published edge, so a
write a wait could have unmade must not ride. The subject writes this exists for ride say-cues,
which `carry_cues` already turned into ADVANCE.

Stored as `info["acc_writes"]`; consumed ONLY by `edge_meta`'s exit `sets` (exit-state writes
win a conflict). The states table itself is untouched — other readers unchanged this round.

Measured on the target: rm380→50 now carries `sets178=26`; rm300/310→50 gain subject-carrying
alternatives (`sets178=32`); **21 of 24 arrivals now carry the subject**. The residue, recorded:
napoleon's write is at the ARMING SITE (`napoleon.sc:1287`, `(= global178 34)` immediately
before `setScript: askBartender`) — arming-context writes ride entry LOCALS, not exits — and
Cemetery keeps one subject-free route. Both permissive, both named.

### §1.19 measured (real rebuild, all six)
**LSL2, KQ4, KQ6, LB2, KQ5 byte-identical.** GK1 moves and it is the GUARD surface, not a
verdict: `softlock_items` and every detector row unchanged; the day-end demands land as APPLIED
edge guards at the map's own exits (`rm370->rm371/372: (has: 32, 38, 40)`, two `rm370
arm-event` placements) where before two placements failed outright (`no free-running trap write
found`); and the two write-guards for the sVoodooCode complex (`reg488=1`, `reg492=1`) flip to
REFUSED — the accumulated sets changed `verify`'s world and the placer now prefers the edge
form. A patch that lands at the room the player actually leaves beats a write-guard that
verify distrusts; and both retired placements guarded a declared-FP complex anyway.

## §1.20 Closing the subject doors (2026-08-31, last round)

§1.19 left rm50 with subject-free arrivals — the carry holes that would defeat any producibility
reading of R4's chain (a stale `178 == 12` carried across the day seal makes flag 44 look
fixable). Chasing each hole to its line found THREE distinct gaps; all shipped, all verified:

1. **`Machine.entry_gwrites`** — a GLOBAL the arming context writes rides the machine like its
   locals already did. napoleon sets the subject one line before `setScript: askBartender`
   (`napoleon.sc:1287`); captured in `_scan_setscript`, necessary-merged per machine in
   `_add_entry`, seeded into `acc_entry_writes`. `460->50` now carries `sets178=34`.
2. **One steps table for both walks** — `compile_machine` re-derived its own steps from the RAW
   bodies without `opmodel._inline_calls`, so a machine whose transitions live inside a proc
   published a table its own delivery walk could not reproduce: `sTalkToKeeper` shows
   `K=4 JUMP 9 -> EXIT 50` and delivered NOTHING, leaving its flat cs_edge unsuppressed as a
   subject-free bypass. The FIFTH walk/table split of the day. It now accepts the caller's
   (inlined, cue-carried, compressed) table.
3. **An absent arming register answers `unknown`, not 0** (`_ctr_holds`) — the zero default is
   SCI's rule for LOCALS; the register is a Script property, absent exactly when the arming's
   third argument was an unresolvable parameter (the clicked topic). Reading it as 0 pruned every
   `register == K` arm — which kept the delivery empty even on the good table.

With all three on: **every arrival at rm50 carries the subject** (22 rows, 0 free; the two flat
bypasses composed away; `machine_delivered` 161→166) — the prerequisite R4's producibility
consumer needed. Diagnosis rig: the (machine, steps) pair pickled once, iterated instantly — the
walk replica found the refusal in one trace after two blind rebuilds.

### ⛔ AND ALL THREE ARE PARKED (2026-09-01): each mover collides with the KQ6 golden
Measured on all six: five byte-identical, **KQ6 — GOLDEN, play-confirmed guards installed —
moved on the guard surface** (every detector row byte-identical): the labyrinth four-item
carry-in guards relocate from the raw `rm340->rm405/rm440` edges into `pullOutMapScr`'s travel
dispatch, and `rm380->rm300` gains `(has: 40)` — ⛔ an FP guard per the USER's 2026-09-01
ruling (the Oracle GIVES the sacred water; there is no way out without it). Two ENFORCED
oracle checks red: `test_kq6_ground_truth` "ALL FOUR carry-ins strand at the ENTRANCE" (the
frontier collapses to the one remaining flat crossing) and `test_toll` "the three capture
guards" (one spec remains).

Bisected T1/T2/T3: the entry_gwrites seed and the unresolved-register seed are **each
sufficient alone** to move KQ6 (`stepDown` is armed `0 [local200 (self rockPointer:)]` —
honestly unreadable — and the capture cutscenes' arming contexts write flags that ride their
exits); with both off, KQ6 restores **byte-for-byte**. The steps-table feed independently moves
it through `pullOutMapScr`'s proc-computed fan.

The parks follow [[oracle-tests-are-the-authority]] and the KQ6 owner's standing preference
(golden lifted verbatim after play-checks): an honest derivation that relocates play-confirmed
installed guards is a BLESS, not a side effect. All three park sites carry the record and unpark
TOGETHER — the new guard shape (capture demands at the travel dispatch + the sacredWater edge)
is one coherent surface and deserves one play-checked bless. Until then GK1's rm50 stands at
**21 of 24 arrivals with the subject** (§1.19's shipped state; free: the two Cemetery path
variants and napoleon), and the producibility consumer must treat those three doors as
carry-permissive.

## §1.21 The KQ6 movers, bisected to SINGLE CAUSES (2026-09-01, the USER's 😬)

The USER's ruling reframed §1.20: *"assume anything that moves KQ6 is wrong... it's possible
there's a bug."* Right on both counts. Per-machine bisection of the parked drivers:

| KQ6 surface change | single mover (bisected) | the fact | verdict |
|---|---|---|---|
| `rm380->rm300 (has: 40)` appears | `flyToBeach@380` gwrites `{flag3: 1}` | HONEST — `goodNews` K=30: `(proc913_1 3)` then **`(global0 get: 40)`** then the arming (`rm380.sc`) | **BUG FOUND, cure named**: the toll row it sites was USER-ruled FP (the Oracle GIVES the water), and the crossing's own arming context GRANTS item 40 — arming-context `get:`s must ride like the writes now do (`entry_ggets`, the machine-level `_cogrants`); a guard demanding a co-granted item refuses itself |
| `rm340->rm405/440` guards relocate to the dispatch | `freeCeleste@441` gwrites `{173: 1}` | HONEST — `minoTrigger.sc`: `(proc913_1 1)` + `(minotaur dispose:)` right before the arming; every freeCeleste exit really does carry "minotaur defeated" | **BUG IS DOWNSTREAM**: an honest fact reaching the guard placer degrades the placement (three play-confirmed sites → dispatch + one). The hunt moves to `guards.py`: why does forcing 173=1 on freeCeleste's exits kill the two edge-guard placements? OPEN |
| (driver 3) cliffs fan delivers `rm340->300` etc. | script-21 `stepDown` (region stair machine, register honestly unreadable) | the UNKNOWN-register walk over-approximates | **PRINCIPLE FOUND**: `delivered` feeds SUPPRESSION, which needs an UNDER-approximation ("this machine certainly carries this statement") while the unknown-register walk over-approximates — two consumers, opposite soundness needs. Cure: certain-only `delivered` (walk marks exits reached through an unknown counter test), or the deeper redesign — suppression keyed on STATEMENT IDENTITY (via-match), not delivery |
| (driver 2) `pullOutMapScr` fan delivers | the inlined steps table | its dispatch fan | same certainty audit needed before unparking |

Also surfaced, unaudited: `timerMinotaurKillEgo` gwrites `{409: 152}` — a property-lowered
synthetic with a non-flag value riding as arming context; A3 shows it moves nothing on KQ6, but
the capture's appetite for lowered-property writes deserves its own census before any unpark.

⛔ Bisection hygiene, learned twice tonight: an empty snapshot is NOT a diff (capture stderr,
check size); an inline `# comment` in a replaced call line can swallow the trailing comma.

### §1.21 addendum — the catacombs mechanism PROVEN to one row (2026-09-01, later)
Seeding ONLY freeCeleste's gwrites changes exactly one emeta row:

    440->340[1]  req={443: [1]}  sets={173: 1, 12: 440}

The seed lands on a composed row whose `req` pins flag 443 (hornSwaggled's spelling of the
defeat), NOT 173 — so in the **173-projection** the row is a free, unpriced `0 -> 1` flip of
"minotaur defeated" (443 is another register; per-projection walks cannot see its scarf price,
which `_reg_cost` carries only for the banned-item reading). Every 173-gated carry-in frontier
in the catacombs dissolves, and the four-item guards at rm340->rm405/440 VANISH — not relocate;
the earlier "relocation" reading was wrong (the +dispatch placement belongs to the sacredWater
mover).

⭐ The principle, stated once: **an effect-set on a row that does not pin the same register in
its `req` is an unpriced cross-projection flip.** The hole is generic — today's exit-state
writes ride the same way (`440->409[0] sets={408: 4} req={}` exists in the blessed surface) —
the gwrites seed merely poured a LOAD-BEARING register into it. Constraint for any unpark:
either a seeded `sets{R: v}` rides only rows whose `req` pins `R` (null-safe), or edge sets grow
a cost channel the projections can price (`_inroom_own` for crossings — the same composition
in-room writes already have).

The cure list after the full hunt, all derived, none KQ6-shaped:
1. `entry_ggets` — arming-context grants ride; a guard demanding a co-granted item refuses
   itself (kills the sacredWater FP mover at the root).
2. Certain-only `delivered` (or statement-identity suppression) — the two-consumer soundness
   split (kills the cliffs phantom mover).
3. A cost channel for edge sets — the unpriced-flip principle above (makes the gwrites seed
   sound; also audits today's pre-existing exit-write sets).

## §1.36 A PARK that arms a fatal machine is a DEATH (2026-09-02, designed)

`_trap_graph` has always had the word — DOOMED, an arming from which the death is certain —
for the ESCAPE question. The armer's own walk never applied it: `(gEgo setScript: killGabe)`
inside `roomScript@480` state 5 leaves that state PARKED (no cue, no cycles), and the
2026-08-28c rule "a PARK is a WAIT" resumes the walk at state 6 — so the maskless visitor's
path reaches state 81 and ends the day dead. Likewise state 9 (mask, no drums). The exact
cases only: a PARK path whose guard is the arming's guard atom-for-atom, or an unconditional
arming, becomes DEATH; FATAL means every path from the target's start terminates in DEATH
(an EXIT/END/PARK terminal disqualifies). Consequence on GK1: state 81's musts become
`{216: {1}, 299: {1}}`, so the ritual's day step is priced at the croc mask and pinned to the
tattoo flag — which is what §1.31's windows can then place on day 7. SIMULATED IN THE LOADED
MODEL (no source touched): GK1 has exactly ten fatal machines (killGabe, deathScript@770,
the hounfour beatings, sDJKills, the ceremony deaths), the pass flips exactly two paths
(roomScript@480 states 5 and 9), and state 81's musts become `{216:{1}, 299:{1}}`. Apply
script ready; measured after the rvs+§1.33 commit.

## §1.35 Why §1.34 fires a day early: a phantom bayou visit (2026-09-02)

Traced to the room: the new day-3→4 step fires at rm480 = `bayouRitual` (the day-7 night
ceremony), reached from rm490 = `bayouMaze` (the tracker maze), reached from the travel movie
rm372, whose destination fan (§1.17) names the bayou through the day map's `bayou` icon —
"the icon that was clicked is the player's choice, not a state". The CHOICE is free; the
icon's PRESENCE is not: it exists only under the map's init condition (a flag raised when the
bayou becomes known, day 7). The resolver conflated the two, so the model can visit the bayou
on day 1. Harmless while the ritual wrote nothing; §1.34 made it write the day.

Two further facts, both recorded and both permissive today:
  * `roomScript@480` state 5: without flag 216 (set only by using the MASK, item 21, in the
    maze) it arms `killGabe` on the ego — recognised as DEATH (`death_signal (241,1)`), armed
    from roomScript states 5 and 9 — and the room script's own path is read as a PARK-and-
    wait, so the walk continues past a certain death to state 81 and increments the day.
    A path that arms a fatal machine and waits is DOOMED (the `_trap_graph` word), and the
    honest transition for it is DEATH.
  * `letsGo@490` reaches `newRoom: 480` with or without the mask (state 0's else-branch
    skips to 7); flag 299 only picks views. So the maze always ends at the ritual clearing,
    and the day-3 gate is entirely the icon's presence condition.

CONFIRMED in `rm205::init`: `(if (proc13_0 268) (greaterMap add: bayou))` — and likewise
the lake (flag 64), grandma (101), the airport (269): each icon is ADDED to the map's
container under a flag. `cast_conditions` reads `init:` sends and misses the `add:` idiom,
so every icon reads as always present.

The cure is a BUNDLE, none of it GK1-shaped: (i) an icon-derived destination carries the
icon's PRESENCE condition — `cast_conditions` learns the container-`add:` idiom, and
`_script_prop_values` conjoins `cast_guard(icon)` onto the destination (the owner rule the
lifter already applies to handlers); (ii) §1.31's consumer windows, extended to EDGE reqs and to pruning `_rstep`
steps whose branch deps pin a windowed value (the scalar day projection cannot see a flag,
but it can see "this flag is never in hand before day 7"); (iii) doomed arming ⇒ DEATH.
§1.34 stays UNCOMMITTED until the bundle restores R1 at day 5.

MEASURED WITH THE SUITE: 884/14/1 unexpected — R1 red, as predicted. §1.34 REVERTED from
the tree (hunk kept as a patch). And one more gap under the bundle: flag 268's ONLY raise
is `PhraseDisplay::checkPhrases` in script 815 — a UI script's method (the code-phrase
puzzle), a class of write the model has never lifted (flag 101's is in `proc99_1`, the
day-start proc, under `day > 1`). Carrying the icon's presence condition BEFORE that
writer is captured would seal the bayou outright — the invented-seal direction. Bundle
order: doomed arming ⇒ DEATH (soundness, alone); §1.31 windows (+edge reqs, +_rstep
pruning); the UI-script/proc write capture for 268/101; icon presence; then §1.34 again.

Script 815 is the DRUM puzzle (`drumInset`, `Drum`, `Drummer`, `PhraseDisplay`): flag 268 is
raised in `PhraseDisplay::checkPhrases`, reached from `drumInset::dispose` and from
`addPhrase`/`deletePhrase` — two METHOD SENDS deep from any handler the harvest walks
(the walker follows proc calls, never self/object method sends). A capture class of its
own: bounded method-send following within a scoped script.

## §1.34 The day increments the model never had: `(++ day)` in a script that never compares it (2026-09-02)

Found by the §1.31 census: the record's ONLY live producer of the day-end flag on days 6 and
7 is go-home, so the windows would have made days 7-8 unreachable — and the reason is a
capture gap, not the game. An IR scan of every write to the day register lists 19 sites; the
model carries rm370's four increments (fanned into the steps 1→2 … 7→8 under the endDay
arms' `day == k`) and the 750/800 clamps, but NOT the increments in `roomScript@480`,
`leaveGermany@500` and `doTheDream@550` — Germany's and Africa's day advances. `_fan_globals`
fans `(++ G)` over `machine.glob_dom`, the literals the machine's OWN script compares G
against, and drops the write when that set is empty ("unknown domain -> never guess"). Those
three scripts never compare the day, so days 6→7→8→9 vanished, and the endgame stayed
reachable only through rm750's clamps. Consequence today: the (123, 6)/(123, 7) rows in
`register_strandings` stand on go-home's phantom day-ends.

Cure: fall back to the GAME-WIDE literal RANGE (every integer between the smallest and
largest literal the game compares or assigns for the register) when the script-local one is empty — the same "read the literals the code tests
against" rule, one scope wider; each fanned branch stays an ORDERED step `k → k+1` (the
permissive direction is an ordered step, never a free write). STATIC BLAST RADIUS (IR-only census of incremented globals with an empty local domain):
LSL2 9 sites (scores 104/105/108/115 …), KQ4 9 (113 the shovel-hole counter, range {5};
186; …), KQ6 1 (script 913, global 153, range 0..5), KQ5 8 (314/315 fan; 322/353/359 have
ranges of 122-201 values), LB2 10 (150 the SNAKE OIL, range 0..4 — its `(-- 150)` shakes
at 520/610 now fan as ordered steps; 111 at 630; 369), GK1 3 (the day). So the goldens
WILL very likely move, and every moved line must be traced to its site and judged
(a genuine missing step → a bless with the diagnosis; anything else → a bug). The fan is
BOUNDED at 64 domain values (the joints' cap precedent — a resource bound, not a game
rule; past it the increment is dropped exactly as before): KQ5's 322/353/359 stay out.
Prerequisite for §1.31's windows to be honest on GK1.

MEASURED (main, vs d76e757; rvs and §1.33 proven inert alone): LSL2/KQ4/KQ6/KQ5/LB2
byte-identical — the shovel counter, the snake oil, the scores, KQ6's 153 all inert.
GK1: exactly its three day-flip rows, each ONE DAY EARLIER (VoodooCode1 5→4, braceMold and
reconVeve 4→3). ⛔ NOT SHIPPABLE AS-IS: R1's true point of no return is the day-5 flip (the
oracle check pins value 5) and "stranded at day 4" is false. Diagnosed: rm480's new
`(++ day)` fires at day 3 because the model can fly to Germany on ANY day — rm490 (arrival)
is entered from the travel-movie room 372 with no day condition, the movie's destination
coming through §1.17's cross-script global fallback, which carries no guard by design. So
§1.34 EXPOSES a pre-existing over-approximation (Germany enterable any day) that was harmless
while Germany wrote nothing. The cure is on the entrance, not the increment: either the
travel destination's own guard (the map's assignment condition — a REGISTER fact that
persists for a counter/latch) rides the movie edge as req, or §1.31's consumer windows,
extended to EDGE reqs, window the flight by the day its enabling flag can be in hand.
§1.34 and §1.31 therefore ship TOGETHER, or not at all.

## §1.33 The cost channel's flat fold: probe was NULL, re-measuring (2026-09-02)

The nine cost sites (`cheapest` ×3, the `_wbranch`/`_wbranch_dom` costs ×6) fold
`_own_positive` — the FLAT reading — so an OR-of-own write prices every branch as necessary
(census of flat≠required at cost sites: LSL2 0, KQ4 341, KQ6 8, KQ5 25, LB2 8, GK1 30).
The candidate cure is `_own_required`: exact for single-item bans, permissive for group bans
(the DNF cost is exact for both; `blocked()` has the shape — a future round).

⛔ INSTRUMENT CONFESSION: the first blast-radius probe reported "byte-identical on all six"
— and its toggle had never applied (a substitution pattern asserted a count of 3 where the
file holds 1; the heredoc died, the script had no `set -e`, and six untoggled snapshots
diffed clean against themselves). Caught by cross-checking the pattern counts in both trees
before applying to main. The corrected probe (five patterns, counts 2/1/2/2/2) is chained
behind the rvs re-measurement; NOTHING about the cost fold is known until it reports, and
its monitor now prints the toggle confirmation line first.

RE-MEASURED, TOGGLE CONFIRMED (`toggled 9 cost sites` in the log): **all six surfaces
byte-identical** vs d76e757. The over-claims never reached a surface; shipped for the
principle — the `_chain_branch_costs` standing. (The probe's own restore step then crashed
and left the worktree toggled; caught and restored by checkout — the worktree holds no
uncommitted work, which is the one case where checkout IS the right restore.)

## §1.32 The rvs `_rstep` blindness, and the FP it uncovered (2026-09-02)

`register_value_strandings`' freeze conjunct and causality half read `_inroom` alone; a write
pinned by its own from-value lives in `_rstep` (GK1's flag 351 is `(0,1)@800`), so a stepped
register was invisible to both. Fixed: a step is a write for both questions. MEASURED (vs
d76e757): four goldens + GK1 byte-identical; **LB2 +1 row** —
`reg128==[0]@seal(12,123)=(26,5)->[350] via sMeetSteve`. Examined, not declared: register
128 is a 15-step counter at rm340, and `sMeetSteve`'s arming that demands it ALSO requires
`act == 2` — a demand an act-5 crosser never faces. Latent in conjunct 2 (`_reg_entry_demands`
records the presupposition without the arming's other musts), exposed the moment pre-flip
steps counted as a fix. Two cures, both principles: (1) the demand must be LIVE at the flip —
the demanding machine's arming musts over the flip's registers must admit a post-flip state
(the `_need_live` reading, applied to rvs); (2) `(not (not x))` IS `x` — `_must_equal` and
`_must_hold` stopped at the outer negation and read the Teller/act lowering's `¬¬(act==2)`
as no constraint. RE-MEASURED (vs d76e757): all six byte-identical — the LB2 row is gone and
nothing else moves; the round is inert on every surface, kept for the two principles.

## §1.31 ONCE-ONLY, DESIGNED AGAIN: the staged closure with necessary co-effects (2026-09-02)

§1.14 pointed at MONOTONE LATCHES and §1.16 at the co-write; the producible closure (§1.27) is
the machine that can compose them. Everything below is a recorded structure:

  * **the unique day-1 producer**: every writer of flag 15 is day-pinned (arms for days 2-5 at
    rm200/205/210) except Grace's go-home (`_wbranch[(257,50,1)]`, deps `{178:[2], 307:[1]}`),
    so the counter step 1→2 (deps `{257:[1], 123:[1]}`) has exactly ONE live producer at day 1;
  * **its recorded co-effect**: the go-home branch's `co` carries `(307, 0)` — the spend
    (the 5db647a handler co-writes);
  * **the raisers' recorded co-effect**: every branch of `(307, *, 1)` carries `(253, 1)` in
    its `co` (theOpeningCartoon / rm470's day-1 cutscenes each raise flag 11 too);
  * **the latch**: 253 is written to exactly one value game-wide and never back — the
    `scene_carryins` monotone test, verbatim.

THE RULE — necessary co-effects of a counter step: neco(k→k+1) = ⋂ over the step's dep-value
producers LIVE at day k (a producer whose deps admit no 123==k is excluded; one with no day
dep is included — the permissive direction) of [its `co` ∪ neco of ITS deps' producers],
bounded depth. neco(1→2) = {307:=0, 253:=1}. A neco fact on a MONOTONE latch persists
forever (confinement `{v}` for every later stage); a neco CLEAR on an ordinary register is a
seed override (the value at the step is 0; later raises may re-raise only if producible).

THE STAGED CLOSURE: PRE_k = closure confined 123 ≤ k, seeded from PRE_{k-1}'s PV with
neco(k-1→k) applied (monotone → confine; clear → seed {0}). With 253 confined to {1},
`470->471` (req 253:[0]) is dead, `(470, prev=471)` is unreachable under the restricted-
projection refinement, the cartoon's `¬253` arming is dead — so PV_k[307] = {0} for all
k ≥ 2. Sound: an over-approximation at every stage, narrowed only by facts that are necessary
consequences of steps the counter provably took.

TWO PAYOFFS FROM ONE PROOF:
  1. **R4 fires in the closure arm** (PRE seeded from the staged PRE_3): go-home is dead on
     day 4, the day-4 arm needs the trace, the trace needs 74, 74 needs 44 (frozen) or 47
     (day 5 — the emust-locked cycle) ⇒ no goal ⇒ the row names flag 44 at the day-4 flip.
  2. **Derived CONSUMER windows for the projections**: window(S==v) = {k : v ∈ PV_k[S]}.
     For 307==1 that is {0, 1}; every `_wbranch` branch whose deps pin 307∈{1} (the go-home
     257:=1) gains deps `{123: [0,1]}`. NOT the §1.16 spelling: that windowed the RAISE
     branches and admitted raise-spend-raise within day 1; a window on the CONSUMER, proved by
     the staged closure, is exactly "go-home only while 65 can be set". The joint (123, 257)
     then cannot end day 3 through Grace, the day-3 arm's cost (reconVeve, and braceMold via
     §1.16) prices the flip, `_flip_live` refuses the banned witness, and BOTH FPs retire.

FACT-CHECKED IN THE MODEL (2026-09-02c), with two refinements the facts demanded:
  * (b) ✓ go-home's branch: deps `{178:[2], 307:[1]}`, co `[(307, 0)]`;
  * (d) ✓ day 1's only live 257:=1 producer is go-home (every other branch is day-pinned
    to 2-5);
  * (a) flag 11 (253) is raised as the STEP `0→1` at rm470 and in-room at 470/471, never
    written to 0 — so "monotone" must read the written-value set over BOTH tables
    (`_inroom` ∪ `_rstep` targets, a singleton), not "no steps";
  * (c) twelve of the fourteen 307:=1 branches co-write `(253, 1)`; the other two co-write
    854 (NOT monotone — written to 0 at 470) but carry deps `{12: [471]}`, and rm471's sole
    entrance is `470→471` (req `253:[0]`) while `init_writes[471] = {253: 1}` unconditional.
    So `prev == 471 ⇒ 253 == 1` — a co-effect of the PREVIOUS-ROOM register's producers:
    `prev == p` means p's init ran, so p's unconditional init writes of monotone latches are
    necessary facts. neco(307==1) = {253:=1} over all fourteen.
CENSUS (2026-09-02c, step-necos = counter steps whose live dep-producers all co-write):
  * LSL2 none (no counters); KQ4 none (counter 116, no co-writes);
  * **KQ6**: counter 162, steps 0→1/1→2/2→3 each via `233==1`, three producers, all
    co-writing `(212, 1)` — the staged closure WILL act on KQ6 (golden: movement = bug);
  * **KQ5**: counter 331, step 5→6 via `332==6`, 42 producers, neco `{(331,2), (333,0)}` —
    a clear (seed override) and, oddly, a write of the counter itself (ignored: a
    co-effect on the counter is the step's own business);
  * **LB2**: counter 111, step 14→15 via `632==0`, five producers, neco = eleven clears
    (631..642 := 0) — seed overrides only;
  * **GK1**: 123 steps 1→2, 6→7, 7→8 via `257==1` with go-home the ONLY live producer —
    days 6 and 7 have NO endDay arm in the record. After the 307 window ({0,1}) the steps
    6→7 and 7→8 die at rm370 (the endgame stays reachable through rm750's clamps to 9/10).
    ⚠️ Either honest (those days end by a route the model lacks — a capture gap the windows
    EXPOSE, to be found in the scripts) or the rows at day 6/7 in `register_strandings`
    move; examine every GK1 line the measurement shows.
The census's monotone test was the OLD one (no steps) and lacked the prev-room rule, so
its GK1 necos read `{307:0}` alone; the refined draft yields `{307:0, 253:1}`.

SIMULATED IN THE LOADED MODEL (2026-09-02f), three faults found and fixed in the draft before
any measurement: (1) a stage must be seeded at the rooms the STEP LANDS in, not everywhere
the previous stage stood (values are carried, places are not) — and with positions reset
the restricted-projection refinement is sound for PRE too; (2) the closure treated a
CHAINED entry (guard None) as always armable — it now carries its chain's ROOT guards
(takeTheBody ← afterTheCloseUp ← `prev == 471`); (3) every cutscene also carries a
`(self changeState: 99)` from its own `handleEvent` — the Esc-to-skip redirect, recorded as
an entry with `is_self` — which is no way IN: the closure skips self-redirects. neco(1→2)
= `{307:0, 253:1}` derives correctly throughout.

## §1.37 The §1.31 payoff, simulated: the proof holds, the payoffs meet two older gaps (2026-09-02)

Simulated in the loaded model with the whole bundle (doomed arming, chain roots, self-redirects
skipped, the fixed staged PRE, the windows applied to the branch tables and `_rstep` and
`_emeta`, projections re-walked):
  * **the once-only proof stands**: `PRE_3[65] = {0}`, `window(65==1) = {0,1}`, and the go-home
    branch's deps read `{178:[2], 307:[1], 123:[0,1]}` — Grace's "go home" ends a day on days
    0-1 only, derived from recorded structures alone;
  * **R4 does NOT fire in the closure arm** — the flag-44-less crosser still reaches the goal,
    through rm750's `(= day 9)` clamp (`showAMovie` state 3, `prev == 500`): the Africa flight
    from Germany's hub, reachable at day 4 because the travel map's AIRPORT icon (flag 269,
    raised by the travel agent — a RECORDED writer) is treated as always present (§1.35's
    resolver gap). Icon presence, with an ignorance floor (carry the condition only when the
    flag has a recorded writer; the bayou's 268 has none), places both flights honestly;
  * **the day-3/4 FP rows retire as predicted** (reconVeve/braceMold at day 4 gone), but
    every day-flip row moved to day 9 — the same phantom flight — and **R1's day-5 row is
    GONE**: with go-home dead at day 4, the record's only day-4 ending is endDay's arm, whose
    flag 248 comes from `sFullShow@290` (Magentia's full show) — armed by using ANY not-yet-
    shown sketch (`_own_required` = ∅), but `entry_musts` reads it FLAT (all five sketches,
    the reading kept deliberately since 2026-08-15 for KQ6's holeInTheWall), so day 4 costs
    VoodooCode1 and the day-5 flip cannot strand it. Whether day 4 can truly end without the
    first tomb sketch is R1's premise — USER-enumerated ground truth, to be asked, not flipped.

SETTLED FROM THE SCRIPTS (2026-09-02h): `sFullShow@290` state 4 raises flag 248 ONLY under
`register == 40`, and message 40 is VoodooCode1 (`doverb_item_messages`; 48/24/16 are
policeVeve/veveCopy/reconVeve, which raise 450/451/452 instead). Flag 248's only other
setter is `proc99_1` — `debugHandler`'s jump-to-day catch-up (script 99: debugHandler,
dInvD, ourPlane), called from nowhere in play. Both day-4 endings (theMapPrint's arm and
the bookstore re-check) require 248. So day 4 cannot end without SHOWING VoodooCode1 to
Magentia; every day-5 player holds it; the day-5 flip strands nothing. **R1's row dying
under the bundle is the model becoming right** — but R1 is enumerated ground truth, and
the ruling is the USER's. The 2026-08-28 catch stood on the go-home leak.

And the phantom flights: the airport icon's presence flag 269 IS recorded (`(511, 220, 1)`,
the travel agent's topic 44) but with no captured topic condition, so carrying icon
presence would gate Germany on a flag producible any day — the day-9 rows and R4's
unfired arm both wait on whatever ties the travel agent's topic to its day.

FOUND (2026-09-02h): topic 44 is offered under `(if (gEgo has: 71))` — an If-VALUED
condition `atom()` has no case for (opaque), and item 71 is the MASTER CARD, Gabriel's
credit card, held from the opening — for which the model records NO source (the opening
grant is uncaptured). Two small gaps in series: the If-value lowering (apply_ifvalue.py,
drafted) and the initial-inventory grant; until the second lands, the first would SEAL the
airport (own(71) never satisfiable). Order: initial inventory → If-value → icon presence →
then the flights carry `own(master card)`, which is free — so the day tie must come from
elsewhere still. Recorded; not built.

The master card's grant: `wallet::cue` in script 24 — the INVENTORY script, an always-live
scope — hands over item 71 when the wallet is examined; `cue` is not a handler selector the
harvest walks, so the card has no source. Once captured it is free from the opening, so
`own(master card)` ties the flights to no day: the Germany/Africa day tie is NOT in the
airport topic. HOW the wallet grants it (2026-09-02k): `wallet::doVerb` verb 6 ends
`(gMessager say: 108 6 26 0 self)` — `self` in the CALLER slot, SCI's "cue me when this
dismisses" — and `wallet::cue` does the `get: 71`. A general idiom: an object passed as a
send's callback target has its `cue` run as the handler's continuation, under the handler's
path condition. Censused: the idiom with an effectful `cue` exists on GK1 alone (wallet,
keyEnvelope, phoEnvelope, veil) — inert elsewhere by construction. PARKED, deliberately:
the inventory scope walks only `doVerb` and REFUSES icon-bar item transfers as sources —
"an item transfer is a fact about a place, and the icon bar has no place" (the KQ6
collapse) — so even a walked `cue` would not source the card; and the card gates nothing
day-related (§1.37). The known limit stands as written in `opmodel._heffect`.

THE FLIGHTS' DAY TIE, FOUND (2026-09-02l): it is not a flag — it is the map icon's own
click handler. `rm205 airport::select` tests `(!= gDay 7)`: on any other day it says the
flight is not available and returns 0; only on day 7 does the icon's `cue` (→ rm750, the
plane) proceed. `select` is a handler selector the model never walks (only doVerb/
handleEvent), so the travel fan's `372→750` and `205→750` carried no day at all — the
phantom Germany/Africa flights, the day-9 rows and R4's unfired arm all trace to this one
method. The protocol, read from the classes: `IconMap::select` selects an icon only if the
icon's own `select` returns nonzero (the `IconI` default returns 1); `airport::select`
returns 0 on BOTH branches, refusing the map's selection and handling the click itself —
message 6 on days ≠ 7, message 4 on day 7 — so which branch boards the plane is not
structurally decidable (the messages would say; a play-check or the message resource
settles it). The honest capture, once settled: an icon-derived destination carries the
boarding branch's path condition (`gDay == 7`), which the day projection can read
directly — no window needed. Not built; recorded with its one open question.
The USER (2026-09-02, from play, "pretty sure"): the airport can be used on ONE day only —
a lead confirming the day-7 branch boards. NOT a value to encode: the rule must read the
boarding branch structurally (how msg 1/0/4 reaches `airport::cue`), or stay unbuilt. Every rm750 entrance tests flag 470 (reg 712), whose only writers sit in
rm93 (`doTheRestart`), so in play it stays 0 and the `712 == 0` alternatives are the open
ones. Where the game keeps Germany off the day-4 map remains to be found in the scripts.

RULED (2026-09-02i): the GK1 oracle is this project's own derivation (the USER: "I didn't
enumerate anything as real, you've been owning gk1 entirely"), so the question is settled
where it lives — the scripts — and the answer is NO, day 4 cannot end without showing
Magentia the tomb sketch. **R1 RETIRED**: VoodooCode1 → CONFIRMED_SAFE; the R1 check now
asserts NO day-flip row for it. The bundle (doomed arming, chain roots, staged closure +
windows) ships with this correction; its remaining known movement — day-flip rows drifting
to day 9 through the any-day flights — is declared, not hidden.
## §1.38 R5 — the croc mask at the ritual clearing, derived by the tool (2026-09-02)

The bundle's measurement (goldens and LB2 byte-identical) moved GK1 by exactly one guard:
`rm490→rm480: (gEgo has: 21)` — the croc mask, at the bayou maze's exit into the ritual
clearing. It is the doomed-arming rule's direct payoff: `bayouRitual`'s room script arms
`killGabe` on the ego at state 5 unless flag 216 is set (state 9 likewise unless flag 299),
and 216 is raised only by `maskAction` in the maze — using the mask. A player who walks into
the clearing without having done that dies with nothing to do about it on that screen:
"you walked into the finale without X", THE ONE RULE's in-scope shape. Before this round the
walk resumed past the death and the crossing read as free.

Mechanism, honestly: the row is an `edge_strandings` line, not a trap carry-in — with the
maskless crossing now a dead end, the mask is "obtainable before, unobtainable after, still
needed" (its need site is the maze itself, which the flat graph reaches again). The death is
what the row is about, and the guard it yields is right in direction and weaker than the
truth: `has: 21` lets a mask-holder who has not used it through, to die. The exact guard is
flag 216; a "doomed arrival" reading of `death_traps` (a room whose init-armed script dies
unless a register is set) would say so directly. R5 joins the oracle as EXPECTED_CAUGHT with
this pin.

THE EXACT GUARD, DERIVED (2026-09-02k, simulated then measuring): two readings in
`death_traps`, neither GK1-shaped. (1) A CHAINED arming of a fatal machine carries its
armer's `state_musts` at the arming state as atoms — killGabe's second entry, armed from
roomScript state 9 "unconditionally", is really `flag216 ∧ ¬flag299` (state 9 is reached
only there); read as None it made the death certain (case (a), no escape). (2) Case (c)'s
lever/clock split now matches case (b)'s: a register the room's machinery never WRITES is
PLOT state — the arrival's, demandable — not a clock that must survive at every value;
before, the survivor `{216:1, 299:1}` projected onto nothing and was lost. Simulated: exactly
one new trap row, `rm480: req {216:[1], 299:[1]}` — survive the clearing iff the mask was
used AND the tattoo done — and no other room moves on GK1.

## §1.39 The airport's day, read from the click: an icon-derived destination carries its gate (2026-09-02)

§1.37 ended on one open trail — how the day-7 message in `rm205 airport::select` reaches
`airport::cue` — and the scripts settle it in one class and one method. `IconMap::
dispatchEvent` (theMapPrint.sc:128-200) cues an icon only under `(self select: icon 1)`, and
`IconMap::select` returns 1 only if the ICON's own `select` does (`IconI::select` = `(return
1)`). The airport overrides it and returns 0 on BOTH branches — the map never cues it. On day
7 the branch says `(global91 say: 1 0 4 0 self 205)`: the Messager stores its `caller`
(Messager.sc:84) and, when the text ends, adds a `Cue` for it (Messager.sc:34-41), so the icon
is cued BACK — `airport::cue` → `(global2 cue: 750)` → `rm205::cue` → `chgRoom` → the plane.
On any other day the message has no caller. The boarding is the say:-caller cue-back, the
exact reading `machine._is_cue_send` has always given a Script state ("`self` anywhere in the
arguments is the cue callback"), applied to a method the model never walked.

**The rule, general.** `_script_prop_values`' param-flow branch (the icons' `(global2 cue:
N)` sends) used to note each destination unguarded. Now each carries (a) the send's own path
condition inside its method with EARLY RETURNS respected (`method_paths`, the third walker
over `control_shape`: grandma's `cue` returns after `(<= 7 gDay 10)` before reaching its
send), and (b) when the sending object is `add:`ed to a container whose class sends an
element a message only under a test of that element (`_class_cue_gate`, read from the class
chain: `(icon cue:)` under `(self select: icon 1)`, and `IconMap::select` testing `(param1
select: …)` one method-send deep — the pair (`select`, `cue`) is derived, never spelled), the
condition under which the icon's gate PERMITS (`_select_permits`): a path that returns
nonzero, a non-literal, nothing, or falls off the end, or one that returns 0 after handing
`self` out as a callback (`is_self_callback`, now the ONE predicate `machine._is_cue_send`
and `compile._count_cues_send` call). Paths that differ only in an unreadable test (the
`((ScriptID 20 0) dialog:)` disposal) collapse to one; several distinct permitting paths
read permissive (an OR is not a conjunct); a gate that never permits drops the destination.

**Second hop.** The first-visit movie (rm372, `newRoom: global175`) resolves through the
game-wide fallback, whose values used to carry NO guard by design (rm205's dispatch raises
flag 449 on the very path to the movie). The value now carries what RIDES (`_rides`): the
register atoms on globals written by NEITHER the assigning script nor the reading one. Flag
449 drops (rm205 writes it); the day is written by nine scripts (17, 93, 180, 370, 480, 500,
550, 750, 800) and by no map and not the movie, so `day == 7` rides.

**Census, from the sim on the cached model (no src touched), then the red test.** Five icons
on the two maps override `select`, all day-tests: rm205 airport → 750 `day == 7`; grandma →
380 `¬g181 ∧ ¬(day ≥ 7)` (g181 has no writer: always 0); rm200 voodooShop → 250 `¬(day >
6) ∧ ¬g181`; voodooMus → 260 `¬(flag465 ∧ day 5) ∧ ¬(flag114 ∧ day 6) ∧ ¬(day > 6)`;
moonBeam → 290 `¬(day ≥ 5)`. Every other icon inherits `(return 1)`: unguarded, as before;
rm200 → 205 is named by two icons and drops its guard as before. rm372 → 750 rides `day ==
7`, → 380 rides grandma's, everything else free, the destination SET unchanged (19).
`src/test_icon_select_gate.py` pins all of it (13 green before the change on the unchanged
rows, 10 red on the new guards).

**Side finding, NOT built.** `(<= 7 gDay 10)` reads as `day ≥ 7` — `_cmp_atom` takes the
first two operands of an n-ary compare. Harmless here (the model's day never exceeds 9) and
permissive on a positive test, but the negated branch is STRONGER than the truth. Census of
chained compares: LSL2 3, KQ4 15, KQ6 70, so a fix is bless-gated; recorded, parked.

**Expected payoff (§1.37).** The any-day flights to Germany and Africa close at both hops:
the day-9 rows should vanish and R4's arm may fire (`reg286==[0]@seal123=4`); if it fires as
an rvs row rather than register_strandings, the oracle's R4 check changes its spelling.
Measuring: the icon test (a GK1 rebuild), then the suite on all six.

**MEASURED on GK1 (the oracle in the pre-change worktree vs the rebuilt model, row by row;
`snapshot.py gk1` times out at 30 min on this title and is not the instrument).** 33 rows →
41. The GK1 checks stay at the same four declared reds. ⛔ The prose was wrong and the
artifact right: the committed model's sketch rows were at days 5/6/7, NOT at day 9 (KNOWN_RED
and the 09-02 handoff said 9 — a simulated state that never shipped). The delta:
  * VoodooCode1's day-7 rows lose need site 260 — the voodoo MUSEUM icon closes after day 6
    (`voodooMus::select`), so on day 7+ the museum is not where the sketch is still needed.
  * reconVeve's `(123,257)=(0,0)` joint row — a day-0 flip — is gone.
  * braceMold and reconVeve gain a row at the 4→5 flip (they had 4, 6, 7): the same declared
    class (the item is consumed and its use site day-dead by the end of day 3; the flat model
    ends days through go-home's accumulate-only flag 65 — §1.29/§1.31's phantom).
  * TWO NEW ITEMS at the 6→7 flip, `crocMask` (21) and `oil` (22): bought TOGETHER at the
    voodoo shop (rm250 state 18 `get: 21 put: 30`, state 28 `get: 22` + flag 358), whose
    icon closes after day 6 (`voodooShop::select`, `(> gDay 6)` refuses) — so on day 7 they
    are unobtainable, and the maze (490, `has: 21`) and Napoleon's `useTheOil` (460, `put:
    22`) still name them. In the GAME day 6 ends only at the bayou ritual (rm480's `(++
    day)`, §1.34's unmodelled increment), which kills the maskless player (R5) — a maskless
    day 7 is unreachable. The MODEL ends day 6 through go-home's phantom, so these two rows
    stand on exactly the phantom the sketch's 6/7 rows stand on. Same class, declared; the
    §1.31+§1.34 round retires the whole family, and before the flights were day-tied the shop
    stayed open on day 7 in the model, which is why they were absent.
  * edge_strandings: the knife's row splits off on its own; crocMask and oil join the
    New-Orleans-items row (past the flight, none of them is obtainable — honest).
  * R4 does NOT fire: the day-7 tie closes the phantom flights, but the day-4 crosser is still
    blocked on once-only flag 65 (§1.29) — the next round, now unblocked on its prerequisite.

## §1.40 A handler's method send is a call: flag 268's writer captured (2026-09-03)

§1.35 named the capture class that parks icon presence and, behind it, §1.34: flag 268 (the
bayou icon) is raised only in `PhraseDisplay::checkPhrases` (drumInset.sc, script 815),
"two method sends deep from any handler the harvest walks". Re-read with the lifecycle in
hand, it is ONE send deep: `sGoToDrum@410` state 2 does `(global2 setInset: (ScriptID 815 0)
self global2)`, so script 815 is ScriptID-scoped into rm410 (`_scriptid_scope`: drumInset,
turnLeft/Right, the page prints — guard None) and the harvest already walks `drumInset::
dispose` as a handler (every own method but `init`/`changeState`); the system `Inset::
handleEvent` disposes the inset on the player's close click (Inset.sc:141-153), so `dispose`
is player-driven. What hid the write is that `dispose` reaches it as `(PhraseDisplay
checkPhrases:)` — a SEND to a class defined in the same script — and `_heffect` followed
`PublicCall`/`LocalCall` only. The model's probe: flag 268 = reg 510 had NO handler write,
no `reg_vals`, no `reg_dom` — the one presence flag in that state (101, 269 have handler
writers; 64/24/14/224 machine values).

**The rule (`opmodel._follow_send`).** A handler's same-script method send is a call: the
callee runs under the handler's path condition, so its writes are the handler's. Bounded and
derived: receiver `self` (the handler's own object, now threaded through `_hwalk`/
`_follow_call` as `owner`) or an object/class DEFINED IN THIS SCRIPT; selector one of the
target's OWN methods; never `init` (cast conditions) or `changeState` (machines); depth 3;
no recursion; the callee walks under ITS method's verb-param scope.

**Simulated first (monkeypatched `_heffect`, the cached model, no src touched):** re-walking
the inset's scoped handlers followed exactly `PhraseDisplay::checkPhrases`, `turnLeft::
dispose`, `turnRight::dispose` and produced 16 handler writes at rm410/815: **flag 268 := 1
under `¬opaque ∧ opaque⁴ ∧ ¬268`** (local0 == 2, count == 3, the three `oneOf` phrase tests
— the puzzle, honestly opaque), the score flag 388, the drum flags 346-349/469, and flag
220's cursor toggles. Static census of the class (same-script own-method sends whose callee
writes a global, depth 3): LSL2 15 / KQ4 20 / KQ6 48 / KQ5 21 / LB2 90 / GK1 37 — mostly
`Game::doit/newRoom`, `Dialog`, cursor plumbing in system scripts outside any scope; KQ6's
scoped hits (`PuzzleInset::doButton` → g110, `spellBookScr::dispose` → g5/10/32/72, Main's
save/restore → g19) write NO modeled register (`reg_dom` None for all six). LB2's largest
hit is `debugHandler`, already excluded.

`src/test_method_send_following.py` pins the writer (4 red before).

**And the rebuild stayed RED — the sim had bypassed the scope.** No handler row from script
815 existed at all, not even `dispose`'s own flag-220 toggle: the harvest never walks the
inset's methods. `_scriptid_scope` (extract's fourth scope) has 815 in rm410, but the
HARVEST's fourth scope is `armed_rooms`, built from two spellings only — `(x setScript:
(ScriptID s n))` (`mb.arms`) and `(<ScriptID obj> init:)` through `init_selectors` — and
`(gRoom setInset: (ScriptID 815 0) self gRoom)` is neither: the ScriptID is the ARGUMENT,
and it is `Inset::setInset`'s body that inits it. A THIRD arming spelling, derived from the
class table the way `init_selectors` is (`extract.client_arming_selectors`): a class method
that sends `init:` to one of its PARAMETERS passing `self` as the client. Census (KQ6/LB2/
GK1, every class): `Script/Game/Prop/Rgn/Conversation::setScript` `(param1 init: self
&rest)`, `Inset/Rm/Room::setInset` `(param1 init: caller self register)` — and `Game/GK/
Kq6::setCursor` `(param1 init:)` with NO client, which is the discriminator: a cursor is not
armed on anyone's behalf and the rule never names it. ScriptID sites through `setInset:`:
GK1 2 (rm410, the hounfour's script 900), KQ6 1, LB2 26 (its close-up insets) — so LB2's
harvest scope grows; the watched surface decides whether any row moves. The cast_refs scan
in `opmodel` now reads both spellings. Measured: 7/7, the writer at rm410 AND rm800 (the
hounfour's ceremonial-room script arms the same inset); committed `94c126a`.

**AND KQ6 MOVED — caught by reading the golden diff, not by the runner (2026-09-03).** The
suite agreed with KNOWN_RED by check NAME, but KQ6's golden diff carried a THIRD line beyond
the two declared: `dangerous: huntersLamp@rm240 -> 74 rooms` (was 3). Diagnosed with a
before/after harvest dump (2fb8a30's cache vs now): +214 handler writes on KQ6, 172 of them
ONE register (bit 2 of `global161`, the lamp's state mask) at script 907 = `KqInv`, the
INVENTORY — in all 86 rooms, under `own(huntersLamp) ∧ own(sacredWater)`: "use the sacred
water on the lamp" is a doVerb forwarded between two inventory items, so the follow re-
recorded the lamp's own write under BOTH item guards, and `real_uses` (which reads every
own()-guarded gating write as "the item is USED here") counted the lamp as used everywhere.
The icon-bar doctrine already says it: the scope is homed to every room, "keep the EFFECT,
drop the CLAIM", and the claim a handler may make there is its `doVerb` body. So the
following stops at that bound (`if script in self.global_homed: return`); every other scope
follows. Recorded gap, not touched: `real_uses` has no `global_homed` exclusion (a third
consumer of the doctrine, alongside `build_maps`' guard refusal) — adding it moves the blessed
KQ6 surface, a bless conversation. Lesson for the runner: a golden red that AGREES by name
can still grow a line; read the diff every run.

## §1.41 Icon presence, floored: the bayou exists only under flag 268 (2026-09-03)

§1.35's item (i), unparked by §1.40's capture. `_script_prop_values` conjoins a third
condition onto an icon-derived destination: the icon's PRESENCE, the path condition of the
`(container add: icon)` site(s) in the script (`_presence_guard`; several sites → the one
condition they agree on, else permissive). `rm205::init` adds grandma under flag 101, the
lake under 64, the bayou under 268, the airport under 269, gedde under 24, tulane under 14,
the French Quarter unconditionally; `rm200::init` adds the cemetery under 77, the police
lobby under 63, Cazaunoux under 266, the moonbeam house under 267, the rest in one
unconditional `add:`. The condition RIDES the movie hop like the day did (`_rides`: every
one of these flags is written by some other script).

**The floor (`_floor`).** A presence atom is only ever carried if the game can satisfy it:
an atom on a register NO SCRIPT WRITES (`_game_global_writes`, the IR-level census) that is
false at SCI's zero-init is dropped — carried, it would seal the destination for good, and
that is the model's ignorance (a writer it could not read), not a condition of the game.
Before §1.40 flag 268 was exactly that case at the MODEL level (an IR writer existed, deep in
the inset); the IR-level floor is the safety net for the next such flag, and `g181` (never
written, tested negatively by grandma and the voodoo shop) shows the harmless half: `¬181`
holds at 0 and is kept.

Pinned in `test_icon_select_gate.py` (the presence atoms on every gated icon, the ride on
rm372, and the floor on a synthetic atom). Measuring: GK1 rebuild, then the six-game suite
on the §1.40+§1.41 tree, then the GK1 row diff against `2fb8a30`.

**What presence does NOT buy, read ahead for §1.34.** The bayou now exists under flag 268,
and 268 is raisable at rm410 (and the hounfour) under the puzzle's condition — which is
OPAQUE to the model: `local0 == 2`, `count == 3`, the three `oneOf` phrase tests on the
inset's own locals. In the flat register model an opaque-guarded write is producible
anywhere its room is, so the bayou opens on day 1 there, exactly as before presence; rm480's
`(++ day)` (§1.34) would still fire on day 1. The game's own tie, read from the scripts:
`tom::doVerb` arms `sGoToDrum` on verb 18 = the DRUM BOOK's `message` (GKInvItem.sc:999) —
"use the drum book on the drummer" — and the book (item 14) is handed over at the start of
day 4 or 5 under flag 73 (startOfDay4.sc:422-487, startOfDay5.sc:602). So the honest window
is "day ≥ 4 with the book", two days early for a day-6 ritual, and the last two days live in
the phrases (message data, not structure). Two things follow: (a) the arming site's path
condition (`param1 == 18` → OWN(14) under the doVerb scope, then the machine's arm) is NOT
carried onto the armed script's handlers today — `armed_rooms` holds rooms, not guards, and
`_scriptid_scope`'s guards feed extract, not the harvest; carrying it is a general fix
(an armed script's handlers run under the arming condition) worth its own round; (b) even
with it, §1.34 cannot ship honestly: the bayou's day is in the puzzle's answer. §1.34 stays
PARKED, now for the right reason.

## §1.42 The topic-said array is a second flag store, and it is lowered now (2026-09-03)

The ten closure-arm rows §1.41 exposed (`register_value_strandings`, pattern
`producible-dead-end`: the day flips 2/6/8 with presence flag 63/64/66 at 0, flip 8 with 269)
trace, in the model's own guards, to DAY-1 CONVERSATIONS: flag 63 (the police lobby icon) is
raised by Grace's murder topic at rm50 under `178 == 2`; flag 66 by the sergeant's topic under
`178 == 6 ∧ ¬253 ∧ day ∈ {0,1}`; flag 64 (the lake) by the radio at rm430 on day 1 with 66
set; 269 by the travel agent's topic 44. Whether day 1 can END without them is decided by
Grace's topic list — the Teller dispatch — and its gates read through a store the model
never lowered. (`proc99_1`, which also raises 63/64/66/101, is the DEBUG day-jump in script
99 = `debugHandler`, correctly excluded.)

**The store.** `interrogation.sc` keeps the TOPIC-SAID array in the exact idiom of the game's
flags — a word array `global182`, bit `(>> $8000 (mod n 16))`: `proc50_5` tests, `proc50_6`
tests-and-sets (returns what it found), `proc50_7` tests-and-clears, `proc50_8` tests the
negation. 435 literal sites: every "second time you ask" (`(if (proc50_6 13) (++ iconValue))`,
215 sites as an `if` test) and every topic offered "iff not yet asked" (`showCases` pairs, 42
`proc50_8` arguments). `derive_flags` already saw it — its docstring names proc50_1/2 — and
kept only the MOST COMMON base, so the whole array read as opaque: R4's wall ("the topic-said
array ... not modelled") and the once-only go-home's third consumer.

**The rule.** `derive_flags` returns every store (`_classify_flag_store` per base; the primary
keeps `flag_synth_base`, the others come back as `extra`), and the build lowers each extra store
to its own synthetic block (`ir.extra_flag_stores`, rendered back through its own test proc).
Census over six games: LSL2/KQ4 none, KQ6/KQ5/LB2 ONE store each, GK1 TWO — so by
construction this moves nothing but GK1. The read-back writer is REWRITTEN EXACTLY where its
value is used (`_lower_tset_sites`): as an `if`/`cond`-arm test the test reads the OLD bit and
`(= g 1)` heads every arm that runs after that test (for a `cond`, this arm and all later ones
and the else — added when missing); as a bare statement it is the set; the 2 sites nested in
an `or` lower as plain sets (the write matters; the read stays opaque there).

**The declared red.** Every game's PRIMARY set proc returns the bit too, and the games use it:
set/clear calls in test position — KQ6 22 as an `if` test (24 with the two under an
`and`; `(if (not (proc913_1 5)) ...)`, "first time only"), LB2 8, GK1 3, KQ5 0. Under the plain reading those tests are opaque and the write
inside them invisible (a test is never walked). The same rewrite would capture them, and
capturing them moves the play-validated KQ6/LB2 surfaces — a bless. Gated to the extra stores;
`test_topic_store.py` keeps the red, KNOWN_RED names it.

## §1.43 R4's flat arm: the triple the joint chooser skips (2026-09-03, designed, not measured)

With the topic store lowered, Grace's "go home" (49) is still offered on `(proc50_2 65)` alone
— flag 65, the main store — and the topic-said array never clears (one `proc50_7 95` in the
game), so §1.42 does not touch R4's flat-arm wall (§1.29): in the day counter's projections
go-home ends any day, because the projection that sees the day-end flag (the joint `(123,
257)`) does not see flag 65 (reg 307), whose value "1" is reachable once and stays reachable
forever in an accumulate-only set. `_gate_joints` KNOWS the tuple — its docstring names
`(123, 15, 65)` as "the tuple that sees the day end exactly" — but its loop `continue`s when
the pair closes the cycle (flag 15's arms are day-conditioned, so `(123, 257)` closes it) and
never reaches the third register. The 2026-08-28 note that justified it ("triples beside a
closing pair are redundant") predates the handler co-writes (5db647a) that record go-home's
`307 := 0` — the spend the triple would carry: day 1 raises 307 (rm470's day-gated cutscenes),
go-home clears it with the day-end, no raise is live on day ≥ 2, so days 2-5 must end through
`endDay`'s evidence arms and the day-4 flip becomes the point of no return R4 claims.

Design: keep the pair, and ALSO add `(A, B, C)` when B's write depends on C and C's write
depends on A. **SIMULATED AND DROPPED (2026-09-03):** the triple the rule finds on GK1 is
`(123, 178, 257)` — the conversation register, not flag 65: `307 := 1`'s branches carry no
day DEP at all (the lake's cutscene is day-1-only by REACHABILITY — the lake exists only
through the radio, the sergeant, and Grace's day-1 topic — not by a register it tests), so
no joint over registers can see it. The flat arm cannot carry this; the closure arm is the
instrument, and §1.44 is its missing check.
## §1.44 A crossing must be producible under the value it carries (2026-09-03, simulating)

The ten closure-arm rows, read to the bottom in game terms. Flag 63 (the police lobby icon)
is raised by arm 78 of Grace's Teller — the FOURTH press of her topic 26 on day 1 (`(cond
((== gDay 1) (proc50_8 5)) ...)`, the asked-bits 2→3→4→5 chain, grace.sc:150-214) — after
`interrogateGrace` has set the conversation register (178 := 2, bookstore.sc:1114, the only
writer of that value). Flag 66 is the sergeant's day-0/1 topic; 64 (the lake) the radio on
day 1 with 66; 269 the travel agent. So the closure is structurally RIGHT that none of them is
producible after day 1 — and the rows are still false, because DAY 1 CANNOT END WITHOUT
THEM: "go home" (topic 49) is offered on flag 65 alone, 65 is raised only by rm470's
cutscenes, rm470 is the LAKE, and the lake exists only through the radio, the sergeant and
Grace's fourth press. `_staged_pre` builds the crosser's world stage by stage and SEEDS each
next day from the previous stage's values with the step's co-effects applied — it never asks
whether the step itself has a live producer under `confine_extra`. The seal arm then adds
`R := w` by hand ("the crosser stands at w") and finds, correctly, that the far side cannot
produce the flag: a true statement about a player who cannot exist.

**The check (general, the closure's `_flip_live`).** At every stage j of a confined PRE, the
step j→j+1 must have a producer LIVE in that stage's closure: a `_wbranch[(C, room, j+1)]`
branch at a room the closure reaches whose every dep value is in hand under the confinement.
None → the crossing is impossible for a player carrying that value → no row. Sound in the
usual direction: the stage closure over-approximates, so a step it cannot produce, the game
cannot either. Applied to both the confined and the unconfined crosser of the seal arm (a
flip nobody can take is not a seal); `_consumer_windows` keeps the unchecked seeding (its
callers read the windows permissively). Simulated first (`sim_stepcheck.py`: the day-2 flip
with 63 = 0 and with 64 = 0, the day-8 flip with 269 = 0, and the unconfined day-2 control).

**The triple joint (§1.43) is not this.** Flag 65's raise has no day DEP — the lake is
day-1-only by reachability — so no register joint sees it; only the closure does.

**SIMULATED (loaded model, seconds per case).** The first cut checked only the stages BELOW
the crosser's day and let the flip itself through — the very step the arm adds by hand — so
all three cases "stood". With the flip step checked: the day-2 flip carrying flag 63 = 0 has
NO live producer (day 1's end needs the day-end flag, whose only day-1 producer, go-home,
needs 65, which needs the lake, which needs 63) — the row retires; likewise flag 64 = 0. The
unconfined control crosser ends day 1 through rm370 as it must. The day-8 flip carrying
269 = 0 STANDS on this check: its stages 1..7 and the flip are live through rm370's increments
with the day-end flag in hand — the §1.34 family (the record's day-7 ending is a phantom;
rm480's increment is unmodelled), not a crossing question. Built as `_step_live` +
`_staged_pre(require_steps=True)`, pinned by `test_crossing_producible.py`; measuring with the
rvs probe and the suite.

## §1.45 A counter step's own co-writes are necessary co-effects (2026-09-03, simulating)

Probed after §1.44: every branch of GK1's day step at rm370 (`graceComeOut` states 5/101,
`phoneCall`, `day5MaliaCall`) co-writes `(257, 0)` — `(proc13_2 15)`, the day-end flag
cleared before `(++ day)` — and `_step_neco(123, k, k+1)` returns `{}` for every k ≥ 2: it
intersects the co-writes of the DEP producers (the arms that raise flag 15 co-write nothing
in common) and never reads the step's own. So flag 15, once raised, stays in the staged PV
forever, and every later day ends "for free": §1.29's accumulate-only phantom, one register
short of where §1.31 stopped (flag 65's spend IS read — through go-home's co — because
go-home is a dep producer). The same reading applied to the flip the seal arm takes by hand
(`R := w` with no co-effects) lets the far side keep the flag it just spent.

**The rule.** neco(k→k+1) also includes the intersection over the step's live branches of
THEIR co-writes (a branch that lacks a write does not make it necessary), and the seal arm
applies neco(w−1→w) to the crosser's PV and confinement at the by-hand flip (`_apply_neco`),
exactly as `_staged_pre` does between stages. Expected on GK1: day k's end must be produced
anew at every stage — by that day's `endDay` arm — so the day-4 crosser without flag 44's
chain cannot end day 4 (R4 fires in the closure arm), and days 6/7, whose endings the record
lacks (§1.34), refuse every crosser (the airport row retires as "nobody crosses"). Measured
first on LB2's act counter (the user-ruled snake-oil row must survive) and the goldens.

**SIMULATED — and the first cut deadlocked itself.** With flag 15 cleared between stages,
the day-2 stage could not even WRITE the counter (`(++ day)` runs under flag 15, the gate
the step just spent), so nothing gated on "day > 1" fired — the drummers' flags 231/232 that
day 2's ending demands — and the staged PRE died at day 2 for every crosser, confined or
not. The step's PRIMARY effect must be seeded too: `pv[C] |= {j+1}` at the stage boundary,
the crosser took the step (the seal arm already does this for the flip by hand). With that,
the stages run through every day: 2, 3, 4, 5 end through their `endDay` arms with flag 15
re-produced each day — and 6 and 7 end too, which the next trace examines (the record's only
day-6/7 endings were go-home's phantom and the bookstore's arms).

## §1.46 R4's chain, traced to the bottom: the murder photo has no source (2026-09-03)

With §1.45's honest day endings, the seal arm's UNCONFINED day-4 crosser cannot reach the goal
either, so the record cannot produce day 4's ending at all. Traced link by link with the
tracer (`sim_why.py`, over `_wbranch` in the staged closure): day 4's `endDay` arm costs the
tattoo trace (item 26); the trace is granted by `sTraceTattoo@450` under flags 74 and 322;
flag 74 is Crash's topic (crash.sc:82); Crash's topic is a follow-up of flag 44's chain;
flag 44 is Cazaunoux's topic 54 (hartridge.sc:257), a follow-up arm reached only through
asked-bits 240 → 262 → 263 (visible since §1.42); bit 240 is set in NPC 40's interrogation
(rm340 sets 178 := 40) under flag 42; flag 42 is raised at the voodoo shop by showing the
MURDER PHOTO (item 1); and the murder photo is granted by OPENING ITS ENVELOPE —
`phoEnvelope::doVerb 6` says its line with `self` as caller, and `cue` does `put: 0`, `get: 2`,
`get: 1` (GKInvItem.sc:1337-1357). Two general gaps stood in the way:

1. **`inventory_scripts` kept the plurality holder.** GK1 declares 52 items in `tile1.sc`
   (24) and 30 in `GKInvItem.sc` (15 — the `Inv` instance and the item class), so script 15
   was homed nowhere (`armed_rooms[15] = None`, 0 handler rows) and thirty items' handlers were
   never walked. Every non-room script that declares items is the scope now; the stray-item
   worry is the room test. Census: every other game declares all its items in one non-room
   script — unchanged by construction.
2. **The icon bar's gets are placeless conversions.** The scope's doctrine refused every item
   transfer as a room fact ("the icon bar has no place"), which is right for drops and for
   requirement evidence and wrong for a GET whose only cost is the container: opening the
   envelope hands over the photo wherever the player stands. Recorded as `inventory_gets`
   (script, item, guard), reached also through the doVerb's self-callback into its own `cue`
   (`_follow_self_cue`, gets only — the KQ6 lamp lesson keeps writes out), and taken by the
   closure anywhere (`gets` rows with room None). The flat `sources` are NOT fed (a later,
   separately measured step). The wallet's master card (71, §1.37's parked grant) is the same
   class and lands with it. Census of the class: KQ6 `clothes::doVerb get 4`, `ribbon::doVerb
   get 16` (closure sources it did not have; the golden decides), KQ5 `Pouch::doVerb get 14`,
   GK1 the envelope's two photos and the wallet's card; LSL2/KQ4 declare in Main and are
   untouched.

## §1.47 R4 CAUGHT — the closure arm sees the day-4 crossing without flag 44 (2026-09-03)

The rvs probe after §1.46 (66 min): `(123, 4, 286, [0])` — crossing into day 4 carrying flag
44 = 0 is a producible dead end: day 4's `endDay` arm costs the tattoo trace, the trace needs
Crash's topic (flag 74), Crash's topic is a follow-up of Cazaunoux's topic 54 (flag 44), and
nothing after day 3 can raise 44 — while the unconstrained crosser reaches the goal. Three
rounds made it visible: §1.44 (a crossing must be producible under the value it carries: the
nine presence rows were players who never existed), §1.45 (the step's own co-effects: flag 15
no longer accumulates, so day 4 must end through ITS arm), §1.46 (the murder photo's source:
the icon bar's placeless gets and the two-script inventory scope — the root of the chain). At
the same flip the probe reports one row per LINK of the chain — flag 42 (the photo shown at
the voodoo shop), the Cazaunoux (266) and Tulane (14) icons, the asked-bits 240/262/263, bit 7
— the same dead end seen at each step; a collapse by sealed region would name the root once.
The airport row `(123, 8, 511, [0])` stands on §1.34's phantom day-7 ending.

**The oracle's spelling.** `register_value_strandings` takes an hour on GK1, so the R4 check
reads `producible_seal(123, 4, 370, flag44, 0)` — the seal arm's per-case body (`_seal_case`,
which the detector itself now calls) with the detector's own forward-reachable day set and
the unconfined control — in seconds. R4 leaves KNOWN_RED. The GK1 oracle stands at R2, R3,
R4, R5 caught, R1 retired (the sketch is forced by day 4's own ending).

## §1.48 The closure as a second opinion on the flat day-flip rows (2026-09-03, simulating)

The three GK1 reds left are one family: `register_strandings`' day-flip rows for the sketch
(days 5/6/7), the mold and the veve (days 4-7), the croc mask and the oil (day 7) — each
"obtainable before the flip, needed after, and the item-less player can reach the flip". The
last clause is `_flip_live`, asked of the flat projections, which carry one register each and
answer permissively: the flag that ends a day is "ever raised" in every projection that does
not carry it, so every day flip is reachable without every item. The staged closure
(§1.44-1.46) is the reading that knows better — it ends each day through that day's own arm
with the crosser's holdings. Asked with the item BANNED (`_staged_pre(..., require_steps,
ban={item})`: its grants and gets filtered out of the closure tables, so `own(item)` never
satisfies), a day whose ending demands the item cannot end, and the flip is no point of no
return for it: the day system prevents that stranding — the USER's words for GK1. Expected:
the sketch's rows (day 4's arm demands flag 248, raised only by showing it), the mold's and
the veve's (day 3's arm) retire as derived FPs; the mask's and the oil's (day 6's ending is
the record's phantom, §1.34) stand until the bayou's day is derivable. Scalar counters only.
Exposure: KQ4's day clock and LB2's act counter are counters — their flip rows (the pouch and
the pole; the act rows) face the same question; a retirement there is a bless (LB2's pressPass
act-1 rows are the one the USER already predicted, [[lb2-pass-necessary-for-act1]]).

**SIMULATED — three findings before it held.** (1) `_step_live` read a step branch's register
deps and ignored its item COST; honoured now (the closure's own `mu <= items`). (2) The flip's
step at rm370 costs nothing itself — it needs flag 15 — and flag 15 was being raised at stage
3 by DAY 2's ending arm, because a stage confined the counter to "at most j" and PV keeps the
earlier values: an arm gated on `day == 2` fired on day 3. The stage confinement is EXACTLY j
now (the crosser is on day j; a write gated on an earlier day cannot fire). Under exact
stages the control crosser ends days 1-4 through their arms and R4 still fires; days 6-7 have
no ending in the record (§1.34), so no crosser reaches day 7 there. (3) Therefore the rule
retires a row only when the item is THE DIFFERENCE: the unbanned crosser takes the flip and
the banned one does not. Verdicts: the sketch into days 5/6 → FP (day 4 ends only by showing
it); the veve and the mold into day 4 → FP (day 3's arm); the croc mask and the oil into day
7 → the row STANDS (nobody reaches day 7 in the record — §1.34's gap, not the item's). R1's
retirement is now the tool's own derivation.

**MEASURED (7f465de).** GK1's scalar rows: the sketch's 4→5 and 5→6, the mold's and the
veve's 3→4, 4→5, 5→6 are GONE; every item's 6→7 row stands (nobody reaches day 7 in the
record) and so does R1's check, now declared on that gap alone. The suite: exactly the
declared fifteen — LB2's act rows and KQ4's day-clock rows did not move. The closure-arm probe
runs in 26 minutes under exact stages (66 before) and reports six rows: R4 and its chain
links (flag 42, the Tulane icon, the three asked-bits); the airport's day-8 row and the
Cazaunoux icon's are gone — nobody reaches day 8 in the record, so no seal. The JOINT twins
of the retired scalar rows ((123, 257) at the same flips) get the same second opinion next.

## §1.49 One story, told once: the closure arm's chain rows collapse to their root (2026-09-03)

After §1.48 the closure-arm probe reports six rows for the day-4 crossing — flag 44 and every
link that produces it: asked-bits 263, 262, 240, flag 42 (the photo shown at the voodoo shop),
and the Tulane icon's flag 14 — each "carried at 0 into day 4, the goal never enters the
closure". They share the crossing and the sealed region: one finding seen at each link.
`_collapse_value_chains` groups rows by (register, value, sealed region), reads the links'
dependencies out of `_wbranch` (S depends on T when a producer of an accepted value of S names
T among its deps), keeps one row per ROOT — a link no other link in the group produces, the
earliest thing the player failed to do — with `chain` = the links downstream in dependency
order, and leaves independent roots as separate rows (the Tulane icon is its own story beside
the photo's). Pure post-processing before `_collapse_value_flips`; `test_value_chains.py` pins
it on synthetic rows. Exposure: a golden with several closure-arm rows on one crossing would
collapse too — the suite decides.

## §1.50 An armed object is present under its arming condition (2026-09-03, designed)

§1.41's tail named it: the drum inset's handlers — the only raise of the bayou icon's flag 268
— read as available wherever rm410 is, because `armed_rooms` holds rooms and not guards. The
presence table already exists for the receiver-side spelling: `MachineBuilder.foreign_inits`
collects every `(<ScriptID obj> init:)` with its path condition conjoined with the calling
room, and `cast_conditions` turns it into the object's cast guard, which the harvest applies
as the scope guard `og` of the object's handlers. The argument-side arming
(`client_arming_selectors`, §1.40 — `(gRoom setInset: (ScriptID 815 0) self gRoom)`) now
feeds the same table with the same claim: the inset is PRESENT under that site's condition.
For the drum inset the site is `sGoToDrum` state 2, whose machine is armed from `tom::doVerb
18` — "use the drum book on the drummer" — so the cast guard folds the machine's entry guard
(`machine_guard`, the existing callback) and every raise of 268 carries own(14). The bayou's
day is still the puzzle's answer (§1.41), but its floor is honest now: not before the book.
Exposure: KQ6 has one `setInset:` site, LB2 twenty-six (its close-up insets gain their rooms
as presence); the suite decides, and LB2 is reported row by row if it moves.

**BUILT, MEASURED INERT, REVERTED (2026-09-03, the same night).** The recording works —
`foreign_inits[815]` gains `('drumInset', 'init', 11==410)` — and NOTHING moved: GK1's rows
byte-identical, five surfaces unchanged, and the test asserting own(14) on flag 268's raises
FAILED. Two reasons, both general and both worth their own round:
  * **the guard is an OR over sites, and one site is unresolvable.** Script 815 is armed
    twice: `sGoToDrum@410` (a room, so `11 == 410`) and `sCeremonialRoom` (script 900, a
    CUTSCENE script — not a room, so the existing rule contributes None, "a scope with no room
    cannot say where you are"). `cast_guard` is `any_guard` over the sites, so the None wins
    and the object is present always. The cure is to resolve a non-room caller through the
    rooms that arm IT (`mb.arms`, the same transitive walk `opmodel.armed_rooms` already does)
    — until then the ignorance floor is doing its job.
  * **the arming MACHINE's entry guard never joins.** `_cast`'s `machine_guard` callback
    resolves an object armed by a machine in its OWN script; a cross-script arm consults
    nothing, so `_entry_guard[(410, 'sGoToDrum')] = own(14)` — already computed — is not
    conjoined. It cannot be done where `foreign_inits` is built (`__init__`, before the
    entry guards exist); the site must record its enclosing (script, object) and resolve
    lazily in `_cast`.
Neither blocks anything today: the bayou's day is the drum puzzle's answer either way (§1.41),
so this was never §1.34's blocker. Reverted rather than shipped inert with a red test.

## §1.51 §1.34 UNPARKED: its two blockers are cured (2026-09-04, measuring)

The day increments the model never had (§1.34: `(++ day)` in rm480, rm500, rm550 — the bayou
ritual, Germany's departure, the dream — dropped because those scripts never COMPARE the day,
so `_glob_domains` returned {}) were reverted on 2026-09-02 for two reasons, and this session
cured both:
  * **the any-day flights** (§1.35's diagnosis: rm480's new increment fired at day 3 because
    Germany was enterable on any day) — the airport icon's `select` ties the flight to day 7
    (§1.39) and the map icons carry their presence (§1.41);
  * **the phantom endings** (a day ended for free because flag 15 accumulated) — the step's own
    co-effects clear it and the stages are confined to exactly their day (§1.45, §1.48).
So the fallback ships as designed: an incremented global whose SCRIPT-LOCAL literal domain is
empty falls back to the GAME-WIDE literal range (every integer between the smallest and largest
literal the game compares or assigns it), each fanned branch an ORDERED step `k → k+delta`,
bounded at 64 values (past it the increment is dropped exactly as before). Static blast radius,
re-stated: LSL2 9 sites, KQ4 9, KQ6 1, KQ5 8, LB2 10, GK1 3 — and the 2026-09-02 measurement
found all five games byte-identical (the shovel counter, the snake oil, the scores, KQ6's 153
inert), which this run re-measures.

Expected on GK1: days 6→7→8 gain real producers, so the closure's second opinion (§1.48) can
finally judge the day-7 rows.

**MEASURED AND REVERTED AGAIN (2026-09-04) — and the real blocker is now named.** It made GK1
strictly worse: **R4 DIED** (the day-4 crossing without flag 44 reads "not a seal"), all six
§1.48 pins failed, and every row moved a day EARLIER (the mold and the veve to day 3, the
sketch to day 4, the mask and the oil to day 6) — §1.35's symptom again, with the flights
already tied. The reason is not the flights and not the endings: **an increment with no
evidence demand is a FREE day-ender.** rm480's `(++ day)` costs nothing but standing in the
bayou, and the bayou is reachable early (flag 268's raise is the drum puzzle, opaque), so with
the increment modelled a player ends any day by walking there — and every fact §1.45 and §1.48
rest on ("day k ends only through its own `endDay` arm") collapses, taking R4 with it.

So §1.34 and the closure's second opinion are in DIRECT tension, and §1.34 loses: the arms are
the game's real day structure, the ritual's increment is the game's real one too but its DAY is
knowledge the record does not carry (§1.41: the phrases). Shipping §1.34 needs the bayou's day
first, in this order: the drum book's own day gate (own(14) at the arming, §1.50's blocked
half), then the phrases. Until then the day-7 rows stay, and R1's check stays declared on this
gap. The apply script is `apply_134.py` in the session scratchpad; the tension is the thing to
remember, not the patch.

## §1.52 sVoodooCode's FP: the premise checked out, MY FIRST TWO DIAGNOSES DID NOT (2026-09-04)

The FP row: `register_strandings`, flag 246 (reg 488) flips to 1 at **rm302**, and item 33
(`sVoodooCode`, the second tomb sketch) is sourced ONLY at rm300 and still needed at 240/260/300
— so the flip reads as a point of no return for it. In the game it cannot be: rm302 is the
tomb-code inset, its only entrance is rm300's `sGoToCode`, and all FOUR arming sites
(rm300.sc:955, 1107, 1163, 1350) carry the SAME conjunction — `¬flag246 ∧ flag249 ∧ has:32 ∧
has:33` — so whoever flips 246 holds both sketches. That much is confirmed against the scripts.

**⛔ Two diagnoses I wrote here earlier were WRONG, both refuted by probing the loaded model:**
1. *"rm302 has a phantom in-edge from rm50."* It is not a phantom. `cs_edges` gives
   `50 -> 302 guard=12==302 via='roomScript'` — a RETURN-TO-SENDER edge, correctly guarded on
   prevRoom, one of 20 such edges out of rm50. You can only take it having already been in 302.
2. *"the arming's cost does not cross the `newRoom`."* It crosses. The flat edge
   `300 -> 302` is `via='sGoToCode'` and its guard is an OR of the arming alternatives, EVERY
   one carrying `own(32), own(33)` (and own(44)); `entry_musts(sGoToCode)` is `{32, 33, 44}`
   at all eight states. The model knows the demand.
   (The "cost does not cross" wording came from KNOWN_RED's older text and I repeated it
   instead of checking — [[re-derive-a-reds-premise]] exists for exactly this.)

**A third claim of mine was also unfounded**: I read `guard_required[(300,302)]` as `None` and
concluded the demand rode neither edge. `build_maps` does not key `guard_required` by edge
tuple, so that probe asked a malformed question and the `None` meant nothing.

**What is actually true, and where the diagnosis now stands.** `_wbranch[(488, 302, 1)]` still
has both its branches at `deps={} COST=[]` — the WRITE carries no cost even though the ROOM is
gated. So the open question is not the movement graph but `register_strandings`' own liveness
test: with the demand present on the only real in-edge and `entry_musts` naming both sketches,
why does the row survive `_flip_live`? Next step is to read that flow rather than infer it —
the three wrong calls above were all inference where a read was cheap.

## §1.53 A self-return is not a first entrance (2026-09-04)

§1.52's diagnosis, finished by reading the code instead of inferring it. `register_strandings`
DOES ask whether the item-less player can reach the flip (`_flip_live`, and item 33 is in the
`priced` set so the ban applies) — and the answer came back YES for rm302, which is the whole
bug. Probed: `_walk(488, banned={33})` reaches rm302 at flag 246 ∈ {0, 1}.

**Why.** rm50's `roomScript` ends `newRoom: global12` — return to sender — and the destination
fan gives it twenty edges, each guarded `prev == <that room>`, one of them `50 -> 302` with
`req {12: [302]}`. In the projection that TRACKS prevRoom that guard is enforced and the walk is
right. In the scalar projection over flag 246 — the only one tracking it — prevRoom is
unconstrained, so the guard reads as satisfiable and the edge becomes a free door INTO rm302,
whose only real entrance (`sGoToCode`) demands own(32) ∧ own(33). Hence a sketch-less player
standing in the tomb-code room, hence the flip looking avoidable, hence the FP.

**The rule.** An edge `a → b` whose guard NECESSARILY demands `prev == b` is the return half of
a round trip: taking it presupposes having stood in b. So it grants no FIRST entrance to b, and
`_flip_live`'s walk drops it (`_walk(..., no_self_return=True)`, threaded to `_psucc` and
`_psucc_joint`, in the cache key). Derived: the register is `em._prev_reg`, never a literal;
the value set must be exactly `{b}`; and the drop is skipped in any projection that carries
prevRoom itself, where the guard already does the work.

**⛔ Scoped deliberately.** Only the first-entrance question asks it. Dropping self-returns in
the ordinary walk would SHRINK the reachable set, and a smaller reachable set INVENTS
strandings — the unsound direction. `test_self_return_entrance.py` pins both halves: the
sketch-less player can no longer enter rm302, and a player banned from nothing loses no room.
GK1 has 30 self-return metas of 284; the rule is inert wherever prevRoom is tracked or the
guard is not exactly the destination.

**MEASURED (the full gate, 8 cores, 13.6 min): 961 passed, 14 declared reds, 0 unexpected, 0
crashed.** Goldens and LB2 unmoved (no `DECLARED RED MOVED`, so their diff lines are exactly the
blessed ones). Two GK1 payoffs, one of them unlooked-for:
  * **sVoodooCode's FP is GONE** — the FP list drops from 7 units to 6.
  * **R1's check WENT GREEN and is promoted**: with self-returns refused, VoodooCode1 has no
    day-flip row at all, so the USER's 2026-09-02 ruling ("day 4 cannot end without showing
    Magentia the sketch") is now derived end to end rather than declared. GK1's oracle is
    11 passed / 2 failed.
  * Side effect worth noting: `test_gk1_ground_truth` fell from 738 s to **211 s** — refusing
    twenty phantom doors shrinks every walk that passes through rm50.

The two reds left are the same FP pair seen from both sides, over five items: the day-7 family
(sketch, mold, veve, mask, oil — all waiting on the bayou's day, §1.51) plus the USER-ruled
knife and the talisman.

## §1.54 The talisman: verified FP, and DELIBERATELY not cured (2026-09-04)

The last unblocked FP unit, run to ground and then left alone on purpose.

**The row.** There is exactly one, and it carries six of GK1's remaining FP units at once:
`edge_strandings from_room 455 to_room 800, items [21, 22, 32, 38, 40, 60, 69]` — the crossing
from the confessional into the hounfour, claiming crocMask, oil, the sketch, the veve, the mold,
the rod and the talisman are all unobtainable past it while still needed. The ROD half is real
(it is R2's own mechanism: `rm455.sc:827` deposits it, `bench1::doVerb 76` under flag 272,
raising flag 280). Five of the other six are the day-7 family, blocked on §1.51.

**The talisman half, verified from the scripts:** granted at `rm720.sc:1040` and `:1281`, each
immediately before `newRoom: 216` — both of Africa's real exits — and never taken back before
`EndGame.sc:1940`. The third `newRoom` out of rm720 (`askWolf`, line 1025) goes to rm50, the
CONVERSATION room, and returns; it is not an exit. So nobody reaches the hounfour without the
talisman, and demanding it at the crossing is vacuous.

**⛔ Why it is not cured.** The natural cure is `_unrefusable_grants`, and that rule is
deliberately STRICT: the grant must sit in a room's `init` with the guard's whole conjunct
spine being the `not (has: X)` idempotence check. Its docstring states the reason — "the
failure direction here is LOST FINDINGS (a barrier shrinks `_reach_without`, and a room dropped
from it is a room no detector will judge)" — and records that the looser reading was measured
on 2026-08-15. GK1's grant is unconditional inside a CUTSCENE STATE, not a room init, so
admitting it means relaxing a measured-strict rule that protects real findings, to retire ONE
unit of six on the game whose oracle is my own derivation. Both red checks stay red either way,
because the day-7 family keeps them red.

**If it is ever built**, the honest shape is narrower than relaxing the strict rule: an
EXIT-PATH grant — every edge leaving a region passes through a state that unconditionally
grants X, so no player leaves the region without X. That is provable here (two exits, both
granting) and does not touch the room-init rule. Recorded, not built.

## §1.55 The bayou's day IS derivable — and §1.34's real blocker, finally named (2026-09-04)

⛔ **ITS CONCLUSION IS SUPERSEDED BY §1.56** (2026-09-05): the chain traced below is right and
still stands, but `fwd` is NOT the blocker — the live-step fixpoint this section proposes was
built and measured as a NO-OP. Read §1.56 for what actually kills R4.

⛔ **My "the record does not carry the bayou's day" was WRONG** (the USER pushed back; they were
right). Every link is a plain register fact in the scripts, and the model already holds all of
them:

| link | where | the model's own record |
|---|---|---|
| the ritual advances the day TWICE | `bayouRitual.sc:890` (roomScript state 81) and **`:911` (`abortCartoon`)** | two write branches at room 480 |
| the main path demands mask + tattoo | §1.36's doomed-arming rule | `deps {flag216:[1], flag299:[1], g123:[k]}` |
| **the ESC "skip this cutscene?" path is the free day-ender** | armed from `roomScript::handleEvent` under `local4`, `proc13_5` = the yes/no dialog | `deps {flag971:[1], g123:[k]}` |
| but the skip only opens at **state 13**, past the deaths at 5 and 9 | `bayouRitual.sc:207` | local4 is lowered to register **1213** (= "flag971"), and `_wbranch[(1213, 480, 1)]` = `deps {flag216:[1], flag299:[1]}` |
| and the tattoo is day-gated | `bookstore.sc:1899`, armed under `(== global123 6)` | a plain register dep |

So the chain closes: **day ⟸ 1213 ⟸ (216 ∧ 299) ⟸ day 6.** Nothing needs hand-carrying, and
`apply_134.py` is NOT the problem.

**MEASURED with §1.34 applied on top of everything from 2026-09-04 (the morning attempt
predated §1.53): R4 STILL DIES, and R1 with it.** 9 passed / 4 failed. So the third revert
stands — but the cause is now named rather than guessed:

⭐ **`producible_seal` computes `fwd` — the day values forward-reachable from the crossing —
straight off `_rstep`, with no liveness test.** Adding the bayou's steps grows `fwd`, the
post-flip confinement `conf_post[R] = set(fwd)` widens with it, the post-flip closure roams
days it could never actually reach, finds the goal, and the seal dissolves. The flat
projections have the same shape one level down: `1213 != 0` reads satisfiable wherever 1213 is
untracked — the SAME defect class as §1.53's self-return, in a different costume.

**THE NEXT FIX, shaped:** `fwd` must be built from LIVE steps only — a step counts only if its
deps are producible in the crosser's own closure, which is exactly what `_step_live` (§1.44)
already asks between stages. Doing it naively is circular (fwd feeds the closure that would
judge it), so the honest shape is a fixpoint: start from `{w}`, admit a step whose deps the
current stage's PV can satisfy, re-close, repeat. ⛔ Cost warning: with §1.34 the GK1 model
REBUILD alone runs ~55 min (the day fan multiplies machine states), so this is a box job, and
each iteration is an hour.

## §1.56 `fwd` was NOT the blocker — the day's clear was (2026-09-05, measured)

⛔ **§1.55's conclusion is WRONG, and this section replaces it.** It named `producible_seal`'s
`fwd` — "the bayou's new steps enlarge `fwd`, the post-flip confinement widens with it, the
closure roams days it could never reach" — and shaped a live-step fixpoint as the next fix.
Both halves were inference where a read was cheap, which is the same failure §1.52 recorded
three times in one day. Read instead:

**1. The proposed fix is a NO-OP, and was measured as one before anything was built.** For the
day-4 crossing at rm370 the live-step fixpoint returns exactly the structural answer:

    CURRENT fwd: [4, 5, 6, 7, 8, 9, 10]     LIVE fwd: [4, 5, 6, 7, 8, 9, 10]
      iter 1  fwd=[4]              38 rooms, goal False   admit 4->5..7->8 @rm370 (deps 257=1)
      iter 2  fwd=[4,5,6,7,8]      51 rooms, goal False   admit 4->9 @rm750 (deps prev=500), 4->10 @rm750 (deps {})
      iter 3  fwd=[4..10]          54 rooms, goal True

**2. `fwd` could not have been the cause anyway.** It is already saturated: `reg_vals[123]` is
`0..10` and `fwd` holds every value at or forward of `w`. §1.34 widens the literal range by one
(`0..11`), so its whole effect on `fwd` is the value 11, which gates nothing.

### What actually kills R4 under §1.34
`_step_neco(123, 3, 4)`, read on both models:

    without §1.34:  {257: 0}
    with    §1.34:  {123: 1, 179: 70, 545: 0, 1215: 1}

Three separate things are wrong there, and only the third is still open.

⭐ **(A) A step's co-effects are what it does to OTHER registers.** `_step_neco`'s own-co-writes
half already says `if R != C`; its dep-producer half did not, so `C` came back as its own
necessary co-effect — GK1 reads `_step_neco(123, 0, 1) = {123: 1, ...}`, "to advance the day
from 0 to 1 the day must become 1". Harmless at `0 -> 1` and fatal anywhere else, because
`_apply_neco` writes the answer as `pv[R] = {v}` AFTER the seal arm has seeded `pv[C] = {w}` by
hand. The crossing was erased, `allowed(123) = {1} ∩ {4..11} = ∅`, the crosser could not leave
the flip room, and the arm read "the flip dooms everyone: not S's fault" and emitted NOTHING —
which is why R4 and R1 both died at once. [[same-rule-two-places]], inside one function.

⭐ **(B) A dep the zero-init already satisfies has no producer.** `_value_neco` intersects the
co-writes of every recorded producer of `S in vs` — sound only if the player must have run one.
Registers are zero-init here (`pv.get(reg, {0})` is the closure's floor, §1.41's reading), so a
dep admitting 0 is satisfied by never writing `S` at all. GK1's specimen is flag 470, a PLATFORM
test the bayou and dream scripts spell BOTH ways (`(if (and (== (Platform) 1) (not (proc13_0
470))) ...)` against `(if (proc13_0 470) ...)`), reaching the branch table as `deps {712: [0,1]}`
— the register's whole domain, establishing nothing. Read as a demand, its "producers" are the
game's opening at rm93, and the opening's co-writes (`global123 := 1`, `global179 := 70`) were
handed back as facts about a day-4 crossing. That is where the `123: 1` in (A) came from.

Both cures only ever REMOVE entries from a map applied as `pv[R] = {v}`, so both WIDEN the
modelled player: the sound direction. Both landed with `test_step_coeffects.py`, red-proven at
`8ca65a0` (2 of 6 checks fail there).

### ⛔ (C) THE BLOCKER THAT REMAINS: the fan itself, and rm550 is the specimen
⚠️ **An earlier draft of this section blamed the lost day-end clear and was REFUTED by its own
probe** — the fourth wrong diagnosis in this line, and the reason every claim below is a
measurement. The clear IS lost, and that is real; it is simply not sufficient.

With (A) and (B) cured the neco reads `{545: 0, 1215: 1}` — and **`257: 0` is gone**. That entry
is §1.45's landing: every one of rm370's five day advances does `(proc13_2 15)` first, so the
step CLEARS the day-end flag and the far side must earn its own ending. It disappears because
`own` is an intersection over every branch performing the step, and §1.34 gives rm480, rm500 and
rm550 a `123 := 4` branch too, none of which clears flag 15. Verified in the scripts, not
inferred: `(proc13_2 15)` appears five times in the whole game and all five are `rm370.sc:71,
173, 230, 632, 739`, each immediately before a `(++ global123)`.

**But forcing `257: 0` back — measured, `own` restricted to rm370's branches, cures A+B in —
leaves `producible_seal(123, 4, 370, flag44, 0)` at `False`.** The flag-44-less crosser's
post-flip closure still reaches the goal, and the write that takes it there is:

    123:=k+1 @rm550  deps={123: [k], 712: [0, 1]}          for every k in 1..10

⭐ **rm550's day advance has NO dependency at all** — 712 is the platform flag, whose dep spans
its whole domain (cure B's specimen, in its other costume). So the crosser winds the day from 4
to 11 at the dream room whatever they hold, and no clear of flag 15 can stop them. rm480 by
contrast is HONESTLY gated (`{458: [1], 541: [1]}` = flags 216 ∧ 299, or `{1213: [1]}` = flag
971) — §1.55 was right about the bayou's chain; the bayou is not the leak.

**Why rm550 has no guard, read in the scripts:** `rm550.sc:47`, the ROOM'S OWN `init`, does
`(global2 setScript: doTheDream)` unconditionally, and the increment is state 61 of that script
(`rm550.sc:533`). Entering the room *is* the day advance. The only guard is the ROOM'S ENTRANCE,
and the model holds it — one hop too far away to use:

    500 -> 550   guard  prev == 540              (the only edge into rm550)
    540 -> 500   req    {123: [7], 1096, 1108-1111, 1218}   (the only edge from rm540 into rm500)

⭐ **THE NAMED NEXT ROUND — a `prev == p` guard imports the edges from p.** Standing at `a` with
`prev == p` means the player TOOK some edge `p -> a`, so the disjunction of those edges' reqs
held at the crossing. Import it, and `500 -> 550` demands day 7, rm550's sub-7 steps die to the
step-pruning `_apply_consumer_windows` already performs, and the fan is bounded by the record
instead of by a literal range. ⛔ SOUNDNESS FENCE: the req held *when they crossed*, not now, so
only facts that PERSIST may be imported — a monotone latch, or a counter's lower bound
(`123 == 7` then means `123 >= 7` now, by the `_counters` rule). A clearable flag may not be.
This is [[teleport-two-hop-prevroom]] generalised from room inits to edge guards, and it is the
same missing composition §1.50 named from the other side (the arming machine's entry guard).

**Two routes MEASURED AND REFUTED before that one, so nobody rebuilds them:**
* **`_pstates` cannot bound the fan.** It reads rm550 at days `[2..11]` and rm480 at `[0..11]`
  — the scalar day projection does not track prevRoom, so `(550, 3)` is attainable in it.
* **The consumer windows cannot either, yet.** `win[541=1]` (flag 299, the tattoo) is the WHOLE
  domain, so no branch of rm480's is narrowed. ⛔ And §1.55's provenance for that flag is wrong:
  `proc13_1 299` occurs ONCE in the game, at `rm220.sc:909` (doTheTattoo state 18), not at
  `bookstore.sc:1899`; `bookstore.sc:1899` is the day-6-gated ARMING of a second `doTheTattoo`
  copy, and `:1899` in the other file is `bayouMaze.sc`, which sets flag 216. The day-6 gate is
  one arming hop away from the write, which is why the window cannot see it — the same
  arming-floor gap as the rest of this section.

### Cost, corrected
§1.55 warned the GK1 rebuild under §1.34 is "~55 min … each iteration is an hour". **Measured:
115 seconds**, and `producible_seal` answers in 4–5 s on that model. This frontier is cheap to
iterate and does not need the box.

## §1.57 §1.34's fan is SELF-JUSTIFYING — the leaks, mapped (2026-09-05, measured; leak 3 RETRACTED, see below)

§1.56 named the fan as the thing to bound and shaped one rule for it. Building that rule in the
product (not in `src/`) got rm550 exactly right and **still left the seal False**, so the
investigation continued until every leak had a number. Here is the whole map. ⛔ Nothing in this
section is built; the simulation ran against `wt134` = `8ca65a0` + `apply_134.py` + §1.56's cures.

### Why an unbounded fan cannot be falsified from inside
Give rm550 a `123 := k+1` step for every k and THREE separate things follow at once, each of
them a place the model is permissive for good reasons elsewhere:

1. **The staged closure LANDS the crosser there.** `_staged_pre` resets positions at every step
   — `land = {r for r, sts in _rstep[C].items() if (j, j+1) in sts}` (`missability.py:7597`),
   which is right and was measured right (§1.44's "places are not carried in hand"). Under
   §1.34 the day-1→2 step lands at rooms `{370, 480, 500, 550}`, so the day-2 crosser is SEEDED
   standing in Germany and in the bayou.
2. **The scalar day projection admits it.** `_psucc` checks `req.get(R)` and nothing else — by
   construction, a projection of one register cannot read a guard on another. So `50 -> 510`'s
   `prev == 510` is invisible to the day walk, and `_pstates[123]` reads rm480 at `[0..11]` and
   rm500 at `[2..11]`.
3. **The write's own branch has no day dep to contradict either of them** — that is what being
   fanned MEANS.

⭐ So the fan supplies its own evidence, and no downstream repair can undo it: each of the three
would have to be tightened, and two of them are load-bearing elsewhere. **The bound has to be
composed BEFORE the fan is believed.**

### Leak 1 — rm550, the dream: SOLVED in simulation, exact
The room's own `init` arms the increment unconditionally (`rm550.sc:47`), so its only guard is
the entrance, and the entrance is a prevRoom test one hop away from a day gate:

    500 -> 550   prev == 540                                     (the only edge in)
    540 -> 500   {123: [7], 1096, 1108-1111, 1218}               (the only edge from rm540)

§1.56's rule — **a `prev == p` guard imports the persisting reqs of the edges `p -> a`**
(⚠️ the numbers below are the §1.34 worktree's; on the LIVE model the windows already bound
rm550 to `[7..10]` unaided — see §1.58), fenced
to the counter's lower bound because `123 == 7` then means `123 >= 7` now (the `_counters` rule)
— was simulated over the whole `_emeta`:

    2 edge-metas gain a bound:  500 -> 550 : 123 [2..11] -> [7..11]   (lo=7)
                                750 -> 500 : 123 [0..11] -> [7..11]   (lo=7)
    rm550's steps then:  (7,8) (8,9) (9,10) (10,11)      -- the record's 7->8, and nothing below

⭐ Two edges in the whole game, and the answer the scripts give. Adding "a counter write cannot
happen at a value its ROOM cannot hold" (`_pstates`-bounded, a sound filter since `_pstates`
over-approximates) pruned a further 77 `_wbranch` branches and 13 `_rstep` steps. **Seal: still
False**, because of leaks 2 and 3.

### Leak 2 — rm480, the bayou: blocked on the UNDATABLE flag 268
rm480's own day branches are honestly gated (`{458: [1], 541: [1]}` = flags 216 ∧ 299, or
`{1213: [1]}` = flag 971) — §1.55 was right about that chain and §1.51's "the ritual costs only
standing in the bayou" was wrong. The leak is the ENTRANCE again:

    372 -> 490   {510: [1], 712: [0, 1]}        reg 510 = FLAG 268
    205 -> 490   {12: [750], 712, 510: [1], 691}
    490 -> 480   {}                              (free, once you are in the maze)

⛔ **SUPERSEDED BY §1.59: flag 268 IS datable** (room 410 ∧ day 6, in `drumInset`'s `local0`).
What follows was written before that was read.

So the maze and the ritual hang on flag 268, whose raise is the drum puzzle the model cannot
date ([[qfg-guards-loud-not-holdy]] is not it; this is §1.41's flag, and §1.51 already called
its raise opaque). Until 268 carries a day, rm480 is attainable at day 0 and the fan there
cannot be bounded. ⛔ This is the one genuinely NEW blocker in the map.

### ⛔ Leak 3 — RETRACTED THE SAME NIGHT: there is no self-return leak
**What this section first said, and it was WRONG:** that Germany hangs off `50 -> 510`, a
self-return from rm50's `newRoom: global12` fan, and that the question was whether §1.53's
`no_self_return` may widen its scope to `_pclose`. That was read off the closure's EDGE TABLE
(`50 -> 510` is indeed the only recorded way in, and prevRoom `:= 510` is indeed written by
nothing but the four edges LEAVING rm510) and then *assumed* to be the route the closure takes.
It is not. The control that settles it is the model WITHOUT §1.34, where no fan exists:

    MAIN (no fan)    landing rooms for every step 1->2, 2->3, 3->4:  [370]
                     day-3 staged closure:  39 rooms
                     rm50 IN, rm480 IN, rm490 IN
                     rm500 / 510 / 520 / 530 / 540 / 550 / 700 / 750 / 800:  ALL ABSENT
                     pv[12] contains 510:  False

⭐ **`_pclose` already refuses the bootstrap.** prevRoom is tracked, `allowed(12)` never admits
510, so the edge is never taken and the fixpoint never closes on it — exactly as designed.
§1.53's rule does NOT need to widen its scope, and the corpus-wide measurement this section
called for is not owed.

Germany is in the §1.34 closure for one reason only: **the landing-seed teleport of leak 1**.
`_staged_pre` reseeds at `{370, 480, 500, 550}` after every step, so the crosser simply STARTS
in Germany, and the prevRoom values they pick up standing there ride forward in `pv` into the
post-flip closure. The blast radius is exact: **39 rooms without the fan, 51 with it.**

So the map is two leaks, not three, and leak 3 was the fifth wrong diagnosis this line has
produced. The lesson is the one §1.52 already wrote down and this section proves again: an edge
table says what edges EXIST, never which one a closure took. Ask the closure.

### Where that leaves §1.34
Three leaks, one solved in simulation, one blocked on flag 268's date, one turning on whether
§1.53's rule may widen its scope to `_pclose`. **§1.34 stays reverted**, and the two GK1 day-7
reds stay red — but they are no longer "the record's floor" as §1.51 called them. They are three
named, measured, independently attackable gaps.

## §1.58 The prev-import rule, LANDED and corpus-neutral — with what it does NOT do (2026-09-05)

§1.57's leak-1 rule is in `src/missability.py` as `_apply_prev_import`, called from the build
just before `_apply_consumer_windows` so the windows read the tightened edges.
`src/test_prev_import.py` pins it (8 checks). **Gate on the box: 967 passed / 14 known-red /
0 unexpected / 0 crashed — byte-identical accounting to the run without it. No golden, no
watched surface, no emitted tree moves on any of the six games.**

### ⚠️ What it does NOT do, stated plainly so nobody re-measures it
⛔ **On the LIVE model the dream room was ALREADY day-7-bounded.** §1.57 reported the rule
taking rm550 from `[2..11]` to `[7..11]`; that was measured on the §1.34 worktree. Against a
true control (`a6357db`, this session's cures in, the rule out) rm550 reads `[7, 8, 9, 10]`
*without* the rule — `_apply_consumer_windows` already gets there, because without the fan
everything downstream of day 7 is honestly windowed. So on today's corpus the rule's headline
checks are green either way and **the rule is inert for R4**; its purpose is to hold rm550 down
once §1.34's fan removes the windows' ability to do it.

Its one measurable effect on today's model is in the other direction, and is the SOUND one:
`_emeta[(750, 500)]`'s day requirement is EMPTY at control — an edge the windows had narrowed
out of existence — and non-empty with the rule, because tightening the edges first changes what
the windows compute. A restored edge WIDENS the projection, which can only remove findings,
never invent them. Nothing on the corpus depended on it.

### Why it is landed anyway rather than parked
It is measured, tested, corpus-neutral, and the §1.34 round needs it; parking it costs the next
session a re-derivation and two box gates to learn what is written here. The precedent is
§1.28's `entry_ggets` — landed inert, "which is the point: the FP never gets to exist".

⛔ **Its second site is still unwritten.** `_closure_tables`' edge list is built from `em.*`
rather than from `_emeta`, so `_pclose` does not see this bound ([[same-rule-two-places]]).
Measured as not needed for the case at hand — `_pclose` tracks prevRoom and already refuses the
bootstrap it would fix (§1.57 leak 3, retracted) — but it is one rule with two readings and the
second should land with the first consumer that needs it.

### A lead dropped in passing
Three GK1 edges carry a NATIVELY EMPTY day requirement — `(205, 380)`, `(370, 371)`,
`(370, 372)` — identical with and without this rule, so they are somebody else's bug. An empty
req is an edge no day-projection walk can ever take; if that is not intended, it is silently
deleting three doors.

## §1.59 Leak 2 is NOT undatable: flag 268's day-6 gate is in a LOCAL (2026-09-05, measured)

§1.57 called flag 268 "the drum puzzle the model cannot date" and made it the one genuinely new
blocker. ⛔ **That was wrong too — the sixth.** The date is in the scripts, in plain sight, and
the model misses it for three specific reasons, each of which has a documented rationale that
does not cover this case.

### The chain, read end to end
`proc13_1 268` occurs ONCE in the whole game — `drumInset.sc:914`, in `checkPhrases`, under
`local0 == 2` (`switch local0`, case 2) plus "the three phrases are 6, 10, 26" and `¬flag268`.
No day gate on the write. But `local0` is assigned exactly once, in `drumInset::init`
(`drumInset.sc:246`), and its value IS the date:

    local0 = switch global11                  ; the room
               410 -> switch global123        ; the DAY
                        6  -> 2      ⭐ the only arm that can raise flag 268
                        7  -> 1
                        10 -> 3
                        else -> 0
               800 -> 4
               else -> (if (< global123 6) 0 else 1)

So **flag 268 ⟸ room 410 ∧ day 6**, and the model's `_wbranch[(268, 410, 1)]` reads
`deps {268: [0]}` — the `¬flag268` conjunct alone. It also files a raise at **rm800**, where
`local0` is 4 and flag 268 can never be raised at all: a phantom writer in the endgame.

⛔ The arming route gives nothing, checked: the inset is armed by `sGoToDrum` (`neJackson.sc:871`,
room 410), which `tom::doVerb 18` arms with no guard whatever. §1.50's rule would not have found
this. The day lives in the local and nowhere else.

### THREE reasons `derive_room_locals` cannot see it, each rationally scoped elsewhere
1. **Scope.** It iterates `set(rooms) & set(ir.scripts)`; script 815 is an `Inset`, not a room,
   so it is never examined. (Census below: this is the ONLY non-room case in the corpus.)
2. **Taint.** The write is `(= local0 (switch ...))`, so `I.as_int(rhs)` is None and the local is
   tainted outright — the rule that keeps KQ4's stepped ocean-grid locals out.
3. **Init-only.** Every write sits in `init`, which is excluded as "a per-visit CONSTANT, not
   state ... the entry reset IS its entire semantics". ⭐ That rationale is exactly what fails
   here: a SWITCH-VALUED local's value is a function of STATE, so the entry reset is not its
   semantics, it is the thing we need.

### ⭐ THE SHAPED RULE, and its measured blast radius
**A local assigned by a switch / cond / if tree whose leaves are all integer literals is a
DERIVED REGISTER — one guarded constant write per leaf — not a taint and not a per-visit
constant.** Census over all six games (`tools/probes/gk1_fan/census_switch_locals.py`):

| game | sites | in ROOM scripts | switching on a GLOBAL |
|---|---|---|---|
| LSL2 | 1 | 1 | 0 |
| KQ4 | **0** | 0 | 0 |
| KQ6 | 3 | 1 | 0 |
| KQ5 | 4 | 3 | 1 |
| LB2 | 4 | 4 | 1 |
| GK1 | 8 | 7 | 1 |

**20 sites corpus-wide, and exactly ONE outside a room script — GK1's `drumInset`.** KQ4 cannot
move at all. ⛔ The `If`-armed shape was invisible to the first census pass (drumInset's outer
`else` is an `if`, not a literal) and the first run reported 5 sites; the table is the corrected
run.

### ⛔ AND IT CANNOT BE SIMULATED — the lowering has to be BUILT to be tested
Injecting the day dep into `_wbranch[(268, 410, 1)]` and deleting the rm800 row changes nothing:
`win[268=1]` comes back as the whole domain. Two reasons, both worth knowing:
* `_consumer_windows` collects its `want` set from the WRITE-BRANCH tables only. Flag 268 is
  demanded by an EDGE (`372 -> 490`, `{510: [1]}`) and by no write at all, so no window is ever
  built for it. **A second, independent gap** — the windows should cover every value the model
  demands, edges included. (Widening `want` to `_emeta` was simulated: the window then exists.)
* Even then it reads `[0..11]`, because `_pclose` — which `_staged_pre` and therefore the
  windows run on — reads `_closure_tables`' ORIGINAL GUARD TREES, not `_wbranch`
  (`_closure_tables`' own docstring says so: "the branch tables are the wrong source here").
  A `_wbranch` injection is invisible to it. The day gate has to be in the guard tree, which is
  what lowering actually produces.

So the next round is a BUILD, fully specified: the switch-valued-local rule, the scope extension
to the one non-room script, and the `want`-from-edges widening. Blast radius is 20 sites with
KQ4 provably untouched, and the gate is the arbiter.

### ⛔ THE BUILD WAS ATTEMPTED THE SAME NIGHT, AND STOPS ONE LINK SHORT — REVERTED
Written and measured, not guessed: `derive_switch_locals` + `sink_switch_assignments`
(rewriting `(= L <switch tree>)` into the tree with `(= L <lit>)` in each arm, so the lowering
sees ordinary guarded constant writes) wired in beside `derive_room_locals`. It WORKS as far as
it goes — `drumInset.local0` lowers to register **1237**, and flag 268's write becomes

    268:=1 @rm410  deps={268: [0], 1237: [2]}          ⭐ the mode gate, captured

⛔ **And then nothing.** Register 1237 has **no writes anywhere in the model** — empty in
`handler_writes`, `init_writes`, `init_seq`, `_inroom` and `_rstep` alike — so the new
dependency is on a register the model can never satisfy. `reg_vals[1237]` comes back `[0, 2, 4]`
from the domain scan alone, and the day projection does not move: rm410, rm490 and rm480 still
read `[0..10]`.

The reason is one scope layer further down. `drumInset::checkPhrases`'s write IS lifted to the
rooms that arm the inset (410 and 800), which is how flag 268 got its rooms in the first place —
but the assignment lives in **`drumInset::init`**, and an `init` of a non-room script is
attributed to no room by any of the three channels. So the mode register is read everywhere and
written nowhere.

**Reverted, and deliberately.** Today the unenforced dep is harmless — 1237 is untracked, so the
atom reads permissively and flag 268 stays raisable — but that is a LATENT TRAP of exactly the
kind `derive_room_locals`' docstring warns about: "a register missing one of its writes can
fabricate a seal, and half a store is worse than none." The moment 1237 became tracked the bayou
would become unreachable and every stranding behind it invented.

⭐ **So the round is THREE changes, not two, and the third is the load-bearing one:** the
switch-valued-local rule (written, works), the `want`-from-edges widening (simulated, works),
and **a non-room script's `init` writes must reach the rooms that arm it** — the same
attribution `checkPhrases` already gets, extended to `init`. Build them together or not at all.


## §1.60 The bayou is dated: the switch-local round, BUILT (2026-09-05)

§1.59 specified three changes and said "build them together or not at all". Built together, and
they close leak 2 on the live model: **rm490 and rm480 read days `[6..10]` instead of `[0..10]`.**
In game terms the tool now knows the bayou is a day-6 place, because it can read why.

| # | the change | where |
|---|---|---|
| 1 | **a local assigned by a switch/if tree of literal arms is a DERIVED REGISTER** — one guarded constant write per arm, sunk into the arms before lowering so nothing downstream learns a concept | `vocab.derive_switch_locals` / `_sink_assignment` / `sink_switch_assignments` |
| 1a | ⛔ **…whose every test READS A REGISTER** — a switch on a send or an `if` comparing two other locals derives nothing a projection carries | `vocab._switches_on_registers` |
| 1b | ⛔ **…and which is READ BACK AS A CONDITION** — `derive_room_locals`' own discipline, which the first draft dropped; a local only ever CONSUMED is a computed value, not state | `vocab._read_as_condition` |
| 2 | **a lowering must harvest the writes it created** — a NON-ROOM script's `init` reaches no room through any channel, so a lowered local there is read everywhere and written nowhere | `opmodel._armed_init_writes` |
| 3 | **the consumer windows want every value the model DEMANDS, edges included** — flag 268 is demanded by an edge and by no write, so it had no window at all | `missability._consumer_windows` |

The chain, end to end, as the model now holds it:

    init_seq[410]:  1237:=2  under  11==410 AND 123==6          ⭐ the arms, with the room test
                    1237:=1  under  11==410 AND !6 AND 123==7
                    1237:=3  under  11==410 AND !6 AND !7 AND 123==10
                    1237:=4  under  !(11==410) AND 11==800
    _wbranch:       268:=1 @rm410  deps {268:[0], 1237:[2]}      the mode gate, captured
    window:         win[1237=2] = [6..10]  ->  win[268=1] = [6..10]
    projection:     rm490 [6..10]   rm480 [6..10]

⛔ **Change 2 is the one that makes it safe as well as the one that makes it work.** It is scoped
to the lowering's OWN synthetic registers — globals that did not exist a moment earlier — so no
existing surface can move through it. A general "harvest every non-room `init`" is a much larger
claim and is NOT made here. And it files into `init_seq` (the POSSIBLE-write channel), never
`init_writes`: an inset's `init` runs when the inset opens, not on arrival, so committing it as
an entry write would assert a value the player need never have.

📝 One inert artifact, pinned rather than fixed: `lower_room_locals` files its reset under the
SCRIPT number, which for a non-room script is a room that does not exist
(`init_writes[815] = {1237: 0}`). No walk can arrive at 815, so it is dead weight; the test fails
loudly if 815 ever becomes a room, at which point the reset would start asserting a value on
arrival somewhere real.

### What this does NOT yet do — §1.34 is still not landable
The bayou is dated, but with §1.34's fan applied `_rstep[123]` at rm480 still carries a step at
EVERY value — `(1,2) … (10,11)` — because `_pstates` bounds ATTAINABILITY and nothing prunes the
steps by it. Measured on the §1.34 worktree with this whole round in:

    rm480 days [6..11]   but   rm480 steps (1,2) (2,3) … (10,11)
    producible_seal(123, 4, 370, flag44, 0) = False

⭐ **So the next round is the fourth change, and it is small: a counter step at a value its ROOM
cannot hold is not a step.** Prune `(f, t) @ room` when `(room, f)` is outside `_pstates[C]`,
prune the matching `_wbranch` branches, and iterate to a fixpoint — sound because `_pstates`
over-approximates, so "not attainable" is a refutation, and monotone decreasing, so it
terminates. Simulated in §1.57 (it removed 77 branches and 13 steps there); with the bayou now
dated it should bound rm480 to `(6,7) …` and rm550 to `(7,8) …`, which is what the scripts say.

### ⛔ THE TWO FENCES WERE FORCED BY THE GATE, not designed in
The first build had neither, admitted twenty locals corpus-wide, and went **RED**:
* **LSL2's FROZEN GOLDEN grew** `register_strandings +['Sewing_Kit@reg490=1->[138]']`,
  `register_write_specs +['reg490=1: (gEgo has: 12)']` and a MALFORMED
  `placements +['rmNone->rmNone: applied=False …']` — a room of `None`, which is a bug, not a
  finding. `rm22Script`'s local0 is assigned from `(< (local6 <sel>:) …)`, a SEND: fence 1a.
* **LB2's watched surface moved 26 → 36 rows** and `mechanism pinned: smellingSalts` broke.
  `actBreak.sc` local0 is assigned 230 / 330 / 355 / `(if (== global12 620) 610 else 510)` /
  420 / 750 and read exactly once, at `(global2 newRoom: local0)` — a DESTINATION, never a
  condition: fence 1b. ([[lb2-err-toward-not-moving]] is a standing instruction.)

⚠️ **AND ONE OF THE THREE "MOVERS" WAS NOT THE RULE AT ALL.** LSL2 kept moving after fence 1a,
with the census reporting ZERO switch locals for it — because the `else:` of change 2 had been
inserted BETWEEN `_init_writes(...)` and the room-local reset loop, orphaning the reset into the
else branch and silently deleting **every game's** room-local entry resets. A pure editing slip,
invisible to `ast.parse`, caught only because the golden moved and the bisect asked which change
did it. The lesson is the file's own: an edit anchored on two lines can capture a third.

With all three fences the corpus census is **exactly one site — GK1's `drumInset` — and nothing
else in any game.** Gate on the box: **986 passed / 14 known-red / 0 unexpected / 0 crashed**,
the failing set exactly the declared one.

## §1.61 A counter step at a value its room cannot hold is not a step (2026-09-05)

The fourth change §1.60 named, built: `_prune_unattainable_steps`, run right after `_pstates`.
`_rstep[C][room]` says the game advances C from f to t HERE; `_pstates[C]` says which values C
can actually hold at each room. Where they disagree the step is a fiction — and not a harmless
one, because a counter's steps are what `_staged_pre` reseeds the crosser at, so an unattainable
step TELEPORTS a player into the room it names (§1.57's landing-seed leak).

Sound because `_pstates` OVER-approximates (the permissive walk ignores every guard on a
register it does not carry, so "not attainable" is a refutation, never a guess); terminating
because it only ever removes. The branch tables are pruned with the steps
([[same-rule-two-places]]) — `_step_neco` and `_step_live` read those, not `_rstep` — and a
branch naming no from-value at all is "from anywhere" and cannot be refuted, so it stays.

**On the live model** it takes rm750 from `(1,9) … (10,10)` to `(7,9) …` and drops the opening
rooms' phantom `(1,1)` self-steps. GK1's oracle is unchanged (11 passed / 2 failed, R1–R5 as
before).

**On the §1.34 worktree it does what the whole round was for.** With the bayou dated (§1.60) and
the steps pruned, the fan collapses onto the record:

    rm480:  (6,7) (7,8) (8,9) (9,10) (10,11)      the bayou ritual ends day 6 — §0 says 6->7
    rm550:  (7,8) (8,9) (9,10) (10,11)            the dream — §0 says 7->8
    rm370:  (1,2) … (7,8)                          unchanged, the bedroom day loop

⛔ **And rm500 does not**, so §1.34 is still not landable: `producible_seal` is still `False` and
`_step_neco(123, 3, 4)` is still `{}` (the flag-15 clear still lost), because rm500 keeps a
`(3,4)` step — it reads attainable from day 2.

### The last leak, traced state by state
A BFS over the day projection, recording each state's predecessor, gives the chain outright:

    rm500@2  <-  rm510@2  <-  rm50@2  <-  rm210@2  <-  rm370@2  <- … <- rm17@0
    rm750@2  <-  rm216@2  <-  rm720@2 <-  rm50@2   <- …

⭐ Both go through **rm50 — the conversation screen — and its `newRoom: global12` SELF-RETURN
FAN**, the same twenty edges §1.53 named. `50 -> 510` demands `prev == 510` and `50 -> 720`
demands `prev == 720`; on the LIVE model both carry a native day floor of `[7..10]` (§1.39's
icon-destination click gate), but under §1.34 the fan makes everything producible everywhere,
the consumer windows stop narrowing, and the floors are gone. So the conversation screen becomes
a free teleport into Germany and Africa on day 2.

⚠️ This does NOT contradict §1.57's leak-3 retraction, and the difference is worth keeping
straight: `_pclose` TRACKS prevRoom and really does refuse the bootstrap, which is what that
retraction measured. `_walk`/`_psucc` on a scalar projection does not carry prevRoom at all, so
the same edge is free there. Two walks, two answers, both correctly measured.

⭐ **THE NEXT RULE, and it is not §1.53's:** a self-return may not be dropped state-by-state —
§1.53's warning stands, since leaving b for a and returning with a higher counter is a real
state only the round trip reaches. But at ROOM level the statement is exact: **a self-return
delivers no room the player could not otherwise enter.** You cannot satisfy `prev == b` without
having stood in b, and every real first entrance is a non-self-return edge, so *rooms reachable
without any self-return = rooms genuinely reachable*. Refuse a self-return INTO a room outside
that set, and rm510 and rm720 stop being day-2 destinations while every legitimate round trip
survives.

**Gate on the box: 986 passed / 14 known-red / 0 unexpected / 0 crashed**, failing set exactly
the declared one — and 507 s against ~790 s, because pruned steps shrink every walk that reads
them. `test_step_prune.py` pins it, red-proven at `7d594da` (3 of 7 checks fail there).

## §1.62 §1.34 IS REACHABLE — the windows/prune fixpoint, and the one thing it breaks (2026-09-05)

⭐⭐ **The circularity §1.55, §1.56 and §1.57 all ran into has a name and a shape: the consumer
windows and the step prune FEED EACH OTHER, and running each once stops far short of what the
record supports.** A narrower fan means fewer stages in which a value is producible, which
windows more branches, which prunes more steps. Iterate the pair and GK1's day model collapses
onto the scripts. Measured pass by pass on the §1.34 worktree, everything from §1.56–§1.61 in:

    pass 0   rm500 [2..11]  rm510 [2..11]   neco(3,4) = {}
    pass 1   rm500 [3..11]  rm510 [3..11]   neco(3,4) = {647: 1}
    pass 2   rm500 [4..11]  rm510 [4..11]   neco(3,4) = {257: 0, 647: 1}   ⭐ the clear is BACK
    pass 3   rm500 [5..11]      …
    pass 5   rm500 [7..11]  rm510 [7..11]   fixpoint

    rm480: (6,7) (7,8) (8,9) (9,10) (10,11)      the ritual ends day 6   -- §0 says 6->7
    rm550: (7,8) (8,9) (9,10) (10,11)            the dream               -- §0 says 7->8
    rm500: (7,8) (8,9) (9,10) (10,11)            Germany's departure     -- §0 says 8->9
    rm370: (1,2) … (7,8)                          the bedroom loop, untouched

⭐⭐ **And with it, `producible_seal(123, 4, 370, flag44, 0) = True`.** R4 survives §1.34.
Confirmed in a real build, not a simulation: GK1 under §1.34 builds in 291 s and the seal answers
in 5 s. **The day-7 family — the two GK1 reds this whole line has been chasing since 2026-09-02 —
is finally askable.** §1.51's "the record's floor" was wrong; so was §1.55's `fwd`, §1.56's lost
clear, §1.57's leak 3 and §1.59's "undatable" flag 268. This is what was actually in the way.

### ⛔ AND IT IS NOT LANDED, because it drops R5
With the outer fixpoint in, GK1's oracle goes **10 passed / 3 failed**: the croc mask's
`edge_strandings` row `rm490 -> rm480` — R5, a CONFIRMED softlock, tool-derived in §1.38 — is
gone. A drop from EXPECTED_CAUGHT is a regression and stops the round.

**Isolated, not guessed.** Disabling only the `_apply_consumer_windows()` re-run inside the
fixpoint (keeping the re-walk and the repeated prune) restores it: **11 passed / 2 failed**. So
it is the window RE-RUN specifically, not the prune and not the extra walks.

⛔ **One hypothesis tested and REFUTED**: that a second narrowing intersects a requirement down
to EMPTY, killing the edge (`rq2[C] = set(rq2[C]) & narrowed` has no non-empty guard, and §1.58
already noted three GK1 edges carrying a natively empty day req). A guard refusing the empty
intersection at both the branch and the edge site was written and measured: **R5 still drops.**
So the mechanism is something else, and the three empty-req edges remain their own lead.

What is NOT the cause, also measured: rm490 and rm480's attainable days are `[6..10]` and the
`(490, 480)` edge metas are identical with and without the fixpoint, and the mask's source is
rm250 either way. The row's disappearance is downstream of all three.

### 📝 Also built, measured INERT, and reverted: the room-level self-return rule
§1.61 proposed it — "a self-return delivers no room the player could not otherwise enter", room
level so it does not collide with §1.53's state-level warning. It is TRUE and it is useless:
censused over three games, **0 refusals**. GK1 has 26 pure self-return edges and every one of
their destinations has a real entrance elsewhere (rm510 and rm720 come in through the endgame
chain), LB2 has 4, KQ6 none. rm50's fan reaches Germany at day 2 because the day VALUE is
unbounded there, not because the room is unreachable — a state-level fact, which is §1.53's
scope and stays there. Reverted rather than carried as dead code.

⭐ **NEXT: find why the window re-run costs R5.** Everything else is measured and in place; the
attempt is kept whole in `tools/probes/gk1_fan/fixpoint_attempt_missability.py` with
`sim_fixpoint.py` beside it, so the next round starts by reproducing the drop rather than
rebuilding the fixpoint.

## §1.63 The R5 "regression" is not one: the fixpoint and §1.34 are ONE round (2026-09-05)

§1.62 stopped with the windows/prune fixpoint making `producible_seal` True but dropping R5, the
croc mask's `rm490 -> rm480` row. Diagnosed to the bottom, and the answer reverses the verdict.

### The drop, traced conjunct by conjunct
`_stranding_drops[(490, 480)]` is EMPTY and the row is absent from the RAW, pre-filter rows — so
none of the three refutations (FORCED / UNHOLDABLE / RETIRED) touched it and the shared core in
`scc_core.edge_strandings` never produced it. Of that core's conjuncts, exactly one flips:

    edge_kind goto ✓   reachable ✓   not freely reversible ✓   comp_of ✓
    mask obtainable before 490, lost after 480 ✓      need rooms {490} ∩ fwd = {490} ✓
    ⛔ rooms_after(480): goal reachable = FALSE      -> "death sink", the edge is SKIPPED

`rooms_after(480)` loses **16 rooms** — 216, 371, 500, 510, 520, 530, 540, 550, 670, **680**,
700, 710, 720, 750, 800, 899: Germany, Africa, the finale and the goal itself.

⭐ **And it is ONE projection that does it.** `rooms_after` walks every projection from the
crossing's states and INTERSECTS. The day projection is fine (51 rooms against the control's 52,
identical day values `[6..10]` from `(480, 6)`). The one that loses the goal is the JOINT
`(123, 257)` — day × day-end flag — which from rm480 has exactly ONE start state, `(day 6,
flag 15 clear)`, and cannot advance from it: rm370's `(6, 7)` step demands `257 == 1`, and
without §1.34 nothing models day 6's ending at all, because day 6 ends AT THE BAYOU RITUAL
(§0) whose `(++ day)` is exactly what §1.34 supplies.

### ⭐ So the fixpoint removed a PHANTOM, and R5 was standing on it
Before the fixpoint the joint carried a `(480, day 6, flag 15 SET)` state it has no business
having — the day-end flag raised in the bayou, which no arm of `endDay` does. That phantom let
the day advance out of rm480, made the goal reachable from it, and kept the crossing out of the
death-sink exclusion. Narrowing it away is CORRECT; the row's disappearance is the detector
faithfully reporting a model in which the bayou cannot reach the ending — which, without §1.34,
it genuinely cannot.

### The prediction, and the measurement that confirms it
If that reading is right, then adding §1.34 — which gives the bayou its own day advance — must
bring R5 back. **Measured on the §1.34 worktree with the whole round in:**

    R1 PASS   R2 PASS   R3 PASS   R4 PASS   R5 PASS   no confirmed softlock DROPPED: PASS
    11 passed / 2 failed  -- the same two declared reds as today

⭐⭐ **The windows/prune fixpoint and §1.34 are ONE round and must land together.** Measured
apart, each looks like a regression the other repairs: the fixpoint alone drops R5, and §1.34
alone (measured five times since 2026-09-02) kills R4. Together the oracle is exactly what it is
today, plus `producible_seal` returns True for the day-4 crossing — the thing the day-7 family
has been waiting on.

### ⛔ WHAT LANDING THEM COSTS, and why it is the USER's call
Under §1.34 + the fixpoint GK1's two declared reds keep failing, but their CONTENT moves:

    FLAGGED: ['VoodooCode1', 'braceMold', 'knife', 'reconVeve', 'sLakePatter', 'talisman']
    (today:  the day-7 family + knife + two model gaps + talisman)

`sLakePatter` returns after being retired 2026-08-31, `crocMask` and `oil` leave the flagged
list, and the NEW list gains a disjunctive group. That is a COVERAGE CHANGE to a
USER-enumerated oracle, so it is reported and not decided
([[report-coverage-changes-loudly]], [[dont-flip-enumerated-ground-truth]]). And §1.34 touches
`_glob_domains` for every game — static blast radius LSL2 9 sites, KQ4 9, KQ6 1, KQ5 8, LB2 10 —
so the corpus gate is owed before anything is believed.

**Nothing from this section is in `src/`.** The fixpoint lives in
`tools/probes/gk1_fan/fixpoint_attempt_missability.py`, §1.34 in `apply_134.py` beside it.

## §1.30 The descent-spec growth is NOT a need-liveness case (2026-09-02)

Probed before building: the three sketches' need sites are day-BLIND but subject-PINNED
(reconVeve's live site at rm50 needs `178==2`, whose only producer is rm340 — dead in the
post-crossing day walk), and `crossing_retires_need` never consults the day projection
because the descent's own req touches only flags 271/273/850 — and NEITHER flag's writers
presuppose the day (271 ← 273 at rm455, 273 ← a free flag at rm450). The record ties the
descent to day 10 only through a COST: 271's write prices the rod, obtainable on day 9. No
projection carries that; the flat `reob` is room-level (455 at day 2 can reach the source,
800 never can), so the witness the row needs — a day-10 crosser lacking the sketch — is
fabricated by coarseness. The honest cure is a STATE-LEVEL CROSSING WITNESS (does an
item-less player reach the crossing state at all, with its costs composed?), which is
`_pclose`'s question, not the projections' — a named future round. Not need-liveness;
the §1.28 note calling it that was wrong.

## §1.29 R4's TRUE WALL: once-only flag 65, third consumer (2026-09-02)

With the record closed (§1.28) the closure arm still emitted nothing, and the emust round
(arming costs required ⊆ items — a genuine soundness fix: without it the day-end/day-5/
flag-47/flag-74/trace cycle closed permissively) narrowed it to one strand. The
why-satisfiable tracer over the day-4 demand web ({689, 490, 278, 469} + flag 15) then
proved every producer HONEST for the deposit-less crosser — wolfPhone-priced 689,
CTR-permissive 490, Mosely-interrogation 278, reconVeve-priced 469 — except the one that
breaks R4: **`257:=1 @rm50` under `178==2 ∧ flag65(307)`, with NO day gate — the go-home
day-ender.** A crosser who never spent flag 65 carries it into day 4 and ends the day
without the trace, in the record as written. The truth is ONCE-ONLY: the go-home handler's
recorded co-write (raise 15 / clear 65, the 5db647a landing) spends the flag — but the
closure's accumulate-only value sets cannot count spends, and the old once-only round
(designed 2026-08-31, BLOCKED: the day-window spelling died to the witness trace; the
honest wall was a 5-wide joint) now has its THIRD consumer after the reconVeve and
braceMold FPs. R4 rests exactly there — one mechanism, three payoffs, waiting on a
counting-capable spelling (multiset closure, or a spent-flag refinement with the co-write
as its record).

## §1.28 UNPARKING THE DOOR-CLOSER ROUND (2026-09-02, the USER's "almost surely buggy")

The USER: *"the parked KQ6-moving round almost surely is buggy, so please diagnose and
fix."* Re-ran §1.20's T1/T2/T3 bisections against TODAY's code (worktree toggles diffed
against the KQ6 golden):

  * **T2 (honest `unresolved_register` seed): MOVES NOTHING.** The stepDown mover died to
    interim work. Unparked 2026-09-02 — and it restores the keeper's delivery, which is
    R4's `300/310→50` record fix.
  * **T3 (shared steps feed): MOVES NOTHING.** The pullOutMapScr mover died too (the
    ScriptID/proc-fan rounds). Unparked 2026-09-02.
  * **T1 (entry_gwrites seed): still moves KQ6, in exactly its two known ways** — the
    sacredWater FP toll (+`rm380→rm300 has:40`) and the rm340 capture guards VANISHING
    (the unpriced 173-flip; the cost-only tier did NOT close it — `_reg_cost(443,{1})` and
    `_reg_cost(173,{1})` both price the scarf, so the mover is a FLIP-side walk treating
    the edge-set 173-write as a new free flip point, not a costing gap).

**Cure 1 SHIPPED @ `87fd3de`** (`entry_ggets`): the arming context's `gEgo get:`s ride
the arming (same walk, same recogniser as the state reader), necessary-merged; the toll
carry-in branch refuses an item every delivering machine of the crossing co-grants.
KQ6's capture is exactly `{flyToBeach@380 → sacredWater}`; suite 885/14/0/0, inert until
the seed lands — which is the point: the FP never gets to exist.

CORRECTED BY MEASUREMENT (2026-09-02): the T1 re-toggle with cure 1 in place STILL grew
the `has:40` spec — the refusal sat in the wrong pew. The actual row (probed, not
guessed): toll `one-visit-toll-pocket`, toll = FLAG 175 on `370→380`, pocket = {380}
itself, the water sourced INSIDE at 380 — the **carry-OUT** branch, whose "leavable
without taking it" conjunct (`_pocket_leavable`) counted the beach flight as a Y-free way
out. But `flyToBeach`'s arming does `(global0 get: 40)` — leaving via that exit you leave
HOLDING the water, which is the USER's ruling verbatim ("no way to get out without it").
Fix: `_edge_ggets_map` promoted to a shared memoized method; `_pocket_leavable` skips an
exit that hands Y over. The carry-in refusal stays (it guards the mirror case).

CURE 3, LANDED IN TWO HALVES (2026-09-02, after three instrument-poisoned rounds — the
probe scripts' `git checkout` restores were wiping the uncommitted info-dict key, so the
req composition ran STARVED and its "failures" were the instrument's):
  * **an arming-context write is an exit INVARIANT, not an exit effect**: `edge_meta`
    conjoins `entry_gwrites` onto every exit's `req` (registers the machine's own states
    never write). The context performed the write before the machine ran; every exit
    presupposes the value.
  * **a value the crossing presupposes is not a value it produces**: `_reg_cost`'s
    edge-set index skips a `sets{R:v}` whose row's `req` pins R to exactly v. Priced as a
    producer, freeCeleste's free-alts exit intersected "minotaur defeated" down to FREE,
    scarf-banned walks sailed through every 173-gated door, and the catacombs strandings
    collapsed from three edges to one (`edge_strandings` bisection: 340→370/405/440 →
    340→370). With the skip, seeded == seedless == golden minus the blessed-pending
    sacredWater line, measured both ways.
The SEED IS ON PERMANENTLY (opmodel); the diagnosis verdict on the park: the seed was
honest all along, and its three KQ6 movers were two consumer bugs (the grant-blind toll,
the presupposition-blind pricing) plus two already-dead drivers (T2/T3).

FULL-ROUND MEASUREMENT (six games): LSL2/KQ4/KQ5/LB2 byte-identical; KQ6 = the
blessed-pending sacredWater line only; GK1 = ONE spec, `rm455→rm800` growing from
`(has:60 ∧ has:69)` to five items (+VoodooCode1 +reconVeve +braceMold). ⚠️ REPORTED
LOUDLY: the growth is the reconVeve FP FAMILY — the three sketches' need sites are all
day-3/4 rooms (240/260/300, 50/200/205/340, 460), DEAD ERAS at the day-10 descent; they
count as "still needed past the edge" only because `edge_strandings`' `need & fwd_rooms`
walks the FLAT graph back out of the endgame. The named cure — NEED-LIVENESS AT THE EDGE
ERA (`_need_live`'s reading, applied to the carry-out test) — is its own future measured
round and would retire the reconVeve/braceMold declared FPs with it. Play-wise the wider
guard never bites (a day-10 player necessarily holds all five); it ships DECLARED, not
silent. R4 note: the record is now fully closed (every `→50` in-edge rewrites the
subject) yet the closure arm still emits nothing — the frozen-286 crosser finds another
road; next diagnosis round continues at the day-4 stage probe.

## §1.22 The hounfour exists now: a variable ScriptID is a fan (2026-09-01, R2/R3 round 1)

R2/R3's first gap was not scene boundaries — it was ABSENCE. The hounfour dispatches its twelve
scenes with `(self setScript: (ScriptID local1 0) self local0)` (`Hounfour.sc:163`), `local1`
assigned the scene script number in a selection ladder (`:651-900`), and every literal-only
ScriptID reader dropped the load whole: scripts 801-812 neither scoped into room 800 nor
produced one machine. `sHRoom8` — R2's point of no return and R3's killer — did not exist.

**`extract.var_script_values`** (the `var_room_values` discipline pointed at scripts) resolves
the ladder; consumed by THREE readers, one resolver ([[same-rule-two-places]]):
* `Extractor.scriptid_refs` — the scope fan (scripts 801-812 now walk into room 800; the
  guises' `get: 78/79` in the storeroom finally give BoarGuise/WolfGuise sources: `[800]`);
* the machine layer's `arms` collection — the cross-script arming records (export 0, the
  interpreter's own reading of a computed load);
* `_targets` (threaded a `home` script through `_scan_setscript`'s five call sites) — so the
  fanned arming matches the scene machine and becomes its ENTRY.

Result: rm800 goes 18 → **31 machines**, `sHRoom8`'s whole cast among them (`sDJKills` with its
four armings — R3's mechanism is REPRESENTED for the first time). Scripts 805/807/809-812 build
no machines and that is HONEST — their scenes are effect-free shells (verified against the
`has_effect` gate; the storeroom's items ride the handler scope, not the scene bodies).

R2/R3 remain RED — representation is not detection; the room-level walks do not yet cross scene
boundaries. New rows to verdict: `knife@reg759=1 -> [899]` (reg 759 = a lowered script-808
register written by `sHRoom8` state 0) and knife joining two edge rows (`800->899`, `750->700`)
— all three the forced-knife class on their face (day 7 cannot end without it, `rm540.sc:299`),
pending the measured round.

### §1.22 measured (real rebuild, all six)
**LSL2, KQ4, KQ6, LB2, KQ5 byte-identical** — the fan is corpus-clean under the KQ6 axiom. GK1
moves by exactly two accounted lines: `knife@reg759=1 -> [899]` and its REFUSED write spec —
the forced-knife FP class (declared under knife's CONFIRMED_SAFE). R1 and every §1.15-§1.19 row
unmoved; rm800's representation gain (18 → 31 machines, the guise sources) lives below the
frozen surface, waiting for the detector round.

## §1.23 R3's detector, DESIGNED: the multi-arm death sorter (case (c)) — not yet built

With the hounfour represented (§1.22), R3's whole chain is in the model:
* `sDJKills` (rm800) is FATAL and SLOT-ARMED with **four** guarded armings — the kill
  partition over `608` (flag 366, Gabriel robed), `607` (flag 365, Mosely robed) and `593`
  (Mosely present): every combination except the properly-robed ones dies (`sHRoom8.sc`).
* `_reg_cost(608,{1}) = {talisman, WolfGuise}` and `_reg_cost(607,{1}) = {talisman,
  BoarGuise}` — the robing already prices the guises through `sPutOnRobe`'s arming.

`death_traps` misses it by CASE SHAPE: its rows fire only for (a) an unconditional arming
(escape rows) or (b) exactly ONE fully-modelled arming (negation rows). A readable
MULTI-ARM sorter — several armings, none unconditional, none opaque — falls through.

### Case (c), derived
When EVERY arming is present and opaque-free: the death fires iff some arm holds, so a
survivable state is an ASSIGNMENT over the arms' named registers falsifying every arm.
Enumerate the (bounded) product of those registers' domains, evaluate each arm (a small
total evaluator over GAnd/GOr/GNot/CMP; any unevaluable atom ⇒ bail, the KQ4-ogre rule),
and emit one `({R: {v}, ...}, (frozenset(),))` row per surviving combination — the same row
shape case (b)'s register complements already use, priced by `_reg_cost` downstream.

### ⛔ The delicate half: the clock rule vs the player's own hands
Case (b) excludes registers the trap room's OWN machines write (the whale's sneeze timer —
a self-advancing clock must not read as an escape lever). For R3 that exclusion is wrong in
the other direction: `sPutOnRobe` writes 608 and it IS the escape — armed by the WolfGuise
verb, a PLAYER action. The derived discriminator: a register write is a CLOCK when its
machine's arming chain is cue/armer-driven; it is an ESCAPE LEVER when some arming traces to
a player source (`entry_sources`: doVerb/handleEvent). Must be derived against the whale
(KQ4) before shipping — resurrecting that FP is the named risk.

### Measured risk, stated before building
Case (c) fires wherever a multi-arm readable sorter exists — KQ5/KQ6 death rooms may gain
rows, and under the 2026-09-01 axiom ANY KQ6 movement is a bug to chase before shipping.

### §1.23 BUILT and measured — surgical (2026-09-01)
`_eval_guard` + case (c) shipped. Measured at the detector: **LSL2/KQ4 stay empty, KQ6's eight
and KQ5's five trap rooms byte-unchanged, GK1 gains exactly rm800 with
`req={607:{1}, 608:{1}}`** — "leave the hounfour only properly robed", priced at
{talisman, WolfGuise} / {talisman, BoarGuise} through `_reg_cost`. The clock projection held:
593 (Mosely present, cue-driven) never pins a row; the whale games gained nothing.

**R3 remains RED, and the remaining distance is now exactly one thing.** The trap prices the
guises for every banned walk out of rm800 — but the oracle wants the GUISES named, and no
room-level detector can: their sources (the storeroom scene) and the demand (Grace's-room
scene switch) are the SAME room. Scene boundaries — the original R2/R3 diagnosis — are the
one remaining gap, with everything beneath them (the scenes exist, the sorter is modeled,
the survival is priced) now in place. R2 likewise: `timeForCeremony` at `sHRoom8.sc:71` is
an intra-room switch; its deposit demand (flags 280/281 ← rm455) crosses ROOMS and may be
catchable sooner — the trap-adjacent window machinery over 455→800 is the nearer target.

### §1.23 surface delta — TWO VERDICTS OPEN (for the USER)
Five games byte-identical. GK1: `talisman` joins `softlock_items` via a new edge_strandings
row `[rod, talisman]` with an APPLIED guard `rm455->rm800: (has: 60) (has: 69)` (+ rm455
setscript placement). The facts: `required[rod] = {455, 710}` — 455 IS the confessional
deposit, R2's own demand, already in the model; `required[talisman] = {800, 899}` — the robing
and the throw; both sourced in Africa (rod 710, talisman 720 + the EndGame re-grant at 899).
**SETTLED FROM THE SCRIPTS the same day (the USER: "can you figure that out from the
scripts?" — yes): the whole row is an FP, both halves the FORCED class.**
* The descent is gated on story flags 273∧271 (`sExitElevator`, `rm455.sc:117`), not items.
* The return (`sHRoom6` verb 8) is refused only under flag 351 — deposits-made-and-descended —
  and `timeForCeremony` (set in Grace's-room init, `sHRoom8.sc:71`, never cleared) takes
  dispatch precedence thereafter. So the deposit stays fixable until Grace's room: R2's pin
  stands verbatim.
* The TALISMAN cannot be absent on day 10: BOTH Africa-exit cutscenes grant it (`get: 69`
  immediately before `newRoom: 216` — `rm720.sc:1040`, `:1285`) and Africa (700↔710↔720,
  + the death room) has no other exit.
* The ROD cannot be absent either: `keyWorks` — the only opener of the wall into rm720 — is
  armed exclusively from `rodCode`'s success arm (`rm710.sc:2303-2328`), and `rodCode` answers
  only the rod's verb 76. You cannot reach the wolf, hence cannot leave Africa, without having
  taken the rod; and nothing puts it before the 455 deposit itself (`put: 60` = the deposit,
  verb 76 on the bench, `rm455.sc:826`).
Declared: `talisman` → CONFIRMED_SAFE with this proof; the rod's appearance in the caught set
is FOR THE WRONG MECHANISM and R2's pin (the deposit + the signal-device pair) remains the
authority. The applied 455→800 guard guards two items every player necessarily holds —
harmless, pointless, and accounted.

## §1.24 R3's last mile, DESIGNED: scene carry-ins (not yet built)

Every input is now modeled; what remains is one detector. The facts, all recorded structures:

* the DEMAND: the §1.23 trap row at rm800 (`607/608 ∈ {1}`), whose writer machines
  (`sPutOnRobe`/`sMoselyPutOnRobe`) arm into slot `('O','sHRoom8')` — the demand SCENE is
  script 808 — and whose `_reg_cost` names the guises;
* the SOURCES: the guises are HANDLER gets scoped from script 807 (the storeroom scene's
  doVerb handlers; its machines are honest effect-free shells) — the source SCENE is 807;
* the SEPARATION, and this is the piece that closed tonight: `sHRoom8`'s own modeled write —
  reg 759 (`timeForCeremony`, property-lowered), set at scene entry and NEVER cleared — is a
  monotone latch that shuts the hub: the Hounfour dispatch cond (`Hounfour.sc:176`) routes to
  the ceremony (899) whenever it is set, before ever reaching the scene ladder. Once the
  demand scene runs, no path re-offers the source scene. (The arming-closure check agrees:
  from `sHRoom8`, the recorded graph reaches only `{sEnter, sMoselyShowsUp}`.)

V1 (`scene_carryins`): for each death-trap row whose survival registers' writers arm into a
scene slot S of script B, and whose value-cost items have in-room HANDLER sources in a
different script A — emit a carry-in unit for each such item when the demand scene latches a
monotone register (written at B's entry, never cleared game-wide) that gates the room's own
scene dispatch. Everything from recorded structures; wire it into `snapshot.py` (a detector
outside the snapshot is not watched) and extend `test_gk1_ground_truth`'s `rows_by_det`.
Measured risk: fires only where death-trap rows already exist (rare); KQ6/KQ5 trap rooms are
the axiom-watch set.

### §1.24 BUILT — R3 IS CAUGHT (2026-09-01)
`scene_carryins` shipped exactly as designed. On GK1 it emits precisely the two rows —
`BoarGuise@rm800/scene[808]<-[807]`, `WolfGuise@rm800/scene[808]<-[807]` — and **R3 flips
GREEN**: the two guises are caught as carry-ins to Grace's room. The second real GK1 row
caught (after R1), the first through scene machinery. Its KNOWN_RED entry is retired (GK1's
declared reds: 5 → 4; remaining: the FP-set pair, R2, R4).

Measured: five games move by EXACTLY one line each — the new frozen key `"scene_carryins": []`
(a detector joins the snapshot unconditionally; the confession block forbids the `if rows`
clause) — and the three goldens' one-line refreshes are DECLARED awaiting the USER's bless,
the 2026-08-14 precedent shape. GK1 additionally gains its two rows and the two units.

R2's remaining distance after this round: the deposit flags (280/281) are written at rm455 —
a DIFFERENT room — so the scene-carryin shape does not cover it; its point of no return is the
same latch (759), but the demand is a FLAG PAIR set elsewhere, not an item held. The R2
detector is the flag-twin of this one: a death-sorter register (351 at rm899, EndGame:637)
whose only writers live behind the latch. Same skeleton, register-valued.

## §1.25 The COST-ONLY register tier (2026-09-01, R2 round 2)

The R2 probe found the model already KNOWS everything and prices NONE of it: the rm899 trap
rows demand `593 ∈ {1}` (flag 351), `sEnterFromElevator`'s write of 593 is guarded
`522!=0 ∧ 523!=0` (flags 280/281, the deposits), and the 522 deposit's own handler guard
carries `own(rod)` — yet `_reg_cost(593,{1})` came back EMPTY. Root: 522/523 are compared in
no movement guard, so `gating_registers` never promotes them, and every cost table is gated
on the promoted set — their writes never seeded `_inroom_own`, their atoms dropped from every
`guard_reqs` read, and 351 folded to free.

⛔ The promotion cure was measured and REVERTED TWICE on 2026-08-28 (196 LSL2 golden lines,
oracle items lost — widened projections eat findings through the intersections); its comment
already names the verdict: "the write-chain gate stays a cost-model question." So this round
builds exactly that: `support_registers(em, regs)` — a register compared in the guard of a
recorded write of a priced register, and itself written, joins the COST tier, to a bounded
fixpoint; object-valued globals refused as promotion refuses them. The tier
(`self._cost_regs`) widens ONLY `_inroom_own` seeding, `_cogrants`, the `guards` fold and the
`_wbranch`/`_wbranch_dom` tables; `_inroom`/`_rstep`/`_emeta`/projections stay on
`self.regs`. Consumers audited: `_psucc_joint` checks deps only for tuple registers,
`_gate_joints` filters `S not in regs`, `priced` only grows (conservative). The `!=0`
spelling carries domain-less because minted flags are BOOL_GLOBALS (`guard_reqs`'s own rule).
The write-harvest is factored into `_written_registers` so promotion and support cannot
drift ([[same-rule-two-places]]).

Probe after: GK1 +23 cost-only registers; `_reg_cost(593,{1}) = {rod}`;
`_wbranch[(593,800,1)]` deps now `{522:{1}, 523:{1}, 593:{0}}` at cost `{rod}`; movement
tables byte-identical in structure.

⚠️ MEASURED BYTE-IDENTICAL ON ALL SIX TITLES (2026-09-01, worktree @ ca8b98a vs patched
tree, full snapshot surfaces): LSL2/KQ4/KQ6/KQ5/LB2/GK1 all 0 changed lines — the KQ6 axiom
holds, and GK1's own surface does not move either, so no existing detector catches R2 from
pricing alone. Control run per [[instruments-lie-run-the-control]]: the worktree (sharing
`build/` — safe, the model cache key hashes every non-test source file) answers
`_reg_cost(593,{1}) = []` with no `_cost_regs`, so the null diff is a real null, not a
cache-poisoned one. Same standing as `_chain_branch_costs`: a PREREQUISITE invisible on its
own — R2's detector (the flag-twin of `scene_carryins`) is what will consume the price.

### §1.27 BUILT — the closure stands; R4's last mile is the PARKED round (2026-09-01)
`_pclose` + the producible-dead-end arm shipped in `register_value_strandings` (counter
flips only; b0 only where PRE-confinement is sound). Three closure bugs found and fixed
in-flight, each a lesson worth its comment:
  * edge SETS only landed when the target room was NEW — PV[prevRoom] kept a handful of
    first-arrival values and every `prev == N` band (GK1's rm500 fan → the goal) stayed
    shut;
  * POST carried the FLIP register's pre-flip values — `270→280`'s day gate satisfied
    after the day-4 flip; cured by confining R to its FORWARD-reachable values (a counter
    may not be wound backwards — `_counters`' own rule);
  * a carried scratch value survived to any use site — `178 == 12` (Cazaunoux's subject)
    satisfied the flag-44 write at rm50 post-flip; cured by the restricted-projection
    refinement: a (room, value) pair is usable only if reachable within the CLOSURE'S
    rooms in that register's own projection (over-approx preserved: the closure's rooms
    over-approximate). Debug-gated writes are excluded from the tables outright.
With these, the GOOD-side closure reaches the goal (rooms#55, exactly the sealed band
missing) — the arm is live end to end.

⚠️ COST, learned the hard way: the first full-detector run OOM-killed at 4.2GB on the 5GB
WSL2 box (the QFG2 lesson — run bounded). The fix went through three shapes before the
structural one: the killer was not any single walk (`MemoryError` on 77-pair sets was the
tell) but ~50 rooms-growth generations × ~130 registers of regenerate-and-free churn
fragmenting the heap. The closure is now TWO-PASS — pass 1 unrefined, pass 2 with every
restricted walk computed ONCE against pass 1's frozen rooms (a superset of the refined
result, so the walks stay over-approximations) — plus: the S-candidate loop skips
registers nothing in the tables compares (`gate_regs`); walks that would still be huge
fall back to no-refinement, loudly; and a cross-closure walk cache rides on the model.

⭐ AND ONE REAL SOUNDNESS CATCH from the same round: a PRE (holdings) closure must NEVER
be refined. Refinement only removes, and removing from the seed of what the crossing
player may hold UNDER-approximates the player — the unsound direction for every claim
built on top. `refine=False` is mandatory there, and doubles as the fast early verdict
on the POST side (pass 1 is a superset: a goal missing from it is missing, full stop).
Five games' snapshots survived the arm unchanged and byte-identical (LB2's act counter
and KQ6's 162 both ran it: zero rows).

⭐ THE ARM'S FIRST ROW WAS AN FP, AND ITS CURE IS THE RECORD'S OWN DISTINCTION. The first
complete GK1 run emitted `reg514==[0]@seal123=10->[680]` — flag 272 (the confessional
key-scene gate) claimed stranded at the day-10 flip. Per-seed bisection: from rm205 and
rm750 (the real day-9→10 ends) the 272-less crosser provably still wins; the only failing
witness was rm800 — whose "step into 10" is the ceremony's own `(= day 10)`, an UNORDERED
clamp the may-not-wind-back rule fans into steps from every value. A forced write is not
a point of player choice: the projections fabricate a player standing at the clamp with
state the game never lets them carry there. Cure: `_build_product` now records the fanned
pairs (`_clamp_steps`) at the moment it synthesizes them, and the closure arm refuses
clamp rooms as flip witnesses. No thresholds — the synthesis site itself is the marker. R4 still does not fire, and the remaining leak is
the RECORD, not the closure: three in-edges of rm50 lack the subject-set —
`300→50`/`310→50` carry a set-less FLAT meta beside the machine edge (the edges are NOT
machine_delivered though `sTalkToKeeper` K=9 exits there writing 178:=32 — the
certain-only-delivered gap), and `460→50` is delivered but `askBartender`'s exit writes
nothing (the subject write sits in its ARMING HANDLER — the entry-writes composition).
Both are ⛔ THE PARKED DOOR-CLOSER ROUND (§1.21: entry_ggets / certain-only delivered /
edge-set costs — the three KQ6 movers, each diagnosed as a FIX). The park's own terms are
met — something real hangs on it — so R4 now WAITS ON THE USER'S BLESS to unpark that
round; the closure emits zero rows until then, measured.

## §1.26 R2's detector, DESIGNED: the register carry-in (2026-09-01)

Why `register_value_strandings` cannot carry R2 as-is, diagnosed to the line:
  * its causality half (`fix_in_b`) and its freeze conjunct both read `_inroom` + edge sets
    and NEVER `_rstep` — and 593's write is pinned by its own `¬593` conjunct into `_rstep`
    (`(0,1)@800`), invisible to both ([[same-rule-two-places]], the write tables split). So
    the row dies at "never fixable before". Fixing the table-blindness alone then kills it
    at the freeze instead: the region DOES contain the step, at rm800.
  * the step is honestly dead post-latch — `sEnterFromElevator` runs only on the 455→800
    ride — but its armer `('sHRoom6', 0)` is an UNRECORDED Script object, so
    arming-reachability cannot prove it ([[arming-floor]]: ignorance stays permissive), and
    dep-satisfiability founders on carried values (the 522-projection permissively reaches
    (800,1), and the "deposited ⇒ 593 already 1" invariant is a joint fact projections
    cannot see).

What CAN carry it is R3's own scene-latch argument, inverted to the writer side — the
register twin the §1.24 tail predicted. All recorded (probed 2026-09-01):
  * the demand: a `death_traps` row at Y=899 requires `593 ∈ {1}` to survive;
  * the writers: every writer of 593→1 in the game is a machine of script 806 at X=800;
  * the seal: script 808's machine at X writes the monotone latch 759 (one recorded value,
    no steps, in `edge_req_regs[800]`), 808 ≠ 806 — once latched, the sorter scene owns the
    room and 806's machines never run again;
  * the crossing: the trap's own in-edge (800→899) pins 759 to the latched value — the seal
    necessarily precedes the demand.
Emit: crossing into Y at R∉vals is fatal and frozen — the register carry-in. Value-0 demands
skip naturally (no writers ⇒ nothing to seal ⇒ initial value, free). Rows land in the SAME
`scene_carryins` snapshot key (register-shaped formatting), so the five clean games move by
ZERO further lines and the pending three-golden bless stays exactly one line each.

Build order: (1) the detector branch in `scene_carryins`; (2) the `_rstep` table-blindness
in `register_value_strandings` is a REAL standalone bug — fix separately, measure separately
(it can retire OR create rows on the stepped registers of other games; do not confound).

### §1.26 BUILT — the rod half of R2 (2026-09-01)
The register branch shipped as designed, with the latch test factored into ONE closure both
branches share. GK1 emits exactly one new row — `rod@rm899/scene[808]<-[806]`
(`register-carry-in`, writer_rooms=[800]) — and the two R3 rows are byte-identical. The five
clean games all stay `[]`. Ground truth: 8/4, the SAME four declared reds, and the rod row
adds no unexpected unit (the rod was already caught by the §1.23 elevator guard, wrong
mechanism; this row is the RIGHT mechanism). R2's check stays red on its device half alone:
`_reg_cost(593,{1})` prices the rod through 522, but 523's write guard reads `opaque()`
where the device `put:` sits — a VARIABLE item argument, and GK1 has zero recorded
`item_menus`, so the pair {signalDev, signalDev2} has no recorded structure yet.

The device half, DIAGNOSED TO THE WORD (2026-09-01): `bench1::doVerb`'s 281-write sits
under `Switch(param1) → Case 60 → If flag272`, and case 60 is the devices' shared
`message` property (`signalDev.message = 60 = signalDev2.message`; `rod.message = 76` —
case 76 is the rod's deposit, whose literal `put: 60` is where `own(rod)` comes from).
`vocab.doverb_item_messages` already lowers exactly this shape — "using item X as the
verb" — but keeps only messages that UNIQUELY identify one item, so the shared 60 is
dropped and the case guard stays opaque. Two rounds remain, measured separately:
  * ROUND B — shared messages become GROUPS: `doverb_item_messages` returns
    message → tuple-of-indices; the extract consumer lowers `== param1 msg` to an
    OR-of-own over the group (the verb-icon exclusion unchanged). KQ6's spaces don't
    overlap (its own docstring), but measure all six.
  * ROUND C — the register branch learns GROUP rows: walk one recorded dep hop from the
    sealed writer (`_wbranch` deps: 593←{522,523}); per dep, singles from `_reg_cost`
    and or-own GROUPS read from the dep's writers' guards. Emit `item_group` rows; the
    snapshot string and the ground-truth caught-builder gain the group spelling
    (the oracle's pair unit is `frozenset({signalDev, signalDev2})`). The cost model's
    flat frozensets stay untouched — alternatives live in the ROW, not in `cheapest`.

## §1.27 R4's detector, DESIGNED: the post-flip producible closure (2026-09-01)

Re-probed after §1.25/§1.26 shipped, the R4 chain is now FULLY RECORDED — the two links
§1.10.4 called open have both closed under other rounds' work:
  * the return edge `50→280` IS priced: `emeta[(50,280)].req = {12:[280], 178:[...],
    123:[0..3]}` (return-to-sender, 2026-08-30) — and the 123-projection reaches rm280
    at days 0–3 ONLY. Cazaunoux's house is provably sealed at day 4 in the model as it is.
  * flag 74's write guard carries the topic gate — `… ∧ (286!=0 ∨ 289!=0)` (the Teller
    band lowering) — invisible to `guard_reqs` only because an OR honestly constrains
    nothing. Flag 44's write needs `178==12` (written only at rm280); flag 47's needs
    `123==5` (day 5 — circular: day 5 needs day 4 to end, which needs the trace ← 74).
  * the demand end is recorded too: flag 15's day-4 arms cost items {…, 26=tatooTrace, …}
    and deps {689/490/278/469: [1]} — exactly §0's day-4 flag set.

What is missing is ONE construction, and it is not a joint (the docs' old verdict stands —
this is a CHAIN): the **post-flip producible closure**. For a flip (R, w) and a carried
value S==b: over-approximate what the crossing player can ever produce, as a mutual
fixpoint of rooms × (register, value) pairs × items over the recorded write branches:
  * PV0 = each register's values attainable at the flip room in its own projection
    (S restricted to b); Rooms0 = the flip room;
  * a write (S2, room, v2) joins PV when room ∈ Rooms and every MUST-dep has an allowed
    value in PV; an item joins when some source's room ∈ Rooms and its guard's deps ⊆ PV
    and its cost items ⊆ items; a room joins Rooms when some in-edge's req reads PV-allowed
    values and its alts are item-satisfiable.
Monotone and over-approximating, so an UNPRODUCIBLE verdict is sound. Bounded: cost-tier
registers × small domains × ~80 rooms. The detector conjunct: the crossing at S==b is a
DEAD END (no goal room enters the closure) while the S∈acc crossing reaches the goal
(the existing flip-side conjunct), and the fix existed pre-flip (existing causality half).
For R4: 286==1 never enters the closure (rm280 outside Rooms), 289==1 never (needs 123==5,
which needs the 4→5 step, whose gate 15==1@day4 costs item 26, whose source guard needs
74, which needs 286∨289 — the cycle the fixpoint never closes), so the trace, the day-end,
day 5's rooms and every goal fall out — the row names flag 44 at the day flip, which is
exactly the oracle's ask (`register==286` among register-stranding rows).

### §1.26 SHIPPED — R2 IS CAUGHT, rounds B+C (2026-09-01)
Round B (shared messages → groups) measured alone first and EXPOSED A FLAT FOLD: the two
devices surfaced as SEPARATE singleton rows, because the cost channel seeds `_own_positive`
— the flat reading — so `own(19) OR own(20)` priced as two necessary singles (the whale's
flat-reading lesson, in the cost channel). Census of the two readings at cost sites:
LSL2 0, KQ4 341, KQ6 8, KQ5 25, LB2 8, GK1 30 — so the ROOT fix (cost sites →
`_own_required`) is a future measured round of its own; recorded as a known gap beside
`register_value_strandings`' `_rstep` blindness.

Round C therefore prices the register rows STRUCTURALLY and locally: `_chain_price` in the
branch — any writer suffices (intersect over writers and values), a writer pays its guard's
NECESSARY owns (`_own_required`) plus its recorded deps' price (`guard_reqs` over the cost
tier, bounded depth 3, memoized, cycle-guarded), and a pure OR-of-OWN (`_or_own_groups`,
positive polarity only) is an ALTERNATIVES GROUP — one `item_group` row for the set, never
per-member singles. KQ5's 42-item message-4 group never arises: the class-default exclusion
(Round B) kills it at the map.

MEASURED (worktree @ cc73660, B+C together): five surfaces 0 changed lines, GK1 exactly ONE
— `signalDev|signalDev2@rm899/scene[808]<-[806]` joins `scene_carryins`; the items-union
is UNCHANGED (group members are not individually claimed). Ground truth 9/3 — **R2 GREEN**
(`rod` + the pair as one alternatives unit), R2's KNOWN_RED entry retired (gk1 declared
reds 4 → 3: the FP-set pair and R4). KQ6: zero shared messages (census) and 0 diff lines —
the axiom holds structurally and by measurement.
