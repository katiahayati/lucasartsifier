"""Compile a lifted machine (machine) into transition-system contributions:
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
from guard_ast import GAnd, GNot, Pred
from extract import atom, _conj, item_transfer, item_transfers, EGO
import machine as M

COUNTER_CAP = 40          # loop/unroll bound
PATH_CAP = 4000           # per-machine path budget


# ---- leaf-path enumeration through a state body --------------------------
def _paths_of(node):
    """List of paths through `node`; each path is a list of ('T', testnode, pol) and
    ('D', opnode) items in source order. Branches fan out; sequences compose.

    The control flow comes from `ir.control_shape`, shared with the three STREAMING walkers.
    Only the policy differs and legitimately so: they visit everything inside a loop, while this
    fans out "skipped" and "ran once". That split -- one shape, two policies -- is the whole
    point; what used to be duplicated was the shape, and `Loop` was missing from this copy."""
    if node is None:
        return [[]]
    shape = I.control_shape(node)
    kind = shape[0]
    if kind == "seq":
        return _seq(shape[1])
    if kind == "branch":
        out = []
        for conds, body in shape[1]:
            prefix = [("T", t, pol) for (t, pol) in conds]
            for p in _paths_of(body):
                out.append(prefix + p)
        return out or [[]]
    if kind == "loop":
        init, _test, incr, body = shape[1], shape[2], shape[3], shape[4]
        if body is None:
            return _seq([init])
        # N iterations are deliberately not modelled: the effects are monotone (a get is a get
        # however many times it happens) and the alternative is unbounded.
        return _seq([init]) + _seq([init, body, incr])
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
    __slots__ = ("guard", "writes", "gets", "counters", "trans", "cues", "drops", "moves",
                 "gincs")

    def __init__(self):
        self.guard = []            # atoms (external) or ("CTR", (vt,idx), op, val)
        self.writes = []           # (glob, val)
        self.gets = []
        self.counters = []         # ((vt,idx), kind, val)
        self.trans = ("PARK",)     # first immediate transition wins; else ADVANCE/PARK
        self.cues = 0              # # of cues this path ARMS (each fires one `self cue:`)
        self.drops = []            # items CONSUMED here (`gEgo put: N -1`). Consuming an item
        #   requires owning it, and some requirements have NO own() guard at all -- the Flower
        #   given to the KGBishnas (rm50) is only ever expressed as a `put: 20 -1`.
        self.moves = []            # (item, dest) -- gets+drops with the destination kept
        self.gincs = []            # (glob, delta) -- `(++ G)`/`(-- G)`. NOT a write: the new
        #   value depends on the old one, so it can only be resolved against the values that
        #   global is known to take. Fanned out per value in walk().


def _count_cues_send(recv, msgs):
    """How many cues a single send ARMS (mirrors machine._is_cue_send, but counts each
    cue-arming message rather than OR-ing them). Each armed cue completes later and drives
    one `(self cue:)` -> one changeState:+1."""
    n = 0
    for sel, params in msgs:
        # `self` anywhere in the arguments is the cue callback -- SCI1.1's Messager puts it
        # mid-list (`say: noun verb cond seq self room`) -- and `(self cue:)` with no arguments
        # is an IMMEDIATE self-cue. Kept in lockstep with machine._is_cue_send; a last-argument
        # test here read every speaking state as PARKing and truncated the cutscene there.
        if (any(isinstance(p, dict) and p.get("t") == "Self" for p in params)) or \
           (sel == "cue" and not params and recv.get("t") == "Self") or \
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
                elif sel == "changeState" and recv.get("t") == "Self" and params and not fixed:
                    k = I.as_int(params[0])
                    if k is not None:
                        st.trans = ("JUMP", k); fixed = True
                else:
                    # `gEgo get:/put:` and `(Inv at: N) moveTo:` are one operation -- see
                    # extract.item_transfer. Held (dest == EGO) is a get; anywhere else is a
                    # loss of ownership, whether that is limbo (-1, 999) or a spot in the world.
                    for (it, dest) in item_transfers(recv, sel, params):
                        st.moves.append((it, dest))
                        (st.gets if dest == EGO else st.drops).append(it)
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
            elif dst.get("t") == "Property" and dst.get("name") in ("seconds", "cycles", "ticks"):
                armed = True
                st.cues += 1
            elif dst.get("t") == "Property" and dst.get("name") == "state" and not fixed:
                k = I.as_int(src)
                if k is not None:
                    st.trans = ("SETSTATE", k); fixed = True
            elif dst.get("t") == "Variable" and dst["vtype"] in ("Local", "Temp"):
                st.counters.append(((dst["vtype"][0], dst["index"]), "set", I.as_int(src)))
        elif tp in ("Increment", "Decrement"):
            d = node["kids"][0]
            delta = 1 if tp == "Increment" else -1
            if I.is_local_or_temp(d):
                st.counters.append(((d["vtype"][0], d["index"]),
                                    "inc" if delta > 0 else "dec", None))
            elif I.is_global(d):
                # A counter kept in a GLOBAL. Every handler modelled this for locals only, so
                # LB2's `(++ global123)` -- the ONE statement that advances the act, and with it
                # the whole game -- was dropped, and no act boundary could ever seal.
                st.gincs.append((d["index"], delta))
        elif tp in ("PublicCall", "LocalCall"):
            # a proc-call CUE: `(procN ... self)`. SCI1 prints messages through a proc, so the
            # "message dismissed -> cue -> changeState:+1" completion is a proc call ending in
            # `self`, not a Send -- same cue semantics as `(x setMotion: ... self)`. rm214's
            # knockDoor advances its door-opening states this way.
            kids = node.get("kids") or []
            if kids and isinstance(kids[-1], dict) and kids[-1].get("t") == "Self":
                armed = True
                st.cues += 1
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


def step_effects(st):
    """Everything this step CHANGES, transition aside. ONE definition, consulted everywhere.

    `compress_chains` (which DELETES states it judges unobservable) and `opmodel._machine_info`
    (which drops whole machines) each carried their own list, and each list was written when the
    model had fewer stores. Neither counted `drops` or `moves`, so a state whose only effect was
    LOSING an item read as nothing at all: 4 such states in LSL2 (rm26 Cruise_Ticket, rm61
    Airline_Ticket, rm72 Stout_Stick, rm116 Million_Dollar_Bill) and 6 in KQ4, including rm15's
    frogActions dropping the Gold_Ball.

    Whenever a new store is added, this is the function to revisit -- and now it is the only one."""
    return bool(st.writes or st.gets or st.drops or st.moves or st.counters or st.gincs)


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
        return (st.trans == ("ADVANCE",) and not st.guard and not step_effects(st)
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


def _fan_globals(guard, writes, gincs, gdom):
    """Expand `(++ G)` / `(-- G)` into concrete (guard, writes) branches.

    A global counter is the shape LB2 builds its whole act structure on:

        (switch global123 (0 ...) (1 ...) ... (5 ...))     ; the act you are in
        ...
        (++ global123)                                     ; actBreak, the ONLY advance

    An increment cannot be a plain write because its result depends on the current value, so
    each branch pins one: guard `G == v`, write `G := v+delta`. Values come from what the
    machine's own script compares G against (machine.glob_dom) -- the same "read the literals
    the code tests against" rule extract._var_room_values uses for destinations.

    Yields the single unchanged branch when there is nothing to expand, so the common path
    allocates no more than before.
    """
    branches = [(guard, writes)]
    for (gi, delta) in gincs:
        dom = gdom.get(gi) or ()
        if not dom:
            continue                     # unknown domain -> drop the step, never guess
        nxt = []
        for (g0, w0) in branches:
            for v in dom:
                nxt.append((g0 + [Pred("CMP", var=gi, op="==", value=str(v))],
                            w0 + [(gi, v + delta)]))
        branches = nxt
    return branches


def step_paths(st, gdom):
    """A Step as the (guard, writes, gets, counters, trans) tuples the machine-state view uses.

    More than one when the step increments a global. compile_machine's walk and opmodel's
    per-state view must expand an increment IDENTICALLY, so this is the single place that
    decides how -- the alternative is the same rule in two places, which is how a fix lands
    and the output does not move.
    """
    return [(g, w, st.gets, st.counters, st.trans)
            for (g, w) in _fan_globals(st.guard, st.writes, st.gincs, gdom)]


def compile_machine(machine, is_death):
    """-> (exits, deaths). exits = [(exit_room, guard_tree, {glob: val})], deaths =
    [guard_tree]. Guards are over EXTERNAL atoms only (counters resolved concretely)."""
    gdom = getattr(machine, "glob_dom", {}) or {}
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
            nc = _apply_counters(counters, st.counters)
            tr = st.trans
            key = (state, tuple(sorted(nc.items())))
            # `(++ G)` is not a write -- the new value depends on the old one -- so the path
            # FANS OUT over the values G is known to take: one branch per value, each learning
            # `G == v` and delivering `G := v+delta`. A global with no known domain is dropped
            # rather than guessed, which is what keeps this inert on the games that only ever
            # increment a score.
            for (ng, nw) in _fan_globals(guard + ext, writes + st.writes, st.gincs, gdom):
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
    for i, (k, eg) in enumerate(machine.entries):
        # Seed the counters with the locals the arming context wrote (machine.entry_locals, parallel
        # to entries) -- knockDoor entered via the staff-use starts with local1==1 and can reach
        # newRoom:18; entered via "open the door" it starts with local1==0 and parks. See machine.py.
        loc = machine.entry_locals[i] if i < len(machine.entry_locals) else {}
        walk(k, dict(loc), [eg] if eg is not None else [], [], 0, frozenset())
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
