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
        "🔴 KNOWN GAP: a use that only sets a room local is not seen as a requirement":
            "room LOCALs are not in the machine model at all (3rd recorded instance: "
            "liftTapestry's L1, huntersLamp's rm520 doit, rm690's lord::doVerb). KQ6's gauntlet "
            "is currently kept by an INCIDENTAL register write -- right verdict, wrong reason.",
        "🔴 KNOWN GAP: no exit guard is placed, so the water is demanded nowhere":
            "in-room register writes are modelled PERMISSIVELY, so no crossing ever commits the "
            "flag and every register-valued exit guard is refused. The teacup's carry-IN ships; "
            "the 'come out with it filled' half does not.",
        "🔴 KNOWN GAP: register_strandings reports prevRoom flips as points of no return":
            "the detector predates prevRoom being a modelled register and reads each of its "
            "values as an irreversible plot advance -- 323 rows on KQ6. Nothing in production "
            "reads it, which is why it could rot unnoticed. Fix = a notion of PLOT-state "
            "registers, not a filter naming prevRoom.",
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
