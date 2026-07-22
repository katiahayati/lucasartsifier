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
it does NOT fall into the next state (segments-per-entry -- the hard lesson of the
DELETED first-generation lifter this file replaced; git history has it).

Effect-timing is exactly the machine's own control flow, so there is no ENTRY/SELF/EXIT
write reconstruction (the seam that lost the parachute).
"""
from __future__ import annotations

import config

from dataclasses import dataclass, field

import ir as I
from extract import atom, _conj, G_EGO, G_CURROOM, item_transfer, EGO


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
    init_entries: list = field(default_factory=list)  # entries from the room's INIT method only.
    #   These run atomically with room init, so they must be bundled onto ROOM ARRIVAL and
    #   evaluated on the pre-entry state -- else an init write to the guard register (rm79:
    #   init sets gIslandStatus:=3, the `changeState 1` cutscene guard is gIslandStatus==2)
    #   makes the standalone one-step-later entry never fire. Player-triggered entries
    #   (handleEvent/doit) stay in `entries` (evaluated in-room, post-init).
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


def _setscript_target(param):
    """The Script instance/class name a `setScript:` param refers to: `henchScript` (an
    Object ref) or `(henchScript new:)` (a Send whose receiver is the Object)."""
    if not isinstance(param, dict):
        return None
    if param.get("t") == "Object":
        return param.get("name")
    if param.get("t") == "Send" and param.get("kids"):
        recv = param["kids"][0]
        if isinstance(recv, dict) and recv.get("t") == "Object":
            return recv.get("name")
    return None


class MachineBuilder:
    def __init__(self, ir, game_death):
        self.ir = ir
        self.is_death = game_death        # (glob_index, value) -> bool
        self.procs_by = {}                # (script, proc-name) -> body, for call-following
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body

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
        # entries: ANY object's init/handleEvent/doit that does `(<inst> changeState: K)`
        # (guarded) -- the machine is often started/redirected by the ROOM object, not by
        # itself (rm65.init -> rm65Script changeState: survive-or-die on gCurrentStatus).
        for other in script.objects:
            is_self = (other.name == m.inst)   # `self` in other's method means `other`,
            #   so a `(self changeState:K)` is an entry to THIS machine ONLY when other IS it.
            #   Cross-object starts must name the instance: `(<m.inst> changeState:K)`.
            for mn in ("init", "handleEvent", "doit"):
                if mn in other.methods:
                    self._entries(other.methods[mn], [], m, script.number, set(),
                                  source=mn, is_self_obj=is_self)
        # setScript entries: `(actor setScript: <m or (m new:)>)` in ANY method (incl a
        # changeState body -- hench1Script state1 -> henchScript). These START m at state 0.
        # The extractor dropped them, so setScript-driven machines (the henchmen chasers, the
        # bottle) never ran -- which is WHY the absent-start fall-through hack was needed.
        for other in script.objects:
            for mn, body in other.methods.items():
                self._scan_setscript(body, [], m, source=("init" if mn == "init" else mn))
        return m

    def _scan_setscript(self, node, pc, m, source):
        """Find `(x setScript: <ref>)` where <ref> is m, and record an entry to m at state 0 with
        the path condition. Control flow is shared -- this used to hand-roll If and Cond."""
        from extract import walk_stream
        walk_stream(node, pc, lambda n, p: self._setscript_leaf(n, p, m, source))

    def _setscript_leaf(self, node, pc, m, source):
        if node["t"] != "Send":
            return
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if sel == "setScript" and params and _setscript_target(params[0]) == m.inst:
                g = _conj(pc)
                m.entries.append((0, g))
                if source == "init":
                    m.init_entries.append((0, g))   # ADDITIONALLY, not instead -- an init-sourced
                    #   entry is bundled onto room arrival AND is still a normal entry

    def _top_switch(self, cs):
        """The `(switch (= state param1) ...)` that IS the machine -- identified by its head
        assigning the `state` property, not by position."""
        for n in I.walk(cs):
            if n["t"] == "Switch":
                head = n["kids"][0]
                if head["t"] == "Assignment":
                    dst = head["kids"][0]
                    if dst.get("t") == "Property" and dst.get("name") == "state":
                        return n
        return None

    def _entries(self, node, pc, m, script, seen, source=None, is_self_obj=False):
        """Find player-triggered `(<me> changeState: K)` entries and the FULL path condition that
        gates them, FOLLOWING PublicCall/LocalCall (the changeState often lives inside a proc,
        with the guard -- e.g. `has: Passport` -- on a Cond case above the call).

        Control flow is shared (walk_stream); this used to hand-roll If and Cond, in a third copy
        of the same code."""
        from extract import walk_stream
        walk_stream(node, pc,
                    lambda n, p: self._entry_leaf(n, p, m, script, seen, source, is_self_obj))

    def _entry_leaf(self, node, pc, m, script, seen, source, is_self_obj):
        tp = node["t"]
        if tp == "Send":
            recv, msgs = I.send_pairs(node)
            # `(self changeState:K)` only when scanning THIS machine's own object; OR
            # `(theMachineInstance changeState:K)` from ANOTHER object -- rm65.init does
            # `(rm65Script changeState: 4)` gated on gCurrentStatus to start the survive
            # segment. Matching bare Self across objects mis-attributed rm34Script's
            # `changeState: 9/15` to henchScript (the disguise), etc.
            targets_me = ((recv.get("t") == "Self" and is_self_obj)
                          or (recv.get("t") == "Object" and recv.get("name") == m.inst))
            if not targets_me:
                return
            for sel, params in msgs:
                if sel == "changeState" and params:
                    k = I.as_int(params[0])
                    if k is not None:
                        m.entries.append((k, _conj(pc)))
                        if source == "init":
                            m.init_entries.append((k, _conj(pc)))
        elif tp in ("PublicCall", "LocalCall"):
            tgt = node.get("script", script)
            name = node.get("name")
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._entries(body, pc, m, tgt, seen | {name}, source, is_self_obj)

    def _ops(self, node, pc, out):
        """Walk a state body, composing path conditions, appending guarded ops.

        Control flow comes from `extract.walk_stream` / `ir.control_shape`; this used to
        re-implement If/Cond/Switch itself, in code identical to extract's and opmodel's."""
        from extract import walk_stream
        walk_stream(node, pc, lambda n, p: self._op_leaf(n, _conj(p), out))

    def _op_leaf(self, node, g, out):
        """What one statement means to the machine model -- the part that is ours, not shared."""
        tp = node["t"]
        if tp == "Send":
            self._send_op(node, g, out)
        elif tp == "Assignment":
            self._assign_op(node, g, out)
        elif tp == "Increment":
            self._counter_op(node["kids"][0], "inc", None, g, out)
        elif tp == "Decrement":
            self._counter_op(node["kids"][0], "dec", None, g, out)

    def _send_op(self, node, g, out):
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            if sel == "newRoom" and params:
                r = I.as_int(params[0])
                if r is not None:
                    out.append(Op("EXIT", g, r))
            elif sel == "changeState" and recv.get("t") == "Self" and params:
                k = I.as_int(params[0])
                if k is not None:
                    out.append(Op("JUMP", g, k))
            else:
                # Same recogniser compile uses -- these two walkers must not drift.
                tr = item_transfer(recv, sel, params)
                if tr is not None and tr[1] == EGO:
                    out.append(Op("GET", g, tr[0]))
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
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
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
