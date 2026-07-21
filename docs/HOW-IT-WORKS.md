# How it works

Finds **softlocks** in Sierra SCI adventure games — states where the game is still running but no
longer winnable — and emits a patch that prevents them. Validated on *Leisure Suit Larry 2* (1988):
16 softlocks found, 9 patch scripts emitted, and the patched game played to the ending.

```
python -m pipeline /path/to/game        # decompile -> analyse -> derive -> patch
python -m pipeline /path/to/game --report
```

## The problem

An adventure game softlock is not a crash. You wander a fully-functional world that can no longer
be completed, usually because an item you needed is behind a door that only opens one way. The
classic LSL2 case: you parachute onto an island without the knife, and nothing in the game will
ever tell you.

Detecting this means answering *"is the goal still reachable?"* over a program's whole state space
— rooms, inventory, hundreds of flags, and the interpreter's own control flow.

## Pipeline

| stage | what it does |
|---|---|
| **decompile** | `sci-tools` reads `RESOURCE.MAP`/`00x` and emits a `.sc` tree plus a typed-AST JSON IR |
| **extract** | walk each room's AST, composing path conditions into guarded movement edges, item acquisitions, register writes |
| **lift** | turn each room's `changeState` switch into an explicit state machine (SCI's cutscene idiom) |
| **analyse** | gate-aware reachability over rooms × registers × items → items that are **required** and **irreversibly missable** |
| **derive** | each stranding becomes a guard condition; each item-destroying dead-end action becomes a removal |
| **patch** | edit the `.sc` sources, recompile, wrap changed scripts as ScummVM loose patch files |

Loose `script.NNN` files in the game folder override the mapped resource, so the original
`RESOURCE.MAP` and volumes are never touched and deleting the files reverts.

## The ideas that actually mattered

**Reachability, not simulation.** Explicit state search explodes: 21 items alone is 2²¹ subsets. But
adventure maps are dominated by *irreversibility*. Condense the room graph into strongly-connected
components — inside one you can wander freely, so *which* items you hold doesn't matter — and state
only carries across the one-way edges between them. That turns a state-space problem into a small
DAG plus a per-edge question: *does crossing this strand something the goal still needs?*

**Gate-aware movement.** The naive room graph ignores guards, so it composes an edge that *sets*
`gCurrentStatus := 14` with one that *requires* `== 7`, welding unrelated regions into one giant
component and hiding every stranding inside it. Modelling the registers fixes it — but jointly
promoting all 19 gating registers explodes past 4,000,000 states. Keeping them as **independent
projections** costs 3,679 states total, and is sound: a genuinely walkable path is walkable in every
projection, so intersecting the answers only ever removes spurious movement. Linear, not
exponential, and each register added can only sharpen the result.

**Guards derived from the winning region.** A guard's condition is the DNF over the paths from
which the goal is *still reachable*, keeping item literals — positive and negative. This is where
an earlier attempt had failed catastrophically: it read requirements syntactically ("this room
mentions item 13") and emitted a guard **forcing** the fatal Spinach_Dip, making the game
unwinnable. The same edge, computed semantically, produces a guard that **forbids** it.

**Disjunction is not conjunction.** Rival handlers arming the same gate are alternatives. rm81
accepts `throw ash` **or** `throw sand`; intersecting them says "free", unioning says "needs both",
and both are wrong. Keeping a DNF and failing an edge only when *every* alternative is blocked is
what lets the analysis say losing either is survivable while losing both is fatal.

**Placement is a separate problem from derivation.** A guard belongs at the last edge where the
player can still comply — which is not always where the condition is tested. The dip prohibition
had to move twice: off rm138's gate (you can no longer ditch it there) and off its own droppability
frontier (an automatic cutscene, nothing to refuse), landing on rm38 → rm131. And guards go on the
*controllable trigger* — the handler that starts a cutscene, never the `newRoom:` at its tail,
which would hang the game mid-animation.

**Anchors are discoverable.** Start and victory rooms were the last hand-declared values. Victory =
terminal + reachable + never raises the death signal (deaths are terminal too — excluding them is
the whole trick). Start = walk from the graph's roots through input-less cutscene rooms to the first
playable one, preferring the widest forward reach. On LSL2 the derived pair reproduces the
hand-tuned pair exactly; on KQ4 it independently picks the room a human had proposed.

## Libraries, and why

| choice | why |
|---|---|
| **sci-tools** (C#, sluicebox) | The only SCI decompiler that reconstructs a **typed control-flow AST** rather than emitting text. We forked it to serialise that AST to JSON (~277 lines, additive) instead of throwing it away — the whole analysis depends on having real `if`/`switch`/`send` structure, not reparsed source. |
| **SCICompanion's compiler** (C++) | To emit a patch you must recompile. SCICompanion is the reference SCI compiler; we ported the compiler core to a headless Linux binary. Regenerating a `.sco` proved byte-identical to the original, which is the evidence the port is faithful. |
| **Python 3, standard library only** | The analysis is graph algorithms over a JSON AST — Tarjan, BFS, fixpoints. No numpy, no networkx, no solver bindings. ~7,500 lines with zero third-party dependencies, which matters because the fragile parts are the two native toolchains. |
| **nuXmv** (symbolic model checker) | **Evaluated and largely rejected.** Encoding the game as a transition system and asking IC3 for winnability is the textbook approach, and it does prove local requirements fast (~5s). But against the real goal both directions time out at 600s — including the "cheap" one we predicted would be fast. Kept only for shallow waypoint queries. The structural analysis solves the whole problem in 23s. |
| **ScummVM** | The only oracle that could confirm any of it. See below. |

## Honest limits

**Validated on one game.** LSL2 is the only title where the results have been checked against
ground truth and play. KQ4 now runs end to end (110 rooms) and reports zero stranded-item
softlocks, consistent with an earlier independent analysis — but nobody has played it, and its
discovered victory rooms disagree with a hand-read ending.

**Two constants are still declared per game**: the death signal and the debug globals. Checked
across both games, they share neither index nor shape (LSL2 dies on `global101 == 1001`, KQ4 on
boolean `global127`; KQ4 has no debug global at all). Deriving a rule from two disagreeing examples
would be overfitting, so they are declared — by index, since the IR carries no symbol table.

**Only one softlock class is handled.** Item stranding, plus item-destroying dead-end actions.
Positional deaths (stepping into a trigger without the right disguise) and required *actions*
(KQ5's throw-the-shoe-to-save-the-mouse) are out of scope.

**Five defects were found by playing, and no static check we wrote could have caught any of them.**
Two misleading refusal messages; a remedy that left the game insisting a still-held item was gone; a
guard that looped forever printing "You made it!"; and item destruction in `Main`, active on every
screen, that a room-keyed detector was structurally blind to. Verification could prove the guards
closed every detected softlock and created none. It had nothing to say about whether the game lied
to the player, and nothing to say about what we had failed to detect.

That last point is the real lesson. The analysis was sound in the sense it claimed to be, and still
wrong in ways only a person walking through a 1988 comedy game could find.
