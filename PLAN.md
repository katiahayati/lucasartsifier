# Plan: Automatic softlock detection & patching for Sierra SCI/AGI games

## Context

Sierra adventure games (LSL2 = SCI0) are infamous for **"walking dead" states**: you keep
playing, the game accepts input, but victory has *already* become impossible — e.g. boarding
the cruise ship without sunscreen bought earlier in LA, or missing the boat's departure timer.
Goal: a tool that **automatically finds every way to become permanently stuck** in a game we
own (running under ScummVM) and, in a later phase, **ships drop-in patches** that neutralize
those traps. It must need **no or minimal user input**, and the core must **generalize** across
the SCI/AGI family, prototyped on LSL2 first.

The problem is a **graph/planning property**, not a game event. This plan reflects two design
corrections from the user:
1. **Winning ≠ max score.** Victory = reaching the *good (non-death) ending state*. Score is
   only a search heuristic (potential-based shaping), never the win oracle. Assume a single
   winning terminal (ignore graded endings like QFG/KQ6 for now).
2. **Do not search over parser commands.** Everything is gated on **item ownership (incl.
   quantities like money) and game-state flags** (`boat_left`, `person_offended`, …). Locations
   expose *opportunities* to acquire items / flip state. We model that item+flag+location state
   and its transitions — the parser layer is lifted away.

Project directory: `/home/hayati/coding/sierra_softlock/`.

## Core model (the reframe)

Treat the game as a **planning domain / transition system** auto-mined from its scripts:

- **State** = `{ items owned (bool) , resource quantities (bounded int, e.g. money) ,
  flags/enum state , current location }`. (Cosmetic/graphics/animation state excluded — see COI
  slicing.)
- **Opportunities** = guarded transitions read off each location's handlers, lifted to their
  *effect* and stripped of the parser string:
  `at(drugstore) ∧ money≥cost  →  acquire(sunscreen), money−=cost`.
- **Automatic/timed transitions** = first-class edges that fire without player action when a
  per-cycle counter crosses a threshold (this is where "board within X turns → `boat_left:=true`"
  lives).
- **Irreversible edges** = effects no other transition can undo (gate flag set, item consumed
  with no re-source, location made unreachable).
- **Goal** = the winning ending state.

**Softlock** = a state that is *reachable* ∧ *not a death* ∧ from which the *goal is
unreachable*. We report the **frontier edges** (goal-reachable → goal-unreachable) plus the
**distinguishing predicate** (which item/flag/quantity flips winnability) and *where that
resource was last obtainable*. The six canonical Sierra patterns are one detector + a tag:
missing-prereq-before-gate · timed gate · consumed/limited resource · one-shot NPC/event ·
sealed area with needed item inside · economy (spent below a required cost).

## Architecture

**Engine-agnostic core over a per-engine front-end.** The analysis operates on an abstract
transition-system IR; each engine produces that IR.

```
[per-engine front-end] → Transition-System IR → [COI slice] → [reachability/frontier] →
   → [engine-in-the-loop verification] → softlock report → (phase 2) drop-in patch synthesis
```

### Front-end: extract the transition system  (LSL2 / SCI0 first)
Mine opportunities + automatic transitions from the game scripts:
- **SCI (LSL2):** decompile/disassemble room scripts (SCICompanion / ScummVM `disasm`,
  `dissect_script`). Enumerate every site that grants/consumes inventory (`Inv`/`InvItem`
  `owner`), sets a global/flag, `changeScore`, or `newRoom`, together with its guard (the
  conditions on items/flags/globals gating that handler). Room number = **global 13**
  (`EngineState::currentRoomNumber()`), score = **global 15**; max-score global is game-specific
  (read live). Parser handlers are located via the `said` opcode + `vocab.000`; **we keep the
  effect, discard the string.**
- **AGI (generalization target):** far cleaner — state is a bounded vector (256 flags + 256
  vars + inventory `OBJECT` table). Reserved indices are uniform: `v0`=room, `v3`=score,
  `v7`=max, `f5`=new-room. Decompile with **agikit** (`extract`); opportunities are fixed-arity
  opcodes (`get/drop/put`, `set/reset`, `assign*/add*`, `new.room`) with immediate operands.

Automatic/timed edges: detect per-cycle counter increments compared to a threshold that triggers
`newRoom`/flag (static pattern), cross-checked dynamically by idling in a room and observing what
state changes on its own.

### COI slice: keep only winnability-relevant state
Cone-of-influence / backward program slice from the **goal guard, death guards, and irreversible
transitions** through the guards/effects. Yields the small set of items/flags/counters that can
influence winnability; everything else is dropped. This is the single biggest tractability lever
(most of an SCI heap is irrelevant to solvability). Slice **conservatively** (over-approximate the
relevant set) to avoid dropping a variable that matters.

### Goal identification (minimal input)
Auto-detect the ending: a terminal state reachable that is *not* the death modal (the
Retry/Restore/Quit `Print` dialog is heuristically detectable; death rooms have no score gain and
no progress edges out). Present the top candidate(s) for a **one-time human confirmation** — the
only required user input. Optionally accept an existing walkthrough as a reachability sanity check.

### Reachability & frontier detection
Explicit-state reachability over the sliced state (items+flags+counters+location):
- `Reachable` = forward-reachable from start.
- `CanWin` = backward-reachable from goal.
- **Softlock candidates** = `Reachable ∧ ¬CanWin ∧ ¬death`; report the **frontier edges**
  (`CanWin → ¬CanWin`) with distinguishing predicate, minimal witness path to the frontier, the
  missed opportunity + its last-available location, and the pattern tag.
- Savestate-hash the *sliced* state to dedupe (transposition table). Irreversibility makes the
  macro graph a near-DAG, so this converges fast. Off-the-shelf planners (Fast Downward reporting
  `unsolvable`) are an option once the domain is emitted in PDDL.

### Engine-in-the-loop verification (the trust anchor)
For each candidate, verify against **real ScummVM** so findings don't depend on
perfect decompilation: use in-memory `gamestate_save`/`gamestate_restore` (stream overloads → no
disk I/O) to snapshot at the frontier, then confirm the goal is unreachable there, and that
restoring the missing resource (write the global/flag/inventory byte via the console
`vmvars`/`setflag`/`vmflags`/`setobj`) makes it reachable again. Kills false alarms from
mis-extracted guards/effects.

## Deliverables (two phases, as requested)

**Phase A — Report first (validate detection before touching anything).**
A machine-readable softlock catalog: for each trap → `{ location/edge, cause predicate (missing
item/flag/quantity), pattern tag, minimal reproduction path, where the resource was last
obtainable, engine-verified: yes/no }`. This is the checkable artifact; a human eyeballs it
against known LSL2 dead-ends (sunscreen-before-boat, boat timer, lifeboat items).

**Phase B — Shippable drop-in patches (separate phase).**
For each *verified* softlock, synthesize an SCI resource patch dropped into the game folder
(`NNN.SCR`+`NNN.HEP`, or SCI0 `script.NNN`) that ScummVM loads in preference to the packed
resource — **no engine rebuild, original files untouched** (same mechanism as
`engines/sci/engine/script_patches.cpp`, delivered as loose files). Remedy per pattern, least
intrusive first: relax the gate guard · make the resource obtainable after the gate · disable/
extend the timer · auto-grant the resource at the frontier · make the gate reversible. Each
patch re-run through Phase-A analysis to confirm the softlock is gone and no new one introduced.

## Honest scope on "soundness"
The reachability method is sound; the *model extraction* is not perfectly faithful on SCI0
bytecode. Net stance: **high-confidence findings (no false alarms, via engine verification) with
best-effort completeness (via the six patterns + conservative slicing)** — not a formal proof of
"no softlocks exist." AGI, with its bounded 256-flag/var vector and clean decompilers, is where
the method is closest to genuinely sound and is the right place to validate the analyzer.

## Key reused facts / APIs (from research)
- SCI globals: room=13, score=15 (`engine/vm.h`, `state.cpp`); in-memory snapshots via
  `gamestate_save/restore` stream overloads (`engine/savegame.cpp`); console `vmvars`, `room`,
  `send`, `said`, save/restore (`console.cpp`); Said via `said` opcode + `vocab.000`
  (`parser/vocabulary.h`); drop-in patches via `readResourcePatches()` (`resource/resource.cpp`).
- AGI: `VM_VAR_*`/`VM_FLAG_*` (`engines/agi/agi.h`), opcode table (`opcodes.cpp`), console
  `vmvars/vmflags/setflag/setvar/room/objs/setobj` (`console.cpp`), agikit for decompile.
- Prior art: Lester (arXiv:2012.15365) — CBMC assertion "win unreachable" over a real IF game
  (sound reachability precedent); Go-Explore/PBRS for savestate-archived, score-guided search;
  COI/CEGAR/BMC for state-explosion. Auto-coupling detection→patch synthesis appears to be open
  ground.

## Verification of the tool itself
1. **Ground truth on LSL2:** confirm the report contains the documented dead-ends
   (sunscreen-before-boat; boat-departure timer; lifeboat-items) with correct cause predicates.
2. **Engine replay:** for each reported trap, script ScummVM to reach the frontier via savestate,
   assert goal-unreachable, inject the missing resource, assert goal-reachable.
3. **AGI cross-check:** run the same core on an AGI title (e.g. an early KQ/SQ) to prove the
   engine-agnostic IR + analysis generalize.
4. **Phase-B patch check:** apply generated patch, re-run Phase A, assert the specific softlock is
   gone and no regression introduced.

## Open items
- Confirm LSL2's max-score global index and exact inventory object layout live (read via
  `vmvarlist` / `view_object`), plus its death-room and ending-script ids.
- Decide whether reachability runs as a hand-rolled explicit-state search or via emitting PDDL to
  an existing planner (start hand-rolled for tight engine-in-the-loop coupling).

---

## Appendix: research notes carried from the planning session

### ScummVM SCI internals (confirmed against `scummvm/scummvm` master)
- State cell is `reg_t` (segment,offset); ints are `make_reg(0, v)` / `.toUint16()`.
  Globals = script 0's locals (`variables[VAR_GLOBAL]`, count = `getLocalsCount()`, game-specific,
  order ~hundreds for SCI0).
- `enum GlobalVar`: 0=ego, 1=Game, 2=current room OBJECT, 11=currentRoomNo, 12=previousRoomNo,
  13=newRoomNo, 15=score. Authoritative room number is **global 13**
  (`EngineState::currentRoomNumber()` reads index 13). Max-score global NOT in the enum — verify
  per game (do not assume 16).
- Inventory is script-level: `Inv` collection of `InvItem` objects; "in inventory" ≈ `owner==ego`.
- Console: `vmvars`/`vv`, `vmvarlist`/`vl`, `room`, `send`, `said`, `parse`, `disasm`,
  `dissect_script`, `save_game`/`restore_game`. Savestates: `gamestate_save`/`gamestate_restore`
  with `WriteStream*`/`SeekableReadStream*` overloads → in-memory snapshot/restore (no disk),
  cost O(live heap), no incremental/COW.
- Vocab: SCI0 main=vocab.000, branches=900, suffixes=901; word = (class bitflags, group id).
  `Said` tokens: `,`=0xf0 (OR), `/`=0xf2 (part sep), `[ ]`=optional, `<`/`>` semantic/no-claim.
  Said specs are embedded as operands of the `said` opcode → per-room command set is statically
  extractable (then lifted to effects and discarded).
- Patching: `engine/script_patches.cpp` = in-memory match/replace (`SIG_*`/`PATCH_*`,
  `SciScriptPatcherEntry{active,scriptNr,desc,applyCount,sig,patch}`), applied after load, files
  untouched. Drop-in loose patches: `readResourcePatches()` loads `script.NNN` (SCI0) or
  `NNN.SCR`+`NNN.HEP` (SCI1+) from the game dir, priority over `resource.000`. Death = script-level
  Print modal (Retry/Restore/Quit), no death kernel → detect heuristically; restart via
  `kAbortRestartGame`.
- No LSL2-specific softlock entry currently in `script_patches.cpp` (LSL1/3/5/6 have some) → LSL2
  is open ground.

### AGI internals (confirmed against `engines/agi/` + AGI Specifications)
- State is a bounded vector: 256 vars (bytes) + 256 flags + `OBJECT` inventory table
  (item→room byte; 255 = carried by ego) + screen-object records.
- Reserved vars: v0=current room, v1=previous room, v2=ego border touched, v3=**score**,
  v6=ego direction, v7=**max score**, v9=word-not-found, v10=time delay, v11–v14=clock. Reserved
  flags: f2=command entered, f4=said accepted, f5=**new room first exec**, f6=restart. (Border
  vars v4/v5 naming is ambiguous between Kelly spec and ScummVM symbols — verify if load-bearing.)
- Opcodes: `said`=0x0E (count + 2-byte WORDS.TOK group ids; group 0=noise, 1=anyword,
  9999=rest-of-line). Inventory: `get`0x5C/`drop`0x5E/`put`0x5F/`has`(cond)0x09. Flags:
  `set`0x0C/`reset`0x0D. Vars: `assignn`0x03/`addn`0x05/`increment`0x01/`decrement`0x02.
  Rooms: `new.room`0x12 / `new.room.v`0x13 (sets v1←v0, v0←n, f5). Score = writes to v3.
- Tooling: **agikit** (`extract`/`build`, scriptable) best for static extraction; WinAGI / QT AGI
  Studio alternatives. No drop-in patch format → fix by rewriting LOGIC (agikit) or runtime shim.
- Console: `vmvars`/`vmflags`/`setvar`/`setflag`/`vars`/`flags`/`room`/`objs`/`setobj`. Savestates
  supported. AGI is the cleaner analysis target (fixed uniform vector; no heap) → validate the
  analyzer here first.

### Prior art (verified)
- **Lester, arXiv:2012.15365** (WPTE 2020): compile IF game to C, assert "win reached", ask CBMC
  to prove the assertion unreachable; failure → counterexample = a winning walkthrough. Direct
  precedent for sound win-reachability + auto-walkthrough; the dual is softlock detection.
- Jericho (arXiv:1909.05398) exposes `get_score`/`max_score` — parser IF remains unsolved by
  learned agents (blind command search is intractable → why we model item/flag state instead).
- TextWorld guarantees winnability by construction (white-box); PDDL solvability = planner
  `unsolvable`; PBRS (Ng/Harada/Russell 1999) justifies score-as-heuristic without changing the
  optimum. COI slicing / CEGAR / BMC / savestate-hash (Go-Explore, Klondike solver
  arXiv:1906.12314) are the state-explosion mitigations. Coupling auto-detection → auto-patch
  appears unpublished (novel contribution).
