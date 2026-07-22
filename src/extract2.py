"""Extraction over the sci-tools typed IR (Phase 3 of PLAN-v2 / ENGINE-DIRECTION Plan A).

Walks each room's typed control-flow AST and composes PATH CONDITIONS along the control
flow into a gated transition system: movement edges, item acquisitions, register writes,
deaths. Because the AST is typed and complete, effect-timing follows the machine's own
control flow -- there is no ENTRY/SELF/EXIT reconstruction heuristic (the seam that lost
the parachute).

Guards reuse model.py's tree (GAnd/GOr/GNot/Pred), but identifiers are IR-canonical:
Pred.var is a global INDEX for CMP, an item number for OWN.

This is built incrementally; this first cut does movement + item acquisitions (guards over
OWN/SAID/POS/CMP/opaque), validated against the old model before registers/machine-state.
"""
from __future__ import annotations

import config

import os
from dataclasses import dataclass, field

import ir as I
from guard_ast import GAnd, GOr, GNot, Pred

G_EGO = 0        # gEgo   (get:/put:/has: receiver)  -- confirmed by IR survey
G_ROOMOBJ = 2    # gCurRoom, the room OBJECT (the `newRoom:` receiver) -- not the room NUMBER

NAV_SELECTORS = ("north", "south", "east", "west")


# ---- guard atoms from a test expression ----------------------------------
def atom(n):
    """A boolean test node -> a guard tree (Pred / GAnd / GOr / GNot). Unknown player
    actions (Said, position) and anything we cannot decide become opaque preds."""
    if n is None:
        return None
    tp = n["t"]
    if tp == "Not":
        return GNot(atom(n["kids"][0])) if n["kids"] else Pred("OPAQUE")
    if tp == "And":
        return GAnd([atom(k) for k in n["kids"]])
    if tp == "Or":
        return GOr([atom(k) for k in n["kids"]])
    if tp == "Said":
        return Pred("SAID")
    if tp == "Send":
        return _send_atom(n)
    if tp in ("Eq", "Ne", "Gt", "Ge", "Lt", "Le", "Ugt", "Uge", "Ult", "Ule"):
        return _cmp_atom(n, tp)
    if tp == "Variable" and n["vtype"] == "Global":
        return Pred("CMP", var=n["index"], op="!=", value="0")   # truthiness of a global
    if tp == "Number":
        return None if n["value"] != 0 else Pred("OPAQUE")       # constant test
    return Pred("OPAQUE")


_OPS = {"Eq": "==", "Ne": "!=", "Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<=",
        "Ugt": ">", "Uge": ">=", "Ult": "<", "Ule": "<="}
_REV = {"==": "==", "!=": "!=", ">": "<", ">=": "<=", "<": ">", "<=": ">="}


def _cmp_atom(n, tp):
    """A comparison test -> a guard. Global vs literal -> Pred CMP; LOCAL/Temp vs literal ->
    a CTR tuple `("CTR", (vt_char, idx), op, val)` (same format compile2 uses for machine
    bodies), so gexpr resolves it against the tracked local. `henchStatus==0` and the like
    used to fall through to OPAQUE -- the 'everything means everything' local-guard hole."""
    ks = n["kids"]
    if len(ks) < 2:
        return Pred("OPAQUE")
    a, b = ks[0], ks[1]
    op = _OPS[tp]
    # GLOBAL vs literal (op reversed if the global is on the right, e.g. `(< 5 gX)` = gX>5)
    if I.is_global(a) and I.as_int(b) is not None:
        return Pred("CMP", var=a["index"], op=op, value=str(I.as_int(b)))
    if I.is_global(b) and I.as_int(a) is not None:
        return Pred("CMP", var=b["index"], op=_REV[op], value=str(I.as_int(a)))
    # LOCAL/TEMP vs literal -> tracked-local CTR guard (the previously-dropped 196)
    if I.is_local_or_temp(a) and I.as_int(b) is not None:
        return ("CTR", (a["vtype"][0], a["index"]), op, I.as_int(b))
    if I.is_local_or_temp(b) and I.as_int(a) is not None:
        return ("CTR", (b["vtype"][0], b["index"]), _REV[op], I.as_int(a))
    # `(edgeHit) == N` -> the ego is at screen edge N (a POSITION guard over (x,y)).
    if _is_ego_edgehit(a) and I.as_int(b) is not None and op == "==":
        return ("POS", "edge", I.as_int(b))
    if _is_ego_edgehit(b) and I.as_int(a) is not None and op == "==":
        return ("POS", "edge", I.as_int(a))
    # property / onControl / distance compares -> opaque (control-map / undecidable)
    return Pred("OPAQUE")


def _is_ego_edgehit(n):
    """`(gEgo edgeHit:)` -- returns which screen edge the ego is at."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        if I.is_global(recv, G_EGO):
            return any(sel == "edgeHit" for sel, _ in msgs)
    return False


G_CURROOM = 11   # gCurRoomNum -- compared against room numbers all over the scripts


def _at_item(n):
    """`(gInv at: N)` -> N. The object handle for inventory item N."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        for sel, params in msgs:
            if sel == "at" and params:
                return I.as_int(params[0])
    return None


# ---- the item-LOCATION store, written two ways ---------------------------
# SCI moves an inventory item by setting its OWNER, and the games spell that differently:
# LSL2 sends the EGO `get:`/`put:`, KQ4 sends the ITEM `moveTo:`. They are one operation --
# `get: N` IS `(item N) moveTo: gEgo` -- and we read only the first spelling, so KQ4's
# Dead_Fish, whose ONLY acquisition is `((Inv at: 24) moveTo: gEgo)` (Room95.sc:673), did not
# exist in our model at all. It is not a KQ4-only idiom either: LSL2 destroys the Soap with
# `((global9 at: 18) moveTo: -1)` at rm48 and rm71, which we have always missed.
#
# The DESTINATION is the second half, and `put:` has always discarded it. KQ4 uses pseudo-room
# numbers as item STATES -- 206 not-yet-appeared, 23/29 lying on the ground, 666 baited on the
# hook, 777 eaten, 207 given to the pelican, 999 destroyed -- so "where did it go" is the whole
# difference between an item that is merely elsewhere and one that is gone. We return the raw
# destination and let callers decide what a number means; only smv_emit3 knows the room set.
EGO = "ego"      # destination sentinel: the item is now HELD


def item_transfer(recv, sel, params):
    """An inventory-transfer send -> `(item, dest)`, else None.

    `dest` is EGO or an int (a room number, real or pseudo; -1 = nowhere, SCI's own idiom).
    Recognises all three spellings:  `gEgo get: N`  /  `gEgo put: N D`  /  `(Inv at: N) moveTo: D`.
    """
    if sel in ("get", "put") and I.is_global(recv, G_EGO) and params:
        it = I.as_int(params[0])
        if it is None:
            return None
        if sel == "get":
            return (it, EGO)
        # `put: N D` -- D defaults to NOWHERE when omitted, which is how LSL2 writes it.
        if len(params) < 2:
            return (it, -1)
        if I.is_global(params[1], G_EGO):
            return (it, EGO)
        d = I.as_int(params[1])
        return (it, d if d is not None else -1)
    # `(Inv at: N) moveTo: D`. The `_at_item` receiver test is what keeps this off the
    # Window/View `moveTo: x y` selector, which is a completely unrelated screen-position send
    # (LSL2's dialog code uses it 30-odd times with two coordinate arguments).
    if sel == "moveTo" and len(params) == 1:
        it = _at_item(recv)
        if it is None:
            return None
        if I.is_global(params[0], G_EGO):
            return (it, EGO)
        d = I.as_int(params[0])
        return (it, d) if d is not None else None
    return None


def _send_atom(n):
    recv, msgs = I.send_pairs(n)
    for sel, params in msgs:
        if sel == "has" and I.is_global(recv, G_EGO):
            it = I.as_int(params[0]) if params else None
            if it is not None:
                return Pred("OWN", var=it)
        if sel in ("said",):
            return Pred("SAID")
        # `(gInv at: X) ownedBy: gCurRoomNum` -- "item X is still LYING IN THIS ROOM". The SCI
        # idiom for a one-time pickup, used 77 times in LSL2 and previously lost as an opaque.
        # It matters because `put: X -1` sets the owner to NOWHERE, so once an item guarded this
        # way is destroyed it can never be re-acquired (barfing into the Airsick_Bag).
        if sel == "ownedBy":
            it = _at_item(recv)
            if it is not None:
                here = bool(params) and I.is_global(params[0], G_CURROOM)
                return Pred("LOC", var=it, op="ownedBy", value="room" if here else "other")
        # `(gEgo inRect: a b c d)` -> a POSITION guard over the ego's (x,y). Coordinates are
        # in the AST, so this is derivable; ONE consistent (x,y) is what makes "cross east =>
        # inRect" unavoidable: one consistent (x,y) per step, not a fresh choice per guard.
        if sel == "inRect" and I.is_global(recv, G_EGO) and len(params) >= 4:
            cs = [I.as_int(p) for p in params[:4]]
            if all(c is not None for c in cs):
                return ("POS", "rect", tuple(cs))
    # onControl (PIC control-map), distanceTo, posn-relative, other sends -> opaque residue
    return Pred("OPAQUE")


# ---- transition system ---------------------------------------------------
@dataclass
class Edge:
    src: int
    dst: int
    guard: object = None       # guard tree; None = free


@dataclass
class Acq:
    item: int
    room: int
    guard: object = None


@dataclass
class TS:
    rooms: set = field(default_factory=set)
    edges: list = field(default_factory=list)
    acqs: list = field(default_factory=list)
    items: set = field(default_factory=set)
    cs_edges: list = field(default_factory=list)   # changeState newRoom exits (room,dst,
    #   guard). The MACHINE owns these; used as a GATED fallback only where the machine
    #   walk can't deliver the exit (control_exits) -- avoids a false dead-end without
    #   reintroducing a free bypass.


def _conj(pc):
    pc = [g for g in pc if g is not None]
    if not pc:
        return None
    return pc[0] if len(pc) == 1 else GAnd(list(pc))


_ROOM_SPECIES = {}          # ir id -> species number of the Rm/Room base class


def _room_species(ir):
    """Species of the game's Room base class, found by NAME in the class table.

    Room detection used to be `name == f"rm{script.number}"`, which is a decompiler NAMING
    CONVENTION, not a fact about the game. sci-tools emits `rm47` for LSL2 but `Room63` for KQ4,
    so every KQ4 room failed the test and the extractor saw 4 rooms out of 159 scripts -- silently
    analysing almost nothing. Inheritance is the real signal, and it is what the docstring always
    claimed. The name check stays as a fallback."""
    key = id(ir)
    if key in _ROOM_SPECIES:
        return _ROOM_SPECIES[key]
    species = None
    for s in ir.scripts.values():
        for o in s.objects:
            if o.is_class and o.name in ("Rm", "Room"):
                species = o.species
                break
        if species is not None:
            break
    _ROOM_SPECIES[key] = species
    return species


def _room_object(script, ir=None):
    """The Room instance of a room script: an instance of the Rm/Room class, else named rm<N>."""
    if ir is not None:
        sp = _room_species(ir)
        if sp is not None:
            for o in script.objects:
                if not o.is_class and o.super == sp:
                    return o
    want = f"rm{script.number}"
    for o in script.objects:
        if o.name == want and not o.is_class:
            return o
    return None


class Extractor:
    def __init__(self, ir):
        self.ir = ir
        self.ts = TS()
        self.procs_by = {}
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body

    def run(self):
        # room universe: any script that has an rm<N> Room instance
        room_scripts = {n: s for n, s in self.ir.scripts.items() if _room_object(s, self.ir)}
        for n in room_scripts:
            self.ts.rooms.add(n)
        for n, s in room_scripts.items():
            self._nav_edges(n, s)
            for o in s.objects:
                for mname, meth_ast in o.methods.items():
                    # changeState newRoom exits belong to the MACHINE (gated); don't
                    # duplicate them as free flat edges. Items still captured. Procedures
                    # are FOLLOWED in-context (below), not walked standalone -- a proc
                    # walked context-free would emit its newRoom as a free bypass.
                    self._walk(n, meth_ast, [], n, set(), movement=(mname != "changeState"))
        # add any newRoom target we saw as a room
        for e in self.ts.edges:
            self.ts.rooms.add(e.dst)
        return self.ts

    def _nav_edges(self, room_num, script):
        obj = _room_object(script, self.ir)
        if obj is not None:
            for sel in NAV_SELECTORS:
                dst = obj.props.get(sel)
                if dst and dst != 0xffff:
                    self.ts.edges.append(Edge(room_num, dst))   # walk-off exit, free
        # static entranceTo on any object (rooms + Doors): walking it goes to that room
        for o in script.objects:
            et = o.props.get("entranceTo", 0)
            if et and et != 0xffff:
                self.ts.edges.append(Edge(room_num, et))

    def _walk(self, room, node, pc, script, seen, movement=True):
        """Compose path conditions and record effects (newRoom, get:), FOLLOWING calls in
        context. `movement=False` for a changeState body: the MACHINE owns those newRoom
        exits, so a free flat duplicate would bypass the gate. Items (get:) always captured
        (duplicate acquisition is monotone)."""
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            test = atom(ks[0])
            self._walk(room, ks[1], pc + [test], script, seen, movement)
            if len(ks) > 2:
                self._walk(room, ks[2], pc + [GNot(test) if test is not None else None], script, seen, movement)
            return
        if tp == "Switch":
            for k in node["kids"][1:]:
                body = k["kids"][1] if k["t"] == "Case" else (k["kids"][0] if k["t"] == "Else" else None)
                self._walk(room, body, pc, script, seen, movement)
            return
        if tp == "Cond":
            priors = []   # a case (and the else) runs only if all PRIOR cases failed
            for k in node["kids"]:
                if k["t"] == "Case":
                    a = atom(k["kids"][0])
                    self._walk(room, k["kids"][1], pc + priors + [a], script, seen, movement)
                    priors = priors + [GNot(a) if a is not None else None]
                elif k["t"] == "Else":
                    self._walk(room, k["kids"][0], pc + priors, script, seen, movement)
            return
        if tp == "Loop":
            self._walk(room, node["kids"][0], pc, script, seen, movement)
            return
        if tp == "Send":
            self._send_effect(room, node, pc, movement)
        elif tp == "Assignment" and movement:
            self._nav_assignment(room, node, pc)
        elif tp in ("PublicCall", "LocalCall"):
            tgt = node.get("script", script)
            name = node.get("name")
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._walk(room, body, pc, tgt, seen | {name}, movement)
        for k in node.get("kids", ()):
            self._walk(room, k, pc, script, seen, movement)

    def _nav_assignment(self, room, node, pc):
        """`(= north 5)` -- a walk-off exit set by ASSIGNING the room's own property.

        The other idiom, declaring it in the properties block, is handled by `_nav_edges`. Both
        mean the same thing and games pick one: LSL2 uses the properties block 98 times and the
        assignment form NEVER; KQ4 uses the assignment form 162 times. Supporting only the first
        left 35 KQ4 rooms with no extractable exit at all and shattered its map into 64 components,
        so the analysis was reasoning about a game it could not walk across.

        Captured here rather than in `_nav_edges` so the path condition applies: an exit opened
        only under some condition becomes a GUARDED edge, and `(= east 0)` (closing an exit) is
        correctly not an edge at all."""
        kids = node.get("kids") or []
        if len(kids) < 2:
            return
        dest, src = kids[0], kids[1]
        if not (isinstance(dest, dict) and dest.get("t") == "Property"
                and dest.get("name") in NAV_SELECTORS):
            return
        dst = I.as_int(src)
        if not dst or dst == 0xffff:
            return                      # 0 CLOSES the exit; it does not open one
        self.ts.edges.append(Edge(room, dst, _conj(pc)))

    def _send_effect(self, room, node, pc, movement=True):
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if sel in ("newRoom", "entranceTo") and params:
                dsts = [I.as_int(params[0])]
                if dsts[0] is None and I.is_global(params[0]):
                    # INDIRECT destination `newRoom: <global>` -- a routing room whose next
                    # room is held in a global (rm40's revolving door: gRmAfter40 cycles
                    # 42..45). Resolve to the room numbers that global can hold; dropping it
                    # made rm43 (the Knife) and its cluster unreachable -> endgame sealed.
                    dsts = self._global_room_values(room, params[0]["index"])
                for dst in dsts:
                    if dst is not None:
                        (self.ts.edges if movement else self.ts.cs_edges).append(
                            Edge(room, dst, _conj(pc)))
            elif sel == "get" and I.is_global(recv, G_EGO) and params:
                it = I.as_int(params[0])
                if it is not None:
                    self.ts.items.add(it)
                    self.ts.acqs.append(Acq(it, room, _conj(pc)))

    def _global_room_values(self, room, gi):
        """Room numbers a `newRoom:` global can hold, from switch-on-G case labels and
        `(= G lit)` assignments anywhere in this room's script. Filtered to real rooms
        (an rm<N> Room instance exists), so cycle counters like 0 are excluded."""
        vals = set()
        s = self.ir.scripts.get(room)
        if s is None:
            return vals

        def is_room(v):
            rs = self.ir.scripts.get(v)
            return rs is not None and _room_object(rs) is not None

        for o in s.objects:
            for _mn, ast in o.methods.items():
                for n in I.walk(ast):
                    if n["t"] == "Switch":
                        head = n["kids"][0]
                        if head.get("t") == "Variable" and head.get("vtype") == "Global" \
                                and head.get("index") == gi:
                            for c in n["kids"][1:]:
                                if c["t"] == "Case":
                                    v = I.as_int(c["kids"][0])
                                    if v is not None and is_room(v):
                                        vals.add(v)
                    elif n["t"] == "Assignment" and I.is_global(n["kids"][0]) \
                            and n["kids"][0].get("index") == gi:
                        v = I.as_int(n["kids"][1])
                        if v is not None and is_room(v):
                            vals.add(v)
        return vals


def extract(ir):
    return Extractor(ir).run()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = I.load_ir(path)
    ts = extract(ir)
    print(f"rooms={len(ts.rooms)} edges={len(ts.edges)} acqs={len(ts.acqs)} items={len(ts.items)}")
    free = sum(1 for e in ts.edges if e.guard is None)
    print(f"  free edges={free} gated edges={len(ts.edges)-free}")
    print("  items acquired:", sorted(ts.items))
