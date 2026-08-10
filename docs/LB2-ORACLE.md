# Laura Bow 2: The Dagger of Amon Ra — validation oracle

Our third SCI1.1 game and the first with an **act structure**. Built 2026-07-26, **re-derived and
corrected 2026-08-06** against six sources plus the game's own script, in that order of authority:
**the game source wins**, then Sierra's own hint file, then the walkthroughs, then me.

Sources (local copies and provenance: `docs/refs/lb2/README.md`, untracked):

| tier | source |
|---|---|
| 1 | our decompilation, `build/sweep/dagger/src` |
| 2 | Sierra's own hint Q&A, `sierrahelp.com/Hints/LauraBow2Spoilers.html` |
| 2 | Sierra's official hint book PDF — **a scan with no text layer**, unusable without OCR |
| 3 | `sierrahelp.com/Walkthroughs/LauraBow2Walkthrough.html` |
| 3 | the-spoiler / justadventure, Avi Machness variant 2 |
| 3 | `thecomputershow.com`, Michael Pemberton |
| 3 | `videogame-tales` LiveJournal Let's Play — the only source that says "unwinnable" in so many words |
| 4 | `walkthroughking.com` (thin — no evidence list) |

> **2026-08-06 headline.** The five ending items are still caught and still correct. But the §5
> twelve-item carry list was a **prediction**, never verified against the source, and re-deriving it
> broke three rows: LB2's designers re-place a missed item under `(if (not (has: N)) ...)` in
> **20 of 33 cases**, and two of the twelve are re-obtainable in the very act that needs them. The
> corrected list, its evidence, and three rows that need a user ruling are in §5. Where we actually
> stand is §7 — and the answer is one sentence: **the act counter is not in the model at all.**

---

## 1. THE ACT STRUCTURE (source-verified, unchanged)

`actBreak.sc` (script 26) is a room — the act-break title card. Seven rooms `newRoom: 26`, and it
alone advances the game:

    (switch global123                         ; the act you are LEAVING
       (0 (= local0 230))  (1 (= local0 330))  (2 (= local0 355))
       (3 (= local0 (if (== global12 620) 610 else 510)))
       (4 (= local0 420))  (5 (= local0 750)))
    ...
    (9  (++ global123)                        ; ADVANCE
        (= global124 0)
        (global2 newRoom: local0))            ; warp into the next act

So `global123` is the act counter, 0..6, incremented **only here**. Measured 2026-08-06 over the
whole `.sc` tree: **239 test sites in 40 files, 10 write sites in 5 files** (`rm440` alone tests it
27 times, `rm420` 19, `rm500` 19).

**This is the softlock engine of the game.** The counter only goes up, rooms condition access on
it, so anything left behind when an act ends is gone. Sierra's own hint file says it plainly: it is
easy to *"head into a new Act without some vital item."*

| act | title | starts in | rooms |
|---|---|---|---|
| 1 | A Nose for News | rm230 | the city — newspaper office, docks, laundry, speakeasy (210–295) |
| 2 | Suspects on Parade | rm330 | the museum fundraiser (300–370, 400) |
| 3 | On the Cutting Edge | rm355 | the museum, open investigation (400–660) — the longest act |
| 4 | Museum of the Dead | rm510 / rm610 | the museum, being hunted |
| 5 | Rex Takes a Bite out of Crime | rm420 | the chase and the tunnel (420–490, 700–740) |
| 6 | The Coroner's Inquest | rm750 | one room, questions only |

### 1a. ⚠️ The act counter has a DEBUG BACK DOOR (found 2026-08-06)

Of those 10 writes, **6 are a debug menu**. `whereTo.sc` is the cab-destination prompt; typing
`-300` into it opens a six-button panel that sets `global123` to any act 0–5 outright, and then
does `(ego get: -1 2)` — the classic Sierra give-me-everything. (`-100` restores, `-200` opens a
second menu.) One more write, `rm355.sc:209`, is a `(= global123 0)` reset inside `sIllegal`.

That leaves **`actBreak`'s `(++ global123)` as the only act write on the main path** — and see §7:
it is an increment on a *global*, which the model drops. So every act value the model can currently
see comes from the debug door. Anything that models the act must exclude `whereTo`'s `-300` block
the way `config.debug_globals` excludes LSL2's; LB2's `debug_globals` is presently empty.

---

## 2. THE ENDING SELECTOR — read out of `rm750.sc:318-380`, NOT a walkthrough

This is the single most important fact about LB2 for our purposes, and it **disagrees with every
walkthrough**, so it is quoted from the game:

    (cond ((and (has: 31) (has: 26) (has: 27) (has: 10) local4 local5 (has: 11))
              (= global126 1))                          ; BEST
          ((and (has: 31) (has: 26) (has: 27) (has: 10) local4)
              (= global126 4))
          (local5  (= global126 2))
          (else    (= global126 3)))                    ; WORST

- The five `has:` items are **31 grapes, 26 bifocals, 27 redHair, 10 wireCutters, 11 daggerOfRa**.
- `local4` / `local5` start at 1 and are zeroed by a **wrong answer** (murder questions, theft
  questions). They are answer-correctness flags, not items.
- `global126` ∈ {1,2,3,4} is **which of the four endings you get**. The game always ends.

So LB2 has **no "cannot finish" state**: missing evidence buys a worse ending, not a dead end. The
walkthroughs' *"the case cannot be solved"* is a description of ending 3, not of a softlock.

**SETTLED (user, 2026-07-26): for Laura Bow 1 and 2 we gate on ITEMS only.** *"Evidence, people
moving around, etc, is the whole point of the game."* So the five `has:`-checked items are in
scope and count; the evidence-examination layer, the NPC schedules and the dialogue state that
drive `local4`/`local5` are **deliberately out of scope** — modelling them would be modelling the
game rather than its blockers. This also settles the KQ6-island-treasure analogy for LB2: the five
count, because they are items.

### `proc0_3 147` is a red herring
`(if (proc0_2 147) ... else (= local4 0))` looks like an evidence gate, but `rm750`'s own `init`
does `(proc0_3 147)` — test-and-**set** — so it is always true by the time it is read. A
"have we been here" marker for the replay path. Checked so nobody has to check it twice.

---

## 3. EVERY ITEM (36), with our extracted index

Indices are ours (`vocab.item_names`, the inventory `add:` order). Act = where it is obtained.

> ⚠️ The `act` column below is **walkthrough-attributed**, not source-derived, and 2026-08-06
> found at least one row wrong (workBoot: `rm440` inits the boot only under `(== global123 4)`, so
> it is an act-**4** pickup, and `rm720` re-places it in act 5). Treat this column as tier-3
> evidence; §5 is the column that has been checked against the game.

| # | item | act | source | use | verdict |
|---|---|---|---|---|---|
| 0 | coupon | 1 | drunk's newspaper, outside the police station | buy the sandwich (`rm210` `put: 0`) | act-local, **consumed** |
| 1 | claimTicket | 1 | trash in the dirty taxi | give to Lo Fat → gown | act-local, consumed |
| 2 | notebook | 0 | Laura's, from the start | pick cab destinations; hieroglyph riddles in act 5 | carried |
| 3 | sandwich | 1 | from the coupon | give to the desk sergeant → password | act-local, consumed |
| 4 | baseball | 1 | trash can, newspaper office | trade to the street boys → magnifier | act-local, consumed |
| 5 | deskKey | 1 | under the desk blotter | opens the drawer → press pass | act-local |
| 6 | pressPass | 1 | desk drawer | cabbie (or ejected), guard, Heimlich at the door | **spans acts 1→2; three `put:` sites** |
| 7 | pocketWatch | 3 | steamer trunk, Mammalogy Lab | shown to the Countess | inquest list (walkthrough only) |
| 8 | skeletonKey | 3 | glued behind the Bosch painting | opens the steamer trunk | act-local; **no `get:` site extracted** |
| 9 | meat | 3 | icebox, Mammalogy Lab | **throw into the trunk before opening** — beetles kill you otherwise | act-local, death |
| 10 | **wireCutters** | 3 | Ernie's toolbox | cut the pterodactyl wire; pry the key | **ENDING ITEM (source)** |
| 11 | **daggerOfRa** | 3 | Vat 13, with the lasso | the murder weapon | **ENDING ITEM (source)** |
| 12 | workBoot | **4** | Armor Room, by the dog armor (`rm440`, act-4 only) | give to Steve in act 5 **before he stands** | **CONTESTED — `rm720` re-places it, §5** |
| 13 | smellingSalts | 4 | the Countess's pocket | revive Steve in act 5 | **spans 4→5** |
| 14 | snakeOil | 3 | Preservation Lab table | the snake (4), the cobra nest (5) | **spans 3→5, and is a COUNTER — §5a** |
| 15 | lantern | 4/5 | `rm600` (act-4-gated room) | light the tunnel | act-local |
| 16 | cheese | 3 | rat trap in Heimlich's office (needs dinoBone) | distract the rats in the tunnel | **spans 3→5** |
| 17 | garter | 3 | poetry book, Heimlich's shelf | — | inquest list (walkthrough only) |
| 18 | dinoBone | 3 | T-Rex room | spring the trap; break the mirror; break the statue (4) | **CONTESTED — `rm480` re-places it, §5** |
| 19 | snakeLasso | 3 | Ernie's toolbox | vat 13; the snake (4); the mummy-case hook (5) | **spans 3→5** |
| 20 | ankhMedallion | 2 | Egyptian exhibit | identifies Tut Smith | inquest list (walkthrough only) |
| 21 | pippin_sPad | 2 | the body in the sarcophagus | **the hieroglyphs that answer the act-5 riddles** | spans 2→5, **no `has:` use site** |
| 22 | magnifier | 1 | the street boys, for the baseball | required to see most evidence, all game | spans 1→4, **no `has:` use site** |
| 23 | lightBulb | 3 | Yvette's lamp (let it cool) | the stairway → the spiral staircase | act-local |
| 24 | watney_sFile | 3 | *Crime and Punishment*, Carrington's shelf | identifies the impostor | inquest list (walkthrough only) |
| 25 | warthogHairs | 3 | Ernie's body, Mastodon Room | — | inquest list (walkthrough only) |
| 26 | **bifocals** | 4 | the corpse inside the broken statue | — | **ENDING ITEM (source)** |
| 27 | **redHair** | 4 | Yvette's office | — | **ENDING ITEM (source)** |
| 28 | waterGlass | 2 | the buffet table | eavesdrop at doors in acts 3 and 4 | spans 2→4, **no `has:` use outside `rm350`** |
| 29 | carbonPaper | 3 | Yvette's wastebasket | hold to the lamp to read it | inquest list (walkthrough only) |
| 30 | yvette_sShoe | 4 | Yvette's office | — | inquest list (walkthrough only) |
| 31 | **grapes** | 4 | the floor by the Countess's body | — | **ENDING ITEM (source)** |
| 32 | eveningGown | 1 | Lo Fat's laundry, with the ticket | worn to the fundraiser | **spans 1→2; no `get:` site extracted** |
| 33 | charcoal | 3 | the fireplace | rub on the notepad | act-local |
| 34 | wire | 3 | clipped from the pterodactyl (needs wireCutters) | wire the door shut in act 5 | **CONTESTED — cuttable in act 5, §5** |
| 35 | mummy | 5 | the mummy case | prop against the elevator door | act-local |

**The walkthroughs' 13-item "conviction list"** — dagger, Watney's file, ankh medallion, red hair,
pocket watch, wire cutters, carbon paper, bifocals, Pippin's notepad, garter, grapes, warthog
hairs, Yvette's shoe — is quoted identically by Sierra's hint file and the-spoiler. Only **5** of
them are `has:`-checked at the inquest. The other 8 are presumably what lets you *know the answers*
(they feed `local4`/`local5` through the dialogue), i.e. **evidence you must have EXAMINED, not
held**. That distinction is a modelling target, not a discrepancy in the sources.

---

## 4. ACTIONS THAT MATTER (the user asked for these explicitly)

Items are only half of it. Ranked by whether missing one can cost you.

**Kills you if skipped or mistimed**
- act 3, Mammalogy Lab: throw the **meat** into the steamer trunk *before* opening it — beetles.
- act 5, the whole chase: wire the pterodactyl door · board the armor-room door · chair + transom ·
  hide in the **far-left** mummy case · move the crate · cut the rope · elevator lever · prop the
  mummy · lasso the case hook. A wrong step is capture. *"The murderer is only a few steps behind."*
- act 5: give Steve the boot **before he stands** (nail).
- act 1: show the press pass to the cabbie or be thrown out.
- act 1: look BOTH ways before crossing the street (Sierra's own hint file lists this as a death).

**Gates content, and the act may end first**
- act 2: eavesdrop on the **14 conversations** — act-2 only, and never repeatable.
- act 3: replace the light bulb → the Thinker's hinge → the spiral staircase.
- act 3, four secret passages: button behind Heimlich's medals (→ Carrington's), the rhesus skull
  horn in Olympia's (→ preservation lab), the button behind Ernie's desk (→ Egyptian display),
  Myklos' → the vats.
- act 3: the wall safe — combination from the phone list under **"B. SAYFF"** (KL 0527).
- act 3: magnifier on the Bosch painting **twice** to expose the glued key.
- act 3: charcoal rubbed on the notepad; carbon paper held to the lamp.
- act 3: show the pocket watch to the Countess.
- **act 4: REFILL THE SNAKE-OIL BOTTLE at the preservation lab** — see §5a. Both Sierra's hint file
  and the Let's Play single this out; the Let's Play calls it flatly unwinnable.
- act 5: the riddles — **"womb"**, then **"tomb"**, read from Pippin's notepad.

**Pure evidence-examination** (magnifier on the daggers, the medallion, the red puddle, the diary,
the watch, the Mastodon body). Sierra's hints: *"you need to see pretty much everything to
progress."* These set flags; they are how the 8 non-`has:` conviction items do their work.

---

## 5. THE ENUMERATED ORACLE (re-derived 2026-08-06)

Four columns, KQ6's shape. Every row says **what evidence it rests on**, because the 2026-07-26
version did not and three of its rows were wrong.

### The mechanism that broke the old list

Measured over the whole tree: of the **33** items with a `get:` site, **20** are sourced by a room
whose script also tests `(not (global0 has: N))` — the shape
`(if (not (global0 has: N)) (<thing> init: ...))`, a deliberate Sierra safety net that re-places
whatever you failed to take. (The measurement is per FILE, so it is an upper bound on the idiom;
the three cases below were read in full and are the real thing.) It means *an item is strandable
only when its SOURCE ROOM stops being reachable* — which in LB2 is precisely an act boundary. It
also means a carry the walkthroughs call fatal may not be:

    rm720.sc:46     (if (not (global0 has: 12)) (boot init: approachVerbs: 4 1 8))
    rm720.sc:989    (instance boot of View ... (4 (global2 setScript: sGetBoot)))
    rm720.sc:770    (2 (boot dispose:) (global0 get: 12) ...)

`rm720` is the act-5 tunnel room where Steve lies — the room where the boot is *used*. So the boot
is obtainable at the point of use, and "fail to pick up the boot in act 4 and the game is
unwinnable" (Let's Play, part 12) is contradicted by the source.

### 5a. NEW UNIT — the snake-oil bottle is a COUNTED RESOURCE (source-verified)

Not in the 2026-07-26 oracle at all. `global150` is the bottle's level:

    Main.sc:230     global150 = 4                      ; starts full
    rm610.sc:692    (if (< cel 3) (++ cel) (= global150 4) ...)  ; REFILL — and the vat's own cel
                                                       ; caps it at THREE refills
    rm520.sc:329    (-- global150)                     ; shaking it at the snake, 3 shakes needed
    rm610.sc:1133   (-- global150)
    rm610.sc:1165   (-- global150)
    invCode.sc:427  (cond ((== global150 4) …) ((== global150 3) …) …)   ; the inventory blurb
    rm730.sc:790    ((== global150 0) (global0 setScript: sThrowBottle))  ; ACT-5 COBRA NEST
    rm730.sc:626    (3 … (global0 … put: 14 …) (self dispose:))           ; …and it THROWS IT AWAY

So arriving in the act-5 tunnel with an empty bottle makes Laura throw it, `put: 14` **destroys the
item**, and the cobras are never repelled. Act 5 has no way back. This is a
`resource_exhaustion` × `dangerous_sinks` unit, not a plain carry, and it is the one place where
LB2 needs a counter and not just a `has:`.

Corroboration, independently: Sierra's own hint file (*"you may need to refill your snake oil
bottle… go to the preservation lab and use the snake oil bottle on the container"*), the sierrahelp
walkthrough (*"Go to lab, fill snake oil bottle"*, act 4), and the Let's Play (*"if you fail to
make sure you have a full bottle now, the game becomes unwinnable"*).

**Not yet derived:** the exact spend arithmetic (how many decrements are forced before act 5, hence
whether the refill is mandatory or merely prudent). Until it is, this row is a *mechanism* we can
state and a *quantity* we cannot.

### 5b. THE COLUMNS

**A — REAL, AND WE CATCH IT** (a drop here is a regression → STOP and confirm)

| item | why it is real | why we catch it |
|---|---|---|
| wireCutters | `rm750` `has: 10` in the ending selector | `rm26->rm750` is a true frontier: rm750 is terminal |
| daggerOfRa | `rm750` `has: 11` | ditto |
| bifocals | `rm750` `has: 26` | ditto |
| redHair | `rm750` `has: 27` | ditto |
| grapes | `rm750` `has: 31` | ditto |
| pressPass | `put: 6` at `Main`, `rm300`, `rm335`; still `has:`-checked at 250/300/335 | `dangerous_sinks`, **not** the act-1→2 carry — the mechanism we catch it by is not the mechanism that makes it real |
| snakeOil | act 3 `rm630` → acts 4, **5**; empty bottle *destroyed* at the cobra nest (§5a) | `register_strandings` joint row `(12,123)=(26,5)→[730]` — ⭐ **promoted from column B 2026-08-10** |
| cheese | act 3 `rm650` → act 5 `rm740` | joint row `(26,5)→[740]` — promoted 2026-08-10 |
| snakeLasso | act 3 `rm640` → act 5 `rm700` | joint row `(26,5)→[700]` — promoted 2026-08-10 |
| smellingSalts | act 4 `rm525` → act 5 `rm720` | joint row `(26,5)→[720]` + `reg123=5→[720]` — promoted 2026-08-10 |

**B — REAL, AND WE MISS IT** — ✅ **EMPTY since 2026-08-10.** The four real act-boundary carries
are caught (rows above); the fifth, **eveningGown, was RULED not a softlock**: *"evening gown:
act 2 gate, not a softlock"* [user, 2026-08-10]. The derived mechanism (§7ab): the act 1→2 break
itself demands `wearingGown`, whose only act-1 writer costs the gown — the boundary's own
precondition, unstrandable, now pinned in `NEVER_STRANDABLE`. ⚠️ The one column-B *debt* left is
not an item: the ruled-in-scope **empty-bottle-at-act-5 death** (`global150 == 0` crossing into
act 5) has no detector — §8.

**C — ✅ RULED SAFE 2026-08-10, pending the §9 play test** (formerly CONTESTED; the user delegated
the check — *"should be checked"* — and then ruled on the findings: *"let's mark those safe, but
let's remember to put them in a play test plan later… I suspect the act 5 chase is very tight"*)

| item | user's play-side shape (2026-08-10) | what the source check found |
|---|---|---|
| workBoot | obtainable act 4, then act 5 is the chase; used in act 5; *"I don't know if it's still available in act 5"* | **available at the point of use**: `rm720:46` re-places it with NO act test, `rm720` IS the act-5 use room (verb 23 on `steve` → `put: 12` + `sGetUp`), both `sGetBoot` armings are plain takes, and `rm720` carries the act-5 chase costume branch (`view 426`) → SAFE by source |
| wire | *"same shape as the boot… I'm guessing it's really a softlock"* | source disagrees: sourced AND used at `rm430`; `wireEnd` inits acts 4 **and 5** (`(> global123 3)`, act 3 under its progress flag; `(not flag44)` = not already cut); `sGetThatWire` dresses the ego in the act-5 running `view 426`; the use (`sWireItShut`) is act-5-only. Arrive wireless → cut a fresh one at the door, **if you hold the wireCutters** — the strandable link is the CUTTERS, already column A |
| dinoBone | obtained act 2, used later, availability unknown | `rm480:79` respawn guard, NO act test; the bone is **never consumed** (zero `put: 18` sites); real uses `rm500` (`sSmashPlaster`, self-limited to acts ≤4), `rm600` (`sBreakGlass`), `rm650` (`sDisarmTrap`) — all in `rm480`'s museum block → SAFE by source |

**D — OUT OF SCOPE BY THE 2026-07-26 RULING** (their absence from `s.required` is correct)

- The 8 examine-to-know conviction items: pocketWatch, garter, ankhMedallion, watney_sFile,
  warthogHairs, carbonPaper, yvette_sShoe, and the notebook's evidence pages.
- **magnifier**, **pippin_sPad**, **waterGlass** — reclassified out of column B on 2026-08-06.
  All three were listed as missed carries in the old §5.
  ⛔ **CORRECTED 2026-08-09: the stated reason was FACTUALLY WRONG.** It read "measured, none of
  them has a downstream `has:` use site at all" — but LB2's use sites are **verb-dispatched**, and
  the verb number is the inventory item's `message` property (`invCode.sc`), not the item index.
  `waterGlass` is `message 38` and has **two** real use sites, `rm510` and `rm700`, both arming
  `sListen`. Its source is `rm350` (the `waterGlass1/2/3` tray). USER CONFIRMED 2026-08-09: *"the
  water glass is used to eavesdrop on conversations"* — so the **conclusion (out of scope) stands
  and the reasoning does not**. Never check an LB2 requirement by grepping `has: N`.
  ⚠️ This matters operationally: the act-5 deadly-exit fix (§7u) makes `waterGlass` a flagged
  finding, which trips `test_lb2_ground_truth`'s "nothing OUT OF SCOPE is flagged" check. The model
  derives requirements from use sites and cannot tell an eavesdrop `setScript:` from a progress
  one, so this needs a ruling (§8) rather than a patch. magnifier's need runs through evidence examination, pippin_sPad's
  through the act-5 riddle UI, waterGlass's through eavesdropping. Under "gate on items only" these
  are exactly the layer the ruling excludes, so they are not gaps — they are the ruling working.

**E — CONFIRMED SAFE** — everything else. Flagging one is a false positive. Note in particular the
act-local consumables (coupon, sandwich, claimTicket, baseball) which are *spent by design*: a
guard demanding you still hold them is not conservative, it is unsatisfiable — see §7c.

---

## 6. SCOPE FOR THE LAURA BOW GAMES (user ruling, 2026-07-26)

**Gate on items only.** Evidence examination, who is standing where, which conversation you
overheard — *"that's the whole point of the game."* We do not model it, and an accusation the
coroner rejects because you never looked at the medallion is not a finding we owe.

Consequences, so this is not re-litigated:
- The five `has:`-checked ending items are **in scope and count as strandings**, notwithstanding
  that LB2 always reaches *an* ending. They are items, and they are irreversibly missable.
- The eight examine-to-know conviction items are **out of scope**, and their absence from
  `s.required` is correct behaviour, not a gap to close.
- The act-boundary carry items in §5 column B are **in scope** and currently missed.

Deaths are a separate question and the standing project rule is that they are in scope
([[one-rule-death-is-in-scope]]). LB2's act-5 chase is a long chain of them (§4) and none is
modelled. That is recorded here, not gated on, pending §8.

---

## 7. WHERE WE ARE — the short version (2026-08-10)

> ⛔ **This section's history corrected itself twice (§7u, §7y) before closing.** §7u put column B
> at 1 of 5 (snakeLasso had been "caught" by a `fatal_uses` FP); §7y took it to 3 of 5 by walking
> the joint projections; §7ab landed the last two blockers and the 2026-08-10 rulings settled the
> remainder.

**Column A 10 of 10 · Column B EMPTY (closed 2026-08-10) · Column C: checks done, awaiting the
user's word (§8 item 1).** The four real act-boundary carries were PROMOTED into column A;
eveningGown was RULED an act gate (§8 item 5) and is pinned `NEVER_STRANDABLE`; the former
KNOWN_RED is promoted and deleted.
✅ **The `skeletonKey` FP IS DEAD** (2026-08-10, latest) — §7ad. The oracle test is **9 of 9
GREEN**: every real softlock caught, zero false positives. With it died the
armed remedy it carried (the `(not (gEgo has: 8))` action spec and the rm630 applied placement —
a prohibition at the key's real use site, the Spinach_Dip shape).
✅ **The hardening round** (2026-08-10, closing) — §7ae: the watched surface RE-BLESSED on the
user's word; the oracle retrofitted to MECHANISM PINS (whole rows, per the 2026-08-09 ruling);
and the STREET SEAL declared as the file's one deliberate red — so "zero declared reds" above is
now, deliberately, one.
✅ **Remediation round 1** (2026-08-10, later) — §7af: the SOLE-EXIT DEFERRAL lands and all four
act-break demands PLACE (`entry-deferral-PARTIAL`, stage-scoped on the game's own act register).
⚠️ Two of the four rest on the street-seal gap and would wall if shipped — they retract when the
seal lands; nothing ships. Open: the register-write hold and the joint rows' specs.
✅ **The empty-bottle death IS caught** (2026-08-10, later): `register_value_strandings` —
see §7ac. One row corpus-wide: `reg150==[0]@seal(12,123)→[730]`.
Nothing safe is flagged, so the false-positive side is clean. The five misses turned out to be
**three independent causes**, all diagnosed and measured:

| # | cause | closes | the fix |
|---|---|---|---|
| 1 ✅ | **The act register could run backwards.** `_inroom[123] = {rm355: [0], rm630: [4]}` — two in-room writes whose from-value was lost, so at act 5 the model set the act back to 4 and re-entered `rm525`. | **smellingSalts — LANDED** | Every ordered step of `_rstep[123]` is `k→k+1`, so: **a register that COUNTS (≥2 ordered steps, all consecutive, >2 values) may not be DECREASED by an unordered write.** Read off the model's own step relation. Post-pass in `_build_product`; corpus census = 3 registers, none in LSL2/KQ4. §7s |
| 2 ◐ | **Act 5's walls are deaths on entry.** Act 5 is an 11-room pursuit region entered at `rm420`; its only two exits (`north 350`, `west 500`) run `sLauraDies` when `global123 == 5`, conditioned on arrival direction. | **snakeLasso LANDED**; cheese and snakeOil still open | Half built. LB2's deaths are now REAL (0 → 37 DEATH transitions) via the three death fixes below. The remaining piece is precision — and the obvious fix for it FAILED, see §7t. |
| 3 ⛔ | **`get:` is variadic and we read one argument.** `(global0 get: -1 32)` — `-1` is a "silent pickup" sentinel, the items follow it. 13 sites lost, 28% of LB2's acquisitions. | eveningGown, and it clears the `skeletonKey` FP | **BUILT AND REVERTED 2026-08-09 — blocked on the debug exclusion.** The rule itself is right and derived: `get`'s role is `dest_fixed='ego'`, `dest_arg=None`, so there IS no destination argument and *every* argument is an item; `-1` filters out as a non-item. Measured, it gives `eveningGown` its real source (`rm270`). **But it is a NET REGRESSION without the exclusion** — see below. §7o |

**Build order:** 1 ✅ landed, then 2, then 3.

### ⭐ THREE BUGS FOUND BY BUILDING #1 — each exposed by fixing the last (2026-08-09)

Cause #1 landed and its own side effects led straight into three defects that had nothing to do
with it. None was invented by the change; each was already there, masked.

| # | bug | fix | measured |
|---|---|---|---|
| A | **LB2 had NO deaths at all.** `derive_death_send` finds `(99, 'deathRoom')`, but `lower_death_sci11` only injected into a `changeState` switch and LB2's dialog offers Restore/Restart from `init` — a silent `continue`. | Inject at the object's **ENTRY**: own `init` if it has one, else `changeState` case 0. `init` IS the SCI entry point; `Script` overrides it to dispatch to `changeState(0)`, so case 0 is not a second rule. Silent skip → loud `[degraded]`. | KQ6 unchanged: 66 DEATH transitions, 34 rooms, 0 of its 4 dialogs define `init` |
| B | **A death SCREEN was walkable.** `deathRoom` is a picture and a `repeat` around a 3-button Print that never returns — and it declares `north 350`, which the game never reads. We took it at face value, so the model could travel by dying, and `rm99` became a sink witness and a guard target (`pressPass@rm99`, `rm210->rm99: (gEgo has: 6)`). | A death dialog that IS its script's room object is a death screen → joins `_no_walk_rooms`, exits dropped. | 1 of 1 on LB2, **0 of 4 on KQ6** (its dialogs are cutscenes inside real rooms) |
| C | **A room's own `newRoom` override was unread.** `rm666` — the dark passage — exits via the placeholder `(gRoom newRoom: 0)` and picks the real destination in its own `newRoom` from `global12`: from 520→610, 630→454, 650→560 (or 565). Reading the literal left it a pocket with no way out, which made `lantern` look stranded. | `_newroom_override_edges`: read the rewrites, ADD them as guarded edges (adding movement is the safe direction). | `rm666` → `[0, 99, 454, 560, 565, 610]`; `lantern` FP gone; `newRoom: 0` occurs in exactly one room corpus-wide |

**On `lantern`:** it was flagged, §5 says `act-local`, and §5 was right — the pocket was ours, not
the game's. Recorded because the standing rule is that an addition is SUSPICION and enumerated
ground truth is never reclassified to make a change look good.

### ⛔ WHY #3 IS REVERTED, AND EXACTLY WHAT IT NEEDS (2026-08-09)

The variadic read is correct and lands `eveningGown`'s real source. Measured with it in:

    eveningGown    sources=[270]              <- right, Lo Fat's, as the user described
    skeletonKey    sources=[0, 29, 500]       <- 500 real; 0 and 29 PHANTOM
    cheese         sources=[0, 29, 650]
    smellingSalts  sources=[0, 29, 525]       <- ...and smellingSalts LEFT the softlock list

**Script 29 is `whereTo` — the debug jump-to-act room — and it is the ONLY caller of `Main`'s
`proc0_13`…`proc0_17`**, which hand over nine items each (`(ego get: -1 25 16 17 30 27 26 12 31
13)`). Read as sources they make the items obtainable from Main scope, which `_sink_rooms` widens
to every room, so a confirmed finding vanished. §1a predicted this in 2026-08-06:

> *"Anything that models the act must exclude `whereTo`'s `-300` block the way
> `config.debug_globals` excludes LSL2's; LB2's `debug_globals` is presently empty."*

**It is reverted rather than shipped**, because a change that deletes a play-confirmed stranding is
worse than the gap it closes — the standing rule is that a DROP is a regression.

### ⭐⭐ §7ab. BOTH BLOCKERS LANDED — and the evening gown turns out to be the act break's PRICE, not a carry (2026-08-10, later)

Three changes shipped, each derived, each measured **byte-identical on LSL2, KQ4 and KQ6**.

| # | change | where | corpus profile |
|---|---|---|---|
| 1 | **`get:` read as VARIADIC**, from the wrapper's own body: `Ego::get` is `(for ((= temp0 0)) (< temp0 argc) ((++ temp0)) ((global9 at: [param1 temp0]) moveTo: self))` — a `ComplexVariable` indexing the ARGUMENT LIST under an `argc`-bounded cursor. That shape, not "`dest_fixed` and no `dest_arg`", is what says "every argument is an item". | `vocab._argc_temps` / `_variadic_item_arg` / `Vocabulary.transfer` | `get` is variadic in ALL FOUR games (it is SCI's own `Ego::get`), but **multi-argument call sites: LSL2 0, KQ4 0, KQ6 0, LB2 16** — so it is inert elsewhere by construction |
| 2 | **A PROCEDURE IS NOT A HANDLER.** `opmodel`'s handler pass walked every script-level procedure standalone in its scope's rooms. The engine dispatches methods; a procedure runs only where it is CALLED, and all three walkers already follow calls in the caller's own room. | `opmodel.py` (the `for pbody in s.procs.values()` walk, deleted) | this is what made `whereTo`'s debug hand-outs into room-0 sources, i.e. sources EVERYWHERE. Nothing to do with detecting debug code — it never asks what a script is for |
| 3 | **The object-property store reached through a GLOBAL.** `_prop_receiver_script` resolved `ScriptID` exports and unique names; a global only ever assigned one object is just as static. Bounded, because those objects are usually the ENGINE's: only a property the class INTRODUCES and that no class introducing that name ever uses itself. | `vocab.derive_global_props` / `_introduced_unused` / `lower_obj_props(split_chains=)` | **LSL2 0, KQ4 0, KQ6 0, LB2 2** (`ego.wearingGown`, `IconBar.walkIconItem`) — the profile of a real store, not a fitted one |

⚠️ **#3 needed `lower_obj_props` to SPLIT CHAINED SENDS**, and that is a rule, not a workaround:
the one load-bearing write is `(global0 put: 32 wearingGown: 1 setMotion: …)`. Lowering the reads
and skipping that write is not "missing a write", it is **half a store** — a register whose only
setter is invisible reads 0 forever, and a permanent 0 *fabricates a seal*. `derive_room_locals`
already refuses to half-lower for exactly this reason. The split is scoped to the new pairs;
curing the same defect for the existing ones is 283 more sites in KQ6 and 90 in KQ4 and needs its
own measurement. **Open item.**

**AND ONE FALSE POSITIVE, WHICH TOOK TWO TRIES TO DIAGNOSE.** #1 gave `notebook` its sources and
it was promptly flagged — the FP `NEVER_STRANDABLE` was written to catch. The model was RIGHT
about the graph: `intro` (script 92, a `Rgn` live in rooms 100…220) claims ESC and runs
`sFadeToBlack` → `newRoom: 26`, so the intro really is skippable and rm220's grant really is
bypassable. The fault was the REQUIREMENT: rm300's bar door arms `sEnterBar` from verb 4, verb 6
**and verb 14**, and 14 is the notebook's `message` — a synonym for "talk to the doorman".

> **An item only SOME armings demand is not a gate.** `missability`'s `required` now reads a
> machine's entry guards through the intersection of `_own_required` over every entry.

The requirement-side twin of the rule `fatal_uses` already carries (*a death armed on one arm of a
fork does not condemn the fork*) and of `_own_required`'s own OR-branch exclusion — the same
disjunction, spelled as separate entries instead of a `GOr`. ⚠️ My first attempt used
`entry_musts`, which reads each alternative with `_own_positive` ("a mention, not a proof") — and
every one of `sAskEnterBar`'s entries conjoins the whole `GOr` of its armer's three cases, so
own(2) is mentioned in all three and the intersection kept it. **The fix has to use the same
reading as the consumer.** It also drops `daggerOfRa`/`wireCutters` from `required@460`, where
`sCutRope` is armed by verb 21 (wireCutters) OR verb 22 (daggerOfRa); both stay caught on rm750.

#### ✅ WHAT THE MODEL NOW DERIVES ABOUT THE GOWN — and why nothing was flagged

    rm250 -> rm26   req {wearingGown: {1}, prevRoom: {300}}      <- the ACT 1 -> ACT 2 break
    rm320  sLauraChanges  writes wearingGown := 1, entries [own(32), own(32)]

`rm250.sc:71` is `(cond ((and (== global12 300) (global0 wearingGown:)) (self setScript: sACTBREAK)) …)`
and `sACTBREAK` state 10 is `newRoom: 26`. So **the act-1 break is gated on an ego property, and
the only act-1 writer of that property costs the evening gown.** This is the act-gated-movement
shape §7h asked for and §7q/§7r looked for in the wrong idiom — a third spelling to add to §7z's
table, and the first one that is an EGO property rather than a room's.

**No verdict moved, and that is the finding.** The gown is not carried ACROSS the act boundary; it
is the boundary's own precondition. Nor is it strandable:

* `rm270` gives it **unconditionally** (`source_guards[32] = {270: [[]]}`);
* `rm250` re-places the laundry ticket while you hold neither ticket, nor gown, nor gown-worn;
* `rm250 / rm270 / rm320` are one strongly-connected act-1 block (measured: rm270 and rm250 are
  both reachable from rm320), so no reachable state loses access.

Sierra's own hint file settles it: *"Act 1 never seems to end… e) Pick up an evening gown at Lo
Fat's Laundry then put it on at the speakeasy"* — listed among the five things that **END ACT 1**,
not among the things you carry into act 2.

⛔ **SO §5's eveningGown ROW ("spans 1→2; no entry to the fundraiser") IS THE SAME SHAPE AS THE
THREE `CONTESTED` ROWS** — a walkthrough's "you need it in act 2" read as a carry, where the game
gates the transition itself. **It is NOT reclassified here. Report and ask** (§8).

⚠️ And note what did NOT happen: **the ego-property store does not seal the street**, exactly as
§7aa's own table predicted and its prose then talked past. Once `wearingGown` is a real register
it is *satisfiable* in acts 2–5 (you are wearing the gown), so `rm330`'s taxi disjunction reduces
to the "honest disjunction" row — measured, still acts 1–5 in the street block. The seal is the
arrival taxi being driven **off-screen** by `sTaxiLeave` (`MoveTo 369 125`, x beyond the 320-wide
screen) under `handsOff:`, so it can never be verbed. That is a POSITION mechanism and is still
unmodelled. **Do not re-read §7aa as if the store were the street's cure; it is the ACT GATE's.**

### ⭐⭐ §7ad. THE skeletonKey FP IS DEAD — a hands-on wait is pre-emptable (2026-08-10, latest)

**The FP**: `fatal_uses` condemned `skeletonKey@rm630/sUnlockTrunk` — every lifted path of the
unlock reaches state 10's `global145 := 1` + `newRoom: 99` (the ferrets). **The truth**: state 6
does `(global1 handsOn:)` + `(= seconds (if (HaveMouse) 6 else 12))` — control comes BACK with a
clock running — and using the meat arms `sInsertMeat` into the same `('G', 2)` slot, disposing the
pending death. Unlocking the trunk is the *solution*; the meat's cost rides sInsertMeat's own
entry (`own(9)`), as a requirement should.

**The rule, all three parts derived:**
1. `vocab.derive_control_selectors` — the Game hierarchy's control switches, found as methods
   writing constant 0/1 to names the USER class itself declares (property or method — SCI0 spells
   `canInput` as a property, SCI1.1 makes both methods). LSL2/KQ4 derive no restore selector, so
   the whole feature is inert on SCI0 by construction. KQ6/LB2: `handsOn → restore`.
2. `machine._restores` marks a state ONLY when it pairs a restore send with a write to the
   engine Script class's own cue clock (`seconds`/`ticks`/`cycles`… — read off `Script::doit`'s
   countdowns, not listed). ⚠️ **The restore send alone was the warned naive form and it did
   exactly what the warning said**: every SCI1.1 cutscene ends with a `handsOn:`, so marking
   those made every doomed machine pre-emptable and KQ6's fatal_uses went to zero in one
   measurement. Restore∧clock = "you are free, and something is coming" — the window is the fact.
3. `_survivable(…, preempt=)` — a marked state is safe when a same-slot competitor
   (`entry_recv`) is not itself in the evolving `unavoidable` set: the slot-race semantics
   `death_traps` is already built on, seen from inside the machine. Only `fatal_uses` passes
   `preempt`; `death_traps` is untouched, so the lingering-timer death class keeps its prices.

**Measured**: LSL2/KQ4/KQ6 snapshots byte-identical (KQ6's `skull@rm420/throwSkull` survives —
it never hands control back); LB2 loses exactly the skeletonKey rows. **The oracle is 9/9.**

### ⭐ §7af. REMEDIATION ROUND 1 — the SOLE-EXIT DEFERRAL: all four act-break demands now PLACE (2026-08-10, later)

**The rule** (`guards.defer_to_entry` + `patcher.apply_guards(defer_info=)`): a demand whose
trigger resolves to `sole-exit` — the pocket's one `newRoom:` lives inside the cutscene the wrap
would refuse to arm, so refusing in place strands the player on the card (§7i) — is re-sited to
the pocket's PREDECESSOR rooms as `(or (not <stage>) <demand>)`. This is the demand-side twin of
the prohibition deferral (the Spinach_Dip raft) and reuses the arrival-commit re-site machinery
(`_guard_arrival_entries`) with the stage passed in rather than read off proc-call heads.

Three derivations, each refusing rather than guessing:
- **The stage is the out-edge's own `_emeta` requirement** (positional registers dropped, exactly
  as the KQ6 re-site drops prev-room clause heads): the act-break card's crossings are not
  distinguishable by position at the entry sites, but the game's own register state names each
  one — `rm26->rm330` is `(== global123 1)`. Any meta alternative that is stage-free,
  multi-valued, or unspellable refuses the whole deferral: an under-stage gates crossings the
  spec says nothing about.
- **A promoted PLAIN global may spell its own stage** (`_stage_spelling`): `render_register`
  refuses real globals for DEMANDS, rightly — only a store's reversal proves the game's reading —
  but a promoted gating register's promotion IS the evidence (LB2 tests `global123` at 239
  sites), so a register no lowering claims, below the synthetic base, at a walk-reached value,
  spells directly. Deliberately NOT widened into `render_register`; that is its own measured
  change.
- **The site list is ALL predecessors, not `commit_entry_frontier`** — a game that STARTS behind
  its own act-break card (the intro's 0→1 break) makes `reach_avoiding` call the entire game
  "inside the pocket", leaving only the intro rooms. Every entry to a sole-exit pocket is a fresh
  committed crossing; what protects the player is the per-site pair of filters: stage
  presentability (`_pstates` — this is what keeps the wraps out of the intro rooms, which only
  ever cross at act 0) and COMPLIANCE (`unsatisfiable` at the site's own crossing — a site where
  the demand can no longer be met is refused, because a demand you cannot meet is a wall).

**Measured**: LSL2/KQ4 goldens byte-identical, KQ6 watched surface unchanged (no sole-exit rows
there), LB2 moved by exactly the four rows → `entry-deferral-PARTIAL sites=4` each, wraps read
in the emitted source at rm250/rm454/rm480/rm620 (`sACTBREAK` / `sFinishIt` armings, silent
no-else arm-gates, mode-off bypass intact). rm500/rm520 report `no wrappable site` — the PARTIAL
is honest. One bug caught by READING the emitted source, again: the first cut embedded the
`dest_test` discriminator — script 26's `local0` — in rooms where that name means something
else; the deferral now uses the pre-dest_test condition (the stage discriminates instead).

⚠️ **TWO OF THE FOUR PLACED DEMANDS REST ON THE STREET-SEAL GAP AND WOULD WALL IF SHIPPED.**
The `rm26->rm355`/`rm26->rm420` pressPass demands (stages 2 and 4) exist because the unsealed
model keeps rm250 "needing" the pass in acts 2–5; in truth the pass is surrendered at the act-2
door and the street is sealed, so a stage-4 wrap demanding it would silently refuse the real
4→5 break for every player. The compliance filter passed them because it walks the same unsealed
model. **Nothing ships** (standing rule; §9 play pass gates that), and when the street seal
lands (§7z red) those two specs retract on their own — which is the right dependency direction:
fix the model, not the placement. STILL OPEN in this round: the `reg123=5` register-write hold
(salts+grapes) does not place — `guard_prop_flag_owner_write` looks for a free-running writer
and LB2's act write is player-committed (§7j: LB2 has no free-running clock); it needs this same
deferral taught to register-write specs. And the joint rows (cheese/snakeOil/snakeLasso at the
`(26,5)` seal) still emit NO spec at all — the seal's entering write is the act break, so their
remedy is this same site once the joint→spec synthesis exists.

### ⭐ §7ae. THE HARDENING ROUND — re-bless, mechanism pins, and the street-seal RED (2026-08-10, closing)

Three closes in one pass, all in `src/test_lb2_ground_truth.py` + `tools/run_tests.py`:

1. **The watched surface is RE-BLESSED** (user's word given). The 38-row diff was re-read before
   refreshing — every row one of the day's intended changes — and both surfaces (KQ6, LB2) are
   green again. One row of it deserves its own record: **pressPass moved detectors.** The
   `dangerous_sinks` catch on the three `put: 6` sites retired, and `analyze` now flags it needed
   at rm250 past the act-1→2 frontier — the catch is finally FOR the reason §5 gives (the act
   1→2 span). A name-scored oracle could not have seen that move at all, which is point 2:

2. **MECHANISM PINS** (the 2026-08-09 ruling, *"pin whole deserialized objects, not names"*,
   applied — LB2 only, KQ4/LSL2 golden). Every column-A item now pins the FULL set of detector
   rows that catch it (`MECHANISM_ROWS`), serialized in `snapshot.py`'s own shapes so a row can
   be eyeballed against the watched surface; and an ATTRIBUTION TABLE (item → every detector row)
   prints on every run, so "caught for the wrong reason" is visible in the run that does it.
   A pinned row dropping or changing is a regression to confirm; a new row is suspicion. The
   snakeLasso churn (two sessions planning on a `fatal_uses` FP that named the right item) is the
   failure this makes automatic.

3. **The STREET SEAL is a declared RED** (`tools/run_tests.py` KNOWN_RED). Ground truth §7z: the
   street block (250/260/270/300/310/320) is unreachable once the museum acts start. Measured
   today: the act projection walks all six rooms at acts 2–5 (the joint `(12,123)` at 2–4). The
   check asserts the truth and fails, per the no-green-limitations rule — the honest derivation
   cannot produce the seal because rm330's arrival-taxi init is `wearingGown:`-guarded
   (satisfiable in acts 2–5, §7aa), and the real mechanism is POSITIONAL (`sTaxiLeave` drives
   the taxi off the 320-wide pic under handsOff) — census-#1 control-map class, unmodelled.
   Goes green only when a derived mechanism seals the street; promote it when it does.

### ⭐⭐ §7ac. THE EMPTY BOTTLE IS CAUGHT — `register_value_strandings`, the register twin of the item rows (2026-08-10, later)

**The ruling it implements** [2026-08-09]: *"you should have enough snake oil left before entering
act 5 to not die because of it in act 5"* — the boundary value is the stranding, the spend
arithmetic is out of scope. **The mechanism, all source-verified this session:**

    global150 = 4 at Main; -- per shake (rm520 cobraDoor, rm610 pipe/drain); sDumpIt pours it out
    rm610 vat refill: (if (< cel 3) (++ cel) (= global150 4))   <- THREE refills, metered by
                                                                    flags 105/106/107
    rm730 verb 25 (the snake-oil verb): (== 150 0) -> sThrowBottle (put: 14, destroys the bottle,
                                        passes NOTHING); else sSprinkleOil / sRepelSnakes
    the (12,123) joint proves rm610 unreachable once act 5 begins

**The detector** — same flips, same walks, same conjuncts as `register_strandings`' item rows,
register-shaped: the flip is reachable with `S == b`; a machine past the seal demands `S ∈ acc`
with `b ∉ acc` (through `_reg_entry_demands`); **the register is FROZEN past the seal** (no write
of any value — the causality conjunct); a pre-flip write could have fixed it; the goal survives.
**Corpus: LSL2 0 · KQ4 0 · KQ6 0 · LB2 1 — exactly the ruled softlock.** Pinned green in
`test_lb2_ground_truth` ("the empty-bottle act-5 crossing is caught"). Snapshot key
`register_value_strandings` appears only when rows exist, so the golden fixtures stay frozen and
a first row on a golden game is a loud new key.

**Three lessons paid for while building it, kept so they are not re-bought:**
1. **The arming floor cuts both ways.** `sSprinkleOil`'s chained entry embeds its armer's whole
   entry disjunction with the recursion cut at the floor, and the floor arm read flat dissolves
   every demand it embeds. `_reg_entry_demands` resolves chained entries through the ARMER's
   demand, coinductively (a back-edge vouches for nothing new — entering a cycle passes some
   member's direct entry), and resolves a doit-arming gated on a room-local latch through the
   latch's machine writers (`local3 := 1` lives in sSprinkleOil state 2; the fifth store's
   writer set is complete by construction, which is what makes the hop sound).
2. **A machine that consumes an item still required where it stands is the LOSS, not the way
   past.** Read as a demand site, `sThrowBottle` inverted the finding into "you can never throw
   the bottle away".
3. **The freeze conjunct is what separates a carry from choreography.** KQ6's wedding-sealed
   castle produced 4 rows about guard-march flags — registers the sealed region itself keeps
   toggling — and LB2's flag 63 (wire handshake, set in the rm435 inset, CLEARED by rm430's cue)
   produced 3 more. If the region can write the register, its value there is the region's working
   state, and blaming what you carried across is wrong attribution. prevRoom is excluded as the
   demanded register for the same reason one level up: movement itself rewrites it.

⚠️ **A real upstream gap found and NOT yet fixed, recorded before the FP-rows it caused were
cured for the right reason:** `_emeta[(430,435)] req = {123: {3}}`. The skewer's guard is
`(or (> global123 3) (and (== global123 3) <stage>))`, and `guard_reqs` reads it FLAT — the
relational arm is ignored, the `== 3` arm is kept — so an OR-arm's atom NARROWS the edge instead
of widening it, and rm435 (Ziggy's-body close-up, the wire-cut enabler) reads act-3-only in the
whole product while the game keeps it verbable in acts 4–5. This is the whale lesson
(`structural_reqs`' docstring) sitting in `edge_meta`'s own req extraction. The cure — structural
reqs on edges — moves every disjunctively-guarded edge corpus-wide and needs its own measured
round. **Open item; do not let the freeze conjunct's success hide it.**

### ⭐ §7z. HOW THE MUSEUM SEALS THE STREET — and the refutation of "zero act-gated exits" (2026-08-10)

**USER GROUND TRUTH:** *"the outside of the museum is not reachable once the museum acts start.
So you need to figure out how that's enforced in the game before we proceed further."* Also:
*"the notebook gets granted during a cutscene at the very beginning, there's no way to not have
it"* — recorded as `NEVER_STRANDABLE` in the oracle test, because the variadic read newly flags it.

This matters beyond eveningGown: the model says **`rm270` (Lo Fat's, the gown) is reachable at acts
1–5**, and that is now known to be WRONG. Two mechanisms, found by reading `rm330` — the museum
steps, which is the ONLY junction between the street block (250/260/270/300/310/320) and the museum:

    rm330.sc:158   (if (< global123 2) (taxi init: stopUpd:))
    rm330.sc:345   taxi doVerb 4 -> (setScript: sInTaxi) -> state 4 -> (newRoom: 250)
    rm330.sc:170   doit: ((proc0_1 global0 256) (setScript: sHitEdgeScreen))
    rm330.sc props  south 250

1. **The taxi is the exit, and it is act-gated.** `sInTaxi` is the only script in the room that
   reaches `newRoom: 250`, it is armed only by `taxi doVerb 4`, and **the taxi object is only
   `init:`ed while `global123 < 2`.** From act 2 on the object does not exist, so the verb cannot
   be dispatched and the exit cannot fire. *An object that is not initialised cannot be verbed* —
   which is the "act-gated `init:`" shape §7h asked for, in a place §7q/§7r never looked.
2. **`south 250` is a DEAD LETTER.** Stepping on control 256 arms `sHitEdgeScreen`, which says a
   line, turns Laura around and walks her back (`MoveFwd 10`). The nav property is never consumed;
   the room refuses the edge. Same class as LB2's `deathRoom north 350` (`extract.death_screen_rooms`)
   and rm640's exits in KQ6 — **a declared exit the room's own `doit` intercepts**.

⛔ **THIS REFUTES §7q/§7r's "ZERO act-gated exit sites corpus-wide", which is quoted in three
places including the RED test.** That measurement asked for an `init:` **on an `ExitFeature` or
`Door`** — and LB2 does not spell it that way. The real spellings, measured:

| site | spelling | class |
|---|---|---|
| `rm330:158` | `(if (< global123 2) (taxi init:))` | **Actor** whose `doVerb` arms the exit |
| `rm370:76` | `(if (> global123 2) (giftShoppeDoor locked: 1))` | **Door**, but `locked:` not `init:` |
| `rm370:31` | `(if (== global123 2) (self setRegions: 93) ... else (setRegions: 90))` | the room's OBSTACLE SET |
| `poly2360Code:42` | `(= points (if (> global123 2) @local0 else @local24))` | the walkable POLYGON itself |

So the acts DO gate LB2's movement; they just never do it through the one idiom that was searched
for. Two of these four are the control map (census #1) and are out of reach for now, but the first
two are ordinary object state and are not.

⚠️ **Do not re-run "grep for an act-gated ExitFeature/Door init".** It answers a question narrower
than the one being asked, and answering it "zero" sent this project down the §7h/§8-item-4 path for
two sessions. The question is *"what, if anything, makes this exit unavailable in this state"* —
and the answer can be an actor's existence, a door's `locked:`, a region, or a polygon.

### ⭐ §7aa. THE CONDITIONAL-INIT RULE ALREADY EXISTS — the blocker is an EGO PROPERTY (2026-08-10)

USER: *"the init condition should be more generic than just act boundaries. I can imagine lots of
other mechanisms. Any condition, when that condition isn't met."* Right — and **the model already
does exactly that, fully generically**, `machine.py:698`:

    # ...and the arming cannot be freer than the object whose method it sits in: a method
    # of an object the room only conditionally `init:`s only runs under that condition.
    self._add_entry(m, 0, _conj(apc + [owner]), loc, ...)

`owner` is whatever guards the object's `init:` — any condition, not just an act. Measured on the
taxi: `sInTaxi`'s entry guard really is

    GAnd([opaque, GOr([ GAnd([GNot(12==335), opaque]), 123<2 ])])

so nothing needs building here. **Do not re-implement it.** Two things stop it from biting:

**1. `rm330` has TWO `taxi init:` sites, so the owner condition is a DISJUNCTION.**

    rm330:158  (if (< global123 2) (taxi init: stopUpd:))                    <- the act gate
    rm330:82   (else ... (if (global0 wearingGown:) (taxi posn: init: ...)))  <- the arrival taxi

and `wearingGown:` is an **ego property we do not model**, so it lowers to `opaque` and the OR
cannot be reduced. A disjunction with an unknown arm correctly yields no requirement. **The model
is not wrong here; it is ignorant, and in the safe direction.**

**2. `south 250` is a free parallel row** from `_nav_edges` (a dead letter — control 256 arms
`sHitEdgeScreen`, which turns Laura round). Two rows, both `({}, {12: 330}, ...)`.

**MEASURED at the product level** (mutate `_emeta`, recompute the projections only — note
`_build_product` REBUILDS `_emeta`, so editing it and calling that throws the edit away):

| variant | outside rooms (250/260/270/300/320) |
|---|---|
| baseline | acts 1,2,3,4,5 |
| drop the nav row | acts 1,2,3,4,5 — **not enough on its own** |
| the honest disjunction `NOT(12==335 AND 123>=2)` | acts 1,2,3,4,5 — the act break arrives with `12==26`, so the `12!=335` arm is open |
| `123<2` alone | **acts [1] — THE STREET IS SEALED** |

So the seal is real and the model can express it; what it cannot do is *derive* it, because the
gown disjunct is opaque. **And even sealed, `eveningGown` is still not flagged — it has no source
until the variadic `get:` lands.** Closing the gown needs BOTH.

**⭐ AND THE GOWN'S USE SITE IS THE SAME PROPERTY**, which is what makes this worth building rather
than routing around: `rm270.sc:366` is `(or (global0 has: 32) (global0 wearingGown:))` — item 32
IS the gown — and `rm320.sc:211` is the write, `wearingGown: 1`. The chain *get it → wear it →
be admitted* runs through the property, not through `has:`.

**THE PROPOSED STORE, with its pre-implementation census.** `vocab.item_property_registers`
already discovers the fourth store by asking which properties the game both WRITES with a constant
and READS back — but it is scoped to the inventory class via `item_of_receiver`. Generalise the
same discovery to the EGO. Raw, that is noisy (LSL2 5, KQ4 5, KQ6 9, LB2 3 non-drawing properties);
the discriminator is pure class-table derivation, the same principle as
[[derived-vocabulary-not-catalogue]] — **a property the game's OWN ego subclass declares and its
engine ancestors do not**:

    dagger   class ego   (script 19)  declares wearingGown   <- game-specific, script < 900
    ALL      classes Actor/Ego/View/Prop (988, 998), Talker/Narrator (928, 909), Body (914),
             RandCycle (941)          declare looper, scaler, scaleSignal, maxScale, reset,
                                      currentSpeed, ignoreHorizon, oldScaleSignal

Applied, that yields **exactly one property in exactly one game: LB2's `wearingGown`** — the same
profile as the fourth store (KQ4 three items, LSL2 none), which is the sign of a real store rather
than a fitted one. It is also the store `snakeLasso`'s survival arm needs (`mummy cel:`), so one
build closes two open items. Not started.

### ✅ §7y. CAUSE #2 IS CLOSED — `register_strandings` now walks the JOINTS (2026-08-09, later)

§7w ended with "the load-bearing blocker for column B is now `{r for r, _ in back}`". It was not.
The blocker was one loop header, and §7w had already named it without following it: the joint
`(12, 123)` **was being built and nothing was reading it.**

    missability.py:2857   for R in self.regs:      <- scalars ONLY
    missability.py:1926   self.proj = list(self.regs) + list(self._joints)
                          "...only the four reachability walks look at `self.proj`"

`register_strandings` is the detector that reports seals, and it was the one place that could not
see a seal expressed in two registers. **Now it iterates `self.proj`.**

**THE USER'S FRAME, which is what produced this** (2026-08-09): *"the stuff that in the previous
game was static — where an item was, whether you could get to it — becomes changeable in LB2 …
we need to parametrize edges, item provenance, item availability based on whatever register values
the game is looking at. It's a generalization of the previous model."* The parametrization was
mostly already there (`_emeta` per-edge reqs/sets, `_pstates` per projection, `source_guards`);
what was missing is that **joint state was a special favour rather than the default**.

    LSL2   0 -> 0 rows     KQ4   0 -> 0 rows
    KQ6    1 -> 1 row      (its one joint (12,173) adds nothing; the row's KEY SET is unchanged)
    LB2    2 -> 14 rows / 9 distinct items, INCLUDING cheese and snakeOil

**Three scalar assumptions had to be generalised**, all of them "the flip landed on `w`": a joint
is entered into `w` when SOME component register is written to its component of `w` (requiring the
whole tuple at once finds nothing — no single write sets two registers, which is precisely why the
seal was invisible). Factored out as `_flip_seeds`.

**And the first cut produced 163 rows carrying 9 facts** — prevRoom's 2026-08-02 degeneracy (323
junk rows on KQ6) wearing a tuple: reg 12 is written by every crossing, so a sealed region reports
once per (room-you-came-from, act) cell, 19 prevRoom values deep. The cure is `_collapse_flips` and
it is derived, naming no register: **rows for the same item whose SEALED REGION is identical are
one row**; flip rooms and values merge, genuinely different regions stay separate. `value` keeps the
lowest merged value and `values` appears only when a merge happened, so a row that merged nothing —
KQ6's letter — is byte-identical to before.

⚠️ **Joint rows are DETECTION-ONLY in `guards.guard_specs`.** The `register-write` remedy holds one
register's write until the items are in hand, and a seal that exists only at `12 == 420 AND
123 == 5` names no single write to hold — neither component's flip is by itself the point of no
return. Emitting `register: (12, 123)` would hand the patcher a global that does not exist. Deriving
the causal component per row is the next piece; until then the finding is reported without a remedy.

**What this leaves.** Column B goes 1 of 5 → 3 of 5 (cheese, snakeOil join smellingSalts).
`snakeLasso` now has a row for the RIGHT reason as well as its `fatal_uses` false positive — the FP
is still a FP and still needs the blame fix of §7u.2. `eveningGown` remains, and it is cause #3
(variadic `get:`), still blocked on debug-code exclusion.

### ⛔ §7w. CAUSE #2 DOES NOT CLOSE cheese/snakeOil — the "+2, validated" claim is WITHDRAWN

> ⛔ **SUPERSEDED BY §7y.** The measurement below is correct — building A+B+C alone changed nothing
> — but its conclusion ("the confinement is a disjunction and `register_strandings` walks scalars
> only, so the blocker is `{r for r, _ in back}`") stopped one step short: the fix for "walks
> scalars only" is to walk the joints, not to rewrite the scalar walk. Fourth instance of stating a
> diagnosis and then not testing the cheapest cure it implies.

Built A+B+C (below) and measured: `death_traps` now fires correctly on `rm350`/`rm500`, the joint
`(12, 123)` projection is created — **and LB2's full surface is byte-identical. No new findings.**

The reason, and it invalidates two earlier simulations including the reviewer's:

    death_traps rm350 = [ ({12: <every room but 420>}, ...),      <- ALTERNATIVE 1
                          ({123: {0,1,2,3,4,6}},      ...) ]      <- ALTERNATIVE 2

`_apply_death_traps` conjoins the negated death condition as a **DISJUNCTION** (`12 != 420 OR
123 != 5`) — correctly, because `NOT(a AND b)` is a disjunction. But `register_strandings` — the
detector that would catch cheese and snakeOil, and the one that already catches smellingSalts —
walks the **scalar** projections. In the scalar `123` projection alternative 1 carries no `123`
requirement at all, so it passes, and the player "leaves rm350 at act 5" freely. The confinement is
invisible to it.

**Both prior simulations got "+cheese +snakeOil" by OVER-restricting**: mine (SHAPE 1) cut the
entry edges outright, the reviewer's (SHAPE 2) applied only the `123` conjunct and dropped the `12`
alternative. Neither is what the model actually writes. *Simulate the CHANGE* — a third time.

`_trap_joints` builds the `(12, 123)` joint precisely for this, and it exists — but the two
consumers that matter do not use it: `register_strandings` iterates `self.regs` (scalars only), and
`reobtainable_rooms` collapses each projection to `{r for r, _ in back}`, so "reobtainable at act 3
but not at act 5" cannot be expressed. **That collapse is the standing limitation §7t's note
already flagged, and it is now the load-bearing blocker for column B.**

Open question for the next block: should `register_strandings` iterate `self.proj` (scalars +
joints) rather than `self.regs`? That is a real design change with corpus-wide blast radius, not a
patch. It is the honest next step and it should be measured before it is built.

### ⭐ §7v. EAVESDROPPING ADVANCES THE PLOT — waterGlass is IN SCOPE, and it is §7t's twin

USER, 2026-08-09: *"I don't know how out of scope it is, particularly if it advances acts. I don't
mind catching it."* Measured — **it does advance state**, so this is a merits call, not an
indulgence:

    Door.sc:20            listenVerb 0                      ; class default
    rm510/560/600/610     listenVerb 38                     ; = waterGlass (invCode `message 38`)
    Door.sc:98            (listenVerb (self listen:))       ; Property case label in a doVerb switch

    rm510::listen         advances global111:  0->1, 4->5, 10->11, 12->13
                          at 12 -> sListenToYvetteAndSteve -> (proc0_3 75)
    global111             WRITTEN by actBreak.sc:52 `(= global111 11)`, rm560, rm630, rm610,
                          triggerAndClock.sc; READ as a gate in rm510/rm550/rm560, often conjoined
                          with the act: `(and (== global123 3) (proc999_5 global111 4 5))`

`global111` is already a promoted register and is one of the three counters in the
counter-monotonicity census (with `global123` and KQ6's `162`). So listening is not dialogue
flavour: it drives a counter that gates room content.

**And the reason we never saw it is §7t's defect in a second place.** `(listenVerb (self listen:))`
is a **Property case label**, so `ir.control_shape` emits an UNGUARDED arm and the model believes
you can listen at those four doors *without the glass*. Same root as the nav labels.

⚠️ **BUT THE NAV-LABEL FIX DOES NOT FIX THIS ONE.** The switch lives in `Door::doVerb` — the CLASS,
where `listenVerb` is **0** — while the real value **38** is declared on the four INSTANCES that
override it. Resolving a Property label against the object that owns the method (what the §7t
lowering does, and what its `v in (0, 0xffff)` skip would reject here anyway) reads 0 and gives up.
Closing this needs class-method specialisation: *a Property label on a class method resolves to the
set of values the instances declare* (`{0, 38}`), which for a `param1` dispatch head becomes
OWN(waterGlass) on the 38 arm. That is a real extension, not a detail — scope it separately.

**Oracle consequence:** `waterGlass` moves OUT of §5 column D (out of scope) and into the ALLOWED
set. It is **not** thereby asserted to be a confirmed softlock — the user's words were "I don't mind
catching it" — so it should be allowed, not expected. See [[dont-flip-enumerated-ground-truth]]:
this is a user ruling, not a reclassification we made to flatter a change.

### ✅ §7x. …AND IT DOES **NOT** GATE AN ACT TRANSITION — the question that settles the column

USER, 2026-08-09, on reading §7v's "it advances the plot": *"if the waterGlass gates an act
transition then it's required."* Correct as a principle, and it is the right question, because
"advances a counter that gates room content" and "gates an act" are different claims and §7v only
established the first. **Measured against the source — it does not.**

    actBreak.sc:38-63   (switch global123 ...)          <- the act break reads global123 ALONE.
                                                           global111 appears NOWHERE in its guards.
    actBreak.sc:52      (= global111 11)                <- the act-3->4 arm OVERWRITES it, always
    triggerAndClock:45  (300 ... (= global111 15))      <- and the 3:00 clock tick forces 15
    rm520.sc:222        ((and (== global123 4) (global0 has: 31)) (= param1 26) ...)

The traffic runs the *other* way: the act break and the clock **erase** listening progress rather
than depend on it. `global111` has exactly one write outside listening-and-plot (`rm630:1151`) and
its readers — `rm510`, `rm550`, `rm560` — gate room content and NPC positions.

**The act-4→5 break is gated on `(global0 has: 31)` — the grapes**, which is already column A, read
out of rm520's own `newRoom`. That is what an act-gating item looks like in this game, and
`waterGlass` is not one. (The other five `newRoom: 26` sites — rm220, rm250, rm454, rm480, rm620 —
are cutscene-terminal states; only rm620's carries a condition, `proc0_10 8512`.)

**The one place listening touches MOVEMENT**, recorded because it is the strongest form of the
user's concern and it survives: `rm510.sc:123` `(if (proc999_5 global111 0 6 10 14) (eastDoor
locked: 1))` — `proc999_5` is OneOf (`System.sc:81`), and `eastDoor` is `entranceTo 550`,
`listenVerb 38`, unlocked by default. So not listening *does* lock rm510's east door in act 3. It
cannot strand: both forced writes above (11 and 15) land outside `{0,6,10,14}`, and the lock is
re-evaluated in `init`, i.e. on every entry.

**Verdict: ALLOWED, not EXPECTED** — the same column §7v landed on, now for a measured reason
instead of a deferred one. If the class-method specialisation of §7v is ever built and `waterGlass`
starts being flagged, that is a legitimate catch, not a false positive; but its absence is not a
gap and must not be filed as one.

### ✅ §7t RESOLVED (2026-08-09, later) — ONE root cause: the fix deletes ACT 4

**Diagnosed end to end by measurement. The nav-label fix is CORRECT; what it lands on is the one
write in LB2 that produces act 4, and a write the register model cannot ORDER it DROPS.**

    BEFORE  _rstep[123] = {26: [(0,1),(1,2),(2,3),(4,5),(5,6)], 355: [(0,0)],
                           630: [(0,4),(1,4),(2,4),(3,4),(4,4)]}
    AFTER   _rstep[123] = {26: [ ...unchanged... ],             355: [(0,0)]}   <- rm630 GONE
    act values reachable   [0,1,2,3,4,5,6]  ->  [0,1,2,3]
    rooms leaving proj 123  [521, 525, 750]   (all other 79 projections: 63 rooms, unchanged)

**The chain, each link measured:**

1. `rm630`'s `(= global123 4)` sits in the **else-arm** of a `(switch global12 …)` (§7s said so).
2. Resolving that switch's labels gives the else-arm priors `global12 != <each resolved case>`.
   The path condition is now RICHER but still says nothing about `global123`.
3. `_build_product` orders a register write **from its own path condition**. With a path condition
   that constrains a *different* register, the derived from-value set for 123 comes out EMPTY, so
   no step is emitted — and the write lands in neither `_rstep` nor `_inroom` (`_inroom[123]` is
   `{}` in both runs; last session's monotonicity pass drains it into `_rstep`). **The write is
   simply gone.**
4. `rm630` is the SOLE producer of act 4 — note `(3,4)` is absent from `rm26`'s steps, because the
   act-3→4 transition *is* that in-room write and not an act-break edge (§7s, already on record).
   So the act counter can no longer pass 3.
5. Acts 4/5/6 vanish, taking every room reachable only at act ≥ 4: **rm521, rm525, rm750**.
6. Two unrelated consumers then absorb it **silently**, which is why it looked like two bugs:
   * `_need_rooms` drops `750` → bifocals/redHair lose their only need room, wireCutters/daggerOfRa
     lose the one past the frontier. (`required[bifocals]` is still `[750]` — the raw map is
     untouched, so a `required` diff shows nothing.)
   * `reobtainable_rooms` INTERSECTS over every projection; projection 123 returns ∅ for anything
     sourced at `rm525`, so grapes and smellingSalts become "obtainable nowhere" — which reads
     downstream as "not strandable", not as "broken".
7. `edge_strandings` therefore emits nothing for `rm26->rm750`, and the five column-A rows plus
   smellingSalts disappear.

**THE DEFECT, stated generally:** *when a write's path condition constrains registers OTHER than
the one being written, `_build_product` must treat the from-value as UNKNOWN (→ `_inroom`, then
let the monotonicity pass forward-restrict it), not as EMPTY (→ drop the write).* Dropping is the
unsound direction and it is silent. Note the before-state `{(0,4),(1,4),(2,4),(3,4),(4,4)}` is
exactly the monotonicity pass's output shape `{(u,4) | u <= 4}` — so that write reached `_rstep`
*through* `_inroom`, and the lowering is what stopped it entering either.

Same room, same write, same root as cause #1 last session. `rm630`'s act write has now produced
two separate multi-session bugs; it deserves a pinned test of its own.

**Hypotheses killed on the way (do not re-run):**

| hypothesis | how it died |
|---|---|
| The goal/rooms become unreachable | `n_reach` 68, all four goals reachable, `edges26` identical |
| Sources are deleted by `_prev_impossible` | `sources` identical; disabling the function entirely changes nothing |
| Requirements are lost | `required`/`guard_required` byte-identical |
| The frontier edge stops being one-way | `edge_kind=['goto']`, `_freely_reversible(26,750)=False`, both runs |
| `rm750`'s ending selector sits in a `switch global12` | **rm750 has none.** `grep -l "switch global12"` matched `global126` — the true count is 37 files, not 45 |
| The five become a DISJUNCTIVE GROUP at rm750 | `disjunctive_groups()[750] == []` in both runs; all four rm750 machines have 0 entries |

**Method note.** The whole diagnosis ran WITHOUT editing `src/`: `_build` calls `I.load_ir`, so
patching that applies the lowering to the IR the model is built from, and `load(cache=False)`
returns before the pickle write, so the model cache is never poisoned. Four builds, ~6 min each.

### ⛔ §7t (ORIGINAL ENTRY, superseded by the resolution above) — the nav-label fix was reverted

`(switch global12 (north …))` compares the previous room against the room's **own `north`
property**, and `ir.control_shape` builds an `Eq` guard only for a `Number` label — a `Property`
label yields an **unguarded arm**. So LB2's act-5 deaths read as unconditional, `death_traps`
returned `None` for `rm500` and `rm350`, and the two ways out of the pursuit region stayed open.
That diagnosis is solid and still stands.

**The fix does not work.** `vocab.lower_property_case_labels` (resolve the label to the property's
literal value; skip 0/$ffff and any property the object assigns) was written, censused and
measured:

    census   LSL2 0 sites · KQ6 6, none resolvable · KQ4 7 · LB2 68, zero reassigned anywhere
    result   LB2 softlocks 9 -> 3.  LOST: wireCutters, daggerOfRa, bifocals, redHair, grapes
             (all COLUMN A, confirmed) and smellingSalts.

A drop is a regression, so it is reverted. **Why five confirmed findings vanish when the model gets
MORE precise is the interesting question, and it is unanswered** — that is a signal about the model,
not merely an obstacle. Guess-free starting point: the guards land on room `init` arms, so entry
writes and `init_seq` become conditional on arrival direction; something downstream is reading a
now-conditional write as absent rather than as possible.

⚠️ **And the probe that "confirmed" this fix was measuring the wrong thing.** It blocked TWO edges
in the act-5 product and showed cheese/snakeOil/eveningGown all strand. Resolving 68 case labels
across the game is not "block two edges". Simulate the CHANGE, not the consequence you want.

**What #3 needs, in order:** a derived notion of debug-only code. `whereTo` (script 29) has no
in-edges in the movement graph — it is entered by typing `-300` into a cab prompt, which is not a
modelled crossing — so the usable shape is *"an acquisition site in a room the movement graph
cannot reach, or in a proc called only from such a room, is not a source."* The proc half needs a
call graph; `trigger.reaching_procs` already computes one for the arming work and is the obvious
thing to reuse. Do NOT special-case `whereTo` by name.

> **#1's result, measured.** `_rstep[123][630]` became `{(0,4),(1,4),(2,4),(3,4),(4,4)}` and
> `[355]` became `{(0,0)}`; `_inroom[123]` is empty. smellingSalts is caught, no unexpected item
> is flagged, and the red narrows from 5 missed to 4.
>
> ⚠️ **And it did NOT work the way §7s predicted it would.** `reobtainable_rooms(13)` still
> returns 64 rooms including `rm420`, because that walk still collapses the product with
> `{r for r, _ in back}` — the item is caught by a different detector. So the collapse hypothesis
> I called refuted in §7s is *not* refuted; it was masked. Monotonicity was enough on its own
> here, and the collapse remains a real, separate limitation for anything that goes through
> `reobtainable_rooms`. Do not read §7s as clearing it.

### ⭐ §7u. THE SCOREBOARD WAS LYING, AND THE REMAINING ACT-5 WORK IS TWO EDGES (2026-08-09, later)

Re-measured from scratch at the uncommitted working tree. A single LB2 snapshot is **13 seconds**
warm — the 11-minute figure is the whole suite, and it has been making this game's iteration loop
look far more expensive than it is. Everything below is from `s` itself, not from these notes.

**1. Column B is honestly 1 of 5, not 2.** `test_lb2_ground_truth` scores by item NAME over the
union of eight detectors, so it cannot tell a right answer from a right-looking one. Per detector:

    analyze              pressPass wireCutters daggerOfRa bifocals redHair grapes   <- column A
    register_strandings  smellingSalts (525->720), grapes (525->750)                <- the real one
    dangerous_sinks      pressPass @rm240 (row emitted TWICE)
    fatal_uses           skeletonKey @rm630/sUnlockTrunk, snakeLasso @rm700/sExitRoom

**`snakeLasso` is not caught by the act-5 confinement.** Its row is a `fatal_uses` verdict about
the *mummy room*, a different room and a different mechanism, and it would survive a full revert of
the act work. Crediting it to "the death fixes" is true only in the sense that the death fixes
created the false positive.

**2. Both `fatal_uses` rows are avoidable deaths read as unavoidable — the fifth correction this
detector has needed.** Each machine really does end at `(newRoom: 99)`, and each really is armed by
the item blamed (the model maps `doVerb` param → item via the inventory item's **`message`
property** — `skeletonKey` is `message 18` and rm630's trunk case is `(18 …)`; `snakeLasso` is
`message 30` and rm700's snake is `(30 …)`. Do **not** grep for `has: N` to check an LB2
requirement, as an earlier reading of this document did — the use sites are verb-dispatched).
What is wrong is "cannot be survived":

| row | the escape the model cannot see |
|---|---|
| `skeletonKey@rm630/sUnlockTrunk` | state 6 does `(global1 handsOn:)` then `(= seconds 6/12)`. Hands are ON and the machine is waiting on real time, so the player can pre-empt it — `trunk doVerb 19` (meat, `message 19`) arms `sInsertMeat` on the same receiver, and `setScript:` cancels the running script. |
| `snakeLasso@rm700/sExitRoom` | state 1 branches on `(or (has: 35) (not (== (mummy cel:) 0)))`; the survival arm needs `mummy setCel: 0`, written by `sPutMummy`. Object-property state — modelling-gap census #3. |

Two consequences. The item blamed is the *entry* guard's, but the death is chosen by an **internal
branch** whose condition names a different item (35, the mummy) — blame belongs to the branch.
And the remedies these rows produce, `skeletonKey@rm630: (not (gEgo has: 8))` and
`snakeLasso@rm700: (not (gEgo has: 19))`, forbid required progress: Spinach_Dip class.

**3. The `skeletonKey` false positive is NOT the variadic `get:` gap.** `fatal_uses` never consults
`sources`; giving item 8 its `rm500` source changes nothing. §7 and the handoff both say cause #3
clears it. It does not — cause #2's blame fix does.

**4. ⭐ THE REMAINING ACT-5 HALF IS TWO EDGES, AND IT IS NOT CONTROL-MAP-CLASS WORK.** §8 item 4
asks whether act-conditioned exits are "worth it… bigger than everything in §7g". Simulated at the
product level — restricting the edge's own register requirement in `_emeta`, which is the same
structure the real fix writes, with no `src/` edit and therefore no cache invalidation:

    restrict rm420->rm350 and rm420->rm500 to `global123 != 5`
    NEW:  cheese (650->740), snakeOil (630->730)   ...and snakeLasso for the RIGHT reason (640->700)
    LOST: nothing.  Column A intact.

All of them arrive through **`register_strandings`, which already works** — it is what catches
smellingSalts and grapes today. `_apply_death_traps` already conjoins a survival condition onto
every way out of a room whose arrival kills you. So the only missing piece is letting `death_traps`
*see* rm350's and rm500's death arm, whose guard is the unresolved `(switch global12 (north …))`
case label. **The plumbing is built; one guard is unread.**

⚠️ First cut of this simulation cut *every* edge leaving `PursuitRgn`'s eleven rooms and lost
smellingSalts with nothing gained — `rm454->rm26` and `rm480->rm26` are the act **break**, so
cutting them removes act 6 and `rm750` with it. The confinement is the pursuit region **plus** the
tunnels (700/710/720/730/740, reached by `rm660->rm700`); only `rm420`'s two exits leave it.

**5. …and it also flags `waterGlass`, which §5 puts OUT OF SCOPE — so the run would fail "nothing
out of scope is flagged".** Not a model bug: `rm700` has a real `(38 …)` case (waterGlass is
`message 38`) arming `sListen`. So **§5 column D's stated reason is factually wrong** — "measured,
none has a downstream `has:` use site at all" missed the verb-dispatched sites. The *conclusion*
(eavesdropping is out of scope) still stands, but the model derives requirements from use sites and
LB2's out-of-scope mechanics **have** use sites. The 2026-07-26 items-only ruling is not expressible
in this model, and every increase in precision will drag another out-of-scope item in. **This is a
ruling question and it supersedes §8's five.**

**6. Two stale diagnoses still steering the work.** `test_lb2_ground_truth.py`'s RED detail still
says the gap "goes green when an act-gated `init:` on a door means THIS EDGE IS NOT THERE" —
refuted by §7q/§7r (zero such sites corpus-wide). `tools/run_tests.py`'s copy of the same rationale
was updated last session and the test's was not: [[same-rule-two-places]], and a red test
protecting a stale diagnosis ([[kq6-wedding-fuse-is-kq4-clock-class]]).

**Method that made this cheap, and is reusable:** build once (13 s), then mutate `s._emeta` in
memory to express the candidate change and re-run the detectors. It simulates *the edit*, not the
consequence you hope for — the failure §7t names — and it costs nothing, because the model cache
keys on `src/` hashes and this never touches `src/`.

### Refuted — do not re-run these

| claim | why it died |
|---|---|
| "Act-conditioned exits are a control-map-class project" | Two edges; simulated +cheese +snakeOil, 0 lost. §7u |
| "The `skeletonKey` FP is cleared by the variadic `get:` fix" | It is a `fatal_uses` row; that detector never reads `sources`. §7u |
| "The act counter is not in the model" | It is. §7a's own correction. |
| "Order the act counter and the boundaries become frontiers" | Ordered it; **zero** verdicts moved. §7h |
| "The acts gate LB2's doors via an act-gated `init:`" | **Zero** such sites corpus-wide. §7h's bullet, §7q |
| "Promote `global124` (the clock/achievement mask) and the five move" | All five acquisitions are unconditional. Census: 1 global in 5 games. §7l |
| "The item-location store is the gap" | Three `owner:` writes in the whole game, all one item. §7m |
| "The `{r for r, _ in back}` collapse is why smellingSalts is missed" | `rm420` is in `back` at **every** act; the cause is #1 above. §7s |

**Method rule, paid for four times over:** measure the prediction against `s.edges`/`s._emeta`
before building. A hand-rolled room graph disagreed with the model's in both directions (§7r).

### The working record

§7a–§7s below are the trail in the order it was measured, corrections included. Several are
superseded — where they disagree with the table above, **the table wins**. They are kept because
each refutation cost a measurement, and re-running one is more expensive than reading it.

---

## 7·0. The original measurement — 2026-08-06 at `7aa9a11` (tag `v2.1-kq6`)

Run: `python3 src/snapshot.py dagger`, plus three derivation probes. Model:
**78 rooms · 311 machines · 193 edges · 33 of 36 items with a source · 27 required.**
Start room 110 discovered; goals {340, 456, 521, 750} discovered.

    softlock items (6):  pressPass  wireCutters  daggerOfRa  bifocals  redHair  grapes
    groups, exhaustion, joint, tolls, fatal_uses, register_strandings:  all EMPTY
    dangerous:  pressPass@rm435 -> still needed at 250/300/335   (×2 rows)
    placements: 2 applied / 4 total

Against §5: **column A is 6 of 6. Column B is 0 of 5. Column C is 0 of 3 (correctly, if the source
reading holds).** Every ending item is caught and nothing safe is flagged, so the *false-positive*
side is clean; the miss is one whole class, and it has one cause.

> **UPDATE, later the same day: the act break is now modelled** (§7g). The diagnosis in §7a below
> was right and its fix landed; the item verdicts did **not** move, and finding out why turned up
> the real reason LB2 is hard — §7h. §7a–§7f are kept as the measurement they were, because the
> corrected numbers only make sense against them.

### 7a. THE CAUSE: the act-break write is orphaned from the act-break edge

> ⚠️ **CORRECTED the same day.** This section first said "the act counter is not in the model" and
> cited *"`(++ global123)` is dropped"* and *"0 of 193 edges carry the act"*. Both were wrong. The
> first read `opmodel`'s Increment handler without following `compile._fan_globals`; the second used
> `s.edge_demands()`, which is the ITEM view — the register view (`s._emeta`) carries an act
> requirement on **35 of 193** edges, including all five act-break destinations. The conclusion
> below (the acts do not separate) is unchanged; the cause is much narrower than advertised.

What is actually built, measured at this commit:

- `global123` **is** a promoted gating register (`123 in s.regs`), domain 0..6.
- `(++ global123)` **is** modelled: `compile._fan_globals` expands it into the six branches
  `123==k → 123:=k+1`, with the domain 0..5 derived from actBreak's own switch by
  `machine._glob_domains` — whose docstring names LB2's act break as the motivating case.
- **35 of 193** edges carry an act requirement, `rm26→{230,330,355,420,750}` among them, each
  demanding the act it belongs to.

And the one thing that is not:

**`_rstep[123]` is empty, and `_inroom[123][26]` is `{1,2,3,4,5,6}`.** The six fanned writes land as
*free values in room 26*, so standing on the act-break card you may set the act to anything and then
leave by whichever break edge matches. The ordering is dropped at one join.

The reason is `machine._send_op`, which resolves `newRoom:` only for a literal argument:

    if sel == "newRoom" and params:
        r = I.as_int(params[0])        # actBreak's `(newRoom: local0)` -> None
        if r is not None:
            out.append(Op("EXIT", g, r))

actBreak state 9 is `(++ global123)` **and** `(newRoom: local0)` in the same breath. A local
destination means the state emits `PARK`, not `EXIT` — and `edge_meta` lifts register writes only
off `EXIT` states. So the act write never reaches the edge that performs the act change.

`extract._var_room_values` already resolves this exact idiom, path condition included, and its
docstring uses LB2's act break as the worked example. It was wired into the flat-edge builder and
never into the machine lift: [[same-rule-two-places]] once more.

**The consequence.** Delete `rm26` from the room graph and ask what each act's entry room reaches:
acts 1, 2, 4 and 5 reach an **identical** 57-room set, and act 3 reaches those 57 **plus `rm355`
itself** (its own entry, which nothing else links into). Acts 1–5 are one undifferentiated blob.
Act 6 → 1 room, because rm750 is terminal — and that, not any understanding of LB2, is the whole
reason the ending items are caught.

A second, smaller ordering leak sits behind the same wall: `_build_product` derives `_rstep` from a
machine's **entry** guards only, so even a counter write that stays in-room (rm630's
`(= global123 4)`) loses its from-value and goes to `_inroom` permissively.

So the five we catch are not caught *because* we understand LB2. They are caught because act 6 is a
single terminal room and the break into it is an ordinary one-way edge. Every other boundary lands
inside the blob and is invisible.

### 7b. A second, smaller gap: the act-3 break destination is still dropped

`rm26`'s modelled out-edges are `{230, 330, 355, 420, 750}` — **510 and 610 are missing**, because
act 3's destination is `(= local0 (if (== global12 620) 610 else 510))`, an `If`-valued `newRoom:`.
Act 4's entry rooms are not reachable from the act break at all; they are only in the blob.

### 7c. ⚠️ The act-blindness does not just LOSE findings — it CORRUPTS the two guards we place

`placements: 2 applied` sounds like progress. Read the specs:

    rm440->rm435: (and (has: 0) (has: 1) (has: 3) (has: 4) (has: 5) (has: 6) (has: 9) (has: 10)
                       (has: 11) (has: 12) (has: 13) (has: 14) (has: 15) (has: 16) (has: 18)
                       (has: 19) (has: 23) (has: 26) (has: 27) (has: 28) (has: 29) (has: 31)
                       (has: 34) (has: 35) …)                      ; 24 items — and rm480 the same

That demands `coupon` (0) **and** `sandwich` (3) at once. `rm210` does `(global0 put: 0)` and then
`(global0 get: 3)` in the same handler: the coupon *buys* the sandwich. **The conjunction cannot be
satisfied in play, and it is `applied=True`.** The demand is that large because, with no act
dimension, the winning-region walk believes act-1 rooms are still ahead of you from `rm435`, so
every act-1 consumable joins "still needed".

`rm435` is not even a real frontier: it is the pterodactyl/skewer cutscene, entered from `rm440`
under `(== global123 3)`, and its own script does `newRoom: 430` on the way out. It is a *frontier*
only because it destroys the press pass (`dangerous_sinks`), and a *big* demand only because of the
act blindness.

**Consequence: LB2 must not be shipped as a patch in its current state.** The finding side is
sound; the guard side would wall the player.

### 7d. What is NOT broken

- The five ending items, their mechanism (`missing-prereq-before-gate`, `need_room 750`), and the
  frontier the detector names (`rm26->rm750`) are all still right.
- No false positives: the 8 examine-to-know items are correctly not required, and no confirmed-safe
  item is flagged.
- The surface is stable: `src/testdata/watched_surfaces.json`'s `dagger` block matches this run
  exactly, so nothing has drifted since it was frozen.

### 7e. The next steps this measurement implied — **superseded by §7g/§7h**

Kept because §7g is best read against what was predicted. The prediction was: model the increment,
exclude the debug door, carry the act on edges, and the boundaries become frontiers. The first
three are done (or measured to be unnecessary). **The last one is false**, and §7h says why.

### 7f. Resolving the "we used to flag 24" note (memory `lb2-oracle-and-item-only-scope`)

A 2026-07-29 note records *"Dagger now flags 24 items, and 9 of the 12 listed as missed are among
them: pressPass, waterGlass, dinoBone, snakeOil, cheese, snakeLasso, wire, workBoot,
smellingSalts."* Today the item list is 6. That looks like a regression of 18 verdicts, and it is
not one.

The 24-item guard conjunction on `rm440->rm435` (§7c) has **exactly 24 members**, and **all nine**
of the note's "caught carries" are among them. What was scored as 24 item verdicts was *one
over-broad demand* on a pseudo-frontier, counted item by item. The nine were never caught for the
reason that makes them real; they were swept in by the same act-blindness that makes the demand
unsatisfiable. The engine work since then stopped promoting that conjunction into item-level
verdicts — the guard spec itself is still emitted, which is why §7c is still true.

So: **a correction, not a regression.** What is *not* established is which commit changed it —
that would need a snapshot from a worktree at the old commit, and it has not been run. The
identity of the two lists is the evidence, and it is strong enough to retire the note.

### 7g. ✅ THE ACT BREAK IS NOW MODELLED (landed 2026-08-06, same day)

Three changes, each small, each general:

1. **`extract.var_room_values` is shared with the machine lift.** It resolved `newRoom: <var>` for
   the flat-edge builder and nowhere else, so a computed destination inside a `changeState` body
   read as PARK — and a state's register writes only ride an edge when the state EXITS. `Step.vexit`
   records the computed destination and `compile._fan_exit` expands it, one branch per room the
   variable can hold, each carrying the condition it was assigned under. Both consumers
   (`compile_machine`'s walk, `opmodel`'s state view) go through that one function, the same
   discipline `_fan_globals` already had.
2. **A register write is ordered from its own path condition.** `_build_product` derived `_rstep`
   from a machine's *entry* guards only; a write reached under `R == k` is executed only at `R == k`,
   which is the one thing that can order a counter. It needs `structural_reqs`, not
   `required_values`: the flat reading UNIONS equalities, so a fanned branch carrying both the
   counter's `123==3` and the destination's `123==2` came out as `{2,3}` and produced the full 6×6
   cross product of act steps.
3. **Contradictory cells of that cross product are dropped where it is formed** (`_contradicts`).
   30 of the 36 are impossible. Left in, `guard_reqs` reads them flat and turns `123==3 ∧ 123==2`
   into "crossable at either act" — worse than no ordering at all.

Measured after:

    rm26->230: req{0} sets{1}      rm26->420: req{4} sets{5}
    rm26->330: req{1} sets{2}      rm26->750: req{5} sets{6}
    rm26->355: req{2} sets{3}      (no k=3 row -- §7b, the `If`-valued destination, still dropped)

    _rstep[123][26] = {(0,1),(1,2),(2,3),(4,5),(5,6)}     _inroom[123][26] = {}   (was {1..6})
    edges carrying an act requirement: 41 (was 35)

That is actBreak's switch, exactly as the game writes it. rm26 is no longer a free act-setter.

**And §7c is fixed as a side effect.** The two `applied=True` guards that demanded 24 items —
`coupon` and `sandwich` among them, which the game cannot hold at once — are now
`rm440->rm435: (gEgo has: 6)` and the same for rm480. With the acts ordered, the winning-region
walk no longer believes the act-1 city is ahead of you at rm435, so the demand collapses to the one
item that crossing really costs. LSL2's golden stayed byte-identical and KQ4's and KQ6's watched
surfaces did not move; LB2's moved by exactly those two specs plus a `dangerous_sinks` witness room
(`pressPass@rm435` → `@rm240` — the row's verdict, item and `still_needed_at` are unchanged; the
detector takes the first room that condemns a site and breaks, so `at_room` is an arbitrary witness).

### 7h. ⚠️ AND THE VERDICTS DID NOT MOVE — the real reason LB2 is hard

Column B is still 0 of 5. The prediction in §7e — "then the blob splits and the boundaries become
frontiers" — is **wrong**, and the measurement says why:

    rm650 (Heimlich's office, where the cheese is) reachable at acts: 0 1 2 3 4 5
    rm740 (the tunnel rats, where it is needed)   reachable at acts: 0 1 2 3 4 5

Ordering the counter did not confine act 5, because **the act does not gate LB2's doors — it gates
what rooms PUT IN THEMSELVES.** `rm440` places the work boot under `(== global123 4)`; `rm430`'s
wire end inits under `(> global123 3)`; the cheese's own pickup carries no act test at all, and what
actually stops you fetching it during the chase is that the museum rooms do not initialise the
objects and exits that would let you walk there. A movement model can order the counter perfectly
and still not separate the acts, because the separation was never expressed as movement.

So the act has to enter through the *content*, and there are two halves:

- **Sources — half done, and it taught us something.** `build_maps` had every site's guard in hand
  and kept only the room (`sources[item] = {rooms}`). It now also keeps
  `source_guards[item][room] = [guard, …]`, and `reobtainable_rooms._source_live` seeds its backward
  walk only from states where some site can actually fire. This is `_prev_impossible`'s rule for a
  general register — that one answers the same question for the previous-room register and needs no
  product, this one does.

  **The first cut of it deleted an LSL2 softlock, and the reason is worth keeping.** LSL2's `Knife`
  has one site, in rm43, gated on `498 != 0`; the 498 projection reaches rm43 only at `498 == 0`.
  Read strictly, the Knife has no source at all — and a play-validated stranding vanished from the
  golden. **`sources` being condition-blind had been COMPENSATING for gaps in the register model**,
  and making it condition-aware turns every such gap into a lost finding, which is the wrong
  direction to be wrong in. The fix is a rule this codebase already states in another place
  ([[arming-floor]]): falling off the end of a walk is IGNORANCE, not evidence. So the filter only
  discriminates between states of a room it already believes in — if no reachable state at a source
  room satisfies any site, the room is kept whole.

  **Inert on LB2 either way**: the boot's `rm440` site does carry `123==4`, but its second source
  `rm720` is unconditional (§5, the respawn idiom), and cheese/snakeOil/snakeLasso/smellingSalts
  have no act test on their acquisition at all.
- **Exits — ⛔ REFUTED 2026-08-08, see §7j.** This bullet used to read: *"An exit that exists only in
  some acts is an act-gated `init:` on a door/Feature… until an uninitialised door means 'this edge
  is not there in this state', acts 1–5 stay mutually reachable."* Measured against the source, **no
  such site exists**: zero rooms gate an `ExitFeature`/`Door` init on `global123`, and zero condition
  a nav property on it. The acts do not gate LB2's exits in that shape or any other we can find.
  Nothing was built on this, which is the one piece of luck in it.

**The honest status: the act counter is modelled, and what the act CHANGES is not.** What §7g bought
is real — a correct act ordering, and the removal of two guards that would have walled the player —
but column B does not need exits. It needs §7j.

### 7j. ⭐ THE CLOCK — what actually moves LB2's world (measured 2026-08-08)

The act counter is the visible half of a story clock, and the clock is the thing that moves items
and people. **Script 22, `triggerAndClock`**, takes ONE packed word and does two jobs with it:

    (method (doit param1 param2)
        (if (& param1 $ff00)                            ; high byte present => a CLOCK TICK
            (= local0 (>> (& param1 $f000) $c))         ;   $f000 = hour
            (= local1 (>> (& param1 $0f00) $8))         ;   $0f00 = quarter
            (= local2 (+ (* local0 100) (* 15 local1))) ;   -> the new time
            (global2 setInset: clockInset …)            ;   the clock face animates
            (&= param1 $00ff))
        (+= global124 param1))                          ; low byte = achievement bits

So the answer to "is LB2 time, or time plus achievement?" is **both, fused in one call**: nothing
ticks on its own (unlike KQ4's real-time clock), the clock is advanced BY story events, and the same
call ORs progress bits into `global124`, which `actBreak` zeroes at every act break.

**12 static tick sites, 11 distinct times**, plus a dynamic one (`MuseumRgn` passes `global125`):

| site | word | time | | site | word | time |
|---|---|---|---|---|---|---|
| rm630 | `0x1310` | 1:45 | | rm400 | `0x7204` | 7:30 |
| rm420 | `0x2140` | 2:15 | | rm454 | `0x8120` | 8:15 |
| rm510 | `0x2301` | 2:45 | | rm355 | `0xa000` | 10:00 |
| rm500 | `0x3104` | 3:15 | | rm430, rm490 | `0xb102` | 11:15 |
| rm520 | `0x4108` | 4:15 | | rm560 | `0xc304` | 12:45 |
| rm335 | `0x7001` | 7:00 | | | | |

**And the same constants are READ BACK by `proc0_10` at about a hundred sites** — `-20222` tested
16×, `16648` 11×, `8512` 10×, `-15612` 9×, `4880` 8×, `-32480` 7×, `12548` 6×. "Has trigger T fired"
is therefore already a first-class predicate in LB2's own source, keyed by the very word that fires
it. That is the store we do not read.

⚠️ **But read `proc0_10` before believing the word "clock" here** — I did not, at first, and the
correction is the whole design:

    (procedure (proc0_10 param1 param2)
        (&= param1 $00ff)                                    ; <- the clock bits are DISCARDED
        (return (if (and (> argc 1) param2)
                    (== (- param1 1) (& global124 (- param1 1)))   ; every bit BELOW this one, i.e.
                                                                   ; "all prior steps are done"
                 else
                    (& global124 param1))))                        ; "this step is done"

So `proc0_10 -20222` does **not** ask "is it 11:15". It asks `global124 & $02`. The time is never
stored in any variable — it lives in script 22's `local2` for the length of one call. **There is no
clock variable to model.** What there is:

- **`global124`, an 8-bit achievement mask** (reset to 0 at each act break), written `(+= global124
  param1)` — addition, not `|=`, so the game is relying on each trigger firing exactly once.
- **the relocations, which are an immediate consequence of the tick site itself** — `clockInset`'s
  switch runs inline when that call happens, so `rm420`'s `doit: 8512` simply *is* the 2:15 moves.

That is a much smaller problem than a clock. It is: an interprocedural constant, feeding a mask
store we already have (the sixth store) and a location store we already have (`ownedBy`).

**What a tick writes** (`clockInset::dispose`, switching on the new time) is the two location stores:

    (1115  ((ScriptID 90 1) goTo: 440) ((ScriptID 90 2) goTo: 520) …)   ; characters relocate
    (215   (if (== ((global9 at: 14) owner:) 520)
               ((global9 at: 14) owner: 630)))                          ; AN ITEM relocates
    …plus (proc0_2 N) tests that `moveTo: -2` characters off-stage entirely

Item **14 is `snakeOil`**, and §5's table records its source as `rm630`: the clock is what put it
there, moving it out of `rm520` at 2:15. Ticks also chain — reaching 1:45 arms trigger `8224`
through `sShowClock`.

So the store to build is the CLOCK, and the store it writes is `ownedBy`, which we already have. No
control map, no new concepts.

### 7k. ⚠️ And §5's "why" column is now partly unverified

Chasing the cheese exposed that the per-item mechanisms in §5 were not all derived from source.
`rm600 → rm650` is a plain `LbDoor` with `entranceTo 650`, init'ed unconditionally; what locks it is
a **flag chain 81→82→83→84** driven by the listen-at-the-door verb — no act, no clock. `rm650`'s own
act/clock conditions gate a character and an intercom script, not the exits, and the rat trap is
`addToPic:`'d unconditionally. **So "but rm650 is act 3/4" is not established**, and the cheese's
real mechanism is unknown.

Before building anything for the five, re-derive each one's mechanism from source. One of them
(snakeOil) is plainly the clock; one of them (cheese) is plainly not what this document says. Do not
generalise from either until all five are read.

### 7l. ⛔ AND THE MASK STORE WOULD NOT MOVE THEM EITHER — two pre-implementation probes

The obvious next build after §7j is to promote `global124`: it is refused today only because
`vocab.derive_mask_globals` rejects a non-literal write, and here the literal is one call-frame
away. `tools/probe_mask_accessor.py` measures the shape corpus-wide:

    dagger  global124  reads 1  writes 1  payload-mask 0xff
                accessor Main:proc0_10 · accessor triggerAndClock:doit
    kq6 / qfgvga / lsl2 / kq4  -
    1 global across 5 games

Exactly one instance — the same profile the sixth store had (`g161`), and the same argument for it:
the accessors *declare their own payload mask* (`(&= param1 $00ff)`), so nothing is assumed, and the
relationship is the one `derive_flags`/`lower_flags` already has with the flag word-array, one level
down (per BIT of one word rather than per FLAG of an array).

**And it would not close column B.** The second probe asks the only question that matters: are the
five items' acquisitions gated by any of this?

    cheese         rm650   no store condition in the enclosing tests
    smellingSalts  rm525   no store condition
    snakeLasso     rm640   no store condition
    snakeOil       rm630   no store condition
    eveningGown            no `get:` site at all (as §5 already records)

**All five acquisitions are unconditional.** No act test, no `proc0_10`, no flag. So promoting
`global124` moves nothing here, exactly as ordering the act counter moved nothing in §7h. Two
mechanisations in a row would have been spent on stores these items never consult.

**What the evidence does point at.** If the acquisition is unconditional, missability cannot be
about *permission* — it has to be about the item not being THERE. And §7j caught the game doing
precisely that: `(global9 at: 14) owner: 630` moves snakeOil out of `rm520` at 2:15. We model
`ownedBy` as a fixed room per item.

⚠️ **AND THIS SECTION'S HEADLINE IS ITSELF TOO STRONG — corrected below.** "The mask store would not
move them" is true only of it as a *site guard*. See §7m: the guard is on the PLACEMENT, and
`global124` is exactly the state coordinate it is written in. I probed the wrong site.

### 7m. ⭐ THE GUARD IS ON THE PLACEMENT, NOT THE ACQUISITION — and the five are THREE mechanisms

The `get:` sites are unconditional because by the time you can click the item, it is already there.
The condition is on whether the game **put it there at all**, and that lives in the room's `init:`:

    ; rm640
    (if (not (proc0_2 4))
        (cond
            ((not (proc0_10 -20222))                       ; before the 11:15 trigger
                … (snakeLasso ignoreActors: 1 … init:))    ;   the lasso is on the floor
            ((not (proc0_10 4880))                         ; before 1:45
                … (if (not (global0 has: 19))
                      (snakeLasso … init:)))               ;   the respawn idiom, still gated
            …

So `source_guards` is the right home and `_source_live` already consumes the shape — but
`build_maps` collects the guard at the acquisition site, where there is nothing to collect. **It has
to come from the placement.**

**Censused across all five, because generalising from `rm640` is how the last two wrong turns
started** (`owner:` writes: *three in the whole game, all item 14*):

| item | mechanism | |
|---|---|---|
| snakeLasso | placement `init:` gated by `proc0_10 -20222` | ✅ found |
| snakeOil | `owner:` relocation `rm520`→`rm630` at the 2:15 tick | ✅ found |
| cheese (`rm650`) | **zero** clock/act-gated init sites; placement and acquisition both unconditional | ❌ unknown |
| smellingSalts (`rm525`) | same — zero | ❌ unknown |
| eveningGown | no `get:` site at all; the source end is unmodelled too | ❌ unknown |

**There is no single fix for the five.** Any design that claims to close all five from one mechanism
is overfitting — which is the whole reason this table exists.

### 7n. THE DESIGN, AND WHY IT IS NOT A NEW STORE [user, 2026-08-08]

> *"it just feels like item source should be a product, rather than there being a new store"*

Right, and the consumer is already built. `sources[item]` is a flat `{rooms}`;
`source_guards[item][room]` already holds a condition per site; `_source_live` already filters a
`(room, register-state)` node by it; `reobtainable_rooms` already intersects over `self.proj`. Source
is half a product already. The missing half is that an item's **location is treated as a constant**
rather than as a function of state.

So: no new store. `ownedBy` exists, and `global124` is a register once the parameterised accessor of
§7l is lowered. The change is that `sources[item]` becomes `{(room, condition)}`, fed by the
PLACEMENT guard (§7m) and by `owner:` writes, and `_source_live` consumes it unchanged.

Expect **2 of 5**. cheese, smellingSalts and eveningGown are not explained by any of this and must
be diagnosed before anything is built for them.

⚠️ **The permissiveness rule is not optional.** Making `sources` condition-aware is exactly what
deleted LSL2's `Knife` (§7h): `sources` had been silently compensating for gaps in the register
model, and a play-validated stranding vanished. [[arming-floor]]'s rule governs — falling off the end
of a walk is IGNORANCE, not evidence — so a state we cannot decide must KEEP the source.

### 7o. ✅ eveningGown DIAGNOSED — `get:` is VARIADIC and we read one argument

User ground truth, 2026-08-08: *"you get the gown at the dry cleaner in the first act/prologue
before going into the museum, and it's never available again."* The dry cleaner is `rm270`
(Lo Fat's), and the acquisition is there — we simply never read it:

    rm270.sc:274   (global0 get: -1 32)

`ego_19`'s override says what `-1` is, and it is not an item:

    (method (get param1)
        (if (== param1 -1)
            (super get: &rest)                    ; -1 = acquire SILENTLY; the items follow
        else
            (super get: param1 &rest)
            (global91 say: 2 4 0 0 0 19)))        ; …otherwise also speak the pickup line

So the item number is the SECOND argument, and `get:` is **variadic** —
`(ego get: -1 25 16 17 30 27 26 12 31 13)` acquires nine items in one statement. Our extractor takes
the first literal and records item **-1**.

**Census: 13 two-argument sites against 33 one-argument ones — 28% of LB2's acquisitions lost**,
across items 1, 2, 6, 8, 20, 21, 22, 25, 28, 32, 34. This is a plain extractor gap, not a modelling
one, and it is the exact sibling of the `put:` gap the previous session fixed via
`patcher.ego_spellings` (`(ego put: 6 0 1 3 4 5 8 9 18 23 32)` — same variadic shape, same receiver
spelling, other direction).

⚠️ **AND THE NAIVE FIX LOSES FINDINGS.** The richest variadic `get:` sites are in `Main`'s
`proc0_13`…`proc0_17` — the **debug act-setup procs**, reached only from `whereTo`, the debug
jump-to-act room. `proc0_16` alone hands over `25 16 17 30 27 26 12 31 13`, which includes **cheese
(16) and smellingSalts (13)**. Read those as sources and both items become obtainable from anywhere
and their strandings vanish. Same hazard as the LSL2 `Knife`, from the opposite direction: a phantom
source is as destructive as a missing one. **The fix must exclude debug-only code.**

### 7p. ❌ cheese and smellingSalts are still NOT diagnosed

Both were chased to the end and neither yielded a gate:

- **cheese** — `rm650`'s trap is `addToPic:`'d unconditionally, `(global0 get: 16)` carries no
  condition, and entry via `rm600`'s `northDoor` is a flag chain (81→82→83→84) driven by the
  listen-at-the-door verb, which is a puzzle you can complete at any time, not a seal.
- **smellingSalts** — `feBody init:` sits in `rm525`'s `localproc_0` unconditionally, `(global0
  get: 13)` carries no condition, and `rm525` is entered from `rm520` alone.

So for both, missability can only be that the source ROOM stops being reachable in act 5 — and the
model denies it. **✅ RESOLVED in §7q.**

### 7q. ⭐ ACT 5 IS A TIMED CHASE, AND ITS WALLS ARE DEATHS ON ENTRY

User, 2026-08-08: *"act 5 is a timed chase, you have to do everything in the right order quickly and
I don't think you can go back and get the items."* Correct, and the code says it in three pieces.

**1. Act 5 begins at `rm420`.** `actBreak` switches on the act you are LEAVING:
`0→230, 1→330, 2→355, 3→610|510, 4→420, 5→750`. The act-4 break fires from `rm520`.

**2. The chase is a REGION, which is why the room graph never showed it.** Script 94:

    (class PursuitRgn of Rgn
        (method (newRoom param1)
            (= keep (proc999_5 param1 420 430 435 440 448 450 454 460 480 490 660))
            (if (not keep) (pursuitTimer dispose: delete:))))

Eleven rooms, named as a literal list. `pursuitTimer` is a real-time `Timer` whose `cue` calls
`(global2 notify:)`, and `rm420::notify` runs `sDie` when `global123 == 5`. `rm420` arms it on entry
(`oRileyTimer setTicks: 300`) and re-arms it on every departure
(`(ScriptID 94 1) setReal: … local0`, 35–85 ticks by `global87`, doubled without a mouse).

**3. The walls are DEATHS ON ENTRY, conditioned on the direction you came from.** `rm420`'s only
exits out of the region are `north 350` and `west 500`, and in act 5 both kill you:

    ; rm500 and rm350, identically
    (switch global12
        (north
            …
            (if (== global123 5)
                … (self setScript: sLauraDies))))      ; -> (global2 newRoom: 99)

So act 5 IS the eleven-room pursuit region. `rm650` (cheese), `rm525` (smellingSalts), `rm640`
(snakeLasso) and `rm630` (snakeOil) are all statically connected to `rm420` — measured, they are —
but every path out is a death.

**And this needs NO new store.** The condition is a conjunction of two registers we already model:

- `global123 == 5` — the act, modelled since §7g;
- `global12 == north` — the previous room, the same register as KQ6's realm seal
  ([[prevroom-is-the-realm-seal]]).

…plus the standing rule that a death not preventable from its own screen is in scope
([[one-rule-death-is-in-scope]]). The rule to state is general: **an edge whose DESTINATION arms a
death on entry, under a condition on (previous room, register state), is not an edge in those
states.** No clock, no control map, no act-gated doors — three directions this document proposed and
all three wrong.

The chase timer is then FLAVOUR for our purposes: it is what makes the confinement urgent in play,
but the confinement itself is the two deadly exits, and those are static.

### 7r. THE PREDICTION, MEASURED — 3 of 4, and it exposed two more causes

The prediction was: *cutting those two edges in act-5 states strands cheese, smellingSalts,
snakeLasso and snakeOil; the variadic `get:` fix closes eveningGown; column B goes 5 of 5.*
Measured before building, in the model's own `(room, global123)` product walked from `(rm420, 5)`,
using `s.edges` and `s._emeta` — **not** a hand-rolled graph, which is what caught the errors:

| item | before the cut | after the cut |
|---|---|---|
| cheese | reachable | **stranded** ✅ |
| snakeLasso | reachable | **stranded** ✅ |
| snakeOil | reachable | **stranded** ✅ |
| smellingSalts | **already stranded** | stranded ⚠️ |
| eveningGown | reachable | **still reachable** ❌ |

(54 rooms reachable while still in act 5 before, 39 after.)

**Two corrections to §7q, both mine:**

1. **`rm525` is ALREADY unreachable at act 5** in the product, before any cut. So the deadly exits are
   not why smellingSalts is missed — the topology already says it is stranded and the oracle still
   does not flag it. That is a THIRD cause, unidentified: something on the "still needed" side, or a
   second source room, is keeping it alive. Do not credit the cut with this one.
2. **`rm270` stays reachable at act 5**, so §7q's *"eveningGown is closed by the `get:` fix alone"*
   is **wrong**. That claim rested on a regex room-graph I built by hand, which disagrees with the
   model's — the model has edges mine did not. Only 31 of 193 edges carry an act requirement, so the
   walk strolls back into the prologue. eveningGown needs the source fix AND the prologue→museum
   crossing modelled as one-way; the second half is a separate gap.

**What the measurement does support:** the deadly-entry rule is worth building, and it closes THREE
of the five (cheese, snakeLasso, snakeOil). It is not the whole of column B, and §7q should not be
read as if it were.

**Method note, for the next person.** The hand-rolled graph and the model's graph disagreed in both
directions — mine said `rm270` unreachable (it is not) and reached 36 rooms where the model reaches
60. A convenient approximation is not a measurement. Walk `s.edges`/`s._emeta`.

### 7s. ✅ smellingSalts DIAGNOSED — THE ACT CAN RUN BACKWARDS

User ground truth, 2026-08-08: *"the smelling salts are obtained in Olympia's office right before
act 5, and then they are used in act 5 to revive someone."* The model agrees on both ends:

    sources[13]       = [525]          # Olympia's office
    required[13]      = [720]          # the tunnels, where Steve is revived
    edge 520 -> 525   requires {579: {1}, 123: {4}}     # act 4 only -- the model KNOWS this

…and still does not flag it, because `reobtainable_rooms(13)` returns 64 rooms including every
act-5 room. The reason is not the source condition and not the room graph:

    _rstep[123]  = {26: {(0,1), (1,2), (2,3), (4,5), (5,6)}}    # ordered -- and (3,4) is ABSENT
    _inroom[123] = {rm355: [0],  rm630: [4]}                    # settable from ANY act

**The act register can DECREASE.** Standing in `rm630` at act 5, the model may set the act back to
**4**, walk `rm520 → rm525` and collect the salts; `rm355` can reset it to **0** outright. This is
§7a's "second, smaller ordering leak" — `_build_product` derives `_rstep` from a machine's ENTRY
guards only, so an in-room write loses its from-value — and it is now measured to be the whole
reason this item is missed. It is also why `(3,4)` is missing from `_rstep`: the act-3→4 transition
IS `rm630`'s in-room write, not an act-break edge.

**The from-value is not recoverable locally.** Both writes sit in the `else` arm of a
`(switch global12 …)` on the arrival direction, with no act test anywhere near them. So no path
condition supplies it.

**The rule that does, derived from `_rstep` itself:** every ordered step of this register is
`k → k+1`. **A register whose ordered steps are all monotone increasing may not be DECREASED by an
in-room write.** That is read off the model's own step relation, asserts nothing about LB2, and is
inert on any register that genuinely moves both ways. It kills both leaks at once: `rm630`'s write
to 4 cannot apply at act 5, and `rm355`'s to 0 cannot apply above act 0.

⚠️ **This partly corrects §7r.** That table called smellingSalts "already stranded before the cut",
from a forward walk of mine that filtered to states with `act == 5`. The model's own backward walk
does not filter, and it is right not to: the player really can end up at act 4 again *if* the
backwards jump is real. It is not. So smellingSalts is a **monotonicity** finding, not a topology
one, and the two fixes are independent.

### 7i. PLACEMENT: 3 of 4, and the fourth is a design gap

Chasing the `every non-refused spec places` red the same day:

- ✅ **The press-pass sink places.** Two causes, both the seam that red already names — the patcher
  re-finding a site by text. The pattern was `\(global0\s+put:\s*6\s*0?\)`; LB2's `Main` spells the
  receiver `(ego put: …)`, and the line carries nine trailing arguments (`(ego put: 6 0 1 3 4 5 8 9
  18 23 32)`) that the engine ignores because `Ego::put` reads exactly two. `patcher.ego_spellings`
  now derives the receiver names from the game's own `(= global0 ego)` rather than assuming `globalN`.
- ✅ **A variable-valued `newRoom:` is findable.** `analyze_room` knew literals and the nav-property
  idiom; the third shape was missing, which is why the act break reported "no controllable trigger"
  while the analysis knew the edge perfectly well.
- ⛔ **…and finding it revealed that placing it would HANG the game.** The emitted guard was
  `(if (or (== global400 2) (and (has: 10) … (has: 31))) (self setScript: sBreakIt))` — which gates
  *every* act break, so the five inquest items would be needed to leave act 1, and which leaves rm26
  with nothing running when refused. **Read out of the emitted source, not inferred.** Script 26
  contains exactly one `newRoom:` and it is inside the cutscene being declined.

  So an arm-event is now refused as `sole-exit` when no `newRoom` site lives outside the script it
  gates. That is what separates it from the arm-events that are safe — KQ4's whale, KQ6's rm440 and
  rm480 — where the room keeps its ordinary exits. **The red stays red, with a true reason instead
  of a false one.**

**What the fourth needs**: a DEFERRAL. `apply_guards` already falls back from an uncontrollable
frontier to "the nearest EARLIER commit that is both controllable and still lets the player comply"
— but only for prohibitions. A demand needs the same treatment, and for LB2 the answer is the last
controllable crossing of act 5, not the act break itself.

---

## 8. OPEN — needs a user ruling

1. ✅ **RULED 2026-08-10 — the three contested rows are SAFE, pending the §9 play test.** The
   source checks (column-C table) found all three re-obtainable at the point of use with the
   game's own act-5 chase handling, and the user ruled: *"let's mark those safe, but let's
   remember to put them in a play test plan later."* Applied: rows moved to `SAFE_RULED` in the
   oracle test, where flagging one is now a false positive; the play-test obligation is §9. The
   user's stated suspicion — the walkthroughs hoard these early **because the act-5 chase is very
   tight** — is the exact claim the play test exists to check.
2. ✅ **RULED 2026-08-09 — deaths ARE in scope, when unavoidable given earlier state.** User:
   *"this is analogous to the other games… yes they're in scope, if they're unavoidable given
   earlier state (the snake oil). The chase and looking both ways are not in scope."* The
   items-only ruling was about the EVIDENCE layer and never covered deaths, so LB2 is not an
   exception to the one rule: **preventable from its own screen ⇒ out**. IN: the act-5 cobras with
   an empty bottle. OUT: every chase step (a wrong step, but the right one was available where you
   stood) and act 1's look-both-ways. Not to be confused with LSL2's parked "dangerous ACTIONS"
   class, which that oracle files as *hazards*, a separate report class — still parked.
3. ✅ **RULED 2026-08-09 — the snake-oil arithmetic is NOT needed.** User: *"you should have enough
   snake oil left before entering act 5 to not die because of it in act 5."* So the requirement is
   the boundary condition, not the spend count: entering act 5 with `global150 == 0` is a
   stranding, and the refill is mandatory rather than prudent. §5a's undelivered quantity stops
   being a blocker.
4. ⛔ **WITHDRAWN — the question was built on a refuted premise.** It asked whether act-conditioned
   exits were worth a control-map-class effort. There are ZERO act-gated door inits corpus-wide
   (§7q/§7r), so the work it proposed does not exist; and the actual remaining act-5 piece was two
   edges, closed in §7y by walking the joint projections. Nothing to rule on.
5. ✅ **RULED 2026-08-10 — eveningGown is an act gate, not a softlock.** User: *"evening gown:
   act 2 gate, not a softlock."* Applied in full: the row left column B (now EMPTY — the four real
   carries were promoted to column A), the item moved to `NEVER_STRANDABLE` in the oracle test,
   and the KNOWN_RED check *"the act-boundary carries are caught"* was **promoted and deleted**
   per the run_tests contract. The mechanism that earned the ruling stays pinned green (the
   wearingGown gate + its gown-priced writer, §7ab).
6. **`reobtainable_rooms._source_live` is inert on LB2** (§7h). It is correct, general, and the
   register form of a rule the codebase already applies to the previous-room register — but on
   today's corpus it changes nothing, so it is groundwork for item 4 rather than a result. Keep it
   or revert it; either is defensible and it should be a decision, not a leftover.

## 9. PLAY-TEST PLAN (recorded 2026-08-10, not yet run)

The 2026-08-10 rulings rest on SOURCE readings; the user asked that these be play-verified later
(*"let's remember to put them in a play test plan later"*). Per the standing method rules: play is
the LAST resort, no console-SET state (reads fine, writes are not evidence), stream progress.

1. **The trio under the chase clock.** For each of workBoot / wire / dinoBone: reach act 5
   WITHOUT the item (skip it in its usual act), then attempt the re-acquisition at the point of
   use during the chase — boot at rm720 (take, then use on Steve), wire at rm430 (use wireCutters
   on the wire, then wire the east door), bone at rm480 (take it mid-chase if any act-5 use needs
   it — note rm500's bone use self-limits to acts ≤4, so the act-5 leg may be vacuous for the
   bone; check whether anything in act 5 demands it at all). The user's suspicion to test: *"the
   act 5 chase is very tight"* — i.e. the source-level availability may not survive the clock.
   If any re-acquisition is not realistically completable, the row moves BACK from SAFE_RULED
   with the user's sign-off, and the walkthroughs were right for the right reason.
2. **The empty-bottle boundary** (§5a): enter act 5 with `global150 == 0` (spend all four shakes
   in act 4 — legitimate play, no console writes) and confirm the cobra nest is impassable, i.e.
   the stranding the 2026-08-09 ruling names. Also confirm the refill really is unavailable in
   act 5 (the vat at rm610, `cel < 3`).
3. While in the file: the standing LB2 items not play-verified — the guard placements do NOT ship
   (§7i), so nothing to verify there yet.

Related: [[one-rule-death-is-in-scope]], [[dont-flip-enumerated-ground-truth]],
[[kq6-softlock-ground-truth]], `docs/KQ6-SOFTLOCK-CANDIDATES.md`, `src/test_lb2_ground_truth.py`.
