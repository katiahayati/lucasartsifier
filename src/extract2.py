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

import os
from dataclasses import dataclass, field

import ir as I
from model import GAnd, GOr, GNot, Pred

G_EGO = 0        # gEgo   (get:/put:/has: receiver)  -- confirmed by IR survey
G_CURROOM = 2    # gCurRoom (newRoom: receiver)

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


def _cmp_atom(n, tp):
    ks = n["kids"]
    if len(ks) < 2:
        return Pred("OPAQUE")
    a, b = ks[0], ks[1]
    # normalize (global CMP number)
    gvar = a if I.is_global(a) else (b if I.is_global(b) else None)
    num = I.as_int(b) if I.is_global(a) else (I.as_int(a) if I.is_global(b) else None)
    if gvar is not None and num is not None:
        op = _OPS[tp]
        if gvar is not b and I.is_global(a):
            pass  # a op b, global on left: op as-is
        return Pred("CMP", var=gvar["index"], op=op, value=str(num))
    # a has:? property compares / position -> opaque
    return Pred("OPAQUE")


def _send_atom(n):
    recv, msgs = I.send_pairs(n)
    for sel, params in msgs:
        if sel == "has" and I.is_global(recv, G_EGO):
            it = I.as_int(params[0]) if params else None
            if it is not None:
                return Pred("OWN", var=it)
        if sel in ("said",):
            return Pred("SAID")
    # position tests (posn, inRect, distanceTo, onControl...) and other sends -> opaque
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


def _conj(pc):
    pc = [g for g in pc if g is not None]
    if not pc:
        return None
    return pc[0] if len(pc) == 1 else GAnd(list(pc))


def _room_object(script):
    """The Room instance of a room script (superclass Rm, or named rm<N>)."""
    want = f"rm{script.number}"
    for o in script.objects:
        if o.name == want and not o.is_class:
            return o
    return None


class Extractor:
    def __init__(self, ir):
        self.ir = ir
        self.ts = TS()

    def run(self):
        # room universe: any script that has an rm<N> Room instance
        room_scripts = {n: s for n, s in self.ir.scripts.items() if _room_object(s)}
        for n in room_scripts:
            self.ts.rooms.add(n)
        for n, s in room_scripts.items():
            self._nav_edges(n, s)
            for o in s.objects:
                for mname, meth_ast in o.methods.items():
                    # changeState newRoom exits belong to the MACHINE (gated); don't
                    # duplicate them as free flat edges. Items still captured.
                    self._walk(n, meth_ast, [], movement=(mname != "changeState"))
            for proc_ast in s.procs.values():
                self._walk(n, proc_ast, [])
        # add any newRoom target we saw as a room
        for e in self.ts.edges:
            self.ts.rooms.add(e.dst)
        return self.ts

    def _nav_edges(self, room_num, script):
        obj = _room_object(script)
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

    def _walk(self, room, node, pc, movement=True):
        """Compose path conditions and record effects (newRoom, get:) at the leaves.
        `movement=False` when walking a changeState body: the MACHINE owns those newRoom
        exits (gated by its entries/state sequence), so emitting them as free flat edges
        too would be a permissive DUPLICATE that routes around the gate (the boarding
        passport gate, the raft gauntlet). Items (get:) are still captured (a duplicate
        acquisition is harmless -- monotone)."""
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            test = atom(ks[0])
            self._walk(room, ks[1], pc + [test], movement)
            if len(ks) > 2:
                self._walk(room, ks[2], pc + [GNot(test) if test is not None else None], movement)
            return
        if tp == "Switch":
            for k in node["kids"][1:]:
                if k["t"] == "Case":
                    self._walk(room, k["kids"][1], pc, movement)
                elif k["t"] == "Else":
                    self._walk(room, k["kids"][0], pc, movement)
            return
        if tp == "Cond":
            for k in node["kids"]:
                if k["t"] == "Case":
                    self._walk(room, k["kids"][1], pc + [atom(k["kids"][0])], movement)
                elif k["t"] == "Else":
                    self._walk(room, k["kids"][0], pc, movement)
            return
        if tp == "Loop":
            self._walk(room, node["kids"][0], pc, movement)
            return
        if tp == "Send":
            self._send_effect(room, node, pc, movement)
        for k in node.get("kids", ()):
            self._walk(room, k, pc, movement)

    def _send_effect(self, room, node, pc, movement=True):
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if movement and sel in ("newRoom", "entranceTo") and params:
                dst = I.as_int(params[0])
                if dst is not None:
                    self.ts.edges.append(Edge(room, dst, _conj(pc)))
            elif sel == "get" and I.is_global(recv, G_EGO) and params:
                it = I.as_int(params[0])
                if it is not None:
                    self.ts.items.add(it)
                    self.ts.acqs.append(Acq(it, room, _conj(pc)))


def extract(ir):
    return Extractor(ir).run()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "lsl2_decomp", "lsl2.ir.json")
    ir = I.load_ir(path)
    ts = extract(ir)
    print(f"rooms={len(ts.rooms)} edges={len(ts.edges)} acqs={len(ts.acqs)} items={len(ts.items)}")
    free = sum(1 for e in ts.edges if e.guard is None)
    print(f"  free edges={free} gated edges={len(ts.edges)-free}")
    print("  items acquired:", sorted(ts.items))
