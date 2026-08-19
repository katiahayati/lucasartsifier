# KQ5 patched-game test plan — everything up to Mordack's island

Game: `~/sierra/patched/kq5` · Console: **Ctrl+Alt+D**, type lines, `exit`.
`C:` = console lines. **After `exit`, move the mouse OFF the icon bar** (the bar pauses the room).
`put N R` **no-ops unless you hold N** — always `get N` first. **Save before every one-way**
(kidnap, sled, roc, sail). Don't teleport straight into rooms 33, 35, 36, 42, 55–67, 86 — they
switch on where you came from; walk in from a neighbor.

**Items:** 2 Pie · 3 Needle · 5 Fish · 6 Bottle · 8 Shoe · 9 Heart · 10 Harp · 11 Coin ·
16 Stick · 18 Beeswax · 19 Lamb · 20 Rope · 21 Crystal · 22 Hammer · 24 Peas · 25 Locket ·
26 Cloak · 29 Sled · 30 IronBar · 31 Fishhook · 37 CatFish

**Flags** (read `vmvars g N`; write `vmvars g N <value>`): 15 = cloak WORN (g129 & $8000) ·
16 = has eaten (g130 & $0001; `vmvars g 130 1` fakes it) · 62 = cat took fish (g132 & $4000) ·
63 = henchman pea'd (g132 & $8000) · 96 = hole-rescue state (g135 & $0001)

Legend: ✅ = already verified under the harness (spot-check only) · ☐ = needs your hands.

## A — Town & market
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | A1 | toymaker (204) | pay Coin / Needle / Heart | **refused** ("Better not…") for all three |
| ☐ | A2 | bakery (206) | pay Coin / Needle / Heart | **refused** for all three |
| ☐ | A3 | tailor (203) | pay Heart | **refused**; Coin buys the cloak (**works**) |
| ☐ | A4 | gypsy rm13 | pay Needle | **works** (amulet) — never guarded |
| ☐ | A5 | girl rm9 | give Heart | **works** (harp) — never guarded |
| ☐ | A6 | anywhere | EAT the pie | joke plays, **pie kept** (retraction) |
| ☐ | A7 | anywhere | EAT the lamb **twice** | 1st bite: **works** (+4, becomes the half leg); 2nd bite: joke plays, **the half SURVIVES** (retraction — the eagle still gets fed) |

## B — Cat & dog scenes
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | B1 | rm6 | offer **Fish** during the chase | **refused**; fish kept |
| ☐ | B2 | rm6 | offer **Lamb** | **refused** |
| ☐ | B3 | rm6 | throw Shoe/Stick | works, **+4 exactly once** |
| ☐ | B4 | rm6 | lose the race → leave → re-enter with a throwable | chase **re-arms** (window held open) |
| ☐ | B5 | rm6 | win (mouse saved) → leave → re-enter | chase **never replays** |
| ☐ | B6 | rm12 dog | offer Lamb | **refused**; Shoe/Stick work (stock) |
| ☐ | B7 | rm11 bear | use Fish on bear | **works** (stock — the point of B1) |

## C — Kidnap & cellar
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | C1 | inn rm85 | approach the north zone without Hammer + a banked throwable | "Not yet!" **once**, walk-back, controls return |
| ☐ | C2 | rm85 | with Hammer (`get 22`) + cat won (or `get 8` + `put 8 6`) | **kidnapped normally**; cellar plays stock (hammer on door, get Rope, mouse frees you) |

## D — Desert temple (rm18)
| ✓ | # | Do | Expect |
|---|---|---|---|
| ☐ | D1 | inside via Staff, leave Bottle/Coin on the floor, walk the exit strip | **refused** + walk-back to the entrance, no message spam |
| ☐ | D2 | pick both up, walk the exit | leaves normally |

## E — Mountains, below the sled
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | E1 | rm30 | use Cloak on Graham | worn (flag 15, +4 once); the cold stops threatening |
| ☐ | E2 | rm30 | use Rope on the branch | **refused** ("Better not…"); rope kept |
| ☐ | E3 | rm32 | never eat, walk east past x≈105 | **stock hungerDeath** (left in: preventable on-screen — eat the lamb) |

## S — The sled commit (rm32 → rm33): the mountains' point of no return ⬅ THE PRIORITY
| ✓ | # | Do | Expect |
|---|---|---|---|
| ☐ | S1 | missing any of Pie 2 / Harp 10 / Beeswax 18 / Hammer 22 / Lamb 19: **use the Sled (29) on the slope** | **"Not yet!"** — ride refused, sled kept (both click paths carry the guard) |
| ☐ | S2 | same state, walk east instead | turned back at the edge, same demand |
| ☐ | S3 | full carries (`get 2 10 18 22 19`, eat the lamb once) — ride | sled breaks, lands rm33 (stock); walking back up stays blocked (stock terrain) |

## F — Above the sled
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | F1 | rm34 eagle | offer Pie | **refused** (the pie is the yeti's) |
| ☐ | F2 | rm34 | feed Lamb (half is fine) | **works** (stock — the intended move) |
| ☐ | F3 | rm36 yeti | pie NOT thrown, walk west | "Not yet!" once + walk-back; **north stays free**; chase still escapable |
| ☐ | F4 | rm36 | throw Pie at yeti, walk west | crosses to rm35 normally |
| ☐ | F5 | rm38 | Hammer on the crystal | pried, +4 (stock; bare hands fail harmlessly) |

## R — The roc edge & the nest ✅ harness-verified — spot-checks only
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ✅ | R1 | rm40 | winning state (Crystal held, eagle fed, no lamb in hand), walk the top strip (~148,144 — cliff room, walk carefully) | **carried off by the roc** |
| ✅ | R2 | rm40 | missing the Crystal | "Not yet!" + walk-back |
| ☐ | R3 | rm40 | Crystal held but eagle NOT fed (lamb in hand) | **turned back** — the nest would kill you |
| ✅ | R4 | rm42 nest | wait 30s+ | eggs do **not** crack until the Locket is taken |
| ✅ | R5 | rm42 | take the Locket | eggs crack → chicks → eagle rescue → rm43, Cedric greets |

## H — Coast, hermit, the sail (the last gate before Mordack's island)
| ✓ | # | Where | Do | Expect |
|---|---|---|---|---|
| ☐ | H1 | rm90 / rm44 | get Fishhook / IronBar | stock |
| ☐ | H2 | coast rm44/45/46 | sail on toward Mordack's, missing Bar or Hook | **refused** (the departure doesn't start / "Not yet!") |
| ☐ | H3 | 〃 | with both (`get 30`, `get 31`) | **departs** (ONE-WAY — save first) |
| ☐ | H4 | hermit rm46/660 | hermit scenes (shell heals Cedric etc.) | stock, un-walled |

## V — Open verdicts (answers change what I build next)
| # | Question | How |
|---|---|---|
| P1 | does the empty pea bag still bag the cat? | castle: 4 pea throws at the henchman, then fish + empty bag on the cat |
| P2 | does a far-miss pea throw spend a pea without setting flag 63? | throw from across the room; check g132 & $8000 |
| L3 | is a 2nd henchman capture (after one hole rescue) death regardless of the locket? | get caught twice; flag 96 is the tell |

## Z — Must-stay-stock spot checks
Snake at rm2 still demands the tambourine · witch forest still needs the worn Amulet ·
in-castle henchman (rooms 58–61) unchanged even after the fish is spent on the cat ·
Cedric-reappears-after-rm32-capture is a **stock bug**, expected, out of scope.
