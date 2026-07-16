"""The fixpoint core: what can you reach and obtain from a given state?

Adventure state is essentially MONOTONIC -- you gain items and set flags, you
rarely un-gain. So we do not enumerate the product state space (21 items => 2^21
subsets, the explosion that made the old code project down to a bare room graph
and throw the guards away). We compute a least fixpoint instead: exact,
guard-respecting, and cheap.

    closure(m, start, held, flags, exhausted) -> Reach(rooms, items, flagvals)
    winnable(...)  ==  a goal room is in reach.rooms

That turns softlock detection into a QUERY rather than a feature:

    for each irreversible action, recompute the closure from its POST-state;
    if the goal no longer closes, that action is the cut.

All four cases we kept re-discovering fall out of this one algorithm, with no
special-casing: the whale (in rm44 without iFeather, the tickle guard fails so
there is no exit), the magic fruit (consumed, its one-shot source exhausted, so
rm694's ending is unreachable), the parachute (on the plane without it, the
rm64->65 survival guard fails), and nightfall (isNightTime latched, so the
day-only doors' guards fail and the fishing pole is gone).

Deaths need no special handling here: the fixpoint does not care WHY you cannot
proceed. "Stuck" and "dead" are the same to it -- both are simply "the goal no
longer closes". The death catalogue (analyze.death_sites) is for LABELLING a
finding, which is a reporting concern.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict, namedtuple

sys.path.insert(0, os.path.dirname(__file__))
from model import load_game, Game                                    # noqa: E402
from analyze import (movement_graph, edge_requirements, region_maps,  # noqa: E402
                     is_room)
from config import ACTIVE as CFG                                      # noqa: E402

Reach = namedtuple("Reach", "rooms items flags")

ANY = object()      # a global written with a non-literal -> any value is possible


class FixModel:
    """Everything the fixpoint needs, extracted from the IR once.

    Note we take ACQUIRE/SET with their GUARDS, unlike analyze.derived_maps which
    flattens them and loses the condition -- the whole point here is to honour the
    conditions.
    """

    def __init__(self, game: Game):
        self.g = game
        self.edges, _kind = movement_graph(game)
        self.edge_reqs = edge_requirements(game)
        members, _room_region, controllers = region_maps(game)
        self.members, self.controllers = members, controllers

        # item -> [(room, guards)]   ; room may be a REGION script (iFeather's
        # source is script 505, a region) -- expand those to their member rooms,
        # exactly as the old _need_rooms did for `required`.
        self.acq = defaultdict(list)
        # global -> [(room, value, guards)]
        self.sets = defaultdict(list)
        for num, s in game.scripts.items():
            for t in s.transitions:
                for e in t.effects:
                    if e.kind == "ACQUIRE":
                        for r in self._rooms_of(num):
                            self.acq[e.arg].append((r, t.guards))
                    elif e.kind == "SET":
                        for r in self._rooms_of(num):
                            self.sets[e.arg].append((r, _lit(e.value), t.guards))

        self.init_flags = {k: {_lit(v)} for k, v in game.global_inits.items()}

        # Items that GATE something -- the only ones that can strand you. An item
        # nothing ever tests can't make the goal unreachable.
        self.gating_items = {p.var for s in game.scripts.values()
                             for t in s.transitions for p in t.guards
                             if p.kind == "OWN" and p.want}

    def _rooms_of(self, num):
        """Where do this script's effects happen?

        - a REGION script isn't a walkable room; its effects happen in its members
          (iFeather's source is script 505, a region -- room reachability can never
          reach 505 itself).
        - non-room scripts (Main's procedures, the class library) are GLOBAL code
          called from anywhere -> None, meaning "available wherever you are".
          Without this, `(= gCurrentTimer name)` inside Main's SetRgTimer procedure
          never fires, and every timer-gated edge is wrongly blocked.
        """
        if num in self.controllers and self.members.get(num):
            return sorted(self.members[num])
        if not is_room(self.g, num):
            return [None]
        return [num]


def _lit(v):
    """Literal value of a SET, or ANY when it isn't a constant (`++`, an expr...)."""
    if isinstance(v, int):
        return v
    s = str(v).strip()
    if s.lstrip("-").isdigit():
        return int(s)
    if s in ("TRUE", "true"):
        return 1
    if s in ("FALSE", "false", "NULL"):
        return 0
    return ANY


def _truthy(vals):
    return any(v is ANY or (isinstance(v, int) and v != 0) for v in vals)


def _cmp_ok(v, op, want):
    if v is ANY:
        return True
    w = _lit(want)
    if w is ANY or not isinstance(v, int) or not isinstance(w, int):
        return True                     # can't evaluate -> permissive
    return {"==": v == w, "!=": v != w, "<": v < w, ">": v > w,
            "<=": v <= w, ">=": v >= w}.get(op, True)


def holds(preds, items, flags):
    """Do these guards hold under (items, flags)? Deliberately PERMISSIVE about
    anything we cannot evaluate -- an unknown guard is assumed satisfiable. That
    biases us to MISS strandings rather than invent them, which is the direction
    we want: a false 'you're stuck' would be far worse than a quiet omission.

    Negative ownership (`(not (ego has: X))`) is also treated as satisfiable: the
    fixpoint is monotonic in items, so it cannot model 'you must not hold X'.
    """
    for p in preds:
        if p.kind == "OWN":
            if p.want and p.var not in items:
                return False            # must hold it, and we can't get it
        elif p.kind == "FLAG":
            vals = flags.get(p.var)
            if vals and p.want and not _truthy(vals):
                return False
        elif p.kind == "CMP":
            vals = flags.get(p.var)
            if vals and not any(_cmp_ok(v, p.op, p.value) for v in vals):
                return False
    return True


def closure(m: FixModel, start_room, held=(), flags=None, exhausted=()):
    """Least fixpoint from a state: everything you could EVER reach/obtain."""
    rooms = {start_room}
    items = set(held)
    fl = {k: set(v) for k, v in (flags if flags is not None else m.init_flags).items()}
    exhausted = set(exhausted)

    changed = True
    while changed:
        changed = False
        # 1. walk anywhere whose edge preconditions hold
        for a in list(rooms):
            for b in m.edges.get(a, ()):
                if b not in rooms and holds(m.edge_reqs.get((a, b), ()), items, fl):
                    rooms.add(b)
                    changed = True
        # 2. pick up anything acquirable in reach (and not consumed away)
        for it, sites in m.acq.items():
            if it in items or it in exhausted:
                continue
            for room, guards in sites:
                if (room is None or room in rooms) and holds(guards, items, fl):
                    items.add(it)
                    changed = True
                    break
        # 3. set any flag we can reach the setter of (room None == global code)
        for g, sites in m.sets.items():
            for room, val, guards in sites:
                if (room is None or room in rooms) and val not in fl.get(g, ()) \
                        and holds(guards, items, fl):
                    fl.setdefault(g, set()).add(val)
                    changed = True
    return Reach(rooms, items, fl)


def winnable(m: FixModel, start_room, held=(), flags=None, exhausted=(), goals=None):
    goals = set(goals if goals is not None else CFG.goal_rooms)
    return bool(closure(m, start_room, held, flags, exhausted).rooms & goals)


def strandings(m: FixModel, start=None, goals=None):
    """Softlock findings, as post-state queries over irreversible actions.

    Not a feature -- a query. `W(room, x)` asks: standing in `room` holding
    everything EXCEPT x, can you still win? (The closure re-acquires x for free if
    a source is still reachable, so a "no" means genuinely unrecoverable.)

    An edge a->b then strands x exactly when  W(a,x) and not W(b,x)  -- obtainable
    before, unrecoverable after. That is the LucasArts invariant, derived rather
    than guessed: no `_sealed`, no reciprocity heuristic, no SCC condensation.

    Memoised on (room, x), not (a, b, x): winnability past an edge depends only on
    where you land and what you lack.
    """
    start = CFG.start_room if start is None else start
    goals = set(CFG.goal_rooms if goals is None else goals)
    base = closure(m, start)
    imax = frozenset(base.items)

    # only items that actually gate something can strand you
    cand = sorted(x for x in m.gating_items if x in imax)

    memo = {}

    def W(room, x):
        k = (room, x)
        if k not in memo:
            memo[k] = bool(closure(m, room, imax - {x}).rooms & goals)
        return memo[k]

    def winnable_from(room):
        k = (room, None)
        if k not in memo:
            memo[k] = bool(closure(m, room, imax).rooms & goals)
        return memo[k]

    out = []
    for a in sorted(base.rooms):
        for b in sorted(m.edges.get(a, ())):
            if b not in base.rooms:
                continue
            if not winnable_from(b):
                continue          # absorbing sink (a death room): you lose there
                                  # holding EVERYTHING, so it strands nothing --
                                  # it just says "dying loses", which is not news.
            already = {p.var for p in m.edge_reqs.get((a, b), ())
                       if p.kind == "OWN" and p.want}
            for x in cand:
                if x in already:
                    continue          # the game already refuses to let you cross
                if W(a, x) and not W(b, x):
                    out.append({"from_room": a, "to_room": b, "item": x,
                                "item_name": m.g.item_name(x)})
    return out


def consumable_strandings(m: FixModel, start=None, goals=None):
    """Items whose LOSS is unrecoverable and fatal to winning -- e.g. eating the
    magic fruit. Post-state = the item gone AND its sources exhausted (a one-shot
    pickup does not respawn just because you can walk back to the room)."""
    start = CFG.start_room if start is None else start
    goals = set(CFG.goal_rooms if goals is None else goals)
    base = closure(m, start)
    out = []
    for x in sorted(m.gating_items):
        if x not in base.items:
            continue
        r = closure(m, start, exhausted={x})
        if not (r.rooms & goals):
            out.append({"item": x, "item_name": m.g.item_name(x)})
    return out


def main():
    game = load_game()
    m = FixModel(game)
    r = closure(m, CFG.start_room)
    goals = set(CFG.goal_rooms)
    rooms_total = len([n for n in game.scripts if is_room(game, n)])
    print(f"{CFG.name}")
    print(f"  edges with preconditions : {len(m.edge_reqs)}")
    print(f"  closure from rm{CFG.start_room}: {len(r.rooms)}/{rooms_total} rooms, "
          f"{len(r.items)}/{len(game.items)} items, {len(r.flags)} globals")
    ok = bool(r.rooms & goals)
    print(f"  goal {sorted(goals)} reachable? {ok}")
    print(f"  SANITY: a shipped game must be winnable with nothing removed -> "
          f"{'PASS' if ok else 'FAIL (the model is wrong, not the game)'}")
    if not ok:
        missing = sorted(goals - r.rooms)
        print(f"    unreached goal rooms: {missing}")
    return m, r


if __name__ == "__main__":
    main()
