# KQ5 patched-game test plan — everything up to Mordack's island

Game: `~/sierra/patched/kq5` · Console: **Ctrl+Alt+D**, type lines, `exit`.
`C:` below = console lines. **After `exit`, move the mouse OFF the icon bar** (bar pauses the room).
`put N R` **no-ops unless you hold N** — always `get N` first. **Save before every one-way** (kidnap, roc, sail).
Teleport-sensitive rooms (init switches on where you came from): 35, 36, 42, 55–67, 86 — walk in from a neighbor instead of `room`-ing straight in.

**Items:** 2 Pie · 3 Needle · 5 Fish · 6 Bottle · 8 Shoe · 9 Heart · 10 Harp · 11 Coin · 16 Stick · 18 Beeswax · 19 Lamb · 20 Rope · 21 Crystal · 22 Hammer · 24 Peas · 25 Locket · 30 IronBar · 31 Fishhook · 34 Tambourine · 37 CatFish
**Flags** (read `vmvars g N`): 62=g132&$4000 (cat took fish) · 63=g132&$8000 (henchman pea'd) · 69=g133&$20 (Cassima with you) · 96=g135&$0001 (hole rescue used?)

## A — Town & market
| # | Where | Setup | Do | Expect |
|---|---|---|---|---|
| A1 | toymaker 204 | C: `send ego get 11` | pay Coin | **refused** "Better not…" |
| A2 | bakery 206 | (Coin held) | pay Coin | **refused** |
| A3 | toymaker+bakery | C: `send ego get 3` | pay Needle | **refused** at both |
| A4 | tailor 203 + both shops | C: `send ego get 9` | pay Heart | **refused** at all three |
| A5 | gypsy rm13 | Needle held | pay Needle | **works** (amulet) — never guarded |
| A6 | tailor | Coin held | buy cloak with Coin | **works** |
| A7 | girl rm9 | Heart held | give Heart | **works** (harp) — never guarded |
| A8 | anywhere | C: `send ego get 2` | EAT the pie | joke plays, **pie kept** (retraction) |
| A9 | anywhere | C: `send ego get 19` | EAT the lamb **twice** | 1st bite: **works** (+4, becomes the half leg — the mountain hunger needs it); 2nd bite: **refused** (the half is the eagle's) |

## B — Cat & dog scenes
| # | Where | Setup | Do | Expect |
|---|---|---|---|---|
| B1 | rm6 | hold Shoe or Stick, walk in | offer **Fish** during chase | **refused** "Better not…"; fish kept |
| B2 | rm6 | 〃 | offer **Lamb** | **refused** |
| B3 | rm6 | 〃 | throw Shoe/Stick | works, **+4 once** |
| B4 | rm6 | lose the race, leave, re-enter w/ throwable | — | chase **re-arms** (window held open) |
| B5 | rm6 | win (mouse saved), leave, re-enter | — | chase **never replays**, score not doubled |
| B6 | rm12 dog | hold Lamb | offer Lamb | **refused** |
| B7 | rm12 | hold Shoe/Stick | throw | works (stock) |
| B8 | rm11 bear | Fish still held | use Fish on bear | **works** (stock — the point of B1) |

## C — Kidnap & cellar (rm85/86)
| # | Setup | Do | Expect |
|---|---|---|---|
| C1 | **no** Hammer or no banked throwable | walk toward inn's north zone | "Not yet!" **once**, walk-back to y≈165, controls return |
| C2 | C: `send ego get 22` + won cat scene (or `get 8` + `put 8 6`) | walk in again | **kidnapped normally** (stock) |
| C3 | in cellar | Hammer on door; get Rope; mouse frees you | all stock |

## D — Desert temple (rm18)
| # | Setup | Do | Expect |
|---|---|---|---|
| D1 | inside via Staff, **leave Bottle/Coin on floor** | walk exit strip | **refused** + walk-back to entrance, no message spam |
| D2 | pick both up | walk exit | leaves normally |

## E — Mountains
| # | Where | Setup | Do | Expect |
|---|---|---|---|---|
| E1 | rm30 | hold Rope | use Rope on branch | **refused** "Better not…"; rope kept |
| E2 | rm34 eagle | hold Pie only | offer Pie | **refused** (pie is the yeti's) |
| E3 | rm34 | hold Lamb (half is fine) | feed Lamb | **works** (stock; the half satisfies the nest fold) |
| E6 | rm32 | flag 16 clear | walk east past x≈105 without ever eating | stock hungerDeath (preventable on-screen: eat the lamb) |
| E4 | rm36 yeti | pie NOT thrown | walk west | "Not yet!" once, walk-back to mid-room; **north stays free**; chase still escapable |
| E5 | rm36 | throw Pie at yeti | walk west | crosses to rm35 normally |

## E½ — The sled commit (rm32) — NEW: the mountains' real point of no return
| # | Setup | Do | Expect |
|---|---|---|---|
| S1 | missing any of: Pie 2, Harp 10, Beeswax 18, Hammer 22, Lamb 19 (or fed eagle) | use the Sled (29) on the slope | **"Not yet!"** — sled kept, ride refused (both click paths) |
| S2 | walk toward rm33 without riding | walk east | turned back at the edge (same demand) |
| S3 | full carries | ride | sled breaks, lands rm33 — stock; and **rm33→32 walk-back stays blocked** (stock terrain) |

## F — The roc edge (rm40) — now: Crystal + fed eagle only
| # | Setup | Do | Expect |
|---|---|---|---|
| F1 | no Crystal (pried at rm38, needs Hammer) | walk the top zone | "Not yet!" once + walk-back |
| F1b | Crystal held but eagle NOT fed (lamb still in hand) | walk the top zone | **turned back** — the nest would kill you; feed the eagle first |
| F2 | **the WINNING state**: `get 10`,`get 18`,`get 21`, eagle fed (`get 19`,`put 19 34`) — carrying NO lamb | walk the top zone (the strip is near 148,144) | **carried off by the roc** → nest. ✅ FIXED before play (fold_respell: the guard now reads `owner(19)==34`, not `has 19`) and harness-verified both ways — this row is a spot-check. |

## G — Nest (rm42) ✅ harness-verified, quick re-check
| # | Setup | Do | Expect |
|---|---|---|---|
| G1 | eagle fed, arrive via roc (or F2) | wait 30s+ | **eggs do NOT crack** until Locket taken |
| G2 | take Locket | — | eggs crack → chicks → **eagle rescue** → rm43, Cedric greets |

## H — Coast, hermit, the sail (last gate before Mordack's)
| # | Where | Setup | Do | Expect |
|---|---|---|---|---|
| H1 | beach rm90 | — | get Fishhook | stock |
| H2 | hermit island rm44 | — | get IronBar | stock |
| H3 | coast rm44/45/46 | missing Bar or Hook | sail on toward Mordack's | **refused** (scene doesn't start / "Not yet!") |
| H4 | 〃 | C: `send ego get 30` + `send ego get 31` | sail | **departs** (ONE-WAY — save first) |
| H5 | hermit rm46/660 | with both | hermit scenes (shell heals Cedric etc.) | stock, un-walled |

## I — Open verdicts (answers change what I build)
| # | Question | How |
|---|---|---|
| P1 | empty pea bag still bags the cat? | castle: empty bag on henchman (4 throws), then fish+empty bag on cat |
| P2 | far-miss pea throw wasted? | throw pea at henchman from across the room; check flag 63 |
| L3 | 2nd capture after one hole-rescue = death? | get caught twice (flag 96) |
| C1 | hammerless route into mountains? descent one-way? | try reaching mountains skipping the kidnap; try walking back down |

## J — Must-be-stock spot checks
Snake still demands tambourine · witch forest needs worn Amulet · in-castle henchman behavior (58–61) unchanged **even after** fish spent on cat · wand always works in endgame · EAT-pie joke text unchanged.
