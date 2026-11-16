# GK1 patched-game test plan — v5 (the bayou ritual and Grace's room)

**v5 INSTALLED 2026-11-16** (`build/gk1_patch_v5`), replacing v4.
- **Change:** Grace's room is now refused at the hallway keypad, when you use the key or press it,
  instead of inside the scene. v4's refusal there was invisible, and dismissing it crashed the
  game (G2 below).
- **Files:**
  - 455, 490 and 720 are byte-identical to v4.
  - 800 changed (it gained the keypad refusal).
  - v5 doesn't touch 808, so Sierra's own `PATCHES/808` is back in the copy.
- **Install check:** all 14 written files were checked byte for byte; 0 mismatches.
- ⚠ **Restart ScummVM before block G, and don't load a save made inside the hounfour under v4.**
  The hounfour script changed under it.
- **Revert:** `build/gk1_patch_v4` is one copy away.

Game: `~/sierra/patched/gk1`.
Stock control, if a result looks wrong: `~/sierra/Games/gk1`.

**Console = Ctrl+Alt+D.** Rules:

1. **`room N` acts only after you close the console** (Esc). Wait for the room to draw, then
   reopen the console for the rest of the lines.
2. **After closing the console, move the mouse off the icon bar.** GK1's bar runs its own loop,
   which pauses the room. It fooled my harness once.
3. **Flags:** run `gameflags_init 127` once per session. After that, `sf N` sets flag N,
   `cf N` clears it and `tf N` reads it.
   - Self-check, once: `sf 351`, then `vv g 148` must print an **odd** number. Then `cf 351`.
   - If `sf` doesn't exist, or the check fails, use the global/bit columns in the flag table
     below: read the global with `vv g <global>`, then write it back with the bit added or
     removed.
4. **Items:** `send GKEgo get N`, `send GKEgo put N`, `send GKEgo has N`.
   - If `GKEgo` isn't found, `vv g 0` prints Gabriel's address (something like `0012:0034`).
     Use that address in place of `GKEgo`.
5. **Day:** `vv g 123 <day>`.

**Save before each block.** The ritual and the ceremony are both one-way.

## Items (`send GKEgo get N`)

| item | # | item | # |
|---|---|---|---|
| signal device | 19 | boar guise | 78 |
| croc mask | 21 | wolf guise | 79 |
| rod | 60 | hounfour key | 80 |
| knife | 64 | boar mask / boar robe | 74 / 75 |
| talisman | 69 | wolf mask / wolf robe | 76 / 77 |

## Flags

| flag | meaning | global | bit |
|---|---|---|---|
| 216 | croc mask worn at the ritual | 140 | 128 |
| 299 | snake tattoo painted (bookstore rm220; uses up the tattoo tracing) | 145 | 16 |
| 271 | confessional: the key's been used and the hidden elevator opened | 143 | 1 |
| 272 | set at the same moment as 271; the bench accepts things only after it | 144 | 32768 |
| 273 | you entered the confessional booth that leads down | 144 | 16384 |
| 280 | rod left on the confessional bench | 144 | 128 |
| 281 | signal device left on the confessional bench | 144 | 64 |
| 351 | set in the elevator lobby, on arrival, only if 280 and 281 are both set | 148 | 1 |

Legend: ✅ = verified; each row says whether by my console harness (Linux rig) or by your play · ☐ = needs your hands.

## What's in the patch

| guard | script | what it does | can it fire in real play? |
|---|---|---|---|
| **R5a bayou mask** | 490 `maskAction` | using the croc mask at the ritual clearing needs the tattoo; otherwise "Not yet!" | **yes** |
| **R5b bayou passage** | 490 `passageExit` | walking into the ritual needs both mask and tattoo; otherwise nothing happens (silent) | **yes** |
| **R2+R3 Grace's room** | 808 `sHRoom8` | entering needs both guises and flag 351; otherwise "Not yet!" and back to the hallway | **yes** |
| hounfour arrival | 800 `Hounfour::init` | the hallway starts only if you hold the knife | no: nothing takes the knife |
| confessional descent | 455 | riding down needs the talisman | no: both of Africa's exits give it to you |
| Africa, Wolfgang | 720 `wolfgang` | talking to Wolfgang needs the knife | no: same reason |

- **Where the softlocks come from.** In stock, the ritual kills Gabriel without the mask, and
  kills him with the mask but without the tattoo (`bayouRitual.sc:151-189`). In Grace's room,
  stock starts the ceremony whether or not you're prepared.
- **The bottom three guards** come from detection false positives. You ruled that a guard that
  can never fire is fine, so these rows only confirm that they stay out of the way.
- ⚠ **The hounfour-arrival guard has no refusal message.** If it ever did fire, the hounfour would
  simply never start.

**Not in this patch:**
- rm750→rm700 (knife): unplaced, "no controllable trigger". It's a knife false positive anyway.
- There are no guards for the rows still waiting on your rulings: flag 44, flag 14 (Tulane on the
  map) and flag 269 (the airport on the map).

## P — is the patch live?

```
resource_info script 490
resource_info script 800
resource_info script 808
```
Expect the decompressed hash to start with:
- **490: c6b3b7e2** (ours; unchanged since v4);
- **800: 41f16d18** (ours, v5);
- **808: 13e0e348** (Sierra's own; v5 doesn't patch it).

If 490 or 800 shows Sierra's hash (d40284eb or 23433274), the engine is running Sierra's copies
instead of ours, which is exactly how the September patch failed. If your ScummVM
doesn't print a hash, skip this block, because B1 proves the patch is live anyway.

## B — the bayou ritual (R5), day 6

Setup. My harness used this same teleport, and it reaches the ritual clearing:
```
gameflags_init 127
vv g 123 6
room 490                          (Esc; wait for the bayou; reopen)
send roomScript changeState 15    (Esc; the ritual clearing draws; reopen)
send GKEgo get 21                 (croc mask)
send GKEgo actions maskAction     (arms "use the mask here"; the bayou does this when Gabriel checks the tracker)
cf 216
cf 299
```
The ritual passages are on the top edge of the clearing, toward the right. The harness stood
Gabriel at x 270, y 88; `send GKEgo posn 270 88` puts him there.

| ✓ | # | Do | Expect |
|---|---|---|---|
| ✅ | B1 | no tattoo: use the croc mask on Gabriel | **"Not yet!"**. Dismiss it, and you're still in the clearing with control. (Stock: he walks in, Dr John spots the missing tattoo, death.) ✅ Your play, 2026-11-16. |
| ✅ | B2 | no mask, no tattoo: **walk** Gabriel up into a ritual passage | **Nothing happens**: no cutscene, no message. Then walk away, and leave by the ordinary bayou exit. ✅ The harness showed the passage arms in stock with any flags, but in the patch only with both. ✅ Your play, 2026-11-16: the walking side checks out too. |
| ✅ | B3 | `sf 299` (tattoo), then use the mask | Stock: the mask goes on, he walks into the ritual, and Dr John's check passes and the ritual carries on. ✅ Your play, 2026-11-16. |
| ☐ | B4 | *optional, the honest route:* after B1, leave the bayou, get the tattoo at the bookstore, and come back the same night | the mask works. I haven't checked that the day stays at 6 along the way, so if it doesn't, say so |

## G — Grace's room (R2 + R3), day 10

Setup. This starts in the confessional booth, so the whole recovery loop gets played. I haven't
run this exact start; my harness teleported straight to `room 800`.
```
gameflags_init 127
vv g 123 10
send GKEgo get 64     (knife)
send GKEgo get 69     (talisman)
send GKEgo get 60     (rod)
send GKEgo get 19     (signal device)
send GKEgo get 80     (hounfour key; normally found inside the hounfour)
send GKEgo get 78     (boar guise)
send GKEgo get 79     (wolf guise)
sf 273
sf 271
sf 272
cf 280
cf 281
cf 351
room 455              (Esc; you're kneeling in the confessional booth)
```
If the booth doesn't draw properly, use the same lines but end with `room 800` instead of
`room 455`. Then skip G3–G5 and run `sf 351` before G6.

Grace's room is the door with the keypad; you open it by using the hounfour key on the keypad.
Harness shortcut, if you don't want to walk there:
`send Hounfour curLoc 7` then `send sMainHallways setScript sEgoInRoundHallway 0 3`.

| ✓ | # | Do | Expect |
|---|---|---|---|
| ✅ | G1 | **leave nothing on the bench**; walk out of the booth | You ride down without a refusal (talisman held). The elevator lobby plays only its usual arrival line, not the second line G5 expects. The hallway starts (knife held). ✅ Your play, 2026-11-16. |
| ✅ | G2 (v5) | **R2's case: both guises, nothing left on the bench.** Use the key on Grace's keypad, then try pressing the keypad too | **"Not yet!"** both times, **on the lit hallway**. The door stays shut, and Gabriel stays in front of it with control. ✅ Your play, 2026-11-16. |
| ❌ | G2 (v4) | **FAILED, your play, 2026-11-16: the door opens, then the game hangs.** Cause, confirmed: the refusal runs after the hounfour has faded the screen to black and cleared the room for the scene, so "Not yet!" is drawn invisibly and waits for a click. Clicking the black screen dismissed it, and then the game CRASHED: `800 disposeCode::doit @ 2873: send to non-object 0000:0000`. The hounfour's teardown runs again after a scene and disposes the scene's obstacles, but our refusal skipped the scene's own setup, so there are none to dispose. A refusal inside the scene is the wrong site. |
| ☐ | G3 | walk back to the elevator lobby and into the elevator | you ride up to the confessional booth |
| ✅ | G4 | use the rod on the bench, then the signal device on the bench | both are stowed; `tf 280` and `tf 281` each print 1. ✅ Your play, 2026-11-16. |
| ✅ | G5 | walk out and ride down again | this time the lobby **plays an extra line**, and `tf 351` prints 1. ✅ Your play, 2026-11-16. |
| ✅ | G6 | **R3's case:** `send GKEgo put 79` (wolf guise gone), then Grace's keypad | **"Not yet!"** on the lit hallway, the door stays shut, and you keep control. ✅ Your play on v5, 2026-11-16. |
| ✅☐ | G7 | `send GKEgo get 79`, then Grace's keypad | **the ceremony starts**, stock from here. ✅ The harness saw the latch at 1 with both guises and flag 351. |
| ☐ | G8 | *optional stock control:* setup and G2 on `~/sierra/Games/gk1` | the ceremony starts unprepared. That's the softlock the guard prevents. |

## K — Africa, Wolfgang (optional: a guard that can't fire)

```
send GKEgo get 64
room 720              (Esc)
```

| ✓ | # | Do | Expect |
|---|---|---|---|
| ☐ | K1 | talk to Wolfgang | the conversation plays as stock. If Wolfgang isn't on screen after the teleport, skip this row; he needs the real arrival. |

## Report back

Send the row IDs with pass or fail. For a fail, say what you saw and give the last few console
lines.
