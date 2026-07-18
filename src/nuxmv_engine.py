"""Drive nuXmv IC3 for our targeted reachability queries.

Winnability = "can a goal room be reached?" We emit an INVARSPEC `!(goal)`, so IC3
returns the invariant FALSE (with a counterexample) exactly when the goal is reachable.
Requirements = "is item X needed?" -- pin item X off forever and re-ask winnability; if
the goal is now unreachable, X is required. Both are plain EF-goal queries, IC3's sweet
spot (ENGINE-DIRECTION.md), so we sidestep the nested EF(!EF goal) softlock query.
"""
from __future__ import annotations

import os
import subprocess

from smv_emit import Emitter


def _find_nuxmv():
    for cand in (
        os.environ.get("NUXMV"),
        os.path.join(os.environ.get("CLAUDE_JOB_DIR", ""), "tmp",
                     "nuXmv-2.0.0-Linux", "bin", "nuXmv"),
        "/tmp/nuXmv-2.0.0-Linux/bin/nuXmv",
    ):
        if cand and os.path.exists(cand):
            return cand
    raise FileNotFoundError("nuXmv binary not found; set $NUXMV")


NUXMV = None


def _nuxmv():
    global NUXMV
    if NUXMV is None:
        NUXMV = _find_nuxmv()
    return NUXMV


def _run_ic3(smv_text, tmpdir=None, timeout=600):
    tmpdir = tmpdir or os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp")
    os.makedirs(tmpdir, exist_ok=True)
    path = os.path.join(tmpdir, "model.smv")
    with open(path, "w") as f:
        f.write(smv_text)
    cmds = f"read_model -i {path}\ngo_msat\ncheck_invar_ic3\nquit\n"
    p = subprocess.run([_nuxmv(), "-int"], input=cmds, capture_output=True,
                       text=True, timeout=timeout)
    out = p.stdout + p.stderr
    # invariant "!(goal)" is FALSE  <=> goal reachable <=> winnable
    reachable = None
    for line in out.splitlines():
        low = line.lower()
        if "is false" in low:
            reachable = True
        elif "is true" in low:
            reachable = False
    if reachable is None:
        raise RuntimeError("nuXmv gave no invariant verdict:\n" + out[-2000:])
    return reachable, out


def winnable(m, game, promote_globals=False, pin_items_off=(), timeout=600):
    """True iff a goal room is reachable. `pin_items_off` forces those item ids to stay
    FALSE (used by requirements to remove an item)."""
    emitter = Emitter(m, game, promote_globals=promote_globals)
    smv, _ = emitter.emit()
    if pin_items_off:
        # rewrite each pinned item's init + next to FALSE (unobtainable)
        for it in pin_items_off:
            smv = _pin_item_off(smv, it)
    reachable, _ = _run_ic3(smv, timeout=timeout)
    return reachable


def _pin_item_off(smv, it):
    """Force item{it} to be permanently FALSE by replacing its next() block with a
    constant. Removes the item from the world (requirements probe)."""
    lines = smv.splitlines()
    out = []
    i = 0
    tag = f"next(item{it}) := case"
    while i < len(lines):
        if lines[i].strip().startswith(tag):
            out.append(f"  next(item{it}) := FALSE;")
            # skip to matching esac;
            while i < len(lines) and lines[i].strip() != "esac;":
                i += 1
            i += 1  # skip the esac;
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    import sys
    import config
    import closure as C
    from model import load_game

    which = sys.argv[1] if len(sys.argv) > 1 else "LSL2"
    promote = "--promote" in sys.argv
    config.ACTIVE = getattr(config, which)
    C.CFG = config.ACTIVE
    g = load_game()
    m = C.FixModel(g)
    print(f"[{which}] promote_globals={promote}")
    w = winnable(m, g, promote_globals=promote)
    print(f"  winnable = {w}")
