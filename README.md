# Sierra softlock analyzer

Finds **softlocks** in Sierra SCI adventure games — states where the game still accepts input but
victory has already become impossible — and emits a patch that prevents them.

Sierra games, unlike LucasArts ones, let you get stuck. Forget the sunscreen in Los Angeles, board
the cruise ship, and you die days later on the raft with no way back. This finds every such trap
automatically and blocks the crossing that causes it.

## Status

Four games run end to end. Nothing about a title is declared: the start room, the victory room,
the death signal and the debug flag are all derived from the game's own code.

| game | engine | model | findings | edits placed | played |
|---|---|---|---|---|---|
| **Leisure Suit Larry 2** (1988) | SCI0 | 101 rooms, 27 components | 15 items + 1 group | 12 of 12 | ✅ patched game played to the ending |
| **King's Quest IV** (1988) | SCI0 | 110 rooms, 15 components | 7 items | 5 of 5 | — never play-tested |
| **King's Quest VI** (1992) | SCI1.1 | 86 rooms, 15 components | 18 items + 1 group | 24 of 26 | ✅ in-game guard control confirmed in play |
| **Laura Bow 2: The Dagger of Amon Ra** (1992) | SCI1.1 | 78 rooms, 26 components | 10 items | 5 of 5 | ✅ act-break guards confirmed in play |

"Findings" is every detector's verdict unioned per item — the frozen surface `src/snapshot.py`
writes. The `softlocks:` line a pipeline run prints is narrower: it counts three of the seven
detectors, so KQ4 reports 5 there against the 7 here, the missing two (the Diamond Pouch and the
Fishing Pole) being register-flip strandings — sealed behind a plot flag rather than behind a
door. "Edits placed" counts the guard and sink sites the patcher actually landed. KQ6's missing
two are the suite's one deliberate red — a shared-dispatcher seam and a trade-shaped sink, both
with their reasons written down rather than quietly dropped.

LSL2 and KQ4 are **golden**: their full output surface is frozen byte-for-byte, and a change to it
means the change is wrong until a human says otherwise. KQ6 and LB2 are **watched**: their surfaces
are frozen too, but they are still moving, so a change is reported and then read row by row.

A patched game lets the player set guard behaviour in-game — **Full** (every guard refuses),
**Lite** (each site refuses once, then warns and lets you through), **Off** — from the SCI0 menu
bar or KQ6's settings panel. See [`docs/GUARD-MODES.md`](docs/GUARD-MODES.md).

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

Step 1 alone is enough to **analyse** a game (`--report`); step 2 is what turns the derived guards
into patch files. `vendor/` is gitignored — no third-party source and no game data is
redistributed here.

## Run it

You supply your own copy of a game; none is included. The commands run from `src/`:

```bash
cd src
python3 -m pipeline /path/to/game            # decompile -> analyse -> derive -> patch
python3 -m pipeline /path/to/game --report   # analyse only, write nothing
python3 -m pipeline /path/to/game --skip-decompile    # reuse the IR under build/ir
```

Output lands in `build/patch/` as ScummVM loose patch files:

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
[2] ANALYSE
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
   reachable — and place it at the last point where the player can still comply.
6. **Recompile and emit.** Item-wasting dead ends are neutralised separately, with a *"Just
   kidding!"* message and no score penalty.

Longer version in [`docs/HOW-IT-WORKS.md`](docs/HOW-IT-WORKS.md); per-file map in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); current KQ6 status in
[`docs/KQ6-STATUS.md`](docs/KQ6-STATUS.md); LB2's derivation log in
[`docs/LB2-ORACLE.md`](docs/LB2-ORACLE.md).

## Running the tests

```
python3 tools/run_tests.py              # the whole suite (~21 min with every model cold)
python3 tools/run_tests.py toll scopes  # only files matching these names
```

Each `src/test_*.py` is also a standalone script you can run directly. Files that need no game
at all — `test_walkers`, `test_abstractions`, `test_guards`, `test_deletion_soundness` — run
anywhere; the rest need the IR of the game they are about.

**Some checks are RED on purpose, and the runner is built around that.** A test that asserts
known-wrong behaviour would be worse than no test, so a known limitation is written as a *failing*
check with its reason recorded in `KNOWN_RED` at the top of the runner. The suite therefore exits
0 only when the failing set is **exactly** the declared one — which means a red check that starts
*passing* is also a failure, reported as "a gap was closed, promote it". Currently **one**: two of
KQ6's guard specs have no placement site (`test_sci11_patch.py`).

Three nets sit behind that, and they are not the same kind of thing:

* `test_golden.py` — the **full** output surface of LSL2 and KQ4, frozen in
  `src/testdata/*.golden.json`. A failure means the change is wrong. Re-blessing needs sign-off.
* `test_watched_surface.py` — the same surface for KQ6 and LB2, in
  `src/testdata/watched_surfaces.json`. A change is allowed, but it must be read row by row and
  then deliberately refreshed.
* `test_kq4_ground_truth.py`, `test_kq6_ground_truth.py`, `test_lb2_ground_truth.py` — per-game
  oracles of user-confirmed verdicts, derived from the games and from hint books rather than from
  our own output. A **drop is a regression**; an **addition is treated with suspicion**. Neither
  column may be edited without sign-off.

The first two answer "did anything move?"; the third answers "is what we emit right?".

### Play-testing a build without playing it

The suite checks the *emitted source*; it cannot see what the patched game draws. That gap
cost four wrong cuts at KQ6's in-game guard control, each shipped on a theory because
checking one meant asking someone to play. It does not:

```
python3 -m venv .venv-x && .venv-x/bin/pip install python-xlib pillow
.venv-x/bin/python tools/drive_scummvm.py --game <COPY of the patched game> --id kq6 \
    --script tools/kq6_panel_probe.py          # -> build/kq6_panel_probe/*.png
```

ScummVM opens a real window, XTEST drives the mouse and keyboard, and the window's pixels
are read off the X server. This is the only part of the project that wants third-party Python
packages, and it is optional. Point `--game` at a **copy**, never at the installed game.

## Layout

```
src/                      the analysis (Python 3, standard library only)
src/testdata/             the frozen surfaces: two goldens + the watched pair
tools/run_tests.py        the test runner (see above)
tools/drive_scummvm.py    play-test a patched build with nobody at the keyboard
tools/kq6_panel_probe.py    ... a driver script: cold start -> KQ6's guard control
tools/sci-tools-fork/     build.sh for our JSON-IR fork of sci-tools               [C#]
tools/scicompile/         headless Linux port of SCICompanion's compiler     [C++, GPL-2.0+]
docs/                     how it works, architecture, per-game status, licensing
docs/reviews/             contextless reviews of tagged releases, verbatim
docs/archive/             superseded plans, kept for their measurements      [see its README]
vendor/                   cloned at build time, never committed (see Install)
```

Per-game configuration is one small file, `src/config.py`. Start and victory rooms are **discovered**
rather than declared; see `src/anchors.py`.

## Limits

- **Play-testing is the only oracle a new title has.** LSL2's patch was played to the ending;
  KQ6's and LB2's guards were confirmed at the sites that mattered; KQ4 has never been played at
  all, golden surface and all. Static verification proves the guards close every *detected*
  softlock and introduce none — it has nothing to say about what detection missed.
- **Required *actions* are out of scope** (KQ5's throw-the-shoe-at-the-cat). What is in scope has
  turned out to be one rule rather than several: a transition must not be taken while something it
  needs is still required and no longer obtainable. That covers a room edge, a plot flag advancing,
  and an event the player does not control — a whale that swallows you, nightfall, an act break.
- **Some deaths are deliberately left in** — the ones you can still avoid from where you are. Walk
  onto the KGB beach without the disguise and you die; we allow that, because every piece of the
  disguise is still reachable from that screen. Reach the raft without sunscreen and you also die,
  but by then the sunscreen is hours behind you in Los Angeles — so we refuse the crossing that
  stranded it, and refuse it at the cruise ship. The test is the same one used for softlocks: is
  what you need still obtainable? Whether failing it kills you or merely leaves you stuck does not
  change the answer or the fix. Al Lowe's "Save Early, Save Often!" still applies.
- **Nothing game-specific is declared any more** — not the start room, the victory room, the death
  signal, or the debug flag. `config.py` holds paths and optional overrides. The death signal is the
  global the Game class tests on its way to offering Restore/Restart/Quit; the debug flag is the one
  a menu toggles with `^=`. Both reproduce the values we used to hand-write. That matters more than
  it sounds: KQ4's debug flag lets the copy-protection screen warp to any room you type, and
  unpinned it would make every room reachable from the start.
- **Five defects were found by playing** that no static check caught — misleading refusal text, a
  self-contradicting message, an infinite loop, and a whole class of item destruction living in a
  globally-active script. Verification proved the guards closed every *detected* softlock and
  created none; it had nothing to say about what we failed to detect.

## Licensing

MIT, **except `tools/scicompile/` which is GPL-2.0-or-later** — it contains modified SCICompanion
source and links its compiler, so it is a derivative work. See [`LICENSE`](LICENSE),
[`NOTICE`](NOTICE), and [`docs/LICENSING.md`](docs/LICENSING.md).

Built on [sci-tools](https://github.com/sluicebox/sci-tools) (sluicebox, MIT) and
SCICompanion (Philip Fortier, GPL-2.0+). No game data is included in this repository under any terms.
