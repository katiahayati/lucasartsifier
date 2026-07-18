# Engine direction — library-maximizing rewrite vs. hand-rolling

Two arguments, written to be reviewed against each other. Plan A: reuse as much
existing work as possible. Plan B (the inversion): why A is wrong and hand-rolling
(formalized in place) is the better path. Concise summaries at the end of each.

Grounding facts (researched):
- **sluicebox `sci-tools`** (C#) is the decompiler that produced our scripts. It builds
  a full typed AST of every script, handles *all* SCI versions, and gives programmatic
  access to *every resource* (so: scripts AND picture/control maps). Clean library/CLI,
  cross-platform (.NET).
- **SCICompanion** (C++, vendored) has an equivalent parser + typed AST (`ScriptOM`) +
  visitor (`ScriptOMTraverse`) + compiler + decompiler + raster/control-map decoding —
  but it's an MFC Windows GUI app; the library is entangled with MFC, so extracting it
  as a clean dependency is painful.
- **ScummVM** SCI engine (C++) is a runtime interpreter; useful as a semantics oracle
  and for its documented resource formats (the three maps: visual, priority, control).
- **BDD engines:** CUDD (C, gold standard), Sylvan (parallel C), `dd` (Python bindings
  to CUDD/Sylvan), oxidd (Rust), JavaBDD, .NET `DecisionDiagrams` (less battle-tested).
- **Symbolic model checkers** (a level up from raw BDDs): nuXmv / NuSMV.

---

# PLAN A — maximize reuse

## The layering

The tool is three jobs; only the middle one is irreducibly ours.

1. **Front-end (REUSE: `sci-tools`).** Authoritative SCI reader. One tool gives us the
   correct typed AST for every script *and* the resource data we lack (control maps),
   for every SCI version. This retires: our hand-rolled `sexpr` reader, the two-dialect
   seam (sluicebox vs EricOakford) we currently special-case, and — via its resource
   access — gap #2 (the control map). SCICompanion is the fallback if `sci-tools`'
   resource coverage is thin, but its MFC coupling makes it second choice.

2. **Extraction (OURS, rebuilt on the AST).** Walk the correct typed AST to build the
   gating transition system: rooms, items (with properties), register/local values,
   gated edges, deaths, writes. This is where we *add the coverage we're missing*:
   - room-as-program (`init` + `doit` + `handleEvent` + actor sub-scripts over
     room-locals) — closes the rm47/disguise class;
   - item-property state (arrow count in the bow's `loop`) — closes Lolotte;
   - control-map position gates (from the front-end's resources) — closes the bomb.
   Built as a principled visitor/dataflow over the typed AST (the toolchain even
   provides the traversal), not the ad-hoc walker — this is the "formalize it" fix.

3. **Encode + engine (REUSE: a BDD library).** Encode the transition system as boolean
   variables + one transition-relation BDD; do symbolic forward reachability (image
   fixpoint) and a backward "can still win" set. **Softlocks fall out directly:
   `reachable ∧ ¬can-win`.** This deletes the entire promotion / scoping / exit-write
   branching / masking / sentinel layer — the BDD represents the joint value-space
   compactly by construction, so the state explosion and the combined-state correctness
   bugs become structural non-problems.

4. **Requirements (OURS, kept).** QuickXplain over symbolic reachability queries →
   minimal CNF requirements ("14 and (11 or 12)"). Already textbook; unchanged in
   spirit, it just calls the symbolic engine.

5. **(Future) Half 2 / backprop.** Supervisory-control synthesis (Supremica) or a
   synthesis encoding. Out of scope here; noted so the language choice doesn't box it in.

## Language / interop decision

The front-end wants C# (`sci-tools` native); the engine wants C/C++/Python (CUDD/`dd`).
Two resolutions:

- **A1 — C# monolith.** Build everything in C# on `sci-tools` (native AST + resources,
  no serialization seam), engine via CUDD through P/Invoke (or a managed BDD lib).
  Cleanest single stack; risk is BDD-in-.NET maturity (mitigated by P/Invoke to CUDD).
- **A2 — hybrid (recommended).** `sci-tools` (C#) emits a **stable serialized IR** (JSON:
  the AST facts + the resources we need). A separate extraction+engine component consumes
  it — in Python with `dd` (most mature bindings) or C++ with CUDD. Clean seam, each part
  in its best-fit language, and our existing extraction + requirements logic can be
  *ported onto the correct AST* rather than rewritten from zero. Cost: define and version
  the IR schema.

## What we keep / replace / delete

- **Keep (concepts + tests):** the softlock *definition* (`reachable ∧ ¬can-win`),
  requirements/QuickXplain, and — critically — `examples.py` + `_check_core` as the
  **acceptance spec** the new stack must satisfy.
- **Replace:** parsing (`sexpr` → `sci-tools` AST); the engine (promotion/scoping/
  branching → BDD symbolic reachability).
- **Delete:** the promotion value-flow machinery entirely (entry/exit/self writes,
  masking, `OTHER`/`NOTTRACKED`, exit-write branching) — the review's engine-half bugs
  vanish with the code that has them.
- **Rebuild + extend:** extraction over the AST, plus the three new coverage areas.

## Sequencing (tests as the fixed target)

1. Front-end: `sci-tools` → serialized IR; verify it reproduces our current extraction
   inputs on both games.
2. Engine: BDD encode + symbolic reachability; reproduce the *passing* catalogue cases
   (base strandings, the parachute) — i.e., don't regress.
3. Requirements: QuickXplain over BDD queries; match current disjunctive findings.
4. New coverage: room-as-program, control map, item-props → turn the 3 FAILING catalogue
   cases GREEN.

## Risks
Language/interop friction; BDD variable ordering (small instance, low risk); the IR-schema
and `sci-tools`-serialization effort; and the honest one — **the extraction abstraction is
still ours to get right**; the AST makes it *rigorous*, not automatic.

## PLAN A — concise summary
Front the tool on `sci-tools`' correct all-versions AST (kills our parser, the dialect
seam, and — via its resources — the control-map gap), rebuild extraction as a principled
visitor over that AST (adding room-as-program, item-props, control gates), and replace our
promotion engine with symbolic BDD reachability (softlocks = `reachable ∧ ¬can-win`),
keeping QuickXplain for minimal requirements. Hybrid language: `sci-tools` (C#) emits a
serialized IR consumed by a Python(`dd`)/C++(CUDD) extraction+engine. The engine's whole
bug-and-explosion class is deleted with the code; the tests become the acceptance spec.

---

# PLAN B — the inversion: why A is wrong, and hand-rolling (formalized) wins

## The holes in A

1. **The reuse misses the actual hard part.** Our bugs are not in *parsing* — `sexpr`
   works; the dialect fixes are done. Our bugs are in the **gating extraction**, the
   modeling judgment "surviving rm47 requires `henchStatus==8`." `sci-tools` gives a
   correct AST; it does **not** give that abstraction. So the rewrite reuses the layer
   that already works and rewrites-from-scratch the layer that's hard — on a new stack,
   where we relearn every extraction bug we already paid for.

2. **We haven't shown the *engine* is the problem.** The LSL2 all-40 drop could just as
   easily be a mis-modeled transition (a wrong write/guard the extraction feeds in). A
   BDD engine over a wrong transition relation reproduces the same wrong answer — faster.
   We've proven *extraction+engine combined* is wrong at scale; we have not isolated the
   engine. Swapping the engine may fix nothing.

3. **A BDD is a black box; our fixpoint is inspectable.** All session, the thing that let
   us *find* bugs was printing reach states and tracing exactly why a room dropped. A BDD
   gives you a right/wrong answer with no readable "why." We'd trade a slow-but-debuggable
   engine for a fast-but-opaque one — and we are *still in the business of the engine
   giving wrong answers*, because the extraction feeds it.

4. **The output layer doesn't get structurally cheaper.** `requirements()` is N
   item-removal reachability queries + QuickXplain. A BDD makes each query fast, but the
   *loop* and the re-encoding are unchanged, and the symbolic set does not hand you "which
   item is required" — you still iterate. The base (non-promoted) analysis is already
   fast; the BDD only helps the promoted case.

5. **"Promote everything at once" may be a self-imposed non-goal.** Every real finding
   came from *targeted* promotion — the parachute is `gCurrentStatus` *alone*, and it's
   fast and clean. Each register alone passes. The explosion we're rewriting the engine
   to fix is the all-40-jointly case, which no actual analysis requires. We may be
   rebuilding the whole stack to solve a problem we invented.

6. **The rewrite is a long dark tunnel; the current tool ships value now.** Cross-language
   `sci-tools` interop, CUDD interop, an IR schema, re-porting extraction and tests — that
   is months, high-risk, and the *user gets nothing better* until it all lands. The
   current tool already finds the base strandings and the parachute; incremental fixes to
   it deliver continuously.

7. **We'd trade known bugs for unknown ones.** The code review *enumerated* our current
   failure modes — we understand them. A new stack has a fresh long tail (BDD encoding
   errors, marshalling, `sci-tools` edge cases) we haven't met, plus every accumulated
   extraction fix encodes a real game quirk that a rewrite silently loses unless
   painstakingly re-derived.

8. **The correct fix for "unformalized" is to formalize — not to adopt someone else's
   formalization via a rewrite.** The engine's bugs (liveness gap, branching) came from
   improvising a state-evolution semantics with no spec. The remedy is to *write the
   spec*: define the abstract domain, state the transition semantics precisely, and prove
   the masking/liveness sound — in the code we have. "Python" and "explicit-state" were
   never the problem; "no formalization" was. Formalizing in place is a fraction of the
   cost of a rewrite and keeps the debuggability and the institutional knowledge.

## What B recommends instead
- **Fix the extraction bugs** (the review's extraction-half) — they persist in *any* engine.
- **Formalize the current engine**: write the abstract-domain spec, then make the code
  match it (this is where the liveness/branching bugs get killed *correctly*, not deleted).
- **Drop the "promote-all" goal**; do targeted per-gate promotion, which already works.
- **Add coverage** (room-as-program, item-props, control map) on the current stack.
- Reuse ScummVM/SCICompanion *only* as the control-map spec and the semantics oracle —
  narrow, low-risk borrowing, not a re-platform.

## PLAN B — concise summary
The rewrite reuses the layer that already works (parsing) and re-does from scratch, on a
riskier cross-language stack, the layer that's actually hard and buggy (the gating
extraction) — which no library provides. We haven't even isolated the engine as the
culprit (the all-40 drop may be an extraction bug a BDD would faithfully reproduce), and a
BDD is opaque where our fixpoint is debuggable. The pain is "we never formalized," and the
cheap, low-risk cure is to *formalize in place* (spec the abstract domain, fix
extraction), drop the self-imposed "promote everything" goal that's the only thing
exploding, and borrow from ScummVM/SCICompanion only the control-map format. Ship value
incrementally instead of disappearing into a months-long re-platform.

---

# For review
The crux between them: **is our pain an *engine* problem (→ Plan A: swap to a real
symbolic engine) or a *formalization + extraction* problem (→ Plan B: the engine is fine,
we just never specified it, and the extraction is ours either way)?** That's the question
to settle before committing.
