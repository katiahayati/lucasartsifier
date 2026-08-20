# KQ5 patched-game test plan — everything up to Mordack's island

Game: `~/sierra/patched/kq5` · Console: **Ctrl+Alt+D**, type lines, `exit`.
`C:` = console lines. **After `exit`, move the mouse OFF the icon bar** (the bar pauses the room).
`put N R` **no-ops unless you hold N** — always `get N` first. **Save before every one-way**
(kidnap, sled, roc, sail). Don't teleport straight into rooms 33, 35, 36, 42, 55–67, 86 — they
switch on where you came from; walk in from a neighbor.

## Items (alphabetical — `send ego get N`)

| item | # | item | # | item | # |
|---|---|---|---|---|---|
| Amulet | 27 | Golden Needle | 3 | Pie | 2 |
| Bag of Peas | 24 | Hairpin | 36 | Pouch | 13 |
| Beeswax | 18 | Hammer | 22 | Rain Spell | 40 |
| Brass Bottle | 6 | Harp | 10 | Rope | 20 |
| Bunny Spell | 39 | Heart | 9 | Shell | 23 |
| Cat Fish | 37 | Honeycomb | 17 | Shoe | 8 |
| Cloak | 26 | Iron Bar | 30 | Sled | 29 |
| Coin (silver) | 4 | Key | 1 | Spinning Wheel | 15 |
| Crystal | 21 | Leg of Lamb | 19 | Staff | 7 |
| Elf Shoes | 33 | Locket | 25 | Stick | 16 |
| Emeralds | 14 | Marionette | 12 | Tambourine | 34 |
| Fish | 5 | Moldy Cheese | 32 | Tiger Spell | 41 |
| Fishhook | 31 | Mongoose Spell | 38 | Wand (Crispin's) | 28 |
| Gold Coin | 11 | Mordack's Wand | 35 | | |

**Flags** (read `vmvars g N`; write `vmvars g N <value>`): 15 = cloak WORN (g129 & $8000) ·
16 = has eaten (g130 & $0001; `vmvars g 130 1` fakes it) · 62 = cat took fish (g132 & $4000) ·
63 = henchman pea'd (g132 & $8000) · 96 = hole-rescue state (g135 & $0001)

Legend: ✅ = verified (harness or your play) · ☐ = still needs your hands.

## A — Town & market
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | A1 | toymaker (204) | pay Gold Coin (11) / Needle (3) / Heart (9) | **refused** ("Better not…") for all three |
| ✅ | A2 | bakery (206) | pay Gold Coin (11) / Needle (3) / Heart (9) | **refused** for all three |
| ✅ | A3 | tailor (203) | pay Heart (9) | **refused**; Gold Coin (11) buys the cloak (**works**) |
| ✅ | A4 | gypsy rm13 | pay Needle (3) | **works** (amulet 27) — never guarded |
| ✅ | A5 | girl rm9 | give Heart (9) | **works** (harp 10) — never guarded |
| ✅ | A6 | anywhere | EAT the Pie (2) | joke plays, **pie kept** (retraction) |
| ✅ | A7a | anywhere (town confirmed!) | EAT the Lamb (19), first bite | **works** (+4, becomes the half leg; hunger flag persists to the mountains) |
| ✅ | A7b | anywhere | EAT the Lamb (19) again | joke plays, **the half SURVIVES** (retraction — the eagle still gets fed) |

## B — Cat & dog scenes
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | B1 | rm6 | offer Fish (5) during the chase | **refused**; fish kept |
| ✅ | B2 | rm6 | offer Lamb (19) | **refused** |
| ✅ | B3 | rm6 | throw Shoe (8) / Stick (16) | works, **+4 exactly once** |
| ✅ | B4 | rm6 | lose the race → leave → re-enter with 8 or 16 | chase **re-arms** (window held open) |
| ✅ | B5 | rm6 | win (mouse saved) → leave → re-enter | chase **never replays** |
| ✅ | B6 | rm12 dog | offer Lamb (19) | **refused**; Shoe (8)/Stick (16) work (stock) |
| ✅ | B7 | rm11 bear | use Fish (5) on bear | **works** (stock — the point of B1) |

## C — Kidnap & cellar
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | C1 | inn rm85 | approach the north zone without Hammer (22) + a banked throwable | "Not yet!" **once**, walk-back, controls return |
| ✅ | C2 | rm85 | with Hammer (`get 22`) + cat won (or `get 8` + `put 8 6`) | **kidnapped normally**; cellar plays stock (Hammer 22 on door, get Rope 20, mouse frees you) |

## D — Desert temple (rm18)
| ✓ | # | Do | Expect |
|---|---|---|---|
| ✅ | D1 | inside via Staff (7), leave Brass Bottle (6) + Gold Coin (11) on the floor, walk the exit strip | **refused** + walk-back, control returns. The door timer is STOCK (USER ruling): dawdle too long and it entombs you — a death, preventable on your own screen, deliberately left in |
| ✅ | D2 | pick both up, walk the exit | leaves normally |

## E — Mountains, below the sled
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | E0 | rm2 | Tambourine (34) on the snake | flag 47 set, road opens (the flag-engine fix, play-confirmed) |
| ✅ | E1 | rm30 | use Cloak (26) on Graham | worn (flag 15, +4 once); the cold stops threatening |
| ✅ | E2 | rm30 | use Rope (20) on the branch | **refused** ("Better not…"); rope kept |
| ✅ | E3 | rm32 | never eat, walk east past x≈105 | **stock hungerDeath** (left in: preventable on-screen — eat the lamb) |

## S — The sled commit (rm32 → rm33): the mountains' point of no return ⬅ THE PRIORITY
| ✓ | # | Do | Expect |
|---|---|---|---|
| ✅ | S1 | missing any of Pie (2) / Harp (10) / Beeswax (18) / Hammer (22) / Lamb (19): **use the Sled (29) on the slope** | **"Not yet!"** — ride refused, sled kept (both click paths carry the guard) |
| ✅ | S2 | same state, walk east instead | turned back at the edge, same demand |
| ✅ | S3 | full carries (`get 2 10 18 22 19`, eat the lamb once) — ride | sled breaks, lands rm33 (stock); walking back up stays blocked (stock terrain) |

## F — Above the sled
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | F1 | rm34 eagle | offer Pie (2) | **refused** (the pie is the yeti's) |
| ✅ | F2 | rm34 | feed Lamb (19; half is fine) | **works** (stock — the intended move) |
| ✅ | F3 | rm36 yeti | Pie (2) NOT thrown, walk west | **STOCK** (USER ruling): the yeti catches you at rm35 — his chase's staged catch, a declinable race (feed, or duck north), deliberately unguarded. The pie's protections live at the sled carry, the EAT retraction, and the eagle refusal |
| ✅ | F4 | rm36 | throw Pie (2) at yeti, walk west | crosses to rm35 normally (pure stock now — our 36.SCR is retired, Sierra's own is restored) |
| ✅ | F5 | rm38 | Hammer (22) on the crystal | pried (Crystal 21), +4 (stock; bare hands fail harmlessly) |

## R — The roc edge & the nest ✅ harness-verified — spot-checks only
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | R1 | rm40 | winning state (Crystal 21 held, eagle fed via `get 19` + `put 19 34`, no lamb in hand), walk the top strip (~148,144 — cliff room, walk carefully) | **carried off by the roc** |
| ✅ | R2 | rm40 | missing the Crystal (21) | "Not yet!" + walk-back **and control returns** (re-check: the old ✅ predates the control-return lesson) |
| ✅ | R3 | rm40 | Crystal (21) held but eagle NOT fed (Lamb 19 in hand) | **turned back** — the nest would kill you |
| ✅ | R4 | rm42 nest | wait 30s+ | eggs do **not** crack until the Locket (25) is taken |
| ✅ | R5 | rm42 | take the Locket (25) | eggs crack → chicks → eagle rescue → rm43, Cedric greets |

## H — Coast, hermit, the sail (the last gate before Mordack's island)
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | H0 | harpy island rm49, first visit, missing Shell (23) or Fishhook (31) | click the boat to sail off / walk south or west into the sea edge | **"Not yet!"** — boat click refused (control returns); walked edge turns back with the line (⛔ 2026-08-19b play-found: the island is ONE SAFE VISIT — the departure writes flag 54, the return patrol kills with the harp spent; USER ruling: guard the depart, never the return) |
| ✅ | H0b | 〃 with both (shell picked up, nest fishhook via `get 31` there) | sail off | **departs, stock** — and any LATER departure (flag 54 up) is never re-demanded |
| ✅ | H0c | return visit to rm49 (flag 54 up) | land, wander | **stock, unguarded** — the 50% harpy patrol may kill you; Caveat-Player BY RULING ("if we can guard the depart we should not guard the return") |
| ✅ | H1 | rm90 / rm44 | get Fishhook (31) / Iron Bar (30) | stock |
| ✅ | H2b | rm46 hermit | click Shell (23) on the hermit, missing Iron Bar (30) or Fishhook (31) | **"Not yet!"** — the give refuses, shell kept, heal deferred (USER ruling 2026-08-19: the whole cutscene chain must not start; ⛔ the first two builds hung at rm660 / deferred the commitment via flag 105) |
| ✅ | H2c | coast rm44/45/46, flag 105 CLEAR (pre-hermit) | sail around, items missing | **stock** — the boat click passes (`(or (not flag105) items)`). ✅ VERIFIED BY PLAY 2026-08-19c: the whole H0-H3 run island-hopped through this guard with flag 105 clear |
| ◐ | H2d | coast, flag 105 SET, items missing | board the boat | **no auto-sail** + **"Not yet!"** on the click. ⚠️ UNREACHABLE BY PLAY in the current build (flag 105 rises only inside the equipped give chain — cartoon2 st18 / goGetBoat); defense-in-depth for stale saves. Repro if desired: load the 2026-08-19 post-give fishhook-less save (the mermaid-tow one) and board — expect refusal instead of the tow |
| ✅ | H3 | rm46 hermit | give Shell with both (`get 30`, `get 31`) | **full stock chain**: heal, farewell, mermaid ride to Mordack's (ONE-WAY — save first) |
| ✅ | H4 | hermit rm46/660-663 | all other hermit scenes | stock, un-walled |

## M — Mordack's island & castle (the endgame — PLAY THROUGH, no mid-state teleports)
The island's shipped guards are M2's pair; everything past them is stock. The three open
verdicts (P1/P2/L3) are woven in where they occur.
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | M1 | rm51 beach | get the Cat Fish (37) | stock (the walkthroughs' "pick up the fish before the stairs" — with our guards, skipping it is refused rather than fatal) |
| ✅ | M2 | rm54 (the stairs/grate room), WITHOUT the Cat Fish (37) | click the grate; linger where the henchman patrols | grate click: **"Not yet!"**, control returns; the beach henchman **never arms** (silent gate — walk back down for the fish). Inside the castle he stays STOCK (see Z) |
| ◐ | M3 | rm54 with 37 | grate, or let the henchman grab you | both **stock** — either way into the castle. ◐ GRATE ✅ (2026-08-19c); ⏰ REMINDER: the henchman-grab entry with the fish still untried — needs a pre-grate save |
| ☐ | M4 | castle halls | cat appears | ✅ GUARD SHIPPED 2026-08-19c (was the ⛔ play-found remote-fuse death, USER-ruled whale shape): the cat **does not spawn** until `flag63 ∧ own(24) ∧ (flag62 ∨ own(37))` — beast pea'd, bag re-taken, and fish in hand (or already thrown). One wrap on proc550_16 in 550.SCR, installed + boot-verified. **TO TEST**: (a) pre-beast / bagless / fishless halls → NO cat, play open; (b) full kit → cat appears, fish→cat then bag→cat works stock; (c) after the fish throw the cat run + fuse are STOCK — catch it at the next encounter (Caveat-Player race, by ruling). Detection red promoted same session (oracle §23) |
| ✅ | M5 = P2 | the blue beast | ONE pea-bag (24) throw when he closes in | ✅ VERDICT IN (USER play + source 2026-08-19c): one throw is the whole mechanism — the script WAITS for the approach phase (global333==3) then atomically sets flag 63, flips the bag's cel to empty, and **DROPS THE BAG ON THE FLOOR — pick it back up**. P2 CLOSED structurally: spend and flag are one state, a flagless spend cannot occur |
| ☐ | M6 | captured by the castle henchman → dungeon rm67 | give the Locket (25) — carried by construction (R4/R5's hold) — when Cassima comes | **rescue** (stock; without the give it's the timer death — that fork is the detection's row 11) |
| ✅ | M6b = L3 | get captured a SECOND time after one rescue | — | ✅ **VERDICT L3 ANSWERED 2026-08-19d, USER play-confirmed** (*"if he catches you a second time you die"*, "got that without even trying"): death REGARDLESS of the Locket. Source agrees and says why — rm067.sc:342-343 sets flags 69 **and 96 together at the rescue**, so 96 = "Cassima has already spent her rescue", not "you were captured before". ⛔ GUARD OWED (red declared, oracle §24): the capture must not ARM unless `(¬96 ∧ owner(25)==57) ∨ (own 24 ∧ ¬bag-empty)` |
| ☐ | M6c | after the guard ships: pre-give halls; then post-rescue with peas; then post-pea | linger where he patrols | (a) **no ambush** until Cassima has the locket (closes the capture-before-give death); (b) with the full bag he comes as normal → pea him; (c) **no ambush after the pea** — this also retires a STOCK death (rm58/rm60 re-init a frozen henchman whose empty bag cannot answer, oracle §24) |
| ☐ | M7 | rm67 mouse hole | use the Fishhook (31) | **Moldy Cheese (32)** — the fishhook chain's payoff (why the harpy-island toll exists) |
| ☐ | M8 = P1 | the cat, fish thrown | use the (now empty) Bag (24) on the cat | **the catch** — the handler demands flag 63 ∧ flag 62 (a pre-throw bag gets message 50, a no-fish cat gets the 550-14 flavor; neither wastes anything). P1's mechanism is source-confirmed; this row just watches it play |
| ☐ | M9 | machine room → endgame | cheese (32) into the machine; the wand swap; the spell battle; victory | **stock, play through** — report anything that hangs, walls, or eats an item it shouldn't |

## V — Open verdicts (answers change what I build next)
| # | Question | How |
|---|---|---|
| P1 | ✅ RESOLVED 2026-08-19c (USER play + source): ONE beast-throw sets flag 63 = "the bag is empty"; the cat catch demands 63 ∧ 62. M8 watches it play | — |
| P2 | ✅ CLOSED 2026-08-19c structurally: the spend and flag 63 are one atomic changeState state (theThrowPeasScript st2) — a flagless spend cannot occur; nothing to build | — |
| L3 | is a 2nd henchman capture (after one hole rescue) death regardless of the Locket (25)? | M6b: get caught twice; flag 96 is the tell |

## Z — Must-stay-stock spot checks
Snake at rm2 still demands the Tambourine (34) ✅ · witch forest still needs the worn Amulet (27) ·
in-castle henchman (rooms 58–61) unchanged even after the Fish (5) is spent on the cat ·
Cedric-reappears-after-rm32-capture is a **stock bug**, expected, out of scope.
