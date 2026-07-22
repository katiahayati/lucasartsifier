# Sierra softlock analyzer

Finds **softlocks** in Sierra SCI adventure games — states where the game still accepts input but
victory has already become impossible — and emits a patch that prevents them.

Sierra games, unlike LucasArts ones, let you get stuck. Forget the sunscreen in Los Angeles, board
the cruise ship, and you die days later on the raft with no way back. This finds every such trap
automatically and blocks the crossing that causes it.

**Status:** validated on *Leisure Suit Larry 2* (1988, SCI0) — **16 softlocks found, 9 patch scripts
emitted, and the patched game played through to the ending.**

## Run it

```bash
tools/sci-tools-fork/build.sh          # one time: build the decompiler
cmake --build tools/scicompile/build   # one time: build the compiler

python -m pipeline /path/to/game            # decompile -> analyse -> derive -> patch
python -m pipeline /path/to/game --report   # analyse only, write nothing
```

You supply your own copy of a game; none is included. Output lands in `build/patch/` as ScummVM
loose patch files:

```bash
cp build/patch/script.* /copy/of/game/    # install
rm  /copy/of/game/script.0*               # revert
```

Loose `script.NNN` files override the mapped resource, so `RESOURCE.MAP` and the volumes are never
modified and the patch reverts by deleting files.

## What it produces

```
[2] ANALYSE   anchors: start rm10, victory [86]  (discovered)
              101 rooms, 27 strongly-connected components, 17 gating registers
              softlocks: 15 items + 1 disjunctive group
[3] DERIVE    rm57 -> rm58: (and (has: 21) (has: 24) (has: 25) (has: 26))
              rm79 -> rm80: (or (has: 30) (has: 31))
              verifying against the guarded model... NEW softlocks introduced: none
[4] PATCH     compiled 117/118 -> 9 loose patch files
```

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
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md); test plan in [`docs/TEST-PLAN.md`](docs/TEST-PLAN.md).

## Layout

```
src/                      the analysis (Python 3, standard library only)
tools/sci-tools-fork/     patch adding JSON-IR output to sci-tools           [C#]
tools/scicompile/         headless Linux port of SCICompanion's compiler     [C++, GPL-2.0+]
docs/                     how it works, architecture, test plan, licensing
```

Per-game configuration is one small file, `src/config.py`. Start and victory rooms are **discovered**
rather than declared; see `src/anchors.py`.

## Limits

- **One game is genuinely validated.** KQ4 runs end to end (110 rooms) and now reports findings of
  its own — stranded items, a wasteable one, finite items spent by ordinary use — several of them
  confirmed against the player's own knowledge of the game. But it has never been play-tested, and
  play-testing is the only oracle a new title has.
- **Required *actions* are out of scope** (KQ5's throw-the-shoe-at-the-cat). What is in scope has
  turned out to be one rule rather than several: a transition must not be taken while something it
  needs is still required and no longer obtainable. That covers a room edge, a plot flag advancing,
  and an event the player does not control — a whale that swallows you, nightfall.
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
