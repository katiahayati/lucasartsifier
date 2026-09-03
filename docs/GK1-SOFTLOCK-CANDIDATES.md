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
