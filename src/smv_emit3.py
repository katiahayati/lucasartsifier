"""Operational SMV emitter (promote EVERYTHING, no counter/register judgment).

Instead of compiling machines to guards (which forces resolving loop counters concretely
-- the counter-vs-register judgment), this emits each machine's `state`, its counters, and
its gating locals as TRACKED SMV variables and lets nuXmv run the loops symbolically.
Uniform treatment: `day`, `henchStatus`, `state`, and every written global are all just
tracked variables; the abstraction (IC3) deals with them.

Per gating machine M in room R (an object with a changeState that has an EXIT/WRITE/DEATH/
GET effect): a state var msM (reset to M.start whenever room!=R), and its gating locals as
promoted vars (reset when away). A step action at (room=R, msM=K) fires one path of state
K: applies its writes/gets/counters and transitions msM (ADVANCE->K+1, JUMP j, SETSTATE
j+1, EXIT->room:=r, DEATH->dead). Player entries (handleEvent changeState:K, guarded) set
msM. init writes are forced on entry. Movement/item edges come from extract2 (flat).

Guards: OWN->item; CMP on a promoted global-> the tracked var; CTR (Local vs literal)->
the tracked counter var; opaque/untracked-> a fresh nondet input (satisfiable both ways).
"""
from __future__ import annotations

import os
import subprocess

import ir as I
import machine2 as M
import compile2 as C
from extract2 import extract, atom
from model import GAnd, GOr, GNot, Pred


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _cmp_const(cur, op, val):
    op = "==" if op == "=" else op
    return {"==": cur == val, "!=": cur != val, ">": cur > val, ">=": cur >= val,
            "<": cur < val, "<=": cur <= val}.get(op, True)


def _conj_atoms(atoms):
    atoms = [a for a in atoms if a is not None]
    if not atoms:
        return None
    return atoms[0] if len(atoms) == 1 else GAnd(list(atoms))


class OpEmitter:
    def __init__(self, ir, cfg, is_death):
        self.ir = ir
        self.cfg = cfg
        self.is_death = is_death
        self.ts = extract(ir)
        self.mb = M.MachineBuilder(ir, is_death)
        self.n_opaque = 0
        self._collect()

    # ---- collection --------------------------------------------------
    def _collect(self):
        ir = self.ir
        self.rooms = sorted(self.ts.rooms)
        self.items = sorted(self.ts.items)
        # machines with an effect, per room; each -> (room, inst, states-as-paths, entries, start)
        self.machines = []          # list of dict
        self.reg_vals = {}          # global index -> set of int values (domain)
        self.loc_vals = {}          # (script, 'L'/'T', idx) -> set of int values
        self.init_writes = {}       # room -> {gi: val} forced on entry
        self.deaths = []            # (room, guard) flat/machine deaths
        self.procs_by = {}          # (script, proc-name) -> body AST, for call-following
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body
        for rn, s in ir.scripts.items():
            if rn not in self.ts.rooms:
                continue
            self._init_writes(rn, s)
            for m in self.mb.machines(s):
                info = self._machine_info(rn, m)
                if info:
                    self.machines.append(info)
        # player-action effects in handleEvent/doit: register writes + item get/put that
        # the game does NOT do via a changeState machine (e.g. `(= gLoweredLifeboats 1)`
        # when the player says "lower lifeboats"). Guard = the path condition (Said/opaque
        # permissive). Without these, promoted gates like `gLoweredLifeboats!=0` can never
        # open. Same shape as the disguise's gCurrentEgoView.
        self.handler_writes = []       # (room, gi, val, guard)
        self.handler_gets = []         # (room, item, guard)
        self.handler_locals = []       # (room, script, (vt,idx), val, guard)
        for rn, s in ir.scripts.items():
            if rn not in self.ts.rooms:
                continue
            for o in s.objects:
                for mn, body in o.methods.items():
                    # changeState -> machine (state-sequenced); init -> forced entry write.
                    # EVERY other method's effects are captured here (globals + locals +
                    # gets), FOLLOWING calls into other scripts, so nothing is absent.
                    if mn in ("changeState", "init"):
                        continue
                    self._hwalk(rn, rn, body, [], set())
            for pbody in s.procs.values():
                self._hwalk(rn, rn, pbody, [], set())
        for room, gi, v, g in self.handler_writes:
            self.reg_vals.setdefault(gi, {0}).add(v)
        for room, script, key, v, g in self.handler_locals:
            self.loc_vals.setdefault((script,) + key, {0})
            if isinstance(v, int):
                self.loc_vals[(script,) + key].add(v)
        # domains: include compared values for globals/locals too (scan all machine guards)
        for info in self.machines:
            for K, paths in info["states"].items():
                for (guard, writes, gets, counters, trans) in paths:
                    for gi, v in writes:
                        self.reg_vals.setdefault(gi, {0}).add(v)
                    for name, kind, val in counters:
                        key = (info["script"],) + name
                        self.loc_vals.setdefault(key, {0})
                        if val is not None:
                            self.loc_vals[key].add(val)
                    self._scan_domains(guard, info["script"])
            for K, eg in info["entries"]:
                self._scan_domains_guard(eg, info["script"])
        for room, wr in self.init_writes.items():
            for gi, v in wr.items():
                self.reg_vals.setdefault(gi, {0}).add(v)
        # finalize domains; single-value dims fold to constants (SMV rejects init on them)
        self.reg_dom, self.reg_const = {}, {}
        for gi, vs in self.reg_vals.items():
            lo, hi = min(vs), max(vs)
            (self.reg_const if lo == hi else self.reg_dom)[gi] = lo if lo == hi else (lo, hi)
        self.loc_dom, self.loc_const = {}, {}
        for k, vs in self.loc_vals.items():
            lo, hi = min(vs), max(vs)
            (self.loc_const if lo == hi else self.loc_dom)[k] = lo if lo == hi else (lo, hi)

    def _inline_calls(self, node, script, seen, depth=0):
        """Return a copy of the AST with PublicCall/LocalCall replaced by the callee's
        body (across scripts), so effects in shared procedures (e.g. proc0_2's
        gCurrentStatus:=0 reset at a changeState cutscene end) are captured in the
        machine's control flow. Params are not substituted -- we capture concrete-valued
        effects; param-valued writes drop out (conservative)."""
        if node is None or depth > 6:
            return node
        if node["t"] in ("PublicCall", "LocalCall"):
            tgt = node.get("script", script)
            name = node.get("name")
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                return self._inline_calls(body, tgt, seen | {name}, depth + 1)
            return node
        new = dict(node)
        new["kids"] = [self._inline_calls(k, script, seen, depth) for k in node.get("kids", [])]
        return new

    def _machine_info(self, room, m):
        states = {}
        has_effect = False
        for K, body in m.bodies.items():
            body = self._inline_calls(body, m.script, set())
            paths = []
            for p in C._paths_of(body):
                st = C._interp(p, self.is_death)
                if st.writes or st.gets or st.trans[0] in ("EXIT", "DEATH"):
                    has_effect = True
                paths.append((st.guard, st.writes, st.gets, st.counters, st.trans))
            states[K] = paths
        if not has_effect:
            return None
        return {"room": room, "inst": m.inst, "script": m.script,
                "states": states, "entries": m.entries, "start": m.start}

    def _hwalk(self, room, script, node, pc, seen):
        """Path-condition walk of a handler; record global + local writes + item gets,
        FOLLOWING PublicCall/LocalCall into their procedures (across scripts)."""
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            a = atom(ks[0])
            self._hwalk(room, script, ks[1], pc + [a], seen)
            if len(ks) > 2:
                self._hwalk(room, script, ks[2], pc + [GNot(a) if a else None], seen)
            return
        if tp == "Cond":
            for c in node["kids"]:
                if c["t"] == "Case":
                    self._hwalk(room, script, c["kids"][1], pc + [atom(c["kids"][0])], seen)
                elif c["t"] == "Else":
                    self._hwalk(room, script, c["kids"][0], pc, seen)
            return
        if tp == "Assignment":
            dst, src = node["kids"][0], node["kids"][1]
            v = _int(src.get("value"))
            if I.is_global(dst) and v is not None and not self.is_death(dst["index"], v):
                self.handler_writes.append((room, dst["index"], v, _conj_atoms(pc)))
            elif I.is_local_or_temp(dst):
                self.handler_locals.append((room, script, (dst["vtype"][0], dst["index"]),
                                            v, _conj_atoms(pc)))
        elif tp == "Increment" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("inc",), _conj_atoms(pc)))
        elif tp == "Decrement" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("dec",), _conj_atoms(pc)))
        elif tp == "Send":
            recv, msgs = I.send_pairs(node)
            for sel, params in msgs:
                if sel == "get" and I.is_global(recv, 0) and params:
                    it = _int(params[0].get("value"))
                    if it is not None:
                        self.handler_gets.append((room, it, _conj_atoms(pc)))
        elif tp in ("PublicCall", "LocalCall"):
            self._follow_call(room, script, node, pc, seen)
        for k in node.get("kids", ()):
            self._hwalk(room, script, k, pc, seen)

    def _follow_call(self, room, script, node, pc, seen):
        tgt_script = node.get("script", script)   # PublicCall carries its script; Local = same
        if tgt_script == 255:                      # script 255 = Print/Dialog: text, no effect
            return
        name = node.get("name")
        body = self.procs_by.get((tgt_script, name))
        if body is None or name in seen:
            return
        self._hwalk(room, tgt_script, body, pc, seen | {name})

    def _init_writes(self, room, script):
        obj = script.by_name.get(f"rm{room}")
        if obj is None or "init" not in obj.methods:
            return
        # forced-on-entry global writes, FOLLOWING calls (e.g. proc0_2 = the hands-on
        # reset gCurrentStatus:=0, called from 66 room inits). Source order -> last wins.
        self._init_walk(room, script.number, obj.methods["init"], set())

    def _init_walk(self, room, script, node, seen):
        if node is None:
            return
        tp = node["t"]
        if tp == "Assignment" and I.is_global(node["kids"][0]):
            gi, v = node["kids"][0]["index"], _int(node["kids"][1].get("value"))
            if v is not None and not self.is_death(gi, v):
                self.init_writes.setdefault(room, {})[gi] = v
        elif tp in ("PublicCall", "LocalCall"):
            tgt = node.get("script", script)
            name = node.get("name")
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._init_walk(room, tgt, body, seen | {name})
        for k in node.get("kids", ()):
            self._init_walk(room, script, k, seen)

    def _scan_domains(self, guard, script):
        for a in guard:
            if isinstance(a, tuple) and a and a[0] == "CTR":
                key = (script,) + a[1]
                self.loc_vals.setdefault(key, {0}).add(a[3])
            else:
                self._scan_domains_guard(a, script)

    def _scan_domains_guard(self, g, script):
        if isinstance(g, Pred) and g.kind == "CMP":
            v = _int(g.value)
            if v is not None:
                self.reg_vals.setdefault(g.var, {0}).add(v)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                self._scan_domains_guard(k, script)
        elif isinstance(g, GNot):
            self._scan_domains_guard(g.kid, script)

    # ---- guard -> SMV ------------------------------------------------
    def _permissive(self):
        k = self.n_opaque
        self.n_opaque += 1
        return f"opq{k}"

    def gexpr(self, g, script):
        """External guard tree -> SMV; script gives the counter namespace for CTR."""
        if g is None:
            return "TRUE"
        if isinstance(g, tuple) and g and g[0] == "CTR":
            key = (script,) + g[1]
            if key in self.loc_dom:
                op = "=" if g[2] == "==" else g[2]
                return f"{self._lv(key)} {op} {g[3]}"
            if key in self.loc_const:
                return "TRUE" if _cmp_const(self.loc_const[key], g[2], g[3]) else "FALSE"
            return self._permissive()
        if isinstance(g, GAnd):
            ks = [self.gexpr(k, script) for k in g.kids]
            if "FALSE" in ks:
                return "FALSE"
            ks = [k for k in ks if k != "TRUE"]
            return "(" + " & ".join(ks) + ")" if ks else "TRUE"
        if isinstance(g, GOr):
            ks = [self.gexpr(k, script) for k in g.kids]
            if "TRUE" in ks:
                return "TRUE"
            ks = [k for k in ks if k != "FALSE"]
            return "(" + " | ".join(ks) + ")" if ks else "FALSE"
        if isinstance(g, GNot):
            inner = self.gexpr(g.kid, script)
            if inner == "TRUE":
                return "FALSE"
            if inner == "FALSE":
                return "TRUE"
            return f"!({inner})"
        if isinstance(g, Pred):
            if g.kind == "OWN":
                return f"item{g.var}"
            if g.kind == "CMP":
                v = _int(g.value)
                if v is None:
                    return self._permissive()
                if g.var in self.reg_dom:
                    op = "=" if g.op == "==" else g.op
                    return f"{self._gv(g.var)} {op} {v}"
                if g.var in self.reg_const:
                    return "TRUE" if _cmp_const(self.reg_const[g.var], g.op, v) else "FALSE"
            return self._permissive()
        return "TRUE"

    def _gv(self, gi):
        return f"g_{gi}"

    def _lv(self, key):
        return f"c_{key[0]}_{key[1]}_{key[2]}"

    def _inc(self, key):
        lo, hi = self.loc_dom[key]
        lv = self._lv(key)
        return f"({lv} >= {hi} ? {hi} : {lv} + 1)"    # saturate at hi (no SMV overflow)

    def _dec(self, key):
        lo, hi = self.loc_dom[key]
        lv = self._lv(key)
        return f"({lv} <= {lo} ? {lo} : {lv} - 1)"

    def _ms(self, info):
        safe = "".join(ch if ch.isalnum() else "_" for ch in info["inst"])
        return f"ms_{info['room']}_{safe}"

    # ---- emit --------------------------------------------------------
    def emit(self):
        from collections import defaultdict
        nxt = defaultdict(list)          # var -> [(cond, value)]
        room_change = []                 # (aid, src_cond, target_room) for init-write bundling
        aid = 0

        def cond(base, guard):
            return base + (" & " + guard if guard not in ("TRUE", "") else "")

        # flat movement edges
        for e in self.ts.edges:
            g = self.gexpr(e.guard, None)
            if g == "FALSE":
                continue
            c = cond(f"action = {aid} & room = {e.src}", g)
            nxt["room"].append((c, str(e.dst)))
            room_change.append((c, e.dst))
            aid += 1
        # flat item acquisitions
        for a in self.ts.acqs:
            g = self.gexpr(a.guard, None)
            if g == "FALSE":
                continue
            nxt[f"item{a.item}"].append((cond(f"action = {aid} & room = {a.room}", g), "TRUE"))
            aid += 1
        # machine steps + entries
        for info in self.machines:
            ms = self._ms(info)
            R = info["room"]
            for K, paths in info["states"].items():
                for (guard, writes, gets, counters, trans) in paths:
                    ext = [a for a in guard]
                    g = self._conj_expr(ext, info["script"])
                    if g == "FALSE":
                        continue
                    base = cond(f"action = {aid} & room = {R} & {ms} = {K}", g)
                    tk = trans[0]
                    if tk == "EXIT":
                        nxt["room"].append((base, str(trans[1])))
                        room_change.append((base, trans[1]))
                    elif tk == "DEATH":
                        nxt["dead"].append((base, "TRUE"))
                    elif tk == "ADVANCE":
                        nxt[ms].append((base, str(K + 1)))
                    elif tk == "JUMP":
                        nxt[ms].append((base, str(trans[1])))
                    elif tk == "SETSTATE":
                        nxt[ms].append((base, str(trans[1] + 1)))
                    for gi, v in writes:
                        if gi in self.reg_dom:
                            nxt[self._gv(gi)].append((base, str(v)))
                    for it in gets:
                        nxt[f"item{it}"].append((base, "TRUE"))
                    for name, kind, val in counters:
                        key = (info["script"],) + name
                        if key in self.loc_dom:
                            lv = self._lv(key)
                            if kind == "inc":
                                nxt[lv].append((base, self._inc(key)))
                            elif kind == "dec":
                                nxt[lv].append((base, self._dec(key)))
                            elif kind == "set" and val is not None:
                                nxt[lv].append((base, str(val)))
                    aid += 1
            for K, eg in info["entries"]:
                g = self.gexpr(eg, info["script"])
                if g == "FALSE":
                    continue
                nxt[ms].append((cond(f"action = {aid} & room = {R}", g), str(K)))
                aid += 1

        # player-action effects (handleEvent/doit register writes + item gets)
        for room, gi, v, g in self.handler_writes:
            if gi not in self.reg_dom:
                continue
            ge = self.gexpr(g, None)
            if ge == "FALSE":
                continue
            nxt[self._gv(gi)].append((cond(f"action = {aid} & room = {room}", ge), str(v)))
            aid += 1
        for room, it, g in self.handler_gets:
            ge = self.gexpr(g, None)
            if ge == "FALSE":
                continue
            nxt[f"item{it}"].append((cond(f"action = {aid} & room = {room}", ge), "TRUE"))
            aid += 1
        for room, script, name, v, g in self.handler_locals:
            key = (script,) + name
            if key not in self.loc_dom:
                continue
            ge = self.gexpr(g, script)
            if ge == "FALSE":
                continue
            lv = self._lv(key)
            if v == ("inc",):
                val = self._inc(key)
            elif v == ("dec",):
                val = self._dec(key)
            elif isinstance(v, int):
                lo, hi = self.loc_dom[key]
                if not (lo <= v <= hi):
                    continue
                val = str(v)
            else:
                continue
            nxt[lv].append((cond(f"action = {aid} & room = {room}", ge), val))
            aid += 1

        # init writes forced on entering a room (bundle onto every room-changing action)
        for c, target in room_change:
            for gi, v in self.init_writes.get(target, {}).items():
                if gi in self.reg_dom:
                    nxt[self._gv(gi)].insert(0, (c, str(v)))   # entry write wins (first)

        n_act = max(1, aid)
        return self._render(nxt, n_act)

    def _conj_expr(self, atoms, script):
        parts = [self.gexpr(a, script) for a in atoms]
        if "FALSE" in parts:
            return "FALSE"
        parts = [p for p in parts if p != "TRUE"]
        return "(" + " & ".join(parts) + ")" if parts else "TRUE"

    def _render(self, nxt, n_act):
        L = ["MODULE main", "IVAR", f"  action : 0 .. {n_act - 1};"]
        for k in range(self.n_opaque):
            L.append(f"  opq{k} : boolean;")
        L.append("VAR")
        L.append("  room : {" + ", ".join(str(r) for r in self.rooms) + "};")
        L.append("  dead : boolean;")
        for it in self.items:
            L.append(f"  item{it} : boolean;")
        for gi, (lo, hi) in self.reg_dom.items():
            L.append(f"  {self._gv(gi)} : {lo} .. {hi};")
        for key, (lo, hi) in self.loc_dom.items():
            L.append(f"  {self._lv(key)} : {lo} .. {hi};")
        for info in self.machines:
            ks = sorted(info["states"])
            lo, hi = min(ks + [info["start"]]), max(ks + [info["start"]])
            L.append(f"  {self._ms(info)} : {lo} .. {hi};")

        L.append("ASSIGN")
        start = self.cfg.start_room
        L.append(f"  init(room) := {start};")
        L.append("  init(dead) := FALSE;")
        for it in self.items:
            L.append(f"  init(item{it}) := FALSE;")
        for gi, (lo, hi) in self.reg_dom.items():
            iv = self.init_writes.get(start, {}).get(gi)
            iv = iv if (iv is not None and lo <= iv <= hi) else self._reg_init(gi, lo, hi)
            L.append(f"  init({self._gv(gi)}) := {iv};")
        for key, (lo, hi) in self.loc_dom.items():
            L.append(f"  init({self._lv(key)}) := {0 if lo <= 0 <= hi else lo};")
        for info in self.machines:
            L.append(f"  init({self._ms(info)}) := {info['start']};")

        # next() for each variable
        self._emit_next(L, "room", nxt, "room")
        self._emit_next(L, "dead", nxt, "dead", latch=True)
        for it in self.items:
            self._emit_next(L, f"item{it}", nxt, f"item{it}", latch=True)
        for gi in self.reg_dom:
            self._emit_next(L, self._gv(gi), nxt, self._gv(gi))
        for key in self.loc_dom:
            self._emit_counter_next(L, key, nxt)
        for info in self.machines:
            self._emit_ms_next(L, info, nxt)

        goals = " | ".join(f"room = {r}" for r in sorted(self.cfg.goal_rooms))
        L.append(f"INVARSPEC !(({goals}) & !dead);")
        return "\n".join(L) + "\n", n_act

    def _reg_init(self, gi, lo, hi):
        for iv0 in self.ir.script(0).locals:
            if iv0["index"] == gi:
                v = iv0["value"]
                return v if lo <= v <= hi else lo
        return 0 if lo <= 0 <= hi else lo

    def _emit_next(self, L, var, nxt, key, latch=False):
        cases = nxt.get(key, [])
        if not cases:
            return
        L.append(f"  next({var}) := case")
        for c, v in cases:
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {var};")
        L.append("  esac;")

    def _emit_counter_next(self, L, key, nxt):
        lv = self._lv(key)
        script = key[0]
        rooms = [info["room"] for info in self.machines if info["script"] == script]
        L.append(f"  next({lv}) := case")
        if rooms:  # reset to 0 when not in the owning room(s)
            away = " & ".join(f"room != {r}" for r in sorted(set(rooms)))
            L.append(f"    {away} : 0;")
        for c, v in nxt.get(lv, []):
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {lv};")
        L.append("  esac;")

    def _emit_ms_next(self, L, info, nxt):
        ms = self._ms(info)
        R = info["room"]
        L.append(f"  next({ms}) := case")
        L.append(f"    room != {R} : {info['start']};")   # reset/park to start when away
        for c, v in nxt.get(ms, []):
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {ms};")
        L.append("  esac;")


def _find_nuxmv():
    for c in (os.environ.get("NUXMV"),
              os.path.join(os.environ.get("CLAUDE_JOB_DIR", ""), "tmp",
                           "nuXmv-2.0.0-Linux", "bin", "nuXmv")):
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("nuXmv not found")


def winnable(em, pin_items_off=(), timeout=900):
    smv, _ = em.emit()
    for it in pin_items_off:
        # force item permanently FALSE: replace its next-block with a constant
        lines = smv.splitlines()
        out, i = [], 0
        while i < len(lines):
            if lines[i].strip() == f"next(item{it}) := case":
                out.append(f"  next(item{it}) := FALSE;")
                i += 1
                while i < len(lines) and lines[i].strip() != "esac;":
                    i += 1
                i += 1
                continue
            out.append(lines[i]); i += 1
        smv = "\n".join(out) + "\n"
    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "op.smv")
    with open(tmp, "w") as f:
        f.write(smv)
    cmds = f"read_model -i {tmp}\ngo_msat\ncheck_invar_ic3\nquit\n"
    p = subprocess.run([_find_nuxmv(), "-int"], input=cmds, capture_output=True,
                       text=True, timeout=timeout)
    out = p.stdout + p.stderr
    for line in out.splitlines():
        low = line.lower()
        if "is false" in low:
            return True
        if "is true" in low:
            return False
    raise RuntimeError("no verdict:\n" + out[-2000:])
