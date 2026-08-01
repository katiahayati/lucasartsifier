"""A room that is a VIRTUAL MAP: exits chosen by room-locals that the player steps like a grid.

KQ4's ocean (rm31) is the case this exists for. `local1`/`local2` are a 2-D cell; entering the
room seeds the cell from the PREVIOUS room (`(switch global12 ...)`); each screen-edge crossing
steps the cell by +-1 (`edgeHit`); and reaching a particular cell fires a `newRoom:`. So the room
is really ~100 nodes we see as one, and the edge `rm31 -> rm43` (the Bridle island, cell 100,100)
is not free -- it is reachable only from cells the player can actually walk to before drowning.

This module SUMMARISES that internal map to edge gates on the PREVIOUS-ROOM global, so the rest of
the pipeline never has to promote the grid: it asks `grid.analyze(em, prev_global)` and gets, per
grid room, `{exit_room: {previous-room values from which that exit is reachable}}`. For rm31 it
yields `{43: {43, 44}}` -- the island is reachable only if you arrived from the island (43) or the
whale (44), which is exactly "the island sits behind the one-time whale trip".

Everything is DERIVED, nothing about rm31/local1/local2 is named:
  * GRID LOCALS -- locals that are `==`-compared on a `newRoom` exit guard AND are stepped
    (inc/dec). A local merely compared (a latch like LSL2's `local8 == 0`) is not a grid; a local
    that moves is. This is what keeps LSL2's latch rooms out.
  * SEEDS -- `init` writes to a grid local guarded by `previous-global == V`, i.e. the entry switch.
  * BUDGET -- a MONOTONE step counter (a local seeded 0, incremented, never decremented) has a
    death threshold; that bounds how far any grid local can move from its seed. Over-estimating the
    budget is the SAFE direction (more reachable -> weaker gate -> never a false strand), and the
    isolating coordinate gap (mainland cells vs the island at 100) dwarfs the exact value.

SOUNDNESS: reachability is OVER-approximated -- a grid local can move at most `budget` from its
seed (each step is +-1), and a local that RESETS to a constant mid-walk (the `local2` wrap) is
treated as its whole domain. So the emitted gate is a permissive over-approximation of "who can
reach this exit": the sweep never blocks a move the game allows. The gate still BITES on the island
because the isolating dimension (`local1`, no reset) cannot span the 95-cell gap within budget.
"""
from __future__ import annotations

from collections import defaultdict

import ir as I
from guard_ast import GAnd, GOr, GNot, Pred


def _ctr_eqs(guard):
    """Positive `local == C` atoms in a guard: {(vt, idx): {C, ...}}. CTR tuples are
    `("CTR", (vt, idx), op, val)`; a negated `!=` is a positive equality, same as asserts_eq."""
    out = defaultdict(set)

    def w(x, pol=True):
        if x is None:
            return
        if isinstance(x, list):
            for y in x:
                w(y, pol)
        elif isinstance(x, tuple) and len(x) >= 4 and x[0] == "CTR":
            key, op, val = x[1], x[2], x[3]
            if (op == "==" and pol) or (op == "!=" and not pol):
                out[tuple(key)].add(val)
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k, pol)
        elif isinstance(x, GNot):
            w(x.kid, not pol)

    w(guard)
    return out


def _prev_eqs(guard, prev_global):
    """Positive `prev_global == V` room values a guard requires (the entry-switch case)."""
    vals = set()

    def w(x, pol=True):
        if x is None:
            return
        if isinstance(x, list):
            for y in x:
                w(y, pol)
        elif isinstance(x, Pred):
            if x.kind == "CMP" and x.var == prev_global:
                try:
                    v = int(x.value)
                except (TypeError, ValueError):
                    return
                if (x.op == "==" and pol) or (x.op == "!=" and not pol):
                    vals.add(v)
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k, pol)
        elif isinstance(x, GNot):
            w(x.kid, not pol)

    w(guard)
    return vals


def analyze(em, prev_global):
    """`{room: {exit_room: frozenset(previous-room values that can still reach it)}}`.

    Only rooms that are genuine virtual-map grids appear, and only exits that are a PROPER subset
    of the seed set (genuinely restricted) get a gate. Everything derived; see module docstring."""
    if prev_global is None:
        return {}

    # --- collect per-room local facts -------------------------------------------------
    inc, dec = defaultdict(set), defaultdict(set)
    zero_seed = defaultdict(set)
    reset = defaultdict(set)
    all_seed_vals = defaultdict(set)                  # room -> {prev values that seed anything}
    seeds = defaultdict(lambda: defaultdict(lambda: defaultdict(set)))  # room->pv->local->{values}
    for room, script, key, v, g in em.handler_locals:
        key = tuple(key)
        if v == ("inc",):
            inc[room].add(key)
        elif v == ("dec",):
            dec[room].add(key)
        elif isinstance(v, int):
            pvs = _prev_eqs(g, prev_global)
            for pv in pvs:                            # a SET per (pv, local): variant seeds (dolphin)
                seeds[room][pv][key].add(v)
                all_seed_vals[room].add(pv)
            if v == 0 and not pvs:
                zero_seed[room].add(key)
            # RESET = a const write to this local guarded by a compare on ITSELF -- the wrap
            # `(< (++ local2) 10) (= local2 0)`. A death-marker write (`local1 := 1000` guarded by
            # the drown COUNTER, not by local1) is NOT a reset, and a prev-room seed is not either.
            if _guarded_by_self(g, key):
                reset[room].add(key)

    stepped = {r: (inc[r] | dec[r]) for r in set(inc) | set(dec)}
    reset = {r: (reset[r] & stepped.get(r, set())) for r in reset}

    # monotone step COUNTER: inc-only, seeded 0, not a grid-exit local -> bounds the walk length.
    budget = {}
    for room in set(inc):
        for key in inc[room]:
            if key not in dec.get(room, set()) and key in zero_seed[room]:
                # its death threshold bounds the walk; over-estimate is safe.
                b = _counter_bound(em, room)
                if b is not None:
                    budget[room] = max(budget.get(room, 0), b)

    # --- exits gated on a stepped local == C ------------------------------------------
    gates = {}
    for room in seeds:
        if room not in budget:
            continue                     # no derivable walk bound -> cannot isolate -> skip (safe)
        exit_gate = {}
        for e in _room_exits(em, room):
            eqs = _ctr_eqs(e.guard)                       # {local: {required values}}
            grid_reqs = {k: vs for k, vs in eqs.items() if k in stepped.get(room, set())}
            if not grid_reqs:
                continue
            reachable_from = set()
            for pv, seedmap in seeds[room].items():
                if _cell_reachable(grid_reqs, seedmap, reset.get(room, set()), budget[room]):
                    reachable_from.add(pv)
            allv = all_seed_vals[room]
            if reachable_from and reachable_from < allv:   # PROPER subset = genuinely restricted
                exit_gate[e.dst] = frozenset(reachable_from)
        if exit_gate:
            gates[room] = exit_gate
    return gates


def _guarded_by_self(guard, key):
    """Does `guard` contain a CTR compare on `key` itself? That is the wrap signature
    `(< (++ local2) 10) (= local2 0)` -- the reset write is conditioned on the local's own value.
    A death-marker write (`local1 := 1000` guarded by the drown counter local3) is not, and neither
    is a prev-room seed (guarded by the previous-room global, a CMP not a CTR)."""
    found = [False]

    def w(x):
        if x is None or found[0]:
            return
        if isinstance(x, list):
            for y in x:
                w(y)
        elif isinstance(x, tuple) and len(x) >= 2 and x[0] == "CTR":
            if tuple(x[1]) == key:
                found[0] = True
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k)
        elif isinstance(x, GNot):
            w(x.kid)

    w(guard)
    return found[0]


def _cell_reachable(grid_reqs, seedmap, reset_locals, budget):
    """Can the required cell (grid_reqs: local -> {values}) be reached from this seed within
    budget? A resetting local is unconstrained; a non-resetting stepped local moves at most
    `budget` from its seed (each step is +-1). Over-approximation: ANY seed value reaching ANY
    required value satisfies the local (variant seeds like the dolphin case). A required local with
    no seed here defaults to 0 (SCI locals start 0) -- the permissive read."""
    for key, wants in grid_reqs.items():
        if key in reset_locals:
            continue                                  # can be anything -> satisfiable
        seedvals = seedmap.get(key) or {0}
        if not any(abs(s - w) <= budget for s in seedvals for w in wants):
            return False
    return True


def _counter_bound(em, room):
    """The death threshold that bounds a monotone step counter's walk.

    A grid room drowns you when the step counter reaches a bound: `(== local3 local12)` with
    `local12 == 4`. That compare is local==local, which the extractor renders OPAQUE -- the
    counter never appears in a captured atom -- so it cannot be read off a guard. What survives is
    the bound itself: `local12` is a CONST-LOCAL (written exactly one value, never stepped). So the
    budget is derived as the room's largest const-local value: the drown threshold a monotone
    counter is checked against.

    Two imprecisions, both in the SAFE (permissive) direction for the ISLAND, which is the finding
    that matters. (1) If the true threshold were larger than any const-local, we UNDER-estimate --
    but a strictly inc-only counter compared to a const-local cannot exceed it, so for that shape
    this is exact. (2) If an unrelated const-local is larger, we OVER-estimate the budget, which
    only WEAKENS the gate (more reachable) and can never invent a strand. The isolating coordinate
    gap (mainland cells vs the island at 100) dwarfs the value either way. Returns None if the room
    has no const-local bound, in which case the walk is unbounded and no grid gate is emitted."""
    written = defaultdict(set)
    stepped = set()
    for r, script, key, v, g in em.handler_locals:
        if r != room:
            continue
        key = tuple(key)
        if v in (("inc",), ("dec",)):
            stepped.add(key)
        elif isinstance(v, int):
            written[key].add(v)
    bounds = [next(iter(vs)) for key, vs in written.items()
              if key not in stepped and len(vs) == 1 and next(iter(vs)) > 0]
    return max(bounds) if bounds else None


def _room_exits(em, room):
    """Movement edges out of `room` (flat + cue), which carry the exit's local guard."""
    for e in em.ts.edges:
        if e.src == room:
            yield e
    for e in em.ts.cs_edges:
        if e.src == room:
            yield e


