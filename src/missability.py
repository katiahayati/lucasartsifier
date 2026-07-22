"""Missability sweep on the JSON-IR / smv_emit3 front-end (the canonical one), NOT the stale
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
import smv_emit3 as E
from guard_ast import GAnd, GOr, GNot, Pred
from scc_core import tarjan_scc, reachable, SccReach

# item names are a reporting nicety; the IR JSON carries none, so keep a local map (LSL2). The
# ANALYSIS is fully on JSON-IR -- only these labels are game-specific.
_NAMES = {1:"Dollar_Bill",2:"Lottery_Ticket",3:"Cruise_Ticket",4:"Million_Dollar_Bill",
    5:"Swimsuit",6:"Wad_O_Dough",7:"Passport",8:"Grotesque_Gulp",9:"Sunscreen",10:"Onklunk",
    11:"Fruit",12:"Sewing_Kit",13:"Spinach_Dip",14:"Wig",15:"Bikini_Top",16:"Bikini_Bottom",
    17:"Knife",18:"Soap",19:"Matches",20:"Flower",21:"Hair_Rejuvenator",22:"Suitcase",
    23:"Airline_Ticket",24:"Parachute",25:"Bobby_Pin",26:"Pamphlet",27:"Airsick_Bag",
    28:"Stout_Stick",29:"Vine",30:"Ashes",31:"Sand"}


class _NameShim:
    def item_name(self, it):
        return _NAMES.get(it, f"item{it}")


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


def build_maps(em):
    """(edges, edge_kind, sources, drops, required, guard_required) from the JSON-IR OpEmitter.

    `guard_required` is `required` WITHOUT the consumption fallback -- only rooms where the game
    actually tests `has: X`. That is the evidence that an item ARMS something, which is a
    different question from where it is needed, and `real_uses` wants the former."""
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

    # DROP sites -- where an item can LEAVE your inventory. Declared since the first version but
    # never populated. Needed to place NEGATIVE guard literals: `!own(Spinach_Dip)` may only be
    # demanded where the dip can still be got rid of (rm131, `throw bread overboard`, +2 score).
    # Guarding it later would convert a death into a permanent wall.
    for room, script, it, g in getattr(em, "handler_drops", ()):
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
    # consuming an item in a HANDLER -- the Pamphlet handed to the bore on the plane (rm62) is a
    # Said-handler `put: 26 -1`, which the machine-body scan never sees. Held back; see below.
    for room, script, it, g in getattr(em, "handler_drops", ()):
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
        self.g = _NameShim()
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
        for room, script, gi, v, g in em.handler_writes:
            if gi in regset:
                self._inroom[gi][room].add(v)
        for info in em.machines:
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if gi in regset:
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
        for room, script, it, g in self.em.handler_drops:
            if script in self.GLOBAL_SCRIPTS:
                # Clause identity is (room, positive-owns), which pins a clause inside a small
                # room but COLLIDES badly in Main -- one giant script where unrelated clauses
                # share an own-set, so a real use elsewhere in Main masks a sink here. We cannot
                # attribute reliably, so assume the worst and let the danger test decide. That is
                # the over-require direction, and it is how "open parachute" (Main destroys the
                # chute needed for the rm63 jump) surfaced at all.
                out.append({"room": room, "script": script, "item": it})
                continue
            k = self._clause_key(room, g)
            if k in armed or any(gi in gate for gi in wrote.get(k, ())):
                continue                          # the clause DOES something -> a real use
            out.append({"room": room, "script": script, "item": it})
        return out

    def real_uses(self):
        """item -> rooms where holding it ARMS something: the uses that are not sinks.

        Both halves of what `pure_sinks` calls "doing something" must count here, or the two
        disagree: a use that writes a GATING REGISTER from a handler was treated as real by
        pure_sinks but invisible to the danger test. Wearing the parachute at rm63 is exactly
        that -- it sets global142 from a handler, arming no machine state -- so destroying the
        chute elsewhere looked harmless."""
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
        # ...and the THIRD half: an own()-guarded machine STATE path. `(if (gEgo has: 25)
        # (self changeState: 20))` at KQ4's Room690 is what makes the Magic Fruit matter -- it
        # arms the good ending -- but it is neither a machine ENTRY nor a register write, so the
        # danger test could not see it and eating the fruit looked free. `guard_required` is
        # already exactly this evidence, filtered for goal-reachability and traps by build_maps,
        # so take it from there rather than re-deriving (and re-deciding) it here.
        for it, rooms in self.guard_required.items():
            out[it] |= rooms
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
                if any(v != w for (_r, v) in after):
                    continue                        # you can get back out; not a point of no return
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
    for row in s.group_strandings():
        print(f"  + disjunctive group {row['item_names']} needed at rm{row['need_room']}, "
              f"all sources {row['source_rooms']} unreachable from there")
