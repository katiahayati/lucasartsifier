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
| 2 | `src/model.py` | Builds the transition-system IR: resolves item/global **names**, extracts **guarded effects** (`get/put`→item ownership, `newRoom`→move, `= gFlag`→state), and the **movement graph** (`Rm` north/south/east/west edge props, `Door entranceTo:`, `setRegions:`). Parser `Said` strings and positional guards are lifted away — winnability is gated on items + flags. |
| 3 | `src/analyze.py` | Derived maps (item sources / requirements), irreversible latches, timed-gate detection, and per-item point-of-no-return candidates. |
| 4 | `src/slice.py` | **Cone-of-influence slice** — backward slice from goal/death/latches to the winnability-relevant state (LSL2: 480 globals → 43, 32 items → 21). |
| 5 | `src/search.py` | **SCC-condensation reachability** — collapses freely-explorable room sets into a DAG of "acts" whose one-way edges are the true points of no return; goal-aware frontier detection. (Naive product-state BFS is intractable — 2²¹ item subsets — so we use this instead.) |
| — | `run.py` | Chains all of the above end-to-end. |

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

## Status
Phase A (static detection) is complete and reproducible. **Not engine-verified**
yet (ScummVM-in-the-loop is a deferred future phase). Phase B (drop-in patches)
is not started. See `PLAN.md`.

## Input note
The analyzer reads a **decompilation** (vendored from
[sluicebox/sci-scripts](https://github.com/sluicebox/sci-scripts), version-matched
to LSL2 1.002.000), not raw `RESOURCE.*` files. The decompilation is fetched, not
redistributed (`vendor/` is git-ignored).
