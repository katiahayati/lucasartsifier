"""Run every `src/test_*.py` and say something meaningful about the result.

    python3 tools/run_tests.py              # the whole suite
    python3 tools/run_tests.py toll scopes  # only files whose name contains one of these

WHY THIS EXISTS. Every test file here is a plain script with its own `run()` and its own
`sys.exit`, and one of them (`test_toll`) exits 1 BY DESIGN -- it carries assertions that are
deliberately RED, because no passing test may assert known-wrong behaviour. So "did the suite
pass" had no answer: a green run and a run with a fresh regression looked identical from the
outside, and the only way to tell was to read twelve files of output by eye.

THE CONTRACT. Failure is not the interesting axis; AGREEMENT WITH `KNOWN_RED` is. This exits 0
only when the set of failing checks is EXACTLY the declared set. That makes two things loud
that were previously silent:

  * an UNDECLARED failure is a regression, named with the file it came from;
  * a declared RED that has gone GREEN is ALSO a failure -- "a gap was closed, promote it".
    Without that half, closing a modelling gap looks like nothing happening, which is how a
    real fix gets landed, forgotten, and later undone by someone who never knew it was there.

Every file prints `  [PASS] name` / `  [FAIL] name`, so the parsing below is the whole protocol;
a new test file needs no registration unless it is deliberately red.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(_ROOT, "src")

# --- THE DELIBERATELY RED CHECKS -------------------------------------------------------------
#
# `file -> {check name: why it is red}`. A check listed here MUST fail; one that starts passing
# is reported as a promotion, not quietly accepted. Keep the reason short and name the gap, so
# the next reader can tell a known limitation from a broken test without opening the file.
KNOWN_RED = {
    "test_toll.py": {
        # ✅ PROMOTED 2026-08-06 -- both mists REDs ("the carry-in demands rain-readiness
        # (global161==15), not just the lamp" and "the isle landing is guarded when the
        # shore-carry revisit is armed") are GREEN and no longer listed. Three derivations
        # closed finding #17: the SIXTH store (vocab.derive_mask_globals/lower_mask_globals
        # lowers plain-global literal-mask arithmetic per-bit -- measured corpus-wide it
        # matches exactly KQ6's g161, zero on LSL2/KQ4/Dagger), the register half of
        # sink_survival_carryins (structural reqs of the positive arming, presentability-
        # checked, spelled `(== global161 15)`, WAIVED under the surviving arm's own one-way
        # latch flag 74 because makeRain resets the word on success -- an unconditional
        # demand would wall every winner), and the stage-conditioned landing propagation
        # (the shore ambush's `captured`, its 25&!14 stage inherited through the new
        # machine-method armer link, demands compliance at every crossing into rm550 under
        # `(or (not <stage>) <demand>)`). Rebuilt GREEN as
        # test_mists_survival_demand_carries_the_register_half's four pins.
        # ✅ CORRECTED, NOT PROMOTED, 2026-08-05 -- "the long route's treasure-corral letter
        # seal is detected" demanded a row with `register != 338`, and that row should never
        # exist: remeasured against the source, flag 166 (reg338, rFlag1 $0002) IS the long
        # route's seal. The wedding fuse (`weddingRemind`, rgCastle::doit, per-real-second)
        # writes it region-homed in every castle room; the hidden-passage arm refuses under it
        # (rm720.sc:429); 850->781 closes by cond order. `register_strandings`' one row
        # (338, 1, letter, flip_rooms = the 15 rooms outside the walls, 770 and 710 included)
        # carries BOTH routes -- the "covers the SHORT route only" reading was the
        # misdiagnosis that also drove the refuted forced-escort design (guard-actor patrol
        # was the drama, not the seal; KQ4's day/night is the same class -- adversarial-clock
        # phase change). The check is rebuilt GREEN as "the letter row covers the long route"
        # (flip_rooms/still_needed_at pinned), and the remedy now reaches the region-homed
        # writer: `guard_prop_flag_owner_write` freezes the fuse's countdown clause until the
        # letter is in hand (v22, 80.SCR joins the set). See test_toll's docstring and
        # docs/KQ6-CASTLE-CAPTURE-MAP.md §2b for the measurement.
        # ✅ PROMOTED 2026-08-02 -- "a use that only sets a room local is not seen as a
        # requirement" is retired: the FIFTH store is WIRED (round 4). Room-script latch locals
        # lower to synthetic registers (vocab.lower_room_locals) and the machine walks thread the
        # own-script ones as counters (Machine.local_regs, compile._lreg_test), so the latch write
        # is an ordinary register write every consumer sees. The marker was rebuilt as
        # test_local_latch_is_modelled, which pins rm690's local0 chain on KQ6 itself.
        # ✅ PROMOTED 2026-08-01 -- "no exit guard is placed, so the water is demanded nowhere" is
        # GREEN and no longer listed. The placement walk now COMMITS what is genuinely committed:
        # unconditional entry writes (`_psucc(commit=...)` from `em.init_writes`) and consumed item
        # tolls (`_settable_frontier`'s compliance fixpoint loses the spent toll edge). The water
        # is demanded at rm680->rm155 -- the guard oracle's own site -- and the mirror-shown flag
        # at rm670->rm660 and rm680->rm155. Detection walks stay permissive.
        # ✅ PROMOTED 2026-08-02 -- "register_strandings reports prevRoom flips as points of no
        # return" is GREEN and no longer listed. The causality conjunct landed: a flip strands
        # only what the pre-flip state could still reach, judged by the same walk from the
        # pre-flip states (no register named). KQ6 323 rows -> 1 (the flag-166 `letter` lead,
        # held for user review); LSL2/KQ4 -> 0, every old row diagnosed as region-junk.
    },
    # THE ROAD TO A PATCHED KQ6. Each of these turns green when its phase lands, and that is the
    # only mechanism that will notice -- a plan document goes stale in silence. Phases are in
    # the approved plan; derivations in docs/SCI11-PATCHING-PLAN.md.
    "test_sci11_patch.py": {
        # ✅ PHASE 2 LANDED 2026-08-01 -- "the refusal primitive is derived per game" is GREEN and
        # is therefore no longer listed. `patcher.refusal_form` reads the game's own text-display
        # procedure out of its scripts (LSL2/KQ4 `proc255_0`, KQ6 and the Dagger `proc921_0`), and
        # a game with no derivable form emits no refusal-bearing guard at all.
        # ✅ PHASE 5's fatal-use half LANDED 2026-08-01 -- "a fatal use produces a remedy spec" is
        # GREEN. `guard_specs` emits an `action` spec per `fatal_uses` row and the patcher places
        # it on the arming of the fatal machine (KQ6: rm420's `setScript: throwSkull`). Inert on
        # LSL2, KQ4 and the Dagger, which have no fatal uses.
        "🔴 KNOWN GAP (KQ6): every non-refused spec places":
            "PHASE 4. The arrival-commit re-site LANDED 2026-08-04: the capture demand sits on "
            "the isle's entry frontier (rm320's cue arm-gate + rm300's shortcut nav-assign "
            "re-route -- finding #8's bypass -- stage-conditioned with the game's own "
            "capture-arm test, sites from guards.commit_entry_frontier -- model knowledge, "
            "not text search), so the rm340 rows all place. Remaining skips, both "
            "deliberate: rm420->rm435 (the shared-dispatcher seam; its demand is covered by "
            "the capture guards) and the huntersLamp sink (a TRADE; its remedy is the mists "
            "carry-in). Goes green only when those two either place or become refusals.",
        # ✅ PROMOTED 2026-08-05 (same day as the play find) -- "the Realm-entry demand wraps
        # catchNiteMare's arming, not blowinIt's" is GREEN. The cross-file block now READS the
        # helper's arming graph (trigger.reaching_owners/reaching_procs) instead of assuming any
        # export is the way in; a helper-internal arming whose call sites all sit outside `init`
        # is wrapped in place (kind `proc-arm`: nightMare.sc's `(nightMare setScript:
        # catchNiteMare)` inside proc344_1), and init call sites still route to the
        # entry-frontier re-site. test_realm_entry_guard_sits_on_the_spell_delivery pins it.
        "🔴 KNOWN GAP (dagger): every non-refused spec places":
            "PHASE 4. 2 of 4 place, and the two that DO are 24-item guards placed as arm-event, "
            "i.e. events that would never fire -- so Dagger is worse off than the count "
            "suggests and Phase 3's §6.1 is what fixes it.",
        # ✅ PHASE 5 LANDED 2026-08-02 -- "every KQ6 finding is closed by a guard" is GREEN and no
        # longer listed. The last three: handkerchief + skeletonKey placed at the Realm's exit
        # frontier (pocket_carryout_frontier, rm640->rm650), and the wrong-door stranding rows
        # died to edge_strandings applying two of its own siblings' rules to its output (forced-
        # not-missable, unholdable-cannot-strand; SINGLETON-only -- the group form deletes LSL2's
        # play-validated raft guard and is ruled out). `pipeline --report` exits 0 on KQ6.
    },
}

CHECK = re.compile(r"^\s*\[(PASS|FAIL)\]\s*(.*?)\s*$")
TALLY = re.compile(r"^(\d+) passed, (\d+) failed")


def run_one(path, echo=True):
    """Run one test file, streaming its output. Returns (passed, failed_names, exit_code)."""
    proc = subprocess.Popen([sys.executable, "-u", path], cwd=SRC,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    passed, failed = 0, []
    for line in proc.stdout:
        if echo:
            sys.stdout.write("    " + line)
            sys.stdout.flush()
        m = CHECK.match(line)
        if m:
            if m.group(1) == "PASS":
                passed += 1
            else:
                failed.append(m.group(2))
    proc.wait()
    return passed, failed, proc.returncode


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    names = sorted(f for f in os.listdir(SRC) if f.startswith("test_") and f.endswith(".py"))
    if argv:
        names = [f for f in names if any(a in f for a in argv)]
    if not names:
        raise SystemExit("no test files matched")

    t0 = time.time()
    total_pass, unexpected, promoted, crashed = 0, [], [], []
    for f in names:
        print(f"\n\033[1m=== {f}\033[0m", flush=True)
        t1 = time.time()
        passed, failed, code = run_one(os.path.join(SRC, f))
        total_pass += passed
        red = KNOWN_RED.get(f, {})
        unexpected += [(f, n) for n in failed if n not in red]
        promoted += [(f, n) for n in red if n not in failed]
        # A file that dies before printing a tally (import error, traceback) fails silently
        # under a pure check-line count -- it has no FAIL lines to find. Catch it on the code.
        if code != 0 and not failed:
            crashed.append((f, code))
        print(f"  \033[2m-- {passed} passed, {len(failed)} failed "
              f"({time.time() - t1:.0f}s)\033[0m", flush=True)

    n_red = sum(len(v) for k, v in KNOWN_RED.items() if k in names)
    print("\n" + "=" * 78)
    print(f"\033[1m{total_pass} passed, {n_red - len(promoted)} known-red, "
          f"{len(unexpected)} unexpected, {len(crashed)} crashed\033[0m  "
          f"({time.time() - t0:.0f}s)")

    for f, name in unexpected:
        print(f"  \033[31mUNEXPECTED FAILURE\033[0m  {f}: {name}")
    for f, code in crashed:
        print(f"  \033[31mCRASHED\033[0m  {f}: exit {code} with no FAIL line -- import error or "
              f"traceback; run it directly")
    for f, name in promoted:
        print(f"  \033[33mRED WENT GREEN\033[0m  {f}: {name}\n"
              f"      {KNOWN_RED[f][name]}\n"
              f"      If the gap really is closed, say so with the user and remove it from "
              f"KNOWN_RED in this file. Until then this is a failure, because a limitation "
              f"that silently stops being one is a limitation nobody will remember to re-check.")
    if not (unexpected or crashed or promoted):
        for f, red in KNOWN_RED.items():
            if f in names:
                for name in red:
                    print(f"  \033[2mknown-red\033[0m  {f}: {name}")
        print("\n\033[32mThe suite agrees with KNOWN_RED.\033[0m")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
