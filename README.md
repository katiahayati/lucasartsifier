# Sierra softlock analyzer

Automatically finds **walking-dead / softlock states** in Sierra SCI adventure
games — states where the game still accepts input but victory has already become
impossible (e.g. boarding the LSL2 cruise ship without the sunscreen you can only
buy back in Los Angeles). Prototyped on **Leisure Suit Larry 2** (SCI0); the core
is engine-general.

It reads the game's **decompiled scripts**, lifts them into a transition system of
*item + flag + location* state, and asks a reachability question: from each
reachable state, can you still reach the winning ending? Where the answer flips
from yes to no is a softlock frontier.

See `PLAN.md` for the full design and `reports/lsl2_phaseA.md` for the current
findings (it reproduces LSL2's three documented dead-ends: sunscreen-before-boat,
the lifeboat items, and the boat timer).

## Run it

```bash
./scripts/fetch_source.sh     # vendor the decompiled LSL2 scripts (one time)
python3 run.py                # parse -> IR -> COI slice -> reachability -> reports
```

No dependencies beyond Python 3. Output is deterministic. Reports land in
`reports/`:
- `lsl2_phaseA.md` / `.json` — the softlock catalog (candidates, frontier edges,
  last-obtainable location, pattern tag, timed gates, irreversible latches).
- `lsl2_reachability.json` — the COI slice + SCC "acts" + goal-aware candidates.

## How it works (pipeline)

| stage | file | what it does |
|---|---|---|
| 1 | `src/sexpr.py` | Reads decompiled Sierra Script (`.sc`) into S-expressions. |
| 2 | `src/model.py` | Builds the transition-system IR: resolves item/global **names**, extracts **guarded effects** (`get/put`→item ownership, `newRoom`→move, `= gFlag`→state, `setScript:`→machine entry), **guard trees** (`and`/`or`/`not`, not a flattened conjunction), and the **movement graph**. Parser `Said` strings and positional guards are lifted away. |
| 3 | `src/analyze.py` | Derived maps (item sources / requirements), irreversible latches, timed-gate detection, edge preconditions. |
| 4 | `src/machine.py` | **Lifts each room's Script state machines** into the transition system: `changeState` switches → states, if/cond → path conditions, `= seconds`/`self`-cue → advance, plus **bounded script-local counters**. A room is not one node — LSL2's lifeboat gauntlet lives entirely inside `rm138Script`'s `(state, day)` loop. |
| 5 | `src/closure.py` | **The semantic core.** A least fixpoint over (rooms, items, flag-values) that honours every guard in 3-valued logic. Softlock detection is a *query* over it — "from this edge's post-state, does the goal still close?" — not a feature. |
| — | `src/slice.py`, `src/search.py` | **Legacy syntactic path**, pending deletion — see below. |
| — | `run.py` | Chains all of the above end-to-end. |
| — | `src/_check_core.py` | Cross-game regression check for the semantic core. |

### Why two paths, and which to trust
`search.py` decides "you need item x here" from the *syntax* — an `OWN(x)` guard is
mentioned in room R. That cannot distinguish an item that **saves** you from one that
**kills** you, and LSL2 has both: the Spinach_Dip is tested first on the raft's day 6
and jumps straight to the death chain. `closure.py` derives the same facts from
winnability instead, so it gets the polarity right. The syntactic path is kept only as
a cross-check for the handful of cases the fixpoint cannot yet derive (see Status);
**do not synthesize patches from it.**

## Engine-general core vs. per-game config

Almost everything is generic **SCI0** machinery. The title-specific knobs live in
one place, `src/config.py`:

- `src_dir` — the decompiled script directory
- `start_room` — free-roam entry point
- `goal_rooms` / `goal_scripts` — the winning terminal (LSL2: the Nontoonyt wedding)
- `timer_globals` — the game-clock globals
- `region_labels` — human labels for the report (cosmetic)

To target another SCI0 game, point `config.ACTIVE` at a new `GameConfig`.

### Auto-discovering the config
`src/discover.py` performs this automatically and emits a *proposed* config
(`reports/discovered_config.json` + a paste-able snippet):

```bash
python3 src/discover.py
```

- **Timers** — globals compared in a guard that are also driven like a clock
  (written per-cycle in a `doit`, or stepped `++`/`--`). Finds every real LSL2
  timer, incl. the *countdown* `gRgTimer` — no human input.
- **Start room** — the player-controlled room whose forward reach covers ~every
  other room (the source act). Recovers the LA act; hand-set `rm21` is in it.
- **Goal** — rooms ranked by victory text + late/sink structure, minus the death
  modal. Surfaces the wedding cluster (rm75/77/78) and, tellingly, the *intermediate*
  lottery "win" (rm104) — which is why the final pick is **confirmed once by a
  human** (the plan's single intended manual step).
- **Region labels** — cosmetic only; best-effort and the noisiest of the four
  (the analysis itself uses region numbers, so this doesn't affect results).

Validation: `discover.py` checks its output against the hand-set `config.LSL2` and
reproduces it (start ✓, every real timer ✓, goal cluster surfaced ✓).

## Phase B — neutralizing softlocks — **DISABLED, the patch broke the game**

The idea was the **maximally-permissive supervisor of the winnability game**: you can't
cross an irreversible edge until you hold everything you'll need past it. The idea is
sound. The implementation synthesized its guards from the *syntactic* path, and shipped
this:

```
rm38 -> rm131 : (and (gEgo has: 11) (gEgo has: 12) (gEgo has: 13) (gEgo has: 14))
                                              ^^^^^^^^^^^^^^^^ Spinach_Dip
```

The Spinach_Dip is **fatal** — rm138 state 6 day 6 tests it first and jumps to the death
chain ("the mayonnaise has spoiled"). Day 6 actually needs Sewing_Kit **or** Fruit. So
the guard forces the one item that kills you and **makes LSL2 unwinnable**; it is wrong on
3 of its 4 items. `validate_patch.py` blessed it because it imports the same `SccReach`
core — detector, synthesizer and validator shared one blind spot, so the "proof" proved
nothing. `src/patch.py` now refuses to run (`DISABLED_WHY`); re-enable it only once guards
come from `closure.py`.

## Status
- **Phase A** (static detection) — reproducible and self-configuring.
- **The semantic core** (`closure.py` + `machine.py`) — derives the LSL2 lifeboat gauntlet
  (Sunscreen, Grotesque_Gulp, Wig, Fruit-OR-Sewing_Kit), the glacier (Sand-OR-Ashes) and
  the KQ4 whale, with no special-casing. Both games sanity-PASS: LSL2 85/100 rooms, KQ4
  89/106. `python3 src/_check_core.py` — the numbers above are asserted there, so they
  cannot drift; **do not hand-write counts into this file.** (They already did: this
  section claimed "0 un-modelled machine exits, KQ4 has 1" long after the strict-walk
  commit made it 10 and 5. `run.py` prints the real figure on every run.)
- **Phase B** (neutralization) — **withdrawn**, see above.
- **Phase A** / the syntactic path — 11 findings the semantic core does not report:
  | syntactic-only finding | verdict |
  |---|---|
  | Swimsuit (rm26→27) | **false positive** — its `has: 5` guards are a `(Load rsVIEW 132)` preload and a "you don't have it" message, not a gate |
  | Spinach_Dip (rm38→131) | **false positive** — it is *fatal*, not required |
  | Fruit + Sewing_Kit (rm38→131) | **now derived**, as a disjunction — `(or (has: 11) (has: 12))` |
  | Airline_Ticket (rm55→56) | **false positive** — the ticket is re-acquirable from rm56 (rm55 is reachable again by another route), so crossing strands nothing |
  | Sand + Ashes (rm79→80), Parachute, Bobby_Pin, Hair_Rejuvenator | **real, and we miss them** — see gap ② |

  **Beware the decoys when judging these.** Al Lowe planted losing uses of the real
  items, each scoring −5: pouring the Hair_Rejuvenator on the plane's padlock ("it makes
  the lock look really new!") or on the glacier ("Nothing happens."), jimmying the lock
  with the Knife ("for naught"). Those are the *first* hits when you grep, and reading
  only them makes a load-bearing item look like a red herring. The Bobby_Pin really does
  unlock the plane's emergency exit (`= gAirplaneDoorStatus 1`), and the Hair_Rejuvenator
  really is the endgame bomb — with the Airsick_Bag stuffed in its neck as a wick.
- ① **disjunctive requirements — CLOSED.** `closure.requirements()` computes *minimal
  blocking sets*: minimal `S` where lacking **all** of `S` loses but dropping any member
  is survivable. Read as "hold ≥1 of S", so `|S| == 1` is an ordinary stranding and
  `|S| > 1` is a disjunction — one shape, both cases. The edge's guard is the AND of its
  clauses, i.e. proper CNF.
- ② **the endgame chain is ungated in the model** (Sand/Ashes, Parachute, Bobby_Pin,
  Hair_Rejuvenator). One cluster, two causes, both now identified:
  - **`gIslandStatus` is poisoned to ANY** by a single `(++ gIslandStatus)` at rm79:226,
    so the wedding gate `rm77→rm78 : gIslandStatus == 104` — and the real chain behind it
    (rm84 sets 100 → rm92 sets 103 → rm75 sets 104 given 103) — is vacuously satisfiable.
    Simply *not* letting a step poison the global makes it concrete and both games still
    pass. (Modelling `++` as a relation over the value set does **not** work: it saturates
    to `[0..106]` and costs 15×.)
  - **the elevator (rm82→rm83) is gated geometrically**, by a door Prop's collision, and
    nothing in the script says so. With both addressed — concrete `gIslandStatus` plus a
    *declared* elevator gate — a new correct finding appears: `rm79→rm80 must hold
    Hair_Rejuvenator`. The declaration is the open design question: it is a per-game fact
    we cannot derive, of the same kind as `goal_rooms`.

  Beware the model's escape hatch here: it will happily "walk back" for a missing item
  **through the endgame** (`rm80 → rm81 → rm181 → rm82 → rm83 → rm84 → rm92 → rm75`),
  which is really riding the elevator down, surviving the lair and the eruption, and
  strolling out. That fake return path is why Sand/Ashes look recoverable. Any claim that
  an item is "re-obtainable" past a frontier deserves a look at *which route* the closure
  used.
- **Not engine-verified** (ScummVM-in-the-loop is deferred). See `PLAN.md`.

## Input note
The analyzer reads a **decompilation** (vendored from
[sluicebox/sci-scripts](https://github.com/sluicebox/sci-scripts), version-matched
to LSL2 1.002.000), not raw `RESOURCE.*` files. The decompilation is fetched, not
redistributed (`vendor/` is git-ignored).
