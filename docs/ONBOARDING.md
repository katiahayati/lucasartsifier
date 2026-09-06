# Start here

You are looking at a static analyzer that finds **softlocks** in 30-year-old Sierra SCI adventure
games and ships a patch that prevents them. This page is the orientation: what the thing is, what
shape the work takes, the rules that are not obvious from the code, and where the open edges are.

Read in this order, and stop when you have enough:

| you want | read |
|---|---|
| what the project is, in prose | `README.md` |
| the idea, in one page | `docs/HOW-IT-WORKS.md` |
| what every file does | `docs/ARCHITECTURE.md` |
| how to run the tests, and why some are RED | `docs/TESTING.md` |
| the current state of one game | `docs/<GAME>-*.md` (see §5) |
| **the rules below** | this page — they are the ones that were learned the expensive way |

---

## 1. The shape of the work

There are **three** stages, and they fail independently. Most confusion in this project comes
from a claim about one being heard as a claim about another.

```
   DETECT                      DERIVE                      SHIP
   ------                      ------                      ----
   decompile -> IR             guards.guard_specs          patcher.apply_guards
   abstract-interpret          "what condition, where"     scicompile -> bytes
   missability.<detector>                                  install -> PLAY
        |                            |                          |
   "there is a softlock"     "here is a site to guard"   "the game refuses the move"
```

* A **detector finding** is not a spec. A finding whose shape no spec kind can express ships
  nothing (GK1's R3 and R4 — `docs/SCI2-PATCHING.md` §5.2).
* A **spec** is not a guard. `patcher.apply_guards` returns `applied: False` with a reason when
  it cannot find a site, and **`build_patch.py` prints only the ones that landed** — so read the
  returned edits, not the build log, whenever you want a denominator.
* A **guard** is not a working guard. Only play says that.

Say which stage you mean. "GK1 is done" has been wrong three different ways.

---

## 2. Non-negotiables

These are short because each one is a scar. Where a longer story exists it is in the file the
rule names.

**Nothing is declared; everything is derived.** The start room, the goal, the death signal, the
item ids, the SCI version — all read out of the game's own bytes. ⛔ Never write a rule that
names a game, a room or an item. Never source a guard from an oracle file: the oracles are TEST
data, and a guard derived from one proves nothing. If a rule needs "and keep game X working",
it is overfitted — rewrite it or delete it.

**Measure the EMITTED BYTES, not the source.** The snapshot surface freezes *whether* a guard
landed, never one byte of the text it produced. A placement that moves to the wrong site reads as
"no regression". The control is a worktree at the pre-change commit:

```sh
git worktree add /tmp/pre <pre-change-commit>
ln -s "$PWD/build" /tmp/pre/build          # ⛔ NOT OPTIONAL — no build/, no IR, vacuous PASS
python3 tools/measure_emitted_bytes.py /tmp/pre/src /tmp/emit_pre
python3 tools/measure_emitted_bytes.py "$PWD/src"   /tmp/emit_now
diff -r /tmp/emit_pre /tmp/emit_now && echo BYTE-IDENTICAL
```

**Run the heavy things on the build box, not the laptop.** The dev box is a ~5.8 GB WSL VM; the
six-game emit peaks at 4.7 GB and the full gate takes ~80 minutes serially there. The EC2 box
does the same gate in ~13-15 minutes at `-j8` (771-908 s measured). This applies to the gate *and* to any job that loads
several game models. ⛔ **Stop the box when the result is in hand, and confirm it says
`stopped`.**

**"Agrees with KNOWN_RED" is not green.** `tools/run_tests.py` exits 0 only when the failing set
is *exactly* the declared one — and a declared RED that starts passing is also a failure ("a gap
was closed, promote it"). The runner prints the open-gap count on purpose. Lead with it.

**Never pin a limitation green.** Found a real gap? Write the RED test, declare it in
`KNOWN_RED` with a reason that names the gap, and commit it red. On a branch, freely.

**A refresh is a BLESS.** Goldens, the watched surface and the emission manifest are frozen
records. Present the delta, get a human yes, *then* refresh. Running `--write` to turn a red
green is exactly the failure the manifest exists to prevent.

**Run the control first.** Instruments lie here, repeatedly. Before believing a probe that says
"clean", ask it a question you know the answer to. Real examples from one week:
`scro N` answered "not loaded" for every script and was read as a pass (caught because Sierra's
own scripts gave the same answer); an IR walk "proved" a construct absent by counting **zero of
everything** (caught by counting the common case too); `verify_scripts` passed on a heap that
crashes the interpreter.

**Report coverage changes loudly.** A change in *what is measured* leads the report. An
unplaced spec, a game joining or leaving a gate, an oracle row moving — say it first, and never
reclassify a human-enumerated ground-truth item without asking.

---

## 3. Running things

```sh
# the gate (on the box; ~13 min at -j8)
python3 tools/run_tests.py -j8
python3 tools/run_tests.py toll scopes        # only files matching these names

# one game's patch, end to end -> build/<game>_patch_<tag>/patch
python3 build/build_patch.py gk1 v2

# ⭐ of everything FOUND, how much is actually GUARDED?  (the denominator build_patch hides)
python3 tools/measure_coverage.py gk1 --items

# would these script/heap pairs LOAD?  (ScummVM's own Script::init checks, transcribed)
python3 tools/verify_sci_script.py --dir ~/sierra/patched/gk1

# ask the LIVE interpreter, over a pipe, with nobody at the keyboard
.venv-x/bin/python tools/sci_console.py --game <A COPY> --id gk1 \
    --binary <a --enable-engine=sci,sci32 --enable-text-console build> \
    --script tools/probes/gk1_patch_verify.py
```

⛔ Point every harness at a **copy**. Patches install to `~/sierra/patched/<game>`; the pristine
games under `~/sierra/Games` are never written.

⛔ Never edit `src/` while the suite is running.

---

## 4. The corpus, and what "done" means for each

Six titles across four engine generations, plus two parked. A game is only as done as its
*weakest* stage (§1), so read the row, not the game's name.

| game | engine | detection | patch built | installed now | played |
|---|---|---|---|---|---|
| LSL2 | SCI0 | **golden** | yes | no | yes |
| KQ4 | SCI0 | **golden** | yes | no | yes (tag `kq4-playtest-1`) |
| KQ5 | SCI1 | oracle | yes | yes | yes |
| KQ6 | SCI1.1 | **golden** | yes | yes | yes |
| LB2 (Dagger) | SCI1.1 | oracle | yes | yes | partly |
| **GK1** | **SCI2/SCI32** | R2–R5 caught | **partial — §6** | yes | **no** |
| QFG1 / QFG2 | SCI1.1 | parked | no | no | no |

The three **goldens** are LSL2, KQ4 and KQ6 (`src/test_golden.py:92`). A golden freezes a game's
whole output surface *and its own test*: if it moves, something is wrong or a human blessed it.
Treat a golden game as the regression net for every change, not as a place to make changes.
"Installed" means `~/sierra/patched/<game>` exists today — it is a fact about this machine, not
about the work.

---

## 5. Where the live documents are

Per-game docs go stale fast; each game has exactly one that is current:

* `docs/GK1-SOFTLOCK-CANDIDATES.md` — GK1's detection record (§1.x, newest at the top of its
  section list). `docs/SCI2-PATCHING.md` — GK1's back end and patch.
* `docs/KQ6-STATUS.md` — KQ6. The archived KQ6 plans are stale by construction.
* `docs/KQ5-ORACLE.md`, `docs/LB2-ORACLE.md` — ground truth for those two.
* `docs/ROADMAP.md` — project-wide state. `docs/TESTING.md` — the gate's contract.

---

## 6. Open edges — good places to start

**⭐ A spec kind for intra-room and flag findings.** The sharpest gap, and it is *placement*, not
detection. GK1's R3 (two disguises demanded across a boundary INSIDE room 800, where the
hounfour's scenes are `Script`s rather than rooms) and R4 (a flag whose only writer is a Teller
topic arm) are both **caught by detectors and expressible by no spec kind**, so they ship
nothing. Every kind today is an edge, a register write, an action or a market case. Start at
`guards.guard_specs` and `patcher.apply_guards`; the measured accounting is
`docs/SCI2-PATCHING.md` §5.2.

**⭐ GK1's five skipped placements.** `rm372 -> {270, 330, 490, 750}` all report *"no
controllable trigger (not-found) and no room-property exit"* — one room, four crossings, one
missing mechanism. `rm750 -> rm700` reports *"sole-exit"*.

**⭐ Two shipped guards are conditioned on a known false positive.** GK1's `rm800->rm899` and
`rm720->rm50` both demand the knife, which a human ruled an FP. They should be inert (the knife
can never be dropped) — but *should be inert* is not *measured inert*.
⭐⭐ The general lesson is worth having up front: **a known FP is cheap in a report and expensive
in a patch.** Read a false-positive list as a shipping list, not a scoreboard.

**⭐ Play GK1.** No GK1 guard has ever been seen to fire. Everything about it is static.

**⭐ An LZS/STACpack decompressor** (`method 32`) would let `sci_resource.py` read SCI32 volumes
directly instead of naming the gap. Nothing on the patch path needs it; graphics and control-map
reading for SCI32 titles do.

**⭐ `napoleon.sc`'s two-argument `loop:`** — 1 of 706 `loop:` sends in GK1, genuinely in the
bytecode, and the only script of 212 that will not recompile. Belongs to the sci-tools fork.

---

## 7. If you break something

The gate names the file. Run that file directly — every `src/test_*.py` is a standalone script.
If a golden or the emission manifest moved, the **default assumption is that your change moved
it**: get the byte-level delta with `tools/measure_emitted_bytes.py` against a worktree, read it,
and only then ask for a bless. If a save-compat check failed, stop — a changed script-0 size
means every existing save on that install is dead.
