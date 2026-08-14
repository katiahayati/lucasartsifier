# How it works

Finds **softlocks** in Sierra SCI adventure games — states where the game is still running but no
longer winnable — and emits a patch that prevents them. Validated on *Leisure Suit Larry 2* (1988):
16 softlocks found, 9 patch scripts emitted, and the patched game played to the ending.

```
python -m pipeline /path/to/game        # decompile -> analyse -> derive -> patch
python -m pipeline /path/to/game --report
```

## The problem

Sierra games are not like LucasArts games: you can get stuck. In LSL2, if you forget to get the
sunscreen in LA at the beginning of the game and you board the cruise ship without it, you will
eventually inevitably die because you can't go back to LA from the ship. The goal of this project is to 
prevent you from boarding the cruise ship until you have all the items from LA you will need going forward, 
applied everywhere in the game. We also prevent you from wasting an item prematurely.

It's worth noting that you can still die. We are not aiming to prevent all deaths, mostly because they are often
informative (the game hints at what you should do) and often funny. As long as the death
can be prevented by an action you can still take starting from the screen the death is on we'll let it happen.
So Al Lowe's motto of "Save Early, Save Often!" still applies, with the added benefit that you won't ever have
to replay a huge chunk of the game because you missed something early on.

## The approach

We do all this automatically by
1. Decompiling the game binaries into source .sc files (which have a Lisp-like s-expression syntax).
2. Building an intermediate representation of the source and doing abstract interpretation over it to 
   generate a game graph. For this we look at the source as well as pictures and views.
3. Decomposing the graph into strongly connected components (essentially regions where you can walk freely
   between all the rooms). Note that this is not just geography, but also sometimes conditional gates based
   on game state and/or items obtained.
4. Finding each stranding: items you need in a later component, obtained in an earlier component.
5. Automatically deriving the last cut point we should prevent you from crossing without the item.
6. Injecting code at that point to prevent you from crossing.
7. We automatically find points in the game that let you waste the resource before it's needed, and prevent
   that with a "Just kidding!" message.


## Pipeline

| stage | what it does |
|---|---|
| **decompile** | `sci-tools` reads `RESOURCE.MAP`/`00x` and emits a `.sc` tree plus a typed-AST JSON IR |
| **extract** | walk each room's AST, composing path conditions into guarded movement edges, item acquisitions, register writes |
| **lift** | turn each room's `changeState` switch into an explicit state machine (SCI's cutscene idiom) |
| **analyze** | gate-aware reachability over rooms × registers × items → items that are **required** and **irreversibly missable** |
| **derive** | each stranding becomes a guard condition; each item-destroying dead-end action becomes a removal |
| **patch** | edit the `.sc` sources, recompile, wrap changed scripts as ScummVM loose patch files |

Loose `script.NNN` files in the game folder override the mapped resource, so the original
`RESOURCE.MAP` and volumes are never touched and deleting the files reverts.

## Libraries

| choice | why |
|---|---|
| **sci-tools** (C#, sluicebox) | An excellent SCI decompiler that reconstructs a **typed control-flow AST** rather than emitting text. We forked it to serialise that AST to JSON (~277 lines, additive) instead of throwing it away — the whole analysis depends on having real `if`/`switch`/`send` structure, not reparsed source. |
| **SCICompanion's compiler** (C++) | To emit a patch you must recompile. SCICompanion is the reference SCI compiler; we ported the compiler core to a headless Linux binary. Regenerating a `.sco` proved byte-identical to the original, which is the evidence the port is faithful. |
| **Python 3, standard library only** | The analysis is graph algorithms over a JSON AST — Tarjan, BFS, fixpoints. No numpy, no networkx, no solver bindings. 7,200 lines with zero third-party dependencies, which matters because the fragile parts are the two native toolchains. |

## Clean-room check

The README's install instructions were run from scratch in a container, because a dependency list
written from the machine that already has everything is a guess. Recipe, with the game mounted
read-only (it is never written to, and no game data is redistributed):

```bash
docker run --rm -v "$PWD:/repo:ro" -v "/path/to/game:/game:ro" ubuntu:24.04 bash -c '
  apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y \
      --no-install-recommends python3 git cmake g++ make dotnet-sdk-8.0 ca-certificates
  git clone -q /repo /work/s && cd /work/s
  tools/sci-tools-fork/build.sh /game /work/s/build/ir
  git clone -q --depth 1 https://github.com/icefallgames/SCICompanion vendor/SCICompanion
  cmake -S tools/scicompile -B tools/scicompile/build && cmake --build tools/scicompile/build -j
  cd src && python3 -m pipeline /game --skip-decompile --out /work/s/build'
```

Measured 2026-08-14 on `ubuntu:24.04` against King's Quest IV (Python 3.12.3, .NET 8.0.129,
cmake 3.28.3, g++ 13.3.0):

| step | time |
|---|---|
| decompiler built + game decompiled to `.sc` + JSON IR | 14s |
| SCICompanion cloned, 76 translation units compiled to `scicompile` | 1m54s |
| analysis (`--report`) | 1m20s |
| full run through patch emission | 1m23s → 5 loose patch files |
| the four game-independent test files (49 checks) | seconds |

Two things this caught that the host machine could not: the pipeline is a `src/`-relative module
(`cd src` first — from the repo root `python -m pipeline` fails), and `vendor/SCICompanion` had
never been written down as a step anywhere, having been cloned by hand once, years of commits ago.

## What didn't work

**Syntactic analysis only** The first prototype just considered where items were used and walked back from there.
It worked to a point, but ended up requiring a fatal item, and by being very coarse in its modeling missed many 
required items.

**Fully symbolic model checking** We tried modeling winnability symbolically using nuXmv. That worked well while the
game graph was kept simple and on shallow, local queries, but could not handle the full graph depth. Ultimately the
model checking did not buy us much practically (other than warm fuzzies about correctness), so we retired it.

## Future work

**Encode more games** So far we've only done LSL2. We've checked the basic machinery against King's Quest 4,
and nothing breaks but nothing falls out either. We think that's because KQ4's strandings are more state- and 
item property-based than region-based. Conceptually the same ideas should work (famous last words), but we 
probably need to take more into account when building the game graph.

**Model required actions** For example, in King's Quest 5 you have to throw a shoe at a cat at the right time to let
the mouse save you later. 

**Two constants are still declared per game**: the death signal and the debug globals. Checked
across both games, they share neither index nor shape (LSL2 dies on `global101 == 1001`, KQ4 on
boolean `global127`; the debug flag is LSL2's `global100`/`global111` and KQ4's `global215`).
Deriving a rule from two disagreeing examples would be overfitting, so they are declared — by
index, since the IR carries no symbol table.

We were wrong about KQ4's for a while, and it is worth saying why: we recorded "KQ4 has no debug
global at all" because we had never walked KQ4's `Main`, which is where the flag is read. Unpinned
it would have been the worst kind of landmine — `copyProtect.sc` uses it to warp to any room number
you type, which would have made every room reachable from the start and quietly emptied the whole
analysis.

## Who's "we"?

Katia (human) and Claude (AI). Claude wrote all the code; Katia, uh, supervised, and came up with ideas.
