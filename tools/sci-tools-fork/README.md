# sci-tools fork — JSON IR emitter (Plan A / A2 front-end)

Per `ENGINE-DIRECTION.md` Plan A: the front-end is sluicebox's **sci-tools** (C#), which
builds a full **typed control-flow AST** from SCI bytecode. Stock sci-tools discards that
AST after emitting `.sc` text. Our `--json` flag serializes it losslessly to
`<game>.ir.json`, which our Python extraction consumes (the A2 hybrid seam).

**Our changes live in a fork: https://github.com/katiahayati/sci-tools, branch `json-ir`**
(MIT, as upstream). They used to be a build-time patch; that stopped scaling once it held two
independent changes, and because `vendor/` is gitignored an edit made there could silently
vanish on the next build — a rebuild would quietly emit an IR missing whatever was lost, with
no test failing. Commits cannot vanish that way.

Two commits, deliberately separable so either could go upstream on its own:
1. `--json` — the AST-as-IR emitter.
2. `exports` — the per-script export table (see below).

`build.sh` clones the fork and checks out the pinned commit; no patch step. Upstream stays
wired up for syncing:

```
git -C vendor/sci-tools fetch upstream
git -C vendor/sci-tools rebase upstream/main      # then re-pin PIN= in build.sh
```

The IR, per script: `locals` (script 0's = globals) with init values; `objects`
(class/instance, species, super, `properties` [selector+value], `methods`); `exports`;
`procedures`.

`exports` is index -> object name (null for a code export, keeping indexes aligned).
`(ScriptID <script> <n>)` -- SCI's cross-script reference, and how a region or a cutscene
Script is reached from another script -- names the *nth export*, which does **not** follow
object order: KQ6's `(ScriptID 80 0)` is `rgCastle`, its `objects[2]`. Without this table the
reference is unresolvable, so every `setScript: (ScriptID ...)` arming (231 of them in KQ6)
lost its guard.
Each method/procedure carries its typed AST (`Switch`/`Case`/`If`/`Loop`/`Send`/
`SendMessage`/`Assignment`/`Variable`/`Property`/`Class`/`Number`/`Said`/…). Identifiers
are bytecode-canonical: globals/locals by **index**, selectors by number (the `selectors`
table resolves names). Friendly global names (`gCurrentStatus` = global 101) are a
sci-tools *annotation* layer, not applied here — the extractor maps indices→names.

## What the fork changes (all additive — without `--json`, behaviour is stock)
- `SCI/Decompile/JsonExport.cs` (new): the AST→JSON serializer (dependency-free).
- `SCI/Decompile/Decompiler.cs`: `public bool EmitJson` + the emit call in `Run`.
- `Snuffer/Options.cs`, `Snuffer/Snuffer.cs`: the `--json` CLI flag.

## Build & run (`build.sh`)
Clones **our fork** at the pinned commit into `vendor/sci-tools`, builds Snuffer (needs the
.NET 8 SDK), and decompiles the game to an IR. Requires the original game resources
(`RESOURCE.MAP`/`RESOURCE.00x`), not the `.sc` tree.

`vendor/` is gitignored, so treat the clone as disposable build output: make changes on the
fork and re-pin, never as uncommitted edits in `vendor/`.
