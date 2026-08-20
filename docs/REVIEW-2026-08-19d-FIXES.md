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
