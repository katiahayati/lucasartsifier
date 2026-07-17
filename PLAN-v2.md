# Plan v2 — read the game, don't reinvent it

*Supersedes the architecture in `PLAN.md` (the goal is unchanged: find walking-dead
states in SCI games, and neutralize them). Written 2026-07-16 after an xhigh review of
`semantic-core-machine-lift` found 15 defects, nearly all of them in code that
hand-reimplements things the game already states.*

## The diagnosis

We are solving **the SCI problem**, not a theoretical one — but we have been solving it
by hand-building three layers that already exist, and hand-guessing a fourth that is
written down in the source tree we parse.

The evidence, all of it from this repo:

- **`Actor.sc:608` defines `has:`** as `((gInventory at: X) ownedBy: self)`. We hardcode
  `OWN_SEL = "has"` as a magic selector and render `ownedBy` as an opaque atom — then
  "discover" it months later with a statistical census. They are the same thing, and the
  source says so in four lines.
- **`System.sc:300` defines `Script::doit`** — it decrements `seconds`/`cycles` and cues.
  That is the cue mechanism `machine.py` reconstructs as a hand-written whitelist.
- **`System.sc:321` defines `Script::init`** as `(self changeState: start)`. We hardcode
  entry state **0**. `start` is a property. Any Script with a non-zero `start` is wrong
  today, and no test would notice.
- **`.sco` files** ship the class hierarchy and per-class selector tables
  (`Feature → View → Prop → Act → Ego`). We infer property-vs-method with a "read as
  `p?`, written as `p:`" heuristic instead.
- **`model.py:715`**, our own comment about the class library: *"They carry no rooms, so
  they stay inert."* They carry the semantics.

And the parts that aren't extraction are textbook:

| layer | what it is | status |
|---|---|---|
| front-end | `.sc` + `.sco` + selector table → object model | **solved** (sci-tools); we hand-roll it |
| dictionary | `System.sc`/`Actor.sc` method bodies → semantics | **shipped**; we guess it |
| extraction | compose conditions along control flow → guarded transitions | a compiler pass; **the real work** |
| winning set | backward fixpoint from the goal → winning region | model checking; **solved** |
| synthesis | disable controllable exits → supervisor | Ramadge–Wonham; **solved** — and `patch.py`'s docstring already names it |

`main` had the right architecture (graph + reachability + supervisor) and the wrong gate
model ("an `OWN` guard is mentioned here" ≠ "you need it here" — which is how it demanded
the fatal Spinach_Dip). `semantic-core-machine-lift` fixed the gate model and dismantled
the architecture: it put an interpreter (`machine.py`) *inside* the fixpoint, and paid for
it with a cache-key bug that deleted a room, a permissive fall-through that deleted a real
softlock, and a test suite that pinned one of the bugs in as ground truth.

**Target: main's architecture, this branch's gates, and no hand-written semantics.**

## The rule that prevents a repeat

> **If the game states it, read it. Never transcribe it into a whitelist.**

Every deep bug of 2026-07-16 was a hand-transcription of `System.sc` or `Actor.sc`, done
from memory. A whitelist entry is a bug with a delay fuse.

Corollary: **ignorance must be measured, not assumed.** `OPAQUE → UNKNOWN → permissive` is
the safe direction, which is exactly why it is silent: no error, no test failure, no
warning — it just answers "sure, you can win". LSL2 carries 2036 unread conditions and KQ4
3212, and nothing counted them for a day. `src/coverage.py` now does; it stays, and it
runs on every build.

## Phases

Each phase must leave `python3 src/_check_core.py` green. It is the contract, not a
formality — the rewrite is only legitimate if the findings survive it.

### Phase 0 — freeze the acceptance criteria
The current findings become the spec, so the restructure is measurable rather than
hopeful:

```
LSL2   rm26->rm27    Sunscreen          rm38->rm131  Wig
       rm26->rm27    Grotesque_Gulp     rm38->rm131  >=1 of {Fruit, Sewing_Kit}
       rm47->rm48    Knife              rm79->rm80   >=1 of {Sand, Ashes}
KQ4    rm31->rm44    iFeather
both   sanity PASS (LSL2 85/100, KQ4 89/106)
```
Plus the negatives, which are the ones that actually encode understanding: the fatal
Spinach_Dip appears in **no** clause; Fruit and Sewing_Kit do **not** strand
individually; `rm101->rm11` and friends carry no activator guard; the debug scaffolding
stays pinned off.

Also add the assertions we know we are missing, as **expected failures** — they are the
scoreboard for phases 3–4:
- KQ4: shooting the unicorn twice must strand Lolotte (`iCupidBow.loop`).
- LSL2: the parachute; the plane door (`Bobby_Pin`).

### Phase 1 — the dictionary: read the class library
Parse the method bodies we currently mark inert and derive the semantics instead of
asserting them:

- `Actor::has` → possession is `ownedBy: self`. **Deletes `OWN_SEL` and unifies `has:`
  with `ownedBy`** — one channel, not two.
- `Script::doit` → `seconds`/`cycles` are deferred cues.
- `Script::cue` → `changeState: state+1`.
- `Script::init` → `changeState: start` (**a property**, not 0).
- `Actor::cue`/`Game::cue` → forward to `script`.

Replace `machine.py`'s whitelist with this. Acceptance: findings unchanged, and `start`
comes from the object rather than a constant.

### Phase 2 — the front-end: stop hand-parsing
Adopt `sci-tools` (already a standing decision in the notes — never wired up) and/or read
`.sco` for the class hierarchy and selector tables. Kills the `game.sh` regex, the
property-vs-method heuristic in `coverage.py`, and the two-decompiler-dialect seam.
Acceptance: both games load; findings unchanged.

### Phase 3 — extraction: compile machines to guards  ✅ **GO — measured, and it is cheap**
> The hedging below was wrong three times over; the measurement is in "Phase 3
> reconsidered". Short version: **0.4 seconds for the worst machine in either game**,
> the formula is small, and it captures the non-monotone trap that `requirements()`
> structurally cannot. Do it.

**A machine must not be a runtime component.** Compute the weakest precondition of each
exit *once*, at extraction, and emit a formula:

```
edge(rm138, rm42) requires  sunscreen ∧ wig ∧ gulp ∧ (fruit ∨ kit)
```

This deletes `Machine.project`, the `_mcache` (and its room-deleting key bug), and the
per-closure re-interpretation that made `strandings` need 1400 closures to rediscover a
formula the WP hands over symbolically. `control_exits` survives in spirit: a machine we
cannot compile falls back to the flat edge rather than inventing a dead end.

#### Phase 3 reconsidered — what the measurement says

The sentence *"a formula the WP hands over symbolically"* was written confidently and is
not true. **The raft is a loop** (`3→4→5→6→7→4`, exiting at `day ≥ 9`), and the weakest
precondition of a loop is a loop-invariant problem. It is only tractable here because the
counter is bounded — i.e. by **unrolling**, which is not "symbolic", it is enumeration
wearing a hat.

The tractable version is a **truth table over the machine's own atoms**: collect the
distinct `OWN`/`FLAG`/`CMP` atoms a machine's guards mention, enumerate assignments, run
the machine per assignment (counters stay concrete and internal), and record which exits
are delivered. Measured atom counts, both games:

```
LSL2   29 gating machines, worst: rm34 (13 atoms), rm138 (8), rm82 (7)
KQ4    43 gating machines, worst: rm79 (6), rm54 (6), rm91 (5)
```

So it is bounded — 2¹³ = 8192 runs worst case, once — but note what it yields: a **DNF of
up to 2ⁿ terms**, not the tidy `sunscreen ∧ wig ∧ gulp ∧ (fruit ∨ kit)` above. Getting
*that* needs simplification (Quine–McCluskey or similar).

**And `requirements()` already produces the readable CNF, by search.** So the payoff the
phase was sold on — "get the guard formula for free" — mostly does not exist. What Phase 3
actually buys is narrower and still worth something: **machines stop being a runtime
component**, which deletes the bug farm (`_mcache`, `project`, the room-deleting key) and
makes Phase 4 a change to one flat loop instead of a change to an interpreter.

**And Phase 4 does not depend on it.** Promoting registers into the current closure is
invasive but self-contained: `rooms` becomes a set of `(room, regvals)`, the machine's
`run` takes the registers, and the cache key gains them. So the 3→4 ordering in this plan
rests on an architectural preference, not a dependency.

#### Then it was actually measured, and the hedging above was wrong three times over

**1. The cost is nothing.** "8192 runs worst case" was presented as if it were a burden.
It is **0.4 seconds**, once, for the worst machine in either game:
```
rm138.rm138Script:  8 atoms ->  256 runs in 0.1s
rm34.rm34Script  : 13 atoms -> 8192 runs in 0.4s
```

**2. The DNF blowup does not happen**, because the *function* is small even when the atom
count is not. Filtering to atoms whose value can actually change the answer:
```
rm34: only  4 of 13 atoms are RELEVANT
rm138:      7 of 8, and they are precisely the raft gauntlet --
            sunscreen==1, sunscreen==3, wig, own(8) gulp, own(13) dip,
            own(12) kit, own(11) fruit
```
18 of 256 assignments reach rm42, which is exactly
`(s1 ∨ s3) ∧ wig ∧ gulp ∧ ¬dip ∧ (fruit ∨ kit)` times the one irrelevant atom. The truth
table recovers the gauntlet exactly.

**3. IT SOLVES THE NON-MONOTONICITY PROBLEM — the one "open problem" below.** Of the 18
assignments that reach rm42, the Spinach_Dip is held in **0**. The extracted guard
*requires not holding it*. A truth table makes no monotonicity assumption: it asks "does
this assignment reach the exit?", and carrying the dip is death, so those rows simply do
not satisfy. `requirements()` can never say this — `_atom3` answers UNKNOWN for
`(not (ego has: X))` precisely because the fixpoint is monotone in items.

So Phase 3 is **not** "architecture with no findings payoff". It is cheap, it deletes the
bug farm, **and it is the only mechanism we have that can express a trap item.**

Lesson for whoever reads this: every number in the original hedge was invented. The user
asked "so the worst complexity is 8192 runs?" and the whole objection collapsed in one
measurement. Measure the plan, not just the code.

Output is a flat transition system: `transition(from, to, guard, effects, controllable?)`.
Movement, `get:`, and `put:` are all transitions — which folds `consumable_strandings()`
back into the general case instead of leaving it as a bespoke twin of `requirements()`.

### Phase 4 — promote registers and counters into the state
Four symptoms, one bug: "the set of values a global can ever take" is the wrong
abstraction for anything **counted** or **moded**.

| | today | consequence |
|---|---|---|
| `day` (raft) | promoted by `machine.py` | works — and is why the sunscreen is found |
| `iCupidBow.loop` | opaque | Lolotte's castle invisible |
| `gIslandStatus` | set-of-values | the wedding gate is vacuous |
| `gCurrentStatus` | set-of-values | the parachute is invisible |

Promote them into the location state. Chosen **by `coverage.py`**, not by hand.

The candidates fall out mechanically (compared with `==` against ≥3 distinct literals,
and assigned ≥3 distinct literals):
```
LSL2   gCurrentStatus 35 · gCurrentEgoView 9 · gIslandStatus 8 · gWearingSunscreen 3 · gBombStatus 3
KQ4    newRoomNum 13 · ghostRoomNum 8 · frogPrinceState 4 · ogreState 3
```

> **⚠ THE SIZING BELOW WAS WRONG — MEASURED 2026-07-17.** "~25k nodes" is per CLOSURE,
> and it ignores that `requirements()` runs **~373 of them**. Measured on the current
> code: one closure is **9 ms** over 85 rooms; `requirements()` is **3.4 s**. Promoting
> `gIslandStatus`(8) × `gCurrentStatus`(35) makes the location space 85 → ~25k, i.e.
> **~300× per closure**, i.e. ~2.6 s each, i.e. **~16 minutes** per `requirements()` run.
> Add `gCurrentEgoView`(9) and it is hours. The Petri-net dismissal was right about the
> *state space* and wrong about the *number of times we search it*.
>
> **Decision needed before implementing (do not let an agent pick this alone):**
> - **(a) Promote only the small registers.** `gIslandStatus`(8) alone is 85 → 680 nodes,
>   ~8×, ~27 s for `requirements()`. Feasible today, and it is the one that unlocks the
>   endgame chain (rm84→100, rm92→103, rm75→104, the rm77→rm78 wedding gate).
> - **(b) Make `requirements()` cheap enough to afford `gCurrentStatus`(35).** 373
>   closures is the real cost driver, not the state space. That is a solver problem
>   (incremental reachability, or reuse across the deletion-based MUS shrink), and it is
>   Phase 5's territory — so **5 may need to come before the expensive half of 4.**
> - **(c) Promote per-query.** A register only matters to the edges that test it; promote
>   the ones a given frontier actually reads rather than globally.
>
> The parachute needs `gCurrentStatus`, so it is gated behind (b) or (c). The endgame
> chain needs only `gIslandStatus`, so (a) buys it now.

Note it *restores* monotonicity rather than breaking it: more arrows never hurts. We only
lose the "collect everything, then decide" shortcut on the promoted dimensions.

### Phase 5 — the solver shrinks
With extraction emitting rules, reachability is a plain monotone fixpoint (Datalog-shaped)
and `requirements()` is MUS enumeration (ours is the naive QuickXplain). Keep the CNF
output — `(and (has: 14) (or (has: 11) (has: 12)))` — since it is the shape the supervisor
needs.

### Phase 6 — synthesis: the supervisor, properly
> **⚠ HARD BLOCKER — do not do this unsupervised.** This phase re-enables the code path
> that shipped a patch making LSL2 unwinnable, and moves the validator onto the same
> core. The failure it caused was invisible *precisely because* detector, synthesizer and
> validator agreed with each other. Re-enabling it is a decision about shipping a
> game-modifying artifact, and it needs a human who wants it re-enabled — not an agent
> finishing a task list.
- Winning region by **backward** fixpoint from the goal.
- Disable **controllable** transitions that leave it (`trigger.py` already finds the
  controllable action — that is the controllability partition, hand-rediscovered).
- Uncontrollable exits (timers) make the spec unrealizable → delete them, which is what
  `patch.py` already does under the name "forcing timers".
- **New requirement:** guards over counters, not just item booleans —
  `(< ((Inventory at: iCupidBow) loop?) 1)`. The LucasArts invariant assumes needs are
  *things*; an arrow budget is a *quantity*, and today's patch vocabulary cannot say it.
- Re-enable `patch.py` against this core, and **move the validator to it too** — the
  shipped game-breaking patch happened because detector, synthesizer and validator all
  shared one blind spot.

### Phase 7 — delete `search.py`
Blocked on 3, 4 and 6.

## Open problems (not scheduled — they need decisions, not code)

- ~~**Non-monotonicity.**~~ **LARGELY ANSWERED by Phase 3** (measured): truth-table
  extraction assumes nothing about monotonicity, so `¬own(Spinach_Dip)` falls out of the
  raft's guard by itself. What remains is a *synthesis* question, not an analysis one: the
  supervisor must **deny an acquisition** ("do not pick that up"), and today's patch
  vocabulary only knows how to forbid a MOVE. Same shape as the arrow-budget guard.
- **Geometric gates.** rm82→rm83 is gated by a door Prop's collision against VIEW cel
  geometry. Not in the scripts at any effort. ScummVM-in-the-loop, or declare it.
- **rm44 / rm45 have no entrance** in the decompiled source, so the Matches (the bomb's
  wick) are unobtainable. May be an *input* problem — which is an argument for Phase 2.
- **Mode registers vs. `coverage.py`.** The instrument finds state we do not model. It
  cannot see state we model *badly* — `gCurrentStatus` reads as "covered". Needs a second
  check.

## What carries over

Keep: `_check_core.py` (the contract), `coverage.py` (the instrument), the CNF/minimal
blocking sets, and — importantly — the **semantics knowledge** this branch bought at the
price of 15 defects (cue idioms, entry activation, segments-per-entry, the traps, the
decoys). That knowledge feeds Phase 1; it just should have been read rather than guessed.

Drop: the whitelists, the machine-inside-the-fixpoint, and eventually `search.py`.

## The standing hazards, for whoever picks this up

- **Never classify an item from a subset of its call sites.** Al Lowe planted decoy uses
  on every real item, scoring −5, and they grep first. This went 0-for-4 in one day
  (Bobby_Pin, Hair_Rejuvenator, Sand/Ashes, Swimsuit) — every one caught by the human,
  never by me. Prefer a query to a claim: `W(room, item)` is cheap and has no opinions.
- **A review is not an oracle either.** Four of the xhigh review's suggested *fixes* were
  wrong and would have deleted most of the findings. Measure every cure.
- **Weight the tests over the prose.** On 2026-07-16 the code comments and README verdicts
  were wrong repeatedly while the assertions held — and then the review found the
  assertions were lying too (vacuous, wrong game's config, pinning a bug in as truth).
  The only thing that ever adjudicated was running the code.
