# The 2026-08-19d contextless review — fix plan and scoreboard

A single contextless agent review critiqued the two features shipped on 2026-08-19d (the castle
cat's `fuse_death_armings` and the henchman's `capture_fold_armings`) on three axes:
derivability, overfitting, correctness. It found **15 findings**, including two latent
CRITICALS in the new patcher appliers and a real derivability defect in the fuse classification.

⚠️ **None of this breaks the shipped KQ5 patch** (v17, play-verified). The criticals are LATENT
— KQ5's sites happen to be the shapes the buggy code handles. Everything else is derivability
and generality: rules that are right on KQ5 for reasons the code does not establish.

**Discipline** ([[commit-rule-and-red-tests]]): every fix gets a test that goes **RED on the
committed code first**, asserting the CORRECT behaviour — never the bug as the expected value.
Latent findings get synthetic fixtures, because a game states the failure mode only if the game
happens to have one (the `test_deletion_soundness.py` doctrine).

**Regression floor** ([[measure-regressions-full-surface]]): LSL2 + KQ4 + KQ6 goldens and the
LB2 watched surface must stay byte-identical on the FULL `snapshot.py` surface (placements
included), and KQ5's two shipped conditions must not move — they are play-confirmed:

    fuse-arm    (and (proc0_12 63) (gEgo has: 24) (or (proc0_12 62) (gEgo has: 37)))
    capture-arm (or (and (not (proc0_12 96)) (== ((gInv at: 25) owner:) 57))
                    (and (gEgo has: 24) (not (== ((gInv at: 24) cel:) 4))))

---

## Order of work

1. **the two text criticals + tests for both appliers** (F1, F2, F14) — safety, and cheapest
2. **rebuild the fuse classification on the DECREMENT** and delete the self-re-arm special case
   (F4, F3)
3. **the soundness trio + the anti-wall gate** (F7, F8, F9, F10, F11)
4. **the nits and the story** (F5, F6, F12, F13, F15, and docs/KQ5-ORACLE.md §23)

---

## Scoreboard

| # | Finding | Where | Test | Status |
|---|---------|-------|------|--------|
| F1 | `_enclosing_if_test` ignores the `else` branch — an arming in the else INVERTS the guard | `patcher.py` | `test_patch_text` | ⚠️ HALF (see R2) |
| F2 | `fuse-arm` wraps the FIRST `(if` in the procedure, not the one containing the spawn | `patcher.py` | `test_patch_text` | ⚠️ HALF (see R3) |
| F3 | the "clock" docstring is FALSE about what the code tests (`local8`, not `local5`; `GetTime` never reaches the spine) | `missability.py` | (with F4) | ✅ |
| F4 | `cds` is "every register compared nonzero", NOT the countdown — root cause of the self-re-arm overfit clause | `missability.py` | `test_fuse_classification` | ✅ |
| F5 | `capture-arm` only lands because an UNRELATED spec edited the site first | `patcher.py` | `test_patch_text` | ✅ |
| F6 | the wrap sits inside `init` after `(super init:)` — a refused arming leaves the object cast-resident with `script == 0` | `patcher.py` | `test_patch_text` | 🔴 declared |
| F7 | neither new remedy has an ANTI-WALL gate, unlike its sibling `fold_carryins` | `guards.py` | `test_fuse_classification` | ✅ |
| F8 | `_fold_disarmed` reads the entry DISJUNCTION conjunctively; and only tests `folds[R][0]` | `missability.py` | `test_deletion_soundness` | ✅ |
| F9 | cannot tell LIGHTING a fuse from TOPPING ONE UP | `missability.py` | `test_fuse_classification` | ✅ |
| F10 | the fixpoint is right for a reason the game does not implement; `price()` never checks whether a chain write FALSIFIES the continuation's arming | `missability.py` + §23 | `test_fuse_classification` | ✅ |
| F11 | discharging is applied to NEGATIVE flag demands too — an unsatisfiable alternative reads as free | `missability.py` | `test_deletion_soundness` | ✅ |
| F12 | `if (a for a in ...) and not alts:` — a generator is always truthy | `guards.py` | `test_fuse_classification` | ✅ |
| F13 | `procs[0]` under-guards a second spawning procedure; `emitted` key is cross-room while `demand_alts` is per-room | `missability.py` | `test_fuse_classification` | ⚠️ HALF (see R5) |
| F14 | neither applier nor `_enclosing_if_test` has ANY test | `test_patch_text` | — | ✅ |
| F15 | dropped non-flag `context`; polarity-blind `_entry_rooms`; `_balanced_span` has no string handling; no memoisation; game-wide `fuse`/`death` | both | mixed | ⚠️ HALF (see R1) |

## What was measured

Run after every commit below, and the last one is the strongest check this project has for a
patcher change — the snapshot surface freezes *whether* a guard landed, never the bytes it
emitted, and F1/F2/F5/F15 all rewrite the text arithmetic:

| Check | Result |
|---|---|
| LSL2 + KQ4 goldens (full surface, placements included) | byte-identical |
| KQ6 + LB2 watched surfaces | byte-identical |
| KQ5 `snapshot.py` surface | byte-identical |
| All five games' **emitted patch source trees**, re-run from `e34516f` in a worktree and diffed | **byte-identical** |
| Suite | 638 passed, 1 known-red (F6), 0 unexpected (from 596/0/0) |

KQ5's classification is unmoved: `fuses {352, 353}`, `phases [(331,3), (331,6)]`,
`deaths [theWizardScript, wakeUpScript]`, and both play-confirmed conditions ship verbatim.

## Where a finding's VERDICT was right and its stated REASON was not

[[re-derive-a-reds-premise]], applied to the review rather than to a red of my own.

**F15's `_entry_rooms`.** The function *was* polarity-blind and now is not (a room named only
under a negation is the one room that conjunct rules out). But that is **not** why KQ5's
henchman row lists rm67: measured before and after, `arm_rooms` is `[54, 58, 59, 60, 61, 67]`
either way, because the region machine's arming disjunction names rm67 POSITIVELY in one of
its per-room arms. A first cut that read only the AND spine dropped rm54, rm58 and rm61 — a
coverage claim shrinking in silence — so the fix descends through both connectives keeping
polarity. Both shapes are pinned in `test_fuse_classification`.

**F9's `zzzScript`.** The review lumps `zzzScript` with `henchCaught` as a top-up. Only
`henchCaught` is provable: its guard bounds the register below the value written
(`(< 353 120) → 353 := 120`), so it can only raise the clock. `zzzScript` writes `353 := 180`
unconditionally, which we cannot prove is not a shortening, so it stays a commitment. The rule
excludes what it can prove and nothing else.

**F9's effect on the cat.** Worth stating because it is the opposite of what a first reading
suggests: KQ5's cat row rides `theCatRunScript st3`'s `353 := 3` *while 353 is running*, which
SHORTENS the clock — a genuine hastening, so it is correctly a commitment. The row does not
depend on the invisible `352 := (Random 5 10)` twin, which remains a stated bounded gap.

## What the review ENDORSED (do not undo)

The shared `_Escapes` refactor; conditions written in the GAME'S OWN spelling rather than a
project alias; and the `fuse-arm` PLACEMENT — a refusal indistinguishable from the stock 20%
no-spawn roll, "strictly better than the `capture-arm` placement it shipped alongside".

---

# THE SECOND REVIEW (2026-08-20) — the cures reviewed on the same mandate

Same brief, no reasoning given, docstrings and commit messages treated as claims to verify —
this time over `e34516f..c3ea337`, i.e. over the cures above rather than the features. It found
six more. **Three are defects the first round introduced or left standing**, which is the whole
argument for reviewing the fix and not only the feature. Every one below was reproduced by hand
before its test was written; ten reds are committed at `58aedb0` and declared in
`tools/run_tests.py` KNOWN_RED so a run reads as "no movement" rather than ten regressions.

| # | Finding | Where | Cure | Status |
|---|---------|-------|------|--------|
| R1 | the candidate scan is raw `finditer`: an `(if` inside a `{…}` message is picked as the arming, the demand lands in the message, the file stops balancing, row says `applied: True` | `patcher.py` `_enclosing_if_test` | filter the scan through `_skip_noncode` too | 🔴 open |
| R2 | conjoining onto `(if T … else B)` DIVERTS control into `B` — on the fixture the else arms the death itself. F1 asked about the else *branch*, never whether the `if` HAS one | `patcher.py` both appliers | disqualify any `(if` with a depth-1 `else`, fall back to wrapping the arming STATEMENT; ⚠️ `NESTED_ELSE_ARM` blesses the bad shape and must be re-derived | 🔴 open |
| R3 | `_place_fuse_arm` enumerates armings as `init:` sends; the arming of a machine is `setScript: <machine>` (`init:` is right on KQ5 only because `theCat::init` does the setScript). One site held, one open, `sites=1` | `patcher.py` | enumerate both spellings — the spec already carries `machine` | 🔴 open |
| R4 | `_falsifies` reads `chain_writes` (an unordered union over every state + the armer) as a register STATE. 26 firings on KQ5, all on a register the chain writes 3 values to. Deletes escapes | `missability.py` | falsify only when NO write of that register satisfies the conjunct; open question: does the pricing walk want an ORDERED last-write? | 🔴 open |
| R5 | `emitted` is outside the room loop, keyed `(machine, item)`, while `demand_alts` is per room — a second room's STRONGER demand never emits | `missability.py` | put the room's demand in the key | 🔴 open |
| R6 | `handler_decs` is 0 on KQ4 and KQ6, so the class this docstring calls "KQ4's day/night, KQ6's wedding fuse" can never classify there. KQ4's clock is a `GetTime` DEADLINE, not a countdown; `(= gN (- gN 1))`, `seconds`/`cycles` and deadlines are all invisible; and `I.walk` does not follow calls while `_hwalk` does | `opmodel.py`, `missability.py` §2 | ⚠️ **needs a design decision, not a patch** — the cure is strictly narrower than what it replaced and its error direction is deleting findings | 🔴 open, USER's call |

## Minor, also open
`_skip_noncode`'s taxonomy names the wrong constructs (the `"` branch is dead on all five trees;
SCI's said specs are `'…'`, unhandled, and are the only non-code construct in this corpus that
actually carries parens — balanced today); the inline `; softlock-guard` comments out the rest
of its line (562 one-line `(if …)` forms across the corpus, 0 containing an arming today);
`_payable` never asks whether the item is obtainable BEFORE the held arming, which is the exact
wall its own prose warns about; and for an owner demand it checks the item has a source, never
that the owner VALUE is establishable.

## What the second review confirmed
Both appliers emit byte-identical output to the code they replaced on real stock KQ5 source, and
F5's claim holds in both directions (stock text: old refuses, new places). `_balanced_span`'s
skip does real work — 21 spans move in KQ6 and LB2, every one inside `DialogEditor.sc` /
`PolyEdit.sc`, which no placement touches. Every cited game source line checks out. F9's stated
effect is exactly what happens. F15's self-correction on `_entry_rooms` is right, and
`_walk_guard` had no remaining references. `_dec_cache`'s `(script, id(node))` key is sound
because the AST dicts are held for the process lifetime.

## What it could NOT verify
The five-game emitted-bytes diff (it stayed read-only and would not clobber a build tree) and
the full 20-minute suite; F6's runtime consequence under ScummVM; and the "catastrophic on LB2"
claim in `test_a_region_clock_does_not_promote_prevroom`, which is hypothetical — LB2's fuse set
is empty before and after, as that test's own comment concedes.

## What it says a NEXT reviewer should take
1. The full five-game emitted-patch diff against `e34516f` — the one claim left half-checked.
2. **The other raw-text scanners** in `patcher.py` / `trigger.py` (`_find_region`,
   `enclosing_clause_head`, `wrap_forbidden_case`, the arm-event `setScript:` finditer). R1 is a
   property of "scan raw text for a candidate, then span from it", and `_skip_noncode` reached
   exactly one of the two halves of one function.
3. `chain_writes` read as a state ANYWHERE else — R4 is one consumer.
4. `ownedby_death_folds`, `_continuation_of`, `_room_unavoidable` / `entry_musts`: not in the
   diff, but they decide what the two new detectors ever see, and this review took them on trust.
