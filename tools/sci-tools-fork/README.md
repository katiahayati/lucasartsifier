# sci-tools fork — JSON IR emitter (Plan A / A2 front-end)

Per `ENGINE-DIRECTION.md` Plan A: the front-end is sluicebox's **sci-tools** (C#), which
builds a full **typed control-flow AST** from SCI bytecode. Stock sci-tools discards that
AST after emitting `.sc` text. `json-ir.patch` adds a `--json` flag that serializes it
losslessly to `<game>.ir.json`, which our Python extraction consumes (the A2 hybrid seam).

The IR, per script: `locals` (script 0's = globals) with init values; `objects`
(class/instance, species, super, `properties` [selector+value], `methods`); `procedures`.
Each method/procedure carries its typed AST (`Switch`/`Case`/`If`/`Loop`/`Send`/
`SendMessage`/`Assignment`/`Variable`/`Property`/`Class`/`Number`/`Said`/…). Identifiers
are bytecode-canonical: globals/locals by **index**, selectors by number (the `selectors`
table resolves names). Friendly global names (`gCurrentStatus` = global 101) are a
sci-tools *annotation* layer, not applied here — the extractor maps indices→names.

## What the patch changes (277 lines, all additive)
- `SCI/Decompile/JsonExport.cs` (new): the AST→JSON serializer (dependency-free).
- `SCI/Decompile/Decompiler.cs`: `public bool EmitJson` + the emit call in `Run`.
- `Snuffer/Options.cs`, `Snuffer/Snuffer.cs`: the `--json` CLI flag.

## Build & run (`build.sh`)
Clones sci-tools at the pinned commit into `vendor/sci-tools`, applies the patch, builds
Snuffer (needs .NET 8 SDK), and decompiles the game to an IR. Requires the original game
resources (`RESOURCE.MAP`/`RESOURCE.00x`), not the `.sc` tree.
