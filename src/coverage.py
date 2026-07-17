"""State-coverage instrument: what DATA does the model refuse to read?

The core defect this exists to prevent is not a wrong answer -- it is a silent one.
Every condition we cannot interpret becomes `Pred("OPAQUE")` -> UNKNOWN -> permissive,
which is the SAFE direction and therefore raises no error, fails no test and prints
no warning. It just quietly makes the tool answer "sure, you can win". LSL2 has 434
such conditions and KQ4 has 1642, and for a full day of work nothing counted them.
KQ4's Cupid bow is the case that made the point: the arrow count lives in the bow's
`loop` property, `(>= ((inventory at: iCupidBow) loop?) 2)` is opaque, and so the
endgame gate in Lolotte's castle simply does not exist for us. A human had to notice.

THE METHOD IS A DIFF, NOT A HEURISTIC. SCI declares its state vocabulary:

    globals          Main.sc's (local ...) block
    script locals    each script's (local ...) block
    item properties  Main.sc's (instance X of Iitem (properties ...))
    object props     any selector that is READ somewhere as `p?` and WRITTEN as `p:`

So "coverage over data" is enumerable: take the declared names, subtract the ones we
model, and what remains is what we are blind to. It cannot miss a store, because the
game names them all. It needs no knowledge of arrows or bikinis -- a name that is both
read and written IS a variable, mechanically.

WHAT IT DELIBERATELY DOES NOT DO. It looks only at DATA -- declared names with reads
and writes. It will never propose modelling collision, control maps or pathfinding,
because those are not in the vocabulary. That is the point: when this report comes
back empty, the data model is complete and everything remaining is engine semantics
or a hole in the input. That is a measured phase boundary rather than an argued one.

KNOWN LIMIT: this finds state we do not model. It cannot see state we model BADLY --
`gCurrentStatus` is "modelled" as the set of values it can ever take, which is wrong
for a mode register, and this report will call it covered.

    python3 src/coverage.py            # both games
"""

from __future__ import annotations

import os
import re
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(__file__))
import config                                              # noqa: E402
import closure as C                                        # noqa: E402
from sexpr import Sym                                      # noqa: E402
from model import load_game, GAnd, GOr, GNot, Pred, head_is, is_sym   # noqa: E402
from machine import all_machines                           # noqa: E402


# --------------------------------------------------------------------------
# 1. The declared state vocabulary
# --------------------------------------------------------------------------
def script_locals(forms):
    out = []
    for f in forms:
        if head_is(f, "local"):
            skip = False
            for t in f[1:]:
                if is_sym(t, "="):
                    skip = True            # `name = init`: the init is not a name
                    continue
                if skip:
                    skip = False
                    continue
                if isinstance(t, Sym):
                    out.append(t.name)
    return out


def item_properties(game):
    """Property names declared on Iitem instances -- the item state vocabulary."""
    out = defaultdict(set)
    for s in game.scripts.values():
        for f in getattr(s, "forms", []) or []:
            if not (head_is(f, "instance") and len(f) >= 4 and is_sym(f[2], "of")
                    and is_sym(f[3], "Iitem")):
                continue
            name = f[1].name if isinstance(f[1], Sym) else "?"
            for sub in f[4:]:
                if head_is(sub, "properties"):
                    toks = sub[1:]
                    for i in range(0, len(toks) - 1, 2):
                        if isinstance(toks[i], Sym):
                            out[toks[i].name].add(name)
    return out


# --------------------------------------------------------------------------
# 2. Reads and writes, straight off the s-exprs (the IR has already thrown away
#    exactly the things we are hunting, so do not ask the IR)
# --------------------------------------------------------------------------
def prop_reads_writes(game):
    """selector -> (read_count, write_count, receivers).

    A selector READ as `p?` and WRITTEN as `p:` is a variable -- that is the whole
    test, and it needs no idea what `p` means.
    """
    reads, writes, recv = Counter(), Counter(), defaultdict(Counter)

    def walk(f):
        if not isinstance(f, list) or not f:
            return
        for i, tok in enumerate(f):
            if not isinstance(tok, Sym):
                continue
            if tok.name.endswith("?"):
                p = tok.name[:-1]
                reads[p] += 1
                recv[p][_recv_of(f)] += 1
            elif tok.name.endswith(":") and i + 1 < len(f):
                p = tok.name[:-1]
                writes[p] += 1
                recv[p][_recv_of(f)] += 1
        for sub in f:
            walk(sub)

    for s in game.scripts.values():
        for f in getattr(s, "forms", []) or []:
            walk(f)
    return reads, writes, recv


def _recv_of(f):
    """A crude label for what a message is sent to: `(Inventory at: iX)` -> the item."""
    if not f:
        return "?"
    h = f[0]
    if isinstance(h, Sym):
        return h.name
    if isinstance(h, list) and len(h) >= 3 and isinstance(h[1], Sym) \
            and h[1].name == "at:" and isinstance(h[2], Sym):
        return f"item:{h[2].name}"          # (Inventory at: iCupidBow) prop
    return "?"


# --------------------------------------------------------------------------
# 3. What the model actually reads
# --------------------------------------------------------------------------
def opaque_atoms(game):
    """Every OPAQUE atom in every guard the model evaluates -> text -> count.

    Both the flat IR trees AND the compiled machine paths, since machine.py resolves
    some atoms (bounded counters) that the IR leaves opaque.
    """
    out = Counter()

    def scan(node):
        if isinstance(node, (GAnd, GOr)):
            for k in node.kids:
                scan(k)
        elif isinstance(node, GNot):
            scan(node.kid)
        elif isinstance(node, Pred) and node.kind == "OPAQUE":
            out[node.text] += 1

    for s in game.scripts.values():
        for t in s.transitions:
            scan(t.guard_tree)
    for ms in all_machines(game).values():
        for mach in ms.values():
            for paths in mach.states.values():
                for path in paths:
                    for (kind, arg) in path:
                        if kind == "TEST":
                            scan(arg)
            for (_st, gd) in mach.entries:
                scan(gd)
    return out


VAR_RE = re.compile(r"\(\s*(?:\w+\s+)?at:\s*(\w+)\)\s*(\w+)\?")   # (Inventory at: iX) p?
BARE_RE = re.compile(r"^\(?\s*([a-zA-Z_]\w*)\s*\??\)?$")


def classify(game, m):
    """The gap list: named state that is READ and WRITTEN but that we do not model."""
    reads, writes, recv = prop_reads_writes(game)
    modelled_globals = set(game.globals)
    counters = {(mach.script, c)
                for ms in all_machines(game).values() for mach in ms.values()
                for c in mach.counters}
    locals_by_script = {num: set(script_locals(getattr(s, "forms", []) or []))
                        for num, s in game.scripts.items()}

    rows = []
    for p in sorted(set(reads) | set(writes)):
        if p in ("state",):                 # machine.py owns the program counter
            continue
        # Which of these reads/writes are aimed at an INVENTORY ITEM? Scan every
        # receiver, not the top few: `view`/`loop`/`cel` are overwhelmingly rendering
        # traffic on actors, and the handful of item-directed uses -- which are real
        # game state -- drown in it. `iCupidBow.loop` is 5 reads against 1066.
        on_items = {r: n for r, n in recv[p].items() if r.startswith("item:")}
        if on_items:
            rows.append({
                "store": "item-property", "name": p,
                "reads": reads[p], "writes": writes[p],
                "receivers": ", ".join(f"{r[5:]}x{n}" for r, n in
                                       Counter(on_items).most_common(4)),
                "modelled": False,
            })
        elif p in reads and p in writes:
            # An object property read AND written is still a variable by definition,
            # but on a non-item receiver it is usually the renderer talking to itself.
            rows.append({
                "store": "object-property", "name": p,
                "reads": reads[p], "writes": writes[p],
                "receivers": ", ".join(f"{r}x{n}" for r, n in recv[p].most_common(3)),
                "modelled": False,
            })
    # -- script locals read in a guard but never promoted to a counter --
    for num, names in locals_by_script.items():
        for n in sorted(names):
            if n in C.CFG.timer_globals or n in modelled_globals:
                continue
            if (num, n) in counters:
                continue
            rows.append({"store": "script-local", "name": f"rm{num}.{n}",
                         "reads": 0, "writes": 0, "receivers": "",
                         "modelled": False})
    return rows


# --------------------------------------------------------------------------
# 4. Which ignorance is LOAD-BEARING? (the filter that makes this usable)
# --------------------------------------------------------------------------
def perturb(game, m, atoms, start, goals, limit=400):
    """Force each opaque atom FALSE instead of unknown; see if any answer moves.

    1642 unread conditions is not an actionable number. This is what cuts it down:
    an atom whose false-verdict changes NOTHING is ignorance we can live with; one
    that changes reachability is ignorance that could be hiding a softlock, because
    the model is leaning on not-understanding it.
    """
    base = C.closure(m, start)
    base_rooms, base_win = len(base.rooms), bool(base.rooms & goals)
    real_atom3 = C._atom3
    hits = []
    for text, n in atoms.most_common(limit):
        def patched(p, items, flags, neg, locs=None, _t=text):
            if p.kind == "OPAQUE" and p.text == _t:
                return C.T if neg else C.F        # force it false
            return real_atom3(p, items, flags, neg, locs)
        C._atom3 = patched
        try:
            m._mcache.clear()
            r = C.closure(m, start)
            d_rooms = len(r.rooms) - base_rooms
            d_win = bool(r.rooms & goals) != base_win
            if d_rooms or d_win:
                hits.append({"atom": text, "count": n, "d_rooms": d_rooms,
                             "breaks_goal": d_win})
        finally:
            C._atom3 = real_atom3
            m._mcache.clear()
    return hits


def report(cfg):
    config.ACTIVE = cfg
    C.CFG = cfg
    game = load_game(cfg.src_dir)
    m = C.FixModel(game)
    goals = set(cfg.goal_rooms)
    name = cfg.name.split(":")[0]

    atoms = opaque_atoms(game)
    rows = classify(game, m)
    print(f"\n{'=' * 72}\n{name}\n{'=' * 72}")
    print(f"conditions the model cannot read: {sum(atoms.values())} "
          f"({len(atoms)} distinct)")

    items = [r for r in rows if r["store"] == "item-property"]
    print(f"\n-- ITEM STATE WE DO NOT MODEL ({len(items)} properties) --")
    print("   an item's own properties ARE game state; we model only `has:` (a boolean)")
    for r in sorted(items, key=lambda r: -len(r["receivers"]))[:10]:
        print(f"   {r['name']:12s} r{r['reads']:<5d} w{r['writes']:<5d} on: {r['receivers'][:56]}")
    if not items:
        print("   (none found -- note a property can be read explicitly but written")
        print("    IMPLICITLY by the engine: `get:`/`put:` set `ownedBy` with no `ownedBy:`")
        print("    ever appearing, so the read-and-written test misses it. The")
        print("    perturbation pass below catches those.)")

    print("\n-- LOAD-BEARING IGNORANCE (forcing the atom FALSE moves an answer) --")
    hits = perturb(game, m, atoms, cfg.start_room, goals)
    if not hits:
        print("   none: every unread condition is currently inert")
    for h in sorted(hits, key=lambda h: (not h["breaks_goal"], h["d_rooms"]))[:14]:
        flag = "GOAL UNREACHABLE" if h["breaks_goal"] else f"{h['d_rooms']:+d} rooms"
        print(f"   {flag:18s} x{h['count']:<4d} {h['atom'][:60]}")
    print(f"\n   {len(hits)} of {len(atoms)} distinct unread conditions are load-bearing")
    return atoms, rows, hits


def main():
    for cfg in (config.LSL2, config.KQ4):
        report(cfg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
