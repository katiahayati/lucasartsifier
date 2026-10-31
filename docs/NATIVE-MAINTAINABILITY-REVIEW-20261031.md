# Native Lucasartsifier maintainability review — 2026-10-31

**Decision: keep the native architecture and resume GK1 on the later SCI2 implementation after a small adoption and cache-lifetime repair. Do not require another general consolidation or rewrite first.** The old `gk1` branch contains avoidable semantic reconstruction that should not be imported wholesale. The later branch has already removed or consolidated much of that work. Its remaining problems are specific interfaces and lifecycle assumptions, not evidence that Sierra-domain modeling has become inherently unmaintainable.

Before new GK1 feature work, establish exactly which SCI2 snapshot is being adopted and repair its inherited process-global, integer-identity derivation caches. Finish predicate preservation, placement coverage, and the machine-compilation seam alongside the first feature that needs them. Broader removal of globals, entry-record migration, and module splitting can wait.

This is a review, not implementation or fresh validation. I read source, selected history and saved artifacts; I ran no builds, tests, analyzers, replays, or cloud work. The only new file is this report. I did not inspect the excluded symbolic identity test files or the unrelated symbolic worktree.

## Reviewed versions and attribution

References prefixed **G** are `/home/hayati/coding/sierra_softlock`, production snapshot `a568315b22e97329039c10d04c3ab1a60c16ef81`; checkout HEAD `d46c9aa` adds the preceding review only. **S** means `/home/hayati/coding/sierra_softlock/build/worktrees/sci2-modeling`, committed HEAD `3dba3f8c689668e734b34f425425a712af7e3164`, plus the explicitly identified dirty changes. **M** is stable main, `45068351290ffd90e74186c69322d200fa60cafd`, inspected through Git. These are divergent branches, not successive versions of one implementation.

The SCI2 dirty pass modifies ten tracked files and has three untracked files. Its production changes include shared variable-effect decoding, machine destinations, register-write prices and local write choices, plus handler-template reuse. They are real improvements despite being uncommitted. I independently compared ten relevant current production files against `build/review_effect_consolidation/final/source-hashes.json`; all matched: `analysis`, `compile`, `extract`, `handler_actions`, `machine`, `missability`, `opmodel`, `sci2_dependencies`, `guards`, and `pipeline`. This is a limited source-identity check, not a new test result or approval of every file.

I began with code and branch diffs. Only afterward did I read `docs/NATIVE-GK1-REVIEW-20261031.md` and retained validation summaries. Its recommendation against a wholesale replacement is consistent with the independent findings below. This review adds a narrower maintainability priority: fix the derivation-cache lifetime seam before using the later branch as the new development base; do not expand that into mandatory elimination of every global.

## Prioritized repair decision

| Priority | Finite change | Timing relative to GK1 | Size / risk |
|---|---|---|---|
| 1 | Adopt one consolidated SCI2 base; exclude the old closure reconstruction | **BEFORE GK1** | Small adoption task; integration risk is moderate |
| 2 | Give native derivation memos an IR lifetime and restore installed room vocabulary | **BEFORE GK1** | Small, localized; low to moderate regression risk |
| 3 | Preserve preparation predicates and account for placement coverage | **WITH first GK1 protective feature**, before emitting it | Medium; behavior-sensitive |
| 4 | Use one compiled step source for machine effects and delivery; expose incomplete walks | **WITH first GK1 feature that depends on this seam** | Medium; policy differences require care |
| 5 | Centralize graph invalidation and explicitly delimit active-game context | **LATER** | Medium; no concurrency rewrite required |
| 6 | Make entry metadata and regression identities resilient to extension | **WITH the next affected feature**; broad migration **LATER** | Small checks first, medium migration if warranted |

There is no additional architecture cleanup gate after items 1–2. “Before GK1” here means before extending the integration base, not a reason to stop reading game source or preparing a feature specification.

## What is intrinsic, and what is avoidable

The native abstractions are mostly legitimate. SCI Scripts have captured registers, cues, explicit state jumps, waits, competing host slots and room-entry effects. Inventory may be an owner relation rather than a Boolean. Flags live in several physical stores. Lowering these into common register and transfer operations preserves useful information while avoiding a whole interpreter. The fact that a rule was discovered through KQ6 or GK1 does not make it a game-specific patch.

The inspected paths overwhelmingly recognize shapes and class/procedure relationships, rather than branch on a game title. `Machine.entry_recv` represents the actual Script slot; `register_flow.fold` preserves a captured value at its read; separate unconditional `init_writes` and conditional `init_seq` preserve a distinction needed by committed entry semantics. Collapsing these distinctions merely to reduce fields would damage the model. Likewise, `ir_semantics` is an explicitly bounded raw-AST summarizer with incomplete boundaries; its existence beside the native room/register graph is not by itself an illicit second softlock engine.

Scalar projections and a limited number of joint projections are a sensible response to state explosion. Intersected reachability supplies useful necessary conditions, without generally constructing one executable trace. `S/src/softlock_policy.py:88` says exactly that `scope_allows` preserves candidate selection and leaves unchecked facts unchecked. `classify_loss`, at line 102, separately distinguishes missing coverage (`None`) from an evaluated empty set and returns `UNRESOLVED` for incomplete inputs. `S/src/analysis.py:33` separates candidate, requirement and hazard roles; `patch_rows` at line 207 rejects ordinary hazard consumption. `S/src/pipeline.py:128` keeps SCI2 integration report-only. These are existing protections, not proposed work.

The weakness is where identity, completion or causality disappears between representations. That is engineering debt with concrete consequences. It is not established by the length of `missability.py`, the number of SCI2 files, or the presence of many historical comments.

### Old GK1 reconstruction is the clearest avoidable debt

G adds a growing network of `_wbranch`, `_wbranch_dom`, `_cogrants`, consumer windows, staged closures, restricted projections and step-pruning passes. Several have useful purposes, but too many reconstruct the same effects independently.

At `G/src/missability.py:3897`, grants are associated with writes by `(room, script, str(guard))`. At line 4720, handler co-writes use the same key. Two independent methods can have identical guards; even two unconditional handlers share the spelling `None`. Matching guard text therefore cannot establish one atomic action. The consequence is concrete: the branch can force an unrelated co-write or suppress a stranding because it believes a flip necessarily grants the item (`:7272`). No title-specific counterexample is needed to show that this identity relation is insufficient.

`_closure_tables` at line 7491 harvests effects again; `_pclose_pass` at line 7999 implements another guard evaluator and another projected successor walk. `_staged_pre` calls `_pclose(..., refine=True)` at lines 7790 and 7808, while `_pclose` documents at line 7989 that a PRE holdings closure must use `refine=False`. That is an actual internal contract contradiction. The growing closure stops after 64 passes (`:8143`) and returns its partial sets without a completion flag (`:8189`). A backward-ordered dependency chain longer than the cap can therefore look unproducible solely because the iteration stopped. This is incompatible with the absence-based verdict consumed by `_seal_case`; it is not merely a heuristic being unfairly judged as a proof.

The 12/8-round narrowing loops, broad exception fallbacks and several independently invalidated memos add maintenance risk. Their presence does not demand that we repair this whole abandoned direction. **Exclude this bundle from the new base.** S already preserves handler action identity (`handler_actions.py:13`), co-writes and grants (`sci2_dependencies.py:65`), return context and causal flip predecessors through more focused mechanisms. It does not include G's staged closure subsystem. Reimplementing or “cleaning up” all of G before proceeding would spend effort on code the recommended route does not need.

### Important inherited limitations remain

The counter rule in `G/src/missability.py:4070` and the corresponding S `_build_product` was already present on M. It identifies registers with several consecutive ordered increments, then prevents unordered writes from decreasing them. Observing `0→1` and `1→2` does not prove that an explicit reset cannot run at 2. This is an abstraction assumption, and its use to remove successors is stronger than its evidence. G amplifies it through staged confinement and previous-room lower-bound imports. S inherits the basic rule, but avoids those additional reconstructions.

Do not abolish the counter abstraction on the strength of this review, nor call every existing counter result false. When a new day-based protective result depends on this rule, establish that reset writes are unreachable in the relevant state or retain them as possible transitions. An acceptance fixture must include a real reset alongside increments. This belongs with the first feature relying on monotonicity; the mask preparation feature does not justify a preliminary redesign of all counters.

Unknown and empty answers are not uniformly wrong. `S/src/sci2_routes.py:30` explicitly returns `None` on path overflow and callers weaken the gate. `sci2_survival.rows` declines unreadable or oversized decision tables. `state_musts` discards an incomplete intersection and emits a degraded warning. These are sensible conservative fallbacks. By contrast, the ordinary compiler's `_seq` breaks on `PATH_CAP` while returning the accumulated prefix paths (`S/src/compile.py:255`), and `compile_machine` silently returns from an exhausted walk (`:812`). Consumers cannot distinguish complete delivery information from truncation. `Analysis.complete` currently means all registered detectors returned, not that every underlying compilation was complete. That distinction should remain visible when a result is promoted into protection.

## Repairs, acceptance criteria and sequencing

### 1. Adopt the consolidated SCI2 base; keep the old closure out

**Before GK1.** Resolve and preserve the exact dirty production pass, its untracked supporting test/probe files, and its evidence provenance through the normal integration process. Port independently needed backend changes separately. Do not merge G's full analysis changes just because they arrived on the same branch as the SCI2 backend.

This is mainly an adoption decision, not another refactor. S commit `3dba3f8` already shares projected transfer and scalar/joint successor logic. Earlier commits add reachable-state products, return context and equivalent-successor reuse. The dirty pass already shares `variable_effect`, `next_state`, `register_write_cost`, `local_write_choices` and handler templates. Asking for those consolidations again would prescribe completed work.

**Acceptance:** the chosen tree has a recorded identity; dirty changes are accounted for rather than accidentally omitted; source/input identities accompany retained evidence; existing game regression constraints remain explicit; report-only SCI2 behavior is preserved until a protective feature is ready. The old closure is absent from the integration plan. Do not require another full audit merely because the existing work was uncommitted.

### 2. Own native derivation memos by IR lifetime

**Before GK1.** S inherits M's module dictionaries keyed only by `id(ir)`: `extract.py:211`, `:850`, `:922`, `:1004`, `:1513`, `:1539`, `:1566`. The values do not retain the IR. After that object dies, Python may reuse its integer identity, and a later IR can receive the previous game's room species, room numbers, selector or delegate derivation. This is relevant to existing multi-load tests and analysis tools, without introducing any concurrent-use requirement.

G repaired identity reuse with `_IR_PINS` (`extract.py:211`), but that permanently retains every referenced IR. Its justification that the model cache already retains those IRs does not generally hold: `_MODEL_MEMO` intentionally stores serialized bytes, and cache loads produce new model copies (`missability.py:10035`). Prefer memo storage on the IR itself, or a small lifetime-aware owner, over porting permanent strong pins. Preserve compatibility with the existing simple fixture IR objects; do not turn this into a new object hierarchy.

The installed `_ROOMVAL` is another narrow hole. Both branches assign it in `install_vocabulary`, but omit it from `_BUILD_STATE` (`S/src/missability.py:7736`). `test_model_cache` poisons and fingerprints that same enumerated list, so it cannot discover an omitted field. Restore the installed mapping and its per-IR owner consistently on cache hits, including when patcher configuration reinstalls vocabulary.

**Acceptance:** two distinct game/fixture IRs retain isolated derivations; cache reload and vocabulary reinstallation preserve the correct room-valued mapping; dropping inactive IRs does not leave a permanent module-owned retention chain. Test isolation and release deterministically rather than waiting for an allocator to reuse an address. No full conversion of extraction globals is required here.

### 3. Carry the actual preparation predicate through patching

**With the first GK1 protective feature, before emission.** Keep the existing candidate roles and permissive queries. Add the minimal feature-level contract that records the preparation predicate, source mechanism, evidence limitations and all required interception sites. A register obligation must not become a current-item possession condition merely because an old renderer accepts items.

The producer/consumer split already exists: S reports arrival requirements and scene carry-ins, while the SCI2 CLI deliberately stops before patching. `analysis.patch_rows` performs role checking, not a proof of every candidate. `guards.verify` explicitly checks only movement-guard item/group effects (`S/src/guards.py:2284`); it does not validate action or sink patches. Do not rename these as universal verification or require `scope_allows` to become strict globally.

There is a concrete placement seam in inherited `trigger.find_trigger`: `G/src/trigger.py:1324` selects `sites[0]`. A successful placement at one arming is not coverage of another route to the same transition. For GK1 the source separates mask preparation (`bayouMaze.sc:1894`) from the independent passage arming (`:2066`); the ritual checks preparation flag 216 (`bayouRitual.sc:158`). This is sufficient grounding for the interface repair without repeating the whole GK1 correctness review.

**Acceptance:** one chosen mechanism retains its source predicate through rendering; every unsafe entry route is either intercepted or reported unresolved; the preparation action remains available; a missing placement is not counted as protection. Regression assertions identify the mechanism and condition, not merely the item name. Existing compiler and gameplay checks then validate their respective stages. Size is medium because placement is behavior-sensitive; implement the first real slice, not a universal proof-certificate framework.

### 4. Share the compiled step source and report bounded incompleteness

**With the first affected GK1 feature; not a prerequisite to report-only progress.** S `opmodel._machine_info` compiles inlined bodies into `steps_by_state` (`:737`), then calls `compile_machine(m, ...)` (`:812`), which recompiles raw bodies. Besides duplicate path expansion, a helper call containing a transition can make the effect view and delivered-exit view disagree. Delivery influences suppression of flat fallback edges, so disagreement changes reachability, not just speed. G has a supplied-steps interface (`compile.py:950`, `opmodel.py:815`), but copying it mechanically would ignore differences in the two branches' capture, handoff and wait policies.

Use one compiled input for these views and keep their intentional filtering/compression policies explicit. Record path/walk exhaustion with that compilation. Consumers making absence-based or guaranteed-effect claims must refuse an incomplete answer or fall back conservatively; ordinary candidate reports can retain useful partial evidence with its limitation. This does not mean eliminating the distinct streaming, early-return and symbolic-summary walkers: they answer different questions.

Also distinguish a failed compilation from an ordinary empty delivery set. `S/src/opmodel.py:814` catches every `Exception` and stores `compiled_exits=None, delivered=set()`. `missability.edge_meta` then uses `machine_delivered` to decide which flat edges to suppress (`:3275`). Keeping a flat fallback can be appropriately permissive, but the failed layer should be reported with its cause; it must not quietly look like a fully analyzed machine that delivers nothing. This calls for an explicit completion/error outcome at this boundary, not removal of all compiler bounds or a requirement that every unsupported machine abort the game analysis.

**Acceptance:** a procedure-supplied exit has consistent source/effect/delivery interpretation; capture and control-handoff states survive the shared input; a deliberately exhausted budget cannot masquerade as complete exits or guaranteed grants; accepted legacy output remains unchanged where semantics did not change. Attribute performance savings to removed duplicate work, with no arbitrary runtime target. If the first feature never touches this seam, defer it until the next that does.

### 5. Centralize invalidation and delimit active-game context

**Later.** `guards.apply_guards` edits graph metadata and manually clears caches. S already clears the analysis result, crossing and market evidence, successors and register-stranding results (`guards.py:2237–2280`), improving on G. S's edge-row and relevant-ban indexes deliberately share `_psucc_cache`, so existing invalidation clears them together. `ReachMemo` is local to immutable query relations and bounds retained closures/members. Preserve these designs.

The remaining risk is extension: a new model cache can silently escape the hand-maintained clearing list. Route graph mutation through one model method that owns invalidation and rebuilds affected projections. Keep the current before/after cache-equivalence controls. Do not introduce epochs and a dependency engine unless multiple independent mutation paths actually demand them.

Separately, `load(A); load(B); query(A)` still leaves A's queries reading B's process globals such as `_IPROP_SPEC` or `BOOL_GLOBALS`. Restoration on load fixes the newly returned model, not all live models. A later repair can move answer-time values onto the model or establish an explicit activation scope. Patcher caches keyed only by destination path likewise need a per-build lifetime if a path is reused. These are sequential lifecycle problems; concurrent multi-game support is not a GK1 prerequisite.

**Acceptance:** supported sequential model usage either restores the owning context or rejects misuse clearly; every sanctioned graph edit invalidates derived answers; rebuilding a patch destination cannot reuse stale source/configuration facts. Defer content-addressing every asset and splitting all globals unless their actual workflows require it.

### 6. Protect entry alignment and use semantic regression identities

**With the next feature changing entries or oracles; broad migration later.** Machine entries are spread across parallel arrays: guards, armer, locals, source, receiver and original site (`S/src/machine.py:93–132`). `_drop_continuation_entries` slices each separately (`:775`), and `sci2_routes` carries another list of parallel field names (`:456`). A new field can be omitted without an immediate error; defaults of `{}` or `None` then weaken causal information. Current resynchronization repairs are valuable, but the extension hazard is real.

First centralize append/filter/remap operations and assert alignment, including init-entry indices. Introduce one entry record only when the next extension otherwise requires another synchronized array; compatibility views can keep unrelated callers unchanged. Do not combine this with a rewrite of all machine dictionaries.

Synthetic register allocation order is also intentionally significant (`G/src/missability.py:10238`; S `:8019`). Preserve native numeric indices internally, but use source-backed store identities in new evidence and checks. G's R2/R3 oracle assertions (`test_gk1_ground_truth.py:248`, `:257`) accept item names anywhere in the result union, while its R4 shortcut calls the same closure under review. Those are weak tests for mechanism correctness. Frozen accepted-game snapshots and emitted binaries remain valuable regression constraints; they are not general semantic proofs. The runner's explicit expected failures are not themselves cheating: it detects unexpected failures and promotions. Improve the specific assertions rather than abolishing the test tiers or re-blessing established behavior.

**Acceptance:** dropping/fanning/reordering entries preserves all metadata; an added field cannot silently detach; a changed synthetic allocation does not change the meaning of a new mechanism assertion; a wrong-site or possession-for-deposit row fails even if it names the expected item.

## Performance and stopping point

Performance is a design constraint, and S already addresses real repeated work. Shared projected edge rows avoid repeated interpretation; relevant-ban normalization reuses equivalent successors; SCC reach memoization shares closures; the dirty register-price index avoids rescanning all write costs; handler templates avoid recompiling the same body for each host room. Do not discard these optimizations merely because they add caches.

Saved evidence supports adoption within its scope. `build/review_effect_consolidation/final/summary.json` records 1,461 passing checks across 57 files, unchanged snapshots and emission for five existing games, and 463 GK1 projections containing 174,033 states. Its approximately 1,150.6-second GK1 number is the instrumented native equivalence audit, not a normal pipeline benchmark. It used the recorded regenerated IR and message hashes, not an unspecified current input. Equality supports a refactor's behavior preservation; it does not validate every candidate.

Remaining visible costs include the double compilation above, nested helper/caller AST scans in `S/src/opmodel.py:147`, and potentially large successor caches. The first warrants a bounded semantic repair; the others warrant measurement in the next real feature workload. A code edit invalidates all model-cache entries by design, and initial disk-cache loading unpickles twice for validation and return. These are optimization opportunities, not reasons to block GK1 before measuring their share. Raising limits or deleting dependency products to obtain faster runs is not an acceptable substitute for reuse and explicit incompleteness.

The minimum safe restart is therefore one identified consolidated SCI2 tree, the localized cache-lifetime repair, preserved established-game regression boundaries, and continued report-only treatment of unintegrated candidates. Then implement a small protective GK1 slice with predicate and placement evidence. Keep raw SCI summaries, native projections, domain lowerings, existing patch infrastructure and useful caches. Do not rewrite all evaluators, replace all dictionaries, migrate every entry before use, build a whole-game symbolic solver, or clean up thousands of historical comment lines first. The architecture remains sustainable if new work repairs the specific handoff that loses information and retires its superseded reconstruction, instead of adding another permanent interpretation beside it.
