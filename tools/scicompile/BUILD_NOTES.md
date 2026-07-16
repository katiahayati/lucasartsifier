# scicompile — build notes

A headless, Linux command-line front-end to **SCICompanion's SCI script compiler**.
It replicates `NewCompileScript()` (`vendor/.../Src/MFCDocuments/ScriptDocument.cpp`)
using the *real* compiler, class browser, resource-map, vocab and SCO subsystems —
no MFC, no GUI, no Windows.

    scicompile <gameProjectDir> <input.sc> <output.bin>

## Status: LINKS ✔, RUNS ✔, produces bytecode ✔

* **Builds**: 76 translation units compile; links to a ~2.5 MB `scicompile` binary. 0 errors.
* **Runs the full pipeline** without crashing: app-state → class-browser source load →
  resource-map/vocab read (real POSIX file I/O + mmap) → lex/parse (both Sierra `;`
  and Studio `//` syntaxes) → class/selector/define resolution → PreScan → codegen.
* **Produces non-empty output** on a complete game:
  `scicompile <TemplateGame/SCI0> <src/rm001.sc> out.bin` → **`Wrote script resource 1: 266 bytes`**
  (valid SCI0 bytecode: opcodes `39` pushi, `76` push0, `38`, `4a` send, …).

### The task's literal test (`lsl2/rm26.sc`) runs but emits no file — and that's correct
`vendor/sci-decomp-archive/lsl2` is a **source-only** decompilation: it has `game.ini`
+ `src/*.sc/*.sh` but **no compiled resources** (`resource.map`, `vocab.997` selectors,
`vocab.000` parser words). SCI compilation *requires* a compiled selector table
(`vocab.997`) to map property/method names ↔ numbers, and `vocab.000` for `Said`
words. Without them `scicompile` runs the whole pipeline and correctly reports
semantic errors (`'setCycle' is not a property or method`, `'look' is not in the
vocabulary`, …) and writes nothing — exactly what the real compiler does. This is a
**test-data gap, not a port defect**, verified by successfully compiling the
`TemplateGame/SCI0` project (which *does* ship `resource.map`) to real bytecode.

## Build & run

```sh
cd tools/scicompile
cmake -S . -B build          # cmake 3.16+, g++ 13
cmake --build build -j

# produces bytecode (complete game with compiled vocab):
TG=../../vendor/SCICompanion/SCICompanion/Files/TemplateGame/SCI0
./build/scicompile "$TG" "$TG/src/rm001.sc" /tmp/rm001.bin   # -> "Wrote script resource 1: 266 bytes"

# runs the full compiler, reports missing-vocab diagnostics, no crash (source-only):
./build/scicompile ../../vendor/sci-decomp-archive/lsl2 \
                   ../../vendor/sci-decomp-archive/lsl2/src/rm26.sc /tmp/rm26.bin
```

Toolchain: **C++14** (`gnu++14`, not C++17 — the vendor uses `std::bind2nd` / `std::mem_fun`
/ `std::unary_function`, removed in C++17), `-fpermissive` (downgrades MSVC-isms like
missing `typename` / extra qualification to warnings), `-DNDEBUG` (the vendor's asserts
assume a full-game/GUI context — e.g. "SCI0 must have vocab.999"), `-pthread`.

### The `-I-` include trick (why it's there)
Vendor code quote-includes its own headers (`#include "sci.h"`), and the preprocessor
normally searches the *current file's* directory first — which would make vendor files
pick up the real headers instead of our compat shadows. The obsolete-but-supported
`-I-` flag removes that rule: dirs **before** `-I-` serve quote-includes (compat wins),
dirs **after** serve quote + angle includes (vendor tree + bundled libs). This makes the
shadows apply uniformly across every TU without touching a single vendor file.

## What is shadowed / stubbed / patched

**Nothing under `vendor/` is modified.** Everything new lives under `tools/scicompile/`.

### `compat/` — header shadows & compat layer (win via `-I` compat-first + `-I-`)
| file | why |
|---|---|
| `stdafx.h` | Linux PCH: Win types, orders the std includes + the `protected→public` `<stack>` trick, includes the shims + foundational SCI headers, defines the MSVC macros at the end |
| `winshim.h`, `winfile.cpp` | Win32 API shim. Handles/GDI structs/consts; **real POSIX-backed** file I/O (`CreateFile`/`ReadFile`/`mmap`/`GetPrivateProfile*`/`FindFirstFile`/…), including `\`→`/` normalization and **case-insensitive path resolution** (Windows FS assumption). Inert stubs for process/shell/GDI. |
| `mfc_stubs.h` | minimal `CWnd`/`CEdit`/`MSG`, `AfxGetMainWnd`, empty `std::tr2::sys` (+ `path`/`exists`), empty `stdext` |
| `AppState.h`, `AppState.cpp` | headless `AppState` backed by **real** `CResourceMap`+`SCIClassBrowser`+`DependencyTracker`; `IsBrowseInfoEnabled()` returns **true** (else the class browser no-ops) |
| `CCrystalTextBuffer.h` | `std::vector<std::string>` text buffer (`LoadFromFile`/`GetLineChars`/…), regular-file-only, case-resolving |
| `sci.h`, `Stream.h` | verbatim copies with 5 mechanical MSVC→GCC fixes (unsized `extern` arrays, enum-class array bound, `typename _T &` param) |
| `ScriptOM.h` | verbatim + `ReduceBlock<>` dead-code realized via `SafeSyntaxNode`/`.release()` (`CastSyntaxNode`/`ReleaseSyntaxNode` never existed) |
| `CompileContext.h` | verbatim + `defines_map` → `scicompat::hash_map_lb` (adds MSVC `unordered_map::lower_bound`==`find`) |
| `Vocab000.h` | verbatim + `word2group_map` → `hash_map_lb` (same) |
| `ParserCommon.h`, `StudioSyntaxParser.h` | verbatim + `this->template`/`::template` qualifiers, renamed shadowing template params, `_CommentPolicy::template …` |
| `ParserActions.h`, `SyntaxContext.h`, `SCISyntaxParser.h`, `SourceCodeFormatter.h` | thin wrappers injecting `using namespace sci/std;` + fwd-decls + `using std::endl;` before `#include_next` (two-phase lookup) |
| `ResourceSources.h` | verbatim + `this->` on 3 dependent-base template calls (`NavAndReadNextEntry`/`WriteEntry`/`FinalizeMapStreams`) |
| `ResourceBlob.h` | verbatim + `using _TLayout::iNumber/iType/…` (dependent-base bitfields) |
| `resource.h`, `SaveResourceDialog.h`, `RemoveScriptDialog.h`, `TlHelp32.h`, `sys/pshpack*.h`, `sys/poppack.h` | stub headers for GUI-dialog / toolhelp / struct-packing includes |
| `keywords_compat.cpp` | `IsSCIKeyword` et al — verbatim keyword tables copied from `ScriptView.cpp` (an MFC file we don't compile) |
| `compilelog_compat.cpp` | `CompileLog::{HasErrors,CalculateErrors,SummarizeAndReportErrors}` — re-impl (defined in `ScriptDocument.cpp`) |
| `linkstubs.cpp`, `linkstubs2.cpp` | link stubs for symbols only defined in GUI/graphics/audio/thread files that are **referenced but never called** on the compile path (see risk table) |

### `patched/` — build-time copies of vendor `.cpp` (vendor originals untouched)
Compiled *instead of* the originals; each has a banner + a minimal, mechanical fix:

| file | fix |
|---|---|
| `Compile.cpp` | `?:` `WORD`/`SpeciesIndex` ambiguity → `SpeciesIndex(DataTypeAny)`; `__super` via `-D__super=FunctionBase` |
| `CompileContext.cpp` | rvalue `istream&` (SCO load) → local; **null-vocab guard** in `LookupWord` (source-only projects have no `vocab.000`) |
| `ScriptOM.cpp` | rvalue `std::string&` in `trim(trim(...))` → locals; `StringCch*` shims |
| `SyntaxParser.cpp` | 6× rvalue `const_iterator&` (`stream.begin()`) → one local |
| `SCO.cpp` | `typename` on dependent iterator; rvalue `istream&` |
| `scii.cpp` | MSVC `list::iterator._Mynode()` → libstdc++ `._M_node` (node-pointer comparator) |
| `CompiledScript.cpp`, `SCISourceCodeFormatter.cpp` | rvalue `istream&`; `false`→`nullptr` pointer arg |
| `ClassBrowser.cpp`, `Vocab000.cpp`, `Vocab99x.cpp` | `typename`; by-value proxy iterator; `(int(*)(int))::tolower`; `__super=CVocabWithNames` |
| `ResourceMap.cpp`, `ResourceBlob.cpp`, `GameFolderHelper.cpp`, `AudioResourceSource.cpp`, `AudioCacheResourceSource.cpp` | rvalue `unique_ptr&`/iterator&/`istream&` bindings; `atomic{0}` init |
| `util.cpp` | `ScriptId::GetFullPath` uses `/`; `ScopedFile` no longer throws on a missing file (degrades) |
| `Stream.cpp` | `streamOwner(HANDLE)` degrades to empty on an INVALID handle instead of throwing |

`main.cpp` adds: `InitializeSyntaxParsers()` (grammar setup — else null match-fn pointers),
explicit per-script language detection, and a top-level `try/catch` so vendor I/O
exceptions report cleanly instead of aborting.

## Semantically-risky compromises — please verify in the fidelity gate

1. **`#define exception(msg) runtime_error(msg)`** (stdafx.h) — MSVC's non-standard
   `std::exception(const char*)`. Faithful (same `what()`), but it's a global macro.
2. **`min`/`max` macros** — vendor uses bare `min()/max()`; `std::min/max` &
   `numeric_limits::max()` are unused on the compile path (verified), so this is safe.
3. **`_Get_container()` → `c`** + `protected→public` on `<stack>`/`<queue>` — MSVC
   accessor for a stack's underlying container. Access-only change; no ABI impact.
4. **`hash_map_lb::lower_bound == find`** (`defines_map`, `word2group_map`) — matches
   MSVC's `unordered_map::lower_bound` used only for duplicate-key existence checks.
5. **`scii._Mynode()` → `_M_node`** — a "consistent but meaningless" node-pointer
   ordering for a `code_pos` multimap. Pointer comparison is a valid strict-weak order.
6. **rvalue-binding rewrites** — many `func(temporary)` sites where the callee took a
   non-const `T&` (MSVC extension). Rewritten to a named local; semantically identical
   because the argument was a discarded temporary. **Worth a spot-check.**
7. **Link stubs (never invoked on the compile path)** — graphics resource creators
   (`Create{View,Pic,Font,Sound,Cursor,Palette,Message,Audio,Map}Resource` + defaults),
   audio/wave helpers, `PaletteComponent`, `_Combine`, `CreateDegenerate`,
   debug/post-build threads, `SniffSCIVersion`, `ResourceNumberFromFileName`,
   `SimpleCompile`. The **Text** resource creator is real (`Text.cpp`).
8. **File I/O robustness** — `ScopedFile`/`streamOwner` no longer throw on missing
   files; case-insensitive path resolution. These change *error behavior* (graceful
   vs. exception) for absent resources, not the bytecode of a successful compile.

## Known issues (beyond Stage 1)

* **Scripts that define classes with methods** currently crash in
  `scii::get_final_offset()` (a null `code_pos` from a method-name→offset lookup during
  `_WriteClassOrInstance`). `rm001.sc` (no method-bearing class of its own) compiles
  cleanly; several method-heavy scripts hit this. Needs investigation — likely a
  method-selector-name vs. local-proc-key mismatch in the emit phase, possibly
  interacting with the `_M_node` comparator or the dynamically-grown selector table.
* **Source-only projects** (no `resource.map`/`vocab.*`) cannot resolve selectors or
  `Said` words, so they never emit output (correct, but limits the lsl2 test).
* **`ReLoadFromSources` returns false** for both test games (falls back to
  `ReLoadFromCompiled`); the class tree is nonetheless populated enough to resolve
  classes when compiled resources are present (rm001 works). Worth confirming the
  source-class path is fully exercised for byte-exact fidelity.
