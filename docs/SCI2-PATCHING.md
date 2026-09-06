# SCI2 (SCI32) patching — GK1's first patch, and why the wall was not one

Written 2026-09-06, the day GK1 stopped being detection-only. Companion to
`docs/SCI11-PATCHING-PLAN.md`, which scoped patching to "SCI1.1 titles we hold: KQ6 and Dagger"
and left GK1 out. Everything below marked MEASURED was run that day; the commands are in §7.

**The claim this document supports:** GK1 now has a patch — four guards, four scripts, compiled to
SCI2 script/heap pairs, installed, and loaded by the real ScummVM SCI32 engine. It has **not**
been played. (The first build had five; §5.0 is why one of them had to go.)

---

## 1. The wall was a missing flag, not a missing back end

`gk1-emission-not-built` recorded the blocker as *"the compiler has no SCI32 backend …
`--version {sci0|sci1|sci11}`. There is no `sci2`/`sci32`."* That reads the **front end's flag
list** as if it were the **code generator's capability**. It is not:

| what SCI2 needs | where it already was |
|---|---|
| a version record | `SCICompanionLib/Src/Util/Version.cpp:223`, `sciVersion2` |
| script/heap split | `SeparateHeapResources = true`, the same field SCI1.1 sets |
| absolute `lofsa` | `lofsaOpcodeIsAbsolute = true` |
| the SCI2 opcode table | `PMachine.cpp`, `OpArgTypes_SCI2` + the 0x7d/0x7e debug opcodes |
| a 64999 resource-number ceiling | `SCIVersion::GetMaximumResourceNumber()` |

**The whole back end is one line** in `tools/scicompile/main.cpp`:

```cpp
else if (v == "sci2")   { g_targetVersion = sciVersion2; }
```

⭐ **The lesson is `instruments-lie-run-the-control`, one level up: a `--help` string is not a
capability census.** Ten days of GK1 analysis were done against a "next milestone is a TOOLCHAIN
build" note that a five-minute probe refutes. §1.3 of the SCI1.1 plan had already found the same
thing for SCI1.1 — *"Pinning `sciVersion1_1` … is the only change needed"* — and the SCI2 answer
is the same answer a second time.

### 1.1 MEASURED: 211 of GK1's 212 scripts compile
First run **181/212**. The 31 failures were 30 × "Unknown procedure" over nine SCI32 kernels
(`KString`, `KArray`, `FirstNode`, `NodeValue`, `TextSize`, `OnMe`, `NewList`,
`DisposeTextBitmap`, `Graph`) — because the probe called `assemble()` without
`patcher.configure(ir)` first, so `_write_kernel_vocab` returned early and never wrote `999.VOC`.
GK1 ships no `vocab.999`, so SCICompanion fell back to its hardcoded SCI0/SCI1 name list. With
the kernel vocab in place: **211/212, converged in 2 passes.**

The one remaining failure is a ROUND-TRIP limitation, and it is worth stating precisely because
my first reading of it was wrong. `napoleon.sc:792`,
`(sam view: 463 loop: 0 0 cel: (sam lastCel:) setCycle: Beg)` — `loop:` is a property, and
SCICompanion refuses a property send with two arguments.

⛔ **It is not a printing artifact.** The IR carries it: script 460, `useTheOil::changeState`,
`SendMessage[Selector loop, Number 0, Number 0]`. Censused over the whole game, `loop:` is sent
**706 times — 113 with no argument, 592 with one, and exactly one with two.** So the bytecode
really does push two arguments there and Sierra's own compiler emitted it; SCICompanion is
stricter than Sierra was. (My first pass claimed zero two-argument sends in the IR — that walk
read a `messages`/`args` shape the IR does not use, and counted nothing at all. The control that
caught it: count the ONE-argument sends too, and notice they came back zero as well.)

`napoleon` is not a patch target, so nothing we ship goes through it; 211/212 is the honest
number and this is the missing one.

### 1.2 MEASURED: the version pin is load-bearing
`--version sci11` on GK1 does not fall back gracefully; it fails two different ways at once:

```
Failed to load selector names from vocab resource        <- SCI1.1 cannot find the bodies
Error: Script number must be less than 16384: 64921      <- GK1's system scripts are 64xxx
```

---

## 2. ⭐ The version is derived from the VOLUME header, not the map

The obvious place to look is the resource map, and it is the wrong place. GK1's map is
SCI1-shaped — its section type bytes are `80 81 82 84 86 87 89`, all ≥ 0x80, so SCICompanion's own
SCI2 map test (`_DetectMapFormat`: a section type byte **below** 0x80) never fires. ScummVM agrees
from the other side: it reports GK1's **"Resource map version: Late SCI1"**.

What actually changed in SCI32 is the **volume header**: the packed and unpacked sizes widened to
32 bits, so the header is 13 bytes where SCI1.1's is 9.

```
sci11   byte type|0x80, uint16 number, uint16 comp, uint16 decomp, uint16 method    (9)
sci32   byte type|0x80, uint16 number, uint32 comp, uint32 decomp, uint16 method    (13)
```

⛔ **AND THE TYPE AND NUMBER DO NOT SEPARATE THEM.** They sit at the same two offsets in both, so
GK1's script 0 read as SCI1.1 **matches** — `_resolve_volume` accepted it and returned
`decomp = 0, method = 5150`, and `get()` died several layers later with "compression method 5150
not implemented". The refutation is the **compression method**, which is drawn from a closed set
{0, 1, 2, 3, 4, 18, 19, 20, 32}. That is SCICompanion's own escalation rule
(`VersionDetectionHelper`: `compression > 20` is "invalid compression for any version up to
SCI1.1", and the package format is stepped SCI0 → SCI1 → SCI1.1 → SCI2 until the header stops
being implausible).

`Sci0Game.volume_format()` votes over a sample rather than trusting one resource, and
`patch_scheme()` answers `sci2` when the vote is `sci32`. ScummVM, detecting independently, says
**"Resource volume version: SCI2/2.1"** — the same answer from the same bytes.

⛔ One fence, paid for: entries that resolve to **nothing** are skipped, not counted against the
vote. GK1's `view.0` is one — the map names an offset no volume holds (the game also ships
`RESOURCE.ALT` with its own map) — and requiring unanimity let that single miss veto the other
seven and return "ambiguous".

### 2.1 MEASURED: the new layout and the method gate move NOTHING
Old module vs new, every installed game, every resource, compared byte for byte:

**16 games, ~16,500 resources, 0 differences, every patch scheme unchanged.** (LSL2, KQ4, KQ5,
KQ6, Dagger, Camelot, PQ1, QFG1-VGA, QFG2, SQ3, SQ4, SQ5, TCB … `sci0`/`sci1`/`sci11` as before;
GK1 alone moves, `sci11` → `sci2`.) The gate can only redirect headers that were already broken:
`_decompress` implements 0/1/2/18/19/20, so an accepted header naming anything else already
raised.

---

## 3. ⚠️ Export width: a trap that is inert, and must stay understood

`sciVersion2` hardcodes `IsExportWide = true`. Feeding that to codegen is the **KQ5 CD boot
crash** verbatim — a 32-bit export table under an interpreter that reads 16-bit entries sends
every cross-script call to export N through word 2N.

It does not happen, for a reason worth writing down rather than rediscovering:

* the separate-heap emitter `_Exports_SCI11` (`GenerateScriptResource.cpp:711`) opens with
  `assert(!context.GetVersion().IsExportWide)` and then **always writes 2-byte entries**;
* `scicompile` builds with `-DNDEBUG`, so that assert is compiled out and the flag is **silently
  ignored** on this path;
* SCICompanion's own `_DetectIsExportWide` agrees it should be: `if (SeparateHeapResources)
  return false;`

MEASURED, script 64921: Sierra's export table is `a4 00 c1 00 de 00 32 01` and ours is
`a4 00 c1 00 de 00 31 01` — four narrow entries either way, three of the four identical.

⛔ **So do not pass `--wide-exports` with `--version sci2`.** `patcher._patch_scheme` derives
export width only for the bare-`sci1` scheme, so it does not — but a future build with asserts
enabled would abort here, and that abort would be *correct*.

---

## 4. ⭐ The validation oracle GK1 ships with itself

GK1 ships three of its own scripts as **uncompressed loose patches** — `391.SCR/HEP` (rm391),
`64921.SCR/HEP` (Print), `64929.SCR/HEP` (Sync). They need no LZS decompressor to read, so they
are a byte-level oracle available today: compile our decompiled source for those same three and
compare against Sierra's.

| script | Sierra scr / hep | ours scr / hep | heap bytes differing |
|---|---|---|---|
| 64921 `Print` | 3648 / **96** | 3618 / **96** | **0 — byte-identical** |
| 64929 `Sync` | 730 / **116** | 754 / **116** | 23 (two strings emitted in the other order) |
| 391 `rm391` | 4052 / **1904** | 4024 / **1904** | 243, at a 44-byte stride = object records |

**All three heaps reproduce Sierra's length exactly, and one reproduces her bytes exactly.** The
243 differences in rm391's heap sit at 52, 120, 164, 208, 252, 296, 340 … — one per object
record, i.e. pointers into a code block that is 28 bytes shorter than Sierra's. That is the same
result the SCI1.1 round got on KQ6 ("every *data* structure reproduces exactly, only the *code*
block differs"), reached independently on SCI2.

---

## 5. The patch itself

`python3 build/build_patch.py gk1 v1` — the canonical order, unchanged, parametric over the game.

| source | script | placement |
|---|---|---|
| `Hounfour.sc` | 800 | arm-event (`rm800 -> rm899`) |
| `bayouMaze.sc` | 490 | setscript (`rm490 -> rm480`) |
| `rm455.sc` | 455 | setscript (`rm455 -> rm800`) |
| `rm720.sc` | 720 | setscript (`rm720 -> rm50`) |

### 5.0 ⛔ THE FIRST BUILD HAD FIVE, AND THE FIFTH WAS A KNOWN FALSE POSITIVE
`EndGame.sc` (899) also came out guarded — on `sDaggerOnMalia`, which is the `knife` row **the
USER ruled a false positive on 2026-08-27**. Since `put: 64` exists nowhere in GK1, every player
at rm899 holds the knife, so the guard refused that window's stab *forever*: a move the player is
entitled to make, denied by our own patch.

⭐ **An FP costs a line of prose in a report and a wrong instruction in a patch**, and nothing
between `guard_specs` and `emit_patches` asks whether a row is one the record already calls an
FP — nor should it ([[derived-only-no-declared-specs]] forbids an oracle-sourced filter). The fix
had to be in the DETECTOR, and the record had already written it: *a fatal use counts only when
the use WASTES the item.* KQ6's skull is `put:` away inside `throwSkull`; KQ5's rope is spent at
`ropeOnBranch`'s arming site; GK1's knife is spent nowhere. One line in `fatal_uses`, and
**GK1 loses the row while KQ6 and KQ5 keep theirs** (docs/GK1-SOFTLOCK-CANDIDATES.md §1.68,
pinned and red-proven by `src/test_fatal_use_waste.py`).

MEASURED: rebuilding after the cure, **the other four scripts are byte-identical to the
five-guard build** and only `899.SCR`/`899.HEP` disappear. ⛔ The install had to have those two
files DELETED, not merely not-rewritten — a stale loose patch overrides the game exactly as a
fresh one does.

⚠️ And the knife is still FLAGGED: it keeps two `register_strandings` rows and two edge rows, so
GK1's declared reds do not move. The cure removed the shipped GUARD, not the finding.

⛔ The one-line cure also crashed `test_deletion_soundness`, which calls `fatal_uses` unbound on
stub models that carry no `drops`. The gate caught it (`1 crashed` against the previous run's 0);
the fix is in the stubs, not a `getattr` default that would quietly disable the rule.

The mode chooser was **RETRACTED** by its own feasibility gate — *"no menu bar or control panel
shape found to host the chooser"* — so every wrap emits modeless, with no `(or (== global<mode> 2)
…)` wrapper. That is the gate working, not a failure.

### 5.1 MEASURED: the guard is in the BYTECODE, not just the source
Compiling each target twice, patched and unpatched, from the same project:

| script | Δ script | Δ heap | the heap delta IS |
|---|---|---|---|
| 800 Hounfour | +12 | **+0** | an arm-event holds SILENTLY — it has no refusal string |
| 490 bayouMaze | +28 | +10 | `Not yet!` |
| 455 rm455 | **+108** | +8 | the seven-item descent guard |
| 720 rm720 | +28 | +8 | `Not yet!` |
| *(899 EndGame)* | *+30* | *+40* | *`Better not. You are going to need that.` = 39 chars + NUL — the retired fifth guard (§5.0); the heap delta matching the string to the byte is what made it readable at all* |

Every refusal string is present in its compiled `.HEP`; `800.HEP` has none, and should not.

---

## 6. ⭐⭐ Does the INTERPRETER take them? Two answers, both with controls

A compiler's exit code is not a loadable resource. The script and the heap are two files that
have to agree about where every object, method body and string lives, and a disagreement is a
crash inside `Script::init`, not a compile error.

### 6.1 `tools/verify_sci_script.py` — ScummVM's checks, transcribed
Every check is one of the engine's own, from `engines/sci/engine/script.cpp` (`Script::init`,
`identifyOffsets`, `getRelocationTableSci0Sci21`), carrying the `error()` text it stands in for.
**8 of 8 pairs OK** — our five and Sierra's three.

⛔ A checker that accepts everything is worth nothing, so it is pinned against four corruptions,
each the shape of a real back-end bug. All four **REFUSED**, the clean copy **OK**:

| corruption | what it stands for |
|---|---|
| a script paired with another script's heap | shipping a stale half |
| a truncated heap | a short write |
| a relocation count bumped past the heap | an off-by-N in the emitter |
| an export pointing past the script | the KQ5-CD wide-export bug |

### 6.2 The live engine — 213/213 instantiated
The playtest ScummVM had **SCI32 off** (`--enable-engine=sci` leaves the `sci32` sub-engine
disabled: *"Game id not supported (SCI32 support not compiled in)"*); reconfigured with
`--enable-engine=sci,sci32` and rebuilt.

⛔ **THE OBVIOUS COMMAND IS VACUOUS.** `scro N` answers *"Script N is currently not
loaded/available"* for any script the game has not entered, and the first draft of the probe read
that as a pass for all five. It was caught only because Sierra's own scripts and two
never-patched stock ones were asked the same question and gave the **same** answer.

`find_callk` is the command that really does it: `printKernelCallsFound` walks every script in
the game, `instantiateScript`s it, disassembles it and uninstantiates it (`console.cpp:3840`).

> **213 scripts found, disassembling… → 0 error/warning lines, VM alive afterwards.**

⛔ And the negative control: the same walk on an install whose `455.HEP` relocation count was
bumped by 40 **killed ScummVM outright**. Note what else that run showed —
**`verify_scripts` PASSED on the corrupted install**, because it only checks that a heap exists
and that script+heap < 64KB. On its own it is the misleading instrument.

### 6.3 Boot
`/usr/games/scummvm` (stock 2.8.0, SCI32 on) runs the patched install and reports
**"Emulated interpreter version: SCI2"**. It reaches the intro and keeps running; the five
patched scripts are late-game rooms and are not loaded at boot, which is exactly why §6.2 exists.

---

## 7. What is NOT done

* ⛔ **PLAY.** Nothing here is a play-test. Every guard's *condition* is still only as good as the
  detection behind it, and no guard has been seen to fire, or seen not to fire when it shouldn't.
  ([[play-beats-my-reading]].)
* ⛔ **The emission manifest does not yet cover GK1.** `measure_emitted_bytes.GAMES` gained `gk1`
  on 2026-09-06; until the manifest is blessed, `test_emission_manifest` carries two declared reds
  (`emission: gk1 matches manifest`, `emission: manifest covers exactly the emitted game set`).
  A refresh is a BLESS and waits on the user.
* `napoleon.sc`'s one two-argument `loop:` (§1.1) — a sci-tools fork issue.
* Reading GK1's *packed* resources from Python still needs an LZS/STACpack decompressor
  (`method 32`). Nothing on the patch path wants it; `sci_resource._decompress` now names the gap
  instead of failing obscurely.

## 8. Commands

```sh
# the back end
cmake --build tools/scicompile/build -j8
./tools/scicompile/build/scicompile --version sci2 --sco <proj>
./tools/scicompile/build/scicompile --version sci2 --all <proj>

# the patch
python3 build/build_patch.py gk1 v1          # -> build/gk1_patch_v1/patch

# would it load?
python3 tools/verify_sci_script.py --dir ~/sierra/patched/gk1

# does it load?  (needs a --enable-engine=sci,sci32 --enable-text-console build)
.venv-x/bin/python tools/sci_console.py --game ~/sierra/patched/gk1 --id gk1 \
    --binary /tmp/scummvm-playtest-build/scummvm \
    --script tools/probes/gk1_patch_verify.py
```
