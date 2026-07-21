# scicompile — Compile-All pass and softlock patch emission

This documents the "Compile All" mode added to `scicompile`, the results on the
LSL2 project, and how the two LucasArts softlock-guard rooms (rm26, rm38) were
compiled and wrapped as ScummVM loose patch files.

## What was implemented

### 1. `--all` (Compile-All) mode in `main.cpp`
New invocation, alongside the existing single-script mode:

```
scicompile <gameProjectDir> <input.sc> <output.bin>   # compile one script -> .bin
scicompile --all <gameProjectDir>                      # Compile All: write every .sco
```

`--all` mirrors `CNewCompileDialog::CompileAll`
(`vendor/.../Src/Dialogs/NewCompileDialog.cpp`): it enumerates every script in
`game.ini`'s `[Script]` section via `CResourceMap::GetAllScripts`, and for each
one runs the real `GenerateScriptResource` with a **shared** `CompileTables` +
`PrecompiledHeaders` (exactly as the GUI does). On success it writes the script's
`.sco` object file with `CSCOFile::Save` to `<gamefolder>/src/<title>.sco`
(the path `GameFolderHelper::GetScriptObjectFileName` returns).

The `.sco` files are the whole point: `(use X)` is resolved by
`CompileContext::_LoadSCO`, which reads `X.sco` **from disk** (errors if absent).
The single-script front-end never wrote them, so a script compiled in isolation
could not resolve `Script`/`ego`/`MoveTo`/base classes. Compile-All fills that gap.

**Multi-pass to a fixed point.** SCI scripts have `use` cycles (Main↔System,
Main↔Intrface, …), so a from-empty single pass cannot bootstrap. `--all` iterates:
each pass recompiles every script, rewrites any `.sco` whose bytes changed, and
stops when a full pass makes zero changes and zero failures (the fixed point), or
when it stops making progress (then it reports the still-failing scripts + first
error). This is the same situation SCICompanion is always in — a real project
already has `.sco` files on disk (the **decompiler** writes them via `SaveSCOFile`)
before you ever hit "Compile All".

Not replicated from `NewCompileScript`: the `AppendResource` step that writes the
compiled script/heap into the game's `resource.map`/volumes. We never mutate the
game resources — `use`/species/selector resolution needs only the `.sco` files
plus the already-present compiled `vocab.997`/`vocab.996`/`vocab.000`.

### 2. Path fix in `patched/util.cpp` — `ScriptId::_Init`
Root-cause bug that blocked the class browser and Compile-All: `_Init` split the
full path on `'\\'` only (`str.ReverseFind('\\')`). Our `GameFolderHelper` builds
POSIX `'/'`-separated paths, so the split found nothing (-1) and mangled
folder/filename — breaking `GetFullPath()`, `GetTitle()`, and (critically)
`SCIClassBrowser::ReLoadFromSources`, which opens each source via `GetFullPath()`.
Before the fix `ReLoadFromSources` returned `false` with 0 classes; after it,
`true` with 63 classes (matches the known-good state), and every script's path
resolves. Fix: split on the **last separator of either kind**.

### 3. Combined-project input gaps fixed (not code — data)
The assembled `out/lsl2_project` was missing include headers that scripts pull in
transitively. `game.sh` includes `system.sh`, which includes `kernel.sh`; the
project's `src/` had only the 5 lowercase `.sh` files. Copied the three missing
headers (`SYSTEM.SH`, `KERNEL.SH`, `SORTCOPY.SH`) from `out/patched_ericoakford/`.
These are `#define`-only headers (symbolic names); selector **numbers** still come
from the real `vocab.997`, so this does not affect emitted bytecode.

## Results

### Compile-All: **118 / 118 scripts compiled** (0 failures)
The 4 `[Script]` entries with no source file (`vAuthors`, `vBEChagrin`,
`vBEDismay`, `vEgoPause`) are stale game.ini rows naming non-script resources;
they are detected and skipped, not counted as failures. `122` total `[Script]`
rows − 4 stale = 118 real scripts, all compiled.

Converges in **1 pass** when the project already holds consistent `.sco` files.

### Fidelity check — our compiler vs. original SCICompanion
Deleting a `.sco` and letting `--all` regenerate it produces a file **byte-identical**
to the original (SCICompanion-produced) seed. This is a strong signal that this
Linux port reproduces SCICompanion's compiler output exactly (at least at the SCO
/ object-interface level).

### Fidelity check — recompiled script vs. original Sierra bytecode
Recompiled scripts are **NOT byte-identical** to the game's original `script.NNN`
— **and that is expected**: the shipped game was built by Sierra's `SCIC` compiler;
we recompile an EricOakford *decompilation* with SCICompanion's compiler. Walking
the SCI0 block chain (see below) shows the difference is pure compiler style:

| block    | orig rm26 (Sierra) | ours rm26 (SCICompanion) |
|----------|--------------------|--------------------------|
| exports  | 8                  | 8                        |
| code     | 500 + 962 + 568    | 1992 (single block)      |
| objects  | 66, 50, 42         | 66, 50, 42               |
| said     | 130                | 130                      |
| strings  | 32                 | 32                       |
| locals   | 20                 | 20                       |
| relocs   | 12                 | 12                       |

Sierra **interleaves** a code block before each object; SCICompanion **consolidates**
all code into one block and groups the objects. Every *data* block (objects, said,
strings, locals, relocs, exports) matches **size-for-size exactly**; only the code
differs (2030 vs 1992 total — a couple fewer block headers + minor instruction
selection). Both are structurally valid (clean block chain to the END terminator).
Object blocks matching to the byte means selectors/properties/method tables are
correct — exactly what the guard code relies on.

## The two patched softlock rooms

The patches (`out/patched_ericoakford/rm26.sc`, `rm38.sc`) add only a guard:
`(if (and (ego has: <items>)) <original boarding> else (NotNow))`. `NotNow` is a
public procedure in `Main.sc` (both rooms `(use Main)`); the item constants are in
`game.sh` (both `(include game.sh)`). No class-interface change, so their `.sco`
are unchanged.

Compiled against the project `.sco` files (in a copy, `out/lsl2_project_patched/`,
so `out/lsl2_project` stays the unmodified reference):

| script | unmodified | patched | delta | where the delta lands |
|--------|-----------:|--------:|------:|-----------------------|
| rm26   | 2354 B     | 2396 B  | +42   | code block 1992→2034 only |
| rm38   | 1842 B     | 1896 B  | +54   | code block 1412→1466 only |

All other blocks are byte-identical between unmodified and patched — the patch is
purely additive guard code.

## Loose patch files — `out/lsl2_patched_game/`

SCI0 loose-patch format, per SCICompanion's own writer
(`ResourceBlob.cpp` `_SaveToFile`, no-header branch) and confirmed against
ScummVM's reader (`convertResType` masks `& 0x7f`):

```
byte 0 : 0x80 | ResourceType   ->  0x80 | 2 (Script) = 0x82
byte 1 : secondByte            ->  0x00  (SCI0: GetResourceOffsetInFile(0)=0, no extra header)
byte 2+: raw compiled script resource
```

| file | bytes | header | = raw + 2 |
|------|------:|--------|-----------|
| `script.026` | 2398 | `82 00` | 2396 + 2 |
| `script.038` | 1898 | `82 00` | 1896 + 2 |

(ScummVM detects `out/lsl2_project` as `sci:lsl2`; loose `script.NNN` files placed
in the game folder override the mapped resource.)

## How to reproduce

```
# build (once)
cmake --build tools/scicompile/build -j4

# 0. one-time project fixups (already applied to out/lsl2_project):
#    - copy missing headers:  SYSTEM.SH KERNEL.SH SORTCOPY.SH  (from out/patched_ericoakford)
#    - seed .sco to break use-cycles: cp out/patched_ericoakford/*.sco out/lsl2_project/src/
#      (these get overwritten by our compiler; final .sco are proven byte-identical)

# 1. Compile All -> writes out/lsl2_project/src/*.sco  (expect 118/118)
tools/scicompile/build/scicompile --all out/lsl2_project

# 2. verify an UNMODIFIED room resolves + emits a non-empty resource
tools/scicompile/build/scicompile out/lsl2_project out/lsl2_project/src/rm26.sc out/scicompile_out/rm26_unmod.bin

# 3. compile the PATCHED rooms against the project .sco (in a copy)
rm -rf out/lsl2_project_patched && cp -r out/lsl2_project out/lsl2_project_patched
cp out/patched_ericoakford/rm26.sc out/lsl2_project_patched/src/rm26.sc
cp out/patched_ericoakford/rm38.sc out/lsl2_project_patched/src/rm38.sc
tools/scicompile/build/scicompile out/lsl2_project_patched out/lsl2_project_patched/src/rm26.sc out/scicompile_out/rm26_patched.bin
tools/scicompile/build/scicompile out/lsl2_project_patched out/lsl2_project_patched/src/rm38.sc out/scicompile_out/rm38_patched.bin

# 4. wrap as loose patches  [0x82][0x00][raw]
mkdir -p out/lsl2_patched_game
printf '\x82\x00' > out/lsl2_patched_game/script.026; cat out/scicompile_out/rm26_patched.bin >> out/lsl2_patched_game/script.026
printf '\x82\x00' > out/lsl2_patched_game/script.038; cat out/scicompile_out/rm38_patched.bin >> out/lsl2_patched_game/script.038
```

## Known cosmetic issue (not a compile problem)
During `ReLoadFromSources`, `SCIClassBrowser::_AddInstanceToMap` logs
`Class browser: Invalid script number in <garbage>` for some instances
(`Script::GetPath()` returns a stale/garbage string for a few nodes). This is
stderr logging only — every script still compiles, and the emitted `.sco` are
byte-identical to the reference. A genuine unresolved symbol produces a real
compile error and a non-zero exit; none occurred.

## The one thing to verify next (deferred, engine-in-the-loop)
Byte-identity with the original was neither achieved nor expected (different
compiler). The remaining, definitive check is **runtime**: load the patched
`script.026` / `script.038` in ScummVM (`sci:lsl2`, headless with
`SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy`) and confirm rooms 26/38 behave —
boarding blocked until the required items are held, `NotNow` message otherwise,
and no regression to normal play. That is the deferred M-step; this pass produced
the correctly-structured, guard-carrying patch resources it needs.

## Include headers and `.sco` bootstrap — both are TOOLCHAIN-PROVIDED (2026-07-21)

Two things looked like "we must generate this ourselves". Neither is.

### 1. `sci.sh` — a packaging gap in this port, not a missing artifact
sci-tools (sluicebox) emits `(include sci.sh)` in all 118 decompiled scripts. SCICompanion SHIPS
that header: `SCICompanion/Files/CompileInclude/{sci.sh,keys.sh}` ("SCI Script Compiler Header, by
Brian Provinciano", 494 + 171 lines). `GameFolderHelper::GetIncludeFolder()` resolves it as
**`<directory of the executable>` + `include`** — on Windows that is the install's `include/`
folder, and our shim's `GetModuleFileName` reads `/proc/self/exe`, so the port wants
`tools/scicompile/build/include/`. We had simply never deployed the files there. Copying the
toolchain's own headers into that folder fixes it; do NOT hand-write a substitute, and do NOT
borrow a foreign game's `game.sh` (tried, and it fails differently: unknown class `InvI`,
undeclared `global12`, because it is a DIFFERENT decompilation's header).

### 2. `.sco` files — generated by the DECOMPILER, from source + compiled script
`(use X)` is resolved by reading `X.sco` from disk, and every LSL2 script has at least one `use`,
so a from-empty Compile-All cannot bootstrap: there is no script that compiles standalone to seed
the chain. SCICompanion never hits this because its own decompiler writes the `.sco` set first --
`DecompileScript.cpp:538`: `SCOFromScriptAndCompiledScript(*pScript, compiledScript)` then
`SaveSCOFile(helper, *scoFile)`.

Both inputs are things we already have: the parsed source (our sluicebox `.sc`) and the compiled
script (the pristine game's resources). And both translation units are ALREADY in this port's
CMake build (`patched/SCO.cpp`, `patched/CompiledScript.cpp`), so `SCOFromScriptAndCompiledScript`
is linkable today. What is missing is only a front-end: a `--sco <gameProjectDir>` mode in
`main.cpp` that walks the scripts, pairs each parsed source with its compiled resource, and saves
the `.sco`. That derives the interface set from THE GAME plus OUR decompilation -- no downloaded
artifacts, and it generalises to any SCI title.

**Do not** seed `.sco` files from a foreign decompilation. We tried that with the EricOakford tree
and it "worked" only because both describe the same game; it is precisely the two-tree seam that
has now caused three separate failures.
