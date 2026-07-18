"""Auto-discover the STATE MACHINERY a game uses to gate progress.

The fixpoint reasons over (rooms, items, flag-values). But real Sierra games gate
movement and death on *state variables* the base extraction renders opaque:

  * GLOBAL mode registers   -- gCurrentStatus (in the water / falling / disguised),
    gCurrentEgoView (which costume), gIslandStatus (endgame phase). Multi-valued,
    compared by exact value to decide an exit or a death.
  * ROOM-LOCAL state         -- henchStatus (rm47: are the KGB charmed by your
    disguise, or chasing you to your death?), goto95, passInRoom. Declared in an
    instance's `(properties ...)`, assigned in `init`/`doit`, read in a sibling
    actor script -- and INVISIBLE to a flag/global analysis, so the model walks the
    KGB beach for free and never sees the disguise requirement.

This pass finds both, per game, with NO hand-list -- so a new SCI game is covered by
running it, not by editing a table. A variable is "machinery the system should care
about" iff it is compared to an int (it feeds a branch we can gate on) inside an
instance that performs a `newRoom` or a death write (so that branch can decide
progress).

We deliberately do NOT also require it to be *assigned* in that same instance. Real
gates are cross-instance: `henchStatus` is set in the `rm47` room and read in the
sibling `henchScript` actor; require both in one instance and you drop exactly the
gates that matter. Over-inclusion is the correct failure direction -- a false include
is at worst a value we track that turns out constant; a false drop is a checkpoint the
player walks into and gets stuck behind, which is the one outcome this tool exists to
prevent.
"""
from __future__ import annotations

import glob
import os
from collections import defaultdict

import sexpr

CMP_OPS = {"==", "!=", "<", ">", "<=", ">=", "u<", "u>"}

# Cosmetic / mechanical locals that are STATE by the letter of the rule but never a
# real progress gate: loop indices, actor-motion internals, kernel scratch. Listed so
# the report is readable; keeping them would only over-require, never under-require.
_MECHANICAL = {
    "state", "i", "n", "j", "ret", "handle", "mover", "cycleCnt", "client", "elements",
    "b-moveCnt", "impulse", "blocks", "legDir", "heading", "counter", "temp0", "num",
    "busy", "dir", "theSpeed", "nonBumps", "seconds", "cycles", "overlays", "aBird",
    "local1", "local2", "local3", "local4", "local9", "work", "machineSpeed",
    "runTitleSequence", "featherX",
}


def _sym(n):
    return getattr(n, "name", None)


def _toks(node):
    return [_sym(x) for x in node] if isinstance(node, list) else []


def _assigned_and_compared(node, assigns, compares):
    if not isinstance(node, list) or not node:
        return
    h = _sym(node[0])
    if h == "=" and len(node) == 3 and _sym(node[1]) and isinstance(node[2], int):
        assigns[_sym(node[1])].add(node[2])
    if h in CMP_OPS and len(node) == 3 and _sym(node[1]) and isinstance(node[2], int):
        compares[_sym(node[1])].add(node[2])
    for x in node:
        _assigned_and_compared(x, assigns, compares)


def _has_progress(node, death_sig):
    if not isinstance(node, list):
        return False
    if "newRoom:" in _toks(node):
        return True
    if (_sym(node[0]) == "=" and len(node) == 3
            and _sym(node[1]) == death_sig[0] and node[2] == death_sig[1]):
        return True
    return any(_has_progress(x, death_sig) for x in node)


def _instances(forms):
    """Yield (name, body) for every `(instance NAME of CLASS ...)` form."""
    if isinstance(forms, list):
        if forms and _sym(forms[0]) == "instance" and len(forms) >= 2 and _sym(forms[1]):
            yield (_sym(forms[1]), forms)
        for x in forms:
            yield from _instances(x)


def discover(src_dir, global_names, death_sig):
    """Return {'globals': {var: rooms}, 'locals': {var: rooms}} of progress-gating
    state, plus 'domains': {var: sorted(values)} for sizing promotion."""
    files = sorted(glob.glob(os.path.join(src_dir, "*.sc"))
                   + glob.glob(os.path.join(src_dir, "*.SC")))
    machinery = defaultdict(set)          # var -> set(room files where it gates progress)
    domains = defaultdict(set)            # var -> set(int values assigned or compared)
    for f in files:
        try:
            forms = sexpr.read_file(f)
        except Exception:
            continue
        base = os.path.basename(f)
        a, c = defaultdict(set), defaultdict(set)
        _assigned_and_compared(forms, a, c)
        for v in set(a) | set(c):
            domains[v] |= a[v] | c[v]
        for _name, body in _instances(forms):
            if not _has_progress(body, death_sig):
                continue
            ai, ci = defaultdict(set), defaultdict(set)
            _assigned_and_compared(body, ai, ci)  # ci = vars tested against an int here
            for v in ci:                   # tested to an int inside an instance that moves/kills
                machinery[v].add(base)
    out = {"globals": {}, "locals": {}, "domains": {}}
    for v, rooms in machinery.items():
        if v in _MECHANICAL:
            continue
        bucket = "globals" if v in global_names else "locals"
        out[bucket][v] = sorted(rooms)
        out["domains"][v] = sorted(x for x in domains[v] if isinstance(x, int))
    return out


def main():
    import config
    import model
    for name, cfg in (("LSL2", config.LSL2), ("KQ4", config.KQ4)):
        config.ACTIVE = cfg
        g = model.load_game()
        d = discover(cfg.src_dir, set(g.globals), cfg.death_signal or (None, None))
        print(f"==================== {name} ====================")
        print(f"GLOBAL registers gating progress: {len(d['globals'])}")
        for v in sorted(d["globals"], key=lambda v: -len(d["domains"][v])):
            print(f"   {v:24s} dom={len(d['domains'][v]):3d}  in {len(d['globals'][v])} rooms")
        print(f"ROOM-LOCAL state gating progress: {len(d['locals'])}")
        for v in sorted(d["locals"], key=lambda v: len(d["locals"][v])):
            print(f"   {v:20s} dom={len(d['domains'][v]):2d}  in {d['locals'][v][:6]}")


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(__file__))
    main()
