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
  (Sunscreen, Grotesque_Gulp, Wig) and the KQ4 whale with no special-casing; both games
  sanity-PASS; LSL2 has **0** un-modelled machine exits, KQ4 has 1.
  `python3 src/_check_core.py`.
- **Phase B** (neutralization) — **withdrawn**, see above.
- **Phase A** / the syntactic path — 11 findings the semantic core does not report:
  | syntactic-only finding | verdict |
  |---|---|
  | Swimsuit (rm26→27) | **false positive** — its `has: 5` guards are a `(Load rsVIEW 132)` preload and a "you don't have it" message, not a gate |
  | Spinach_Dip (rm38→131) | **false positive** — it is *fatal*, not required |
  | Fruit + Sewing_Kit (rm38→131), Sand + Ashes (rm79→80) | **real, but disjunctive** — see gap ① |
  | Parachute, Bobby_Pin, Hair_Rejuvenator (rm57→58, rm82→83) | **real, and we miss them** — see gap ② |
  | Airline_Ticket (rm55→56) | the *item* is real (rm57's gate opens the jetway); whether that *edge* is a point of no return is unverified |

  **Beware the decoys when judging these.** Al Lowe planted losing uses of the real
  items, each scoring −5: pouring the Hair_Rejuvenator on the plane's padlock ("it makes
  the lock look really new!") or on the glacier ("Nothing happens."), jimmying the lock
  with the Knife ("for naught"). Those are the *first* hits when you grep, and reading
  only them makes a load-bearing item look like a red herring. The Bobby_Pin really does
  unlock the plane's emergency exit (`= gAirplaneDoorStatus 1`), and the Hair_Rejuvenator
  really is the endgame bomb — with the Airsick_Bag stuffed in its neck as a wick.
- Remaining gaps:
  - ① **disjunctive requirements.** `strandings` removes one item at a time, so it can
    never see "you need Fruit **or** Sewing_Kit and have neither" — each alone is
    covered by the other. Needs a *minimal sufficient kit* query, not single removals.
  - ② **the endgame chain is ungated in the model.** Plane door → parachute → bomb are
    all missed, and it is one cluster, not three items: the model reaches the wedding
    without ever needing them. Partly mode registers (we model a global as the set of
    values it can *ever* take, so `(== gCurrentStatus 12)` asks "can it be 12?", not "is
    it 12 now?"), but not only — `W(rm83, Hair_Rejuvenator)` is True, so something on
    rm83→84→…→rm75-78 that should require the bomb does not. Not yet diagnosed.
- **Not engine-verified** (ScummVM-in-the-loop is deferred). See `PLAN.md`.

## Input note
The analyzer reads a **decompilation** (vendored from
[sluicebox/sci-scripts](https://github.com/sluicebox/sci-scripts), version-matched
to LSL2 1.002.000), not raw `RESOURCE.*` files. The decompilation is fetched, not
redistributed (`vendor/` is git-ignored).
