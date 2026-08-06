"""WATCHED SURFACES: KQ6, KQ4 and LB2's full output, frozen so a change is REPORTED, not silent.

This is deliberately NOT `test_golden`, and the difference is the point.

  `test_golden` (LSL2)   the behaviour is the ORACLE. "If this test fails, the DEFAULT
                         assumption is that the change is wrong, not the golden."
  this file              the behaviour is WATCHED. A change is allowed -- these games are
                         under active work and their surfaces are expected to move -- but it
                         must be seen and checked, item by item, the moment it happens.
                         [user ruling 2026-08-06: "not like as a golden omg don't touch, but
                         any regression should be loudly and immediately reported and checked"]

Until now the only thing standing between KQ6 and a silent surface change was a human
remembering to run `snapshot.py` against a worktree baseline before committing. That worked
because someone kept doing it by hand; it is not a net. Every detector verdict, every guard
spec (all four site kinds), every placement row and its site count is frozen here, so the
answer to "did that refactor move anything?" arrives in the same run that made the change.

WHEN THIS FAILS, READ THE DIFF. It prints one line per moved row, grouped by key, with the
old and new values. Then either fix the change, or -- once you have checked every line with
the user -- refresh the file:

    python3 -c "import test_watched_surface as T; T.refresh()"

Refreshing without reading the diff is the one thing this file cannot stop you from doing and
the one thing that makes it worthless.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                                            # noqa: E402
from snapshot import snapshot                                            # noqa: E402

PASS, FAIL = [], []
_HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(_HERE, "testdata", "watched_surfaces.json")

# The games whose surfaces are watched. LSL2 is absent on purpose -- it has `test_golden`,
# which holds it to the stricter standard. `dagger` is LB2 (Laura Bow 2); the identifier is
# what `config.by_name` and the build directory use.
WATCHED = ("KQ6", "KQ4", "dagger")
LABEL = {"dagger": "LB2"}


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           "" if cond else ("  -- " + detail)))


def _capture(name):
    cfg = config.by_name(name)
    if cfg is None or not os.path.exists(cfg.ir_path):
        return None
    return snapshot(cfg, with_placements=True)


def _diff(old, new):
    """Every moved row, as readable lines. Lists are compared as SETS of rows, because their
    order is already canonical (sorted) and what matters is which rows exist."""
    out = []
    for key in sorted(set(old) | set(new)):
        a, b = old.get(key), new.get(key)
        if a == b:
            continue
        if isinstance(a, list) and isinstance(b, list):
            for gone in sorted(set(map(json.dumps, a)) - set(map(json.dumps, b))):
                out.append("    %-22s REMOVED  %s" % (key, json.loads(gone)))
            for added in sorted(set(map(json.dumps, b)) - set(map(json.dumps, a))):
                out.append("    %-22s ADDED    %s" % (key, json.loads(added)))
        else:
            out.append("    %-22s %r -> %r" % (key, a, b))
    return out


def refresh():
    """Rewrite the watched surfaces from the current tree. Read the diff first."""
    data = {}
    for name in WATCHED:
        snap = _capture(name)
        if snap is None:
            print("  (skip %s: no IR)" % name)
            continue
        data[name] = snap
    os.makedirs(os.path.dirname(DATA), exist_ok=True)
    with open(DATA, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)
    print("refreshed %s: %s" % (DATA, ", ".join(sorted(data))))


def run():
    if not os.path.exists(DATA):
        print("  (skip: no watched surfaces yet -- create with "
              "`python3 -c \"import test_watched_surface as T; T.refresh()\"`)")
        return True
    with open(DATA) as f:
        frozen = json.load(f)
    for name in WATCHED:
        label = LABEL.get(name, name)
        got = _capture(name)
        if got is None:
            print("  (skip %s: no IR)" % label)
            continue
        if name not in frozen:
            check("%s: surface is watched" % label, False,
                  "no frozen surface for %s -- refresh() to start watching it" % label)
            continue
        lines = _diff(frozen[name], got)
        check("%s: full surface unchanged (%d keys)" % (label, len(got)), not lines,
              "%d row(s) moved" % len(lines))
        if lines:
            print("\n  \033[33m%s SURFACE MOVED -- check every line, then refresh:\033[0m"
                  % label)
            for ln in lines[:60]:
                print(ln)
            if len(lines) > 60:
                print("    ... and %d more" % (len(lines) - 60))
            print()
    return not FAIL


if __name__ == "__main__":
    ok = run()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(0 if ok else 1)
