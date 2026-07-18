"""Machine layer over the typed IR: lift each room Script's changeState into an explicit
transition system (states -> guarded ops), then simulate/compile it.

The changeState switch is uniform: `(switch (= state param) (K body) ...)`, one Case per
state. Each state body is a sequence of ops, some guarded by if/cond path conditions:
  EXIT r     `(gCurRoom newRoom: r)`              -- leave to room r
  WRITE g v  `(= Global[g] v)`                    -- register write
  DEATH      the death signal write / death proc  -- absorbing sink
  ADVANCE    a cue is armed (`... self` arg, `(= seconds N)`, `(= cycles N)`,
             `(other changeState: K)`, `(self cue:)`) -> next state = state+1
  JUMP k     `(self changeState: k)`              -- go to state k now
  SETSTATE k `(= state k)`                        -- set state (then a cue advances to k+1)
  GET i      `(gEgo get: i)`                       -- acquire item
  COUNTER    `(++ c)`/`(-- c)`/`(= c lit)`        -- bounded local counter update
A state that arms NO cue and does not transfer PARKS (waits for the next player action);
it does NOT fall into the next state (segments-per-entry -- see machine.py's hard lesson).

Effect-timing is exactly the machine's own control flow, so there is no ENTRY/SELF/EXIT
write reconstruction (the seam that lost the parachute).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import ir as I
from extract2 import atom, _conj, G_EGO, G_CURROOM


@dataclass
class Op:
    kind: str                 # EXIT WRITE DEATH ADVANCE JUMP SETSTATE GET COUNTER
    guard: object = None      # path condition (guard tree) or None
    a: object = None          # EXIT room / WRITE glob / JUMP-SETSTATE state / GET item / COUNTER name
    b: object = None          # WRITE value / COUNTER (kind,val)


@dataclass
class Machine:
    script: int
    inst: str
    states: dict = field(default_factory=dict)     # k -> [Op] in source order (debug view)
    bodies: dict = field(default_factory=dict)     # k -> state body AST (for path compile)
    entries: list = field(default_factory=list)    # [(state, guard)] how it is entered
    start: int = 0

    def __repr__(self):
        return f"Machine({self.inst}@{self.script}: states {sorted(self.states)})"


def _is_cue_send(recv, msgs):
    """A send that ARMS a cue (completes later -> advance to state+1)."""
    for sel, params in msgs:
        # `... self` as the last argument is the universal cue callback
        if params and params[-1].get("t") == "Self":
            return True
        if sel in ("cue", "setCycle", "setMotion", "setScript") and params and \
                any(p.get("t") == "Self" for p in params):
            return True
        # `(otherInstance changeState: K)` starts another script that cues back here
        if sel == "changeState" and recv.get("t") != "Self":
            return True
    return False


class MachineBuilder:
    def __init__(self, ir, game_death):
        self.ir = ir
        self.is_death = game_death        # (glob_index, value) -> bool

    def machines(self, script):
        out = []
        for o in script.objects:
            if "changeState" in o.methods and o.methods["changeState"]:
                m = self._build(script, o)
                if m.states:
                    out.append(m)
        return out

    def _build(self, script, obj):
        m = Machine(script.number, obj.name, start=obj.props.get("start", 0))
        cs = obj.methods["changeState"]
        sw = self._top_switch(cs)
        if sw:
            for c in sw["kids"][1:]:
                if c["t"] == "Case":
                    k = I.as_int(c["kids"][0])
                    if k is not None:
                        m.bodies[k] = c["kids"][1]
                        ops = []
                        self._ops(c["kids"][1], [], ops)
                        m.states[k] = ops
        # entries: init -> changeState: start; and handleEvent/doit changeState: K (guarded)
        for mn in ("init", "handleEvent", "doit"):
            if mn in obj.methods:
                self._entries(obj.methods[mn], [], m)
        return m

    def _top_switch(self, cs):
        for n in I.walk(cs):
            if n["t"] == "Switch":
                head = n["kids"][0]
                if head["t"] == "Assignment":
                    dst = head["kids"][0]
                    if dst.get("t") == "Property" and dst.get("name") == "state":
                        return n
        return None

    def _entries(self, node, pc, m):
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            a = atom(ks[0])
            self._entries(ks[1], pc + [a], m)
            if len(ks) > 2:
                from model import GNot
                self._entries(ks[2], pc + [GNot(a) if a else None], m)
            return
        if tp == "Send":
            recv, msgs = I.send_pairs(node)
            if recv.get("t") == "Self":
                for sel, params in msgs:
                    if sel == "changeState" and params:
                        k = I.as_int(params[0])
                        if k is not None:
                            m.entries.append((k, _conj(pc)))
        for k in node.get("kids", ()):
            self._entries(k, pc, m)

    def _ops(self, node, pc, out):
        """Walk a state body, composing path conditions, appending guarded ops."""
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            a = atom(ks[0])
            self._ops(ks[1], pc + [a], out)
            if len(ks) > 2:
                from model import GNot
                self._ops(ks[2], pc + [GNot(a) if a else None], out)
            return
        if tp == "Cond":
            for c in node["kids"]:
                if c["t"] == "Case":
                    self._ops(c["kids"][1], pc + [atom(c["kids"][0])], out)
                elif c["t"] == "Else":
                    self._ops(c["kids"][0], pc, out)
            return
        if tp == "Switch":
            for c in node["kids"][1:]:
                if c["t"] == "Case":
                    self._ops(c["kids"][1], pc, out)
                elif c["t"] == "Else":
                    self._ops(c["kids"][0], pc, out)
            return
        g = _conj(pc)
        if tp == "Send":
            self._send_op(node, g, out)
        elif tp == "Assignment":
            self._assign_op(node, g, out)
        elif tp == "Increment":
            self._counter_op(node["kids"][0], "inc", None, g, out)
        elif tp == "Decrement":
            self._counter_op(node["kids"][0], "dec", None, g, out)
        for k in node.get("kids", ()):
            self._ops(k, pc, out)

    def _send_op(self, node, g, out):
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if sel == "newRoom" and params:
                r = I.as_int(params[0])
                if r is not None:
                    out.append(Op("EXIT", g, r))
            elif sel == "get" and I.is_global(recv, G_EGO) and params:
                it = I.as_int(params[0])
                if it is not None:
                    out.append(Op("GET", g, it))
            elif sel == "changeState" and recv.get("t") == "Self" and params:
                k = I.as_int(params[0])
                if k is not None:
                    out.append(Op("JUMP", g, k))
        if _is_cue_send(recv, msgs):
            out.append(Op("ADVANCE", g))

    def _assign_op(self, node, g, out):
        dst, src = node["kids"][0], node["kids"][1]
        if dst.get("t") == "Variable" and dst["vtype"] == "Global":
            gi, v = dst["index"], I.as_int(src)
            if v is not None:
                if self.is_death(gi, v):
                    out.append(Op("DEATH", g))
                else:
                    out.append(Op("WRITE", g, gi, v))
        elif dst.get("t") == "Property" and dst.get("name") in ("seconds", "cycles"):
            out.append(Op("ADVANCE", g))            # timing set -> cue will fire
        elif dst.get("t") == "Property" and dst.get("name") == "state":
            k = I.as_int(src)
            if k is not None:
                out.append(Op("SETSTATE", g, k))
        elif dst.get("t") in ("Variable",) and dst["vtype"] in ("Local", "Temp"):
            v = I.as_int(src)
            self._counter_op(dst, "set", v, g, out)

    def _counter_op(self, dst, kind, val, g, out):
        if dst.get("t") == "Variable" and dst["vtype"] in ("Local", "Temp"):
            out.append(Op("COUNTER", g, ("L" if dst["vtype"] == "Local" else "T", dst["index"]),
                          (kind, val)))


if __name__ == "__main__":
    import os
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "lsl2_decomp", "lsl2.ir.json")
    ir = I.load_ir(path)

    def is_death(gi, v):
        return gi == 101 and v == 1001      # LSL2 death_signal gCurrentStatus==1001

    mb = MachineBuilder(ir, is_death)
    for rn in (64, 138):
        s = ir.script(rn)
        for m in mb.machines(s):
            print(m, " start=", m.start, " entries=", [(k, g is not None) for k, g in m.entries])
            for k in sorted(m.states):
                ops = m.states[k]
                if ops:
                    desc = ", ".join(f"{o.kind}{'' if o.a is None else o.a}{'' if o.b is None else '='+str(o.b)}"
                                     f"{'[g]' if o.guard is not None else ''}" for o in ops)
                    print(f"   state {k:2d}: {desc}")
