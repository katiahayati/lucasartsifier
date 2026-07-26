"""Machine layer over the typed IR: lift each room Script's changeState into an explicit
transition system (states -> guarded ops), then simulate/compile it.

The changeState switch is uniform: `(switch (= state param) (K body) ...)`, one Case per
state. Each state body is a sequence of ops, some guarded by if/cond path conditions:
  EXIT r     `(gCurRoom newRoom: r)`              -- leave to room r
  WRITE g v  `(= Global[g] v)`                    -- register write
  DEATH      the death signal write / death proc  -- absorbing sink
  ADVANCE    a cue is armed (`... self` arg, `(= seconds N)`, `(= cycles N)`, `(= ticks N)`,
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
from guard_ast import GAnd, GOr
from extract import atom, _conj, item_transfer, EGO
import extract as X


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
    entry_armers: list = field(default_factory=list)   # PARALLEL to entries: the machine whose
    #   changeState body armed us, or None. A cutscene armed by ANOTHER cutscene inherits its
    #   preconditions -- see MachineBuilder._chain_entries.
    entry_locals: list = field(default_factory=list)   # PARALLEL to entries: {(vt,idx): val} the
    #   arming context wrote before setScript'ing us. A machine's internal local branches read
    #   these -- rm214 sets local1:=1 (guarded by using the staff) and knockDoor only reaches
    #   `newRoom: 18` when local1==1, so the coin/bottle inside are reachable ONLY with the staff.
    #   Kept parallel (not a 3-tuple) so every consumer that unpacks `(state, guard)` is untouched.
    init_entry_locals: list = field(default_factory=list)   # PARALLEL to init_entries.
    start: int = 0

    def __repr__(self):
        return f"Machine({self.inst}@{self.script}: states {sorted(self.states)})"


def _is_cue_send(recv, msgs):
    """A send that ARMS a cue (completes later -> advance to state+1)."""
    for sel, params in msgs:
        # `self` as an argument is the universal cue callback -- ANY position, not just last.
        # SCI1.1's Messager puts it mid-list (`say: noun verb cond seq self room`), so a
        # last-argument test read those states as PARKing and truncated every cutscene that
        # speaks: KQ6's minotaur fight stalls at state 1 and never reaches the state where the
        # red scarf decides it.
        if any(isinstance(p, dict) and p.get("t") == "Self" for p in params):
            return True
        if sel in ("cue", "setCycle", "setMotion", "setScript") and params and \
                any(p.get("t") == "Self" for p in params):
            return True
        # `(self cue:)` -- an IMMEDIATE self-cue, the way a state says "nothing to wait for,
        # carry on". No arguments, so the callback tests above cannot see it, and the state
        # read as PARKing: KQ6's minotaur fight takes this branch whenever it is not the
        # talking variant, and stalled one state before the scarf decides the outcome.
        if sel == "cue" and not params and recv.get("t") == "Self":
            return True
        # `(otherInstance changeState: K)` starts another script that cues back here
        if sel == "changeState" and recv.get("t") != "Self":
            return True
    return False


def _setscript_target(param, ir=None):
    """The Script a `setScript:` param refers to, as `(script_or_None, name)`.

    Three spellings: `henchScript` (an Object ref in the same script), `(henchScript new:)`
    (a Send whose receiver is the Object), and `(ScriptID 344 3)` -- SCI's CROSS-SCRIPT
    reference, which needs the export table to resolve and so is only available when an `ir`
    is supplied. A `None` script means "this same script", which is all the first two can mean.

    KQ6 arms 231 scripts this way and we resolved none of them, so every cutscene armed from
    another script -- the realm-of-the-dead entry among them -- lost its guard."""
    if not isinstance(param, dict):
        return None
    if param.get("t") == "Object":
        return (None, param.get("name"))
    if ir is not None:
        got = ir.script_id_target(param)
        if got:
            return got
    if param.get("t") == "Send" and param.get("kids"):
        recv = param["kids"][0]
        if isinstance(recv, dict) and recv.get("t") == "Object":
            return (None, recv.get("name"))
        got = ir.script_id_target(recv) if ir is not None else None
        if got:
            return got
    return None


def _pc_covers(wpc, apc):
    """The write's path condition is a PREFIX of the arm's -- so whenever the arm fires, the write
    has already run and its value holds at machine start. Sibling leaves in one branch share the
    same atom OBJECTS (walk_stream passes one `pc + ext` list per branch), so identity comparison
    is exact and cheap; a shallower unconditional write also covers a deeper guarded arm."""
    return len(wpc) <= len(apc) and all(wpc[i] is apc[i] for i in range(len(wpc)))


class MachineBuilder:
    def __init__(self, ir, game_death):
        self.ir = ir
        self.is_death = game_death        # (glob_index, value) -> bool
        self.procs_by = {}                # (script, proc-name) -> body, for call-following
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body
        # CROSS-SCRIPT arming index: (target script, target instance) -> [(arming script, method,
        # body)]. A `setScript:` naming an Object can only mean an object of the SAME script, so
        # the per-script scan in _build covers it; a `(ScriptID s n)` target can live anywhere, so
        # the arming code has to be found by looking outward from the machine. Built once here
        # rather than re-scanned per machine, which would be quadratic over 341 scripts.
        self.arms = {}
        for rn, s in ir.scripts.items():
            bodies = [(o.name, mn, b) for o in s.objects for mn, b in o.methods.items()]
            bodies += [(nm, "proc", b) for nm, b in s.procs.items()]
            for _oname, mn, body in bodies:
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    _r, msgs = I.send_pairs(n)
                    for sel, params in msgs:
                        if sel != "setScript" or not params:
                            continue
                        tgt = _setscript_target(params[0], ir)
                        if tgt and tgt[0] is not None and tgt[0] != rn:
                            self.arms.setdefault(tgt, []).append((rn, mn, body))

    def machines(self, script):
        out = []
        for o in script.objects:
            if "changeState" in o.methods and o.methods["changeState"]:
                m = self._build(script, o)
                if m.states:
                    out.append(m)
        self._chain_entries(out)
        return out

    def _chain_entries(self, ms):
        """A cutscene armed by ANOTHER cutscene inherits its preconditions.

        KQ6's catacombs exit hinges on this: `freeCeleste` walks you out to the surface with an
        empty guard, because it is armed deep inside `minotaurCharging` -- which is itself only
        armed once the minotaur has seen you. Read alone, the escape looks free and the catacombs
        never become the sealed pocket they are.

        The armer's entries are alternatives, so they contribute a DISJUNCTION; conjoined with the
        path condition at the arming site. Bounded: only when the armer has a small entry set (a
        big one says little and would blow the guard up), and only one level, since the chains that
        matter are short and a fixpoint over mutually-arming scripts is not worth the risk."""
        by_name = {m.inst: m for m in ms}
        for m in ms:
            for i, armer in enumerate(m.entry_armers):
                a = by_name.get(armer[0]) if armer else None
                if a is None or a is m or not a.entries or len(a.entries) > 3:
                    continue
                alts = [g for _k, g in a.entries if g is not None]
                if not alts or len(alts) != len(a.entries):
                    continue                    # some arming of the armer is unconditional
                pre = alts[0] if len(alts) == 1 else GOr(list(alts))
                K, g = m.entries[i]
                m.entries[i] = (K, GAnd([pre, g]) if g is not None else pre)

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
                # If the arming site is inside ANOTHER machine's changeState, remember whose AND
                # at which state: that machine's preconditions up to that point are ours too, and
                # a cutscene decides its outcome long before the state that pays it off (KQ6's
                # minotaur fight branches at 8 and arms the walk-out at 14). Scanned per CASE so
                # the state is known; the whole body otherwise loses it.
                if (mn == "changeState" and other.name != m.inst
                        and "changeState" in other.methods):
                    sw = self._top_switch(body)
                    for c in (sw["kids"][1:] if sw else []):
                        if c.get("t") != "Case":
                            continue
                        k = I.as_int(c["kids"][0])
                        if k is None:
                            continue
                        self._scan_setscript(c["kids"][1], [], m, source=mn,
                                             armer=(other.name, k))
                    continue
                self._scan_setscript(body, [], m, source=("init" if mn == "init" else mn))
        # ...and the same scan over the OTHER scripts that arm this machine by `(ScriptID s n)`.
        # Deduplicated per body: one method can arm the same machine on several branches, and
        # _scan_setscript already records one entry per arming site within a body.
        seen = set()
        for (arm_script, mn, body) in self.arms.get((script.number, m.inst), ()):
            key = (arm_script, mn, id(body))
            if key in seen:
                continue
            seen.add(key)
            self._scan_setscript(body, [], m, source=("init" if mn == "init" else mn))
        return m

    def _targets(self, param, m):
        """Does this `setScript:` argument name machine `m`? An Object reference is scoped to the
        script it appears in, so only the name is compared; a `(ScriptID s n)` carries its own
        script and must match m's too, or two same-named Scripts in different scripts would be
        conflated."""
        tgt = _setscript_target(param, self.ir)
        if not tgt:
            return False
        s, name = tgt
        return name == m.inst and (s is None or s == m.script)

    def _scan_setscript(self, node, pc, m, source, armer=None):
        """Find `(x setScript: <ref>)` where <ref> is m, record an entry to m at state 0 with the
        path condition, AND carry the LOCAL WRITES the arming context made before the setScript. A
        machine reads its own script's locals, so a local the arming branch set gates the machine's
        internal flow -- rm214 sets `local1:=1` in the same branch that arms knockDoor, and knockDoor
        only reaches `newRoom: 18` while local1==1. Control flow is shared (walk_stream)."""
        from extract import walk_stream, verb_param_scope
        events = []                               # ordered: ("w",(vt,idx),val,pc) | ("a",pc)
        def leaf(n, p):
            t = n.get("t")
            if t == "Assignment":
                ks = n.get("kids") or []
                d = ks[0] if ks else None
                if (d and d.get("t") == "Variable" and d.get("vtype") in ("Local", "Temp")
                        and len(ks) > 1 and I.as_int(ks[1]) is not None):
                    events.append(("w", (d["vtype"][0], d["index"]), I.as_int(ks[1]), list(p)))
            elif t == "Send":
                _r, msgs = I.send_pairs(n)
                for sel, params in msgs:
                    if sel != "setScript" or not params or not self._targets(params[0], m):
                        continue
                    # `setScript: <script> <caller> <register>` -- the third argument tells the
                    # Script WHICH job it is doing, and its body branches on it. Carried like a
                    # local write so the entry only reaches the arm it selected: without it,
                    # KQ6's `walkOut 0 1` (flag-gated, out to the surface) and `walkOut 0 0`
                    # (back into the maze) merge, and the gated escape reads as free.
                    reg = X.REG_KEY if len(params) > 2 and I.as_int(params[2]) is not None else None
                    events.append(("a", list(p), I.as_int(params[2]) if reg else None))
        # A doVerb that arms this machine with `setScript:` gates it on the item the player used --
        # `(== param1 <item.message>)` -> OWN. verb_param_scope makes `atom` see that inside the
        # arming path condition (the machine lift shares extract.atom but does not set the context).
        with verb_param_scope(source):
            walk_stream(node, pc, leaf)
        for i, ev in enumerate(events):
            if ev[0] != "a":
                continue
            apc = ev[1]
            loc = {}
            for e in events[:i]:                  # writes that RAN before this arm, on its path
                if e[0] == "w" and _pc_covers(e[3], apc):
                    loc[e[1]] = e[2]
            if len(ev) > 2 and ev[2] is not None:
                loc[X.REG_KEY] = ev[2]            # the `register` this arming selected
            self._add_entry(m, 0, _conj(apc), loc, source == "init", armer)   # init entries are ADDITIONALLY
            #   bundled onto room arrival, not instead -- still normal entries too

    def _add_entry(self, m, state, guard, locals_, is_init, armer=None):
        """Append an entry AND its carried locals, keeping the two parallel lists in lockstep."""
        m.entries.append((state, guard))
        m.entry_locals.append(dict(locals_))
        m.entry_armers.append(armer)
        if is_init:
            m.init_entries.append((state, guard))
            m.init_entry_locals.append(dict(locals_))

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
                        self._add_entry(m, k, _conj(pc), {}, source == "init")
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
                for tr in X.item_transfers(recv, sel, params):
                    if tr[1] == EGO:
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
        elif dst.get("t") == "Property" and dst.get("name") in ("seconds", "cycles", "ticks"):
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
