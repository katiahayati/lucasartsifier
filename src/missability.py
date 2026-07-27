"""Missability sweep on the JSON-IR / opmodel front-end (the canonical one), NOT the stale
model.Game / analyze.py front-end that search.py was left on.

search.py's SCC-condensation *algorithm* (tarjan_scc, reobtainable_rooms/_sealed,
edge_strandings, analyze) is sound and front-end-agnostic -- it operates on a generic
(room-graph, item-sources, required-set, goal) interface. This module builds that interface
from the JSON-IR OpEmitter so the sweep inherits every extraction fix the winnability engine
already has: the revolving-door indirect-newRoom resolution (rm40 -> rm43/44/45, which makes
Matches' room reachable), debug-global pinning, etc. Then it just subclasses SccReach.
"""
from __future__ import annotations

import os
from collections import defaultdict, deque

import ir as I
import config
import opmodel as E
import vocab
import grid
from guard_ast import GAnd, GOr, GNot, Pred
from scc_core import tarjan_scc, reachable, SccReach

# Item names are a reporting nicety; the IR JSON carries only the raw instance name, so derive the
# number -> name map from the game's own class table (vocab.item_names). Previously this was a
# hardcoded LSL2 dict applied to EVERY game, so KQ4's Shovel printed as "Bikini_Top" -- the last
# game-specific catalogue, now gone. The ANALYSIS was always fully on JSON-IR; only these labels
# were game-specific, and now they derive too.
class _ItemNames:
    def __init__(self, names):
        self._names = names        # {number: name}, derived per game

    def item_name(self, it):
        return self._names.get(it, f"item{it}")


def _own_positive(guard):
    """Item numbers that appear as a POSITIVE own(item) in `guard` (a guard-tree, a list of
    atoms as machine-state guards carry, or None)."""
    out = set()
    def walk(g, pol):
        if g is None:
            return
        if isinstance(g, list):
            for x in g:
                walk(x, pol)
        elif isinstance(g, Pred):
            if g.kind == "OWN" and pol:
                out.add(g.var)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, GNot):
            walk(g.kid, not pol)
        # ("CTR",...) / ("POS",...) tuples carry no OWN
    walk(guard, True)
    return out


def _own_required(guard):
    """Items NECESSARILY held whenever `guard` is true -- the REQUIREMENT semantics, stricter than
    `_own_positive`. An item inside an OR-branch is NOT required (another branch may satisfy the
    guard), so GOr INTERSECTS its kids while GAnd UNIONS them (and negation swaps the two, De
    Morgan). This is why KQ4's Obsidian Scarab is NOT required by the nightfall guard `(or (clock)
    (and (>= g109 3) (has:7) (has:25)))`: it is one WAY night falls, not a thing you must hold. A
    disjunctive requirement (ash OR sand) correctly contributes nothing here -- it is caught by
    `disjunctive_groups`, not by per-item `required`."""
    def walk(g, pol):
        if g is None:
            return set()
        if isinstance(g, list):
            out = set()
            for x in g:
                out |= walk(x, pol)
            return out
        if isinstance(g, Pred):
            return {g.var} if (g.kind == "OWN" and pol) else set()
        if isinstance(g, GNot):
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)     # AND&true or OR&false -> union; else intersect
            sets = [walk(k, pol) for k in g.kids]
            if not sets:
                return set()
            return set().union(*sets) if union else set.intersection(*sets)
        return set()
    return walk(guard, True)


def _loc_placed_required(guard, placed):
    """Items required by a POSITIVE owner-gate `owner == R` where R is a room the item is PLACED at
    (a `put`/`moveTo` writes its owner to R -- see extract.TS.placed). Reaching `owner == R` for a
    placed room means the item was actively put there, which required holding it, so the item is
    required wherever the gate is. A gate on the item's INITIAL resting room -- never written, so
    not in `placed` -- is the 'is it still there?' check (KQ4's fruit `owner == 78`) and contributes
    nothing. Same De Morgan polarity as `_own_required`: an owner-gate inside an OR-branch is not
    required, because another branch may satisfy the guard. This is the state-grounded reading of
    the owner-gate the source heuristic could not give: the writes ARE the owner's transitions, so
    'use it in the room you got it' is a placement like any other and correctly requires the item."""
    def walk(g, pol):
        if g is None:
            return set()
        if isinstance(g, list):
            out = set()
            for x in g:
                out |= walk(x, pol)
            return out
        if isinstance(g, Pred):
            if (g.kind == "LOC" and pol and isinstance(g.value, int)
                    and g.value in placed.get(g.var, ())):
                return {g.var}
            return set()
        if isinstance(g, GNot):
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)
            sets = [walk(k, pol) for k in g.kids]
            if not sets:
                return set()
            return set().union(*sets) if union else set.intersection(*sets)
        return set()
    return walk(guard, True)


def _after(info, tr, gr, goal_ok):
    """Can the goal still be reached AFTER taking this transition?"""
    if tr[0] == "DEATH":
        return False                           # death is just one way to fail goal-reachability
    if tr[0] == "EXIT":
        return tr[1] in goal_ok
    if tr[0] == "PARK":
        return info["room"] in goal_ok         # control returns to the player, in this room
    return True                                # ADVANCE/JUMP/SETSTATE resolve via `gr`


def next_state(K, tr):
    """The machine state a transition lands on, or None if it leaves the machine."""
    return (K + 1 if tr[0] == "ADVANCE" else
            tr[1] if tr[0] == "JUMP" else
            tr[1] + 1 if tr[0] == "SETSTATE" else None)


def hopeful(info, K, tr, gr, goal_ok):
    """Can the goal still be reached after taking this path out of state K?

    This is the rule the TRAP test is built on. An own(X)-guarded path you cannot still WIN from
    is not evidence that X is required -- death is merely the commonest way to fail that, and a
    use stranding you in a region with no route to the goal fails it identically."""
    nxt = next_state(K, tr)
    return _after(info, tr, gr, goal_ok) if nxt is None else gr.get(nxt, True)


def goal_reaching(info, goal_ok):
    """State -> can the goal still be reached from it (backward fixpoint over the machine)."""
    gr, changed = {}, True
    while changed:
        changed = False
        for K, paths in info["states"].items():
            cur = any(hopeful(info, K, tr, gr, goal_ok) for (g, w, gg, c, tr) in paths)
            if gr.get(K) != cur:
                gr[K] = cur
                changed = True
    return gr


def goal_reaching_rooms(edges, goal_rooms):
    """Rooms from which a goal room is still reachable (backward walk in the room graph).

    The guard-IGNORING graph is deliberate: over-approximating goal-reachability makes fewer uses
    look hopeless, so we under-call traps and OVER-require -- the safe direction."""
    rev = defaultdict(set)
    for a, bs in edges.items():
        for b in bs:
            rev[b].add(a)
    return reachable(rev, set(goal_rooms))


def _debug_gated_guard(guard, debug_idx=frozenset()):
    """Does this guard depend on QA scaffolding? Those branches are not real availability --
    LSL2's rm82 hands you the entire bomb under `if gDebugging`."""
    refs = []
    def w(g):
        if isinstance(g, list):
            for x in g: w(x)
        elif isinstance(g, Pred):
            if g.var in debug_idx: refs.append(g.var)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids: w(k)
        elif isinstance(g, GNot):
            w(g.kid)
    w(guard)
    return bool(refs)


def _iprop_spec(em):
    """(item, prop) -> {values, counter} for the fourth store, as extraction discovered it."""
    import extract as X
    return dict(getattr(X, "_IPROPS", {}))


_IPROP_SPEC = {}


def build_maps(em):
    """(edges, edge_kind, sources, drops, required, guard_required) from the JSON-IR OpEmitter.

    `guard_required` is `required` WITHOUT the consumption fallback -- only rooms where the game
    actually tests `has: X`. That is the evidence that an item ARMS something, which is a
    different question from where it is needed, and `real_uses` wants the former."""
    global _IPROP_SPEC
    _IPROP_SPEC = _iprop_spec(em)
    edges, edge_kind = defaultdict(set), defaultdict(set)
    md = em.machine_delivered

    def add(a, b):
        edges[a].add(b); edge_kind[(a, b)].add("goto")   # every JSON-IR movement is a newRoom

    for e in em.ts.edges:
        add(e.src, e.dst)
    for e in em.ts.cs_edges:
        if (e.src, e.dst) not in md:
            add(e.src, e.dst)
    # A machine EXIT to a spliced-out MAZE DISPATCHER means "walk out of this cell", so it
    # resolves to the rooms the grid says you can walk to -- not to the dispatcher, which is only
    # the code that computes where you come out and would otherwise reconnect the levels the maze
    # keeps apart. The flat and cutscene edges were substituted in `extract`; these are built here,
    # so the same rule is applied here rather than left as the one path that leaks.
    disp = getattr(em.ts, "dispatchers", set())
    mreach = getattr(em.ts, "maze_reach", {})
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    if tr[1] in disp:
                        for d in sorted(mreach.get(info["room"], ())):
                            add(info["room"], d)
                    else:
                        add(info["room"], tr[1])

    # sources: skip DEAD debug-gated acquires (rm82's `(if gDebugging (get 19 21 27))` bomb
    # hand-out). The JSON-IR TRACKS gDebugging rather than const-pinning it, so gexpr won't
    # fold `gDebugging != 0` to FALSE -- and the IR json carries no global names, so we can't
    # resolve config.debug_globals to indices from it. TODO(generalize): pin debug globals in
    # the emitter / carry a name->index map. For now use the known LSL2 debug indices.
    DEBUG_IDX = frozenset(em.cfg.debug_globals)
    def _debug_gated(guard):
        refs = set()
        def w(g):
            if isinstance(g, list):
                for x in g: w(x)
            elif isinstance(g, Pred):
                if g.var in DEBUG_IDX:
                    refs.add(g.var)
            elif isinstance(g, (GAnd, GOr)):
                for k in g.kids: w(k)
            elif isinstance(g, GNot):
                w(g.kid)
        w(guard)
        return bool(refs)
    sources, drops = defaultdict(set), defaultdict(set)
    for a in em.ts.acqs:
        if not _debug_gated(a.guard):
            sources[a.item].add(a.room)
    for room, script, it, g in em.handler_gets:
        if not _debug_gated(g):
            sources[it].add(room)
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                for it in gg:
                    sources[it].add(info["room"])

    # BULK transfers -- the whole inventory at once, written as a walk of the Inv list setting
    # each item's `owner:`. KQ4 confiscates everything at rm92 (captured) and rm81 (the wedding
    # room) into room 89, and rm89's cupboard hands it all back. No item number appears anywhere
    # in that code, so this is the one case where "no constant" has to mean "every item".
    #
    # Fed to sources/drops only, NOT to the consumption-as-requirement fallback: being taken from
    # you is not evidence that you needed it there.
    all_items = set(em.ts.items) | set(sources) | {it for _r, _s, it, _g in em.handler_gets}
    for room, dest, _g in getattr(em.ts, "bulk_moves", ()):
        for it in all_items:
            (sources if dest == E.EGO else drops)[it].add(room)

    # THE FOURTH STORE. An item's own property can hold state, and putting it into a state the
    # item's USES reject is the same thing as losing the item:
    #     Room16:249  (if (and (gEgo has: 15) (== 0 ((Inv at: 15) loop:))) ... dig ...)
    #     Room16:592  ((Inv at: 15) loop: 1)            -- the shovel breaks, and stays broken
    #     Room82:625  ((Inv at: 14) loop: (+ ... 1))    -- an arrow is spent, and never comes back
    # The shovel is a CHAIN, and we currently see only its last link:
    #     Room16:611  (= local5 (* (- (++ global113) 1) 3))   ++ per hole dug -- INVISIBLE, since
    #                                                          _hwalk handles Increment on LOCALS
    #                                                          only, never on globals
    #     Room16:589  (if (>= global113 5) ...)                ignored -- relational ops are
    #                                                          deliberately permissive
    #     Room16:592  ((Inv at: 15) loop: 1)                   recorded, as of this change
    # so the drop site is right and its CONDITION is not modelled at all. Over-approximating a
    # loss is the safe direction, but nothing yet turns it into a finding -- see TODO A0g.
    # so these feed `drops`, not the movement product: nothing about them is a room gate.
    #
    # ONE-WAY is the whole question, and the discovered value set answers it without a rule about
    # `loop`: a property written to exactly one value, or incremented with no reset, cannot be put
    # back. KQ4's fishing pole writes BOTH 0 and 1 -- you can re-bait it -- so it is excluded, and
    # excluded for a reason rather than by name.
    for room, it, prop, val, _g, *_rest in getattr(em.ts, "item_prop_writes", ()):
        spec = getattr(E.X, "_IPROPS", {}).get((it, prop)) if hasattr(E, "X") else None
        spec = spec or _IPROP_SPEC.get((it, prop))
        if spec and (spec.get("counter") or len(spec.get("values", ())) == 1):
            drops[it].add(room)

    # DROP sites -- where an item can LEAVE your inventory. Declared since the first version but
    # never populated. Needed to place NEGATIVE guard literals: `!own(Spinach_Dip)` may only be
    # demanded where the dip can still be got rid of (rm131, `throw bread overboard`, +2 score).
    # Guarding it later would convert a death into a permanent wall.
    for room, script, it, g, _dest in getattr(em, "handler_drops", ()):
        drops[it].add(room)
    for info in em.machines:
        for it in info.get("drops", ()):
            drops[it].add(info["room"])

    # required: rooms whose guard tests own(item)==True (across every guard-bearing structure).
    # PASS 1 -- TRAP items: an item whose own()-guarded branch walks into a DEATH is a trap, not
    # a requirement (Spinach_Dip: eat it -> "the mayonnaise has spoiled" -> death). Mark them
    # GLOBALLY, because the same item is also consumed on a survivable-looking `Said 'eat'`
    # handler (rm300) that would otherwise re-add it as required.
    # The rule is GOAL-REACHABILITY, not death: a use you cannot still win from is not evidence
    # that the item is needed. Death is merely the commonest way to fail that -- a use that dumps
    # you in a region with no path to the goal fails it too, and this catches those for free.
    # An item is a TRAP only if EVERY own()-guarded use is hopeless: Grotesque_Gulp has a fatal
    # use (drink it at the wrong moment) AND winnable ones (the raft), so "hopeless anywhere"
    # would wrongly un-require it; Spinach_Dip is hopeless everywhere.
    goal_ok = goal_reaching_rooms(edges, em.cfg.goal_rooms)

    gr_maps, hopefuls, hopeless = {}, set(), set()
    for i, info in enumerate(em.machines):
        gr = gr_maps[i] = goal_reaching(info, goal_ok)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                target = hopefuls if hopeful(info, K, tr, gr, goal_ok) else hopeless
                target |= _own_positive(g)
    # ...and the uses that live on a MOVEMENT EDGE. The rule below is "a trap is an item whose
    # EVERY own()-guarded use is hopeless", but it only ever looked at machine states, so an item
    # whose real use is an edge could be condemned by an unrelated machine branch -- and being
    # named a trap erases the item's requirements GLOBALLY, including the ones that edge
    # established. KQ4's Peacock_Feather is exactly that: it tickles the whale into sneezing you
    # out (the rm44->rm31 edge, which reaches the goal), but it ALSO picks the longer digestion
    # timer inside the whale, and that branch ends in death whichever way it is taken. Judging it
    # on the timer alone made the feather a trap and dropped a confirmed stranding.
    for e in list(em.ts.edges) + list(em.ts.cs_edges):
        (hopefuls if e.dst in goal_ok else hopeless).update(_own_positive(e.guard))
    trap_items = hopeless - hopefuls

    required = defaultdict(set)
    # CONSUMPTION is a FALLBACK evidence source, not an additive one -- see the note where it is
    # applied, below. Collected separately so it can be weighed after all guard evidence is in.
    consumed_at = defaultdict(set)
    def req_item(it, room):
        if it not in trap_items:
            required[it].add(room)
    def req(guard, room):
        for it in _own_required(guard):     # OR-branch items are NOT required -- see _own_required
            req_item(it, room)
        for it in _loc_placed_required(guard, em.ts.placed):   # owner-gate on a PLACED room
            req_item(it, room)
    for e in em.ts.edges:
        req(e.guard, e.src)
    for e in em.ts.cs_edges:
        req(e.guard, e.src)
    for a in em.ts.acqs:
        req(a.guard, a.room)
    for room, script, it, g in em.handler_gets:
        req(g, room)
    for room, script, gi, v, g in em.handler_writes:
        req(g, room)
    # entry guards of machines we chose not to model -- see opmodel.dropped_entries
    for room, eg in getattr(em, "dropped_entries", ()):
        req(eg, room)
    # consuming an item in a HANDLER -- the Pamphlet handed to the bore on the plane (rm62) is a
    # Said-handler `put: 26 -1`, which the machine-body scan never sees. Held back; see below.
    for room, script, it, g, _dest in getattr(em, "handler_drops", ()):
        consumed_at[it].add(room)
    for i, info in enumerate(em.machines):
        gr = gr_maps[i]
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                # Same GOAL-REACHABILITY rule as the trap pass, applied per use: an own(X) path
                # you cannot still win from is not evidence X is required here. rm138's day-6
                # hunger accepts own(Spinach_Dip) -> eat it -> "the mayonnaise has spoiled in the
                # hot, tropical sun!" -> death, while the sibling own(Sewing_Kit) branch fishes
                # and lives. Counting the hopeless branch made Spinach_Dip look required.
                if not hopeful(info, K, tr, gr, goal_ok):
                    continue
                req(g, info["room"])
        # machine ENTRY guards too: a `Said 'throw/beach'` success branch is captured as an
        # entry/changeState guarded by own(Sand) -- skipping entries lost Sand/Ash.
        for K, eg in info.get("entries", ()):
            req(eg, info["room"])
        for K, eg in info.get("init_entries", ()):
            req(eg, info["room"])
        for it in info.get("drops", ()):
            consumed_at[it].add(info["room"])

    # CONSUMPTION as requirement evidence -- a FALLBACK, scoped exactly as its own rationale
    # always stated: it "catches requirements carrying NO own() guard at all", like the Flower
    # handed to the KGBishnas (rm50), which exists in the game only as `gEgo put: 20 -1`.
    # It was being applied unconditionally, which is additive rather than fallback, and that is
    # a different rule: for an item the game DOES test for, every place it is later used up
    # becomes an extra "needed here" room -- including places past a one-way edge.
    #
    # That produced two confirmed false positives the moment `moveTo:` extraction made LSL2's
    # consumptions visible: rm48's "take off the bikini" handler destroys the Soap, the
    # Bikini_Top and the Bikini_Bottom on three adjacent lines, so all three gained `required@48`
    # beyond the one-way rm47 -> rm48. Both the Soap and the Bikini_Bottom are re-obtainable/safe
    # in play (confirmed by the user); the Bikini_Top is a true softlock, but on its own evidence
    # -- the real `has:` test at rm44, across the rm38 -> rm131 boarding frontier.
    #
    # An item the game tests for already tells us where it is needed. Consumption only speaks
    # for items that carry no test at all -- which is every case this rule was built for
    # (Flower, Pamphlet, Bobby_Pin, Airsick_Bag, Matches, Hair_Rejuvenator, Sand, ...), all of
    # which have empty guard evidence and so are untouched.
    guard_required = {it: set(rooms) for it, rooms in required.items()}
    for it, rooms in consumed_at.items():
        if not required.get(it):
            for room in rooms:
                req_item(it, room)

    # NOTE: a CUTSCENE-SPLICE pass used to live here -- it rewrote `pred -> cutscene -> succ`
    # into `pred -> succ` to fix the Airline_Ticket false positive. It is RETIRED (git history
    # has it). It needed three guards, each added only after the sweep collapsed, and it was
    # actively harmful: splicing rm83 out fabricated an rm82 -> rm92 edge that reconnected the
    # volcano to the island hub, hiding the Ashes/Sand stranding. The gate-aware product graph
    # subsumes it -- the ticket FP was really an unguarded duplicate edge shadowing the machine
    # EXIT's own(ticket) guard (see edge_meta's machine_delivered filter).
    return edges, edge_kind, sources, drops, required, guard_required


def _cmp_atoms(guard, out):
    """Collect (register, op, const, polarity) comparison atoms from a guard tree."""
    def w(x, pol=True):
        if isinstance(x, list):
            for y in x:
                w(y, pol)
        elif isinstance(x, Pred):
            if x.kind == "CMP":
                try:
                    out.append((x.var, x.op, int(x.value), pol))
                except (TypeError, ValueError):
                    pass
        elif isinstance(x, (GAnd, GOr)):
            for k in x.kids:
                w(k, pol)
        elif isinstance(x, GNot):
            w(x.kid, not pol)
    w(guard)


def _movement_guards(em):
    """Every guard that can gate MOVEMENT: room edges, machine EXIT paths, and machine entries
    (an entry gates the state chain that leads to an EXIT)."""
    for e in em.ts.edges:
        yield e.guard
    for e in em.ts.cs_edges:
        yield e.guard
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    yield g
        for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
            yield eg


def gating_registers(em):
    """DISCOVER the registers worth promoting into the movement model, instead of naming one.

    The product exists to catch exactly one thing: an edge that SETS R:=v composed with an edge
    that REQUIRES R==w for w != v. So a register earns promotion iff it is BOTH compared against
    in a movement guard AND written somewhere -- a register that is never written cannot create
    an inconsistent composition, and one that is never compared cannot block anything.

    Purely structural: on LSL2 this rediscovers gCurrentStatus (101) as the widest gater, plus 18
    others, with no game knowledge. See docs/HOW-IT-WORKS.md for why they are kept as independent
    PROJECTIONS rather than one joint product."""
    compared = set()
    for g in _movement_guards(em):
        atoms = []
        _cmp_atoms(g, atoms)
        for (r, op, v, pol) in atoms:
            compared.add(r)
    written = set()
    for room, script, gi, v, g in em.handler_writes:
        written.add(gi)
    # `init` runs on arrival, so a register it sets is genuinely written -- it was only collected
    # apart to keep arrival atomic. Omitting it here meant a flag raised ONLY on entering a room
    # counted as never-written and so was never promoted, however much movement it gated. That is
    # how KQ6 seals the realm of the dead: rm600's init raises flag 15, nothing clears it, and the
    # way in demands it clear.
    for room, vs in getattr(em, "init_writes", {}).items():
        written.update(vs)
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                for (gi, v) in w:
                    written.add(gi)
    # The PREVIOUS-ROOM register is written by no room and by every transition: the Game loop's
    # room switch does `(= <prev> <current>)` before it goes (see extract.prev_room_global), so
    # taking any edge a->b sets it to a. `edge_meta` puts that write on the edge; here it only has
    # to count as written, or the "never written cannot create an inconsistent composition" rule
    # above would keep refusing to promote it while 13 KQ6 edges, 12 KQ4, 53 KQ5 compare against it.
    prev = prev_room_reg(em)
    if prev is not None:
        written.add(prev)
    return sorted(compared & written)


def prev_room_reg(em):
    """The previous-room register for this game, derived once per model. See edge_meta.

    None for a model with no IR behind it -- the derivation reads the Game loop, so a synthetic
    emitter that has no scripts has no previous-room register rather than a default one."""
    if not hasattr(em, "_prev_reg"):
        import extract as X
        ir = getattr(em, "ir", None)
        em._prev_reg = X.prev_room_global(ir) if ir is not None else None
    return em._prev_reg


def asserts_eq(op, pol):
    """Does a `(reg, op, value, polarity)` atom assert `reg == value`?

    Both spellings do: `x == v`, and `not (x != v)`. The second matters because `(if (not gX)
    ...)` is SCI's way of writing "gX is 0" and `atom()` renders a bare global's truthiness as
    `CMP(gX, !=, 0)` -- which is how KQ4's day-only doors are gated.

    Shared deliberately: this test used to be spelled out separately in `required_values` and in
    `edge_meta.reqs`, and fixing one and not the other left the night gate parsed but toothless."""
    return (op == "==" and pol) or (op == "!=" and not pol)


def _must_hold(guard, out=None):
    """`(reg, value)` pairs the guard REQUIRES along its top-level AND spine.

    `_cmp_atoms` is deliberately flat -- it ignores AND/OR structure and reports every comparison
    it can see. That is fine for collecting positive equalities, which only ever under-constrain,
    but it cannot be used to turn `!= 0` into `== 1`: under a NOT or inside an OR the flag is not
    required at all, and claiming it would BLOCK movement the game allows. So this walks only the
    conjuncts that must hold, stopping at any negation or disjunction."""
    out = set() if out is None else out
    if isinstance(guard, list):
        for g in guard:
            _must_hold(g, out)
    elif isinstance(guard, GAnd):
        for k in guard.kids:
            _must_hold(k, out)
    elif isinstance(guard, Pred) and guard.kind == "CMP" and guard.op == "!=":
        try:
            out.add((guard.var, int(guard.value)))
        except (TypeError, ValueError):
            pass
    elif (isinstance(guard, GNot) and isinstance(guard.kid, Pred)
          and guard.kid.kind == "CMP" and guard.kid.op == "=="):
        # `(not (== x v))` is the same assertion as `(!= x v)` -- the two spellings SCI compiles
        # the same test into, and only one of them was read here. Descending a negation is safe
        # exactly when its operand is a leaf: the flip is computable, which is not true of the
        # subtree cases this deliberately stops at.
        try:
            out.add((guard.kid.var, int(guard.kid.value)))
        except (TypeError, ValueError):
            pass
    return out


def guard_reqs(guard, regs, dom=None):
    """{reg: {values it REQUIRES}} for every reg in `regs` this guard constrains.

    THE one reading of "what does this guard demand of a register", used by both consumers: the
    per-register `required_values` (machine entries, state musts) and `edge_meta`'s per-edge scan.
    They were separate, and only this one knew the flag-SET rule below, so a "this flag is set"
    gate constrained a machine entry and nothing at all on a room edge -- which is how KQ6's realm
    of the dead kept its doors open. See the same-shaped bug in `asserts_eq`'s docstring.

    Only positive equalities are used. `!=` and the relational ops are deliberately ignored: they
    would need the value-partition abstraction to stay exact, and ignoring them is the PERMISSIVE
    direction (we never block movement the game allows).

    A NEGATED `!=` is a positive equality, though, and that is not a technicality: `(if (not gX)
    ...)` is how SCI writes "gX is 0", and `atom()` turns bare-global truthiness into
    `CMP(gX, !=, 0)`. KQ4's day-only doors are guarded exactly that way -- `(if (not global100)
    <open the door>)` -- so without this the night gate parsed fine and then constrained nothing.

    ...and a POSITIVE `!=` is exact too whenever we know the register's COMPLETE domain, because
    "not v" is then just "one of the others". Two registers qualify and `dom` carries them:

      * a flag global WE minted from a flag store -- our lowering writes 1 to set and 0 to clear
        and nothing else, so `(!= flag 0)` IS `== 1`. The only way a "this flag is SET" gate can
        ever carry, and KQ6's walk out of the catacombs needs the minotaur-defeated flag.
      * the PREVIOUS-ROOM register, whose domain is the set of rooms an edge can leave from -- by
        construction, since `edge_meta` is what writes it. KQ6's realm of the dead is left through
        exactly one door and that door reads `(!= global12 670)`: you may go out only if you came
        back from rm690, which is to say only if you held up the mirror and won.

    Both stay subject to `_must_hold`, so a `!=` under a negation or inside an OR still constrains
    nothing -- claiming otherwise would block movement the game allows.

    One walk of the guard tree for ALL the registers: walking it once per register made edge_meta
    19x slower than it needed to be, and `_must_hold` is only paid for if such an atom shows up.
    """
    atoms = []
    _cmp_atoms(guard, atoms)
    out, must = {}, None
    for (r, op, v, pol) in atoms:
        if r not in regs:
            continue
        if asserts_eq(op, pol):
            out.setdefault(r, set()).add(v)
        elif (op == "!=" and pol) or (op == "==" and not pol):
            # Both spellings of "not equal", the mirror of asserts_eq's two spellings of "equal".
            full = ({0, 1} if (v == 0 and r in vocab.BOOL_GLOBALS)
                    else (dom or {}).get(r))
            if not full or v not in full:
                continue                        # domain unknown, or the test excludes nothing
            if must is None:
                must = _must_hold(guard)        # only conjuncts that MUST hold -- see _must_hold
            if (r, v) in must:
                out.setdefault(r, set()).update(full - {v})
    return out


def required_values(guard, reg):
    """Values of `reg` this guard REQUIRES, or None if it doesn't constrain it. See guard_reqs."""
    return guard_reqs(guard, (reg,)).get(reg) or None


def structural_reqs(guard, regs, dom=None):
    """{reg: {values}} NECESSARILY true whenever `guard` is -- the register twin of `_own_required`.

    `guard_reqs` reads the atoms FLAT, which is right for its job (what values may this edge be
    crossed at) and wrong for composing one guard into another, because a disjunction of two ways
    through reads as a conjunction of both their conditions. KQ4's whale is exactly that shape:

        (or (and (not (prev == 43)) (prev == 44))         ; arrived from inside the whale
            (and (g109 == 1) ... (g183 == 0) ...))        ; swam up to it with the flute played

    Flat, that demands prev == 44 AND g109 == 1 to be swallowed -- i.e. you may only enter the
    whale if you have just come out of it. So GOr keeps a register only if EVERY branch constrains
    it, unioning the values, and GAnd unions the registers, intersecting values where both
    constrain one. Negation swaps the two, as in `_own_required`."""
    regs = set(regs)

    def walk(g, pol):
        if g is None:
            return {}
        if isinstance(g, list):
            return walk(GAnd(list(g)), pol)
        if isinstance(g, Pred):
            got = guard_reqs(g if pol else GNot(g), regs, dom)
            return {R: set(v) for R, v in got.items()}
        if isinstance(g, GNot):
            if isinstance(g.kid, Pred):
                got = guard_reqs(g if pol else g.kid, regs, dom)
                return {R: set(v) for R, v in got.items()}
            return walk(g.kid, not pol)
        if isinstance(g, (GAnd, GOr)):
            union = pol == isinstance(g, GAnd)   # AND&true or OR&false -> union; else intersect
            kids = [walk(k, pol) for k in g.kids]
            if not kids:
                return {}
            if union:
                out = {}
                for d in kids:
                    for R, vs in d.items():
                        out[R] = (out[R] & vs) if R in out else set(vs)
                return {R: vs for R, vs in out.items() if vs}
            keep = set(kids[0])
            for d in kids[1:]:
                keep &= set(d)
            return {R: set().union(*(d[R] for d in kids)) for R in keep}
        return {}
    return walk(guard, True)


def entry_alts(info):
    """State K -> the ALTERNATIVE ways of arming it: a tuple of item-sets, one per machine entry
    that reaches K (DNF). K is armed iff you satisfy SOME alternative, so an EXIT at K is
    traversable iff some alternative is fully held.

    Disjunction, not conjunction. rm81 (past the vine chasm) is armed only by `throw ash`
    (own 30) OR `throw sand` (own 31): intersecting them gives {} ("free"), unioning them gives
    {30,31} ("needs both") -- both wrong. Keeping them as alternatives is what lets the sweep say
    losing EITHER is survivable while losing BOTH strands you. An empty tuple means no entry
    reaches K (treat as ungated); an alternative that is itself empty means K can be armed with
    no items at all, so the gate is free."""
    # Which states each entry reaches -- CARRIED-LOCAL aware. The successor walk threads the locals
    # the arming context wrote (info["entry_locals"], parallel to entries) and prunes an ADVANCE
    # whose guard tests a CARRIED local the entry does not satisfy. knockDoor's "open the door" entry
    # carries no local1, so at the door state its only advancing path (the `if local1` branch) is
    # pruned and no other path advances -- a genuine ABORT -- so it never reaches the newRoom:18
    # state to dilute the staff requirement. Crucially this prunes only on a FULL abort (no path
    # advances): a machine that merely branches on a carried local still advances via its other
    # path. A machine with NO carried locals (the common case, ~all of LSL2/KQ4) threads {} and takes
    # every advance exactly as the old guard-ignoring graph did -- byte-for-byte identical.
    from compile import _ctr_holds
    def _paired(es_key, loc_key):
        # Pad locals to the entry count with {} rather than zip-truncating: a machine whose entries
        # carry no recorded locals (every synthetic test, and any entry opmodel didn't annotate)
        # must still contribute its entry, threading no carried local -- the old behaviour. A bare
        # zip silently DROPPED such entries, emptying entry_alts and ungating the EXIT.
        es = list(info.get(es_key, ()))
        locs = list(info.get(loc_key, ()))
        locs += [{}] * (len(es) - len(locs))
        return list(zip(es, locs))
    ents = _paired("entries", "entry_locals") + _paired("init_entries", "init_entry_locals")
    carried = set().union(*[set(loc) for _ke, loc in ents]) if ents else set()

    def _ctr_ok(g, counters):
        for a in g:                                # g is a path's atom list (a conjunction)
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in carried and not _ctr_holds(a, counters):
                return False
        return True

    def _apply(counters, cw):
        c = dict(counters)
        for (name, kind, val) in cw:
            if name not in carried:
                continue                           # track only carried locals -> bounded state space
            c[name] = val if kind == "set" and val is not None else \
                c.get(name, 0) + (1 if kind == "inc" else -1 if kind == "dec" else 0)
        return c

    per_entry = _entry_reach_walk(info, ents, carried, _ctr_ok, _apply)
    out = {}
    for K in info["states"]:
        out[K] = tuple({frozenset(_own_positive(eg)) for (seen, eg, _loc) in per_entry if K in seen})
    return out


def _entry_reach_walk(info, ents, carried, _ctr_ok, _apply):
    """[(states this entry can reach, its guard)] -- the ONE entry-reachability walk.

    Factored out because two views need it: `entry_alts` (which items arm a state) and
    `entry_reqs` (which registers every arming establishes). An entry-reachability rule
    implemented in two places is this project's most-repeated bug -- see test_walkers."""
    cached = info.get("_entry_reach")
    if cached is not None:
        return cached
    per_entry = []
    for (K, eg), loc in ents:
        seen, visited = set(), set()
        stack = [(K, {n: v for n, v in loc.items() if n in carried})]
        while stack:
            if len(visited) > 4000:                # a carried local inc'd in a loop can blow up the
                seen |= set(info["states"])         # (state, counters) space; fall back to permissive
                break                               # (all states reachable) rather than under-report
            u, counters = stack.pop()
            key = (u, tuple(sorted(counters.items())))
            if key in visited:
                continue
            visited.add(key)
            seen.add(u)
            for (g, w, gg, c, tr) in info["states"].get(u, ()):
                if not _ctr_ok(g, counters):
                    continue
                nc = _apply(counters, c)
                if tr[0] == "ADVANCE":
                    stack.append((u + 1, nc))
                elif tr[0] == "JUMP":
                    stack.append((tr[1], nc))
                elif tr[0] == "SETSTATE":
                    stack.append((tr[1] + 1, nc))
        per_entry.append((seen, eg, dict(loc)))
    info["_entry_reach"] = per_entry
    return per_entry


def state_musts(info, regs):
    """State -> {register: allowed values} that hold on EVERY path reaching it from an entry.

    A cutscene decides its outcome early and pays it off late. KQ6's minotaur fight branches at
    state 8 -- with the red scarf on the minotaur it charges into the wall and dies, without it you
    are gored -- and only the surviving path walks on to state 14, which sets the minotaur-defeated
    flag and arms the walk-out. We guard each state independently, so state 14's effects looked
    reachable regardless, and the catacombs never sealed.

    Forward dataflow over the machine's own transitions, intersecting where paths rejoin, so a
    constraint survives only if EVERY way of getting here established it. A register the machine
    WRITES on the way loses its constraint at that point -- the machine changed it, so what held
    before says nothing after."""
    out = {}
    ents = list(info.get("entries", ())) + list(info.get("init_entries", ()))
    work = []
    for (K, _eg) in ents:
        work.append((K, {}))
        out.setdefault(K, {})
    seen = 0
    while work and seen < 4000:
        seen += 1
        K, cur = work.pop()
        for (g, w, gg, c, tr) in info["states"].get(K, ()):
            nxt = dict(cur)
            for R in regs:
                v = required_values(g, R)
                if v:
                    nxt[R] = (nxt[R] & v) if R in nxt else set(v)
            for (gi, _val) in w:
                nxt.pop(gi, None)                  # the machine wrote it; prior facts expire
            if not tr:
                continue
            if tr[0] == "ADVANCE":
                dst = K + 1
            elif tr[0] == "JUMP":
                dst = tr[1]
            elif tr[0] == "SETSTATE":
                dst = tr[1] + 1
            else:
                continue
            if dst in out:
                merged = {R: out[dst][R] | nxt[R] for R in set(out[dst]) & set(nxt)}
                if merged == out[dst]:
                    continue                       # fixpoint on this edge
                out[dst] = merged
            else:
                out[dst] = nxt
            work.append((dst, out[dst]))
    return out


def entry_reqs(info, regs):
    """State K -> {register: allowed values} that EVERY entry reaching K establishes.

    The REGISTER twin of `entry_alts`, and deliberately the opposite composition. Items are a
    DISJUNCTION -- arm the machine any way you can, so holding one alternative suffices. A
    register requirement is a MUST: it may be carried onto the exit only if every way of arming
    the machine pins it, because a single unconstrained entry means the machine can be reached
    with the register at any value (the same soundness rule `_build_product` applies to ordered
    writes).

    Without this the exit edge inherited its entry's ITEM gates but silently dropped its FLAG
    gates -- so a cutscene armed only while a flag is clear (KQ6's sacred-water rm350->rm370,
    armed only when flag 174 is still 0) came out a free walk."""
    from compile import _ctr_holds
    reach = _entry_reach_walk_of(info)
    per = []
    for (seen, eg, loc) in reach:
        per.append((seen, loc,
                    {R: v for R, v in ((R, required_values(eg, R)) for R in regs) if v}))

    def _consistent(loc, guard):
        """Could an arming carrying `loc` have produced a path guarded by `guard`?

        One machine can serve several exits, chosen by the `register` its arming passed --
        KQ6's `walkOut` leaves to the surface when armed with 1 (behind the minotaur flag) and
        back into the maze when armed with 0. Both armings reach the same STATE, so a per-state
        answer intersects them to nothing and the gated escape reads as free. The exit's own
        guard says which arming it belongs to, so honour it."""
        for a in (guard or ()):
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in loc \
                    and not _ctr_holds(a, loc):
                return False
        return True

    def reqs_for(K, guard=None):
        ds = [d for (seen, loc, d) in per if K in seen and _consistent(loc, guard)]
        if not ds:
            return {}
        common = {R: set().union(*(d[R] for d in ds))
                  for R in set(ds[0]).intersection(*(set(d) for d in ds))}
        return common
    out = {K: reqs_for(K) for K in info["states"]}
    out = {K: v for K, v in out.items() if v}
    out["_by_guard"] = reqs_for
    return out


def _entry_reach_walk_of(info):
    """`entry_alts` populates the cache; call it if nothing has yet."""
    if info.get("_entry_reach") is None:
        entry_alts(info)
    return info.get("_entry_reach") or []


def blocked(alts, banned):
    """Is an edge with these DNF alternatives blocked when `banned` items are unavailable?"""
    return bool(alts) and all(a & banned for a in alts)


def edge_meta(em, regs):
    """(a,b) -> [(req, sets, alts)] for the discovered gating `regs`.

    req  = {reg: {allowed values}}   what the edge's guard demands -- see guard_reqs
    sets = {reg: value}              writes the edge performs on the way out
    alts = DNF tuple of item-sets    (see entry_alts / blocked)

    This is what makes movement GATE-AWARE. The guard-ignoring graph walks rm82 -> rm152 -> rm52
    and so welds the volcano to the airport (the mega-SCC that hid the Pamphlet stranding and
    produced the Airline_Ticket FP). But rm82 dumps you into rm152 having set gCurrentStatus to
    14/15 (bomb botched) while rm152's exit to rm52 REQUIRES 7 -- an impossible composition."""
    regset = set(regs)
    # The previous-room register's COMPLETE domain: every room an edge leaves from, plus the 0 it
    # starts at. Complete by construction -- the writes below are the only ones -- which is what
    # lets `guard_reqs` read `(!= prev 670)` exactly instead of dropping it.
    pdom = {r for e in em.ts.edges for r in (e.src,)} | \
           {r for e in em.ts.cs_edges for r in (e.src,)} | \
           {i["room"] for i in em.machines} | {0}
    dom = {prev_room_reg(em): pdom} if prev_room_reg(em) in regset else {}

    def reqs(guard):
        return guard_reqs(guard, regset, dom)
    # THE PREVIOUS-ROOM WRITE. `(= <prev> <current>)` in the Game loop's room switch runs on every
    # transition, so every edge a->b carries `prev := a`. Modelled here rather than as a room write
    # because it is a property of the EDGE, and that is the whole point of it: a room whose exit
    # asks where you came from is a router, not a hub. KQ6's rm155 is the flight to the Realm of
    # the Dead -- `(if (== global12 340) (newRoom 600) else (newRoom 200))` -- and with prev
    # unwritten both branches read as free, which welded the realm to the rest of the world in
    # both directions. rm680's only way out asks the same question (`global12 != 670`, i.e. you
    # came back from rm690 having held up the mirror), so "solve the level or stay" is spelled in
    # this one register too.
    prev = prev_room_reg(em) if prev_room_reg(em) in regset else None
    def sets_of(src, base=None):
        s = dict(base) if base else {}
        if prev is not None:
            s[prev] = src
        return s
    meta = defaultdict(list)
    for e in em.ts.edges:
        meta[(e.src, e.dst)].append(
            (reqs(e.guard), sets_of(e.src), (frozenset(_own_positive(e.guard)),)))
    md = em.machine_delivered
    # A cs_edge whose (room, dst) a machine delivers is the SAME `newRoom` statement the machine
    # EXIT carries -- the cutscene walk knows the machine's gate, the flat edge knows the room's
    # path condition to the statement. Keeping both as separate rows makes the flat one a free
    # bypass of the gate (rm57 -> rm58 must hand the ticket to the agent), which is why it is
    # suppressed. But suppressing DROPPED its path condition, and a machine EXIT is not
    # automatically the stronger of the two: KQ6's realm of the dead is entered by a cutscene
    # armed under `flag14 and flag4 and not flag15`, the machine kept none of that, and the
    # one-visit seal on the whole region vanished at this line.
    #
    # So the two are COMPOSED instead: same statement, both conditions hold. Matched by the object
    # that emitted them (`via` == the machine's instance), because a room can deliver one (a,b) from
    # several instances and only the matching one is the same statement -- 105 of KQ6's 108
    # suppressed edges match, and the three that do not are left dropped rather than guessed.
    # Composed with the NECESSARY reading of both (structural_reqs / _own_required), not the flat
    # one: this guard is about to be ANDed into another, and a flat read turns "either of two
    # armings" into "both". That distinction is the whole of KQ4's whale -- see structural_reqs.
    suppressed = defaultdict(list)
    for e in em.ts.cs_edges:
        if (e.src, e.dst) in md:
            suppressed[(e.src, e.dst, e.via)].append(
                (structural_reqs(e.guard, regset, dom), frozenset(_own_required(e.guard))))
            continue
        meta[(e.src, e.dst)].append(
            (reqs(e.guard), sets_of(e.src), (frozenset(_own_positive(e.guard)),)))

    def _merged(key):
        """The conditions EVERY suppressed statement of this (room, dst, instance) demanded.

        Several statements are ALTERNATIVE ways to make the same move, so a register survives only
        if all of them constrain it, and then its allowed values are the union -- the same merge
        `chain` does over a machine's armers below."""
        rows = suppressed.get(key)
        if not rows:
            return {}, frozenset()
        rq, own = None, None
        for (r, o) in rows:
            rq = dict(r) if rq is None else {R: rq[R] | r[R] for R in set(rq) & set(r)}
            own = o if own is None else (own & o)
        return rq, own
    # Per-machine "what held on every path to this state", keyed so a machine armed by ANOTHER
    # can inherit the armer's facts at the arming state. Cutscene chains hand off mid-sequence:
    # KQ6's `freeCeleste` walks you out of the catacombs and is armed at state 14 of
    # `minotaurCharging`, whose state 8 is where the red scarf decided you survived at all.
    _musts = {}
    for _i in em.machines:
        key = (_i.get("script"), _i.get("inst"), _i.get("room"))
        _musts[key] = state_musts(_i, regs)
    for info in em.machines:
        eo = entry_alts(info)
        er = entry_reqs(info, regs)
        sm = state_musts(info, regs)
        # What EVERY arming of this machine had already established.
        chain = None
        for armer in info.get("entry_armers", ()) or ():
            got = _musts.get((info.get("script"), armer[0], info.get("room")), {}).get(armer[1], {}) \
                if armer else {}
            chain = dict(got) if chain is None else \
                {R: chain[R] | got[R] for R in set(chain) & set(got)}
        chain = chain or {}
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    exit_own = frozenset(_own_positive(g))
                    alts = eo.get(K) or (frozenset(),)
                    sets = sets_of(info["room"],
                                   {gi: v for (gi, v) in w if gi in regset})
                    # The exit inherits its ENTRY's register requirements as well as its item
                    # ones. Both must hold, so a register constrained in both places INTERSECTS.
                    rq = reqs(g)
                    # Ask for THIS exit's entries, not the state's: a machine serving two exits
                    # via `register` reaches one state from both armings, and only the exit guard
                    # says which arming it belongs to.
                    by_guard = er.get("_by_guard")
                    inherited = by_guard(K, g) if by_guard else er.get(K, {})
                    # ...whatever every path THROUGH the machine to this state established, and
                    # the path condition of the flat edge this EXIT suppressed (see `suppressed`).
                    supp_rq, supp_own = _merged((info["room"], tr[1], info.get("inst")))
                    for R, vals in (list(sm.get(K, {}).items()) + list(chain.items())
                                    + list(inherited.items()) + list(supp_rq.items())):
                        rq[R] = (rq[R] & vals) if R in rq else set(vals)
                    meta[(info["room"], tr[1])].append(
                        (rq, sets, tuple(exit_own | supp_own | a for a in alts)))
    return meta


class IrSccReach(SccReach):
    """SccReach fed from the JSON-IR model instead of model.Game (same algorithm)."""
    def __init__(self, em):
        self.em = em
        self.g = _ItemNames(vocab.item_names(em.ir))
        (self.edges, self.edge_kind, self.sources, self.drops, self.required,
         self.guard_required) = build_maps(em)
        self.rooms = list(em.rooms)
        self.comps, self.comp_of = tarjan_scc(self.rooms, self.edges)
        self.cedges = defaultdict(set)
        for a, bs in self.edges.items():
            for b in bs:
                if a in self.comp_of and b in self.comp_of and self.comp_of[a] != self.comp_of[b]:
                    self.cedges[self.comp_of[a]].add(self.comp_of[b])
        self.creach = {c: reachable(self.cedges, {c}) for c in range(len(self.comps))}
        self.items_in_comp = defaultdict(set)
        for it, srcs in self.sources.items():
            for r in srcs:
                if r in self.comp_of:
                    self.items_in_comp[self.comp_of[r]].add(it)
        self.reach_rooms = reachable(self.edges, {em.cfg.start_room})
        self.members, self.room_region, self.controllers = {}, {}, set()   # no regions in IR
        self.goal_comps = {self.comp_of[r] for r in em.cfg.goal_rooms if r in self.comp_of}
        self._reob, self._rw, self._after = {}, {}, {}
        self._build_product()

    # ---- gate-aware movement ------------------------------------------------
    def _build_product(self):
        """Build one PROJECTION per discovered gating register -- the gate-aware movement model.

        Not one joint product. Promoting all 19 of LSL2's gating registers jointly explodes past
        4,000,000 reachable states (the flags are near-independent, so they multiply); the same 19
        as separate projections cost 3,679 states total. Precision is monotone and soundness is
        preserved: a genuinely walkable path is walkable in EVERY projection, so intersecting the
        answers can only remove spurious movement, never invent it. Adding a register can only
        sharpen the result, which is why we promote every register that qualifies rather than
        judging which ones matter.

        In-room register changes (handler writes, non-exit machine writes) are added UNGUARDED, so
        each projection stays permissive and can only remove movement the guards actually forbid."""
        em = self.em
        self.regs = gating_registers(em)
        self._emeta = edge_meta(em, self.regs)
        self._inroom = {R: defaultdict(set) for R in self.regs}
        # OWN requirements on each in-room write. The writes themselves stay PERMISSIVE for
        # registers (see below), but a write you can only perform by USING an item is not
        # available when that item is banned: KQ6 sets `scarfOnMino` from `doVerb 72`, i.e. only
        # if you hold the red scarf, and that single write is what eventually opens every exit
        # from the catacombs. Ignoring it made the scarf look re-obtainable from inside the very
        # trap that needs it.
        self._inroom_own = {}
        regset = set(self.regs)
        dbg = frozenset(em.cfg.debug_globals)
        for room, script, gi, v, g in em.handler_writes:
            # A debug-gated write is not real availability -- the same reason `build_maps` skips
            # debug-gated ACQUISITIONS (rm82's `if gDebugging` hands over the whole bomb). Applied
            # here it also restores single-writer structure: KQ4's `Said 'enter/night'` cheat sets
            # global109 := 3 from Main, which is the only thing stopping Lolotte's task counter
            # from having exactly one writer -- see register monotonicity below.
            # LSL2 has 62 debug-gated writes and NONE touches a gating register, so this cannot
            # move it; KQ4 has 12 across 8 registers, among them global100 (night) and global109.
            if gi in regset and not _debug_gated_guard(g, dbg):
                self._inroom[gi][room].add(v)
                self._inroom_own[(gi, room, v)] = frozenset(_own_positive(g))
        # MACHINE writes, with the machine's own entry guard on the SAME register kept as an
        # ordering. KQ4 dispatches Lolotte's conversations with `(switch global109 (1 lotTalk3)
        # (2 lotTalk4) (3 lotTalk5))`, and each writes the next value -- so lotTalk4 is a
        # transition 2 -> 3, not "3 becomes available". Collapsing it to a free value is what let
        # the model walk back from task 3 to task 1 and made every flip look reversible.
        #
        # But this ordering is only sound when EVERY entry establishes the from-value. If any entry
        # leaves R unconstrained, the machine can be entered with R at any value, so a write reached
        # from that entry is a transition FROM anything -- pinning it to the OTHER entries' values
        # deletes real movement. KQ4's uniActions writes global123:=1 from its arrow-taming entry
        # (which constrains nothing on 123) yet also has a bit-placement entry needing 123==1;
        # unioning to {1} lost the 0->1 step, so global123 never reached 2, the unicorn-ride room
        # (entered at 123==2) vanished from the projection, and reobtainability read that absence as
        # a seal -- fabricating a 32-item "carry your whole inventory" guard. When the entries
        # DISAGREE (some constrain R, some do not), we cannot pin the from-value, so we honour the
        # permissive default above and leave the write unguarded. This is a no-op for the Lolotte
        # counter (lotTalk3/4/5 each have a single 109-constraining entry, so they still order).
        # ROOM-ENTRY writes. `init` runs on arrival, so a register it sets really does change in
        # that room -- but init writes were collected separately (for the atomic-arrival ordering)
        # and never reached the projections, so a flag raised ONLY on arrival looked never-written
        # and did not even qualify as a gating register. KQ6 seals the realm of the dead exactly
        # that way: rm600's init sets flag 15, nothing clears it, and the entry needs it clear.
        for room, vs in getattr(em, "init_writes", {}).items():
            for gi, v in vs.items():
                if gi in regset:
                    self._inroom[gi][room].add(v)
                    self._inroom_own.setdefault((gi, room, v), frozenset())
        self._rstep = {R: defaultdict(set) for R in self.regs}
        for info in em.machines:
            entries = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            gates = {}
            for R in self.regs:
                rvs = [required_values(eg, R) for _, eg in entries]
                if rvs and all(rv for rv in rvs):        # every entry pins R -> ordering is sound
                    gates[R] = set().union(*rvs)
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi not in regset:
                            continue
                        need = gates.get(gi)
                        if need:
                            for frm in need:
                                self._rstep[gi][info["room"]].add((frm, v))
                        else:
                            self._inroom[gi][info["room"]].add(v)
                            self._inroom_own[(gi, info["room"], v)] = frozenset(_own_positive(g))
        self._own_fixpoint()
        self._pstates = {R: self._walk(R, frozenset()) for R in self.regs}

    def _reg_cost(self, R, vals):
        """Items you must hold to make register R take any of `vals` -- the cheapest route."""
        best = None
        for v in sorted(vals):
            if v == 0:
                return frozenset()               # registers start at 0
            ways = [own for k, own in self._inroom_own.items() if k[0] == R and k[2] == v]
            if not ways:
                return frozenset()               # nothing writes it -> initial value -> free
            cost = ways[0]
            for w in ways[1:]:
                cost &= w
            best = cost if best is None else (best & cost)
        return best or frozenset()

    def _reg_unreachable(self, req, banned):
        """Is some register requirement on this edge impossible while `banned` items are held back?

        Projections are per-register, so an edge with two ways through -- KQ6's lair exit opens
        once the minotaur is dead OR once the victory cutscene has run, testing two DIFFERENT
        registers -- looks free in BOTH projections: each sees its own register unconstrained on
        the other alternative and lets it by. Item bans are global, so ask the question here
        instead, where every register on the edge is visible at once.

        Deliberately NOT folded into the edge's item set. `alts` means "items you must be HOLDING
        to cross", while a register's cost is "items you needed EARLIER" -- conflating them made
        LSL2 demand you still carry the Vine long after spending it."""
        if not banned:
            return False
        return any(self._reg_cost(R, vals) & banned for R, vals in req.items())

    def _own_fixpoint(self):
        """Let item requirements flow ALONG register chains.

        A write is often gated not on an item but on another register, and that register only
        became what it is because you used an item. KQ6's catacombs are the case: showing the
        minotaur the red scarf sets `scarfOnMino`, the path that guards opens the state that sets
        "minotaur defeated", and THAT is what every exit tests. Each link we already had; the chain
        we did not, because projections are built one per REGISTER (a joint product over LSL2's 19
        explodes past 4,000,000 states, while the projections cost 3,679) so `scarfOnMino` and
        "minotaur defeated" never meet.

        So propagate instead of joining: if a write is guarded by `S == v`, it inherits whatever
        every way of making S equal v requires. Repeated to a fixpoint, that carries an item
        requirement as far along the chain as the chain goes, and projections stay independent.

        Both compositions are the conservative one. A register value costs the INTERSECTION over
        the writes that produce it -- you may use whichever is cheapest -- and a value that no
        write produces is free, because it is the value the register starts at."""
        # (R, room, val) -> {other register: allowed values} the write depends on. For a machine
        # write that means the path guard AND everything every route to that state established --
        # a cutscene decides early and pays off late, so the constraint that matters is usually in
        # an earlier state (KQ6 branches on the scarf at state 8 and sets the flag at 14).
        regs = set(self.regs)
        guards = {}
        for room, script, gi, v, g in self.em.handler_writes:
            if gi in regs:
                d = {S: vs for S in self.regs if (vs := required_values(g, S))}
                if d:
                    guards[(gi, room, v)] = d
        for info in self.em.machines:
            sm = state_musts(info, self.regs)
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi not in regs or (gi, info["room"], v) not in self._inroom_own:
                            continue
                        d = dict(sm.get(K, {}))
                        for S in self.regs:
                            vs = required_values(g, S)
                            if vs:
                                d[S] = (d[S] & vs) if S in d else set(vs)
                        if d:
                            guards[(gi, info["room"], v)] = d

        def value_cost(R, val, own):
            """Items needed to make R == val: the cheapest write, or free if none writes it."""
            if val == 0:
                return frozenset()        # registers start at 0; no action needed
            ways = [own.get(k, frozenset()) for k in own if k[0] == R and k[2] == val]
            if not ways:
                return frozenset()        # nothing writes it -> initial value -> free
            out = ways[0]
            for w in ways[1:]:
                out &= w
            return out

        own = dict(self._inroom_own)
        for _round in range(6):           # chains in practice are 2-3 links; bound the walk
            changed = False
            for key, deps in guards.items():
                extra = set(own.get(key, frozenset()))
                for S, vals in deps.items():
                    if S == key[0] or not vals:
                        continue          # a write ordering itself is _rstep's business
                    # reaching ANY allowed value suffices, so take the cheapest
                    costs = [value_cost(S, v, own) for v in sorted(vals)]
                    need = costs[0]
                    for c in costs[1:]:
                        need &= c
                    extra |= need
                if frozenset(extra) != own.get(key, frozenset()):
                    own[key] = frozenset(extra)
                    changed = True
            if not changed:
                break
        self._inroom_own = own

    _FREE = ({}, {}, (frozenset(),))

    def _psucc(self, R, node, banned):
        """Successors of a (room, value-of-R) node in projection R. `banned` is a set of items you
        do not hold, so edges needing them are false -- the ITEM dimension of gate-awareness, and
        what the old `_sealed` heuristic crudely approximated: you cannot use the parachute to
        walk back to the parachute."""
        r, st = node
        out = {(r, v) for v in self._inroom[R].get(r, ())
               if not (banned and self._inroom_own.get((R, r, v), frozenset()) & banned)}
        # ...plus writes the game only makes FROM a particular value of R -- see _build_product
        out |= {(r, to) for (frm, to) in self._rstep[R].get(r, ()) if frm == st}
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                need = req.get(R)
                if need is not None and st not in need:
                    continue                      # guard forbids this move at this value of R
                if banned and blocked(alts, banned):
                    continue                      # every way through needs a banned item
                if self._reg_unreachable(req, banned):
                    continue                      # a register it needs can never reach that value
                out.add((b, sets.get(R, st)))
        return out

    def _walk(self, R, banned, starts=None):
        """Forward reachable (room, value) states in projection R."""
        seen = set(starts) if starts else {(self.em.cfg.start_room, 0)}
        q = list(seen)
        while q:
            u = q.pop()
            for v in self._psucc(R, u, banned):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen

    def _reach_without(self, item):
        """Rooms reachable from the start WITHOUT ever holding `item` (gate-aware forward walk),
        intersected over every projection. `item` may be one item or a frozenset (a group).

        A room whose own(item) guard can only be reached BY holding item isn't a stranding site
        at all -- you can never stand there lacking it. rm61 tests own(Airline_Ticket) but every
        route in already spends the ticket, which is why the ticket looked missable."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._rw:
            return self._rw[ban]
        out = None
        for R in self.regs:
            rooms = {r for r, _ in self._walk(R, ban)}
            out = rooms if out is None else (out & rooms)
        self._rw[ban] = out if out is not None else set(self.reach_rooms)
        return self._rw[ban]

    def _need_rooms(self, item):
        """Rooms where own(item) is actually FACED -- gate-aware. See _reach_without."""
        return {R for R in super()._need_rooms(item) if R in self._reach_without(item)}

    def reobtainable_rooms(self, item):
        """Rooms from which `item` can still be ACQUIRED -- GATE-AWARE, intersected over every
        projection.

        Backward walk in each (room, register) projection instead of the guard-ignoring room
        graph. This replaces the `_sealed` one-way-edge heuristic: a pocket is sealed when the
        guards actually seal it, which is derived rather than assumed."""
        ban = item if isinstance(item, frozenset) else frozenset({item})
        if ban in self._reob:
            return self._reob[ban]
        srcs = set()
        for it in ban:
            srcs |= self.sources.get(it, set())
        if not srcs:
            self._reob[ban] = set()
            return self._reob[ban]
        out = None
        for R in self.regs:
            states = self._pstates[R]
            prev = defaultdict(set)               # reverse edges, minus own(item)-gated ones
            for u in states:
                for v in self._psucc(R, u, ban):
                    if v in states:
                        prev[v].add(u)
            back = {p for p in states if p[0] in srcs}
            q = deque(back)
            while q:
                u = q.popleft()
                for w in prev.get(u, ()):
                    if w not in back:
                        back.add(w)
                        q.append(w)
            rooms = {r for r, _ in back}
            out = rooms if out is None else (out & rooms)
        self._reob[ban] = out if out is not None else set()
        return self._reob[ban]

    def _freely_reversible(self, a, b):
        """Gate-aware override: b->a is a FREE walk only if some DNF alternative on it needs no
        item. An item-gated return -- the whale sneeze rm44->rm31 needs the Peacock Feather
        (alts={8}) -- is not free, so the forward swallow rm31->rm44 stays a one-way commit and the
        feather it demands is correctly stranded. Register gates are left alone here: the stranding
        test bans ITEMS, so an item-free-but-flag-gated return is still a walk you can make."""
        if a not in self.edges.get(b, set()):
            return False
        metas = self._emeta.get((b, a))
        if not metas:
            return True                          # return edge exists but carries no gate -> free
        # A register gate whose VALUE costs an item is not a free walk either. The docstring's
        # "flag-gated returns are still walkable" holds only while the flag is free to set: KQ6's
        # way back out of the catacombs tests "minotaur defeated", and the only thing that sets it
        # is showing him the red scarf, so the walk back is not free to someone who never had one.
        return any((not alts or any(not alt for alt in alts))
                   and not any(self._reg_cost(R, vals) for R, vals in req.items())
                   for (req, sets, alts) in metas)

    def rooms_after(self, b):
        """Rooms still reachable after crossing into `b` -- GATE-AWARE, intersected over
        projections. The condensation default counts the whole mega-SCC, which is what made
        rm52/rm57 look reachable from rm58 and inflated the boarding guard."""
        if b in self._after:
            return self._after[b]
        out = None
        for R in self.regs:
            starts = {p for p in self._pstates[R] if p[0] == b}
            if not starts:
                continue
            rooms = {r for r, _ in self._walk(R, frozenset(), starts)}
            out = rooms if out is None else (out & rooms)
        self._after[b] = out if out is not None else {b}
        return self._after[b]

    def goal_rooms_set(self):
        return {r for r in self.em.cfg.goal_rooms if r in self.comp_of}

    def _clause_key(self, room, guard):
        """Correlate effects belonging to the SAME source clause. Guard TEXT cannot be used --
        sibling branches of one `cond` share most conjuncts but differ (the rm82 bomb clause and
        its machine entry differ only in a counter term) -- so key on the room plus the clause's
        positive item preconditions, which a clause and the state it arms necessarily share."""
        return (room, frozenset(_own_positive(guard)))

    def _armed_wrote(self):
        """(armed clause-keys, wrote-map): the clauses that DO something -- arm a machine state,
        get an item, or write a register. Cached; the shared core of the arms-nothing test."""
        if getattr(self, "_aw", None) is None:
            armed, wrote = set(), defaultdict(list)
            for info in self.em.machines:
                for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                    armed.add(self._clause_key(info["room"], eg))
            for room, script, gi, v, g in self.em.handler_writes:
                wrote[self._clause_key(room, g)].append(gi)
            for room, script, it, g in self.em.handler_gets:
                armed.add(self._clause_key(room, g))
            self._aw = (armed, wrote)
        return self._aw

    def _clause_productive(self, room, guard):
        """Does the clause at (room, guard) ARM something -- a machine state, a get, or a gating
        register? The per-CLAUSE version of `real_uses` (which is per-room and too coarse: it calls
        the Lolotte shot wasteful and the shovel break productive). Tells a wasteful resource drain
        (KQ4's shoot-into-the-air) from a productive one (taming the unicorn, killing Lolotte)."""
        armed, wrote = self._armed_wrote()
        k = self._clause_key(room, guard)
        return k in armed or any(gi in set(self.regs) for gi in wrote.get(k, ()))

    def pure_sinks(self):
        """Consumptions that ACCOMPLISH NOTHING: a handler clause that removes an item from
        inventory while arming no machine state and writing no register any guard reads.

        Adventure games are full of these (drop it, eat it, throw it) and most are harmless, so
        this is a candidate set, not a finding -- see dangerous_sinks."""
        armed, wrote = set(), defaultdict(list)
        for info in self.em.machines:
            for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                armed.add(self._clause_key(info["room"], eg))
        for room, script, gi, v, g in self.em.handler_writes:
            wrote[self._clause_key(room, g)].append(gi)
        for room, script, it, g in self.em.handler_gets:
            armed.add(self._clause_key(room, g))
        gate = set(self.regs)
        out = []
        for room, script, it, g, dest in self.em.handler_drops:
            if script in self.GLOBAL_SCRIPTS:
                # Clause identity is (room, positive-owns), which pins a clause inside a small
                # room but COLLIDES badly in Main -- one giant script where unrelated clauses
                # share an own-set, so a real use elsewhere in Main masks a sink here. We cannot
                # attribute reliably, so assume the worst and let the danger test decide. That is
                # the over-require direction, and it is how "open parachute" (Main destroys the
                # chute needed for the rm63 jump) surfaced at all.
                out.append({"room": room, "script": script, "item": it, "dest": dest})
                continue
            k = self._clause_key(room, g)
            if k in armed or any(gi in gate for gi in wrote.get(k, ())):
                continue                          # the clause DOES something -> a real use
            out.append({"room": room, "script": script, "item": it, "dest": dest})
        return out

    def real_uses(self):
        """item -> rooms where holding it ARMS something -- the uses `dangerous_sinks` weighs a
        consumption against: a machine state armed by own(item), and a GATING REGISTER written from
        a handler guarded by own(item). Wearing the parachute at rm63 is the second -- it sets
        global142, arming no machine state -- so destroying the chute elsewhere looked harmless
        until this counted it.

        NOT `guard_required` (the broader "the game TESTS has: X"). This split -- sinks weigh
        against `real_uses`, `resource_exhaustion` weighs against `guard_required` -- is what makes
        LSL2's `dangerous_sinks` reproduce the v1.0-lsl2 tag EXACTLY (Matches / Hair_Rejuvenator /
        Parachute / Airsick_Bag; NOT the Grotesque_Gulp, which is drunk to death, NOR the Fruit).

        THAT TAG BEHAVIOUR IS A CORRECT ORACLE, frozen in test_golden.py. It was broken once by a
        later commit folding guard_required in here, and I nearly broke it again "fixing the smell"
        of the split. So: the split is load-bearing, not a mistake to derive away. Do NOT change it
        (or anything that moves LSL2's golden) without re-running test_golden AND checking with the
        user first -- the tag is the oracle, not something to re-litigate."""
        out = defaultdict(set)
        for info in self.em.machines:
            for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                for it in _own_positive(eg):
                    out[it].add(info["room"])
        gate = set(self.regs)
        for room, script, gi, v, g in self.em.handler_writes:
            if gi in gate:
                for it in _own_positive(g):
                    out[it].add(room)
        return out

    def _loc_required(self, guard, item, room=None):
        """Does this guard REQUIRE item `item`'s object to still be lying in THIS room?

        `room` is where the guard was found. LSL2 writes the test as `ownedBy: gCurRoomNum`, which
        says "here" without naming a room; KQ4 names it -- `ownedBy: 78` inside Room78. Both mean
        the same thing, and only the caller knows which room it is in, which is why the atom keeps
        the literal instead of collapsing it at extraction time."""
        found = []
        def walk(g, pol):
            if isinstance(g, list):
                for x in g:
                    walk(x, pol)
            elif isinstance(g, Pred):
                if (g.kind == "LOC" and g.var == item and pol
                        and (g.value == "room" or (room is not None and g.value == room))):
                    found.append(True)
            elif isinstance(g, (GAnd, GOr)):
                for k in g.kids:
                    walk(k, pol)
            elif isinstance(g, GNot):
                walk(g.kid, not pol)
        walk(guard, True)
        return bool(found)

    def destroyed_is_permanent(self, item):
        """Once destroyed with `put: X -1`, is `item` gone for good?

        True when EVERY acquisition demands the object still be lying in the world
        (`(gInv at: X) ownedBy: gCurRoomNum`). `put: X -1` sets the owner to -1 -- NOWHERE, not a
        room -- so that test can never hold again. This is the one-time-pickup idiom, and it is
        why barfing into the Airsick_Bag costs you the game at rm82 even though rm62 is still
        walkable. Note it does NOT make the item unobtainable for someone who simply never took
        it, so it is deliberately scoped to DESTRUCTION and leaves the stranding sweep alone."""
        guards = [(a.guard, a.room) for a in self.em.ts.acqs if a.item == item]
        guards += [(g, room) for room, script, it, g in self.em.handler_gets if it == item]
        dbg = frozenset(self.em.cfg.debug_globals)
        guards = [(g, r) for (g, r) in guards if not _debug_gated_guard(g, dbg)]
        return bool(guards) and all(self._loc_required(g, item, r) for (g, r) in guards)

    def _groups(self):
        return {frozenset(g) for gs in self.disjunctive_groups().values() for g in gs}

    GLOBAL_SCRIPTS = frozenset({0})   # Main: its handleEvent runs in EVERY room

    def _sink_rooms(self, sk):
        """Rooms a consumption can actually happen in.

        Normally the room it was found in. But Main (script 0) handles events in every room, so a
        `put: X -1` there is reachable from anywhere -- and being attributed to pseudo-room 0, which
        has no outgoing edges, it could never satisfy the "still needed downstream" test and was
        silently skipped. That is how four generic destroy-the-item verbs in Main went unnoticed
        until someone played the game and poured the rejuvenator out on an arbitrary screen."""
        if sk["script"] in self.GLOBAL_SCRIPTS:
            return sorted(r for r in self.reach_rooms if r in self.rooms and r != 0)
        return [sk["room"]]

    def dangerous_sinks(self):
        """Pure sinks that COST you the game: the item is still needed somewhere you can still
        reach, and once wasted it cannot be re-obtained. The action-shaped sibling of a room-gate
        stranding -- nothing about it is a movement edge, so `edge_strandings` cannot see it.

        LSL2: rm63 `apply rejuvenator to bolt` (-5 points, and the bolt does NOT open) and rm81
        `drop rejuvenator` (-5) both destroy the bomb ingredient rm82 needs."""
        uses = self.real_uses()
        out = []
        for sk in self.pure_sinks():
            it = sk["item"]
            for room in self._sink_rooms(sk):
                ahead = (uses.get(it, set()) - {room}) & self.rooms_after(room)
                if not ahead:
                    continue
                # a one-time pickup destroyed here is gone regardless of which rooms stay walkable
                if not self.destroyed_is_permanent(it) and room in self.reobtainable_rooms(it):
                    continue
                # ...but a DISJUNCTIVE alternative rescues you: throwing the Ashes away is
                # survivable while the Sand is still gettable, since rm81 accepts either.
                if any(it in G and any(room in self.reobtainable_rooms(o) for o in G - {it})
                       for G in self._groups()):
                    continue
                out.append({**sk, "at_room": room, "still_needed_at": sorted(ahead)})
                break          # one witness room is enough to condemn the site
        return out

    def register_strandings(self):
        """Softlocks caused by a REGISTER flipping, not by walking through a one-way door.

        The second class in the taxonomy, and one `edge_strandings` structurally cannot see: it
        reasons about crossing an edge, and here nothing is crossed. A plot flag advances -- you
        finish Lolotte's first errand, the sun goes down -- and a region that was open closes
        behind you while something you still need is inside it.

        Same shape as an edge stranding otherwise, so the same three conjuncts:
          1. the flip is a POINT OF NO RETURN: from every state at the new value, no state at any
             other value is reachable. (Nightfall in KQ4 is NOT one -- Room82 brings the dawn --
             which is why it correctly reports nothing.)
          2. the goal is still reachable afterwards, or this is a dead end rather than a softlock;
          3. every source of the item is outside the post-flip region, and a use is inside it.

        Runs on the projections `_build_product` already made, so it costs a walk per (register,
        value) and no new model."""
        out = []
        goal = self.goal_rooms_set()
        for R in self.regs:
            states = self._pstates[R]
            vals = {v for (_r, v) in states}
            if len(vals) < 2:
                continue
            for w in sorted(vals):
                # Seed where the flip ITSELF can happen -- rooms that write w, and edges that set
                # it on the way out -- not every room already seen at w. Seeding a room with its
                # own post-flip state is how a first attempt at this "proved" that KQ4's start
                # room was sealed by nightfall.
                seeds = {(r, w) for r, vs in self._inroom[R].items() if w in vs}
                for (_a, b), metas in self._emeta.items():
                    for (_req, sets, _alts) in metas:
                        if sets.get(R) == w:
                            seeds.add((b, w))
                seeds &= states
                if not seeds:
                    continue
                after = self._walk(R, frozenset(), starts=seeds)
                # NOTE there is deliberately no separate "is this irreversible" test. An earlier
                # version required that no state at another value be reachable, which rejects
                # every plot counter -- moving FORWARD is not getting back out. `after` already
                # includes whatever the register does next, so if a source is still reachable the
                # flip stranded nothing, and if it is not, the flip stranded it. The source test
                # below IS the irreversibility test.
                rooms_after = {r for (r, _v) in after}
                if goal and not (goal & rooms_after):
                    continue                        # already unwinnable: a dead end, not a softlock
                for it in sorted(self.required):
                    srcs = self.sources.get(it, set())
                    if not srcs or (srcs & rooms_after):
                        continue                    # obtainable after the flip, or never obtainable
                    ahead = self.required[it] & rooms_after
                    if ahead:
                        out.append({"pattern": "register-flip-point-of-no-return",
                                    "register": R, "value": w, "item": it,
                                    "item_name": self.g.item_name(it),
                                    "source_rooms": sorted(srcs),
                                    "still_needed_at": sorted(ahead)})
        return out

    def resource_exhaustion(self):
        """Items you USE UP rather than throw away -- the fourth store's softlock shape.

        `dangerous_sinks` asks for a PURE sink: a clause that wastes the item and does nothing
        else, like pouring the rejuvenator on a bolt. Breaking the shovel is not that. It happens
        inside a perfectly legitimate dig, so the clause plainly does something, and the purity
        test rejects it -- correctly, for what that test is for.

        The shape here is different: a finite item, degraded ONE-WAY by ordinary use, and still
        required somewhere else. KQ4's shovel snaps after five holes (`Room16:589`,
        `(if (>= global113 5) ((Inv at: 15) loop: 1))`), and it is needed in BOTH the graveyard
        and the crypt -- and global113 is a global, so holes dug in one count against the other.
        Cupid's bow is the same shape with a counter instead of a flag.

        Conjuncts, deliberately the same three `dangerous_sinks` uses, minus purity:
          1. the degradation is one-way (decided upstream, by the discovered value set);
          2. the item is still needed somewhere reachable from the degradation site;
          3. that somewhere is not the site itself -- using it where it is needed is the point.
        """
        spec = _IPROP_SPEC
        oneway = {it for (it, _p), sp in spec.items()
                  if sp.get("counter") or len(sp.get("values", ())) == 1}
        # "still NEEDED" here means the game tests `has: X` at a room the player can still reach --
        # `guard_required` is exactly that, and it is the RIGHT notion for a degraded item (the bow
        # is needed at Lolotte rm82 because rm82 tests has: bow). NOT `real_uses`, which is the
        # narrower "arms something" the SINK test wants; see real_uses on why the two differ.
        uses = self.guard_required
        out = []
        for room, it, prop, val, g, *_rest in getattr(self.em.ts, "item_prop_writes", ()):
            if it not in oneway:
                continue
            # ...and this particular write must BE the degradation. For a counter only the
            # increment degrades -- DebugMenu resets the bow's arrow count to 0, which is the
            # opposite. For a single-valued property the write of that value is the degradation.
            sp = spec.get((it, prop), {})
            if sp.get("counter"):
                if val != "inc":
                    continue
            elif val not in sp.get("values", ()):
                continue
            # room 0 is MAIN -- a scope, not a place. A degradation there can happen wherever the
            # player is standing, so widen it exactly as `_sink_rooms` does for global sinks.
            # KQ4's `Said 'launch'` lives in Main and spends an arrow through `ScriptID 305`, so
            # this is the difference between seeing the bow's real waste and seeing only its two
            # legitimate uses.
            sites = self._sink_rooms({"script": 0, "room": 0}) if room == 0 else [room]
            for site in sites:
                ahead = (uses.get(it, set()) - {site}) & self.rooms_after(site)
                if not ahead:
                    continue
                out.append({"pattern": "resource-exhaustion", "item": it,
                            "item_name": self.g.item_name(it), "property": prop,
                            "at_room": site, "global_scope": room == 0,
                            "still_needed_at": sorted(ahead)})
                if room == 0:
                    break        # one witness room is enough to condemn a global-scope site
        return self._collapse_roaming(out)

    def _roaming_regions(self):
        """`{region-script: frozenset(member rooms)}` for regions that ROAM -- whose script writes
        a global to two or more of its OWN member rooms. That global is the encounter's location
        register (KQ4's regUnicorn sets `global124` to 20/26/27), so the region's rooms are where
        ONE moving thing may appear, not distinct places. The graveyard and crypt (a fixed region)
        write no such register and are correctly NOT roaming, so the shovel -- needed in both -- is
        left as two findings."""
        out = {}
        for rgn, rooms in self.em.region_rooms.items():
            sc = self.em.ir.script(rgn)
            if sc is None:
                continue
            writes = defaultdict(set)
            bodies = [b for o in sc.objects for b in o.methods.values()] + list(sc.procs.values())
            for body in bodies:
                for n in I.walk(body):
                    if n.get("t") == "Assignment":
                        ks = n.get("kids") or []
                        if len(ks) >= 2 and I.is_global(ks[0]) and ks[1].get("t") == "Number":
                            writes[ks[0]["index"]].add(ks[1]["value"])
            if any(len(vals & rooms) >= 2 for vals in writes.values()):
                out[rgn] = frozenset(rooms)
        return out

    def _collapse_roaming(self, rows):
        """Collapse exhaustion rows for one item whose sites are all within a single ROAMING region
        into one finding -- the roaming encounter is one thing, not three. `still_needed_at` drops
        the region's own rooms (they are the same encounter). Non-roaming multi-room findings (the
        shovel across graveyard and crypt) and out-of-region sites (rm1 ANYWHERE, rm82 Lolotte) are
        untouched. See TODO A0n(2): the unicorn ROAMS, its rooms are one shot from three positions."""
        roam = self._roaming_regions()
        if not roam:
            return rows
        by_item = defaultdict(list)
        for r in rows:
            by_item[(r["item"], r["property"])].append(r)
        out = []
        for _key, group in by_item.items():
            used = set()
            for rgn, members in roam.items():
                inside = [r for r in group if r["at_room"] in members and id(r) not in used]
                if len(inside) < 2:
                    continue
                for r in inside:
                    used.add(id(r))
                sites = sorted({r["at_room"] for r in inside})
                need = sorted(set().union(*(set(r["still_needed_at"]) for r in inside)) - members)
                if not need:
                    # every use is INSIDE the one roaming encounter -- degrading the item where it
                    # is used is not a softlock. The per-site rows only looked like findings because
                    # a roaming region attributes the same encounter to each of its rooms, so each
                    # site is "still needed at" the OTHERS; once collapsed they cancel. Drop the
                    # whole group (rows stay consumed, nothing emitted) -- the same net judgement as
                    # `resource_exhaustion`'s `if not ahead: continue`, applied after the merge.
                    continue
                out.append({**inside[0], "at_room": sites[0], "at_rooms": sites,
                            "still_needed_at": need, "roaming_region": rgn})
            out.extend(r for r in group if id(r) not in used)
        return out

    def joint_strandings(self):
        """Softlocks only a JOINT projection can see: an item behind a gate whose two conditions
        live in DIFFERENT registers, so every single-register projection lets it through.

        KQ4's Golden Bridle is the case. It is on Genesta's island (rm43), reachable only through
        the whale, and the whale is one-time. Reaching the island needs BOTH "you arrived from the
        whale or the island" (the previous-room global) AND "the whale is unspent" (a monotone
        flag). The independent projections `_build_product` makes cannot express that conjunction:
        in the previous-room projection the whale edge is free, in the flag projection the island
        edge is free, so each says the island is still reachable and their intersection agrees. Only
        the two TOGETHER show the single window closing behind you.

        And it is a STATE-level property, not a room-level one: you CAN reach the unicorn before the
        whale (flag still 0, island still reachable), so `reobtainable_rooms` -- which collapses to
        rooms -- calls the island reobtainable and reports nothing. The softlock is that you can
        ALSO reach the unicorn AFTER the whale (flag 1) with no bridle and no way back. So the test
        is: is there a reachable joint state at a room where the item is required, from which no
        source of it is reachable, while the goal still is (so it is the ITEM that is missing, not a
        generic dead end)?

        Everything derived: the island's previous-room gate comes from `grid.analyze` (the ocean's
        virtual map summarised to an edge gate); the whale flag is the monotone register gating a
        previous-room the gate names. Runs only when a grid gate exists, so LSL2 (no grid) reports
        nothing and cannot be moved by it."""
        prev_global = self._prev_room_global()
        gates = grid.analyze(self.em, prev_global)
        if not gates:
            return []
        prev_universe = set().union(*(set().union(*ex.values()) for ex in gates.values()))

        # DERIVE the joint monotone flags: registers that gate an in-edge to a previous-room the
        # grid names, and that only ever advance (domain {0} or {0, v}, set by an entry write).
        def edge_eqs(guard):
            out = defaultdict(set)
            atoms = []
            _cmp_atoms(guard, atoms)
            for (r, op, v, pol) in atoms:
                if asserts_eq(op, pol):
                    out[r].add(v)
            return out

        entry_writes = defaultdict(dict)
        for room, vs in self.em.init_writes.items():
            for gi, v in vs.items():
                entry_writes[gi][room] = v

        def monotone(gi):
            dom = self.em.reg_vals.get(gi, set())
            return len(dom) <= 2 and 0 in dom and gi in entry_writes

        flags = set()
        in_eqs = defaultdict(list)                      # (src,dst) -> {reg:{vals}}
        for e in list(self.em.ts.edges) + list(self.em.ts.cs_edges):
            eqs = edge_eqs(e.guard)
            in_eqs[(e.src, e.dst)].append(eqs)
            if e.dst in prev_universe:
                for gi in eqs:
                    if monotone(gi):
                        flags.add(gi)
        flags = sorted(flags)
        if not flags:
            return []

        # --- joint reachability over (room, previous-room-abstract, flag values) ------------
        def succ(state):
            r, pa, fv = state
            out = set()
            for b in self.edges.get(r, ()):
                gate = gates.get(r, {}).get(b)
                if gate is not None and pa not in gate:
                    continue                            # grid gate: wrong entry cell
                blocked_flag = False
                nfv = list(fv)
                for reqs in in_eqs.get((r, b), ()):
                    for i, gi in enumerate(flags):
                        if gi in reqs and fv[i] not in reqs[gi]:
                            blocked_flag = True
                if blocked_flag:
                    continue
                for i, gi in enumerate(flags):
                    w = entry_writes[gi].get(b)
                    if w is not None:
                        nfv[i] = w
                out.add((b, r if r in prev_universe else "o", tuple(nfv)))
            return out

        start = (self.em.cfg.start_room, "o", tuple(0 for _ in flags))
        F = {start}
        q = deque([start])
        rev = defaultdict(set)
        while q:
            u = q.popleft()
            for v in succ(u):
                rev[v].add(u)
                if v not in F:
                    F.add(v)
                    q.append(v)

        def backward(targets):
            seen = set(targets)
            dq = deque(seen)
            while dq:
                u = dq.popleft()
                for w in rev.get(u, ()):
                    if w not in seen:
                        seen.add(w)
                        dq.append(w)
            return seen

        goal = self.goal_rooms_set()
        can_win = backward({s for s in F if s[0] in goal}) if goal else F

        out = []
        for it in sorted(self.required):
            srcs = self.sources.get(it, set())
            need = self.required[it]
            if not srcs or not need:
                continue
            # DELIVERABILITY, not mere obtainability. A source only helps if a need-room is still
            # reachable AFTER visiting it -- otherwise you can obtain the item but never carry it to
            # where it is used. `can_get` demands you can still reach a source FROM WHICH a need is
            # reachable. This is a strict generalisation of the old "can still reach a source":
            #   * Golden_Bridle -- its source (island rm43) can always reach its need (unicorn), so
            #     every source is "good" and the test is unchanged.
            #   * Dead_Fish -- its source (rm95) can NOT reach its need (island rm43) once the
            #     one-time whale is spent, so a fishless island state is correctly stranded. The old
            #     test called rm95 reachable and stopped, missing that you cannot get back to rm43.
            need_reachers = backward({s for s in F if s[0] in need})
            good_sources = {s for s in F if s[0] in srcs} & need_reachers
            can_get = backward(good_sources)
            # a reachable state at a required room, from which no DELIVERABLE source is reachable but
            # the goal still is (so it is the item that is missing, not a dead end).
            stuck = sorted({s[0] for s in F
                            if s[0] in need and s not in can_get and s in can_win})
            if stuck:
                out.append({"pattern": "joint-window-point-of-no-return",
                            "item": it, "item_name": self.g.item_name(it),
                            "source_rooms": sorted(srcs), "flags": flags,
                            "stranded_at": stuck})
        return out

    def _prev_room_global(self):
        if not hasattr(self, "_prg"):
            import extract as X
            self._prg = X.prev_room_global(self.em.ir)
        return self._prg

    def requirement_units(self):
        """Every unit that must be satisfied to win: single items, plus disjunctive GROUPS.

        `edge_strandings` iterates these rather than bare items, so a group inherits all of its
        conjuncts -- irreversibility, non-death-sink, and "still needed past the edge" -- instead
        of needing a parallel frontier walk that would drift from the canonical rule."""
        units = [frozenset({it}) for it in self.required if self.sources.get(it)]
        for R, groups in self.disjunctive_groups().items():
            for G in groups:
                if any(self.sources.get(i) for i in G):
                    units.append(frozenset(G))
        return units

    # ---- disjunctive requirement groups -------------------------------------
    def disjunctive_groups(self):
        """room -> {frozenset(items)}: sets that ALTERNATIVELY open the same gate.

        The per-item sweep is blind to these by construction -- no single member is required, so
        every member looks re-obtainable via its sibling. rm81 past the vine chasm is the case:
        `throw ash` (own 30) or `throw sand` (own 31) both arm the exit, and both sources sit
        back in the jungle you can never return to. Losing EITHER is survivable; losing BOTH is
        the softlock."""
        out = defaultdict(set)
        for (a, b), variants in self._emeta.items():
            for (req, setv, alts) in variants:
                uniq = set(alts)
                if len(uniq) < 2 or any(not x for x in uniq):
                    continue          # one alternative is free -> the gate is not a requirement
                if set.intersection(*map(set, uniq)):
                    continue          # a common item is needed -> per-item sweep already sees it
                out[a].add(frozenset().union(*uniq))
        return out

    def group_strandings(self):
        """Disjunctive groups that are faced past a point of no return to ALL their sources."""
        rows = []
        for R, groups in sorted(self.disjunctive_groups().items()):
            for G in sorted(groups, key=sorted):
                if R not in self.reach_rooms or R not in self._reach_without(G):
                    continue          # can never stand here lacking the whole group
                if R in self.reobtainable_rooms(G):
                    continue          # some member is still fetchable from here
                srcs = set()
                for it in G:
                    srcs |= self.sources.get(it, set())
                rows.append({"pattern": "missing-disjunctive-prereq-before-gate",
                             "items": sorted(G),
                             "item_names": [self.g.item_name(i) for i in sorted(G)],
                             "need_room": R, "source_rooms": sorted(srcs)})
        return rows

    def free_running_traps(self):
        """Free-running POINT-OF-NO-RETURN registers -- softlock class 2, the register-flip trap.

        A register the player CANNOT keep at a safe value: written pervasively by the always-live
        Game loop (KQ4's `KQ4::newRoom` sets global100:=1 -- nightfall -- in ~every room, driven by
        the wall clock), whose SAFE value (0, the start value) is restored in only a FEW rooms.
        Night falls everywhere and lifts nowhere but dawn (rm82, itself gated behind Lolotte's
        death). That asymmetry -- TRAP value pervasive, RESET localized -- IS the point-of-no-return
        signature, and it is exactly what separates KQ4's g100 from LSL2's g127: g127 is also
        Game-written across ~100 rooms, but its SAFE value 0 is the pervasive one and the trap 1 is
        written in just rm34/35 -- reset everywhere, so it can never trap you. Derived, not fitted:
        the rule reads the shape (which value is pervasive vs. localized), and LSL2's g127 fails it.

        Returns {R: {trap, safe, reset_rooms, set_in}}. This only CLASSIFIES the register; whether
        an item is actually sealed by the flip is a separate stranding query (which still needs the
        reset guard recovered -- the dawn write's Lolotte-dead condition -- and a joint over
        (R x possession), the remaining Phase-1b build)."""
        out = {}
        SAFE = 0     # SCI globals default-init to 0 and the opmodel seeds every register {0}; that
                     # start value is the SAFE baseline. Being FORCED to it is never a trap. (A game
                     # whose register has a non-zero start would need that init read from Main -- a
                     # documented limit, not a silent fudge.)
        for R in self.regs:
            loop_vals = {v for (room, script, gi, v, g) in self.em.handler_writes
                         if gi == R and script in self.GLOBAL_SCRIPTS}   # the always-live forcing
            if not loop_vals:
                continue                        # not written by the Game loop (script 0), so no trap
            byval = defaultdict(set)
            for r, vs in self._inroom.get(R, {}).items():
                for v in vs:
                    byval[v].add(r)
            # The trap value is one the Game loop FORCES that is NOT the safe baseline, and that
            # DOMINATES the room set -- so the reset to safety is the minority, i.e. localized. That
            # shape is what separates KQ4 g100 (loop forces 1=night, reset 0=day confined to rm82)
            # from LSL2 g127 (loop forces 0=safe -- forcing you to stay safe is no trap). The old
            # code baked reset<=3 and trap>=10x; here it is a derived dominance, no magic constant.
            for T in sorted(loop_vals):
                if T == SAFE:
                    continue
                forced = byval.get(T, set())
                reset = set().union(*(byval[v] for v in byval if v != T)) if byval else set()
                if forced and len(forced) > len(reset):
                    out[R] = {"trap": T, "safe": SAFE, "reset_rooms": sorted(reset),
                              "set_in": len(forced)}
                    break
        return out

    def register_flip_strandings(self):
        """Items sealed by a free-running TRAP register's flip -- softlock class 2.

        For each classified trap R (`free_running_traps`: safe value 0, an adversarial value written
        pervasively by the Game loop, reset confined to a few rooms), a door gated on `R == safe`
        SHUTS when the flip fires -- and the player cannot prevent the flip (it is the wall clock,
        not a choice). So there is a reachable state, R flipped and the item not yet taken, from
        which the item -- now behind a closed door whose reset is localized and downstream -- is no
        longer obtainable. By the one rule (is what you need still obtainable from here?) that is a
        softlock. KQ4: night (g100) shuts the dwarves' door rm22->54 (Diamond_Pouch) and the
        shanty door rm7->42 (Fishing_Pole); dawn is only at rm82, behind Lolotte's death.

        We flag an item only when EVERY one of its sources sits behind a trap-gated door (removing
        those doors makes the source unreachable) -- otherwise there is a trap-free way in and no
        seal. LSL2 has no trap register, so this returns [] and cannot move its golden."""
        traps = self.free_running_traps()
        if not traps:
            return []
        out = []
        for R, info in sorted(traps.items()):
            safe = info["safe"]
            doors = {(a, b) for (a, b), metas in self._emeta.items()
                     for (req, sets, alts) in metas if req.get(R) == {safe}}
            if not doors:
                continue
            # rooms still reachable if every trap-gated door is shut (the flipped world)
            shut = {x: (set(y) - {b for (a, b) in doors if a == x}) for x, y in self.edges.items()}
            reach_shut = reachable(shut, {self.em.cfg.start_room})
            for it in sorted(self.required):
                srcs = self.sources.get(it, set())
                if not srcs or (srcs & reach_shut):
                    continue                 # no source, or a source reachable without the door
                out.append({"pattern": "free-running-trap-seal", "item": it,
                            "item_name": self.g.item_name(it), "register": R,
                            "trap": info["trap"], "reset_rooms": info["reset_rooms"],
                            "source_rooms": sorted(srcs), "doors": sorted(doors)})
        return out

    def _pocket_leavable(self, pocket, Y):
        """Can you exit `pocket` to an outside room WITHOUT owning Y? False only if every
        pocket-exit edge REQUIRES Y in all its alternatives (Y forced, so not missable)."""
        for p in pocket:
            for q in self.edges.get(p, set()):
                if q in pocket:
                    continue
                metas = self._emeta.get((p, q))
                if not metas:
                    return True                  # ungated exit -> leavable
                if any(any(Y not in alt for alt in alts) for (req, sets, alts) in metas):
                    return True                  # some alternative needs no Y
        return False

    def toll_strandings(self):
        """One-visit-pocket strandings -- the consumed-gate class (softlock class 4).

        An edge a->b whose LONE item-gate X is SPENT crossing it (X dropped or one-way placed at a,
        and no longer re-acquirable from a) is a TOLL: it can be paid once. Cutting the toll edge
        leaves a POCKET of rooms reachable ONLY through it (b is dominated by the toll -- a pure
        room-graph fact, so the desert grid that walls off the gate-aware projections cannot
        confound it). A required item whose every source sits in that pocket, still needed outside
        it, and leavable without taking it, is stranded: you can walk out empty-handed and the toll
        is already spent.

        KQ5's temple: the Staff(7) breaks opening rm18 (`put: 7 214`), so rm18 is a one-visit
        pocket and the Brass_Bottle(6)/Gold_Coin(11) inside become unreachable once you leave
        without them. The reobtainable(X) filter keeps this silent on LSL2/KQ4 -- every candidate
        gate item there (Vine, Ashes, Sand, Lottery_Ticket, Talisman) is re-obtainable, so neither
        game has a one-way toll and this returns [] for both."""
        placed = getattr(self.em.ts, "placed", {})
        start = self.em.cfg.start_room
        full = self.reach_rooms
        out, seen = [], set()
        for (a, b), metas in sorted(self._emeta.items()):
            if a not in full:
                continue
            gates = {next(iter(alt)) for (req, sets, alts) in metas
                     for alt in alts if len(alt) == 1}
            # A toll need not be an ITEM. The same "you may cross this once" shape arises when the
            # gate is a set-once FLAG the far side raises: KQ6's realm of the dead is entered only
            # while flag 15 is clear, and arriving in rm600 sets flag 15 and nothing ever clears
            # it. Item-spent and flag-raised are two spellings of one fact, so they share the
            # pocket logic below rather than getting a second detector.
            inroom = getattr(self, "_inroom", {})
            flag_tolls = sorted(_selfsealing_flags(metas, inroom))
            for X in sorted(gates) + [("flag", F) for F in flag_tolls]:
                if isinstance(X, tuple):
                    pass                         # a flag toll is one-time by construction
                else:
                    spent = a in self.drops.get(X, set()) or a in placed.get(X, set())
                    if not spent or a in self.reobtainable_rooms(X):
                        continue                 # not spent here, or spent but re-gettable -> benign
                cut = {u: (v - {b} if u == a else v) for u, v in self.edges.items()}
                pocket = full - reachable(cut, {start})
                if b not in pocket:
                    continue                     # b reachable another way -> not a sealed pocket
                if isinstance(X, tuple) and not _flag_set_inside(X[1], pocket, inroom):
                    continue                     # the flag is not raised in there -> re-enterable
                for Y in sorted(self.required):
                    if Y == X:
                        continue
                    srcs = self.sources.get(Y, set())
                    if not srcs or not (srcs <= pocket):
                        continue                 # obtainable outside the pocket
                    if not (self.required.get(Y, set()) - pocket):
                        continue                 # only needed inside -> taking it there suffices
                    if not self._pocket_leavable(pocket, Y):
                        continue                 # every exit demands Y -> forced, not missable
                    k = (Y, a, b)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append({"pattern": "one-visit-toll-pocket", "item": Y,
                                "item_name": self.g.item_name(Y),
                                "toll_item": None if isinstance(X, tuple) else X,
                                "toll_item_name": (f"flag{X[1]}" if isinstance(X, tuple)
                                                   else self.g.item_name(X)),
                                "toll_edge": [a, b], "pocket": sorted(pocket),
                                "source_rooms": sorted(srcs)})
        return out


def _selfsealing_flags(metas, inroom):
    """Registers this edge needs at 0 which the FAR SIDE then raises for good.

    The self-disabling one-visit entry: you may cross while F is clear, and crossing leads
    somewhere that sets F and nothing ever clears it, so the crossing happens exactly once. Only
    registers we synthesized from a flag store qualify -- their domain really is {0,1}, so "needs
    0" and "raised to 1" are the same axis -- and only if nothing writes 0 anywhere, which is what
    makes it permanent rather than a toggle."""
    out = set()
    for (req, sets, alts) in metas:
        for R, vals in req.items():
            if vals != {0} or R not in vocab.BOOL_GLOBALS:
                continue
            writes = {v for rooms in (inroom.get(R) or {}).values() for v in rooms}
            if 0 in writes or 1 not in writes:
                continue                         # cleared somewhere, or never raised -> no seal
            out.add(R)
    return out


def _flag_set_inside(R, pocket, inroom):
    """Is R raised somewhere in the pocket -- i.e. does going in seal the way back?"""
    return any(1 in vs for room, vs in (inroom.get(R) or {}).items() if room in pocket)


def load(cfg=None, ir_path=None):
    cfg = cfg or config.ACTIVE
    ir_path = ir_path or cfg.ir_path
    ir = I.load_ir(ir_path)
    # DERIVE both of the old per-game constants; config is now only a fallback/override.
    # See vocab.derive_death / derive_debug -- the anchors are engine vocabulary (the Game
    # subclass's route to Restore/Restart/Quit, and the `^=` toggle a debug checkbox compiles to),
    # which is why they survive a change of game. The old claim here was that death "cannot be
    # derived; LSL2 and KQ4 disagree on both index and shape" -- true only if you guess the shape
    # instead of reading it out of the test.
    import vocab as V
    # Death detection is DISPATCHED on the engine generation (vocab.is_sci11), a sharp and principled
    # divide: SCI0/SCI1 offer Restart/Restore ONLY on death, so any reachable Restart offer IS a
    # death; SCI1.1 also surfaces it from an always-available control panel, so that assumption breaks
    # and death must be recognised at the hazard instead. The signal is normalised to one (global,
    # value) either way, so nothing downstream knows which path ran.
    sig = tuple(cfg.death_signal) if cfg.death_signal else ()
    if not sig and V.is_sci11(ir):
        # SCI1.1: death = reaching a death DIALOG (a non-menu object offering both restart: and
        # restore:), either inline in a hazard script or via a proc that newRooms into a death room
        # (KQ6 proc0_1 -> rm640, called from the archer/minotaur/... hazards). See derive_death_sci11.
        dialogs, dprocs = V.derive_death_sci11(ir)
        if dialogs or dprocs:
            synth, _n = V.lower_death_sci11(ir, dialogs, dprocs)
            sig = (synth, 1)
    if not sig and not V.is_sci11(ir):
        found = V.derive_death(ir)          # the global-flag shape (LSL2 gCurrentStatus, KQ4 g127)
        if found:
            sig = found[0][0]
        if not sig:
            # Imperative death: no "you died" global -- death is a call to a dialog PROCEDURE
            # (Camelot proc128_0, TCB proc0_19, KQ5 proc0_26). Lower each call to a synthetic
            # death-flag write so the (gi, v) machinery below applies unchanged.
            dprocs = V.derive_death_proc(ir)
            if dprocs:
                synth, _n = V.lower_death_procs(ir, dprocs)
                sig = (synth, 1)
    if not sig:
        raise SystemExit("could not derive a death signal, and config.death_signal is unset. "
                         "Expected the Game subclass to test a global on the way to restart:/"
                         "restore:, a public death procedure that offers it, or (SCI1.1) a death "
                         "dialog offering both restart: and restore:.")
    import dataclasses
    if not cfg.debug_globals:
        cfg = dataclasses.replace(cfg, debug_globals=frozenset(V.derive_debug(ir)))
    if not cfg.death_signal:
        cfg = dataclasses.replace(cfg, death_signal=sig)   # so reports show what was derived
    # Flag store: lower the game's boolean-flag bit-array into synthetic per-flag globals, so each
    # flag becomes an ordinary gating register with nothing downstream aware of "flags" (see
    # vocab.derive_flags). Runs after death lowering so the synthetic block clears the death flag
    # too. A no-op on games with no bit-array store -- LSL2/KQ4 have none, so they are untouched.
    flags = V.derive_flags(ir)
    if flags:
        V.lower_flags(ir, flags[0], flags[1])
    # SECOND flag store: the same bit-in-a-word abstraction kept in an object's PROPERTY words
    # instead of a global array (SCI1.1 regions do this). Lowered to the same synthetic globals,
    # after lower_flags so the two synthetic blocks cannot overlap. Games without it are
    # untouched -- LSL2/KQ4/KQ5/QFG-VGA/Dagger have zero sites, KQ6 has 329.
    V.lower_prop_flags(ir, V.derive_prop_flags(ir))
    # THIRD container: state kept in an ordinary object's PROPERTY. SCI1.1 leans on it because a
    # region object outlives the rooms inside it -- KQ6's minotaur fight is decided entirely by
    # `(ScriptID 30 0) scarfOnMino:` / `seenByMino:`. Same "written with a constant AND read back"
    # rule as every other store, lowered to the same synthetic globals.
    V.lower_obj_props(ir, V.derive_obj_props(ir))
    # FOURTH store, in the spelling item_property_registers cannot see: an item keeping its own
    # state as BIT FLAGS in its own property, written from inside its own methods via `self` and
    # read as a bare property. KQ6's skull gates the realm-of-the-dead cutscene on exactly that.
    import extract as _X
    _X.install_vocabulary(ir)
    V.lower_item_bit_flags(ir, V.derive_item_bit_flags(ir, _X._at_item), _X._at_item)
    d_gi, d_val = sig[0], (sig[1] if len(sig) > 1 else None)
    is_death = (lambda gi, v: gi == d_gi and v == d_val) if d_val is not None else \
               (lambda gi, v: gi == d_gi and bool(v))
    em = E.OpEmitter(ir, cfg, is_death)
    if not cfg.start_room or not cfg.goal_rooms:
        # Derive the reachability anchors from the game rather than declaring them. See anchors.py:
        # start = first room the player can act in, widest forward reach; goal = terminal,
        # reachable, never fatal. On LSL2 the derived pair reproduces the hand-tuned one exactly.
        import dataclasses, anchors
        st, gl = anchors.discover(em)
        cfg = dataclasses.replace(cfg, start_room=cfg.start_room or st,
                                  goal_rooms=cfg.goal_rooms or gl)
        em.cfg = cfg
    return IrSccReach(em)


if __name__ == "__main__":
    s = load()
    print(f"rooms={len(s.rooms)}  SCCs={len(s.comps)}  goal_comps={sorted(s.goal_comps)}")
    cands = s.analyze()
    flagged = sorted({c["item"] for c in cands})
    print(f"softlock candidates ({len(flagged)} items):",
          [s.g.item_name(i) for i in flagged])
    for row in s.resource_exhaustion():
        where = (f"the roaming region {sorted(row['at_rooms'])}" if "at_rooms" in row
                 else f"rm{row['at_room']}")
        print(f"  + resource exhaustion: {row['item_name']} ({row['property']}) becomes unusable "
              f"at {where}, still needed at {row['still_needed_at']}")
    for row in s.group_strandings():
        print(f"  + disjunctive group {row['item_names']} needed at rm{row['need_room']}, "
              f"all sources {row['source_rooms']} unreachable from there")
    base = {c["item"] for c in cands}
    for row in s.joint_strandings():
        if row["item"] in base:
            continue                    # already an edge/register stranding -- the joint just re-sees it
        print(f"  + joint-window softlock: {row['item_name']} (source {row['source_rooms']}) is "
              f"unreachable once flags {row['flags']} advance -- still needed at {row['stranded_at']}")
