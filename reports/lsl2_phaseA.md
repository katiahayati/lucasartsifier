# LSL2 softlock catalog — Phase A (static analysis, **not yet engine-verified**)

**Game:** Leisure Suit Larry 2 v1.002.000 (SCI0, interpreter 0.000.409), English DOS.
**Method:** decompiled `.sc` → S-expr (`sexpr.py`) → normalized transition-system IR
(`model.py`) → reachability/frontier analysis (`analyze.py`). No walkthrough or
game-specific hand-coding used; everything below is derived from the scripts.
Reproduce: `python3 src/analyze.py` → `reports/lsl2_phaseA.json`.

## Pipeline status
| stage | state |
|---|---|
| Parse 118 scripts | ✅ 118/118 |
| IR: 32 items + 480 globals name-resolved, 633 guarded transitions | ✅ |
| Location model: newRoom + Rm edge-props (N/S/E/W) + Door `entranceTo` + `setRegions` | ✅ 171 edges, 100 rooms |
| Reachability + point-of-no-return frontier | ✅ |
| **COI slice** (`slice.py`) — prune to winnability-relevant state | ✅ 480→43 globals, 32→21 items |
| **Goal-aware SCC reachability** (`search.py`) | ✅ tractable exact method |
| Goal/death identification | ◐ death oracle found; goal = wedding rooms {75,76,77,78,178} |
| Full product-state BFS (timed/economy) | ◐ intractable at scale (see below); SCC method used instead |
| Engine verification | ⬜ deferred (possible future phase) |

## Geography (auto-derived from `setRegions:`)
region **200 = Los Angeles** · **300 = cruise ship / voyage** · **400/401 = Nontoonyt
Island** · 500 island interior · 600 airport/plane · 700 volcano/jungle. The LA→ship
transition is a **single one-way edge `rm28→rm31`** (boarding); no return edge exists —
the structural point of no return behind the classic trap.

## Softlock candidates (10) — ranked; each is a *missing-prereq-before-gate*
"High" = the resource's only source is in a different region than where it's needed, and
no source is reachable once you're there (a structural point of no return). All are
**candidates pending engine verification** — some may be false positives (alternate
acquisition, or a non-critical use of the item).

| # | resource | needed in | last obtainable | conf |
|---|---|---|---|---|
| 1 | **Sunscreen** | cruise ship (region 300) | rm118 LA drugstore (region 200) | high |
| 2 | **Swimsuit** | cruise ship (300) | rm116 LA (200) | high |
| 3 | Wig | cruise ship (300) | rm37 (ship interior) | high |
| 4 | Bikini_Top | Nontoonyt Island (400) | rm134 (ship) | high |
| 5 | Bikini_Bottom | Nontoonyt Island (400) | rm41 (island 401) | high |
| 6 | **Fruit** | rm138 **lifeboat** | rm32 (ship) | medium |
| 7 | **Sewing_Kit** | rm138 **lifeboat** | rm33 (ship) | medium |
| 8 | **Spinach_Dip** | rm138 lifeboat / ship | rm35 (ship) | medium |
| 9 | Grotesque_Gulp | rm138 lifeboat | rm114 LA (200) | medium |

**These reproduce the documented LSL2 dead-ends:**
- **#1 Sunscreen-before-boat** — the textbook LSL2 walking-dead state. Frontier: LA→ship
  boarding (`rm28→rm31`). Distinguishing predicate `own(9)`. ✅
- **#6–9 Lifeboat items** — Fruit / Sewing_Kit / Spinach_Dip / Grotesque_Gulp needed in
  **rm138 (the lifeboat)**, obtainable only on the ship (or LA) before the bomb goes off
  and the lifeboats are lowered. Frontier: the ship→lifeboat gate. ✅

## Timed gates (the "boat timer" class) ⏱
Auto-detected clocks: `gRgTimer` (real-game timer via `SetRgTimer`), `gGameSeconds`,
`gCurrentTimer`. Timer-compared transitions fire in rm0/rm200/rm300/rm32
(`gCurrentTimer==N → set(gCurrentStatus=…)`), driving LSL2's staged timed events. Exact
turn thresholds and which lead to unwinnable states still to be pinned.

## Irreversible story-flag latches (31; set-once, never reset)
These are candidate one-way gates. Notable:
- `gLoweredLifeboats`, `gBombStatus`(1→2→3) — the **ship→lifeboat** shipwreck sequence.
- `gWearingSunscreen`(1→3), `gReappliedSunscreen`, `gScoredWoreSunscreen` — sunscreen state.
- `gWearingWig`, `gLAhaircut` — disguise.
- `gPossibleScore := 500` — **max score is 500** (resolves a plan open-item; it is global
  index 16 / `gPossibleScore`, confirmed by value not assumption).

## Goal / death (M2, partial)
- **Death oracle found:** the Main.sc restart modal ("Well, Larry, you've screwed up
  again!" → `{Restore}/{Restart}/{__Quit__}`, `gGame restart:`). Any transition raising
  this = death (not a softlock).
- **Victory:** the Nontoonyt Island endgame (rm42 "Congratulations… survived… adrift";
  rm75 Kalalau / defeat Dr. Nonookee / marriage). Exact winning terminal still to be
  confirmed (the plan's one-time human-confirmation step).

## Workstream A — COI slice + full-reachability (state-space) analysis
Added to make the detector *complete* (state, not just per-item) and *goal-aware*.

- **COI slice** (`src/slice.py`): backward slice from the goal guards, death guards, and
  irreversible latches shrinks the tracked state from **480 globals → 43** and **32 items →
  21** — the single biggest tractability lever. Kept variables are exactly the story state
  (all candidate items, `gLoweredLifeboats`, `gBombStatus`, sunscreen/wig flags, timers).
- **State explosion is real** (validates the PLAN's central concern): naive explicit-state
  BFS over `(room, item-subset, flag-subset)` blows past a 400 000-state cap — 21 items
  alone is 2²¹ subsets, and the freely-explorable early game makes a huge fraction
  reachable. Brute enumeration is the wrong tool here.
- **Tractable exact method used instead — SCC condensation** (`src/search.py`): collapse
  each strongly-connected set of rooms (where you can wander and backtrack freely) into one
  node. LSL2's 100 rooms condense to **30 components with just 4 real "acts"** —
  **LA (25 rooms) · ship (9) · island (37) · a 3-room island bit** — joined by one-way
  edges that are the true points of no return. State only matters *across* those edges.
- **Goal-aware frontier:** a resource is only flagged if, from the act where it's needed,
  you (a) can no longer reach any source and (b) can still otherwise reach the wedding.
  This reproduces the catalog above from *exact* reachability regions and correctly drops
  candidates that can't actually block victory — more precise than the region heuristic.
  Output: `reports/lsl2_reachability.json`.
- **Economy pattern:** LSL2 money is item-based (Dollar_Bill / Million_Dollar_Bill /
  Wad_O__Dough), not a counter — so "spent below a cost" reduces to item-gating, already
  covered. No continuous money variable to model.
- **Timed pattern:** the timer machinery is *detected* (`gRgTimer`/`gGameSeconds`/
  `gCurrentTimer`), but *proving* a timed softlock (dawdle → miss event → unwinnable) needs
  a timer-forcing model on top of the SCC analysis — future work. For an exhaustive proof
  at full state granularity, the scalable route is emitting the sliced domain to PDDL and
  asking a planner (Fast Downward) for `unsolvable`.

## Known limitations / next
1. **Not engine-verified.** Findings are static candidates; the trust anchor (reach the
   frontier in ScummVM → assert goal-unreachable → inject the item → assert reachable) is
   deferred per the current direction.
2. **State-gated reachability not yet full.** Movement is over-approximated (guards on
   edges ignored). This is conservative for the item-gate patterns here, but the *timed*
   and *economy* (money) patterns need the full explicit-state search over
   `(location, items, flags, counters)`.
3. **Goal terminal** needs pinning + confirmation.
4. A few candidates may be false positives (alternate item sources / non-critical uses) —
   engine verification is what separates them.
