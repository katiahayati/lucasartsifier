# Architecture: what every file does, and how they wire together

~7,200 lines of Python (standard library only) over two native toolchains. Entry point:

```
python -m pipeline /path/to/game          # decompile -> analyse -> derive -> patch
```

## Dataflow

```
  game resources (RESOURCE.MAP + RESOURCE.00x)
        |
        |  vendor/sci-tools + tools/sci-tools-fork/json-ir.patch   [C#]
        v
  build/ir/  <game>.ir.json  +  src/*.sc
        |
   ir.py ........................ load the typed AST, index scripts/objects/methods
        v
   extract.py .................. walk each AST, compose PATH CONDITIONS
        |                         -> movement edges, item get/put, register writes, guards
        +--> guard_ast.py ........ the Pred/GAnd/GOr/GNot types every stage shares
        v
   machine.py .................. lift `changeState` switches into explicit state machines
   compile.py .................. per-state ops; cue carry; chain compression
        v
   opmodel.py ................. OpEmitter: assembles the whole operational model
        |                         (rooms, machines, handlers, registers, cutscene sets)
        +--> control_oracle.py ... positional gates read from PIC/VIEW art
        |      +--> sci_gfx.py ... decode pictures/views
        |      +--> sci_resource.py  read + decompress SCI0 resources
        v
   anchors.py ................... DISCOVER start room and victory rooms
   missability.py ............... gate-aware reachability -> REQUIRED and MISSABLE items
        +--> scc_core.py ......... SCC condensation, edge_strandings, the report view
        v
   guards.py .................... derive guard conditions from the WINNING REGION
        v
   patcher.py ................... edit .sc sources, compile, emit ScummVM loose patches
        +--> trigger.py .......... find the CONTROLLABLE trigger to place a guard on
        |      +--> sexpr.py ..... s-expression reader for .sc source
        +--> tools/scicompile ..... [C++] headless SCICompanion compiler, --sco / --all
        v
  build/patch/ script.NNN
```

## Files

### Entry points
| file | lines | role |
|---|---:|---|
| `pipeline.py` | 173 | The whole shebang: decompile → analyse → derive → patch. `--report` stops before writing. Refuses to emit if verification fails or an edited script won't compile. |
| `patcher.py` | 463 | Turns specs into bytes: assembles a compilable project, applies edits, runs the compiler, wraps changed scripts as `script.NNN`. Decides *nothing* about what to patch. |
| `missability.py` | 817 | The detector, and the analysis hub. Gate-aware movement model, pure-sink detection, disjunctive groups. Also `load()`, which most tools call. |
| `guards.py` | 467 | The synthesiser: guard conditions, prohibition relocation, sink remedies, and `verify()` against the guarded model. |

### Front end (game → model)
| file | lines | role |
|---|---:|---|
| `ir.py` | 137 | Loads `<game>.ir.json`; indexes scripts, objects, methods, procedures. Thin. |
| `extract.py` | 368 | The real extractor. Walks each typed AST composing path conditions into guarded edges, acquisitions, drops, register writes. Room identity comes from *inheritance* from the `Rm`/`Room` class. |
| `machine.py` | 339 | Lifts SCI's `changeState` switch idiom into an explicit state machine — the construct that holds every cutscene, and where most gates hide. |
| `compile.py` | 390 | Per-state operations: cross-state cue carry (SCI's `cycles`/`seconds` semantics), effect-free chain compression. |
| `opmodel.py` | 964 | `OpEmitter` — assembles everything into one operational model: rooms, machines, handler gets/drops/writes, register domains, cutscene classification. Also still emits SMV, which is vestigial (see below). |
| `guard_ast.py` | 64 | `Pred / GAnd / GOr / GNot`. Pure data, no dependencies — deliberately, so nothing needs the old front end to talk about guards. |
| `config.py` | 115 | Per-game config — now paths and overrides only. Anchors, `death_signal` and `debug_globals` are all DISCOVERED; see `vocab.py`. |

### Analysis
| file | lines | role |
|---|---:|---|
| `scc_core.py` | 198 | Tarjan SCC condensation, `edge_strandings` (the canonical "what does crossing this edge strand" rule), and the report view. Front-end agnostic: operates on a generic (edges, sources, required, goal) interface. |
| `anchors.py` | 142 | Discovers start and victory rooms. Victory = terminal + reachable + never fatal; start = walk the graph roots through input-less cutscenes to the first playable room, widest reach wins. |
| `control_oracle.py` | 620 | Derives positional gates from the game's *art*: reads the PIC control map to decide which pixels the ego may stand on. Some gates exist nowhere in the script. |
| `sci_gfx.py` | 306 | Decodes SCI0 pictures and views for the above. |
| `sci_resource.py` | 243 | Reads `RESOURCE.MAP`/volumes and decompresses (LZW, Huffman). Also how we read the game's own message strings. |

### Patch emission
| file | lines | role |
|---|---:|---|
| `trigger.py` | 279 | Finds the **controllable trigger** for a guard — the handler that *starts* a cutscene, never the `newRoom:` at its tail — and wraps the whole enclosing clause so side effects cannot fire ahead of a refusal. |
| `sexpr.py` | 191 | S-expression reader for `.sc` source. Only the patch path needs source text; the analysis never touches it. |

### Tests (196)
`test_gate_aware` (35) · `test_control_oracle` (32) · `test_everything` (25) · `test_abstractions` (20) ·
`test_guards` (17) · `test_scopes` (55) · `test_anchors` (10) · `test_walkers` (2).  Almost all on synthetic inputs —
end-to-end scoring lives in `python -m missability` and `python -m guards`.

### Native
| path | language | role |
|---|---|---|
| `tools/sci-tools-fork/` | C# patch | Adds `--json` to sci-tools so its typed AST is serialised instead of discarded. Built by `build.sh`. |
| `tools/scicompile/` | C++ | Headless Linux port of SCICompanion's compiler. `--sco` builds interface files from source + compiled resources; `--all` compiles everything. **GPL-2.0-or-later** — see NOTICE. |

## Two things worth knowing

**`opmodel.py` used to be called `smv_emit3.py`.** It began as an SMV emitter for nuXmv model
checking; that direction was measured and largely abandoned (both query directions time out at
600s against the real goal). What survived is `OpEmitter` — the operational model every analysis
reads — and the SMV emission is now a vestigial side-door used for shallow waypoint queries.
This section used to argue the rename wasn't worth a dozen import changes. It was.

Three siblings carried version numbers from an early parallel branch and no longer do:
`extract2` → `extract`, `machine2` → `machine`, `compile2` → `compile`.

**The analysis never reads `.sc` text.** Everything upstream of `patcher.py` works from the JSON IR.
Only patch *emission* touches source, via `sexpr.py`/`trigger.py`. That separation is why swapping
decompilations mid-project was survivable, and why the two-tree seam (analysing one tree while
patching another) was so easy to introduce by accident — and so damaging.
