# LSL2 softlock neutralization — Phase B (the LucasArts invariant)

Generalizable fix for every softlock Phase A finds, via the **maximally-permissive
supervisor of the winnability game**: forbid the controllable moves that leave the winning
region (the frontier edges), and delete the uncontrollable timers that can push you out.
Concretely — *you can't take an irreversible edge until you hold everything you'll need
past it.* The guards are computed directly from the reachability analysis; detection and
synthesis are the same object.

Pipeline: `src/patch.py` (synthesize) → `src/patch_sci0.py` (realize in source) →
`src/validate_patch.py` (guard-aware regression).

## Synthesized remedies (2 act-boundary guards neutralize all 10 softlocks)
| irreversible edge | LucasArts guard: can't cross until you hold… | fixes |
|---|---|---|
| **rm26 → rm27** (leave LA for the ship) | Swimsuit, Grotesque_Gulp, **Sunscreen** | the sunscreen-before-boat class |
| **rm38 → rm131** (leave the ship for the lifeboat) | **Fruit, Sewing_Kit, Spinach_Dip**, Wig | the lifeboat-items class |

Each guard = `⋀ own(r)` over exactly the resources that are obtainable *before* that edge,
needed *after* it, and unobtainable once crossed — i.e. the frontier's distinguishing
predicates. Realized in source by wrapping the room's `newRoom:` in
`(if (and (gEgo has: …)) (… newRoom: …) else (NotNow))`; originals untouched, edits land in
`out/patched_src/`.

Forcing timers: none of the detected LSL2 timers set a one-way latch that crosses a
frontier, so 0 timer-deletions were required here (the mechanism is in place for games
where a clock forces the crossing).

## Regression result — PASS ✅
Guard-aware check (`validate_patch.py`) computes the **guaranteed-inventory invariant** the
guards establish (`guaranteed[C]` = items you provably hold on entering component C) and
confirms each stranded item is now guaranteed where it's needed:

```
ORIGINAL game: 10 softlock candidates
PATCHED  game: 10 neutralized by guards, 0 SURVIVING
goal still reachable:        True
guard deadlocks:             0
PASS — patched game is softlock-free and still winnable
```

Selectivity check (not a trivial pass): past the LA gate the ship act guarantees exactly
{Swimsuit, Grotesque_Gulp, Sunscreen}; past both gates the lifeboat act guarantees those
plus {Fruit, Sewing_Kit, Spinach_Dip, Wig}; unrelated items (e.g. Knife) are *not*
guaranteed. Only 3–7 of 32 items are forced at any act — the invariant is real.

## Why this is the right general method
- **Detector-coupled:** the guards are the analyzer's frontier output; no new analysis.
- **Faithful:** every puzzle survives — you still have to *earn* the sunscreen; you just
  can't walk into the dead end. (Contrast auto-granting the item, which is a "cheat".)
- **Provable:** it's the winning region of a reachability game; the patched game is closed
  under play. Winnable-by-construction, verified by the regression.
- **Safe/degrades gracefully:** if a required resource weren't obtainable before its gate
  (the game were a guaranteed dead-end), the check flags a deadlock instead of silently
  over-blocking — telling us that frontier needs a reversible/relocate remedy.

## Not yet done
- **Shippable drop-in binary (B4):** compile a patched room → loose `script.NNN` that
  ScummVM loads over `resource.001` (mechanism confirmed). Blocked only by the SCI-compiler
  toolchain on Linux (SCICompanion is Windows) — a spike. In-model fix is proven above.
- **Engine verification (M4):** deferred.
