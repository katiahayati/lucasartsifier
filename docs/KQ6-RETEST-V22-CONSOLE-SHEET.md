# KQ6 v22 retest sheet — exact ScummVM console commands

Install: **delete ALL loose patches first, then copy** — `rm -f *.SCR *.HEP *.VOC` in the
game copy, then `build/kq6_patch_v22/patch/*` + `patch_project/999.VOC`. Copy-over
upgrades leave RETIRED scripts behind, and retired-by-removal is how v20 fixed the
finding-#15 hang: a stale v19 `680.SCR` hangs the game right after the Lord of the Dead
challenge completes (bitten 2026-08-04 with the Aug-1 leftovers, again 2026-08-05).
The complete v22 set is exactly: 0 21 80 190 220 230 320 340 344 420 550 560 640 660
740 880 (.SCR+.HEP each) + 999.VOC — anything else (670, 680, 300, 11, 425, 460, 470)
is a leftover; delete it.
Console = Ctrl-Alt-D. Three rules, then no more theory:

1. **`room <N>` doesn't act until you close the console.** Type it, press Esc, let the
   room draw, reopen the console for the rest.
2. **`send ?rgCastle …` only works while standing in a castle room** (700–880) — the
   object has to be loaded. `send ?ego …` works anywhere.
3. **`sf <N>` sets game flag N, `cf <N>` clears it, `tf <N>` reads it.** ScummVM knows
   KQ6's flag table. If `sf` complains the first time, run `gameflags_init` once.

Item cheat-list (for `send ?ego get <N>` / `send ?ego put <N> 0`): brick 2 ·
deadMansCoin 7 · dagger 8 · skull 11 · gauntlet 15 · handkerchief 17 · holeInTheWall 18 ·
huntersLamp 19 · **letter 20** · mint 23 · mirror 24 · nightingale 27 · peppermint 31 ·
scarf 41 · skeletonKey 44 · teaCup 46 · tinderBox 48.

The **wedding setup block** (used by R1–R3) — run it standing in rm710:

```
send ?rgCastle setFlag 709 32768
send ?rgCastle setFlag 710 256
send ?rgCastle setFlag 711 512
send ?rgCastle weddingRemind 10
```

Handy reads: `send ?rgCastle weddingRemind` (frozen vs ticking) ·
`send ?rgCastle weddingMusicCount` (−1 until the music fires) ·
`send ?rgCastle tstFlag 709 2` (1 = wedding music has fired).

---

## R1 — wedding: the clock resumes on pickup

```
room 710            (Esc, wait, reopen)
<wedding setup block>
send ?ego has 20    (confirm 0)
```
Close the console, stand around 30s: **nothing happens** (that's the hold — you saw it).
Reopen:
```
send ?ego get 20
```
Expect: music starts **by itself within ~10s**; count climbs; dogs post; corral and
Saladin play out completely stock.

## R2 — wedding: with the letter, everything equals stock

```
room 710            (Esc, wait, reopen)
<wedding setup block>
send ?rgCastle weddingRemind 300    (override the block's 10 -- see note)
send ?ego get 20
```
⚠️ With the letter in hand the hold no longer freezes the fuse — at 10s the music fires
before you reach the panel, the dogs post, and the treasure door's one scripted refusal
(guards posted) blocks you. 300s gives you time; the treasure room pauses the fuse anyway.
Open the wall panel in 710 (see THE PANEL below), browse the treasure room, walk out.
Expect: music near-instantly, escalation jumps, corral within seconds — the stock ride.

### THE PANEL (rm710 wall closeup) — how it actually works

No flag gates it: "seeing Ali and Zebu" (the keyhole scene in the walls) is player
knowledge only — the panel accepts the right presses cold. It scores by GRID POSITION:
five letters per row, A–E / F–J / K–O / P–T / U–Y, and Z alone CENTERED on the bottom
row. Click, in order:

    A (row 1, col 1) · L (row 3, col 2) · I (row 2, col 4) · Z (row 6, center)
    · E (row 1, col 5) · B (row 1, col 2) · U (row 5, col 1)

A wrong click fails SILENTLY (all 7 presses complete, then "nothing happens"); a repeat
click on the same button is ignored (doesn't advance, doesn't fail). The honest unlock,
for E-row runs: watch the guard dogs through the first keyhole in the walls (rm800) —
that scene is where the word is given.

## R3 — wedding: treasures FIRST, letterless (finding #3's own trace)

```
room 710            (Esc, wait, reopen)
<wedding setup block>
```
No letter. Panel (ALIZEBU) → browse 770 → walk out. Expect **still no music**.
Then: pull the lever in 720 → the passage must still open (dogs stay transient
patrols — dodge them; they must NOT post permanently). Walk the walls to the study,
take the letter from the trunk **in-game**. Expect: music starts on its own right after.

## R4 — Charon's crossing (v20 added the cup demand)

```
room 650            (Esc, wait, reopen)
send ?ego get 7
send ?ego get 15
send ?ego get 24
send ?ego get 46
```
Walk to the Styx shore (660). Cup is EMPTY — do not `sf 58`.
1. Try to board → refusal that names the unfilled cup; no hang, controls live.
2. `send ?ego put 15 0` → board → refusal (gauntlet). `send ?ego get 15`
3. `send ?ego put 24 0` → board → refusal (mirror). `send ?ego get 24`
4. Fill the cup at the river **with the game's own verb** (use cup on the Styx).
5. Board → pays the coin, crosses normally.

## R5 — Realm interior is stock again (the v19 hang is gone)

Continue from R4 after crossing: gate (670) → Death's hall (680) → the challenge (690):
show Death the mirror, win. Expect: the win scene plays, the ride back happens,
**zero refusals and zero hangs anywhere past Charon**, both directions.

## R6 — mists: lampless approach turns you back (v18 form, never played)

```
room 550            (Esc, wait, reopen)
send ?ego put 19 0
```
Walk the north trail. Expect: ONE message, Alex walks back a few steps, controls
return. Walk at it again → same, once per approach (no message machine-gun, no
walking off-screen, no hang). Then:
```
room 560            (Esc, wait, reopen)
```
Walk the east edge lampless → it is silently closed (the game's own idiom). Then:
```
send ?ego get 19
```
Both crossings behave completely normally.

## R7 — mists: the forced revisit rides the SHORE CAPTURE (measured 2026-08-05)

Flag 25 = "visited the mists and LEFT" (written by the region's own dispose,
`rMist.sc:42`) — NOT the rain. The shore druids (rm550.sc:282: flag 25 ∧ NOT flag 14)
are the game's forced-revisit mechanic, and their `captured` script ends in a direct
`newRoom: 580` — it never touches the trail crossing our lamp guard wraps, so the
recorded over-block risk is structurally moot. What's left to confirm:
```
sf 25
cf 14
send ?ego put 19 0
room 550            (Esc, wait, reopen)
```
Let the shore druids take you. Expect: carried to the camp (580) lampless with no
interference from our guard, and `tf 14` reads set afterwards. Separately, WALKING
the trail lampless (R6) still gets our turn-back — that path is a player walk, not
the game's carry.

⚠️ Fresh-game gotcha (bitten 2026-08-05): flag 25 can leak into a "fresh" test game
(a leftover `sf 25`, or restarting while standing in a mists room lets the region's
dispose stamp it). `tf 25` on any fresh start before a mists trip; `cf 25` if set —
otherwise the shore ambush fires on your FIRST landing.

## R8 — cliff: ALLOW with the four + free down-climb

```
sf 123
sf 124
sf 125
sf 126
sf 2
cf 1
send ?ego get 2
send ?ego get 18
send ?ego get 41
send ?ego get 48
room 300            (Esc, wait, reopen console only if needed)
```
(123–126 = the four cliff puzzles solved; flag 2 set + flag 1 clear = capture stage.)
Climb the rocks. Expect: NO "Not yet!" — stock climbing all the way; stepping DOWN is
free at any point; the repeat-climber summit shortcut behaves stock.

## R9 — catacombs captures still work WITH the four (and refuse without)

Same flags/items as R8. **Walk** into the mountain entrance from outside — do not
`room 340`, the capture arming reads the real approach.
- With all four in hand: the seizure/capture proceeds as stock.
- Then `send ?ego put 2 0`, `put 18 0`, `put 41 0`, `put 48 0`, walk in again:
  the guards must NOT throw you in — refusal instead.

## R10 — castle doors (never played)

Short door:
```
room 220            (Esc, wait, reopen)
send ?ego get 8
send ?ego get 24
send ?ego get 27
send ?ego get 23
```
Try the door dropping one item at a time (`send ?ego put 27 0` → try → refusal →
`send ?ego get 27`, next item…). With the full set the crossing proceeds. Note: the
game's own dress/plot requirements still apply on top — only OUR refusal is under test.

Long door:
```
room 230            (Esc, wait, reopen)
send ?ego get 8
send ?ego get 17
send ?ego get 24
send ?ego get 44
send ?ego get 23
```
Same drill. Extra check: the nightingale (27) must NOT be demanded here.

## R11 — the skull refusal + whole-room regression (we overwrite Sierra's own patch)

```
room 420            (Esc, wait — mind the ceiling)
send ?ego get 11
```
Throw the skull into the gears → refusal line, skull still in inventory, still alive.
Without the skull the room speaks stock. Regression-eye the whole room: crushing
ceiling timing, the brick business — all must be stock.

## R12 — ✅ VERIFIED 2026-08-05 on v23 ("mints refusal works")

FINDING #18 (2026-08-05): v22's retraction Print clobbered the async joke message when
using the mint on yourself — fixed in **v23** (the retraction now rides the say's
completion). Install: v23 = v22 + new `0.SCR`/`0.HEP` — copy those two from
`build/kq6_patch_v23/patch/` over your game copy (everything else is byte-identical).
```
send ?ego get 23
send ?ego get 31
```
Use each on YOURSELF (the finding's own trace): the joke box shows, dismisses normally,
THEN "Just kidding!..." shows, dismisses normally, item still in inventory. Then wrong
objects around the world → never consumed. (The genie feed at the pawn shop is in R13.)

## R13 — the honest runs (NO console commands — that's the point)

1. Short-route win, start to rm180.
2. Long-route win, start to rm180.
3. With the letter fetched, let the wedding complete → **the losing ending must still
   be reachable** (we guard softlocks, not defeats — this is the doctrine the old
   code protected, so prove v22 kept it).

No guard may fire on a correctly-played run. Un-die overlay for exploring death rooms:
`build/kq6_playtest_undie/patch/` — never for verdict runs.

---

Reporting, per defect: room, what you did, expected vs got, and a save from just
before. The three finding classes that matter most: a guard that HANGS, a guard that
fires on a legitimate path (over-block), and a PREVENT that walks through.

---

# v24 addendum — the mists (finding #17) + the sacred-water catch

**Install (delete-then-copy, as always):** in the game copy `rm -f *.SCR *.HEP *.VOC`,
then copy `build/kq6_patch_v24/patch/*` + `build/kq6_patch_v24/patch_project/999.VOC`.
The complete v24 set is exactly: **0 21 80 130 190 220 230 320 340 344 420 550 560 580
640 660 740 880** (.SCR+.HEP each) + 999.VOC. New vs v23: **130** (the magic map —
the landing guard lives in the map click) and **580**; 0/550/560 changed.

New flag/global cheats for this block: `vv g 161` reads the Make-Rain readiness word
(0 = nothing done, 15 = fully ready; the game RESETS it to 0 when the rain succeeds —
that reset is why the guard waives readiness under flag 74). Faking readiness:
`vv g 161 15` then `sf 31`. Flags: **25** = visited the mists and left · **14** = met
the druids · **74** = befriended-forever (the rain happened). Items: magic map **0** ·
huntersLamp **19** · sacredWater **40**.

⚠️ Do NOT use `room 550` to test the landing — the guard sits on the MAP CLICK, and
teleporting bypasses it. Use the map from the inventory.

## R6a — first visit, unready: the trail refuses (the map must NOT)

Fresh game, console:
```
tf 25          (expect 0 -- if 1, cf 25: the flag-25 leak gotcha)
tf 14          (expect 0)
tf 74          (expect 0)
send ?ego get 0
send ?ego get 19
vv g 161       (expect 0)
```
Esc → open the map, click the Isle of the Mists → **landing works** (first visit is
free). Walk north up the trail → Alexander **turns back, "Not yet!"** — v16 demanded
only the lamp; v24 also demands readiness, so even with the lamp in hand this refuses.
(Stock: capture → cage → burn.)

## R6b — the legitimate run, readiness faked

Standing on the mists shore from R6a:
```
vv g 161 15
sf 31
```
Esc → walk north → capture plays out → the cage → **make rain → befriended**. Verify:
```
tf 74          (expect 1)
vv g 161       (expect 0 -- the game's own reset)
```

## R7a — leave-unready-then-return: the NEW map refusal

Fresh game (or a pre-mists save):
```
send ?ego get 0
send ?ego get 19
sf 25          (fake "visited and left" -- honest version: land once, map away)
tf 14          (expect 0)
vv g 161       (expect 0)
```
Esc → map → click the mists → **"Not yet!" and the map stays usable** — this exact
click is the crossing that in stock delivers you to the shore ambush and the burning
cage with no further control. Then make it legitimate:
```
vv g 161 15
sf 31
```
map → mists → landing proceeds → **shore druids seize you on the beach** → cage →
rain → befriended. (The other two islands' clicks must be untouched — click Wonder
or the Beast isle any time: stock behavior.)

## R7b — befriended is never walled (the waiver) — v25 SHAPE

USER RULING 2026-08-06 (on v24, in play): "let you revisit the camp without the lamp
once there's no trap there." From **v25** the 74 latch waives the WHOLE demand:
after a completed rain (74 set): leave, map back → **landing free** (no ambush), then
```
send ?ego put 19 0
```
walk north WITHOUT the lamp → **allowed**, friendly camp. (On v24 this refused — that
refusal is the finding this ruling retired.)

## W1 — sacred water: wasting it is retracted (the by-product catch)

Anywhere:
```
send ?ego get 40
```
Esc → use the water on random scenery / the ground / yourself. Expect: the stock
flavor line, then **"Just kidding! You hold on to it because you still need it."**,
water still in inventory (stock: silently destroyed — mint/peppermint's class, found
when g161's bits gave the pour a modeled consequence). The legitimate pour (on the
spell page during Make Rain prep, flag 77 studied) must still consume it — that path
writes the readiness bit and is untouched.
