# Sierra softlock analyzer

**Static analysis for 30-year-old adventure games.** This tool decompiles a Sierra SCI game,
abstract-interprets the decompiled scripts into a graph of guarded room transitions, item
movements and plot-flag writes, finds the **softlocks** — states where the game still accepts
input but victory has quietly become impossible — and derives, verifies, compiles and installs
guards that prevent them. Nothing about any title is declared: the start room, the victory room,
the death signal and the debug flags are all discovered from the game's own code.

Sierra games, unlike LucasArts ones, let you get stuck. Forget the sunscreen in Los Angeles,
board the cruise ship, and you die days later on a raft with no way back. This finds these traps
automatically and blocks the crossing that causes them — at the last moment you can still comply.

**Four games analyzed and play-tested** — Leisure Suit Larry 2 (SCI0, 1988), King's Quest IV (SCI0, 1988), King's Quest VI (SCI1.1, 1992),
and Laura Bow 2 (SCI1.1, 1992) — same engine, no game-specific analysis code.

## Demo

King's Quest IV, patched — the whale, the night clock and seven stranded items, all guarded:

[![Demo: King's Quest IV, patched](https://img.youtube.com/vi/FvspDYQZj34/hqdefault.jpg)](https://youtu.be/FvspDYQZj34)

## The thirty-second version

Abridged from a real run on Leisure Suit Larry 2 (`python3 -m pipeline <game>`):

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

The analyzer discovered the ship boarding as a one-way crossing, derived which items must cross
with you, **re-verified the guarded model to prove the guards introduce no new softlocks**, and
recompiled the touched scripts into Sierra's own loose-patch format.

Note `rm131 -> rm138: (not (gEgo has: 13))`. Guards carry negative literals too: the Spinach Dip
is fatal to be *holding* in rm138, so the fix is to refuse the crossing while you still have it —
placed where you can still throw it overboard, because demanding you drop something you can no
longer drop is a wall, which this project treats as worse than the bug. The pipeline refuses to
emit anything if the guards fail verification, or if a script it edited will not compile.

A patched game plays normally — the patch mechanism is how Sierra shipped its own bug fixes, and
the originals are never modified (delete the patch files to revert). You can set the guard
behavior in-game: **Full** prevents every dangerous action; **Lite** prevents it once, then
allows it with a warning; **Off** turns the guards off.

## What counts as a softlock? (or: Caveat Player)

**Some deaths are deliberately left in** — the ones you can still avoid from where you are. The
analysis distinguishes *unwinnable states* from *avoidable deaths* by reachability, not by death
conditions. In Leisure Suit Larry 2, walking onto the KGB beach without the full disguise kills
you. Some pieces of the disguise exist only on the cruise ship, so the analyzer refuses to let
you leave the ship without them. But the rest is obtainable on the island — from the very place
the death occurs — so that death stays in: it is how Sierra games hint at what you need to do.
As Al Lowe says, "Save Early, Save Often!"

## Status

**Four games done, spanning the engine's two major eras (SCI0 1988 → SCI1.1 1992), with nothing
declared per title** — start room, victory room, death signal and debug flags are all derived
from each game's own code.

| game | engine | found → guarded | what it taught the engine |
|---|---|---|---|
| **Leisure Suit Larry 2** (1988) | SCI0 | 15 items + 1 group → 12/12 sites | the Spinach Dip: fatal to *carry*, so the guard is a negative literal, placed while you can still ditch it |
| **King's Quest IV** (1988) | SCI0 | 7 items → 5/5 | the real-time night clock; the whale — random events guarded by arming them only when survivable |
| **King's Quest VI** (1992) | SCI1.1 | 18 items + 1 group → 24/26 | two endings multiply everything: exclusive castle routes, the Realm's carry-in/out, the wedding fuse (the 2 skips are deliberate, pinned — one is a trade you're *meant* to make) |
| **Laura Bow 2** (1992) | SCI1.1 | 10 items → 5/5 | the act structure: the plot clock is a register, act breaks are one-way, demands ride the act-flip interceptor |
| **King's Quest V** (1990) | SCI1-middle | *in progress (`kq5` branch)* | the market: consumables with more consumers than copies — detection becomes a matching problem |

## How it works, briefly

1. **Decompile** the game binary to a typed control-flow AST (JSON IR).
2. **Abstract-interpret** that AST, composing path conditions into a game graph: guarded movement
   edges, item acquisitions, item losses, register writes. Room art (PIC/VIEW) and obstacle
   polygons are read too, since some gates are geometric and exist nowhere in the script.
3. **Condense** the graph into strongly-connected components — regions you can wander freely.
   Only the one-way edges between them can strand you, which is what makes the problem finite.
4. **Find strandings**: an item obtainable before a crossing, unavailable after, still needed beyond.
5. **Derive a guard** from the winning region — the condition under which the goal is still
   reachable — and place it at the last point where the player can still comply. Item-wasting
   dead ends are neutralized separately, with a *"Just kidding!"* message that prevents you from
   wasting the needed item, and no score penalty.
6. **Recompile and emit.** The patched game is now playable normally (e.g. in ScummVM or DOSBox).

Longer version in [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md); per-file map in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); current KQ6 status in
[`docs/KQ6-STATUS.md`](docs/KQ6-STATUS.md); LB2's derivation log in
[`docs/LB2-ORACLE.md`](docs/LB2-ORACLE.md).

### The toolchain

Steps 1 and 6 stand on two excellent existing projects, driven headless:

- **Decompilation** is [sci-tools](https://github.com/sluicebox/sci-tools) (sluicebox, MIT).
  We maintain [a fork](https://github.com/katiahayati/sci-tools) whose `json-ir` branch adds a
  second emitter beside the `.sc` source output: the typed control-flow AST as JSON, which is
  what the analysis consumes. The decompilation logic itself is untouched.
- **Compilation** is [SCICompanion](https://github.com/icefallgames/SCICompanion)'s script
  compiler (Philip Fortier, GPL-2.0+), which we ported to build and run headless on Linux —
  `tools/scicompile/` is a small CLI plus a compatibility layer that replaces the MFC/Windows
  surface, calling the real parser, class browser, resource map and code generator
  (`GenerateScriptResource`). The vendor tree is cloned at build time and never edited; a
  handful of files are patched as a build step for MSVC-only constructs, with every change
  documented in [`tools/scicompile/BUILD_NOTES.md`](tools/scicompile/BUILD_NOTES.md). Each
  guarded script the pipeline emits is compiled by the same code paths SCICompanion uses in
  its IDE, then wrapped in Sierra's loose-patch header.

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

- **Required *actions* are not currently modeled.** Currently we guard a transition that must not
  be taken while something it needs is still required and no longer obtainable after the crossing.
  That covers a room edge, a plot flag advancing, and an event the player does not control — a
  whale that swallows you, nightfall, an act break. But we do not model actions that, if not
  taken, lead to a death later. For example, in King's Quest V you have to throw a shoe at a cat
  to save a mouse who will later save you from bandits.
- **State explosion in Quest For Glory games.** QFG games have SO MUCH going on that the analyzer
  cannot complete. I suspect we can fix that by abstracting away from player stats, combat, and
  health consumables (rations, etc.), but that work has not been done yet.
- **SCI1.0 / SCI1-middle.** SCI0 and SCI1.1 are modeled. King's Quest V — the weird hybrid in
  between — is in progress on the `kq5` branch and most of the way there.
- **Full end-to-end playtesting.** All four games have been extensively tested where patched, but none has been played end to 
end yet. Doing that might uncover bugs.
- **More games!** There is no game-specific code in the engine, but Sierra shipped a lot of
  game-specific code in each game, so every new title has so far required extending the analysis.
  Hopefully at some point this converges to zero.
- **AGI.** AGI games should definitely be included, but that work is not started yet.

## Licensing

MIT, **except `tools/scicompile/` which is GPL-2.0-or-later** — it contains modified SCICompanion source and links its compiler, so it is a derivative work. See 
[`LICENSE`](LICENSE), [`NOTICE`](NOTICE), and [`docs/LICENSING.md`](docs/LICENSING.md).

Built on [sci-tools](https://github.com/sluicebox/sci-tools) (sluicebox, MIT) and
SCICompanion (Philip Fortier, GPL-2.0+). No game data is included in this repository under any terms.
