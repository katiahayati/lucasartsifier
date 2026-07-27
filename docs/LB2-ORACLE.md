# Laura Bow 2: The Dagger of Amon Ra — validation oracle

Our third SCI1.1 game and the first with an **act structure**. Built 2026-07-26 from four
walkthroughs plus the game's own script, in that order of authority: **the game source wins**, then
Sierra's official hint file, then the walkthroughs, then me.

Sources:
- Sierra BBS official hints (via `groups.google.com/g/comp.sys.ibm.pc.games/c/hh-Q5Cf72A4`)
- `the-spoiler.com/ADVENTURE/Sierra/dagger.of.amon.ra.2.html`
- `sierrahelp.com/Walkthroughs/LauraBow2Walkthrough.html`
- `walkthroughking.com/text/daggerofamonra.aspx` (thin — no evidence list)
- our decompilation, `build/sweep/dagger/src`

---

## 1. THE ACT STRUCTURE (source-verified)

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

So `global123` is the act counter, 0..6, incremented **only here**. (One reset, `(= global123 0)`
at `rm355.sc:209`, lives inside `sIllegal` — not the main path.) Thirty-plus sites test it;
`rm440` alone has 26. Act 6 is the inquest, `rm750`.

**This is the softlock engine of the game.** The counter only goes up, rooms condition access on
it, so anything left behind when an act ends is gone. Sierra's own hint file says it plainly: it is
easy to *"head into a new Act without some vital item."*

| act | title | starts in | rooms |
|---|---|---|---|
| 1 | A Nose for News | rm230 | the city — newspaper office, docks, laundry, speakeasy (210–295) |
| 2 | Suspects on Parade | rm330 | the museum fundraiser (300–370, 400) |
| 3 | On the Cutting Edge | rm355 | the museum, open investigation (400–660) — the longest act |
| 4 | Museum of the Dead | rm510 / rm610 | the museum, being hunted |
| 5 | Rex Takes a Bite out of Crime | rm420 | the chase and the tunnel |
| 6 | The Coroner's Inquest | rm750 | one room, questions only |

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

| # | item | act | source | use | verdict |
|---|---|---|---|---|---|
| 0 | coupon | 1 | drunk's newspaper, outside the police station | buy the sandwich | act-local |
| 1 | claimTicket | 1 | trash in the dirty taxi | give to Lo Fat → gown | act-local |
| 2 | notebook | 0 | Laura's, from the start | pick cab destinations; hieroglyph riddles in act 5 | carried |
| 3 | sandwich | 1 | from the coupon | give to the desk sergeant → password | act-local |
| 4 | baseball | 1 | trash can, newspaper office | trade to the street boys → magnifier | act-local |
| 5 | deskKey | 1 | under the desk blotter | opens the drawer → press pass | act-local |
| 6 | pressPass | 1 | desk drawer | cabbie (or ejected), guard, Heimlich at the door | **spans acts 1→2** |
| 7 | pocketWatch | 3 | steamer trunk, Mammalogy Lab | shown to the Countess | inquest list (walkthrough only) |
| 8 | skeletonKey | 3 | glued behind the Bosch painting | opens the steamer trunk | act-local |
| 9 | meat | 3 | icebox, Mammalogy Lab | **throw into the trunk before opening** — beetles kill you otherwise | act-local, death |
| 10 | **wireCutters** | 3 | Ernie's toolbox | cut the pterodactyl wire; pry the key | **ENDING ITEM (source)** |
| 11 | **daggerOfRa** | 3 | Vat 13, with the lasso | the murder weapon | **ENDING ITEM (source)** |
| 12 | workBoot | 3 | Armor Room, by the dog armor | give to Steve in act 5 **before he stands** | **spans 3→5** |
| 13 | smellingSalts | 4 | the Countess's pocket | revive Steve in act 5 | **spans 4→5** |
| 14 | snakeOil | 3 | Preservation Lab table | the snake (4), the cobra nest (5) | **spans 3→5** |
| 15 | lantern | 5 | downstairs hallway | light the tunnel | act-local |
| 16 | cheese | 3 | rat trap in Heimlich's office (needs dinoBone) | distract the rats in the tunnel | **spans 3→5** |
| 17 | garter | 3 | poetry book, Heimlich's shelf | — | inquest list (walkthrough only) |
| 18 | dinoBone | 3 | T-Rex room | spring the trap; break the mirror; break the statue (4) | **spans 3→4** |
| 19 | snakeLasso | 3 | Ernie's toolbox | vat 13; the snake (4); the mummy-case hook (5) | **spans 3→5** |
| 20 | ankhMedallion | 2 | Egyptian exhibit | identifies Tut Smith | inquest list (walkthrough only) |
| 21 | pippin_sPad | 2 | the body in the sarcophagus | **the hieroglyphs that answer the act-5 riddles** | **spans 2→5** |
| 22 | magnifier | 1 | the street boys, for the baseball | required to see most evidence, all game | **spans 1→4** |
| 23 | lightBulb | 3 | Yvette's lamp (let it cool) | the stairway → the spiral staircase | act-local |
| 24 | watney_sFile | 3 | *Crime and Punishment*, Carrington's shelf | identifies the impostor | inquest list (walkthrough only) |
| 25 | warthogHairs | 3 | Ernie's body, Mastodon Room | — | inquest list (walkthrough only) |
| 26 | **bifocals** | 3/4 | the corpse inside the broken statue | — | **ENDING ITEM (source)** |
| 27 | **redHair** | 4 | Yvette's office | — | **ENDING ITEM (source)** |
| 28 | waterGlass | 2 | the buffet table | eavesdrop at doors in acts 3 and 4 | **spans 2→4** |
| 29 | carbonPaper | 3 | Yvette's wastebasket | hold to the lamp to read it | inquest list (walkthrough only) |
| 30 | yvette_sShoe | 4 | Yvette's office | — | inquest list (walkthrough only) |
| 31 | **grapes** | 4 | the floor by the Countess's body | — | **ENDING ITEM (source)** |
| 32 | eveningGown | 1 | Lo Fat's laundry, with the ticket | worn to the fundraiser | **spans 1→2** |
| 33 | charcoal | 3 | the fireplace | rub on the notepad | act-local |
| 34 | wire | 3 | clipped from the pterodactyl (needs wireCutters) | wire the door shut in act 5 | **spans 3→5** |
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
- act 5: the riddles — **"womb"**, then **"tomb"**, read from Pippin's notepad.

**Pure evidence-examination** (magnifier on the daggers, the medallion, the red puddle, the diary,
the watch, the Mastodon body). Sierra's hints: *"you need to see pretty much everything to
progress."* These set flags; they are how the 8 non-`has:` conviction items do their work.

---

## 5. WHAT WE CURRENTLY FIND

At `a6e4c1c`+ (after `newRoom: <local>` resolution, task #11), pointed at Dagger:

    rooms 78 · machines 304 · items with a source 34/36 · required 22
    softlock candidates (5): wireCutters, daggerOfRa, bifocals, redHair, grapes

**Those are exactly the five items `rm750`'s ending selector tests — all five, and nothing else.**
Found without any walkthrough, from the scripts alone. That is the strongest single validation the
SCI1.1 machinery has had on a game it was not built against.

Before the fix the same run produced one item (`pressPass`) and called the act-break card a winning
terminal.

### …and the mechanism is the right one (verified, not assumed)

    pattern        missing-prereq-before-gate
    need_room      750                      <- the has: chain in sAfterQuestions
    source_rooms   640 / 620 / 500 / 525    <- acts 3 and 4, all behind the boundary
    frontier_edges ["rm26->rm750"]          <- THE ACT BREAK

The frontier the detector names is the act-break edge itself — the one task #11 restored. Not a
coincidental true positive. The other eight conviction items are correctly **not** required, which
matches the source: they are never `has:`-checked.

### ⚠️ But this is the ACT-6 boundary only — 5 of a larger set

`rm26 -> rm750` is a frontier because rm750 is terminal. The other four act breaks land inside the
mega-SCC, so **boundaries 1→2, 2→3, 3→4, 4→5 are still invisible** and every item carried across
one is a stranding we do not yet report. From §3, the predicted list — the validation target for
tasks #12/#13:

| item | obtained | needed | consequence of arriving without it |
|---|---|---|---|
| pressPass | 1 | 2 | no entry to the fundraiser |
| eveningGown | 1 | 2 | ditto |
| magnifier | 1 | 2–4 | most evidence is invisible |
| waterGlass | 2 | 3–4 | cannot eavesdrop at doors |
| pippin_sPad | 2 | **5** | cannot answer the sphinx riddles |
| dinoBone | 3 | 4 | cannot break the statue → no bifocals |
| snakeOil | 3 | **5** | the cobra nest is impassable |
| cheese | 3 | **5** | the rats are impassable |
| snakeLasso | 3 | **5** | cannot reach the mummy-case hook |
| wire | 3 | **5** | cannot wire the door shut |
| workBoot | 3 | **5** | Steve is injured |
| smellingSalts | 4 | **5** | Steve cannot be revived |

The act-5 six are the sharpest: act 5 is a linear chase with no way back to the museum, so entering
it short of any one of them is a hard stop.

### Known gaps against this oracle
- Act 3's break destination is `(if (== global12 620) 610 else 510)` — an `If`-valued `newRoom:`,
  still dropped. 20 more `If` sites in Dagger.
- The act counter never advances: `(++ global123)` is an increment on a GLOBAL, and all four
  Increment handlers are gated on `is_local_or_temp` (task #13).
- No edge carries the act as a guard yet (task #12), so the act break is a free hub between acts.
- The 8 examine-to-know items are invisible: their requirement runs through dialogue flags, not
  `has:`.
- 2 of 36 items have no source.

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
- The twelve cross-act carry items in §5 are **in scope** and currently missed.

Related: [[one-rule-death-is-in-scope]], [[dont-flip-enumerated-ground-truth]],
[[kq6-softlock-ground-truth]], `docs/KQ6-SOFTLOCK-CANDIDATES.md`.
