"""Compile a lifted machine (machine2) into transition-system contributions:
edges (with guards + register writes delivered on the move), deaths, and forced
entry-writes. Effect-timing is the machine's own control flow.

Method (PLAN-v2 Phase 3, path form): enumerate leaf PATHS through each state body
(branches + sequential preemption -- newRoom/changeState/death act immediately, cues only
ARM), then walk the state graph from each entry (init->start, or a handleEvent
changeState:K) to every EXIT/DEATH, accumulating the path guard + register writes, with
bounded-counter unrolling for loops. A machine we cannot compile contributes nothing and
the flat movement edge stands (control_exits, in spirit).
"""
from __future__ import annotations

import ir as I
from model import GAnd, GNot, Pred
from extract2 import atom, _conj, G_EGO
import machine2 as M

COUNTER_CAP = 40          # loop/unroll bound
PATH_CAP = 4000           # per-machine path budget


# ---- leaf-path enumeration through a state body --------------------------
def _paths_of(node):
    """List of paths through `node`; each path is a list of ('T', testnode, pol) and
    ('D', opnode) items in source order. Branches fan out; sequences compose."""
    if node is None:
        return [[]]
    tp = node["t"]
    if tp == "List":
        return _seq(node["kids"])
    if tp == "If":
        ks = node["kids"]
        test = ks[0]
        out = [[("T", test, True)] + p for p in _paths_of(ks[1])]
        if len(ks) > 2:
            out += [[("T", test, False)] + p for p in _paths_of(ks[2])]
        else:
            out.append([("T", test, False)])
        return out
    if tp == "Cond":
        out, priors = [], []
        for c in node["kids"]:
            if c["t"] == "Case":
                test = c["kids"][0]
                for p in _paths_of(c["kids"][1]):
                    out.append([("T", t2, False) for t2 in priors] + [("T", test, True)] + p)
                priors.append(test)
            elif c["t"] == "Else":
                for p in _paths_of(c["kids"][0]):
                    out.append([("T", t2, False) for t2 in priors] + p)
        return out or [[]]
    if tp == "Switch":
        out = []
        for c in node["kids"][1:]:
            body = c["kids"][1] if c["t"] == "Case" else c["kids"][0]
            out += _paths_of(body)
        return out or [[]]
    return [[("D", node)]]


def _seq(forms):
    res = [[]]
    for f in forms:
        nxt = []
        for pre in res:
            for sub in _paths_of(f):
                nxt.append(pre + sub)
        res = nxt
        if len(res) > PATH_CAP:
            break
    return res


# ---- interpret a path into (guard, writes, gets, counters, transition) ---
class Step:
    __slots__ = ("guard", "writes", "gets", "counters", "trans")

    def __init__(self):
        self.guard = []            # atoms (external) or ("CTR", (vt,idx), op, val)
        self.writes = []           # (glob, val)
        self.gets = []
        self.counters = []         # ((vt,idx), kind, val)
        self.trans = ("PARK",)     # first immediate transition wins; else ADVANCE/PARK


def _interp(path, is_death):
    st = Step()
    armed = False
    fixed = False   # an immediate transition already taken
    for item in path:
        if item[0] == "T":
            _, node, pol = item
            a = atom(node) if pol else GNot(atom(node))
            st.guard.append(_ctr_or(node, pol, a))
            continue
        node = item[1]
        tp = node["t"]
        if tp == "Send":
            recv, msgs = I.send_pairs(node)
            for sel, params in msgs:
                if sel == "newRoom" and params and not fixed:
                    r = I.as_int(params[0])
                    if r is not None:
                        st.trans = ("EXIT", r); fixed = True
                elif sel == "get" and I.is_global(recv, G_EGO) and params:
                    it = I.as_int(params[0])
                    if it is not None:
                        st.gets.append(it)
                elif sel == "changeState" and recv.get("t") == "Self" and params and not fixed:
                    k = I.as_int(params[0])
                    if k is not None:
                        st.trans = ("JUMP", k); fixed = True
            if M._is_cue_send(recv, msgs):
                armed = True
        elif tp == "Assignment":
            dst, src = node["kids"][0], node["kids"][1]
            if I.is_global(dst):
                v = I.as_int(src)
                if v is not None:
                    if is_death(dst["index"], v) and not fixed:
                        st.trans = ("DEATH",); fixed = True
                    elif v is not None:
                        st.writes.append((dst["index"], v))
            elif dst.get("t") == "Property" and dst.get("name") in ("seconds", "cycles"):
                armed = True
            elif dst.get("t") == "Property" and dst.get("name") == "state" and not fixed:
                k = I.as_int(src)
                if k is not None:
                    st.trans = ("SETSTATE", k); fixed = True
            elif dst.get("t") == "Variable" and dst["vtype"] in ("Local", "Temp"):
                st.counters.append(((dst["vtype"][0], dst["index"]), "set", I.as_int(src)))
        elif tp == "Increment" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            st.counters.append(((d["vtype"][0], d["index"]), "inc", None))
        elif tp == "Decrement" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            st.counters.append(((d["vtype"][0], d["index"]), "dec", None))
    if not fixed and armed:
        st.trans = ("ADVANCE",)
    return st


def _apply_counters(counters, updates):
    c = dict(counters)
    for (name, kind, val) in updates:
        if kind == "inc":
            c[name] = c.get(name, 0) + 1
        elif kind == "dec":
            c[name] = c.get(name, 0) - 1
        elif kind == "set" and val is not None:
            c[name] = val
    return c


def _ctr_holds(cond, counters):
    _, name, op, val = cond
    cur = counters.get(name, 0)
    return {"==": cur == val, "!=": cur != val, ">": cur > val, ">=": cur >= val,
            "<": cur < val, "<=": cur <= val}[op]


def compile_machine(machine, is_death):
    """-> (exits, deaths). exits = [(exit_room, guard_tree, {glob: val})], deaths =
    [guard_tree]. Guards are over EXTERNAL atoms only (counters resolved concretely)."""
    steps = {k: [_interp(p, is_death) for p in _paths_of(body)]
             for k, body in machine.bodies.items()}
    exits, deaths = [], []
    budget = [PATH_CAP]

    def walk(state, counters, guard, writes, depth, seen):
        if depth > COUNTER_CAP * 4 or budget[0] <= 0:
            return
        if state not in steps:
            # ABSENT state falls through to the next (SCI "wait for a later cue"); a
            # PRESENT state that only parks stops. Bound the fall-through.
            if state <= max(steps, default=0):
                walk(state + 1, counters, guard, writes, depth + 1, seen)
            return
        for st in steps[state]:
            budget[0] -= 1
            ext, ok = [], True
            for a in st.guard:
                if isinstance(a, tuple) and a and a[0] == "CTR":
                    if not _ctr_holds(a, counters):
                        ok = False
                        break
                elif a is not None:
                    ext.append(a)
            if not ok:
                continue
            ng = guard + ext
            nw = writes + st.writes
            nc = _apply_counters(counters, st.counters)
            tr = st.trans
            key = (state, tuple(sorted(nc.items())))
            if tr[0] == "EXIT":
                exits.append((tr[1], _conj(ng), dict(nw)))
            elif tr[0] == "DEATH":
                deaths.append(_conj(ng))
            elif key in seen:
                continue
            elif tr[0] == "ADVANCE":
                walk(state + 1, nc, ng, nw, depth + 1, seen | {key})
            elif tr[0] == "JUMP":
                walk(tr[1], nc, ng, nw, depth + 1, seen | {key})
            elif tr[0] == "SETSTATE":
                walk(tr[1] + 1, nc, ng, nw, depth + 1, seen | {key})
            # PARK: dead end (no exit from this path)

    walk(machine.start, {}, [], [], 0, frozenset())
    for k, eg in machine.entries:
        walk(k, {}, [eg] if eg is not None else [], [], 0, frozenset())
    return exits, deaths


def _ctr_or(node, pol, external_atom):
    """If the test is a Local/Temp vs literal comparison, tag it as a counter condition
    (the compiler resolves it against tracked counter values); else the external atom."""
    OPS = {"Eq": "==", "Ne": "!=", "Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<="}
    if node["t"] in OPS:
        a, b = node["kids"][0], node["kids"][1]
        loc = a if I.is_local_or_temp(a) else (b if I.is_local_or_temp(b) else None)
        num = I.as_int(b) if I.is_local_or_temp(a) else (I.as_int(a) if I.is_local_or_temp(b) else None)
        if loc is not None and num is not None:
            op = OPS[node["t"]]
            if not pol:
                op = {"==": "!=", "!=": "==", ">": "<=", ">=": "<", "<": ">=", "<=": ">"}[op]
            return ("CTR", (loc["vtype"][0], loc["index"]), op, num)
    return external_atom
