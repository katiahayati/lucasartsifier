# KQ6 guard oracle — what should be guarded, and where

The answer key for KQ6 **patching**, in the shape `docs/KQ6-ITEM-ORACLE.md` is for detection.
Derived 2026-08-01 from the user's in-game rulings, the walkthroughs and the scripts — **not** from
what the engine currently emits. When the engine and this file disagree, this file is the target.

`[U]` = user-tested in-game (authoritative) · `[W]` = walkthrough- or script-derived (ours)

## Boundary guards

| # | site | demand | why |
|---|---|---|---|
| 1 | **`rm340::init`, the capture arming** — `(and (not (proc913_0 1)) (proc913_0 2))`, i.e. the 2nd Sacred Mountain visit | brick 2, tinderBox 48, holeInTheWall 18, scarf 41 | `[U]` you cannot leave until the minotaur is dead, and all four are sourced outside. **Not an out-edge**: the guards grab you on ARRIVAL, so by any out-edge you are already committed. Gate the arming — lacking the four, you get the first-visit brush-off instead of the toss-in. The brick belongs here too, not at rm420: from inside there is no way back for it |
| 2 | **rm340 → rm155** (Realm of the Dead entry, flag 15, one visit) | deadMansCoin 7, mirror 24, teaCup 46 | `[U]` coin pays Charon (rm660), mirror is the only non-death exit (rm690), cup must be filled at the Styx (rm660) |
| 3 | **rm660 → rm670** (Charon's crossing, coin consumed, one-way) | mirror 24, gauntlet 15, **cup filled with Styx water (flag 58)** | `[U]` gauntlet is sourced at rm650, *before* the crossing, and without it the game refuses to show Death the mirror. Cup-filled joined 2026-08-05 (user, in-game): "you can't get styx water into the teacup after you cross charon... there should not be [any] realm guard after charon" — Charon is the LAST controllable moment; the interior (670/680/690) is sealed (670↛660; 680↛670 via `dontGoAlex`) and its only exits are the win ride or death, so it carries NO guards |
| 4 | **rm640 → rm650** for the items; **rm680 → rm155** for the flag | handkerchief 17, skeletonKey 44 @ 640→650 · **cup filled** (flag 58) @ 680→155 | `[U]` "we should not let you leave the realm of the dead without it" — and the site moved on the user's own in-game test (2026-08-02): **you can go 640→650 but not back** (the knight's room is one-way; the ticket taker at rm640 keeps your ticket), so rm680→155 would demand compliance where none is possible. The last crossing that can still comply for the rm630/rm640 items is 640→650, exactly where the engine derived it. ~~The cup-filled flag stays at the Realm exit — the Styx (rm660) is past 650 either way~~ **CORRECTED 2026-08-05 (user, in-game, finding #16): the fill is only possible BEFORE crossing Charon, so the cup-filled demand moves to row 3 (rm660→rm670) and NO guard may sit past Charon** — the v19 680→155 arm-events are the finding-#15 hang and leave the set |
| 5 | **rm380 → rm370** (Lady Celeste's spring, one visit) | sacredWater 40 | `[W]` drawn only inside; poured into the old lamp at rm580 |
| 6 | **rm220 → rm730** (castle, SHORT — servant's dress) | dagger 8, mirror 24, nightingale 27, (mint 23 \| peppermint 31) | `[W]` terminal region. No Realm items: the short route never enters the Realm |
| 7 | **rm230 → rm710** (castle, LONG — magic paint) | dagger 8, mirror 24, handkerchief 17, skeletonKey 44, (mint \| peppermint) | `[W]` no nightingale: the paint brush *is* the nightingale after three pawn-counter trades |

## Action refusals

| # | site | refuse | why |
|---|---|---|---|
| 8 | **rm420 `throwSkull`** (crushing ceiling) | throwing the skull into the gears | `[U]` "exactly the kind of bad use we need to prevent" — it looks like the solution, it kills you, and the skull is gone (rm420 re-casts the brick, never the skull) |
| 9 | **rm240 `lampTradeScr`** (lamp peddler) | trading the old lamp before its three waters are poured | `[U]` "you cannot trade it again because the peddler leaves" — this is not the pawn shop. rm580's `makeRain` can then never fire |
| 10 | **Main, mint / peppermint destroy-verb** | eating them | `[W]` one of the two is needed at rm750, and past the castle door the pawn shop is unreachable |

## Write holds — a flip waits instead of a door refusing

| # | site | demand | why |
|---|---|---|---|
| 11 | **the wedding flip (flag 166, `rFlag1 $0002`) — every writer**: rm880's watch scene, rm740's debug menu, and **`rgCastle::doit`'s fuse** (the countdown clause freezes; the long route's only writer) | letter 20 in hand | `[U]` the softlock: the flip refuses the hidden-passage arm (rm720), the only route to the letter's trunk (rm781), while Saladin (rm730) still demands showing it (finding #3, play-tested 2026-08-03). `[W]` the fuse freeze is safe: an armed fuse implies the ghost-boy bit ($8000), so the hallway stays open while the hold refuses — nobody is stalled, the wedding starts the moment the letter is pocketed. Mechanism: `KQ6-CASTLE-CAPTURE-MAP.md` §2b (v22, 2026-08-05; NOT play-tested) |

## Explicit negatives — no guard belongs here

* **shield 43, clothes 5, coal 6** — `[U]` both catacomb levels re-enter from the surface (rm340
  left → rm405, far left → rm440), so nothing found inside strands; coal buys the egg, and it is
  the egg that crosses.
* **nightingale 27 at the LONG door** — cannot be held there (it is the brush).
* **handkerchief 17 / skeletonKey 44 at the SHORT door** — cannot exist there. Demanding either
  would wall the route, which this project holds to be strictly worse than the softlock.
* **The upper→lower fall (B2)** — a hard one-way within a visit, but re-entry from the surface
  means nothing found upstairs strands.

## Notes

* The **skull** is spent at the Mists (amber + egg + hair) *before* the Realm entry, so it is not a
  carry-in at #2; its only guard is #8.
* **mint at the long door** (#7) is a per-route need question and is *not* settled: the genie is
  beatable with the lamp instead.
* The two castle doors are mutually exclusive **by item, not by flag** — rm580's Druids burn
  Beauty's clothes and there is no second source.
* Guards 2/3 both demand the mirror; the later one is the tighter and the redundancy is harmless.

Related: `docs/KQ6-ITEM-ORACLE.md` (detection oracle), `docs/KQ6-STATUS.md` (what is actually
emitted and placed today), `docs/SCI11-PATCHING-PLAN.md` (how to get from one to the other).
