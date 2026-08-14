# Sierra softlock analyzer

Finds **softlocks** in Sierra SCI adventure games — states where the game still accepts input but
victory has already become impossible — and emits a patch that prevents them.

Sierra games, unlike LucasArts ones, let you get stuck. Forget the sunscreen in Los Angeles, board
the cruise ship, and you die days later on the raft with no way back. This finds every such trap
automatically and blocks the crossing that causes it.

A patched game is playable normally, because the patch mechanism is how Sierra shipped its own bug fixes.
You can set the guard behavior in-game: **Full** prevents every dangerous action; **Lite** prevents the action
once, then allows it with a warning; and **Off** turns the guards off.

## Caveat Player

**Some deaths are deliberately left in** — the ones you can still avoid from where you are. In Leisure Suit Larry 2,
  if you walk onto the KGB beach without the full disguise you will die. Some pieces of the disguise are only obtained
  on the cruise ship, so we prevent you from leaving it until you have them. But the rest of the disguise is obtainable
  on the island, i.e. from the place the death occurs, so we let it happen. The main reason is that these kinds of deaths
  are how Sierra games hint at what you need to do. So, as Al Lowe says, you still have to "Save Early, Save Often!".

## Status

Four games run end to end. Nothing about a title is declared: the start room, the victory room,
the death signal and the debug flag are all derived from the game's own code.

| game | engine | model | findings | edits placed |
|---|---|---|---|---|
| **Leisure Suit Larry 2** (1988) | SCI0 | 101 rooms, 27 components | 15 items + 1 group | 12 of 12 | 
| **King's Quest IV** (1988) | SCI0 | 110 rooms, 15 components | 7 items | 5 of 5 | 
| **King's Quest VI** (1992) | SCI1.1 | 86 rooms, 15 components | 18 items + 1 group | 24 of 26 | 
| **Laura Bow 2: The Dagger of Amon Ra** (1992) | SCI1.1 | 78 rooms, 26 components | 10 items | 5 of 5 | 

"Findings" is every detector's verdict unioned per item — the same seven a run prints and the
frozen surface freezes; an item found by something other than the three stranding detectors is
labeled with what found it (*sealed by a plot flag*, *fatal to use here*, …). "Edits placed"
counts the guard and sink sites the patcher actually landed. KQ6's missing two are the suite's
one deliberate red — a shared-dispatcher seam and a trade-shaped sink, both with their reasons
written down rather than quietly dropped.

## Install

The analysis is Python 3 with **no third-party packages at all** — `src/` imports only the
standard library. What needs installing is the two external toolchains it drives: the decompiler
(C#) and the SCI compiler (C++), both built here from source.

### Prerequisites

```bash
sudo apt install python3 git cmake g++ make dotnet-sdk-8.0     # Debian/Ubuntu
```

| what | why | verified against |
|---|---|---|
| Python **3.12** | the analysis and the tests (`src/`) | 3.12.3 |
| **.NET SDK 8** | builds sci-tools, which decompiles the game | 8.0.129 |
| **cmake ≥ 3.16**, a **C++14** compiler, make | builds scicompile, which recompiles the patched scripts | cmake 3.28.3, g++ 13.3 |
| **git** | both vendored trees are cloned at build time, not bundled | 2.43 |

Verified from scratch in a clean `ubuntu:24.04` container: the packages above, the two builds
below, a full pipeline run and the game-independent tests — see the log recipe in
[`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md#clean-room-check).

### One-time build

```bash
git clone https://github.com/katiahayati/lucasartsifier && cd lucasartsifier

# 1. the decompiler. Clones our sci-tools fork into vendor/, builds it, and decompiles
#    GAME into build/ir -- both a .sc source tree and the typed-AST JSON IR.
tools/sci-tools-fork/build.sh /path/to/game

# 2. the compiler: SCICompanion's, ported headless. Its source is cloned and never modified;
#    the port lives beside it in tools/scicompile/{compat,patched}.
git clone --depth 1 https://github.com/icefallgames/SCICompanion vendor/SCICompanion
cmake -S tools/scicompile -B tools/scicompile/build
cmake --build tools/scicompile/build -j
```

Step 1 alone is enough to **analyze** a game (`--report`); step 2 is what turns the derived guards
into patch files. `vendor/` is gitignored — no third-party source and no game data is
redistributed here.

## Run it

You supply your own copy of a game; none is included. The commands run from `src/`:

```bash
cd src
python3 -m pipeline /path/to/game            # decompile -> analyze -> derive -> patch
python3 -m pipeline /path/to/game --report   # analyze only, write nothing
python3 -m pipeline /path/to/game --skip-decompile    # reuse the IR under build/ir
```

Output lands in `build/patch/` as loose patch files:

```bash
cp build/patch/script.* /copy/of/game/    # install
rm  /copy/of/game/script.0*               # revert
```

Loose `script.NNN` files override the mapped resource, so `RESOURCE.MAP` and the volumes are never
modified and the patch reverts by deleting files. Point it at a **copy** of the game, never at
your only one.

## What it produces

Abridged from a real run on LSL2 (`python3 -m pipeline <game>`, 2026-08-14):

```
[2] ANALYZE
    anchors: start rm11, victory [86]  (discovered)
    death signal: global101 == 1001, debug globals: [14, 100]  (derived)
    101 rooms, 27 strongly-connected components, 40 gating registers
    softlocks: 15 items + 1 disjunctive group(s)
      - Sunscreen
      ...
[3] DERIVE
    rm38 -> rm131: (and (gEgo has: 11) (gEgo has: 12) (gEgo has: 14) (gEgo has: 15))
    rm57 -> rm58: (and (gEgo has: 21) (gEgo has: 24) (gEgo has: 25) (gEgo has: 26))
    rm79 -> rm80: (or (gEgo has: 30) (gEgo has: 31))
    rm131 -> rm138: (not (gEgo has: 13))
    rm63: delete `(gEgo put: 21 -1)` (Hair_Rejuvenator)
    verifying against the guarded model...
    fixed 15 + 1 group(s); NEW softlocks introduced: none
[4] PATCH
    compiled 117/118 scripts
    script.000  Main  10790 bytes
    script.057  rm57  2938 bytes
    ...
Done. 10 patch files in build/patch
```

Note `rm131 -> rm138: (not (gEgo has: 13))`. Guards carry negative literals too: the Spinach Dip
is fatal to be holding in rm138, so the fix is to refuse the crossing while you still have it —
placed where you can still throw it overboard, because demanding you drop something you can no
longer drop is a wall, which this project treats as worse than the bug.

It refuses to emit anything if the guards fail verification, or if a script it edited will not
compile.

## How it works, briefly

1. **Decompile** the game binary to a typed control-flow AST (JSON IR).
2. **Abstract-interpret** that AST, composing path conditions into a game graph: guarded movement
   edges, item acquisitions, item losses, register writes. Room art (PIC/VIEW) is read too, since
   some gates are geometric and exist nowhere in the script.
3. **Condense** the graph into strongly-connected components — regions you can wander freely. Only
   the one-way edges between them can strand you, which is what makes the problem finite.
4. **Find strandings**: an item obtainable before a crossing, unavailable after, still needed beyond.
5. **Derive a guard** from the winning region — the condition under which the goal is still
   reachable — and place it at the last point where the player can still comply. Item-wasting dead ends are also neutralized separately, 
   with a *"Just kidding!"* message that prevents you from wasting the needed item and no score penalty.
6. **Recompile and emit.** The patched game is now playable normally (eg, from ScummVM or DOSBox).

Longer version in [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md); per-file map in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); current KQ6 status in
[`docs/KQ6-STATUS.md`](docs/KQ6-STATUS.md); LB2's derivation log in
[`docs/LB2-ORACLE.md`](docs/LB2-ORACLE.md).

## Running the tests

```
python3 tools/run_tests.py              # the whole suite (~21 min with every model cold)
```

[`docs/TESTING.md`](docs/TESTING.md) has the rest: why some checks are RED on purpose, the three
regression nets and the different questions they answer, how to measure a change against the full
output surface before committing it, and how to drive a patched build under ScummVM with nobody at
the keyboard.

## Layout

```
src/                      the analysis (Python 3, standard library only)
src/testdata/             the frozen surfaces: two goldens + the watched pair
tools/run_tests.py        the test runner (docs/TESTING.md)
tools/drive_scummvm.py    play-test a patched build with nobody at the keyboard
tools/kq6_panel_probe.py    ... a driver script: cold start -> KQ6's guard control
tools/sci-tools-fork/     build.sh for our JSON-IR fork of sci-tools               [C#]
tools/scicompile/         headless Linux port of SCICompanion's compiler     [C++, GPL-2.0+]
docs/                     how it works, architecture, testing, per-game status, licensing
docs/reviews/             contextless reviews of tagged releases, verbatim
docs/archive/             superseded plans, kept for their measurements      [see its README]
vendor/                   cloned at build time, never committed (see Install)
```

Per-game configuration is one small file, `src/config.py`. Start and victory rooms are **discovered**
rather than declared; see `src/anchors.py`.

## Future work

- **Required *actions* are not currently modeled** Currently we guard a transition that must not be taken while something it
  needs is still required and no longer obtainable after the crossing. That covers a room edge, a plot flag advancing,
  and an event the player does not control — a whale that swallows you, nightfall, an act break. But we do not model actions that, if not taken, will lead to a death
  later. For example, in King's Quest V you have to throw a shoe at a cat to save a mouse who will later save you from bandits.
- **State explosion in Quest For Glory games** QFG games have SO MUCH going on that the analyzer cannot complete. I suspect we can fix that by abstracting away
  from player stats, combat, and health consumables (rations, etc.), but that work has not been done yet.
- **SCI1.0** We have successfully modeled SCI0 and SCI1.1 games. SCI1.0 (e.g. KQ5) are a weird hybrid and have not been fully modeled yet. Those are next on the list.
- **More games!** While there is no game-specific code in the engine, unfortunately Sierra does ship a lot of game-specific code in each game! That means that every
  new game requires new work to extend the engine. Hopefully at some point this will converge to 0.
- **AGI** AGI games should definitely be included, but that work is not started yet.


## Licensing

MIT, **except `tools/scicompile/` which is GPL-2.0-or-later** — it contains modified SCICompanion source and links its compiler, so it is a derivative work. See 
[`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and [`docs/LICENSING.md`](docs/LICENSING.md).

Built on [sci-tools](https://github.com/sluicebox/sci-tools) (sluicebox, MIT) and
SCICompanion (Philip Fortier, GPL-2.0+). No game data is included in this repository under any terms.
