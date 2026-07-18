"""Emit our extracted transition system as SMV for nuXmv.

The engine spike (ENGINE-DIRECTION.md) showed: full reachable-set computation is
intractable for the promote-everything model, but TARGETED IC3 queries -- exactly what
our analysis needs -- are fast. So this emits the model as SMV and we drive nuXmv IC3.

Encoding: one nondeterministic `action` input selects which transition fires each step;
each `next(var)` is a case over the actions that touch it (others stutter). Rooms are an
enum of the real room ids; items are booleans; PROMOTED globals are concrete integer
ranges (lo..hi over the values they are set/compared/init'd to) so every write and
comparison is native and exact -- concrete game semantics, no abstraction. Opaque atoms
(Said/position) and untracked globals are fresh nondeterministic inputs: the player CAN
satisfy them (either polarity), matching our base closure's 3-valued "unknown".

`promote_globals=False` is the BASE model (registers are permissive/unknown, only items
bind). NOTE: the base model is MORE permissive than the old engine's base, which tracks
achievable register values -- so it under-catches register-gated requirements (sunscreen,
disguise, parachute). Those need promote_globals=True, which is the real target.
"""
from __future__ import annotations

from collections import defaultdict

from model import GAnd, GOr, GNot, Pred


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _has_pred(node):
    """True if the guard tree contains ANY predicate leaf (own/flag/cmp/opaque). A guard
    with none (empty conjunctions all the way down, or None) is genuinely unconditional --
    the line between an ENTRY reset and a conditional write (mirrors closure._has_any_pred)."""
    if node is None:
        return False
    if isinstance(node, Pred):
        return True
    if isinstance(node, (GAnd, GOr)):
        return any(_has_pred(k) for k in node.kids)
    if isinstance(node, GNot):
        return _has_pred(node.kid)
    return False


class Emitter:
    def __init__(self, m, game, promote_globals=False):
        # promote_globals: False (base), True (promote every set global), or an iterable
        # of global names to promote (targeted -- others stay permissive/unknown).
        self.m = m
        self.g = game
        self.promote = bool(promote_globals)
        self.promote_only = (None if promote_globals in (True, False)
                             else set(promote_globals))
        self.rooms = sorted(set(m.edges) | {b for a in m.edges for b in m.edges[a]})
        self.items = sorted(game.items)
        self.n_opaque = 0           # fresh nondet inputs for permissive/unknown atoms
        self.reg_range = {}         # gn -> (lo, hi): promoted, mutable registers
        self.const_val = {}         # gn -> int: compared but never set (frozen at init)
        if self.promote:
            self._classify_globals()

    @property
    def CFG(self):
        import config
        return config.ACTIVE

    def _classify_globals(self):
        m = self.m
        skip = set(getattr(self.CFG, "debug_globals", ())) | set(
            getattr(self.CFG, "timer_globals", ()))
        # every global we SET is a mutable register: range spans its set + compared +
        # init values (int only; non-int writes are dropped, which only makes the
        # register reach FEWER values -> gates stay closed -> over-require, the safe way).
        for gn in m.sets:
            if gn in skip or (self.promote_only is not None and gn not in self.promote_only):
                continue
            vals = set()
            for v in m.reg_tested.get(gn, ()):
                iv = _int(v)
                if iv is not None:
                    vals.add(iv)
            for _room, val, _g, _st in m.sets.get(gn, ()):
                iv = _int(val)
                if iv is not None:
                    vals.add(iv)
            for iv0 in m.init_flags.get(gn, {0}):
                iv = _int(iv0)
                if iv is not None:
                    vals.add(iv)
            if vals:
                lo, hi = min(vals | {0}), max(vals | {0})
                if lo == hi:
                    self.const_val[gn] = lo   # only ever one value -> a constant
                else:
                    self.reg_range[gn] = (lo, hi)
        # globals COMPARED but never set are constants: freeze at init, const-fold gates.
        for gn, vals in m.reg_tested.items():
            if gn in self.reg_range or gn in skip:
                continue
            if self.promote_only is not None and gn not in self.promote_only:
                continue
            init = None
            for iv0 in m.init_flags.get(gn, ()):
                init = _int(iv0)
                break
            self.const_val[gn] = 0 if init is None else init

    # ---- guard -> SMV boolean expression -------------------------------
    def expr(self, node):
        if node is None:
            return "TRUE"
        if isinstance(node, GAnd):
            ks = [self.expr(k) for k in node.kids]
            if any(k == "FALSE" for k in ks):
                return "FALSE"
            ks = [k for k in ks if k != "TRUE"]
            return "(" + " & ".join(ks) + ")" if ks else "TRUE"
        if isinstance(node, GOr):
            ks = [self.expr(k) for k in node.kids]
            if any(k == "TRUE" for k in ks):
                return "TRUE"
            ks = [k for k in ks if k != "FALSE"]
            return "(" + " | ".join(ks) + ")" if ks else "FALSE"
        if isinstance(node, GNot):
            inner = self.expr(node.kid)
            if inner == "TRUE":
                return "FALSE"
            if inner == "FALSE":
                return "TRUE"
            return f"!({inner})"   # parens: ! binds tighter than != in SMV
        if isinstance(node, Pred):
            return self._pred(node)
        return "TRUE"

    def _permissive(self):
        # Fresh nondeterministic boolean input. An "unknown" atom (opaque player action,
        # or an untracked global) is satisfiable in BOTH polarities: the player can do it
        # or not. A constant TRUE would make NOT(atom)=FALSE and wrongly kill the edge --
        # this matches the base closure's 3-valued "unknown".
        k = self.n_opaque
        self.n_opaque += 1
        return f"opq{k}"

    def _cmp(self, gv, op, val):
        op = "=" if op == "==" else op          # SMV uses single = for equality
        return f"{gv} {op} {val}"

    def _const_cmp(self, cur, op, val):
        if op in ("==", "="):
            return "TRUE" if cur == val else "FALSE"
        if op == "!=":
            return "TRUE" if cur != val else "FALSE"
        if op == ">":
            return "TRUE" if cur > val else "FALSE"
        if op == "<":
            return "TRUE" if cur < val else "FALSE"
        if op == ">=":
            return "TRUE" if cur >= val else "FALSE"
        if op == "<=":
            return "TRUE" if cur <= val else "FALSE"
        return "TRUE"

    def _pred(self, p):
        if p.kind == "OWN":
            return f"item{p.var}"
        if not self.promote:
            return self._permissive()
        if p.kind == "FLAG":
            if p.var in self.reg_range:
                return f"{self._gv(p.var)} != 0"
            if p.var in self.const_val:
                return "TRUE" if self.const_val[p.var] != 0 else "FALSE"
            return self._permissive()
        if p.kind == "CMP":
            val = _int(p.value)
            if val is None:
                return self._permissive()
            if p.var in self.reg_range:
                return self._cmp(self._gv(p.var), p.op, val)
            if p.var in self.const_val:
                return self._const_cmp(self.const_val[p.var], p.op, val)
            return self._permissive()
        return self._permissive()   # POS / SAID / OPAQUE

    def _gv(self, gname):
        return f"g_{gname}"

    # ---- build the SMV ------------------------------------------------
    def emit(self):
        m = self.m
        # actions (expr() calls allocate opaque inputs, so build these before headers)
        moves = []
        for a in m.edges:
            for b in m.edges[a]:
                gd = (m.machine_guards.get((a, b)) if (a, b) in m.machine_edges
                      else m.edge_reqs.get((a, b)))
                moves.append((a, b, self.expr(gd)))
        acqs = []
        for it, sites in m.acq.items():
            for room, gd in sites:
                if room is not None:
                    acqs.append((room, it, self.expr(gd)))
        # A death write (game.is_death_write) is TERMINAL, not a live register value: it
        # latches `dead`, and reaching the goal while dead is not winning. Collected
        # regardless of promotion -- death poisons the state either way. Avoidable deaths
        # (permissive guards) never force `dead`; only forced ones (a promoted register
        # value that must hold) block winning, so promotion sharpens which deaths bind.
        # ENTRY writes (unconditional, st is None, no guard pred) are FORCED on room
        # entry -- they overwrite the arriving value, so the player cannot skip rm64's
        # gCurrentStatus:=12. SELF writes (guarded or inside a changeState) are OPTIONAL
        # in-room actions that ADD a value; the register persists across a plain move, so
        # SELF+persistence already delivers the value downstream (== the old engine's
        # self/exit union). Death writes latch `dead`.
        self_writes = []
        deaths = []
        entry_writes = defaultdict(dict)     # room -> {gn: entry-value}  (last wins)
        for gn, sites in m.sets.items():
            for room, val, gd, st in sites:
                if room is None:
                    continue
                if self.g.is_death_write(gn, val):
                    deaths.append((room, self.expr(gd)))
                    continue
                if not (self.promote and gn in self.reg_range):
                    continue
                iv = _int(val)
                if iv is None:
                    continue
                if st is None and not _has_pred(gd):
                    entry_writes[room][gn] = iv
                else:
                    self_writes.append((room, gn, iv, self.expr(gd)))
        n_act = len(moves) + len(acqs) + len(self_writes) + len(deaths)

        L = ["MODULE main", "IVAR", f"  action : 0 .. {max(0, n_act - 1)};"]
        for k in range(self.n_opaque):
            L.append(f"  opq{k} : boolean;")
        L.append("VAR")
        L.append("  room : {" + ", ".join(str(r) for r in self.rooms) + "};")
        L.append("  dead : boolean;")
        for it in self.items:
            L.append(f"  item{it} : boolean;")
        for gn, (lo, hi) in self.reg_range.items():
            L.append(f"  {self._gv(gn)} : {lo} .. {hi};")

        L.append("ASSIGN")
        L.append(f"  init(room) := {self.CFG.start_room};")
        L.append("  init(dead) := FALSE;")
        for it in self.items:
            L.append(f"  init(item{it}) := FALSE;")
        start = self.CFG.start_room
        for gn, (lo, hi) in self.reg_range.items():
            if gn in entry_writes.get(start, {}):     # start-room reset applies at init
                iv = entry_writes[start][gn]
            else:
                iv = None
                for iv0 in m.init_flags.get(gn, ()):
                    iv = _int(iv0)
                    break
                iv = iv if (iv is not None and lo <= iv <= hi) else lo
            L.append(f"  init({self._gv(gn)}) := {iv};")

        # next(room)
        L.append("  next(room) := case")
        for k, (a, b, ge) in enumerate(moves):
            cond = f"action = {k} & room = {a}"
            if ge != "TRUE":
                cond += " & " + ge
            L.append(f"    {cond} : {b};")
        L.append("    TRUE : room;")
        L.append("  esac;")

        # next(itemI)
        base_acq = len(moves)
        by_item = {}
        for j, (room, it, ge) in enumerate(acqs):
            by_item.setdefault(it, []).append((base_acq + j, room, ge))
        for it in self.items:
            L.append(f"  next(item{it}) := case")
            for aid, room, ge in by_item.get(it, []):
                cond = f"action = {aid} & room = {room}"
                if ge != "TRUE":
                    cond += " & " + ge
                L.append(f"    {cond} : TRUE;")
            L.append(f"    TRUE : item{it};")
            L.append("  esac;")

        # next(global): forced ENTRY writes piggyback on move-into-room actions
        # (they fire with the move, overwriting), then OPTIONAL in-room SELF writes.
        base_self = len(moves) + len(acqs)
        self_by_g = defaultdict(list)
        for j, (room, gn, v, ge) in enumerate(self_writes):
            self_by_g[gn].append((base_self + j, room, v, ge))
        for gn in self.reg_range:
            L.append(f"  next({self._gv(gn)}) := case")
            for k, (a, b, ge) in enumerate(moves):
                if gn in entry_writes.get(b, {}):
                    cond = f"action = {k} & room = {a}"
                    if ge != "TRUE":
                        cond += " & " + ge
                    L.append(f"    {cond} : {entry_writes[b][gn]};")
            for aid, room, v, ge in self_by_g.get(gn, []):
                cond = f"action = {aid} & room = {room}"
                if ge != "TRUE":
                    cond += " & " + ge
                L.append(f"    {cond} : {v};")
            L.append(f"    TRUE : {self._gv(gn)};")
            L.append("  esac;")

        # next(dead): latches TRUE on any death action, never clears
        base_d = len(moves) + len(acqs) + len(self_writes)
        L.append("  next(dead) := case")
        for j, (room, ge) in enumerate(deaths):
            cond = f"action = {base_d + j} & room = {room}"
            if ge != "TRUE":
                cond += " & " + ge
            L.append(f"    {cond} : TRUE;")
        L.append("    TRUE : dead;")
        L.append("  esac;")

        # winnable = reach a goal room ALIVE; invariant violated => such a state exists
        goals = " | ".join(f"room = {r}" for r in sorted(self.CFG.goal_rooms))
        L.append(f"INVARSPEC !(({goals}) & !dead);")
        return "\n".join(L) + "\n", n_act


def emit_smv(m, game, promote_globals=False):
    return Emitter(m, game, promote_globals).emit()
