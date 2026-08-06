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
_WARNED_MODEL = set()


def _degraded_model(msg):
    """Report a place where the model gave up and answered with less than the game contains.

    Budget caps and fallbacks are legitimate, but a SILENT one is indistinguishable from a
    clean analysis -- the failure mode this project keeps naming. Deduplicated so a per-machine
    loop cannot spam."""
    if msg in _WARNED_MODEL:
        return
    _WARNED_MODEL.add(msg)
    import sys as _sys
    print("  [degraded] " + msg, file=_sys.stderr)


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

    # SEALED EXITS: a room's own `newRoom:` override that intercepts a destination and arms a
    # turn-back instead of calling super refuses that crossing at the engine funnel itself, so
    # the edge does not exist -- whatever spelling produced it above (nav property, walk-off,
    # machine EXIT). KQ6's Realm interior is the instance (rm670-/->660, rm680-/->670,
    # `dontGoAlex`; findings #15/#16): unsealed, the toll walk deferred the Styx-cup demand
    # past Charon into a pocket with no controllable site, and the placed arm-events hung the
    # game in play. Subtracted HERE, at the one assembly point, so every consumer -- reach,
    # frontiers, the placement walk's last-satisfiable-crossing -- sees the same world.
    ir = getattr(em, "ir", None)
    if ir is not None:
        import extract as X
        for (a, b) in X.sealed_exits(ir):
            edges.get(a, set()).discard(b)
            edge_kind.pop((a, b), None)

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
    # AN ACQUISITION YOU CAN ONLY REACH WHILE ALREADY HOLDING THE ITEM IS NOT A SOURCE. Sierra
    # writes "take it back down" with the very same `get:` as "pick it up", and the only thing
    # separating them is the condition: KQ6's hole-in-the-wall sticks onto any wall you like and
    # comes off again, so `get: 18` appears in the labyrinth's shared script and thus in EVERY
    # maze room, and the model believed the hole was freshly obtainable throughout the trap it is
    # needed to escape. The take-back is armed from an object that only exists because you put the
    # hole up (see `cast_conditions`), so its entry demands own(18) -- and something you must
    # already have is not something a room GIVES you.
    #
    # Per SITE, and a room keeps its source if ANY site is free: this only ever removes a
    # re-acquisition, never a first one.
    # ...AND AN ACQUISITION YOU CAN ONLY REACH BY ARRIVING FROM SOMEWHERE THAT CANNOT REACH IT is
    # not a source either. Same "per site, only ever removes an impossible one" discipline; the
    # question it answers -- and why it is the previous-room register rather than a debug global --
    # is in `_prev_impossible`. `edges` is complete by here; nothing below adds to it.
    prev = prev_room_reg(em)
    mg = getattr(em, "machine_gets", set())
    for a in em.ts.acqs:
        # The same `get:` inside a `changeState` body is walked twice -- here with the body's own
        # path condition (nothing) and by the machine lift, which knows what arming it costs.
        # Matched by the emitting object, exactly as `edge_meta` matches a suppressed cs_edge.
        if (a.room, a.via, a.item) in mg:
            continue
        if (not _debug_gated(a.guard) and a.item not in _own_required(a.guard)
                and not _prev_impossible(a.guard, a.room, prev, edges)):
            sources[a.item].add(a.room)
    for room, script, it, g in em.handler_gets:
        if (not _debug_gated(g) and it not in _own_required(g)
                and not _prev_impossible(g, room, prev, edges)):
            sources[it].add(room)
    for info in em.machines:
        em_ = entry_musts(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                # ...and what EVERY way of arming this machine demands you already hold.
                must = em_.get(K, frozenset())
                for it in gg:
                    if it not in must | _own_required(g):
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
    # THE ALWAYS-LIVE SCOPES CONTRIBUTE EFFECTS, NOT REQUIREMENTS. `required[X]` means "own(X) is
    # FACED here, as a gate" -- it is the evidence a frontier is computed from, so it has to be a
    # claim about a PLACE. An SCI1 inventory `doVerb` is dispatched by the icon bar and so is
    # available in every room at once; attributing its guard per room converts an AVAILABILITY
    # into a universal requirement, every frontier ends up with everything past it, and
    # `edge_strandings` collapses. Measured on KQ6 when it was done that way: five confirmed
    # softlocks LOST (brick, deadMansCoin, handkerchief, skeletonKey, tinderBox), thirteen false
    # positives gained, and a 45-item guard on rm340->rm155.
    #
    # What such a scope legitimately contributes is kept in full, and elsewhere: the register write
    # itself and its PRECONDITIONS, which land on the cost path (`cheapest((gi, room, v), ...)`).
    # "What it costs to make flag 22 true" is exactly where `flag58 AND flag68` belongs, and that
    # is what makes the teacup's Styx water reach the castle door.
    #
    # `opmodel.global_homed` is derived (`vocab.inventory_scripts`), and on SCO0 titles it is empty
    # because their items live in script 0 -- so this test cannot move LSL2 or KQ4.
    globalsc = getattr(em, "global_homed", ())

    def req(guard, room, script=None):
        if script is not None and script in globalsc:
            return
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
        req(g, room, script)
    for room, script, gi, v, g in em.handler_writes:
        req(g, room, script)
    # entry guards of machines we chose not to model -- see opmodel.dropped_entries
    for room, eg, _inst, _recv in getattr(em, "dropped_entries", ()):
        req(eg, room)
    # consuming an item in a HANDLER -- the Pamphlet handed to the bore on the plane (rm62) is a
    # Said-handler `put: 26 -1`, which the machine-body scan never sees. Held back; see below.
    for room, script, it, g, _dest in getattr(em, "handler_drops", ()):
        if script in globalsc:
            continue        # ...and the same for the consumption fallback: an inventory `put:` is
        consumed_at[it].add(room)   # spent wherever you do it, which is nowhere in particular.
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
    # BOTH lists: an always-live scope's writes are real writes -- KQ6's flag 22 (the magic
    # paint) is written by the inventory `doVerb` and nowhere else, so without this it can never
    # be promoted and the castle's long door reads as free. See opmodel.global_machines for why
    # that scope is kept out of `machines` everywhere else.
    for info in all_machines(em):
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


def all_machines(em):
    """Room machines PLUS the always-live scopes' -- for the three consumers that want both.

    EVERYTHING ELSE TAKES `em.machines` ALONE, DELIBERATELY. A machine the icon bar dispatches has
    no place, and almost everything `machines` feeds is a claim about a place (`required`,
    `sources`/`drops`, EXIT, `death_traps` -- each measured, each broken by lifting it). Only the
    register build wants both lists, because "you can make flag 22 true here, at this cost" IS
    true in every room. See `opmodel.global_machines` for the argument in full.

    Written once so the exception is stated once instead of at each call site, and so the
    defensive `getattr` -- which exists for the duck-typed emitters the unit tests build, not for
    the real one -- lives in one place rather than three."""
    return list(em.machines) + list(getattr(em, "global_machines", ()))


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


def _must_equal(guard, out=None):
    """`(reg, value)` pairs the guard REQUIRES to be EQUAL, along its top-level AND spine.

    The mirror of `_must_hold`, which collects the `!=` assertions; same discipline and the same
    reason for it. Stops at any negation or disjunction, because a conjunct under an OR is not
    required and claiming it would let a caller delete something the game allows. The one negation
    it does descend is `(not (!= x v))`, whose flip is computable because the operand is a leaf."""
    out = set() if out is None else out
    if isinstance(guard, list):
        for g in guard:
            _must_equal(g, out)
    elif isinstance(guard, GAnd):
        for k in guard.kids:
            _must_equal(k, out)
    elif isinstance(guard, Pred) and guard.kind == "CMP" and guard.op == "==":
        try:
            out.add((guard.var, int(guard.value)))
        except (TypeError, ValueError):
            pass
    elif (isinstance(guard, GNot) and isinstance(guard.kid, Pred)
          and guard.kid.kind == "CMP" and guard.kid.op == "!="):
        try:
            out.add((guard.kid.var, int(guard.kid.value)))
        except (TypeError, ValueError):
            pass
    return out


def _prev_impossible(guard, room, prev, edges):
    """Does `guard` demand you arrived in `room` from somewhere that cannot reach it?

    The previous-room register is written by no room and by every transition -- taking a->b sets it
    to a -- so `prev == R` inside room X asserts "you got here from R", and the ROOM GRAPH already
    knows whether that is possible. Nothing about items is involved, so this needs no fixpoint: it
    can be asked while the maps are still being built.

    What it is for: Sierra's developer warps. KQ6 hands out five items at once in
    `rm470::init` under `(and global100 (== global12 99) (FileIO 10 {g}))`, and rm99 is the room
    `Main::init` ends on -- so the branch is dead in play, but read permissively it is a free source
    for the old lamp, the skull and the teacup, in a room you can always reach. rm740 and rm750 do
    the same for the peppermint.

    DERIVED, not a debug heuristic, and that distinction is load-bearing. The alternative was to
    recognise KQ6's `(FileIO 10 <marker>)` probe and pin the global it sets, the way
    `config.debug_globals` pins LSL2's. That is worse twice over: KQ6 sets `global90` from the very
    same probe shape to detect the CD, so the recogniser would have to tell two identical idioms
    apart -- and pinning the global also deletes the debug hand-out in `rm740.sc:261`, which sits
    inside a LEGITIMATE `(== global12 180)` branch, leaving `royalRing` with no modelled source and
    inventing a softlock the item oracle says is safe. Reading the previous room leaves that one
    alone, because `prev == 180` IS satisfiable. Measured both ways.

    Three conditions, all of them the conservative direction:
      * the demand is on the top-level AND spine (`_must_equal`), so a `prev` test inside an OR or
        under a negation -- where it is not required -- is ignored;
      * we must actually KNOW where R goes (`R in edges`). A room we extracted no out-edge for is a
        room we learned nothing about, and "no evidence" must not read as "cannot happen" -- that
        is the direction that invents softlocks;
      * and `room` must not be among them."""
    if prev is None:
        return False
    for reg, val in _must_equal(guard):
        if reg == prev and val in edges and room not in edges[val]:
            return True
    return False


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
    from compile import _ctr_holds, _lreg_test
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
    # The machine's OWN lowered room locals (vocab.lower_room_locals) thread through this walk as
    # counters keyed by their synthetic-global index: the script reloads on room entry, so every
    # arming starts from the declared reset unless the arming context itself wrote the latch --
    # the same "unset reads as 0" the raw-local counters have always had, with the declared value
    # in place of the guess. The atoms and writes STAY registers for every other consumer.
    lregs = info.get("local_regs") or {}
    if lregs:
        ents = [((K, eg), {**lregs, **loc}) for (K, eg), loc in ents]
    carried = set().union(*[set(loc) for _ke, loc in ents]) if ents else set()

    def _ctr_ok(g, counters):
        for a in g:                                # g is a path's atom list (a conjunction)
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in carried and not _ctr_holds(a, counters):
                return False
            if _lreg_test(a, lregs, counters) is False:
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

    per_entry = _entry_reach_walk(info, ents, carried, _ctr_ok, _apply, lregs)
    # THE ARMING FLOOR. You cannot be executing ANY state of this machine without having armed it,
    # so the machine's full arming disjunction bounds every state -- including one the walk above
    # never reached. Falling off the end of the walk is IGNORANCE about the internal path, not
    # evidence that the state is free; the same lesson `fatal_uses` had to learn ("falling off the
    # end of the state graph is not evidence of survival"), in a different consumer.
    #
    # What stops the walk is idiom-specific and there are several: an elided state, a register
    # handoff, or -- KQ6's `wearClothingScr` -- a state that cues ANOTHER script and is resumed by
    # it, so the advance leaves this machine entirely. state 20 does `(secondGuardDoorScr cue:)`
    # and state 21 is the `newRoom: 730` that puts on Beauty's clothes and walks into the castle.
    # The walk stops at 20, so 21 came out ungated and the disguise requirement vanished from the
    # castle's short door. A floor fixes the whole class at once rather than one idiom at a time.
    #
    # This can only ever ADD a requirement that some arming genuinely demands, never invent one:
    # it is the disjunction OVER the entries, so an EXIT is blocked exactly when every way of
    # arming the machine is blocked. A machine with NO entries keeps the empty tuple -- there we
    # really do not know how it is armed, and free is the only honest answer.
    floor = tuple({frozenset(_own_positive(eg)) for (_seen, eg, _loc) in per_entry})
    out = {}
    for K in info["states"]:
        reached = tuple({frozenset(_own_positive(eg)) for (seen, eg, _loc) in per_entry if K in seen})
        out[K] = reached or floor
    return out


def _entry_reach_walk(info, ents, carried, _ctr_ok, _apply, lregs=None):
    """[(states this entry can reach, its guard)] -- the ONE entry-reachability walk.

    Factored out because two views need it: `entry_alts` (which items arm a state) and
    `entry_reqs` (which registers every arming establishes). An entry-reachability rule
    implemented in two places is this project's most-repeated bug -- see test_walkers."""
    cached = info.get("_entry_reach")
    if cached is not None:
        return cached
    lregs = lregs or {}
    per_entry = []
    for (K, eg), loc in ents:
        seen, visited = set(), set()
        stack = [(K, {n: v for n, v in loc.items() if n in carried})]
        while stack:
            if len(visited) > 4000:                # a carried local inc'd in a loop can blow up the
                seen |= set(info["states"])         # (state, counters) space; fall back to permissive
                break                               # (all states reachable) rather than under-report
            u, counters = stack.pop()
            key = (u, tuple(sorted(counters.items(), key=repr)))
            if key in visited:
                continue
            visited.add(key)
            seen.add(u)
            for (g, w, gg, c, tr) in info["states"].get(u, ()):
                if not _ctr_ok(g, counters):
                    continue
                nc = _apply(counters, c)
                for (gi, v) in (w or ()):
                    if gi in lregs:                # the machine's own lowered-local write: the
                        nc[gi] = v                 # walk tracks it, the register model keeps it
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
    before says nothing after.

    The dataflow node is `(state, local valuation)`, NOT the state alone, and that distinction is
    the whole point. A cutscene routinely decides something early, remembers it in a LOCAL, and
    acts on it much later. KQ6's tapestry is the case:

        (2  (if (rLab seenSecretLatch:) (= local1 1) ... else (self cue:)))
        (18 (if local1 ... (rLab hiddenDoorOpen: 1) ... else (self cue:)))

    so opening the secret door to the minotaur's lair requires having watched him through the
    hole-in-the-wall. Keyed by state alone, both branches of state 2 reach state 18 and the merge
    -- correctly, for "what holds on EVERY path here" -- throws `seenSecretLatch` away before the
    local can discriminate. Split the node by the local and the two paths never meet: the branch
    that reaches the write is the one that established the latch. (Tracking locals as extra FACTS
    instead of as part of the node does not work, and was tried; the merge still erases them.)

    Locals are the machine's own, resolved exactly as `compile_machine` resolves them -- same
    `_apply_counters` / `_ctr_holds`, same "an UNESTABLISHED local is unknown, not 0" (corrected
    2026-08-06: reading it as 0 answered confidently about a value the walk never saw and killed
    203 KQ6 state-paths, `alexWedding`'s exits among them), same seeding from the arming
    context's `entry_locals` -- so the two views of one machine cannot drift. A path whose counter
    guard is decidably false at the current valuation is not walked at all.

    Returns a mapping usable as before (`sm.get(K, {})` merges every valuation reaching K, the
    conservative answer) plus `sm.at(K, guard)`, which keeps only the valuations that guard's own
    counter conditions admit -- what a consumer holding a specific path should ask."""
    import compile as C
    out = {}                                       # (K, loc-key) -> {R: set(values)}
    work = []

    def key(loc):
        return tuple(sorted(loc.items(), key=repr))

    def seed(K, loc):
        k = (K, key(loc))
        if k not in out:
            out[k] = {}
            work.append((K, dict(loc), {}))

    ents = list(info.get("entries", ()))
    elocs = list(info.get("entry_locals", ()))
    for i, (K, _eg) in enumerate(ents):
        seed(K, elocs[i] if i < len(elocs) else {})
    ients = list(info.get("init_entries", ()))
    ilocs = list(info.get("init_entry_locals", ()))
    for i, (K, _eg) in enumerate(ients):
        seed(K, ilocs[i] if i < len(ilocs) else {})
    seen = 0
    while work and seen < 20000:
        seen += 1
        K, loc, cur = work.pop()
        for (g, w, gg, c, tr) in info["states"].get(K, ()):
            if any(isinstance(a, tuple) and a and a[0] == "CTR" and not C._ctr_holds(a, loc)
                   for a in (g if isinstance(g, list) else [g])):
                continue                           # this branch is not taken at this valuation
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
            nloc = C._apply_counters(loc, c or ())
            dk = (dst, key(nloc))
            if dk in out:
                merged = {R: out[dk][R] | nxt[R] for R in set(out[dk]) & set(nxt)}
                if merged == out[dk]:
                    continue                       # fixpoint on this edge
                out[dk] = merged
            else:
                out[dk] = nxt
            work.append((dst, nloc, out[dk]))
    if work:
        # THE CAP RAN OUT WITH WORK LEFT, so `out` holds constraints established by only SOME
        # of the paths that reach each state -- and a MUST is an intersection, so a partial
        # answer is too TIGHT, not too loose. Downstream `edge_meta` intersects it into the
        # crossing's requirements, so an over-tight must removes a crossing the game allows,
        # shrinks `reobtainable_rooms` and INVENTS a stranding. Fall back to no constraints,
        # which is the direction the sibling walk at `_entry_reach_walk` already takes ("fall
        # back to permissive rather than under-report"), and say so: a machine whose musts we
        # could not establish is a real gap in the model, not a normal result.
        _degraded_model("state_musts hit its %d-step cap for %s; treating its musts as "
                        "UNKNOWN (permissive) rather than shipping a partial intersection"
                        % (20000, info.get("inst", "?")))
        return _Musts({})
    return _Musts(out)


class _Musts(dict):
    """`state -> musts`, merged over local valuations, with `at()` for a specific path.

    Subclasses dict so every existing `sm.get(K, {})` reads the merged (conservative) answer and
    nothing had to change to keep working."""

    def __init__(self, by_node):
        self._by_node = by_node
        merged = {}
        for (K, _lk), d in by_node.items():
            merged[K] = d if K not in merged else \
                {R: merged[K][R] | d[R] for R in set(merged[K]) & set(d)}
        super().__init__(merged)

    def at(self, K, guard):
        """The musts at K over only the valuations `guard`'s own counter conditions admit."""
        import compile as C
        conds = [a for a in (guard if isinstance(guard, list) else [guard])
                 if isinstance(a, tuple) and a and a[0] == "CTR"]
        if not conds:
            return self.get(K, {})
        acc = None
        for (K2, lk), d in self._by_node.items():
            if K2 != K or not all(C._ctr_holds(a, dict(lk)) for a in conds):
                continue
            acc = dict(d) if acc is None else {R: acc[R] | d[R] for R in set(acc) & set(d)}
        return acc if acc is not None else self.get(K, {})


def _own_negative(guard, out=None):
    """Items the guard requires you NOT to hold -- `own(X)` under a negation. The mirror of
    `_own_positive`, and what turns "you die here without the brick" into "leaving needs it"."""
    out = set() if out is None else out

    def w(g, neg):
        if isinstance(g, list):
            for k in g:
                w(k, neg)
        elif isinstance(g, GNot):
            w(g.kid, not neg)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                w(k, neg)
        elif isinstance(g, Pred) and g.kind == "OWN" and neg:
            out.add(g.var)
    w(guard, False)
    return out


def _has_opaque(guard):
    """Does the guard contain anything we could not model? Then it is not safe to negate."""
    if isinstance(guard, list):
        return any(_has_opaque(k) for k in guard)
    if isinstance(guard, (GAnd, GOr)):
        return any(_has_opaque(k) for k in guard.kids)
    if isinstance(guard, GNot):
        return _has_opaque(guard.kid)
    if isinstance(guard, Pred):
        return guard.kind not in ("OWN", "CMP", "LOC", "IPROP", "POS")
    return guard is not None            # a bare tuple (CTR) or anything unrecognised


def _trap_rooms(em):
    """`room -> [machine info]`, including the machines we chose not to model.

    A machine we dropped is still a COMPETITOR for the room's script slot. KQ6's `lightItUp` is
    gated `own(tinderBox)` and does nothing we track (it starts a palette fade), so it is dropped --
    and it is the only thing that stops the minotaur killing you in the dark. Carried as a stateless
    stand-in: no states, so it can never be `fatal`, but its NAME still participates in the doomed
    walk, so a dropped machine that re-arms the death is excluded like any other."""
    by_room = {}
    for info in em.machines:
        by_room.setdefault(info["room"], []).append(info)
    for room, eg, inst, recv in getattr(em, "dropped_entries", ()):
        by_room.setdefault(room, []).append(
            {"room": room, "inst": inst, "entries": [(0, eg)], "entry_recv": [recv],
             "entry_armers": [], "states": {}})
    return by_room


def _trap_graph(infos):
    """`(arms, fatal, doomed)` for one room's machines.

    `fatal` names the machines that reach a DEATH transition themselves; `doomed` closes that over
    the arming graph, so a machine that ends by arming the death is doomed too. KQ6's `throwSkull`
    is the specimen -- it throws the skull into the gears, the gears are not jammed, and its last
    state arms `sqwishEm` again.

    `handoff` is the same arming relation keyed by the ARMING STATE,
    `(armer, state) -> {armed name: the entry guard IT gets from this site}`, which is what tells a
    state that ends the machine apart from one that ends it by starting the death. `entry_armers`
    already carries the state; only `arms` was throwing it away. The guard comes along because an
    arming site can carry a condition the armer itself contradicts -- see `_ctr_contradicted`.

    Shared by `death_traps` and `fatal_uses`, which ask opposite questions of the same graph: one
    wants the machines that are NOT doomed (the escapes), the other wants the ones that ARE (the
    actions that kill you). They were one function's local variables, and the second consumer is
    exactly the moment that becomes a bug waiting to happen -- see the codebase's running theme of
    the same rule living in two places."""
    arms, handoff = {}, {}                         # machine name -> names it arms; + by state
    for info in infos:
        for j, a in enumerate(info.get("entry_armers") or ()):
            if a:
                arms.setdefault(a[0], set()).add(info["inst"])
                ents = info.get("entries") or ()
                g = ents[j][1] if j < len(ents) else None
                handoff.setdefault(a, {})[info["inst"]] = g
    fatal = {i["inst"] for i in infos
             if any(tr and tr[0] == "DEATH"
                    for _K, ps in i["states"].items() for (_g, _w, _gg, _c, tr) in ps)}
    doomed, changed = set(fatal), True
    while changed:                                 # ...and anything that arms something fatal
        changed = False
        for a, bs in arms.items():
            if a not in doomed and (bs & doomed):
                doomed.add(a)
                changed = True
    return arms, fatal, doomed, handoff


def _succ_state(K, tr):
    """The state a transition moves to, or None if it ends the machine. The successor rule is the
    game's, and it is spelled the same way in `opmodel._state_info`; keep them in step."""
    if not tr:
        return None
    return (K + 1 if tr[0] == "ADVANCE" else tr[1] if tr[0] == "JUMP" else
            tr[1] + 1 if tr[0] == "SETSTATE" else None)


def _ctr_contradicted(guard, known):
    """Does `guard` demand a local/register value that `known` says it does not have?

    Only the top-level AND spine, and only leaves whose key we actually know -- the same discipline
    as `_must_hold`. A demand under an OR is not a demand, and a key we have no value for tells us
    nothing.

    This exists because SCI's `register` lets ONE machine be two, and the two halves can disagree
    about whether you die. KQ6's rm407 is the case, and it is why putting the hole on the wall --
    the puzzle's solution -- looked like a fatal use:

        rm407.sc:193       (gCurRoom setScript: putHoleOnWall 0 1)     ; armed with REGISTER 1
        putHoleOnWall st4  (if (== register 1) (gEgo setScript: holeTimer) ... (self dispose:)
                            else (client setScript: emptyHandedDeath))

    so the death is armed from `putHoleOnWall` only when its register is NOT 1 -- and it is always
    1. The model had both halves all along: the death's entry from that site carries
    `NOT (R0 == 1)`, and `putHoleOnWall`'s own `entry_locals` carries `{('R',0): 1}`. Nothing was
    missing except putting them together."""
    if not known:
        return False
    out = []

    def walk(g, pol):
        if isinstance(g, list):
            for k in g:
                walk(k, pol)
        elif isinstance(g, GAnd) and pol:
            for k in g.kids:
                walk(k, pol)
        elif isinstance(g, GNot):
            walk(g.kid, not pol)
        elif isinstance(g, tuple) and len(g) == 4 and g[0] == "CTR" and g[1] in known:
            got, op, want = known[g[1]], g[2], g[3]
            holds = (got == want) if op == "==" else (got != want) if op == "!=" else None
            if holds is not None and holds is not pol:
                out.append(True)
    walk(guard, True)
    return bool(out)


def _armer_knowns(info):
    """Local/register values that EVERY arming of this machine establishes.

    Intersected across entries, because one arming setting `register 1` says nothing about a second
    arming that sets 0 -- and suppressing a death on a value only one way in provides is how you
    lose a real hazard."""
    ents, els = info.get("entries") or (), info.get("entry_locals") or ()
    if not ents or len(els) != len(ents):
        return {}
    common = None
    for d in els:
        d = d or {}
        common = dict(d) if common is None else {k: v for k, v in common.items() if d.get(k) == v}
    return common or {}


def _survivable(info, unavoidable, handoff, start=None):
    """Is there ANY way through this machine, FROM STATE `start`, that does not end in death?

    Per ENTRY, not per machine, because one machine routinely serves both roles. KQ6's
    `emptyHandedDeath` is armed four ways at three different states -- one of them the timer that
    kills you for lingering, another the act of putting the hole UP, which is the puzzle's solution.
    Asking only about the machine's own `start` and then blaming every entry condemned the
    hole-in-the-wall for the death it exists to prevent.

    `doomed` -- death is REACHABLE -- is the wrong test for blaming an item, and getting that wrong
    is instructive: it condemned the shield for the KQ6 archer, the hole-in-the-wall for the
    labyrinth and LSL2's Matches for the volcano, which are precisely the items that SAVE you.
    Those machines all branch on the item and only one arm dies. `throwSkull` does not branch: every
    path reaches state 24, which arms the ceiling again.

    So the question is co-reachability, not reachability. A state survives if any of its paths
    does, and a path survives when it EXITS the room, or ends the machine without handing off to
    something unavoidable, or moves to a state that survives. Cycles resolve to "does not survive"
    by starting pessimistic and only ever adding survivors -- a loop with no way out is exactly the
    timer that kills you.

    PERMISSIVE where we cannot see: a machine with no states at all (a dropped competitor)
    contributes survival, because "we did not learn what happens" must not become "you die here" --
    the same rule `death_traps` states for opaque conjuncts.

    ...with ONE exception, and it is the difference between catching KQ6's skull and not. Running
    off the end of the state graph normally means the machine finished, which is safe. But our
    graph ELIDES states that carry no effect we track, and an arming is not an effect: `throwSkull`
    is modelled as `st23 -> JUMP 25` with a max state of 24, so state 24,
    whose entire body is `(gCurRoom setScript: sqwishEm 0 1)`, is unreachable in our graph and the
    machine reads as survivable. It is not; that state is the crushing ceiling being re-armed.

    So for a machine that DEMONSTRABLY hands off to something unavoidable -- we know it from
    `entry_armers`, which does not depend on state reachability -- falling off the end is not
    evidence of survival, and we decline to call it safe. That is still the conservative direction
    for the machine's own claim: the only machines it can affect are ones already known to arm a
    death."""
    states = info.get("states") or {}
    if not states:
        return True
    inst = info["inst"]
    known = _armer_knowns(info)

    def _lethal_handoff(K):
        """The deaths this state really starts -- an arming whose own guard this machine's
        register contradicts is not one of them."""
        return {m for m, g in (handoff.get((inst, K)) or {}).items()
                if m in unavoidable and not _ctr_contradicted(g, known)}

    hands_to_death = any(_lethal_handoff(K) for (a, K) in handoff if a == inst)
    safe, changed = set(), True
    while changed:
        changed = False
        for K, paths in states.items():
            if K in safe:
                continue
            # A state that hands the room's script slot to a death is not safe by ANY path: the
            # `setScript:` replaces whatever this machine would have done next.
            if _lethal_handoff(K):
                continue
            for (_g, _w, _gg, _c, tr) in paths:
                if tr and tr[0] == "DEATH":
                    continue
                if tr and tr[0] == "EXIT":
                    ok = True
                else:
                    nxt = _succ_state(K, tr)
                    ok = (nxt in safe) if (nxt is not None and nxt in states) \
                        else not hands_to_death
                if ok:
                    safe.add(K)
                    changed = True
                    break
    start = info.get("start", 0) if start is None else start
    return start not in states or start in safe


def death_traps(em, regs, dom):
    """`room -> [(req, alts), ...]` -- the ALTERNATIVE ways to leave a room whose arrival kills you.

    A room you cannot survive offers no exits, and SCI writes that as a race for one slot. A Script
    object holds exactly one `setScript:` slot, so whichever machine is set last is the one that
    runs, and a player action that grabs the room's slot cancels the timer that was in it. KQ6's
    crushing ceiling is the pure case:

        rm420 walkIn  (9  (global2 setScript: sqwishEm))       ; arrival -> the ceiling comes down
        rm420 theGears doVerb 39 -> (global2 setScript: useBrick)   ; jam it: needs the brick
        rm420 theGears doVerb 51 -> (global2 setScript: throwSkull) ; needs the skull, and ENDS
                                    (global2 setScript: sqwishEm 0 1)  ; ...by dying anyway

    So the slot alone is not enough -- `throwSkull` takes it and hands it straight back to the
    death. An ESCAPE is a competitor from which the death is NOT reachable, following the arming
    graph the machines already record in `entry_armers`. That distinction is the whole rule: with it
    the brick is required to leave rm420 and the skull is not.

    Returns a DISJUNCTION per room, since any one of these gets you out:
      * one alternative per escape (its items), and
      * one per register the death CONDITION pins, requiring the complement -- rm411's collapsing
        floor kills you only while the minotaur lives (`(if (proc913_0 1) <corridor> else
        (setScript: dieAlready))`), so leaving needs flag 1 set.
    Empty when the death is unconditional and no escape was found: refusing to model it is the
    permissive answer, and blocking every exit on a non-observation is how you invent a softlock."""
    out = {}
    for room, infos in _trap_rooms(em).items():
        arms, fatal, doomed, _handoff = _trap_graph(infos)
        rows = []
        for info in infos:
            if info["inst"] not in fatal:
                continue
            slots = {r for r in (info.get("entry_recv") or ()) if r}
            if not slots:
                continue                           # not slot-armed -> no competitor story
            esc = []
            for other in infos:
                if other["inst"] in doomed or other["inst"] == info["inst"]:
                    continue
                for j, (_k, g) in enumerate(other["entries"]):
                    recv = (other.get("entry_recv") or [None] * (j + 1))[j] \
                        if j < len(other.get("entry_recv") or ()) else None
                    items = _own_positive(g) if g is not None else set()
                    if recv in slots and items:
                        esc.append(frozenset(items))
            # The death fires if ANY entry does, so surviving means EVERY entry is false -- and we
            # may only say that when we can read them all. An OPAQUE conjunct makes an entry
            # NARROWER than what we can see, so negating what we can see over-restricts, and
            # "we do not know when this fires" must never become "you die here". KQ4 is the
            # warning: the ogre's `grabbed` is gated on opaques, and negating its readable half
            # demanded the Axe to walk out of four ordinary rooms. Two cases are decidable:
            ents = list(info["entries"])
            if any(g is None for _k, g in ents):
                #  (a) some arming is UNCONDITIONAL, so the death is certain and only an escape
                #      helps. KQ6's ceiling: `walkIn` state 9 arms `sqwishEm` with no guard.
                rows.extend(({}, (a,)) for a in esc)
            elif len(ents) == 1 and not _has_opaque(ents[0][1]):
                #  (b) one arming, fully modelled, so its negation is exactly the way to survive --
                #      a disjunction over its conjuncts, since falsifying any one is enough.
                g = ents[0][1]
                rows.extend(({}, (a,)) for a in esc)
                rows.extend(({}, (frozenset({it}),)) for it in _own_negative(g))
                # The NECESSARY reading, not the flat one. `guard_reqs` reports every comparison it
                # can see, which is right for "what values may this edge be crossed at" and wrong
                # for composing a guard into another -- the same lesson KQ4's whale taught, where
                # the flat reading of a disjunction demanded both its arms. Negating the flat
                # reading of a big `not (or prev==a prev==b ...)` left KQ6's rm480 -> rm490 needing
                # `prev == 490` to reach rm490, so the scarf's own source became unreachable and the
                # scarf stopped being a softlock at all.
                sreq = structural_reqs(g, regs, dom)
                # ...but a register the trap room's OWN machinery writes is the trap's CLOCK, not
                # an escape lever. The complement row asserts "hold the register at another value
                # and the death never fires" -- true for PLOT state written elsewhere (KQ4's dawn
                # is Room82's to bring), and false for a value the room's machines advance on
                # their own: the walk would 'escape' the whale by standing in the state the timer
                # is actively leaving. KQ4's whale taught this the day room locals were lowered
                # into visibility -- the sneeze timer's states pinned the death, their complement
                # priced free, and the feather stopped being required.
                clock = {gi for i2 in infos for _K, paths in i2["states"].items()
                         for p in paths for (gi, _v) in p[1]}
                for R, vs in sreq.items():
                    if R in clock:
                        continue
                    d = dom.get(R)
                    if vs and d and set(vs) < set(d):
                        rows.append(({R: set(d) - set(vs)}, (frozenset(),)))
        if rows:
            out[room] = rows
    return out


def entry_reqs(info, regs, dom=None):
    """State K -> {register: allowed values} that EVERY entry reaching K establishes.

    The REGISTER twin of `entry_alts`, and deliberately the opposite composition. Items are a
    DISJUNCTION -- arm the machine any way you can, so holding one alternative suffices. A
    register requirement is a MUST: it may be carried onto the exit only if every way of arming
    the machine pins it, because a single unconstrained entry means the machine can be reached
    with the register at any value (the same soundness rule `_build_product` applies to ordered
    writes).

    Without this the exit edge inherited its entry's ITEM gates but silently dropped its FLAG
    gates -- so a cutscene armed only while a flag is clear (KQ6's sacred-water rm350->rm370,
    armed only when flag 174 is still 0) came out a free walk.

    Read with `structural_reqs`, the NECESSARY reading, because carrying an entry onto an exit is
    COMPOSING one guard into another -- the third place that distinction has mattered and the same
    lesson KQ4's whale taught (see `structural_reqs`, and `death_traps` case (b)). Flat, a
    disjunction of alternative armings reads as a conjunction of all their conditions: once an
    object's cast condition became a real disjunction, KQ6's `gates` was `arrived from rm490 OR
    NOT arrived from rm490` -- a tautology -- and the flat read turned it into a requirement to
    have already been in rm490 to reach rm490, which strands the red scarf behind its own door."""
    from compile import _ctr_holds, _lreg_test
    reach = _entry_reach_walk_of(info)
    lregs = info.get("local_regs") or {}
    per = []
    for (seen, eg, loc) in reach:
        per.append((seen, loc, {R: v for R, v in structural_reqs(eg, regs, dom).items() if v}))

    def _consistent(loc, guard):
        """Could an arming carrying `loc` have produced a path guarded by `guard`?

        One machine can serve several exits, chosen by the `register` its arming passed --
        KQ6's `walkOut` leaves to the surface when armed with 1 (behind the minotaur flag) and
        back into the maze when armed with 0. Both armings reach the same STATE, so a per-state
        answer intersects them to nothing and the gated escape reads as free. The exit's own
        guard says which arming it belongs to, so honour it. A lowered own-script room local
        (`local_regs`) is the same question in register spelling."""
        for a in (guard or ()):
            if isinstance(a, tuple) and a and a[0] == "CTR" and a[1] in loc \
                    and not _ctr_holds(a, loc):
                return False
            if _lreg_test(a, lregs, loc) is False:
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


def entry_musts(info):
    """State K -> the items you must be holding to arm this machine at all, by ANY route.

    `entry_alts` is the DNF of ways in; an item you cannot avoid is one that appears in every
    alternative, which is exactly `blocked(alts, {item})`. Stated as a set so callers that need
    the items rather than the yes/no can have them.

    What it is for: a cutscene's body usually carries no path condition at all -- the decision was
    made where the machine was started -- so read alone its effects are free. KQ6's `lookInHole`
    writes `seenSecretLatch`, which is what eventually opens the minotaur's lair and so the only
    way out of the catacombs, and it is armed by clicking a hole that exists only because you
    carried the hole-in-the-wall in and put it up. Its sibling `getTheHole` hands item 18 straight
    back, which is not the labyrinth GIVING you the hole.

    The reading inside one entry is `_own_positive`, inherited from `entry_alts` and deliberately
    the same one `edge_meta`/`blocked` have always used to gate an EXIT on its machine's arming: a
    positive mention of own(X) anywhere in the guard is evidence the action presupposes X. That is
    a mention, not a proof, so it can over-state -- which is why it is intersected over every
    alternative, and why the consumers that subtract on it (a source, a register's cost) keep the
    room or the write whenever ANY other site is free."""
    ea = entry_alts(info)
    return {K: (frozenset(set.intersection(*[set(a) for a in alts])) if alts else frozenset())
            for K, alts in ea.items()}


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
        er = entry_reqs(info, regs, dom)
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
                    for R, vals in (list(sm.at(K, g).items()) + list(chain.items())
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
        self._reob, self._rw, self._after, self._avoid = {}, {}, {}, {}
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

        def cheapest(key, cost):
            """Record what this write costs, keeping the CHEAPEST route when a room has several.

            Same composition `_reg_cost`/`value_cost` already apply across rooms -- you may make
            the register take the value whichever way suits you, so the requirement is the
            intersection. Per room it used to be first-writer-wins, which is arbitrary in a room
            where one script gates the write and another does not."""
            cost = frozenset(cost)
            self._inroom_own[key] = (self._inroom_own[key] & cost
                                     if key in self._inroom_own else cost)
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
                cheapest((gi, room, v), _own_positive(g))
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
                    cheapest((gi, room, v), ())
        self._rstep = {R: defaultdict(set) for R in self.regs}
        # ...and here, the one consumer an always-live scope is lifted FOR: what its action makes
        # true, and what that costs. `cheapest` below is where "mixing the paint costs the Styx
        # water" enters the model.
        for info in all_machines(em):
            entries = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            emust = entry_musts(info)
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
                        # ...and the write's PRECONDITIONS either way. Learning that a write is an
                        # ordered transition says nothing about what it costs, but `_rstep` recorded
                        # only the ordering, so an ordered write became free: KQ6's tapestry sets
                        # `hiddenDoorOpen` -- the secret door to the minotaur's lair -- and every
                        # arming of that cutscene pins the same flag, so the write went to `_rstep`
                        # and the hole-in-the-wall it depends on was dropped on the floor.
                        #
                        # A write inside a cutscene costs whatever ARMING the cutscene costs, too
                        # -- see `entry_musts`. The path condition inside a `changeState` body is
                        # usually empty, the decision having been made where the machine was
                        # started, so reading only that made every cutscene effect free.
                        cheapest((gi, info["room"], v),
                                 _own_positive(g) | emust.get(K, frozenset()))
        self._joints = []
        self._apply_death_traps()
        self._own_fixpoint()
        # Projections = one per register, PLUS the few joints the death traps ask for. See
        # _trap_joints: `self.regs` stays scalar because everything else iterates it expecting a
        # register, and only the four reachability walks look at `self.proj`.
        self.proj = list(self.regs) + list(self._joints)
        self._pstates = {R: self._walk(R, frozenset()) for R in self.proj}

    def _trap_joints(self, traps, dom):
        """The register TUPLES a death trap needs evaluated together.

        Negating a conjunction gives a disjunction, so a trap whose death condition is
        `prev == 435 AND minotaur alive` becomes two ALTERNATIVE ways out -- and per-register
        projections let each one through in the projection that cannot see the other. KQ6's dark
        room is exactly that: in the prevRoom projection the flag alternative is unconstrained, in
        the flag projection the prevRoom one is, so the trap never bites and the tinderbox you must
        light to survive the fall never looks required.

        Self-selecting, which is what keeps this from being "promote everything": the pair comes
        from the trap that needs it, and a game with no such trap gets no joints at all (LSL2, KQ4
        and every other title in the corpus). Bounded twice over -- by how many trap rooms name two
        or more registers, and by the size of the product -- because a joint projection is the
        expensive kind."""
        want, seen = [], set()
        for room in sorted(traps):
            named = tuple(sorted({R for (req, _alts) in traps[room] for R in req}))
            if len(named) < 2 or named in seen:
                continue
            size = 1
            for R in named:
                size *= max(1, len(dom.get(R) or (0,)))
            if size > 4000 or len(want) >= 8:
                continue                          # a joint is the expensive projection; bound it
            seen.add(named)
            want.append(named)
        return want

    def _apply_death_traps(self):
        """Conjoin `death_traps`' disjunction onto every way OUT of a room whose arrival kills you.

        The rows are alternatives and each existing meta is an alternative, so the two cross: a
        crossing is possible when some (existing way) and some (way to survive) both hold."""
        dom = defaultdict(set)                     # values each register is ever given
        for R in self.regs:
            dom[R] |= {v for vs in (self._inroom.get(R) or {}).values() for v in vs}
            dom[R] |= {t for pairs in self._rstep[R].values() for (_f, t) in pairs}
            dom[R].add(0)                          # registers start at 0
        for metas in self._emeta.values():
            for (_req, sets, _alts) in metas:
                for R, v in sets.items():
                    if R in dom:
                        dom[R].add(v)
        traps = death_traps(self.em, self.regs, dom)
        self._joints = self._trap_joints(traps, dom)
        for room, rows in traps.items():
            for b in self.edges.get(room, ()):
                base = list(self._emeta.get((room, b)) or [self._FREE])
                out = []
                for (req, sets, alts) in base:
                    for (treq, talts) in rows:
                        r2 = dict(req)
                        for R, vals in treq.items():
                            r2[R] = (r2[R] & set(vals)) if R in r2 else set(vals)
                            if not r2[R]:
                                break
                        else:
                            out.append((r2, sets,
                                        tuple(a | t for a in alts for t in talts)))
                if out:
                    self._emeta[(room, b)] = out

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
        # ...and the ALWAYS-LIVE scopes, exactly as `_build_product` iterates them. A machine the
        # icon bar dispatches records its own cost through `cheapest` up there but was never a
        # source of register-chain DEPENDENCIES down here, so half of what that scope contributes
        # was landing: KQ6 mixes the magic paint from the inventory under
        # `own(spellBook) AND flag68 AND flag58 AND NOT flag22`, and the cost of "the paint is
        # mixed" came out as the spell book ALONE -- the Styx water and the mud, which are what
        # the teacup buys, were dropped on the floor. The rule this scope shipped under is
        # "effects AND THEIR COSTS"; a cost that cannot propagate along a chain is not the second
        # half of it. Inert on SCO0 titles, whose items live in script 0 and which therefore have
        # no global machines at all.
        for info in all_machines(self.em):
            sm = state_musts(info, self.regs)
            # ...and what ARMING the machine established. `state_musts` walks the machine's own
            # transitions and seeds each entry with nothing, so a decision made in the ENTRY GUARD
            # -- which is where a cutscene's preconditions almost always live -- reached no write.
            # This is the register twin of the `entry_musts` term `_build_product` already puts on
            # the ITEM side of the very same write, and it is composed exactly as `edge_meta`
            # composes it onto an EXIT: intersect, because both must hold.
            er = entry_reqs(info, self.regs)
            by_guard = er.get("_by_guard")
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi not in regs or (gi, info["room"], v) not in self._inroom_own:
                            continue
                        d = dict(sm.at(K, g))
                        inherited = by_guard(K, g) if by_guard else er.get(K, {})
                        for S, vs in list(inherited.items()):
                            if vs:
                                d[S] = (d[S] & vs) if S in d else set(vs)
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

    def _psucc(self, R, node, banned, commit=frozenset()):
        """Successors of a (room, value-of-R) node in projection R. `banned` is a set of items you
        do not hold, so edges needing them are false -- the ITEM dimension of gate-awareness, and
        what the old `_sealed` heuristic crudely approximated: you cannot use the parachute to
        walk back to the parachute.

        `commit` reverses the direction of soundness for the registers it names, and exists for
        the PLACEMENT question only. Detection over-approximates movement (in-room writes are
        optional successors) so it can never miss a stranding; a placement proof must not CREDIT
        movement the game does not have, or "the player can walk back and comply" is asserted of a
        player who cannot. The one class of write that can be committed exactly is the
        UNCONDITIONAL entry write -- `em.init_writes`, unconditional by construction (a guarded
        init write goes to `init_seq` instead): entering the room forces the value, so a state
        that carries the old value past that door does not exist in play. For a register in
        `commit`, crossing into such a room arrives AT the written value instead of keeping the
        carried one. Every detection caller leaves `commit` empty and is bit-for-bit unchanged."""
        if isinstance(R, tuple):
            return self._psucc_joint(R, node, banned, commit)
        r, st = node
        out = {(r, v) for v in self._inroom[R].get(r, ())
               if not (banned and self._inroom_own.get((R, r, v), frozenset()) & banned)}
        # ...plus writes the game only makes FROM a particular value of R -- see _build_product.
        # Same item cost as any other write: knowing WHEN the game makes it does not make it free.
        out |= {(r, to) for (frm, to) in self._rstep[R].get(r, ()) if frm == st
                and not (banned and self._inroom_own.get((R, r, to), frozenset()) & banned)}
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                need = req.get(R)
                if need is not None and st not in need:
                    continue                      # guard forbids this move at this value of R
                if banned and blocked(alts, banned):
                    continue                      # every way through needs a banned item
                if self._reg_unreachable(req, banned):
                    continue                      # a register it needs can never reach that value
                arrive = sets.get(R, st)
                if R in commit:
                    # the destination's own unconditional entry write wins over anything carried
                    # or set in transit -- init runs LAST on the way in.
                    arrive = self.em.init_writes.get(b, {}).get(R, arrive)
                out.add((b, arrive))
        return out

    def _psucc_joint(self, Rs, node, banned, commit=frozenset()):
        """`_psucc` over a TUPLE of registers tracked together -- see `_trap_joints`.

        Same rules, one value per register (`commit` included -- see `_psucc` for its contract).
        Deliberately a separate body rather than a generalised
        one: the scalar path is walked millions of times and every corpus baseline is pinned to it,
        so it stays untouched."""
        r, st = node
        out = set()
        for i, Ri in enumerate(Rs):
            for v in self._inroom[Ri].get(r, ()):
                if banned and self._inroom_own.get((Ri, r, v), frozenset()) & banned:
                    continue
                nv = list(st)
                nv[i] = v
                out.add((r, tuple(nv)))
            for (frm, to) in self._rstep[Ri].get(r, ()):
                if st[i] != frm or (banned and
                                    self._inroom_own.get((Ri, r, to), frozenset()) & banned):
                    continue
                nv = list(st)
                nv[i] = to
                out.add((r, tuple(nv)))
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                if any(req.get(Ri) is not None and st[i] not in req[Ri]
                       for i, Ri in enumerate(Rs)):
                    continue
                if banned and blocked(alts, banned):
                    continue
                if self._reg_unreachable(req, banned):
                    continue
                ivs = self.em.init_writes.get(b, {})
                out.add((b, tuple(ivs.get(Ri, sets.get(Ri, st[i])) if Ri in commit
                                  else sets.get(Ri, st[i]) for i, Ri in enumerate(Rs))))
        return out

    def _walk(self, R, banned, starts=None, commit=frozenset()):
        """Forward reachable (room, value) states in projection R."""
        if starts:
            seen = set(starts)
        else:
            # The start room's own unconditional entry write is as committed as any other room's:
            # the game runs its init before the player moves, so 0 is only the initial value of a
            # register the start room does not write.
            iv = self.em.init_writes.get(self.em.cfg.start_room, {})
            if isinstance(R, tuple):
                zero = tuple(iv.get(Ri, 0) if Ri in commit else 0 for Ri in R)
            else:
                zero = iv.get(R, 0) if R in commit else 0
            seen = {(self.em.cfg.start_room, zero)}
        q = list(seen)
        while q:
            u = q.pop()
            for v in self._psucc(R, u, banned, commit):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        return seen

    def reach_avoiding(self, rooms):
        """Rooms reachable from the start WITHOUT ever ENTERING `rooms` -- gate-aware, intersected
        over every projection. The room-pruning twin of `_reach_without` (which bans an ITEM).

        Gate-awareness is the whole point and the flat graph gives the opposite answer: KQ6's Realm
        of the Dead sits behind `flag14`, and rm580 is the ONLY room that writes it, so refusing
        rm580 makes the entire Realm unreachable -- while the guard-ignoring graph happily routes
        around rm580 and says the Realm is still there."""
        key = frozenset(rooms)
        if key in self._avoid:
            return self._avoid[key]
        out = None
        for R in self.proj:
            zero = tuple(0 for _ in R) if isinstance(R, tuple) else 0
            start = (self.em.cfg.start_room, zero)
            seen, q = {start}, [start]
            while q:
                u = q.pop()
                for v in self._psucc(R, u, frozenset()):
                    if v[0] in key or v in seen:
                        continue
                    seen.add(v)
                    q.append(v)
            got = {r for r, _ in seen}
            out = got if out is None else (out & got)
        self._avoid[key] = out if out is not None else set(self.reach_rooms)
        return self._avoid[key]

    def edge_strandings(self):
        """The shared core, minus the rows two existing rules already refute.

        FORCED, NOT MISSABLE -- the crossing ITSELF demands the unit, so nobody crosses without
        it and the crossing cannot strand it. The toll carry-in detector has stated this rule
        since it existed (`if Y in self.edge_demands(a, b): continue`); the edge detector never
        applied it to its own rows, which is why a guarded door kept "stranding" the very item
        its guard demands and `verify` could not see its own fix.

        UNHOLDABLE -- the crossing's demand EXCLUDES the item (`guards.unholdable_at`: a room
        cost, or an exchange over one counter), so nobody arrives holding it and there is nothing
        to lose. KQ6's castle is one of each: the short door's dress costs the Realm (so the
        handkerchief and skeleton key cannot be in hand there), and the long door's route rides
        the pawn chain (so the nightingale IS the brush). Their real boundaries -- the Realm exit
        for the carry-outs, the short door for the nightingale -- carry the real guards.

        GROUPS pass through untouched, twice over. `edge_demands` is the intersection over DNF
        alternatives, so a demanded group's members distribute across alternatives and never
        survive the intersection -- the filter could only ever fire on a group via a SINGLE
        member demanded outright, and MEASURED (2026-08-02) that fires exactly once across the
        corpus: LSL2's play-validated rm79->rm80 raft guard, which it deletes. That baseline is
        ruled untouchable, and a filter whose one observable effect is wrong stays off."""
        import guards as _G                    # module-level would be a cycle; resolved by now
        out = []
        drops = {}                             # (a, b) -> {item: why} -- a dropped row is never
        #   silent: `guard_specs` folds these into the spec's dropped_incompatible/dropped_why,
        #   which is where the castle-door tests pin the reasons.
        for e in super().edge_strandings():
            a, b = e["from_room"], e["to_room"]
            dem = self.edge_demands(a, b)
            why = {it: "the crossing itself demands it -- forced, not missable"
                   for it in e["items"] if it in dem}
            rest = set(e["items"]) - set(why)
            why.update(_G.unholdable_at(self, a, b, rest) if rest else {})
            if why:
                drops.setdefault((a, b), {}).update(why)
            items = [it for it in e["items"] if it not in why]
            if items or e["groups"]:
                out.append({**e, "items": items, "groups": e["groups"]})
        self._stranding_drops = drops
        return out

    def edge_demands(self, a, b):
        """Items the edge a->b ITSELF requires -- the NECESSARY reading.

        `_emeta` holds one row per way of making the move and each row's `alts` is a DNF of
        item-sets, so an item is genuinely required only if it appears in EVERY alternative of
        EVERY row. Anything weaker would read one arming's demand as the edge's."""
        rows = self._emeta.get((a, b))
        if not rows:
            return frozenset()
        need = None
        for (_req, _sets, alts) in rows:
            for alt in (alts or (frozenset(),)):
                need = frozenset(alt) if need is None else (need & alt)
        return need or frozenset()

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
        for R in self.proj:
            rooms = {r for r, _ in self._walk(R, ban)}
            out = rooms if out is None else (out & rooms)
        self._rw[ban] = out if out is not None else set(self.reach_rooms)
        return self._rw[ban]

    def _need_rooms(self, item):
        """Rooms where own(item) is actually FACED -- gate-aware. See _reach_without.

        Deliberately RAW with respect to disjunctions -- see `_unit_need_rooms`, which is where a
        single item stops counting a room its group already covers. Subtracting here instead
        emptied the GROUP's need as well (a group's need is the union over its members), and LSL2's
        glacier guard `(or has:30 has:31)` disappeared entirely."""
        return {R for R in super()._need_rooms(item) if R in self._reach_without(item)}

    def _unit_need_rooms(self, u):
        """Rooms a requirement UNIT is faced in.

        A GROUP keeps every room its members are faced in -- the group IS the requirement there.
        A SINGLE item drops the rooms where it is merely one alternative of a group, because you
        are not required to bring THAT member; the group unit already demands one of them. Without
        this a guard asks for every solution to a puzzle at once: KQ6's castle demanded the mint
        AND the peppermint, LSL2's glacier the Sand AND the Ashes."""
        raw = set().union(*(self._need_rooms(i) for i in u)) if u else set()
        if len(u) > 1:
            return raw
        it = next(iter(u))
        groups = self.disjunctive_groups()
        return {R for R in raw
                if not any(it in G and len(G) > 1 for G in groups.get(R, ()))}

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
        for R in self.proj:
            # For a JOINT projection the universe is the states you can actually BE in without the
            # item. `_pstates` is the UNBANNED walk, so it holds states you could only have reached
            # by already surviving WITH the item, and a backward walk starting from one of those
            # says the item is re-obtainable from a place you could never have stood. KQ6's dark
            # room is the case: lit, you walk on and eventually kill the minotaur, so
            # `(rm406, minotaur dead)` exists and reaches the pawn shop; unlit you die there.
            #
            # This is the more correct universe for EVERY projection, and it is applied only to the
            # joints deliberately. WIDENED TO SCALARS AND REVERTED 2026-08-01: measured, it moves
            # LSL2 (two Vine dangerous-sinks, a refused rm101->rm102 spec) and KQ4 (three
            # rm20/26/27->rm333 specs demanding item 21), and the USER RULED those verdicts
            # incorrect -- "anything that moves LSL2 and KQ4 is incorrect and should not be
            # relitigated". The direction of the error: a banned walk UNDER-approximates movement
            # (blocked() over-requires), and reobtainability read from an under-approximation
            # invents sinks. Do not widen this again; a trap that needs the tight universe must
            # come through a JOINT, which exists precisely to be judged tightly -- KQ6's catacombs
            # (the brick) is the standing case, see test_toll.
            states = self._walk(R, ban) if isinstance(R, tuple) else self._pstates[R]
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
        for R in self.proj:
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
        mg = getattr(self.em, "machine_gets", set())
        guards = [(a.guard, a.room) for a in self.em.ts.acqs
                  if a.item == item and (a.room, a.via, a.item) not in mg]
        guards += [(g, room) for room, script, it, g in self.em.handler_gets if it == item]
        # ...and a pickup the game performs inside a CUTSCENE, whose condition is on the way IN.
        # The flat walk sees `(gEgo get: N)` in a `changeState` body with no path condition at all,
        # so read alone every cutscene pickup looks unconditional and NOTHING is ever permanent.
        # KQ6's old lamp is the case: `rm520.init` only puts `theHuntersLamp` in the cast under
        # `((gInv at: 19) owner:) == gCurRoomNum`, and `getLamp` -- armed from that object's doVerb
        # -- is what actually hands it over. Trade the lamp to the peddler and he LEAVES (flag 12,
        # one writer, never cleared), so the destruction is final and this is the only place that
        # can know it. Entries are ALTERNATIVES, so the acquisition is location-gated only if every
        # one of them is; a machine with no entry contributes an unconditional acquisition, which is
        # the permissive answer.
        for info in self.em.machines:
            if not any(item in gg for paths in info["states"].values()
                       for (_g, _w, gg, _c, _tr) in paths):
                continue
            ents = [eg for (_seen, eg, _loc) in _entry_reach_walk_of(info)]
            guards.extend((eg, info["room"]) for eg in ents) if ents else \
                guards.append((None, info["room"]))
        dbg = frozenset(self.em.cfg.debug_globals)
        guards = [(g, r) for (g, r) in guards if not _debug_gated_guard(g, dbg)]
        # ...and the same for an acquisition you could only reach by arriving from somewhere that
        # cannot reach it. This list is re-derived from `ts.acqs` rather than read off `sources`,
        # so `build_maps`' filters do NOT apply to it and each one has to be repeated here -- the
        # recurring shape in this codebase, and the reason the skull's throw looked survivable:
        # rm470's developer warp contributes an unconditional acquisition, and one unconditional
        # alternative is all it takes to make a destruction look undoable.
        prev = prev_room_reg(self.em)
        guards = [(g, r) for (g, r) in guards if not _prev_impossible(g, r, prev, self.edges)]
        return bool(guards) and all(self._loc_required(g, item, r) for (g, r) in guards)

    def _groups(self):
        return {frozenset(g) for gs in self.disjunctive_groups().values() for g in gs}

    # Main: its handleEvent runs in EVERY room. Hardcoded, and legitimately so -- script 0 IS
    # Main in every SCI dialect, which is a fact about the format rather than about a game.
    #
    # ⚠️ THERE ARE TWO NOTIONS OF "ALWAYS-LIVE SCOPE" IN THIS CODEBASE AND THIS IS THE OLDER ONE.
    # The other is `opmodel.global_homed`, DERIVED from the item class table
    # (`vocab.inventory_scripts`), which covers SCI1's icon bar -- on KQ6 that is scripts
    # {84, 90, 96, 97, 101, 907, 915}. The two do not intersect and neither consults the other:
    #   * this one homes a scope's sinks to every room (`_sink_rooms` below) but is only ever
    #     script 0, so it says nothing about the icon bar;
    #   * `global_homed` homes its scope's REGISTER effects everywhere and deliberately drops its
    #     item transfers entirely, so no sink from it ever reaches `_sink_rooms` to begin with.
    # That is why the gap is currently inert rather than wrong. Unifying them is a REAL change
    # (an icon-bar sink would become visible for the first time) and is deliberately not part of
    # the cleanup pass -- see docs/KQ6-STATUS.md, known inconsistencies.
    GLOBAL_SCRIPTS = frozenset({0})

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

    NOWHERE = (-1, None)     # `(gEgo put: N)` with no destination -- SCI's owner = -1

    def destroying_sinks(self):
        """Consumptions admitted because the item goes NOWHERE, whatever else the clause does.

        The SECOND way into `dangerous_sinks`, and it exists because `pure_sinks`' arms-nothing test
        is a PROXY. What that test is really trying to say is "spending it here was the intended
        move"; what it actually asks is "does this clause do anything at all", and a TRADE answers
        yes. KQ6's old lamp is the counterexample:

            lamps::doVerb 5   (gEgo put: 19)        ; the old lamp goes nowhere...
                              (gEgo get: 25)        ; ...and you are handed a new one

        The `get:` in the same clause makes it non-pure, so the destruction was invisible -- and the
        peddler then LEAVES (`lampTradeScr.sc:192` sets flag 12, one writer, never cleared), so
        there is no second trade. Meanwhile the old lamp is what `rm580::init` demands to cast the
        rain spell instead of caging you: `(if (and (gEgo has: 19) (== global161 15)) makeRain else
        inTheCage)`.

        Deliberately narrow: only `put:` with NO destination. That is SCI's owner = -1, which no
        `owner == gCurRoomNum` acquisition can ever satisfy again, so the loss is a fact rather than
        an inference -- no re-obtainability reasoning is involved and none of `pure_sinks`' judgement
        is being second-guessed. A `put:` to a ROOM is a different question (the item is lying
        somewhere, and whether anything there can pick it up is a real question) and is left alone.

        The "was it the intended move" worry is answered by `dangerous_sinks` itself rather than
        here: an intended use does not leave the item still needed in a room you can still reach."""
        seen = {(sk["room"], sk["script"], sk["item"]) for sk in self.pure_sinks()}
        out = []
        for room, script, it, g, dest in self.em.handler_drops:
            if dest in self.NOWHERE and (room, script, it) not in seen:
                out.append({"room": room, "script": script, "item": it, "dest": dest})
        return out

    def fatal_uses(self):
        """USING an item somewhere that kills you: the dangerous ACTION, in its purest form.

        Not a stranding and not a sink -- nothing is stranded and nothing is spent, because you do
        not survive to notice. It is still the thing the tool exists to prevent. KQ6's crushing
        ceiling offers the player two things to do with the gears, and one of them is a trap that
        looks exactly like the solution:

            theGears doVerb 39 -> useBrick     ; jam them with the brick -- you live
            theGears doVerb 51 -> throwSkull   ; throw the skull in -- the gears eat it and
                                               ; state 24 arms `sqwishEm` again: you are crushed

        `sqwishEm` is armed `0 1`, and its register only chooses whether one extra line is spoken
        (`(if register (say: ...) else (self cue:))`); both arms fall through to `(proc0_1 9)`,
        which is KQ6's imperative death proc. So there is no register value, no branch and no
        timing under which throwing the skull works.

        **Deaths are IN SCOPE, and the reasoning that says otherwise is the trap.** "You die, so you
        restore, so the item was never really lost" is true and irrelevant -- the player still spent
        a real attempt on a move the game invited them to make, and a tool that can see the move is
        fatal and says nothing is failing at its job. Recording that here because I talked myself
        out of this exact finding once, on exactly that argument.

        Derived, with no room or item named: an item appears here when some entry that requires
        holding it arms a machine that cannot be survived. "Cannot be survived" is `_survivable`,
        NOT `_trap_graph`'s `doomed` -- doomed means death is REACHABLE, and using it here condemned
        the shield for the KQ6 archer, the hole-in-the-wall for the labyrinth and LSL2's Matches for
        the volcano, i.e. exactly the items that keep you alive. Those machines branch on the item;
        this one does not.

        The complement of `death_traps`, which asks the same graph for the machines that are NOT
        doomed. That is why the brick is a REQUIREMENT to leave rm420 and the skull is a HAZARD in
        it, from one arming graph and one death set."""
        out, seen = [], set()
        for room, infos in _trap_rooms(self.em).items():
            if room not in self.reach_rooms:
                continue
            _arms, _fatal, doomed, handoff = _trap_graph(infos)
            unavoidable = {i["inst"] for i in infos
                           if i["inst"] in doomed and not _survivable(i, doomed, handoff)}
            # ...and settle the mutual dependency the same way `_trap_graph` settles `doomed`: a
            # state that hands off to a machine we have just condemned is not an escape either.
            changed = True
            while changed:
                changed = False
                for i in infos:
                    if i["inst"] in unavoidable or i["inst"] not in doomed:
                        continue
                    if not _survivable(i, unavoidable, handoff):
                        unavoidable.add(i["inst"])
                        changed = True
            for info in infos:
                if info["inst"] not in doomed:
                    continue
                # PER ENTRY, because the state an arming enters at decides whether it is
                # survivable: LSL2's bore talks you to death from state 0 and is SHUT UP by
                # `(boreScript changeState: 10)`, which is what giving him the pamphlet does.
                lethal = [(K, g) for K, g in (info.get("entries") or ())
                          if not _survivable(info, unavoidable, handoff, start=K)]
                if not lethal:
                    continue
                # WHAT NO LETHAL ARMING AVOIDS -- `entry_musts` read over the fatal entries. An
                # item is the CAUSE of a death only if the death cannot happen without it; if some
                # other arming kills you just the same, holding it was incidental. KQ6's
                # `emptyHandedDeath` is the case and it is the exact inverse of the truth: one of
                # its armings is unconditional, and the hole-in-the-wall reaches it only through
                # the composed chain of PUTTING THE HOLE UP, which is the puzzle's solution. Blame
                # per entry and you condemn the item that exists to prevent the death.
                #
                # (`_own_required` inside each, for the usual reason: an item in one arm of an OR
                # is a way to arm this, not a thing you must hold.)
                blame = set.intersection(*[set(_own_required(g)) for _K, g in lethal])
                for it in blame:
                    if (it, room) not in seen:
                        seen.add((it, room))
                        out.append({"item": it, "room": room, "machine": info["inst"],
                                    "states": sorted(K for K, _g in lethal)})
        return out

    def dangerous_sinks(self):
        """Consumptions that COST you the game: the item is still needed somewhere you can still
        reach, and once wasted it cannot be re-obtained. The action-shaped sibling of a room-gate
        stranding -- nothing about it is a movement edge, so `edge_strandings` cannot see it.

        LSL2: rm63 `apply rejuvenator to bolt` (-5 points, and the bolt does NOT open) and rm81
        `drop rejuvenator` (-5) both destroy the bomb ingredient rm82 needs.

        Candidates come from two places, one danger test over both: `pure_sinks` (the clause
        accomplishes nothing) and `destroying_sinks` (the item goes NOWHERE, whatever else the
        clause accomplishes)."""
        uses = self.real_uses()
        out = []
        for sk in self.pure_sinks() + self.destroying_sinks():
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

        PRODUCTION SINCE 2026-08-02: `guards.guard_specs` consumes these rows into
        `register-write` remedies (hold the flip until the sealed items are in hand), so the
        snapshot's spec/placement surface carries them; `test_scopes` Part 7 (LSL2) and
        `test_toll.test_register_strandings_is_degenerate_on_sci11` (KQ6) pin the rows
        themselves. The one KQ6 row -- flag 166, the `letter` -- is user-confirmed (oracle unit
        #19) and remeasured 2026-08-05 as BOTH castle routes' seal: the flip is the wedding
        fuse's expiry in rgCastle::doit, region-homed into every castle room by the rFlag
        lowering (same class as KQ4's day/night -- an adversarial-clock phase change).

        CAUSAL SINCE 2026-08-02 (was: degenerate on SCI1.1, 323 junk rows on KQ6 -- above all
        reg12, `prevRoom`, whose every crossing-write was read as an irreversible plot advance).
        The cure is the causality conjunct below, derived from the projection alone; the history
        and the diagnosis live in the promoted test's docstring.

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
                #
                # ...but THE FLIP MUST BE THE CAUSE, and that half was missing -- the SCI1.1
                # degeneracy (2026-08-02, was 323 rows on KQ6). A seed inside an already-sealed
                # region cannot reach the outside sources WHATEVER the register does, so blaming
                # the flip reported every register ever written inside the Realm -- and prevRoom,
                # which every crossing writes, once per room value. The causality test is the
                # same walk from the PRE-flip states at the same rooms: what the pre-flip player
                # could not reach either, the flip did not strand (that is the REGION's doing,
                # and the edge/toll detectors own it). A room only ever seen at `w` has no
                # pre-flip player, and its "flip" is an arrival -- an edge crossing wearing a
                # register, owned by edge_strandings. Derived from the projection alone; no
                # register is named.
                seed_rooms = {r for (r, _v) in seeds}
                rooms_after = {r for (r, _v) in after}
                # ...and THE QUANTIFIER over WHERE the flip happens must be EXISTENTIAL. The
                # union walk asks "does every flip strand?", invisible while registers had one
                # or two write sites -- the moment the rFlag lowering gave the wedding flag its
                # region-homed writer (every castle room, rm781 itself included), the union
                # reached the letter through the flip-at-the-source seed and the confirmed row
                # dissolved. A softlock needs only SOME reachable flip whose player can no
                # longer reach a source their pre-flip self could: the wedding starting while
                # you stand in the throne room strands the letter regardless of the flip that
                # could have happened in the letter's own room. Per-seed-room walks; the
                # arrival exclusion and the causality conjunct apply per room, same as before.
                per_room = {}
                def _flip_at(r):
                    if r not in per_room:
                        a = {q for (q, _v) in self._walk(R, frozenset(), starts={(r, w)})}
                        b0 = {(r2, v) for (r2, v) in states if r2 == r and v != w}
                        b = ({q for (q, _v) in self._walk(R, frozenset(), starts=b0)}
                             if b0 else None)       # None: no pre-flip player -> an arrival
                        per_room[r] = (a, b)
                    return per_room[r]
                if goal and not (goal & rooms_after):
                    continue                        # already unwinnable: a dead end, not a softlock
                for it in sorted(self.required):
                    srcs = self.sources.get(it, set())
                    if not srcs:
                        continue                    # never obtainable: not this detector's story
                    strand_at = []
                    for r in sorted(seed_rooms):
                        a, b = _flip_at(r)
                        if b is None:
                            continue                # an arrival, owned by edge_strandings
                        if (srcs & a) or not (srcs & b):
                            continue                # still obtainable, or never was from here
                        if goal and not (goal & a):
                            continue                # that flip is a dead end, not a softlock
                        if self.required[it] & a:
                            strand_at.append(r)
                    if strand_at:
                        ahead = self.required[it] & set().union(
                            *(_flip_at(r)[0] for r in strand_at))
                        out.append({"pattern": "register-flip-point-of-no-return",
                                    "register": R, "value": w, "item": it,
                                    "item_name": self.g.item_name(it),
                                    "flip_rooms": strand_at,
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

    # ---- mutually EXCLUSIVE items (the other half of disjunctive_groups) ----
    def _or_own_sets(self):
        """room -> {frozenset(items)}: every `(or own(a) own(b) ...)` the model holds.

        Pure OR of positive own()s only. Anything mixed in (a register test, a negation) means
        the disjunction is about something else, so the set is not a statement about items."""
        out = defaultdict(set)

        def collect(g, room):
            def w(x):
                if isinstance(x, list):
                    for y in x:
                        w(y)
                elif isinstance(x, GOr):
                    if all(isinstance(k, Pred) and k.kind == "OWN" for k in x.kids):
                        fs = frozenset(k.var for k in x.kids)
                        if len(fs) > 1:
                            out[room].add(fs)
                    for k in x.kids:
                        w(k)
                elif isinstance(x, GAnd):
                    for k in x.kids:
                        w(k)
                elif isinstance(x, GNot):
                    w(x.kid)
            w(g)

        for info in self.em.machines:
            for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                collect(eg, info["room"])
            for _K, paths in info["states"].items():
                for (g, _w, _gg, _c, _tr) in paths:
                    collect(g, info["room"])
        for e in list(self.em.ts.edges) + list(self.em.ts.cs_edges):
            collect(e.guard, e.src)
        for a in self.em.ts.acqs:
            collect(a.guard, a.room)
        return out

    def exchange_slots(self):
        """Item sets at most ONE member of which you can be HOLDING -- `[(frozenset, room)]`.

        The twin of `disjunctive_groups`: that one finds items the game accepts as alternatives to
        each other, this one finds items the game will not let you have at the same time. Both are
        reasons a guard must stop reading a set of item literals as a shopping list.

        KQ6's pawn shop is the case, and it is a chain three trades long: the mechanical
        nightingale buys the flute, the flute buys the tinderbox, the tinderbox buys the paint
        brush. So the brush that paints the castle's magic door IS the nightingale, and a guard on
        that door cannot demand both.

        THREE facts, each already in the model and none sufficient alone:

        1. A MENU -- one `get:` statement whose item is chosen at run time from a fixed set
           (`vocab.item_menus`). One statement moves one item, so the set is a choice. This alone
           does not stop you coming back for a second.
        2. ONE COUNTER -- every member's sole source is the same room, and that room also DROPS
           every member. So there is no other supply, and the supply takes members back. This is
           why "sole" is not a hedge: a member obtainable elsewhere could be held alongside
           another, and the exclusion would be false.
        3. A REFUSAL -- that room guards on `(or own(a) own(b) ...)` over exactly the menu set:
           the shopkeeper declining to deal while you already hold one. This is the coupling that
           1 and 2 cannot supply, and it is only evidence because it names EXACTLY a menu --
           MEASURED, KQ6 has 13 OR-of-own guard sets and 12 of them mean "show him anything"
           (one is eight unrelated items), so the refusal alone would over-group wildly.

        Inert wherever a game has no runtime-selected transfer: LSL2, KQ4 and the Dagger of Amon
        Ra have zero menu sites, so this returns [] and cannot move their output."""
        if hasattr(self, "_slots"):
            return self._slots
        menus = {S for (S, dest) in getattr(self.em.ts, "item_menus", ()) if dest == E.EGO}
        refusals = self._or_own_sets()
        out = []
        for S in sorted(menus, key=sorted):
            rooms = {r for it in S for r in self.sources.get(it, ())}
            if len(rooms) != 1:
                continue                       # not one counter: some member is sourced elsewhere
            R = next(iter(rooms))
            if not all(R in self.drops.get(it, ()) for it in S):
                continue                       # the counter does not take every member back
            if S not in refusals.get(R, ()):
                continue                       # the game never refuses a second one
            out.append((S, R))
        self._slots = out
        return out

    # ---- disjunctive requirement groups -------------------------------------
    def disjunctive_groups(self):
        """room -> {frozenset(items)}: sets that ALTERNATIVELY open the same gate.

        The per-item sweep is blind to these by construction -- no single member is required, so
        every member looks re-obtainable via its sibling. rm81 past the vine chasm is the case:
        `throw ash` (own 30) or `throw sand` (own 31) both arm the exit, and both sources sit
        back in the jungle you can never return to. Losing EITHER is survivable; losing BOTH is
        the softlock."""
        out = defaultdict(set)

        def offer(room, alts):
            uniq = set(alts)
            if len(uniq) < 2 or any(not x for x in uniq):
                return                # one alternative is free -> the gate is not a requirement
            if set.intersection(*map(set, uniq)):
                return                # a common item is needed -> per-item sweep already sees it
            out[room].add(frozenset().union(*uniq))

        for (a, b), variants in self._emeta.items():
            for (req, setv, alts) in variants:
                offer(a, alts)
        # A disjunction does not have to gate a MOVEMENT. SCI1.1's item-use idiom is a `doVerb`
        # switch on the item's message, so rival ways of solving one puzzle are sibling cases that
        # arm the SAME machine -- and that machine's ENTRIES are then exactly the DNF an edge's
        # `alts` would be. KQ6's genie is the case: `rm750`'s doVerb has `(63 put:23 ... 753)` and
        # `(67 put:31 ... 753)`, so `giveGenieMint` has entries [own(mint), own(peppermint)] and
        # the two are ALTERNATIVES -- the walkthroughs agree ("you can also defeat Shamir by giving
        # him some mint leaves"). Read off the entries rather than the edges, this is the same
        # shape and the same rule; reading only edges made every such puzzle look like a
        # conjunction of all its solutions.
        for info in self.em.machines:
            ents = list(info.get("entries", ())) + list(info.get("init_entries", ()))
            if len(ents) < 2:
                continue
            offer(info["room"], tuple(frozenset(_own_positive(eg)) for _K, eg in ents))
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

    def _uses_in(self, item, rooms):
        """Everything using `item` in `rooms` does: `({(reg, value)}, items moved, exits)`.

        A use is a machine those rooms arm whose ENTRY presupposes the item -- `_own_positive`,
        the same reading `_build_product` prices a write with -- plus the handler forms of the
        same act. Machine BODIES are read whole: a cutscene decides at its entry and pays off
        several states later."""
        key = (item, frozenset(rooms))
        cached = getattr(self, "_uses", None)
        if cached is None:
            cached = self._uses = {}
        if key in cached:
            return cached[key]
        writes, moved, exits = set(), set(), False
        for info in self.em.machines:
            if info["room"] not in rooms:
                continue
            own = set()
            for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
                own |= _own_positive(eg)
            if item not in own:
                continue
            moved |= set(info.get("drops", ()))
            for _K, paths in info["states"].items():
                for (_g, w, _gg, _c, tr) in paths:
                    writes |= {(gi, v) for (gi, v) in w}
                    if tr and tr[0] == "EXIT":
                        exits = True
        for a in self.em.ts.acqs:
            if a.room in rooms and item in _own_positive(a.guard):
                moved.add(a.item)
        for room, _script, gi, v, g in self.em.handler_writes:
            if room in rooms and item in _own_positive(g):
                writes.add((gi, v))
        for room, _script, it, g in self.em.handler_gets:
            if room in rooms and item in _own_positive(g):
                moved.add(it)
        for room, _script, it, g, _dest in getattr(self.em, "handler_drops", ()):
            if room in rooms and item in _own_positive(g):
                moved.add(it)
        cached[key] = (writes, moved, exits)
        return cached[key]

    def _use_escapes(self, item, pocket):
        """Does using `item` inside `pocket` LEAVE A TRACE, or is it only a joke?

        The conjunct that separates a carry-in from a souvenir. A one-visit pocket is full of
        things the game lets you do with what you brought, and some of them are flavour: KQ6 lets
        you play Charon the flute and the mechanical nightingale while you wait for the ferry, and
        both scripts write NOTHING, move nothing and go nowhere. Demanding those at the entrance
        would be inventing a requirement out of a joke.

        Three traces, and the test is that there is one -- not where it ends up:
          1. it writes a register;
          2. it moves an item that is needed outside the pocket;
          3. it is a CROSSING. Paying Charon and holding up the mirror go somewhere, and movement
             you must make is not optional.

        ⚠️ (1) USED TO ASK WHERE THE REGISTER IS READ, and that qualifier was FITTED TO A WRONG
        ANSWER. It was justified by KQ6's gauntlet -- thrown down at the Lord of the Dead, writing
        a register only rm690 itself reads -- which I read out of the scripts as flavour worth two
        points. The user tested it: **you need the gauntlet, because without it the game refuses to
        show Death the mirror.** `lord::doVerb 13` is `(if local0 <brush-off> else holdUpMirror)`,
        `introScript` sets `local0 := 1` before handing you control, and the ONLY thing that clears
        it while you still have control is `issueChallenge` -- the gauntlet. So the challenge is
        the precondition of the pocket's only exit.

        We keep the gauntlet now, but on trace (1) -- an INCIDENTAL register write that merely
        picks which death message you get -- and not on the reason the game actually has. The real
        link runs through a room LOCAL, which we do not model at all; it is the third recorded
        instance of that gap (`liftTapestry`'s L1 on the catacombs latch, `huntersLamp`'s rm520
        approach-idiom `doit`). `test_toll` carries a RED assertion naming it so the verdict cannot
        look better founded than it is."""
        writes, moved, exits = self._uses_in(item, pocket)
        if exits:
            return "it is a crossing you cannot make later"
        if writes:
            R, v = min(writes)
            return f"it sets reg{R}:={v}, and that write outlives the use"
        for it in sorted(moved):
            if self.required.get(it, set()) - pocket:
                return f"it moves {self.g.item_name(it)}, which is needed outside"
        return None

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
                    if not self.sources.get(X):
                        continue                 # A TOLL YOU NEVER PICKED UP IS NOT A TOLL. An item
                        #   with no source anywhere is a CAPTURE GAP, not a one-way spend -- KQ6's
                        #   pawn-shop trades have no `get:` at all -- and reading one as a paid toll
                        #   invents a sealed pocket around whatever lies past the edge that mentions
                        #   it. Everything downstream (the carry-out rows, and the carry-in rows
                        #   below) is then reasoning about a room the player can walk back into.
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
                                # the sealing register, exactly as the carry-in rows carry it: a
                                # consumer judging the pocket's EXITS (the carry-out placement)
                                # needs the seal in its joint or every walk re-enters freely.
                                "toll_reg": X[1] if isinstance(X, tuple) else None,
                                "toll_edge": [a, b], "pocket": sorted(pocket),
                                "source_rooms": sorted(srcs)})
                # ...AND THE OTHER DIRECTION, which is the same fact read the other way round. A
                # pocket you may enter once strands what you obtain inside and need outside -- and
                # equally what you must USE inside and can only obtain OUTSIDE. Every conjunct
                # below is the mirror of one above; the fourth has no mirror because it has no
                # counterpart in the carry-out case, where merely HOLDING the item on the way out
                # is the whole requirement.
                #
                # KQ6's teacup is the case. Its only source is a room outside the Realm of the
                # Dead; the Styx water is drawn at rm660, inside; the Realm admits you once
                # (flag 15, raised on arrival, never cleared); and you may walk in without it. Come
                # out with an empty cup and the magic paint can never be mixed.
                for Y in sorted(self.required):
                    if Y == X or not (self.required.get(Y, set()) & pocket):
                        continue                 # not used in there
                    srcs = self.sources.get(Y, set())
                    if not srcs or (srcs & pocket):
                        continue                 # no source, or obtainable INSIDE -> fetch it there
                    if Y in self.edge_demands(a, b):
                        continue                 # the crossing itself demands it -> forced, not
                                                 # missable (the mirror of `_pocket_leavable`)
                    why = self._use_escapes(Y, pocket)
                    if not why:
                        continue                 # what it does in there, the pocket keeps
                    k = ("in", Y, a, b)
                    if k in seen:
                        continue
                    seen.add(k)
                    out.append({"pattern": "one-visit-pocket-carry-in", "item": Y,
                                "item_name": self.g.item_name(Y),
                                "toll_item": None if isinstance(X, tuple) else X,
                                "toll_item_name": (f"flag{X[1]}" if isinstance(X, tuple)
                                                   else self.g.item_name(X)),
                                # the REGISTER that seals the pocket, kept as a number and not only
                                # as a label: it is what a consumer must put in a joint projection
                                # to see the pocket as one-visit at all. Without it every walk
                                # cheerfully re-enters and concludes you can go back for anything.
                                "toll_reg": X[1] if isinstance(X, tuple) else None,
                                "toll_edge": [a, b], "pocket": sorted(pocket),
                                "source_rooms": sorted(srcs),
                                "need_rooms": sorted(self.required[Y] & pocket),
                                "why": why})
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


_MODEL_MEMO = {}                       # in-process: key -> built model


def _model_cache_key(cfg, ir_path):
    """Identity of a BUILT MODEL: the config that shapes it, the IR it is built from, and the
    code that builds it.

    The code hash is the load-bearing part. A cached model is only sound while every module
    that participates in building or querying it is byte-identical to the one that produced
    the pickle -- otherwise an edit to a detector would be silently answered from a model built
    by the previous version, and the suite would gate on a stale analysis. So every non-test
    source file in this directory goes into the hash: touching any of them misses the cache and
    rebuilds. (Test files are excluded on purpose -- editing a test must not throw away the
    models it is about to read.)"""
    import hashlib
    here = os.path.dirname(os.path.abspath(__file__))
    h = hashlib.sha1()
    h.update(repr((cfg.name, cfg.src_dir, cfg.ir_path, cfg.resource_dir, cfg.start_room,
                   sorted(cfg.goal_rooms), tuple(cfg.death_signal),
                   sorted(cfg.debug_globals), repr(cfg.promote_registers))).encode())
    try:
        st = os.stat(ir_path)
        h.update(("%d:%d" % (st.st_size, st.st_mtime_ns)).encode())
    except OSError:
        return None
    for fn in sorted(os.listdir(here)):
        if fn.endswith(".py") and not fn.startswith("test_"):
            with open(os.path.join(here, fn), "rb") as f:
                h.update(f.read())
    return h.hexdigest()


# Module-level state a BUILD installs and a QUERY later reads. It must travel with a cached
# model or the model answers against whichever game was loaded last. This list is the cache's
# one fragile seam -- it is a hand-maintained mirror of every `global` a build assigns -- so
# `test_model_cache.py` pins it by diffing a cache-hit's state against a fresh build's, which
# is what caught `_IPROP_SPEC` missing here (four KQ4 resource-exhaustion checks went empty).
# Derived from `grep -rn "^\s*global [_A-Z]" src/`: extract's vocabulary (one `global`
# statement, seven names), extract's doVerb parameter, and missability's item-property spec.
_BUILD_STATE = (("extract", ("_VOCAB", "_IPROPS", "_EGO", "_CURROOM", "_ITEM_MSG", "_ONEOF",
                             "_MENUS", "_VERB_PARAM")),
                ("missability", ("_IPROP_SPEC",)))


def _vocab_state():
    """The module-level state a build INSTALLS, so a cached model can restore it.

    Several query paths read this state at ANSWER time -- `guards.sink_survival_carryins`
    reads `extract._CURROOM`, `resource_exhaustion` reads `_IPROP_SPEC` -- so a model handed
    back without it answers against another game. `vocab.BOOL_GLOBALS` is snapshotted rather
    than re-derived because it is a byproduct of the lowering passes, and restoring it also
    fixes a bug that predates caching: it only ever GREW, so loading LSL2 after KQ6 left
    KQ6's synthetic registers in the set (measured elsewhere at 57 KQ4 / 28 LSL2 registers
    wrongly marked boolean)."""
    import importlib
    return ({mod: {k: getattr(importlib.import_module(mod), k, None) for k in names}
             for mod, names in _BUILD_STATE},
            set(vocab.BOOL_GLOBALS))


def _restore_vocab_state(state):
    import importlib
    mods, bools = state
    for mod, names in mods.items():
        m = importlib.import_module(mod)
        for k, v in names.items():
            setattr(m, k, v)
    vocab.BOOL_GLOBALS.clear()
    vocab.BOOL_GLOBALS.update(bools)


class DeathSignal:
    """`(global, value)` -> "is this write a death", as a PICKLABLE callable.

    A closure would be the obvious spelling and was the original one, but the emitter and the
    MachineBuilder both hold this object, so a local lambda made the entire analysis model
    unpicklable -- and that is what blocked caching a built model between callers. `value`
    None means "any non-zero" (KQ4's global127 is a plain boolean set in 37 death rooms;
    LSL2 raises death as the magic constant `gCurrentStatus == 1001`)."""
    __slots__ = ("gi", "val")

    def __init__(self, gi, val):
        self.gi, self.val = gi, val

    def __call__(self, gi, v):
        return gi == self.gi and (v == self.val if self.val is not None else bool(v))

    def __eq__(self, other):
        return (isinstance(other, DeathSignal)
                and (self.gi, self.val) == (other.gi, other.val))

    def __hash__(self):
        return hash((self.gi, self.val))


_UNSET = object()      # "argument omitted", which is NOT the same request as `cfg=None`


def load(cfg=_UNSET, ir_path=None, cache=True):
    """The analysed model for `cfg`, built once and REUSED.

    Building is expensive (measured: LSL2 27s, KQ4 78s, KQ6 171s) and the suite asks for the
    same three models 26 times across six processes, which was ~96% of a 39-minute run. The
    model is pure derived data, so it is cached: in-process first, then a pickle under
    `build/.model_cache` keyed by `_model_cache_key` (config + IR + the hash of every
    non-test source file here). Round-tripping is ~164x faster than rebuilding.

    Set `cache=False`, or `SOFTLOCK_NO_MODEL_CACHE=1` in the environment, to force a build --
    and note the cache is per (cfg, IR, code), so a source edit invalidates every entry by
    construction rather than by anyone remembering to clear it.

    An EXPLICIT `cfg=None` is an error, while omitting the argument still means "the active
    config". The two are not the same request: `config.sweep_config(name)` returns None for a
    title with no IR built, and `cfg or config.ACTIVE` silently turned that into a full,
    confident analysis of whatever was active -- measured, five swept titles each reported
    LSL2's rooms, items and softlock count under their own name."""
    if cfg is _UNSET:
        cfg = config.ACTIVE
    elif cfg is None:
        raise ValueError(
            "load(cfg=None): no config. `config.sweep_config(name)` returns None when that "
            "title has no IR under build/sweep/<name>/ -- build it first, or pass a real "
            "GameConfig. (Omit the argument entirely to analyse config.ACTIVE.)")
    ir_path = ir_path or cfg.ir_path
    use_cache = cache and not os.environ.get("SOFTLOCK_NO_MODEL_CACHE")
    key = _model_cache_key(cfg, ir_path) if use_cache else None
    if key is None:
        return _build(cfg, ir_path)
    import pickle
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "build", ".model_cache", key + ".pkl")
    blob = _MODEL_MEMO.get(key)
    if blob is None and os.path.exists(path):
        try:
            with open(path, "rb") as f:
                blob = f.read()
            pickle.loads(blob)                     # reject a truncated/stale file here, not later
            _MODEL_MEMO[key] = blob
        except Exception:                          # noqa: BLE001 -- a bad pickle is not a
            blob = None                            # failure: fall through and rebuild
    if blob is None:
        model = _build(cfg, ir_path)
        blob = pickle.dumps((model, _vocab_state()), protocol=5)
        _MODEL_MEMO[key] = blob
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            tmp = path + ".%d.tmp" % os.getpid()   # atomic: parallel test processes race here
            with open(tmp, "wb") as f:
                f.write(blob)
            os.replace(tmp, path)
        except Exception:                          # noqa: BLE001 -- caching is an optimisation
            pass
        _restore_vocab_state(_vocab_state())
        return model
    # EVERY CALLER GETS ITS OWN COPY, which is why the memo holds bytes rather than the object.
    # `guards.apply_guards(s, specs)` mutates the model IN PLACE to build the guarded world it
    # verifies against (`s._emeta[key] = ...`, `s._pstates = ...`, and four `.clear()`s), so a
    # shared instance would hand the next caller a model with someone else's guards already
    # applied. Unpickling costs ~0.2s against a ~27-170s rebuild, so isolation is nearly free.
    model, state = pickle.loads(blob)
    _restore_vocab_state(state)
    return model


def _build(cfg, ir_path):
    # A BUILD OWNS ITS OWN BOOL_GLOBALS. The set is a module-level accumulator the lowering
    # passes add to, and it only ever grew: a process that loaded KQ6 and then KQ4 left KQ6's
    # synthetic registers in it, and since each game allocates its synthetic block from
    # `max_gi+1` the ranges overlap (KQ6 172..558 against KQ4's real 0..400), so registers of
    # the second game were read as boolean when they are nothing of the kind -- which widens a
    # `(!= gN 0)` into a hard `== 1` requirement and can invent a stranding. Clearing here
    # makes the set exactly this game's, which is also what lets a cached model restore a
    # clean one instead of freezing whatever contamination existed when it was built.
    vocab.BOOL_GLOBALS.clear()
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
        synth_base = V.lower_flags(ir, flags[0], flags[1])[0]
        # Keep the mapping back. Lowering is deliberately one-way for the ANALYSIS -- nothing
        # downstream should know what a "flag" is -- but a PATCH has to be written in the game's
        # own spelling, and a synthetic register has none. `guards.render_register` reverses it:
        # register R is flag `R - synth_base`, tested by the proc the derivation already named.
        ir.flag_synth_base = synth_base
        ir.flag_test_proc = next((n for n, op in flags[1].items() if op == "test"), None)
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
    # FIFTH store, BUILT AND STILL NOT WIRED after TWO measured rounds: a ROOM script's LOCAL
    # shared between that room's machines -- KQ6 rm690's local0, the gauntlet latch
    # (`vocab.derive_room_locals` / `lower_room_locals`, entry-reset via ir._room_local_resets ->
    # init_writes; rm690 derives exactly).
    #
    # THREE measured rounds, ONE blocker left:
    # ROUND 1 (2026-08-01): KQ4 whale items + KQ6 huntersLamp lost -> trap-clock rule and
    #   store-aware render_register landed on their own merits.
    # ROUND 2 (2026-08-02): still lost. Round 2's `_joints == []` lead was a red herring
    #   (`_joints` is [] on KQ4 stock too); the whale rows come from `joint_strandings` = the
    #   OCEAN GRID x monotone flags, and the grid died because the derivation lowered its data:
    #   `++`/`--` are Increment/Decrement nodes the taint missed (rm31's stepped cells), and
    #   rm31's local12 is `grid._counter_bound`'s CONST-LOCAL drown threshold (init-only writes).
    #   Both derivation fixes are IN (`derive_room_locals`), and with them KQ4 wired is
    #   byte-identical to stock -- whale, bridle, all five joint rows back.
    # ROUND 3 (2026-08-02): the LAST blocker, measured to a single boolean: KQ6's huntersLamp
    #   dies because `destroyed_is_permanent(19)` flips True->False. The lamp's acquisition
    #   entries come from `_entry_reach_walk_of(getLamp)`, and the walk threads machine-internal
    #   sequencing as CARRIED-LOCAL counters (`entry_locals`, CTR atoms in path guards, `c`
    #   writes). Lowering rm520's cross-object latches (locals 0-2 -- genuinely this gap's 2nd
    #   recorded instance) moves all three into register-land (Pred CMP atoms, `w` writes, no
    #   entry annotation), so the walk loses its internal resolution and the entry set weakens.
    # ROUND 4 (2026-08-02), WIRED: lowered OWN-SCRIPT registers now thread through the machine
    #   walks as counters keyed by the synthetic index (`Machine.local_regs`, `compile._lreg_test`,
    #   `_entry_reach_walk`), seeded from the declared reset (`ir._room_local_resets`) and
    #   overridden by the arming context's writes -- while the atoms and writes stay registers
    #   for every cross-scope consumer, which is the store's whole point. Pinned:
    #   `destroyed_is_permanent(huntersLamp)` True (test_kq6_ground_truth), the rm690 latch
    #   fixture in test_toll, and byte-identical LSL2/KQ4/Dagger surfaces.
    V.lower_room_locals(ir, V.derive_room_locals(ir, _X._room_numbers(ir)))
    _X.install_vocabulary(ir)
    V.lower_item_bit_flags(ir, V.derive_item_bit_flags(ir, _X._at_item), _X._at_item)
    # SIXTH container: a plain global used as a BIT-MASK WORD -- written `(|= gN $mask)`, read
    # by equality/bit-test -- with no accessor to key on. Same per-bit lowering as every flag
    # store. Measured corpus-wide: exactly one instance, KQ6's g161 (the Make-Rain readiness
    # word, the register half of the mists cage sorter); LSL2/KQ4/Dagger have zero mask-written
    # globals, so this is inert there by construction. LAST of the lowerings, deliberately:
    # ALLOCATION ORDER IS REGISTER IDENTITY (see lower_prop_flags), and a new store that
    # allocates mid-sequence renumbers every store after it -- measured: it took the skull's
    # item-bit registers (489/490) and test_scopes' pinned callback-scope check tripped on the
    # wrong store's writes.
    V.lower_mask_globals(ir, V.derive_mask_globals(ir))
    d_gi, d_val = sig[0], (sig[1] if len(sig) > 1 else None)
    is_death = DeathSignal(d_gi, d_val)
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
    # AN UNANCHORED GOAL IS A FAILURE, NOT A CLEAN BILL OF HEALTH. Every "is X still
    # required?" question is answered against goal reachability, so an empty goal set makes
    # `goal_reaching` false everywhere: every guarded item lands in `hopeless`, `required`
    # collapses, and the pipeline prints "softlocks: 0 items" for a game it never anchored.
    # The death signal already refuses to be silent about this (see the SystemExit above);
    # the goal is the other half of the same pair and was not symmetric.
    if not cfg.goal_rooms:
        raise SystemExit(
            "could not derive a goal room for %s, and config.goal_rooms is unset. Every "
            "requirement question is answered against goal reachability, so continuing "
            "would report zero softlocks for a game that was never anchored. See anchors.py: "
            "a goal is terminal, reachable and never fatal; where the ending shares its flag "
            "with death, the ending that TESTS WHAT YOU ACHIEVED is the win." % cfg.name)
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
