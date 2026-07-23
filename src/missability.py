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
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
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
    for room, it, prop, val, _g in getattr(em.ts, "item_prop_writes", ()):
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
    trap_items = hopeless - hopefuls

    required = defaultdict(set)
    # CONSUMPTION is a FALLBACK evidence source, not an additive one -- see the note where it is
    # applied, below. Collected separately so it can be weighed after all guard evidence is in.
    consumed_at = defaultdict(set)
    def req_item(it, room):
        if it not in trap_items:
            required[it].add(room)
    def req(guard, room):
        for it in _own_positive(guard):
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
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                for (gi, v) in w:
                    written.add(gi)
    return sorted(compared & written)


def asserts_eq(op, pol):
    """Does a `(reg, op, value, polarity)` atom assert `reg == value`?

    Both spellings do: `x == v`, and `not (x != v)`. The second matters because `(if (not gX)
    ...)` is SCI's way of writing "gX is 0" and `atom()` renders a bare global's truthiness as
    `CMP(gX, !=, 0)` -- which is how KQ4's day-only doors are gated.

    Shared deliberately: this test used to be spelled out separately in `required_values` and in
    `edge_meta.reqs`, and fixing one and not the other left the night gate parsed but toothless."""
    return (op == "==" and pol) or (op == "!=" and not pol)


def required_values(guard, reg):
    """Values of `reg` this guard REQUIRES (positive `== v`), or None if it doesn't constrain it.

    Only positive equalities are used. `!=` and the relational ops are deliberately ignored: they
    would need the value-partition abstraction to stay exact, and ignoring them is the PERMISSIVE
    direction (we never block movement the game allows).

    A NEGATED `!=` is a positive equality, though, and that is not a technicality: `(if (not gX)
    ...)` is how SCI writes "gX is 0", and `atom()` turns bare-global truthiness into
    `CMP(gX, !=, 0)`. KQ4's day-only doors are guarded exactly that way -- `(if (not global100)
    <open the door>)` -- so without this the night gate parsed fine and then constrained nothing."""
    vals = set()
    atoms = []
    _cmp_atoms(guard, atoms)
    for (r, op, v, pol) in atoms:
        if r == reg and asserts_eq(op, pol):
            vals.add(v)
    return vals or None


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
    succ = defaultdict(set)
    for K, paths in info["states"].items():
        for (g, w, gg, c, tr) in paths:
            if tr[0] == "ADVANCE":
                succ[K].add(K + 1)
            elif tr[0] == "JUMP":
                succ[K].add(tr[1])
            elif tr[0] == "SETSTATE":
                succ[K].add(tr[1] + 1)
    per_entry = []
    for K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
        seen, q = {K}, [K]
        while q:
            u = q.pop()
            for v in succ.get(u, ()):
                if v not in seen:
                    seen.add(v)
                    q.append(v)
        per_entry.append((seen, frozenset(_own_positive(eg))))
    out = {}
    for K in info["states"]:
        out[K] = tuple({owns for (seen, owns) in per_entry if K in seen})
    return out


def blocked(alts, banned):
    """Is an edge with these DNF alternatives blocked when `banned` items are unavailable?"""
    return bool(alts) and all(a & banned for a in alts)


def edge_meta(em, regs):
    """(a,b) -> [(req, sets, alts)] for the discovered gating `regs`.

    req  = {reg: {allowed values}}   from positive `== v` atoms on the edge's guard
    sets = {reg: value}              writes the edge performs on the way out
    alts = DNF tuple of item-sets    (see entry_alts / blocked)

    This is what makes movement GATE-AWARE. The guard-ignoring graph walks rm82 -> rm152 -> rm52
    and so welds the volcano to the airport (the mega-SCC that hid the Pamphlet stranding and
    produced the Airline_Ticket FP). But rm82 dumps you into rm152 having set gCurrentStatus to
    14/15 (bomb botched) while rm152's exit to rm52 REQUIRES 7 -- an impossible composition."""
    regset = set(regs)
    def reqs(guard):
        """One walk of the guard tree for ALL registers -- walking it once per register made
        edge_meta 19x slower than it needed to be."""
        atoms = []
        _cmp_atoms(guard, atoms)
        out = {}
        for (r, op, v, pol) in atoms:
            if r in regset and asserts_eq(op, pol):
                out.setdefault(r, set()).add(v)
        return out
    meta = defaultdict(list)
    for e in em.ts.edges:
        meta[(e.src, e.dst)].append((reqs(e.guard), {}, (frozenset(_own_positive(e.guard)),)))
    md = em.machine_delivered
    for e in em.ts.cs_edges:
        if (e.src, e.dst) in md:
            continue          # same newRoom the machine EXIT already carries, but WITHOUT its
        #                       guard -- keeping it shadows the real gate (rm57 -> rm58 needs the
        #                       ticket handed to the agent). build_maps applies this filter too.
        meta[(e.src, e.dst)].append((reqs(e.guard), {}, (frozenset(_own_positive(e.guard)),)))
    for info in em.machines:
        eo = entry_alts(info)
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    exit_own = frozenset(_own_positive(g))
                    alts = eo.get(K) or (frozenset(),)
                    sets = {gi: v for (gi, v) in w if gi in regset}
                    meta[(info["room"], tr[1])].append(
                        (reqs(g), sets, tuple(exit_own | a for a in alts)))
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
        self._pstates = {R: self._walk(R, frozenset()) for R in self.regs}

    _FREE = ({}, {}, (frozenset(),))

    def _psucc(self, R, node, banned):
        """Successors of a (room, value-of-R) node in projection R. `banned` is a set of items you
        do not hold, so edges needing them are false -- the ITEM dimension of gate-awareness, and
        what the old `_sealed` heuristic crudely approximated: you cannot use the parachute to
        walk back to the parachute."""
        r, st = node
        out = {(r, v) for v in self._inroom[R].get(r, ())}
        # ...plus writes the game only makes FROM a particular value of R -- see _build_product
        out |= {(r, to) for (frm, to) in self._rstep[R].get(r, ()) if frm == st}
        for b in self.edges.get(r, ()):
            for (req, sets, alts) in self._emeta.get((r, b), (self._FREE,)):
                need = req.get(R)
                if need is not None and st not in need:
                    continue                      # guard forbids this move at this value of R
                if banned and blocked(alts, banned):
                    continue                      # every way through needs a banned item
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
        return any(not alts or any(not alt for alt in alts)     # some alternative needs no item
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
        for room, it, prop, val, g in getattr(self.em.ts, "item_prop_writes", ()):
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
            can_get = backward({s for s in F if s[0] in srcs})
            # a reachable state at a required room, from which no source is reachable (cannot get
            # the item) but the goal still is (so it is the item that is missing, not a dead end).
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
    sig = tuple(cfg.death_signal) if cfg.death_signal else ()
    if not sig:
        found = V.derive_death(ir)
        if found:
            sig = found[0][0]
    if not sig:
        raise SystemExit("could not derive a death signal, and config.death_signal is unset. "
                         "Expected the Game subclass to test a global on the way to "
                         "restart:/restore:.")
    import dataclasses
    if not cfg.debug_globals:
        cfg = dataclasses.replace(cfg, debug_globals=frozenset(V.derive_debug(ir)))
    if not cfg.death_signal:
        cfg = dataclasses.replace(cfg, death_signal=sig)   # so reports show what was derived
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
