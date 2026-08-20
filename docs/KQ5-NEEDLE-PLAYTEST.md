# KQ5 — the fortune teller's needle: play-test sheet

**The question.** Oracle §6 (tier 3, the Telltale dead-ends thread) says *paying the gypsy with the
Golden_Needle makes the game unwinnable, because the needle's real consumer is the tailor → cloak*.
The source says the tailor takes **three** tokens, so the stated reason is false — but the verdict
is the user's to make. This sheet is the minimum in-game work that settles it.

Everything here is derived from `build/sweep/kq5/src`; each row cites its site.

## The market, as the source has it

| slot | room | accepts (item #) | sells | scores | site |
|---|---|---|---|---|---|
| gypsy | **13** | Golden_Needle 3 · **Gold_Coin 11** | Amulet 27 | +3 for **11** only | `rm013.sc:664–686` |
| tailor | **5**, `global313=1` | **Golden_Needle 3** · Gold_Coin 11 · Heart 9 | Cloak 26 | +4 for **3** only | `tailorShop.sc:143–151, 557–605` |
| toy maker | **5**, `global313=2` | **Marionette 12** · 3 · 9 · 11 | Sled 29 | +4 for **12** only | `toyShop.sc:461–474, 706–765` |
| baker | **206** | **Coin 4** · 3 · 9 · 11 | Pie 2 | +2 for all | `bakeShop.sc:495–520, 888–912` |

Item 4 (Coin) is **refused** by the tailor and the toy maker — they play a shake-head animation and
no sale (`tailorShop.sc:565`, `toyShop.sc:737`). Only the baker takes it.

**Token sources (one each):** Golden_Needle 3 ← rm27 (haystack, the ants' repayment) · Coin 4 ←
rm4 · Heart 9 ← rm21 · Gold_Coin 11 ← **rm18, the temple** · Marionette 12 ← rm10.

⭐ **Heart 9 is the one token behind the amulet** — rm21 is two screens into the forest. That is why
the amulet slot `{3, 11}` is the tight one, and why the hazard (if any) is a *two-payment* one.

## Numbers you need

| what | value |
|---|---|
| items | Pie **2** · Golden_Needle **3** · Coin **4** · Heart **9** · Gold_Coin **11** · Marionette **12** · Cloak **26** · Amulet **27** · Sled **29** |
| rooms | shop street **4** · shop interior **5** · bakery street **6** · gypsy tent **13** · bakery **206** · amulet cutscene **680** |
| which shop rm5 is | `global313` = **1** tailor · **2** toy maker · **3** shoemaker (set by rm4's three doors, `rm004.sc:904/936/968`) |
| score | `global15` (`proc0_27` adds to it, `Main.sc`) |

## Console commands (ScummVM SCI console)

    room 13                  ; teleport (this is the room NUMBER, decimal)
    vv g 313 1               ; set global313 = 1  -> rm5 becomes the tailor
    vv g 15                  ; read the score
    send ?ego get 3          ; give yourself item 3
    send ?ego put 3 -1       ; take item 3 away (owner = nowhere)
    send ?ego put 2 206      ; hand an item you hold to a room (here: the pie back to the bakery)

`?ego` and the item objects resolve by name — `?Golden_Needle`, `?Gold_Coin`, `?Pie` etc. are the
real object names in `KQInv.sc`, so `?obj` lookups work if you prefer them.

⚠️ **Set `global313` BEFORE `room 5`.** `rm005::init` switches on it to pick the shop region
(`rm005.sc:30`); with a stale or zero value you get a room with no shopkeeper in it at all.

⚠️ Use the doors in rm4 if you want the ordinary path — clicking door0/door1/door2 sets `global313`
for you and walks you in.

## TEST 1 — the decisive one (≈2 minutes)

*Does paying the gypsy with the needle still leave you able to buy the cloak?*

    send ?ego get 3
    send ?ego get 11
    room 13

Use the **Golden_Needle** on the gypsy. Expect: she takes it, you sit down, the scene cuts to
rm680 and you come back with the Amulet. Score should **not** move (`rm013.sc:680` has no
`proc0_27`).

    vv g 313 1
    room 5

Use the **Gold_Coin** on the tailor.

- **If he sells you the cloak** → the needle payment is NOT a dead end, and the red is wrong.
- **If he refuses** → the source and I are wrong about `tailorShop.sc:601`; tell me and I'll re-read.

## TEST 2 — control (confirms the score is only an intent tell)

Fresh state, no amulet and no cloak:

    send ?ego put 27 -1
    send ?ego put 26 -1
    send ?ego get 11
    send ?ego get 3
    vv g 15            ; note the score

Gold_Coin → gypsy should give **+3**; Golden_Needle → tailor should give **+4**. That is the
"intended pairing" signal — the same signal the throwable pool has, where the Lamb and the Fish
score nothing at the cat and still save the mouse. If both pairings work either way round, the
score is decoration, not a warning.

## TEST 3 — the hazard I actually think exists (the two-payment squeeze)

    send ?ego put 27 -1      ; make sure you have no amulet
    send ?ego get 3
    send ?ego get 11
    send ?ego get 4
    send ?ego get 12
    ; deliberately NOT item 9 -- the Heart is in the forest, which needs the amulet

1. `vv g 313 2` then `room 5` — pay the toy maker with the **Golden_Needle** (he takes it; the
   Marionette would have done).
2. `room 206` — pay the baker with the **Gold_Coin** (he takes it; the Coin would have done).
3. `room 13` — now try to buy the Amulet with everything you have left (Coin 4, Marionette 12).

Expected: she refuses all of it — the slot only reads items 3 and 11 (`rm013.sc:664/678`), and
item 4 gets message 9041. No amulet ⇒ no forest ⇒ no rm24 ⇒ **no Beeswax**, which is a hard
requirement later.

If that plays as expected, the real KQ5 mechanism here is a **market squeeze needing two wrong
payments**, not the single "needle to the gypsy" the walkthrough names.

## Gotchas that will make a test fail for the wrong reason

| guard | site | effect |
|---|---|---|
| `has: 27` | `rm013.sc:665/679` | the gypsy refuses to deal once you own the Amulet |
| `has: 26` | `tailorShop.sc:136` | `soldCloak` bails once you own the Cloak |
| `has: 29` | `toyShop.sc:708` etc. | the toy maker refuses once you own the Sled |
| `((gInv at: 2) owner:) == 206` | `bakeShop.sc:888` | the baker only deals while **the pie is still in his shop** |

To reset the baker between runs: `send ?ego get 2` then `send ?ego put 2 206`.

## Results

| test | expected | observed | date |
|---|---|---|---|
| 1 — needle→gypsy, then coin→tailor | cloak sold | ✅ **BOTH CONFIRMED, USER.** *"the gypsy at the door will take the golden needle rather than the gold coin"*, and *"yes you can buy the cloak for the gold coin"* | 2026-08-17 |
| 2 — coin→gypsy +3, needle→tailor +4 | both pairings work, only these score | not run — test 1 settles the verdict; this only re-confirms the score is decoration | |
| 3 — needle→toy, coin→baker, then gypsy | amulet unbuyable | not run — the OPEN mechanism (§6), worth running before anyone builds for it | |

**RULING: the needle substitution is NOT a softlock.** Scorecard row 9 withdrawn, the red retired
and rebuilt as green pins. ⛔ Note what test 1 did *not* settle: whether the two-payment squeeze
(test 3) is real. Nothing should be built for it until that is run.

## Getting into rm13 — read this before teleporting

`room 13` alone will not do it, and it is **not** a flag. `rm013::init` ends with
`(switch global12 ...)` on the PREVIOUS room number, whose cases are the room's own neighbours
(`east 9`, `south 12`, `west 14`). Arrive from anywhere else and you take the `else` branch, which
drops the ego at **(187, 127)** — a point inside `poly1`, the camp's own obstacle
(`[10 113, 240 113, 260 120, 260 128, 209 128, 170 134, 107 134, 107 128, 10 129]`) — and then
`egoWalk` hands control back only when its `MoveTo` cues.

`Game::newRoom` sets `global12` from `global11` on the way in, so writing `global12` yourself is
useless — it gets overwritten. **Teleport in two hops instead:**

    room 12        ; the dog screen, rm13's declared `south` neighbour
    room 13        ; global12 is now 12 -> the south branch, posn 133 180, stdWalkIn

`room 9` then `room 13` works the same way (rm9 is the `east` neighbour).

**Click the item on `body`** — the seated gypsy woman (`rm013.sc:621`), which owns the
give-handler. The `gypsy` Actor (`rm013.sc:799`) only inits during the transaction cutscene, so
there is no point waiting for her to appear first.
