"""Emit every game's patched SOURCE TREE, so two revisions can be diffed byte for byte.

WHY THIS IS NOT THE SNAPSHOT SURFACE. `snapshot.py` freezes whether a guard landed -- `applied`,
`kind`, `sites`, the skip reason -- and never one byte of the source text a placement produced.
Every fix to the text arithmetic in `patcher.py` (the span walk, the candidate scan, which `(if`
a demand is conjoined onto, where the marker goes) is therefore INVISIBLE to a green snapshot
run. A guard that moved to the wrong site, or that commented out the arming it was meant to
hold, reads as "no regression" ([[measure-the-emitted-bytes]]).

HOW TO USE IT -- two runs and a recursive diff. The control is a git worktree at the last commit
before the change:

    git worktree add /tmp/pre <pre-change-commit>
    ln -s "$PWD/build" /tmp/pre/build          # ⛔ NOT OPTIONAL -- see below
    python3 tools/measure_emitted_bytes.py /tmp/pre/src  /tmp/emit_pre
    python3 tools/measure_emitted_bytes.py "$PWD/src"    /tmp/emit_now
    diff -r /tmp/emit_pre /tmp/emit_now && echo "BYTE-IDENTICAL"

⛔ `build/` IS GITIGNORED, so a bare worktree has none -- and `config` derives every `src_dir`
and `ir_path` from the tree it is imported out of. Without that symlink the control run finds no
IR for any game, SKIPs all five, and emits an empty directory that `diff -r` compares against
the real one without complaint: a vacuous PASS reading as "byte-identical" (2026-08-20 third
review). Hence the symlink, and hence a skip is now a NONZERO EXIT with the reason printed --
this tool may not report success on a measurement it did not make.

Both runs read the same build trees and the same IR, so any difference in the output is a
difference the change made. `--games` narrows the set; with no flag it does all five.

⛔ IT WRITES ONLY WHERE YOU POINT IT. `assemble` copies the game's decompiled sources into
`<out>/<game>` and the appliers rewrite them in place; nothing here touches `~/sierra/Games`,
`/mnt/i`, or any installed patch ([[install-patches-by-default]]).
"""
import argparse
import os
import shutil
import sys

GAMES = ("LSL2", "KQ4", "KQ6", "dagger", "kq5")


def emit(src_dir, out_dir, games):
    sys.path.insert(0, src_dir)
    import config                                                        # noqa: E402
    import guards as G                                                   # noqa: E402
    import missability as M                                              # noqa: E402
    import patcher as P                                                  # noqa: E402

    done, skipped = [], []
    for name in games:
        cfg = config.by_name(name)
        if cfg is None or not os.path.exists(cfg.ir_path):
            skipped.append(name)
            print("SKIP %s -- no IR at %s"
                  % (name, cfg.ir_path if cfg else "<no config>"))
            continue
        s = M.load(cfg=cfg)
        dest = os.path.join(out_dir, name)
        shutil.rmtree(dest, ignore_errors=True)
        os.makedirs(dest)
        P.configure(s.em.ir)
        nums = P.assemble(dest, cfg)
        titles = {n: t for t, n in nums.items()}
        # ⛔ `patcher.main`'s CANONICAL ORDER, and the mode chooser is not optional. It is a
        # FEASIBILITY GATE that runs before any wrap: where the chooser cannot be installed it
        # RETRACTS the mode (`T.MODE = None`, `_MODE_DEST` pinned so `_init_mode` cannot re-arm
        # later), and `stock_or` then emits the bare condition instead of
        # `(or (== global<mode> 2) <cond>)`. Skip it and `apply_guards` arms a mode of its own,
        # so every guarded site emits a wrapper the shipped patch does not have -- measured on
        # KQ5, that alone is 18 differing source files against the play-tested v17. Both sides
        # of a diff would still agree, so the comparison stays valid, but "byte-identical" would
        # stop meaning "byte-identical to what ships", which is the only claim worth making.
        P.install_mode_chooser(dest, titles)
        P.apply_sink_remedies(dest, G.sink_remedies(s), titles)
        P.apply_resource_remedies(dest, G.resource_remedies(s), titles)
        P.apply_guards(dest, G.guard_specs(s), titles, nums,
                       s_drops=lambda it: s.drops.get(it, set()), rooms=set(s.rooms),
                       entry_frontier=lambda r: G.commit_entry_frontier(s, r),
                       defer_info=lambda sp: G.defer_to_entry(s, sp))
        P.declare_mode_globals(dest)
        done.append(name)
        print("DONE %s -> %s" % (name, dest))
    print("emitted %d game(s): %s%s"
          % (len(done), ", ".join(done),
             ("  (skipped %s)" % ", ".join(skipped)) if skipped else ""))
    if skipped:
        print("\n⛔ %d of %d games emitted NOTHING. A diff against this output measures "
              "nothing.\n   `build/` is gitignored -- in a worktree, symlink it in:\n"
              "       ln -s <repo>/build %s/build"
              % (len(skipped), len(games), os.path.dirname(src_dir)))
    return 0 if done and not skipped else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", help="the src/ directory to run the patcher FROM")
    ap.add_argument("out", help="directory to emit the patched source trees into")
    ap.add_argument("--games", default=",".join(GAMES),
                    help="comma-separated game names (default: all five)")
    a = ap.parse_args()
    return emit(os.path.abspath(a.src), os.path.abspath(a.out),
                [g for g in a.games.split(",") if g])


if __name__ == "__main__":
    sys.exit(main())
