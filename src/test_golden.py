"""Golden-snapshot lock on the FULL analysis output surface for the VALIDATED games: LSL2 and KQ4.

The v1.0-lsl2 tag's behaviour on LSL2 is a CORRECT ORACLE -- 16 softlocks, four dangerous sinks,
its guard specs -- validated by playing the patched game to the ending. This test freezes that whole
surface (softlock items, groups, resource exhaustion, joint-window strandings, edge/gate guard specs,
and sink specs) so it cannot be silently changed. It exists because the sink behaviour was quietly
broken once by a later commit and nearly "fixed" a second time by re-litigating it.

⭐ KQ4 JOINED 2026-08-09 [user ruling: "KQ4 must be moved into golden"]. It had been in
`test_watched_surface` since that file existed, which was a POLICY/IMPLEMENTATION MISMATCH: KQ4 has
been declared golden since 2026-07-25, but the watched tier's default response to a failure is
"check the diff, then maybe refresh", and golden's is "the change is wrong". A reference you may
re-bless is not a reference. Its golden was lifted VERBATIM out of `watched_surfaces.json` -- the
surface that tier had been holding green -- so the move froze exactly what was already blessed and
re-derived nothing. (This docstring previously said KQ4 was "still under active development"; that
stopped being true on 2026-07-25 and the file was never updated.)

⛔ AND THIS FILE NEVER SKIPS [user, 2026-08-09]. One check per golden game, emitted on every run.
A missing IR, a missing golden or an unmounted resource drive is a FAILURE, not a `(skip …)` line:
a gate that can quietly decline to run is not a gate, and until today an unmounted `/mnt/i/sierra`
turned this whole file into a silent pass. If you are working somewhere the drives are absent, the
right answer is a red run you can see, not a green one you cannot trust.

GOLDEN FREEZES THE WHOLE APPARATUS, THIS TEST INCLUDED. Do not "improve" a golden game's oracle,
its config, or the checks here -- a better gate is a different gate, and then nothing is anchored.
Improvements go to the WIP game (LB2/KQ6) and reach a golden only with sign-off.

If this test fails, the DEFAULT assumption is that the change is wrong, not the golden. Do not
regenerate a golden to make a red test green without understanding, or without the user's sign-off
(these games' behaviour is the oracle, not something to re-derive).

Regenerate deliberately (after a change you have confirmed is correct), naming ONE game:
    python3 -c "import json, config; from snapshot import snapshot; \
        json.dump(snapshot(config.LSL2, with_placements=True), \
                  open('testdata/lsl2.golden.json','w'), indent=2, sort_keys=True)"

`with_placements=True` since 2026-08-01: a spec is a claim, a PLACEMENT is whether the patcher
could act on it, and the two move independently. Nothing froze the placement half for any game
until then, so the SCI1.1 placement work could have broken the placements of the one title that
has been played end to end without a test noticing.
"""
import json
import os
import sys

import config
from snapshot import snapshot

PASS, FAIL = [], []
_HERE = os.path.dirname(os.path.abspath(__file__))


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n      {detail}" if detail and not cond else ""))


def _diff(golden, got):
    """Field-by-field difference, so a failure names exactly what moved."""
    lines = []
    for k in sorted(set(golden) | set(got)):
        g, c = golden.get(k), got.get(k)
        if g == c:
            continue
        if isinstance(g, list) and isinstance(c, list):
            added = [x for x in c if x not in g]
            removed = [x for x in g if x not in c]
            lines.append(f"{k}: +{added}  -{removed}")
        else:
            lines.append(f"{k}: golden={g!r} got={c!r}")
    return "\n      ".join(lines)


def run():
    print("=== test_golden: the full analysis surface is frozen (LSL2, KQ4) ===")
    for name, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        path = os.path.join(_HERE, "testdata", f"{name.lower()}.golden.json")
        # ⛔ THIS FILE NEVER SKIPS [user ruling, 2026-08-09: "test_golden shouldn't skip anything
        # ever"]. Exactly ONE check is emitted per golden game, on every run, whatever the state of
        # the machine -- because a gate that can quietly not run is not a gate, and "0 failed" has
        # to mean "both surfaces were compared", not "nothing was in a position to disagree".
        #
        # Every precondition below is therefore a FAILURE, not a `continue`, and they all report
        # under the SAME check name, so `run_tests.KNOWN_RED` sees one stable key per game and an
        # unmounted drive is as loud as a moved row. Cheap to satisfy and impossible to overlook.
        label = f"{name}: full output surface matches the frozen golden"
        if not os.path.exists(cfg.ir_path):
            check(label, False, f"NO IR at {cfg.ir_path} -- the surface could not be computed, so "
                                f"this golden was NOT checked. Build it (tools/build.sh); do not "
                                f"let the run pass without it.")
            continue
        if not os.path.exists(path):
            check(label, False, f"NO GOLDEN at {path} -- a golden game with no frozen surface is "
                                f"unprotected. Restore it from git rather than regenerating, or "
                                f"the baseline becomes whatever the tree happens to emit today.")
            continue
        # PLACEMENTS ARE PART OF THE SURFACE. A correct spec that lands nowhere ships nothing, and
        # until 2026-08-01 no game froze the placement half at all -- so the SCI1.1 placement work
        # (`trigger.py`, `patcher.py`) could silently break the placements of the one title that
        # has actually been played. Computing them needs the game's own resources, because the
        # patcher assembles a project from them.
        if not os.path.isdir(cfg.resource_dir):
            check(label, False, f"RESOURCES NOT MOUNTED at {cfg.resource_dir} -- the placement "
                                f"half of the surface cannot be computed, so this golden was NOT "
                                f"checked. Mount the drive. (This used to `continue`, which made "
                                f"an unmounted drive look like a passing gate.)")
            continue
        golden = json.load(open(path))
        got = snapshot(cfg, with_placements=True)
        check(label, got == golden, _diff(golden, got))
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
