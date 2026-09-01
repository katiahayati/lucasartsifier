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
