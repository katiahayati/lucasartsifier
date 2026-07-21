# Licensing status

Research notes, not legal advice. The purpose is to record what the code actually contains so a
license can be chosen deliberately.

## What we distribute, and under what terms

| component | origin | license | do we redistribute it? |
|---|---|---|---|
| `src/**` (Python analysis) | ours | unset | yes |
| `tools/scicompile/patched/**` | **SCICompanion**, modified | **GPL-2.0-or-later** | **yes** — 18 files |
| `tools/scicompile/compat/**` | ours, but 9 files carry SCICompanion's header | **GPL-2.0-or-later** for those 9; the other 26 are ours | yes |
| `tools/scicompile/main.cpp` | ours | derivative (see below) | yes |
| `tools/sci-tools-fork/json-ir.patch` | patch against **sci-tools** | patch is ours; target is **MIT** | yes |
| `vendor/SCICompanion`, `vendor/sci-tools` | upstream | GPL-2.0-or-later / MIT | **no** — gitignored |
| Prof-UIS 2.92 (commercial UI lib) | bundled inside SCICompanion | proprietary | **no** — not shipped, not linked (the port is headless, no MFC/GUI) |
| game data (`.sc`, IR, resources) | Sierra | proprietary | **no** — removed from history 2026-07-21 |

## The binding constraint

**SCICompanion is GPL-2.0-or-later.** Every ported file carries:

```
Copyright (c) 2015 Philip Fortier
This program is free software; you can redistribute it and/or modify it under the terms of
the GNU General Public License as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.
```

27 of the 53 C/C++ files we publish carry that notice. `main.cpp` and the `compat/` shims include
SCICompanion headers and link its compiler, class browser, resource map and SCO subsystems, so the
**`scicompile` binary is a derivative work and must be GPL-2.0-or-later**. That is not a choice.

Good news on compliance hygiene: every ported file already states that it is a modified copy and
what changed (e.g. *"PATCHED COPY (build-time) of SCO.cpp -- vendor original is UNMODIFIED.
scicompile: mechanical MSVC->GCC fix only"*), which is what GPL §2(a) asks for.

**Gap to fix either way: there is no LICENSE file in the repo at all**, and we are distributing
GPL-licensed code without shipping the GPL text. That should be corrected regardless of which
option below is chosen.

## The Python question

The analysis (`src/**`) never links SCICompanion. It invokes `scicompile` as a **separate process**
with command-line arguments and communicates through files. Under the FSF's own reading, programs
communicating at arm's length (exec, pipes, files, sockets) are separate works, and shipping them
together is "mere aggregation", which the GPL explicitly permits. So the Python is not *required*
to be GPL.

## Options

**A — GPL-2.0-or-later for the whole repo.** Simplest and safest: no argument about where the
boundary falls, and MIT (sci-tools) is GPL-compatible so the fork patch is fine. Cost: anyone reusing
the *analysis* inherits copyleft, even though that part is independent of SCICompanion.

**B — Segmented.** `tools/scicompile/**` GPL-2.0-or-later (unavoidable); `src/**` permissive
(MIT/Apache-2.0). Keeps the novel work reusable. Cost: relies on the subprocess boundary being
accepted as arm's length — well-supported, but it is an interpretation, and a `LICENSE` per
directory plus a clear README note is needed so nobody has to guess.

**C — Drop the compiler from the repo.** Ship only the `.sc` edits and a build script that fetches
and patches SCICompanion itself, exactly as we already do for sci-tools. Then nothing GPL is
redistributed and `src/**` can be anything. Cost: the port was real work (a headless Linux build,
two upstream null-deref/bounds bugs fixed, a `--sco` mode added); hiding it behind a patch file
makes it much harder for anyone to use, and those upstream fixes are worth contributing back.

## Suggested

**B**, plus in either case:
1. add `LICENSE` (project choice) and `tools/scicompile/LICENSE` (full GPL-2.0 text),
2. add a `NOTICE` crediting Philip Fortier (SCICompanion, GPL-2.0+) and sluicebox (sci-tools, MIT),
3. keep `vendor/` and game data out of the repo, as now.

Worth considering separately: the two upstream bugs we fixed in `patched/SCO.cpp` (a null deref via
`operator[]` on a missing class name, and an unbounded index in the export loop) are real defects in
SCICompanion that only appear when compiling a *different* decompiler's output. Offering them
upstream would be a courtesy, and GPL-2.0+ makes that straightforward.
