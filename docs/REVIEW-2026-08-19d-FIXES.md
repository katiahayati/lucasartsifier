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
| R1 | the candidate scan is raw `finditer`: an `(if` inside a `{…}` message is picked as the arming, the demand lands in the message, the file stops balancing, row says `applied: True` | `patcher.py` `_enclosing_if_test` | filter the scan through `_skip_noncode` too | ✅ `a9bad5f` |
| R2 | conjoining onto `(if T … else B)` DIVERTS control into `B` — on the fixture the else arms the death itself. F1 asked about the else *branch*, never whether the `if` HAS one | `patcher.py` both appliers | disqualify any `(if` with a depth-1 `else`, fall back to wrapping the arming STATEMENT; ⚠️ `NESTED_ELSE_ARM` blesses the bad shape and must be re-derived | ✅ `a9bad5f` |
| R3 | `_place_fuse_arm` enumerates armings as `init:` sends; the arming of a machine is `setScript: <machine>` (`init:` is right on KQ5 only because `theCat::init` does the setScript). One site held, one open, `sites=1` | `patcher.py` | enumerate both spellings — the spec already carries `machine` | ✅ `a9bad5f` |
| R4 | `_falsifies` reads `chain_writes` (an unordered union over every state + the armer) as a register STATE. 26 firings on KQ5, all on a register the chain writes 3 values to. Deletes escapes | `missability.py` | falsify only when NO write of that register satisfies the conjunct; open question: does the pricing walk want an ORDERED last-write? | ✅ `de90dd4` |
| R5 | `emitted` is outside the room loop, keyed `(machine, item)`, while `demand_alts` is per room — a second room's STRONGER demand never emits | `missability.py` | put the room's demand in the key | ✅ `de90dd4` |
| R6 | `handler_decs` is 0 on KQ4 and KQ6, so the class this docstring calls "KQ4's day/night, KQ6's wedding fuse" can never classify there. KQ4's clock is a `GetTime` DEADLINE, not a countdown; `(= gN (- gN 1))`, `seconds`/`cycles` and deadlines are all invisible; and `I.walk` does not follow calls while `_hwalk` does | `opmodel.py`, `missability.py` §2 | ⚠️ **needs a design decision, not a patch** — the cure is strictly narrower than what it replaced and its error direction is deleting findings | 🔴 **RE-DERIVED below** — verdict right, every stated reason wrong; USER's call is narrower than it looked |

---

# THE 2026-08-20 CURES (this round)

Nine of the ten declared reds are green. What is written below each is the part the review did not
say — because on four of the six, the VERDICT was right and the stated REASON was not
([[re-derive-a-reds-premise]], applied to the reviewer rather than to a red of my own).

## What was measured

| Check | Result |
|---|---|
| All five games' **emitted patch source trees**, against a worktree at `cc3b897`, recursive diff | **byte-identical** |
| …re-run after the `trigger.py` change, which feeds every placement | **byte-identical** |
| Suite | **655 passed, 1 known-red (F6), 0 unexpected, 0 crashed** (925s), from 638/1 at `c3ea337` |
| KQ5's classification | unmoved: `fuses {352,353}`, `phases [(331,3),(331,6)]`, `deaths [theWizardScript, wakeUpScript]`, both play-confirmed conditions verbatim |

The emitted-bytes harness is now `tools/measure_emitted_bytes.py` rather than a scratchpad
script — the second review named it as the one claim it could not independently confirm.

## R2 — and the outward climb, which the review did not name

Disqualifying any `(if` with a depth-1 `else` is R2's stated cure and it is right. What the
statement missed is the *other* half: when the innermost arming `if` is disqualified, the first
cut CLIMBED OUTWARD to an enclosing `if` and held there. That withholds the arming, which is why
it looked sound — and it is the wrong site, for a reason `trigger.py`'s `proc-arm` branch has
carried in prose since it was written: *"wrap ONLY the arming form, never its enclosing clause:
the `else` sibling is the game's own other outcome and must stay free."* Climbing outward
suppresses that sibling, which no row derived and no spec scoped — the wall-shaped failure
`test_stage_match_is_structural` already refuses elsewhere.

So `_enclosing_if_test` now returns the innermost arming test **or None**, never a wider scope,
and both appliers fall back to wrapping the arming STATEMENT. `NESTED_ELSE_ARM` was re-derived
(it asserted the climb), and `BARE_SPAWNER` with it: it asserted a whole REFUSAL, and full
coverage beats a refusal at the same claim.

## R1 — the red's own assertion was unsatisfiable

The finding is real and reproduced (both appliers wrote the demand inside the message; code
parens 8/8 → 9/10). The test written for it could not have passed on any code: it asked for
`out.count("(") == out.count(")")` on a fixture whose message carries unmatched parens **by
design** — 10/8 before any edit and 10/8 after a perfect one — and for the marker to land after
the last `}`, when the arming `(if` sits *before* the message. Re-derived to the three things the
fix must actually deliver: the message comes through byte-identical, the CODE balances, and the
demand lands on the real arming test. The fuse fixture was rebuilt too; the red had produced it
with two `.replace` calls that dropped a `(method` line and left its closing parens behind, so it
did not balance either.

## R4 — right verdict, wrong measurement

"26 firings on KQ5, all on a register the chain writes 3 values to. **Deletes escapes**."
Instrumented: all 26 firings are the same conjunct, `global332 == 7`, against the write set
`{2, 3, 4}`. None of the three satisfies it, so the old rule and the new one agree on **every**
firing and nothing on KQ5 moves. R4 is latent exactly as F1 and F2 were.

The reviewer's open question — ordered last-write vs. a set — is answered in the docstring as a
stated gap rather than silently: a write reached on only some paths is in the union all the same,
so a register the chain might leave untouched is treated as certainly written. Fixing that needs
a path-sensitive write model `chain_writes` is not.

## R5 — and the test that tested a string

Real, and latent here: 13 castle rooms reach `(theCatScript, 24)` and all 13 derive the same
demand. The red as committed read the SOURCE of `fuse_death_armings` and grepped its key line for
the word `"room"` — a test that would pass on a comment. Rebuilt as a two-room fuse world driven
through the detector: room 1 pays with item 24, room 2's only way out needs 24 **and** 37, and
item 24 must get both demands. Verified red against the committed code first.

## ⭐ R1's OTHER HALF WAS LIVE — the finding this round added

The review's hand-off list said a next reviewer should take *"the other raw-text scanners… R1 is
a property of 'scan raw text for a candidate, then span from it'"*. Measured across the five
source trees, one of them is not latent at all.

`trigger._find_region` takes its region from `re.search(header_re, text)` — first match wins —
and KQ6's and LB2's `WriteFeature.sc` is a **source-code generator**: its message strings are
themselves SCI source, `{ \t(method (doVerb theVerb)\0d\n\t\t(switch theVerb\0d\n}`. That message
holds the first `(method (doVerb` in the file, so the region returned was `(9255, 9815)` — 560
bytes beginning in the middle of a string, every span inside it arithmetic on text that is not
code, and the placement that asked would have rewritten it.

Census of the family, five trees, *matches / matches inside non-code*:

| pattern | | pattern | | pattern | |
|---|---|---|---|---|---|
| `(instance\|class` | 6,356 / 0 | `setScript:` | 2,192 / 0 | `newRoom:` | 763 / 0 |
| `(procedure (` | 328 / 0 | `(if` | 11,073 / 0 | `put: <n>` | 340 / 0 |
| `(cond` | 1,676 / 0 | **`(method (`** | **7,747 / 2** | | |

Both of the two are this. `_find_region` uses `sexpr.code_search` now, and the whole non-code
taxonomy moved to **`sexpr.py`** — one rule, two importers, because `patcher` and `trigger` had
each grown their own and that is precisely what R1 cost ([[same-rule-two-places]]). `trigger`'s
inline copy carried two hazards the shared one does not: it tested `'` **before** `;`, so an
apostrophe in an English comment (`; don't`) opened a said spec and skipped to the next quote
anywhere in the file (zero such comments today), and an unterminated `{` or `'` made `find`
return −1, so the walk restarted from the top of the file forever.

The scanners still raw (`wrap_forbidden_case`'s `rfind("(if")`, the arm-event/arm-clause
`setScript:` searches) are safe for one reason only: nothing they look for is written inside a
message in these five games. That is a fact about the corpus, so it is now a **census check in the
suite** rather than a claim in a docstring — the day a new game writes one, the run says so before
the placement built on it ships.

## ⭐ R6, RE-DERIVED — the verdict holds and not one of its reasons does

R6 was declared as needing a design decision because "the F4 cure is strictly NARROWER than what
it replaced, its error direction is deleting findings, and nothing in the corpus can measure the
loss." The loss is now measured, and it is zero — for reasons that have nothing to do with the
decrement rule.

**The verdict is right,** and its headline number checks out — measured, not taken from the
review: `handler_decs` is KQ5 40 (registers `110, 111, 314, 315, 352, 353, 359, 384, 385` — the
two fuses among them), LSL2 4 (`108`), LB2 3 (`150, 369`), **KQ4 0, KQ6 0**. `fuse_death_armings`
returns `[]` on KQ4 and KQ6 and always will.

**"The docstring calls this class 'KQ4's day/night, KQ6's wedding fuse'."** It calls them the
PARENT class and says so in the same sentence: *"the class is the adversarial clock
([[softlock-mechanism-taxonomy]] class 5, KQ4's day/night, KQ6's wedding fuse) **grown a third
hop**: the clock does not seal an item, it arms a DEATH, and the countdown is not free-running,
it is ARMED by the encounter the player failed to answer."* A free-running clock is excluded by
definition, decrement rule or no. The docstring's last paragraph already states the measurement
and the reason: *"LSL2, KQ4, KQ6 and LB2 all return [] — KQ6's wedding fuse writes a flag no
unavoidable machine's entry pins, so it has no death phase and stays `register_strandings`'
item-seal."*

**"KQ4's clock is a `GetTime` DEADLINE, not a countdown."** It is not a deadline either. It is a
**count-UP wall clock**, `Main.sc:863-877`, in `KQ4::doit`:

```
(if (!= (= global156 (GetTime 1)) global157)     ; the per-real-second tick latch
    (= global157 global156)
    (if (>= (+= global158 4) 60)                 ; seconds accumulator      -- INCREMENT
        (++ global159)                           ; minutes                  -- INCREMENT
        (-= global158 60)                        ; the modulo CARRY         -- not a tick
        ...
        (if (== global159 60) (++ global160) (= global159 0))))   ; hours   -- INCREMENT
```

**"`(= gN (- gN 1))`, `seconds`/`cycles` and deadlines are all invisible."** Censused across the
five IRs: `Assignment(g = g − k)` on a global occurs **zero** times. `g −= k` on a global occurs
**once** — and it is `(-= global158 60)` above, the carry. Teaching `handler_decs` that spelling
would promote KQ4's seconds accumulator to a countdown: a **false positive**, not a recovered
finding. The narrowing the review worried about is, on the one instance the corpus actually has,
the thing keeping a wrong answer out.

**"KQ6's wedding fuse."** It *is* a countdown, of exactly KQ5's shape — `rgCastle.sc:270`, in `rgCastle::doit`, latched
on `(!= lastSeconds (GetTime 1))`, with **four** of them:

```
(if (and (> weddingRemind 0) (== (-- weddingRemind) 0)) …)   ; and loiterTimer, guardTimer, guard2Timer
```

`weddingRemind` is an **object property**, not a global, and its expiry writes `(|= rFlag1 $0002)`
— a property MASK. `handler_decs` records `I.is_global` only. So the blocker on KQ6 is the
**object-property store**, [[modeling-gap-census]] #3, already declared — not the decrement
reading and not this class's taxonomy.

**"`I.walk` does not follow calls while `_hwalk` does."** True only ACROSS SCRIPTS. `_heffect`
routes `PublicCall`/`LocalCall` to `_follow_call`, which re-enters `_hwalk`, which runs the
decrement scan on the callee body. A **LocalCall** files the tick under the same script as the
caller's write, so it matches. Only a cross-script `PublicCall` files `(room, callee, var)`
against a write recorded as `(room, caller, var)`.

### What is actually left for the USER

Two things, and both are narrower than "is the F4 cure too narrow":

1. **Should `handler_decs` learn the object-property store?** That is what would make KQ6's
   wedding fuse reachable by this class. ⚠️ KQ6 is GOLDEN, and its wedding fuse is already
   carried — by `register_strandings` as the letter seal (flag 166 / reg338, `guard_prop_flag_
   owner_write`, shipped in v22). Promoting it here risks a second row for a mechanism that
   already has a guard.
2. **The cross-script tick/write script-key mismatch.** No instance in the corpus; a one-line
   widening (record the tick against the caller's key as well) with no way to measure it here.

## Minor list — two done, two still open

✅ **`_skip_noncode`'s taxonomy** — corrected, and the whole rule moved to `sexpr.py`. Said and
menu specs `'…'` are handled (3,100 in code position on LSL2+KQ4, all balanced, none carrying a
`;` or a `{` — measured, so the addition moves nothing); the `"` branch is documented as dead on
all five trees and kept line-bounded.

✅ **The inline `; softlock-guard` comments out the rest of its line** — 562 one-line `(if …)`
forms corpus-wide, 0 with an arming today. The marker now pushes the remainder onto its own line
when the line is not already blank; when it is (every site today, KQ5's two included) the bytes
are unchanged.

🔴 **`_payable` never asks whether the item is obtainable BEFORE the held arming**, which is the
exact wall its own prose warns about — and for an owner demand it checks the item has a source,
never that the owner VALUE is establishable. Both need the closure `window_closures` builds;
still open, and still stated in the docstring rather than papered over.

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

---

# THE THIRD REVIEW (2026-08-20) — the cures reviewed again, and two of three are MINE

Same mandate, run over the nine cures above. Three findings, **two introduced by the round that
was fixing the round before it** — which is the argument for reviewing the fix, made twice now
([[review-the-fix-not-only-the-feature]]). Every one reproduced by hand before its test was
written; the reds are committed at `51d43b6`.

| # | Finding | Where | Status |
|---|---------|-------|--------|
| N1 | `; softlock-guard` IS A LINE COMMENT — the fix went into `_conjoin_marked` alone, twenty lines from `_wrap_statement`, **which the same commit made the common path** | `patcher.py` + 11 more emitters | ✅ |
| N1b | `_arming_statement_span` returns the innermost balanced form, which is routinely an expression in VALUE position | `patcher.py` → `sexpr.py` | ✅ |
| N2 | R2's anti-wall doctrine is enforced for the `else` SPELLING only — a `cond`/`switch` fork between the arming and the `if` is invisible | `patcher._depth1_else` | ✅ |
| N3 | the census tripwire cannot fail for the reason it names: the family omits `(method (`, the one pattern with hits, and both loops omit KQ5 | `test_patch_text.py` | ✅ |
| N4 | R4's cure has a SECOND error direction, undeclared: a value written on a branch NOT TAKEN can now *satisfy* a conjunct and keep an escape the run never offers | `missability._falsifies` | ⏸ **declared + instrumented, then PARKED [USER]** |

## What was measured

| Check | Result |
|---|---|
| All five games' **emitted patch source trees** vs a worktree at `6aa0a1d`, recursive diff | **byte-identical, 1,084 files** |
| …first run, before the `mark_line` refinement below | **1 file moved** — LB2's `rm520.sc`, and it is what taught the rule its boundary |
| Suite | **691 passed, 1 known-red (F6), 0 unexpected, 0 crashed** (939s), from 655/1/0 |

## N1 — and the eleven other emitters that splice a marker in front of live text

`_conjoin_marked` got the fix on 2026-08-20 and `_wrap_statement` did not, twenty lines away in
the same commit. That is worse than a coincidence: **R2, in that same commit, made
`_wrap_statement` the common path.** Any `(if` carrying a depth-1 `else` is now disqualified
from the conjoin and handed to the statement wrap, and 774 of the corpus's 780 one-line
`(if ...)` forms carry one (re-measured over all five trees, 1,084 files — the "562" the old
comment quoted was a four-tree figure).

Three shapes, all reproduced before the tests were written:

⛔ **The numbers below were RE-MEASURED (2026-08-20 fourth review, P9).** The figures this table
carried — `4/4 → 5/5`, `7/7 → 7/6`, `4/4 → 6/5` — came from hand repros with a **1-paren** demand
and matched neither the committed fixtures nor each other, so nobody could reproduce them. These
are the committed fixtures (`TAIL_SIBLING`, `ONE_LINE_FORK`, `VALUE_POSITION_ARM` in
`test_patch_text.py`) run through `_place_fuse_arm` with the committed **3-paren** `DEMAND`, with
`sexpr.mark_line` swapped for the pre-fix emitter that appended the marker inline. Code parens,
counted the way `_skip_noncode` counts them.

| fixture | before | naive marker | fixed | what the naive marker costs |
|---|---|---|---|---|
| `TAIL_SIBLING` — `(theCat init:) (theRat init:)` | 4/4 | 7/7 | 8/8 | balanced, so it still compiles — and `(theRat init:)` is still greppable in the file while being **gone from the program** |
| `ONE_LINE_FORK` — `(if T <arm> else B)` on one line | 6/6 | **9/8** | 10/10 | unbalanced: the file does not compile |
| `VALUE_POSITION_ARM` — `(= [local0 0] (theCat init: yourself:))` | 4/4 | 8/8 | 8/8 | **nothing** — the marker is harmless here. This fixture's defect is N1b (the hold lands in the value slot), not the marker, and the old `6/5` implied a paren cost this shape never had |

The population is **not four copies**. Twelve emitters across `patcher` and `trigger` splice
`<edit><marker>` in front of preserved text: the two arming holds, the register/property flip
holds, the flag closer, the prop-flag write, LB2's act flip, the notify-award gate, both
turn-back emitters and both positional gates. All twelve now call **`sexpr.mark_line`**.

⭐ **And LB2 taught the rule its boundary.** The first measured run moved exactly one emitted
file: `dagger/src/rm520.sc`, where TWO act-flip rows conjoin onto the same head, so the second
row's marker is spliced in front of the first row's — and a `strip()`-shaped test called that
"content" and pushed a **comment** onto a line of its own, moving the bytes of a play-confirmed
patch to protect nothing. What a `;` can destroy is CODE. Whitespace and an existing comment are
not at risk; a `{...}` message or a `'...'` Said on the next line is. With that reading the
five-game diff is clean and the rule is stronger, not weaker.

## N1b — a statement is not merely a balanced form

`_arming_statement_span` returned the innermost balanced form containing the arming, which is
routinely an expression in **value position**: `(= [local0 0] (theCat init: yourself:))`,
`(not (self init: param1))`. Wrapping that in `(if <demand> ...)` does not withhold the arming —
it changes what the assignment stores. `sexpr.statement_span` climbs out through value positions
to the enclosing statement (which is what the game's own no-arm path also skips) and returns
None when there is none — an arming performed inside a TEST, which `_enclosing_if_test` already
refuses for the same reason. Body slots are read positionally per head, with the grandparent
distinguishing a `cond` clause `((> a b) (foo))` from a computed-receiver send
`((gInv at: 25) owner:)`, which are identical from inside.

## N2 — a fork is a fork, whatever it is spelled

R2's doctrine is *"the game's own other outcome must stay free"*. `_depth1_else` looks for four
letters, so a `cond` or `switch` standing between the arming and the `if` was invisible and the
search widened straight past the fork it should have stopped at. Reproduced: a `cond` whose arms
init `theCat` and `theRat` puts the demand on the outer `if`, so a player who cannot pay gets
**neither** — the wall R2's own docstring forbids, reached by a different spelling.

⚠️ **The cure is not "any fork disqualifies".** KQ5's shipped `proc550_16` has a `switch global11`
between the `if` and the spawn, and that emission is play-confirmed. The distinguishing question
is the one R2's `else` already answers — **can stock run this arm WITHOUT the arming?** A fork
every arm of which is itself an arming this hold covers answers no, and withholding it is
exactly what the game's own no-arm path does (KQ5: the same cat, positioned per room). A fork
with an arm the hold does not cover answers yes, and that arm is an outcome no row derived. Both
directions are pinned; KQ5's condition and its emitted bytes do not move.

## N3 — the tripwire that could not fire for the reason it names

`test_patch_text.py`'s census asserted "the still-raw scanners have nothing to trip over in this
corpus" over a family that **omitted `(method (`** — the one pattern with hits, named in the
comment three lines above it — and over **four** source trees, not five: both loops listed
`LSL2, KQ4, KQ6, dagger`. So every "five source trees" figure this file has printed was a
four-tree figure.

Fixed, and the assertion split, because a pattern that HAS non-code matches is not a failure by
itself — it is a requirement that every scanner reading it be code-filtered:

* the still-raw patterns must have zero non-code matches (unchanged, and now over five trees);
* the KNOWN-quoted ones must still be found, so the census cannot go quiet the way it just did;
* all five trees must actually have been read.

⭐ **And the remaining raw reader of `(method (` was a second live instance of R1's shape.**
`patcher._guard_travel_dispatch` — the applier that guards KQ6's magic map — picks its `doVerb`
with a raw first-match-wins `re.search`. Driven against a file carrying a `WriteFeature`-style
source generator it reports `applied: True sites=1`, **destroys the message**, and leaves code
parens 15/16. Latent on this corpus only because `WriteFeature.sc` has no `newRoom:` at all.
Now `code_search`, with a behavioural test verified red against the committed code.

Three more copies of the shared taxonomy went with it: `patcher._enclosing_form` (a third
inline copy, carrying the `'`-before-`;` hazard `trigger`'s had), `_recycle_counter_break`'s raw
`(if` scan and inline else-walk, and `wrap_forbidden_case._if_arms`'s raw `rfind("(if")` and
*fourth* else-walk. `depth1_else` now lives in `sexpr.py` with the rest.

## N4 — R4's cure has two error directions, and only one was declared

The two readings of `chain_writes` differ on **exactly one case**, and it is the case R4's own
example is: the register is written, some write satisfies the conjunct and some contradicts it.

| reading | what it does | what it costs |
|---|---|---|
| keep it (**what ships**, R4's cure) | admits an escape that may exist only on the path not taken, at its DISCHARGED price, so `_minimal` prefers it | **the hold ships weaker than the game needs** — F10's failure, in the function written to prevent F10 |
| drop it (before R4) | deletes an escape the game really offers on some path | the demand rises into a wall, or the row vanishes and the softlock ships unguarded |

Neither is a deduction, and **the corpus cannot choose between them**: all 26 KQ5 firings are
`global332 == 7` against the write set `{2, 3, 4}`, where every write contradicts — not
divergent, so both readings agree on all 26 and the shipped demand does not move either way.
R4 is latent here exactly as F1 and F2 were, and so is its reversal.

So the divergence is now **recorded** (`missability._DIVERGENT`) rather than guessed at in
silence, the docstring states both directions, and `test_kq5_ground_truth` pins the measured
fact that KQ5 never asks the question — a game that does asks it out loud, before its hold
ships. Re-measured 2026-08-20: 26 firings, all `global332 == 7` against `{2, 3, 4}`, **0
divergent**.

⏸ **PARKED [USER, 2026-08-20].** The permissive reading ships, deliberately. This is not a red
and not a pending decision — there is nothing in the corpus to decide it with, so it waits for a
game that asks. Three answers were laid out (keep / drop / refuse-the-row-and-report), plus the
real fix, a path-sensitive last-write model. The `_DIVERGENT` tripwire is what makes waiting
safe; ⛔ do not re-raise it, and do not flip it on a derivation.

## Minor list — the four that were open

✅ **`measure_emitted_bytes.py`'s own recipe could not work.** `build/` is gitignored, so the
control worktree has none — and `config` derives every `src_dir` and `ir_path` from the tree it
is imported out of. The control run therefore found no IR for any game, SKIPped all five, and
emitted an empty directory that `diff -r` compared against the real one without complaint: **a
vacuous PASS reading as "byte-identical"**. The recipe now carries the `ln -s "$PWD/build"` line
and a skip is a NONZERO EXIT — this tool may not report success on a measurement it did not make.

✅ **Four assertions that constrain a STRING, not a behaviour.** `"row_site = _ModeSite()" in
open(patcher.py).read()` and a regex over a `def` line (both pass on a comment, fail on a
rename, and cannot tell a threaded site from a variable of that name assigned and never used) →
asserted on the site objects and the signature. `"edits + gedits + uedits" in pipeline.py` → the
mode-UI ROW SHAPE, which is what "unions titles only" has to rest on. And
`test_model_cache.py`'s *"the key covers this directory's source (edit → miss → rebuild)"*,
which asserted `len(src) > 0 and k1 is not None` — **true of any key from any inputs** — now
adds a source file, requires the key to move, removes it, and requires the key to come back.

✅ **The stale `fuse_death_armings` docstring** — it still said rows are emitted once per
`(machine, item)`, which R5 changed, and described the arming as an `init:` send, which R3
changed.

🔴 **`_payable` never asks whether the item is obtainable BEFORE the held arming** — unchanged,
still open, still stated in the docstring rather than papered over.

## ⭐ AND THE CURES HAD THREE DEFECTS OF THEIR OWN — all three caught by measuring, not by reading

Third round, same lesson ([[review-the-fix-not-only-the-feature]]). Two of these shipped green
in the first GREEN commit and were found only when the *next* change made them visible.

**1. `form_chain` closed a form at a SIBLING's parenthesis.** The single-pass version recorded a
chain level's end at the first `)` that returned the scan to that depth — but a sibling opening
and closing *after* the level closed returns to the same depth, so the end was overwritten with
the sibling's. `(a (b (c) (d)) (e))` reported `(b (c) (d)) (e)` as the form at offset 3. The two
appliers then computed overlapping holds and **refused whole**. Caught by the existing
`test_fuse_arm_holds_the_if_that_spawns`, which is what it is for.

**2. `statement_span` read a `cond` clause by its parent's HEAD** — which is right for
`((> a b) …)` and `(57 …)` and wrong for KQ5's own spelling, `(local2 (= local2 0) (proc0_10 71)
(self setScript: bringCedric))`, where a bare variable test is indistinguishable from a send. So
the walk climbed out of the clause, past the `cond`, and returned **the whole fork** as the
arming statement. Measured: `kq5/src/rm046.sc`, the one emitted file that moved, with the guard
wrapping seventy lines instead of one send. ⚠️ **This one was already in the first GREEN commit**
— invisible there only because KQ5's fuse-arm site takes the conjoin path, not the statement
wrap. The grandparent decides now, whatever the parent's head looks like.

**3. An arming inside a TEST got the enclosing `if` as its "statement."** The docstring claimed
None for that shape and the code returned `(if …)`. Holding *that* changes which branch runs,
which is the very thing `_enclosing_if_test` refuses — so the first BODY-BEARING parent now
decides and may say no: a form in a leading slot (an `if`'s or `while`'s test, a `switch`'s
dispatch value, a `cond` clause's test, a method's signature) has no statement of its own.
Caught by a fixture written for the previous fix.

All three now have regression guards: `test_form_chain_is_the_nesting_and_nothing_else` and
`test_statement_span_climbs_out_of_value_positions_only`.

**And the same rule reached `trigger.wrap_trigger_in_source`** — the arm-event wrap, the
workhorse placement — whose own expansion was still "the innermost balanced form", the exact
shape N1b is about, with a raw `setScript:` scan feeding it. Both closed, and re-measured:
**byte-identical on all five games**, so every arming site in this corpus was already a
statement. The `_arming_statement_span` docstring's claim that the two use the same rule is now
true.

---

# THE FOURTH REVIEW (2026-08-20) — the third round's cures, same mandate

Over `6aa0a1d..c89f378`. **12 findings, none CRITICAL. Three are mine, from the round that was
fixing the round before it** — fourth time running ([[review-the-fix-not-only-the-feature]]).

## ⭐ WHAT IT CONFIRMED INDEPENDENTLY — it took nothing on trust

It rebuilt **both** emitted trees itself (a `6aa0a1d` worktree and HEAD) and got an empty
`diff -rq`, 1,084 `.sc` files. It ran the suite: `691 passed, 1 known-red, 0 unexpected, 0
crashed`. It re-derived 780/774 one-line `(if …)` forms, the two quoted `(method (` hits, KQ5's
26 falsifying answers, and 3,303/3,303 `setScript:` sites already resolving as statements. And
it **mutation-tested every new regression guard** — reverting each guarded change in a scratch
copy — and every one of them goes red. The round's central claims hold.

Two useful measurements it added: **117** markers are emitted across the five games and **none**
has a paren after it on its line, while **610 of 4,959 (12.3%)** real form-end splice points
*would* need the push — so `mark_line` removes a substantial class rather than a hypothetical
one. And **165** `init:`-bearing sends in the corpus are places where `statement_span` and the
old innermost-form rule differ, in real room scripts (`dagger/rm460.sc`, `KQ6/rm450.sc`,
`KQ6/slaveWomenScr.sc`), not only in dev tools.

## The findings

| # | Finding | Where | Sev | Status |
|---|---------|-------|-----|--------|
| P1 | the arm-event wrap SILENTLY DROPS an arming site `statement_span` cannot resolve and still reports `sites: n` — the sibling applier refuses whole for the same rule | `trigger.py:1582` | HIGH | ✅ **CURED** (red→green), **+ a second half I found**: nested arming statements corrupted the splice |
| P2 | the `setscript` branch of the SAME function still uses the raw scan + innermost-form rule — "Now they do [use the same rule]" is false | `trigger.py:1476` | MED-HIGH | ✅ **CURED** (red→green), **+ a third half**: two verbs in one handler collapsed to one wrap |
| P3 | `QUOTED` exempts `(method (` from the census while **twelve** raw scanners still read it | `test_patch_text.py:1038` | MED-HIGH | ✅ **CURED** — **thirteen**, all converted; the exemption is now a checked obligation |
| P4 | the `co_varnames` check no longer catches un-threading `site=row_site` — the same weakness its own comment criticises | `test_mode.py:331` | MED | ✅ **CURED** — AST check that mutation-tests itself; no product defect under it |
| P5 | `_enclosing_if_test` climbs outward past an INNER `if`'s `else` when the arming sits in that inner `if`'s test | `patcher.py:3300` | MED | ✅ **CURED** — see below |
| P6 | the `_DIVERGENT` tripwire reads KQ5 only, short-circuits on the first falsifying conjunct, and has no anti-vacuity check | `missability.py:2519` | MED | ✅ **CURED** — all three; ⛔ N4 itself untouched |
| P7 | `test_model_cache` writes a `.py` into the LIVE `src/`, changing every game's cache key for the duration | `test_model_cache.py:109` | MED | ✅ **CURED** — `_model_cache_key(here=...)`, probing a copy |
| P8 | the pipeline-union check was deleted and its replacement is vacuous on the only input the test provides (a SKIP row) | `test_mode.py:249` | LOW-MED | ✅ **CURED** — a second mini project with a menu bar makes the chooser LAND |
| P9 | three more four-tree figures still labelled "five trees" — in the very file N3 was about | `test_patch_text.py:731,957`, `trigger.py:1278` | LOW | ✅ **CURED** — **all eight** family figures were four-tree, plus 562→780 |
| P10 | `skip_noncode` ignores the `\}` escape its own lexer honours — 8 corpus messages end their span early (0 parens, 0 `;`, 0 `{` leak, so nothing moves) | `sexpr.py:225` | LOW | ✅ **CURED** — benignity re-derived first (80 chars, 0/0/0), then fixed |
| P11 | a magic `-40` byte offset assertion; `_turnback_emit(region=None)` defaults back to the UNSAFE marker; a stale "still-raw scanners" comment | mixed | LOW | ✅ **CURED** — all three, **+ the `-400` next door** |
| P12 | `until`/`switchto` have zero corpus occurrences, and `switchto` is in `_FORKS` *and* `_BODY_HEADS`, which disagree about its arms | `sexpr.py:334` | LOW | ✅ **CURED** — not a contradiction, but an unverified reading; documented + tripwire |

## ✅ ALL TWELVE WORKED (2026-08-20, this session) — and what it cost to check them

**Measured, both gates:**

* **Emitted bytes: BYTE-IDENTICAL across all five trees** (LSL2, KQ4, KQ6, dagger, kq5; 1,084
  `.sc` files, 57 carrying a guard), against the `6aa0a1d` baseline in `/tmp/emit_pre`. Every
  `src/` change this session — P1, P2, P3, P6, P7, P10, P11 — closes a shape rather than moving
  an emission.
* **Suite: 718 passed, 1 known-red, 0 unexpected, 0 crashed** (1,051s). ⛔ NOT a clean bill of
  health: F6 is still open and declared. 693 → 718 is +25 new checks.

**⚠️ One scare, and it was mine.** An early `diff -r` after P1's cure showed the KQ4 whale guards
REMOVED from `Room31.sc` — a golden, play-tested emission. It was a half-written tree: I diffed
while the background emit was still on KQ4. Re-derived directly on `build/kq4/src/Room31.sc`
(both `whaleActions` armings resolve to statements, neither refusal can fire) and the completed
run agreed. **Never diff a tree that is still being written.**

**Three defects the review did not file, found while reproducing the ones it did** — the
[[review-the-fix-not-only-the-feature]] pattern, fifth time running:

1. **P1's second half.** Two armings whose statements NEST were spliced in reverse document
   order, which is safe only for disjoint spans: the outer span's end offset goes stale after the
   inner wrap and the splice cuts mid-identifier (`setScript: wh` / `aleActions)`). It reports
   `n=2, applied: True`, and it passes a raw paren count, which is why the count is not the test.
   `_place_fuse_arm` refuses this too; the same port dropped both refusals.
2. **P2's third half.** `find_all_armings` fans out per (instance, method), but `patcher.py:3138`
   skips any extra arming matching the primary's instance AND method, and the branch itself took
   `re.search`'s first match — so one handler arming one machine under two verbs shipped guarded
   on one verb and open on the other. ⛔ The "160" printed here was DEFINITIONLESS and does not reproduce -- P9's own sin, in the paragraph reporting P9's cure. Definition: `(method (` forms (code-filtered, spanned with `_block_span`) holding two or more code-filtered `setScript: <name>` sites naming the SAME target, any receiver. Under it, five trees: **161** (requiring the same RECEIVER too gives 146).
3. **A second magic offset** beside P11's, `out.index("(Refuse)") > out.index("put: 19 1") - 400`,
   satisfied by almost any arrangement of the file.

**And two figures that only became checkable once something counted them:** P6's `_FIRINGS`
counter shows KQ5 puts **39** questions to `_falsifies` in one `guard_specs` pass, not 26 — 26
are `global332 == 7` vs {2,3,4} (the shape the argument rests on, correctly quoted all along) and
**13 more are `global464 != 0` vs {1}**, which nothing had ever counted. "Every firing is
`global332 == 7`" was two thirds of the picture.

**⚠️ Coverage note, reported loudly:** the N4 tripwire now runs on all five games but only KQ5
reaches it. KQ4/LSL2, KQ6 and LB2 each ask `_falsifies` **zero** questions, so their new checks
pass VACUOUSLY today. That is a fact about those games, not a clean result, and the `[n4]` line
each of them prints is what makes it visible.

## P1, reproduced

Two armings of the same machine in one `init`, one of them in a test position:

```
arming sites in the source: 2   sites reported: 1   both held? False
```

`statement_span` returns None for the test-position site and the loop skips it with no `why`;
`n` counts only what was wrapped, and the row reports `applied: True`. That is findings #4 and
#8's shape — a guard on one door while the player walks through the other — and it is exactly
what `_place_fuse_arm` refuses whole for (`patcher.py:3435`: *"The invariant is EVERY arming
site or none"*). The N1b rule was ported into `trigger` without its refusal, so the failure mode
moved from LOUD (a broken build) to SILENT. **Latent**: 0 of the corpus's 3,303 `setScript:`
sites are in a test, but 157 `init:` sends are.

## ✅ P5 — CURED, one line [USER, 2026-08-20]

Reproduced: `(if (== global5 1) (if (self setScript: capture) (foo) else (bar)))` puts
the demand on the OUTER test, so a player who cannot pay gets neither `(foo)` nor `(bar)`.

First ruled COMMENT-ONLY — *"I feel uneasy about #5. let's just put a comment there on the code
and not invent some walking upwards that is not currently exercised"* — then reversed once it
was clear the cure REMOVES an outward climb rather than adding walking: the `continue` at the
"pos is inside this candidate's test" case became `return None`, so an outer `if` found earlier
in the scan can no longer stay `best`.

⛔ Why a REFUSAL is the right answer and not a wider scope: an arming evaluated while a test runs
cannot be held by that test without duplicating it, and no ENCLOSING test can hold it either —
suppressing it changes the value the test computes, so the hold would decide which branch runs
rather than whether the arming fires. `_place_fuse_arm` was already immune (`statement_span`
refuses first); `_place_capture_arm` calls `_enclosing_if_test` with no statement check and was
not.

**Measured**: of **9,508** arming candidate sites across the five trees, the answer changes at
**6** — every one of them inside SCI's own dev tools (`DialogEditor.sc`, `PolyEdit.sc`,
`WriteFeature.sc`, in KQ6 and LB2), which no placement touches. Emitted trees byte-identical;
suite **693 passed, 1 known-red, 0 unexpected, 0 crashed**.

## What it could NOT verify

* **"76 `init:` sends carry text after them on their line"** — it gets **79** under three other
  readings. Re-measured under the original definition (a `code_finditer` `init:` send whose
  `_balanced_span` end is followed by non-blank text on the same line): **76**, exactly. The
  figure is DEFINITION-SENSITIVE and the comment does not say which definition, so it is not
  checkable as written. Fix the comment, not the number.
* **The paren figures "7/7 → 7/6" and "4/4 → 6/5"** — re-measured: the committed fixtures are
  `TAIL_SIBLING` 4/4, `ONE_LINE_FORK` **6/6**, `VALUE_POSITION_ARM` 4/4, with a 3-paren `DEMAND`.
  The doc's "7/7 → 7/6" came from a hand repro with a 1-paren demand and matches NEITHER; that
  hand repro measured 7/7 → **8/7**. The deltas are right and the printed numbers are not.
* **Nothing ran under ScummVM.** Every "the emitted program behaves correctly" statement in this
  document is source reading plus paren/comment arithmetic, not a play test.
