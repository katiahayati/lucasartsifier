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

**B — REAL, AND WE MISS IT** (the act-boundary carries; §7 says why)

| item | obtained | needed | consequence of arriving without it | evidence |
|---|---|---|---|---|
| snakeOil | act 3 `rm630` | acts 4, **5** | cobra nest impassable; empty bottle is *destroyed* (§5a) | source + Sierra hints + LP |
| cheese | act 3 `rm650` (`(not (has: 16))` respawn — but `rm650` is act 3/4) | **5** | the rats are impassable | source + all walkthroughs |
| snakeLasso | act 3 `rm640` (respawns in `rm640`) | **5** | cannot reach the mummy-case hook | source + all walkthroughs |
| smellingSalts | act 4 `rm525` (respawns in `rm525`) | **5** | Steve cannot be revived | source + all walkthroughs |
| eveningGown | act 1, Lo Fat's | 2 | no entry to the fundraiser | walkthroughs; **no `get:` site extracted**, so the source end is unmodelled too |

**C — CONTESTED: the source contradicts the walkthroughs. NEEDS A USER RULING (§8)**

| item | walkthroughs say | the source says |
|---|---|---|
| workBoot | miss it in act 4 → unwinnable (LP part 12) | `rm720` (the act-5 room that uses it) re-places it under `(not (has: 12))` with a working `sGetBoot` |
| wire | clip it in act 3 or the act-5 door cannot be wired | `rm430`'s `wireEnd` inits under `(or (> global123 3) …)` and `(not flag44)`, and `sGetThatWire` has an explicit `(== global123 5)` branch — so it is cuttable *in act 5* |
| dinoBone | act 3 only; needed act 4 to break the statue | `rm480:79` `(if (not (global0 has: 18)) (bone init: stopUpd:))` — no act test on that line. Whether `rm480` is reachable in act 4 is **unresolved** and needs the act partition |

**D — OUT OF SCOPE BY THE 2026-07-26 RULING** (their absence from `s.required` is correct)

- The 8 examine-to-know conviction items: pocketWatch, garter, ankhMedallion, watney_sFile,
  warthogHairs, carbonPaper, yvette_sShoe, and the notebook's evidence pages.
- **magnifier**, **pippin_sPad**, **waterGlass** — reclassified out of column B on 2026-08-06.
  All three were listed as missed carries in the old §5; measured, **none of them has a downstream
  `has:` use site at all**. magnifier's need runs through evidence examination, pippin_sPad's
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

## 7. WHERE WE ARE — MEASURED 2026-08-06 at `7aa9a11` (tag `v2.1-kq6`)

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
- **Exits — not started, and this is the real work.** An exit that exists only in some acts is an
  act-gated `init:` on a door/Feature, not an act test on a `newRoom:`. Until an uninitialised door
  means "this edge is not there in this state", acts 1–5 stay mutually reachable and no act boundary
  can be a frontier. This is the same class as modelling-gap census #1 (the control map), and it is
  a bigger piece than everything in §7g put together.

**The honest status: the act counter is modelled and the act STRUCTURE is not.** What §7g bought is
real — a correct act ordering, and the removal of two guards that would have walled the player — but
column B needs the exits.

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

1. **The three CONTESTED rows (§5 column C).** The source says workBoot and wire are obtainable in
   the act that uses them, contradicting the walkthroughs and the Let's Play. Our own authority
   order says the source wins, which would move them to column E (safe) — but they are in the
   twelve-item list this project has been carrying since 2026-07-26, and
   [[dont-flip-enumerated-ground-truth]] says report and ask rather than reclassify. **Asking.**
   dinoBone is genuinely unresolved and needs the act partition either way.
2. **Deaths in LB2.** The standing rule is that deaths are in scope; the 2026-07-26 LB2 ruling was
   about the *evidence* layer and did not speak to them. LB2's act-5 chase is ten or so forced
   deaths (§4). Do we gate on them for this game, or hold the line at items?
3. **The snake-oil quantity (§5a).** The mechanism is source-verified; the arithmetic that decides
   whether the refill is *mandatory* is not derived yet. Worth deriving, or enough to guard the
   `global150 == 0` sink unconditionally?
4. **Act-conditioned exits — is it worth it?** (New, from §7h.) It is the only route to column B,
   and it is a control-map-class piece of work: an act-gated `init:` on a door has to mean the edge
   is absent in that state. Bigger than everything in §7g. The alternative is to accept that LB2
   detects its act-6 boundary and stop there. Worth knowing before anyone starts.
5. **`reobtainable_rooms._source_live` is inert on LB2** (§7h). It is correct, general, and the
   register form of a rule the codebase already applies to the previous-room register — but on
   today's corpus it changes nothing, so it is groundwork for item 4 rather than a result. Keep it
   or revert it; either is defensible and it should be a decision, not a leftover.

Related: [[one-rule-death-is-in-scope]], [[dont-flip-enumerated-ground-truth]],
[[kq6-softlock-ground-truth]], `docs/KQ6-SOFTLOCK-CANDIDATES.md`, `src/test_lb2_ground_truth.py`.
