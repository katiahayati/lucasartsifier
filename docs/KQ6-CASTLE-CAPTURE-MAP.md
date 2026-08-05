# KQ6 castle capture mechanism — static map (measured 2026-08-05)

Scouted from the pristine decompile (`build/kq6_patch_v21/ir/src`) for the treasure-corral
letter seal (the standing KNOWN_RED in `test_toll`). Every claim carries file:line. This is
the measurement base for the capture-seal detection rule; the guard oracle rows stay the
verdict authority.

**Root fact:** TWO region objects, TWO independent flag banks, both spelled
`setFlag:/clrFlag:/tstFlag:` with a *selector number* first arg (`rgCastle.sc:397-417`):
**709 = `rFlag1`, 710 = `rFlag2`, 711 = `rFlag3`** (`rgCastle.sc:235-237`; cross-check
`rgCastle.sc:424` writes `rFlag1 $2000` vs `rm781.sc:403` `setFlag: 709 8192`).

* `(ScriptID 80 0)` = class `rgCastle` used as an object (`rgCastle.sc:233`), region for
  rooms 700-880 + 180 + 743 (`rgCastle.sc:330-353`, `Main.sc:779-808`).
* `(ScriptID 81 0)` = class `RgBasement of rgCastle` (`RgBasement.sc:3,21`) — a SECOND
  region with its OWN rFlag storage, attached to rooms **840 710 720 770 820 780** only
  (`RgBasement.sc:69`, `Main.sc:805-807`).
* `guard1` = `(ScriptID 80 5)`, `guard2` = `(ScriptID 80 6)` (`rgCastle.sc:21-22,510,538`)
  — the ONLY two `GuardDog` instances in the game.

## 1. Guard posting

### 1a. Roving patrol (region 81 bits) — rooms 710/720/840 only
`RgBasement.rFlag1`: `$0001` guard1 posted · `$0002` guard2 posted · `$0004` permanent
alert · `$0008` 840 shortcut taken · `$0010` panel-open-in-710 (transient).

| site | who | gate |
|---|---|---|
| `RgBasement.sc:26-33` | guard1 (view 725, `guardPath1`) | `tstFlag: 709 1` — re-runs on every entry (`RgBasement.sc:68-72`, `Game.sc:544-549,726-735`) |
| `RgBasement.sc:34-41` | guard2 (view 727, `guardPath2`) | `tstFlag: 709 2` |
| `RgBasement.sc:93-111` `startGuard:` | either | `& rFlag1 $0001/$0002`, no live mover |
| `rm720.sc:82-101` | both planted, `okToCheck: 1`, `moveOtherGuard 1` | `tstFlag: 709 4` (permanent alert) |
| `rm720.sc:288-302` | guard1 through the guard door | player opened it (`rm720.sc:702-711`) |

Patrol: `guardPath1` 840→720, `guardPath2` 720→710→840 (`RgBasement.sc:17-18`);
`endType 2` when `$0004` (`RgBasement.sc:167-170`). Danger windows: guard1 waypoints 4..10,
guard2 3..13 (`RgBasement.sc:120-131`); rm840 installs its own `CheckCode`
(`rm840.sc:103-104`). Posting triggers: 1-in-6 random on entering 720 (`rm720.sc:145-152`)
/ 710 (`rm710.sc:226-234`); `doLoiter` on `loiterTimer` expiry (`RgBasement.sc:74-91`,
armed to 36 at `RgBasement.sc:55-66`, ticked at `rgCastle.sc:263-269`); wedding-music
escalation `weddingMusicCount >= 3` → posts + `$0004` permanent (`rm840.sc:228-247`,
`rm710.sc:305-328`, `rm720.sc:158-206`, `RgBasement.sc:141-158`); `weddingCorralCrunch`
(`rm840.sc:459-471`, entered when `$0004` and not `$0008`, `rm840.sc:130-136`).
Rooms 770/820/780 load region 81 but DISPOSE guards on entry (`rm770.sc:105-111`,
`rm820.sc:91-100,176-184`, `rm780.sc:161-170`).

### 1b. Static/scripted guards (region 80 flags)
| room | site | gate |
|---|---|---|
| 850 | `rm850.sc:230-256` (sets `local1:=1`) | `(or (not rFlag1 $0200) (and rFlag2 $0001 (not rFlag3 $0100)) (not rFlag1 $0080))` |
| 850 | `rm850.sc:778-786` `walkGuardsOnScreen` | from init cond `rm850.sc:280-288`, `warnUser 2` (`rm850.sc:406-418`) |
| 860 | `rm860.sc:137-155` (`guardPatrol` + `guardCheck`) | **unconditional — always two guards** |
| 870 | `rm870.sc:284-297,316-330` `walkGuardOn` | `guard2Timer` (`rgCastle.sc:305-318`) or `rm870.sc:86-89` |
| 880 | `rm880.sc:126-152` `guardsPatrol` | nightingale not yet delivered (`(global9 at: 27) owner: != 730`) |
| 781 | `rm781.sc:393-395` `they_reBack` | `rgCastle rFlag1 $0001` at entry (`rm781.sc:186-196`) |
| 730 | `rm730.sc:159-192` | `rFlag3 $4000` or `tstFlag: 709 512` |
| 740 | `earlyGuest.sc:24-26` (script 741) | `(not (tstFlag: 709 2))` — pre-wedding |
| 730 | `enterFromBasement.sc:22-27` (script 732) | `(not (tstFlag: 709 2))` |

## 2. The long-route trigger (NOT the treasure room)
rm770 (treasure room, reached only 710→770, `rm710.sc:260-262`, `rm770.sc:93`) CLEARS the
guards (`rm770.sc:105-111`). `doTreasureDoor` is in **rm710** (`rm710.sc:418-489`,
`treasureDoor rm710.sc:665-700`), refused while guards up (`rm710.sc:686-692`), suspends
`loiterTimer` while the panel is open (`rm710.sc:432-434,477-481,759-761`).

The seal chain is the **nightingale hand-off / guardTimer**:
1. `rm880.sc:527` `guardsTakeBird` state 7: `guardTimer: 301 setFlag: 709 512` (bird →
   owner 730; guards leave post for 301 real-time seconds).
2. `rgCastle.sc:291-304` (ticked per second, `rgCastle.sc:250-262`): timer hits 0 →
   `(|= rFlag2 $0001)` = **guards are back**; if in 850/880/781 → `warnUser: 2`; if in
   850 already flagged → instant `spotEgo:`.
3. `rm880.sc:49-56`: re-enter 880 with `rFlag3 $0200`, `rFlag2 $0001` clear, `rFlag1
   $0002` clear → `guardTimer: 0 setFlag: 710 1` (instant).
4. Accelerator `rm850.sc:174-182`: `has: 20` + dagger at 870 + `rFlag3 $0200` clear +
   `guardTimer > 30` → `guardTimer: 30`.
`rFlag2 $0001` clear sites: `rm850.sc:312`, `rm850.sc:779`, `rm880.sc:1457,1505` — nothing
else. `dungeonEntered` is an enum 1/2/3 (`rm710.sc:42-78,166-214`; forced 3 by capture:
`rgCastle.sc:424`, `throwInDungeon.sc:34`, `rm880.sc:1441`; read `rm820.sc:108,126,558`).
`resetGuard` callers (masks literal): rm780:163(1)/168(2), rm720:268(1)/269(2),
rm820:93/177(1) 97/181(2); direct clears rm770:105, rm820:100/184, rm710:296/300/337,
rm720:200, rgCastle:532,568-571.

## 3. The catch
`GuardDog.doit` (`rgCastle.sc:204-221`): `okToCheck` ∧ `checkCode` → `handsOff` +
`(global2 spotEgo: self)`. `checkCode` installed per room by `rgCastle.setupGuards`
(`rgCastle.sc:366-395`, cleared each room change `rgCastle.sc:358`): `rm720.sc:774-789`,
`rm840.sc:1086-1135`, `rm710.sc:801-820`, `rm850.sc:1537-1561`, `rm860.sc:616-630`.
`CastleRoom.spotEgo` (`rgCastle.sc:129-137`) → room's `spotEgoScr` else `guardsGetEgo`
(`rgCastle.sc:420-508`, export 4): approach scene → state 6 **`newRoom: 820`**
(`rgCastle.sc:503-504`); its dispose sets `rFlag1 |= $2000`, `dungeonEntered: 3`
(`rgCastle.sc:423-427`). Every capture terminus → 820: `rgCastle.sc:504`, `rm710.sc:628`,
`rm720.sc:375`, `rm730.sc:429,456,887`, `rm781.sc:403-405`, `rm840.sc:447`,
`rm850.sc:761`, `rm860.sc:440`, `rm870.sc:346`, `rm880.sc:1443`,
`enterFromBasement.sc:116-118`.

Avoidability: 710/720/840 avoidable (windows + shared-control tests; guards self-retire
`rgCastle.sc:531-533,567-572`; saving refused while posted `rm710.sc:342-368`,
`rm720.sc:222-249`, `rm840.sc:288-315,1136-1157`). **850 with `rFlag2 $0001`: NOT
avoidable** — `rm850.sc:280-288` unconditionally arms `walkGuardsOnScreen`, state 3
(`rm850.sc:801-812`) captures UNLESS `(vizierDoor cel:)` ≠ 0, which holds only when
`global12 == 781` (`rm850.sc:257`); escaping via 781 sets `rFlag1 $0001` → `they_reBack`
next 781 entry. 860 from 870: not avoidable (`rm860.sc:150-154` → `rm860.sc:366-378`);
from 730 you must hide (`hideEgo`). 740 pre-wedding: not avoidable
(`earlyGuest.sc:47-49`). 781 with `rFlag1 $0001`: not avoidable (`rm781.sc:186-196`).

## 4. rm820 (dungeon)
Entry split `rm820.sc:91-119`: `rFlag1 $2000` → `throwInDungeon` (script 821), door
locked (`rm820.sc:103`); else `enterDungeon` (`rm820.sc:143-198`), unlocked; ghost boy
chain when `dungeonEntered ∈ {1,2}` and `rFlag1 $8000` clear (`rm820.sc:106-115`).
Exits: walk out if unlocked (`rm820.sc:200-256` → 710); skeleton key (44) escape
(`rm820.sc:643-651,503-504`, sets `709 4096`); Jollo rescue once (global flag 10 +
`rFlag1 $4000` unset, `throwInDungeon.sc:96-104` → 278). **Dead ends:** `noWayOut`
(`rm820.sc:324-419` = Restore/Restart/Quit) via `throwInDungeon.sc:135-137`; `searchEgo`
confiscates the key when `rFlag1 $1000` (`throwInDungeon.sc:86-89` `put: 44 820`) — **a
second capture after a key escape is unwinnable**; `boyGhostScript.sc:96-107` = second
noWayOut (no handkerchief). `rFlag1 $2000` cleared on return to 710 (`rm710.sc:165`).
Saladin is NOT here: rm730 (`rm730.sc:1124-1163`) / rm740 (`rm740.sc:308-313`); letter
shown via verb 61 → `showLetter` (`rm730.sc:720-800`), sets `rFlag1 $0400`, **consumes
the letter** (`rm730.sc:783`); branch gated off once `tstFlag: 709 512`
(`rm730.sc:1126-1131`).

## 5. The letter (item 20, owner 780)
Got in **rm781 only**: trunk (`rm781.sc:891-895` → `openTrunk` `rm781.sc:201-274` →
`papers_ChestInset` → `(global0 get: 20)` `rm781.sc:1103-1107`). Consumers:
`rm870.sc:454-459` (needs `rFlag2 $0004`), `cassimaScript.sc:706-713`,
`rm730.sc:1146-1149` (Saladin, destroys). Routes into 781: (a) rm850 control `$2000` →
`newRoom: 781` (`rm850.sc:346-348`); (b) secret hallway 720→800→810→781
(`rm720.sc:581`, `rm800.sc:98`, `rm810.sc:117-127,270-280`). Guards-posted kills (a) —
850 is capture-sealed and `vizierDoor.doVerb` refuses/`spotEgo`s under `local1`
(`rm850.sc:1146-1173`) — and (b) needs `rFlag1 $8000` (ghost boy, `rm720.sc:660-670`,
`boyGhostScript.sc:110`), refused once `rFlag1 $0002` (wedding).

## 6. Recognizer discipline (overfire/underfire table)
Must fire: 850 (flag-gated, sealing); 740 pre-wedding (`earlyGuest`); 730-from-basement
(script 732); 781 under `rFlag1 $0001`; 860-from-870 (prev-room-conditional!).
Flag-keyed-only rules MISS: 860 (unconditional), 880 (item-owner gate), 870
(`guard2Timer`). Must NOT fire: `guardsScript.sc:161-183` (keyhole Views, name collision
with real exports); `rm781.sc:596-640` + `rm730.sc:1005-1007` tempGuards (decorative
Actors); `rm740.sc:955-957` `guard3`/`saladin` (doVerb responders, no checkCode);
`rm790.sc:350-352` `doLoiter` override (vizier duel — a `loiterTimer` recognizer
overfires here); ambient patrols (`rm850.sc:891+`, `rm880.sc:942+`).

Suggested predicate: room R capture-sealed under condition C iff R's arrival flow (init or
a script it unconditionally sets) reaches the capture dispatch (`spotEgo:` /
`setScript: (ScriptID 80 4)`) under C, where C may include region-object flag bits AND
prev-room tests (850's `vizierDoor cel` proxy = `global12 == 781`, `rm850.sc:257`).
Mere pursuit hazard (okToCheck+checkCode posted patrols, 710/720/840) is NOT a seal.
