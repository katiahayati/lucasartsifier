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
    __slots__ = ("guard", "writes", "gets", "counters", "trans", "cues")

    def __init__(self):
        self.guard = []            # atoms (external) or ("CTR", (vt,idx), op, val)
        self.writes = []           # (glob, val)
        self.gets = []
        self.counters = []         # ((vt,idx), kind, val)
        self.trans = ("PARK",)     # first immediate transition wins; else ADVANCE/PARK
        self.cues = 0              # # of cues this path ARMS (each fires one `self cue:`)


def _count_cues_send(recv, msgs):
    """How many cues a single send ARMS (mirrors machine2._is_cue_send, but counts each
    cue-arming message rather than OR-ing them). Each armed cue completes later and drives
    one `(self cue:)` -> one changeState:+1."""
    n = 0
    for sel, params in msgs:
        if (params and params[-1].get("t") == "Self") or \
           (sel in ("cue", "setCycle", "setMotion", "setScript") and params
                and any(p.get("t") == "Self" for p in params)) or \
           (sel == "changeState" and recv.get("t") != "Self"):
            n += 1
    return n


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
            c = _count_cues_send(recv, msgs)
            if c:
                st.cues += c
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
                st.cues += 1
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


def carry_cues(steps_by_state, start):
    """Reclassify PARK -> ADVANCE where a prior state's SURPLUS cues carry through it.

    A state arming C cues emits C `(self cue:)`s: the first advances into the next state, the
    remaining C-1 are still pending and fire later, advancing subsequent no-delay states.
    `Script::doit` only cues on cycles/seconds, so a Print-only state (arms nothing) would
    PARK -- but a motion armed two states back with `... self` still completes and cues it
    onward (rm84 s78 arms `MoveTo 333 214 self` + `= cycles 12`; the timer cues s78->s79, the
    motion cue then carries s79->s80 past the Print-only s79 to s81's `= gIslandStatus 100`).
    Linear forward pass over the ADVANCE spine; conservative -- a PARK flips only when an
    incoming carried cue actually reaches it (a lone single-cue ADVANCE leaves 0 surplus, so
    normal chains never flip a downstream park)."""
    if not steps_by_state:
        return
    ks = sorted(steps_by_state)
    surplus = 0
    for K in range(min(ks[0], start), ks[-1] + 1):
        paths = steps_by_state.get(K)
        if paths is None:
            continue                       # absent state: SCI falls through, no cue consumed
        flow = [st for st in paths if st.trans[0] in ("PARK", "ADVANCE")]
        if not flow:
            surplus = 0                    # only immediate transitions here -> spine ends
            continue
        if surplus >= 1:                   # a carried cue reaches this state
            for st in flow:
                if st.trans[0] == "PARK":
                    st.trans = ("ADVANCE",)
        surplus = min(max(0, surplus + st.cues - 1) for st in flow)   # least carry (conservative)


def compress_chains(steps_by_state, entry_states, start):
    """Collapse maximal runs of effect-free unconditional ADVANCE states into a single hop.

    A cutscene like rm84Script marches through ~80 states that only burn animation cycles
    (each an unconditional ADVANCE with no writes/gets/counters/exit) -- ~80 steps of pure
    depth a nuXmv witness must unroll, for zero observable change. A `transparent` state is
    unobservable: single path, empty guard, ADVANCE, no effects, not an entry target, not the
    start. Redirect every transition that would land on such a state PAST the transparent run
    to the first non-transparent state (an ADVANCE becomes a JUMP to that state). Sound: the
    skipped states change nothing but the (unobserved) ms value; observationally identical, and
    the witness depth drops from ~80 to a handful. NOTE: keep the state VALUES (domain unchanged)
    -- only the transitions are rewritten, so guards/gates that name a surviving state still hold."""
    def transparent(J):
        sts = steps_by_state.get(J)
        if not sts or len(sts) != 1:
            return False
        st = sts[0]
        return (st.trans == ("ADVANCE",) and not st.guard and not st.writes
                and not st.gets and not st.counters
                and J not in entry_states and J != start)

    def skip(J):
        seen = set()
        while transparent(J) and J not in seen:
            seen.add(J)
            J += 1
        return J

    for K, sts in steps_by_state.items():
        for st in sts:
            t = st.trans
            if t[0] == "ADVANCE":
                tgt = skip(K + 1)
                if tgt != K + 1:
                    st.trans = ("JUMP", tgt)
            elif t[0] == "JUMP":
                tgt = skip(t[1])
                if tgt != t[1]:
                    st.trans = ("JUMP", tgt)
            elif t[0] == "SETSTATE":
                tgt = skip(t[1] + 1)          # SETSTATE k lands on k+1 (a cue advances)
                if tgt != t[1] + 1:
                    st.trans = ("JUMP", tgt)


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
    carry_cues(steps, machine.start)      # SCI cross-state cue carry: PARK -> ADVANCE where covered
    _entry_states = {k for k, _ in machine.entries} | {k for k, _ in machine.init_entries}
    compress_chains(steps, _entry_states, machine.start)   # collapse effect-free ADVANCE runs
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


def summarize_machine(machine, is_death, from_state=None):
    """Collapse a CUTSCENE machine (a room with NO player input -> its path is forced) to its
    net-effect SUMMARIES: walk from `from_state` (default start) to every EXIT/DEATH accumulating
    writes AND gets along the way. Returns [(exit_room|None, guard_tree, writes_dict, gets_list,
    is_death)]. Same walk as compile_machine but also carries gets and starts anywhere, so the
    whole cutscene (including effect-bearing states compress_chains can't touch) becomes ONE hop
    -- removing its depth. Called per ENTRY state (rm92 enters at 16/23/1/0 by gIslandStatus)."""
    steps = {k: [_interp(p, is_death) for p in _paths_of(body)]
             for k, body in machine.bodies.items()}
    carry_cues(steps, machine.start)
    _entry_states = {k for k, _ in machine.entries} | {k for k, _ in machine.init_entries}
    compress_chains(steps, _entry_states, machine.start)
    out = []
    budget = [PATH_CAP]

    def walk(state, counters, guard, writes, gets, depth, seen):
        if depth > COUNTER_CAP * 4 or budget[0] <= 0:
            return
        if state not in steps:
            if state <= max(steps, default=0):
                walk(state + 1, counters, guard, writes, gets, depth + 1, seen)
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
            ng, nw, ngets = guard + ext, writes + st.writes, gets + st.gets
            nc = _apply_counters(counters, st.counters)
            tr = st.trans
            key = (state, tuple(sorted(nc.items())))
            if tr[0] == "EXIT":
                out.append((tr[1], _conj(ng), dict(nw), list(ngets), False))
            elif tr[0] == "DEATH":
                out.append((None, _conj(ng), dict(nw), list(ngets), True))
            elif key in seen:
                continue
            elif tr[0] == "ADVANCE":
                walk(state + 1, nc, ng, nw, ngets, depth + 1, seen | {key})
            elif tr[0] == "JUMP":
                walk(tr[1], nc, ng, nw, ngets, depth + 1, seen | {key})
            elif tr[0] == "SETSTATE":
                walk(tr[1] + 1, nc, ng, nw, ngets, depth + 1, seen | {key})

    walk(machine.start if from_state is None else from_state, {}, [], [], [], 0, frozenset())
    return out


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
