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
