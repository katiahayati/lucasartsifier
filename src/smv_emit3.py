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
from extract2 import extract, atom, item_transfer, _room_object, EGO
from guard_ast import GAnd, GOr, GNot, Pred


MAIN_SCRIPT = 0     # script 0 -- the Game subclass. A dispatch SCOPE, never a room.
                    # missability.GLOBAL_SCRIPTS is the consumer-side half of the same fact.


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
        self._loc_inc = set()       # counter keys with an inc op (need +1 saturation headroom)
        self._loc_dec = set()       # counter keys with a dec op (need -1 headroom)
        self.init_writes = {}       # room -> {gi: val} UNCONDITIONAL entry writes (initial value)
        self.init_seq = {}          # room -> ordered [(gi, val, guard)] entry writes, source order.
        #   Conditional init writes (inside if/cond) keep their guard instead of being FORCED --
        #   the rm79 seal: `(NormalEgo)` g101:=0 unconditional, then `(= gCurrentStatus 11)` only
        #   `if gIslandStatus==2`; flattening forced g101=11 always -> every win edge (needs
        #   g101==0) sealed. Emitted as ordered guarded cases (last source wins where guard holds).
        self.deaths = []            # (room, guard) flat/machine deaths
        self.procs_by = {}          # (script, proc-name) -> body AST, for call-following
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body
        # REGIONS: a room's `(setRegions: R)` activates region script R while you are in
        # that room. Region-script effects (e.g. rm300.handleEvent's gWearingSunscreen:=3
        # on the ship voyage) apply in the rooms that set the region, NOT in an unreachable
        # "room R". region_rooms: region-script -> {rooms that activate it}.
        #
        # The room lookup here used to be `by_name["rm<N>"]` -- the LSL2 decompiler naming
        # convention, which extract2._room_object stopped relying on when KQ4 turned out to
        # name its rooms `Room<N>`. That fix never reached this copy, so KQ4 mapped 0 region
        # scripts and every one of its 26 regions was dropped whole (LSL2: 9 regions over 62
        # rooms). SCI dispatches at three scopes -- Main, region, room -- and this is the
        # middle one; losing it silently loses every guard and effect that lives there.
        self.region_rooms = {}
        for rn, s in ir.scripts.items():
            room = _room_object(s, ir)
            if room is None:
                continue
            for _mn, a in room.methods.items():
                for n in I.walk(a):
                    if n["t"] == "Send":
                        recv, msgs = I.send_pairs(n)
                        for sel, params in msgs:
                            if sel == "setRegions":
                                for p in params:
                                    v = _int(p.get("value"))
                                    if v is not None:
                                        self.region_rooms.setdefault(v, set()).add(rn)
        for rn, s in ir.scripts.items():
            # A region's machines run in the rooms that activate it, exactly as its handlers do
            # (below). Lifting them only for real rooms dropped 12 of KQ4's region scripts whole
            # -- among them regUnicorn's `uniActions`, the ONLY place the Golden_Bridle is ever
            # required. The duplication is not an approximation: the same machine really is live
            # in each of those rooms.
            targets = self.region_rooms.get(rn) or ({rn} if rn in self.ts.rooms else None)
            if not targets:
                continue
            if rn in self.ts.rooms:
                self._init_writes(rn, s)
            for m in self.mb.machines(s):
                for room in sorted(targets):
                    info = self._machine_info(room, m)
                    if info:
                        self.machines.append(info)
        # player-action effects in handleEvent/doit: register writes + item get/put that
        # the game does NOT do via a changeState machine (e.g. `(= gLoweredLifeboats 1)`
        # when the player says "lower lifeboats"). Guard = the path condition (Said/opaque
        # permissive). Without these, promoted gates like `gLoweredLifeboats!=0` can never
        # open. Same shape as the disguise's gCurrentEgoView.
        self.handler_writes = []       # (room, script, gi, val, guard)  -- script for CTR-local resolve
        self.handler_gets = []         # (room, script, item, guard)
        self.handler_drops = []        # (room, script, item, guard) -- `gEgo put: N -1` in a
        #   handler. Consuming an item requires owning it; the Pamphlet handed to the bore on
        #   the plane (rm62) is a Said-handler consumption, invisible to the machine-body scan.
        self.handler_moves = []        # (room, script, item, dest, guard) -- the same transfers as
        #   gets/drops, but keeping the DESTINATION that `put:`/`moveTo:` carry. KQ4 uses
        #   pseudo-room numbers as item states (206 unplaced, 666 on the hook, 777 eaten,
        #   999 destroyed), so `where did it go` separates "elsewhere" from "gone" -- see
        #   `item_moves_to_world`, which is what keeps a bird placing a worm out of the
        #   dangerous-sink report.
        self.handler_locals = []       # (room, script, (vt,idx), val, guard)
        for rn, s in ir.scripts.items():
            # target rooms: a region script's effects apply in the rooms that activate it;
            # a real room's in itself. (A region "room" R is never entered directly.)
            if rn in self.region_rooms:
                targets = self.region_rooms[rn]
            elif rn in self.ts.rooms:
                targets = {rn}
            elif rn == MAIN_SCRIPT:
                # Main is a SCOPE, not a room: its Game subclass's handleEvent/doit/newRoom run
                # everywhere. LSL2's script 0 happens to land in ts.rooms and so was walked;
                # KQ4's is not, so every effect in its Main was dropped -- including
                # `(gEgo put: 25 999)` at Main.sc:1246, the Magic Fruit being eaten. Recorded
                # against room 0 (as LSL2's already was); consumers that know Main is global
                # widen it -- see missability.GLOBAL_SCRIPTS.
                targets = {0}
            else:
                continue
            for room in targets:
                for o in s.objects:
                    for mn, body in o.methods.items():
                        # changeState -> machine; init -> forced entry write. EVERY other
                        # method's effects captured here (globals + locals + gets),
                        # FOLLOWING calls into other scripts, so nothing is absent.
                        if mn in ("changeState", "init"):
                            continue
                        self._hwalk(room, rn, body, [], set())
                for pbody in s.procs.values():
                    self._hwalk(room, rn, pbody, [], set())
        for room, script, gi, v, g in self.handler_writes:
            self.reg_vals.setdefault(gi, {0}).add(v)
            self._scan_domains_guard(g, script)      # CTR-local values in the guard
        for room, script, key, v, g in self.handler_locals:
            k = (script,) + key
            self.loc_vals.setdefault(k, {0})
            if isinstance(v, int):
                self.loc_vals[k].add(v)
            elif v == ("inc",):
                self._loc_inc.add(k)
            elif v == ("dec",):
                self._loc_dec.add(k)
            self._scan_domains_guard(g, script)
        for room, script, it, g in self.handler_gets:
            self._scan_domains_guard(g, script)
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
                        if kind == "inc":
                            self._loc_inc.add(key)
                        elif kind == "dec":
                            self._loc_dec.add(key)
                    self._scan_domains(guard, info["script"])
            for K, eg in info["entries"]:
                self._scan_domains_guard(eg, info["script"])
        for room, seq in self.init_seq.items():
            for gi, v, g in seq:
                self.reg_vals.setdefault(gi, {0}).add(v)
                self._scan_domains_guard(g, None)   # guard values (e.g. gIslandStatus==2)
        # exits the machines can deliver -> which changeState newRoom targets DON'T need a
        # flat fallback (the rest do, gated by their extract2 path condition).
        self.machine_delivered = set()
        for info in self.machines:
            for dst in info.get("delivered", ()):
                self.machine_delivered.add((info["room"], dst))

        # Control-map oracle FIRST (reads the PIC control plane + VIEW cels, not declared):
        #  - prop-gate  (rm82): machine EXIT->83 requires causedEruption (the aDoor Prop covers
        #    the onControl-$0004 floor until the bomb opens it);
        #  - crossing-gate (rm47): the win-ward exit that PROVABLY forces the doit death-rect
        #    inherits the disguise requirement, per-exit (does not over-gate the retreat).
        self._apply_control_gates()

        # finalize domains; single-value dims fold to constants (SMV rejects init on them)
        self.reg_dom, self.reg_const = {}, {}
        for gi, vs in self.reg_vals.items():
            lo, hi = min(vs), max(vs)
            (self.reg_const if lo == hi else self.reg_dom)[gi] = lo if lo == hi else (lo, hi)
        self.loc_dom, self.loc_const = {}, {}
        for k, vs in self.loc_vals.items():
            lo, hi = min(vs), max(vs)
            # saturation headroom: a saturating inc emits `lv+1` (static range up to hi+1) that
            # the `>= hi ? hi` ternary clamps at runtime -- declare hi+1 (unreachable sentinel)
            # so nuXmv's static range check doesn't false-warn "cannot assign hi+1". Ditto dec.
            hi += 1 if k in self._loc_inc else 0
            lo -= 1 if k in self._loc_dec else 0
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

    def _cutscene_room_set(self):
        """Rooms with NO player input (HandsOff + no `Said` handler) -- pure cutscenes we can
        collapse to net-effect edges to remove their depth (rm84's 82-state volcano, the
        gIslandStatus endgame chain). Definition keyed on the decompiled source."""
        if getattr(self, "_cutscenes", None) is None:
            import re
            out, d = set(), getattr(self.cfg, "src_dir", "")
            try:
                for f in os.listdir(d):
                    mm = re.match(r"rm(\d+)\.sc$", f)
                    if mm:
                        t = open(os.path.join(d, f), errors="ignore").read()
                        if "HandsOff" in t and "Said" not in t:
                            out.add(int(mm.group(1)))
            except OSError:
                pass
            self._cutscenes = out
        return self._cutscenes

    def _collapse_cutscene(self, room, m):
        """Collapse a cutscene machine to its net-effect SUMMARIES: one hop per (entry, exit
        path), carrying accumulated writes+gets, replacing the internal state sequence. Summarize
        from every entry state (rm92 enters at 16/23/... by gIslandStatus), not just start."""
        entry_ks = {m.start} | {k for k, _ in m.entries} | {k for k, _ in m.init_entries}
        states, has_effect, drops = {}, False, set()
        for K in entry_ks:
            paths = []
            for (X, gtree, writes, gets, sdrops, dead) in C.summarize_machine(m, self.is_death, from_state=K):
                trans = ("DEATH",) if dead else ("EXIT", X)
                paths.append(([gtree] if gtree is not None else [], list(writes.items()), gets, [], trans))
                if not dead:
                    drops |= set(sdrops)   # consumed on a SURVIVABLE path -> a real requirement
                has_effect = True
            if paths:
                states[K] = paths
        if not has_effect:
            return None
        try:
            exits, _d = C.compile_machine(m, self.is_death)
            delivered = set(r for r, g, w in exits)
        except Exception:
            delivered = set()
        return {"room": room, "inst": m.inst, "script": m.script, "states": states,
                "entries": m.entries, "init_entries": m.init_entries, "start": m.start,
                "delivered": delivered, "cutscene": True, "drops": drops}

    def _machine_info(self, room, m):
        if room in self._cutscene_room_set():
            return self._collapse_cutscene(room, m)
        states = {}
        has_effect = False
        steps_by_state = {}
        for K, body in m.bodies.items():
            body = self._inline_calls(body, m.script, set())
            steps_by_state[K] = [C._interp(p, self.is_death) for p in C._paths_of(body)]
        C.carry_cues(steps_by_state, m.start)   # SCI cross-state cue carry (PARK -> ADVANCE)
        entry_states = {k for k, _ in m.entries} | {k for k, _ in m.init_entries}
        C.compress_chains(steps_by_state, entry_states, m.start)   # collapse effect-free ADVANCE runs
        for K, steps in steps_by_state.items():
            paths = []
            for st in steps:
                if st.writes or st.gets or st.trans[0] in ("EXIT", "DEATH"):
                    has_effect = True
                paths.append((st.guard, st.writes, st.gets, st.counters, st.trans))
            states[K] = paths
        # Items CONSUMED (`gEgo put: N -1`) on a SURVIVABLE path: consuming an item requires
        # owning it (the Flower at rm50 has no own() guard at all, only the consumption). Skip
        # death-bound paths -- consuming on the way to a death is a TRAP, not a requirement.
        succ, deadK = {}, set()
        for K, steps in steps_by_state.items():
            for st in steps:
                t = st.trans
                if t[0] == "DEATH":
                    deadK.add(K)
                elif t[0] == "ADVANCE":
                    succ.setdefault(K, set()).add(K + 1)
                elif t[0] == "JUMP":
                    succ.setdefault(K, set()).add(t[1])
                elif t[0] == "SETSTATE":
                    succ.setdefault(K, set()).add(t[1] + 1)
        dr, changed = set(deadK), True
        while changed:
            changed = False
            for K, ss in succ.items():
                if K not in dr and (ss & dr):
                    dr.add(K); changed = True
        drops = set()
        for K, steps in steps_by_state.items():
            for st in steps:
                if not st.drops:
                    continue
                t = st.trans
                tgt = (K + 1 if t[0] == "ADVANCE" else t[1] if t[0] == "JUMP" else
                       t[1] + 1 if t[0] == "SETSTATE" else None)
                if t[0] == "DEATH" or (tgt is not None and tgt in dr):
                    continue
                drops |= set(st.drops)
        if not has_effect:
            return None
        # which exits this machine can actually DELIVER (control_exits): a changeState
        # newRoom target the machine cannot walk to needs a flat fallback so the room
        # isn't a false dead-end.
        try:
            exits, _d = C.compile_machine(m, self.is_death)
            delivered = set(r for r, g, w in exits)
        except Exception:
            delivered = set()
        return {"room": room, "inst": m.inst, "script": m.script, "states": states,
                "entries": m.entries, "init_entries": m.init_entries,
                "start": m.start, "delivered": delivered, "drops": drops}

    def _apply_control_gates(self):
        """Consume control_oracle.find_gates: for each prop-gate, AND the derived door-open
        latch onto the machine EXIT that the gated onControl trigger delivers. Everything is
        read (PIC control plane, VIEW cel footprints, the opener state's own write), nothing
        declared; the latch is the persistent write the opener state makes (rm82: causedEruption
        L3:=1 in state 16). This is the general Sierra door/gate/movable-block mechanism."""
        self.control_gates = []
        if not getattr(self.cfg, "resource_dir", ""):
            return
        try:
            import control_oracle as CO
            gates = CO.find_gates(self.cfg, self.ir)
        except Exception:
            return
        self.control_gates = gates
        for gate in gates:
            room = gate["room"]
            if gate.get("kind") == "prop":
                # prop-gate (rm82 door): gate the machine EXIT->gated_room on the opener latch.
                latch = gate.get("opener_latch")
                gr = gate.get("gated_room")
                if not latch or gr is None:
                    continue
                vt, idx, val = latch
                self.loc_vals.setdefault((room, vt, idx), {0}).add(val)   # give the latch a domain
                guard = ("CTR", (vt, idx), "==", val)
                for info in self.machines:
                    if info["room"] != room:
                        continue
                    for K, paths in list(info["states"].items()):
                        newp = []
                        for path in paths:
                            g, rest, trans = path[0], path[1:], path[4]
                            if trans[0] == "EXIT" and trans[1] == gr:
                                g = list(g) + [guard]
                            newp.append((g,) + rest)
                        info["states"][K] = newp
            elif gate.get("kind") == "crossing":
                # crossing-gate (rm47 disguise): the win-ward flat exit (proven to force the
                # doit rect) requires the safe local value, i.e. NOT(L==bad). Only this exit is
                # gated -- only this proven-forced exit; the retreat exit is left free.
                dst = gate.get("gated_room")
                vt, idx = gate["safe_local"]
                bad = gate["bad_value"]
                if dst is None:
                    continue
                self.loc_vals.setdefault((room, vt, idx), {0}).add(bad)
                # Prefer the derived DISGUISE CONDITION (persistent globals, e.g. gBodyWaxed &
                # egoView==151) -- it makes the disguise ITEMS required (egoView is item-gated)
                # and can't be satisfied by ARMING the henchmen (henchStatus==1). Fall back to
                # the local's safe value only if the init disguise-write wasn't found.
                safe = gate.get("safe_guard") or GNot(("CTR", (vt, idx), "==", bad))
                for e in self.ts.edges:
                    if e.src == room and e.dst == dst:
                        e.guard = safe if e.guard is None else GAnd([e.guard, safe])

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
            priors = []   # a case (and the else) runs only if all PRIOR cases failed
            for c in node["kids"]:
                if c["t"] == "Case":
                    a = atom(c["kids"][0])
                    self._hwalk(room, script, c["kids"][1], pc + priors + [a], seen)
                    priors = priors + [GNot(a) if a is not None else None]
                elif c["t"] == "Else":
                    self._hwalk(room, script, c["kids"][0], pc + priors, seen)
            return
        if tp == "Assignment":
            dst, src = node["kids"][0], node["kids"][1]
            v = _int(src.get("value"))
            if I.is_global(dst) and v is not None and not self.is_death(dst["index"], v):
                self.handler_writes.append((room, script, dst["index"], v, _conj_atoms(pc)))
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
                tr = item_transfer(recv, sel, params)
                if tr is None:
                    continue
                it, dest = tr
                g = _conj_atoms(pc)
                self.handler_moves.append((room, script, it, dest, g))
                if dest == EGO:
                    self.handler_gets.append((room, script, it, g))
                else:
                    self.handler_drops.append((room, script, it, g))
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
        # Entry global writes WITH their path condition, FOLLOWING calls (e.g. proc0_2 =
        # the hands-on reset gCurrentStatus:=0, called from 66 room inits). Records the full
        # ordered guarded sequence; UNCONDITIONAL writes ALSO feed init_writes (initial value).
        self._init_walk(room, script.number, obj.methods["init"], [], set())

    def _init_walk(self, room, script, node, pc, seen):
        if node is None:
            return
        tp = node["t"]
        if tp == "If":
            ks = node["kids"]
            a = atom(ks[0])
            self._init_walk(room, script, ks[1], pc + [a], seen)
            if len(ks) > 2:
                self._init_walk(room, script, ks[2], pc + [GNot(a) if a else None], seen)
            return
        if tp == "Cond":
            priors = []
            for c in node["kids"]:
                if c["t"] == "Case":
                    a = atom(c["kids"][0])
                    self._init_walk(room, script, c["kids"][1], pc + priors + [a], seen)
                    priors = priors + [GNot(a) if a else None]
                elif c["t"] == "Else":
                    self._init_walk(room, script, c["kids"][0], pc + priors, seen)
            return
        if tp in ("Switch", "Loop"):
            # a value we can't decide -> writes inside are CONDITIONAL (optional), never forced
            for k in node.get("kids", ()):
                self._init_walk(room, script, k, pc + [Pred("OPAQUE")], seen)
            return
        if tp == "Assignment" and I.is_global(node["kids"][0]):
            gi, v = node["kids"][0]["index"], _int(node["kids"][1].get("value"))
            if v is not None and not self.is_death(gi, v):
                g = _conj_atoms(pc)
                self.init_seq.setdefault(room, []).append((gi, v, g))
                if g is None:                    # unconditional -> also the initial value
                    self.init_writes.setdefault(room, {})[gi] = v
        elif tp in ("PublicCall", "LocalCall"):
            tgt = node.get("script", script)
            name = node.get("name")
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._init_walk(room, tgt, body, pc, seen | {name})
        for k in node.get("kids", ()):
            self._init_walk(room, script, k, pc, seen)

    def _scan_domains(self, guard, script):
        for a in guard:
            if isinstance(a, tuple) and a and a[0] == "CTR":
                key = (script,) + a[1]
                self.loc_vals.setdefault(key, {0}).add(a[3])
            else:
                self._scan_domains_guard(a, script)

    def _scan_domains_guard(self, g, script):
        if isinstance(g, tuple) and g and g[0] == "CTR":       # local-compare guard
            if script is not None:
                self.loc_vals.setdefault((script,) + g[1], {0}).add(g[3])
        elif isinstance(g, Pred) and g.kind == "CMP":
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
        # An opaque (unresolvable) guard atom. Opaques are INDEPENDENT fresh free choices, so a
        # guard `real & f(opaques)` is enabled exactly when `real` holds -- f is always
        # satisfiable by some opaque assignment. We therefore EXISTENTIALLY PROJECT the opaques
        # out: `_gx` propagates this OPAQUE sentinel (dropped in AND, absorbs OR to TRUE, stays
        # OPAQUE under NOT) and the public `gexpr` maps a surviving OPAQUE to TRUE. The result is
        # reachability-IDENTICAL to a free-input encoding but emits ZERO free booleans -- the
        # dominant width reduction for nuXmv (was ~1500 opaque IVARs on LSL2).
        return "OPAQUE"

    def _posexpr(self, g):
        """A POS guard -> SMV over the ego's free (x,y) (posx/posy IVARs). ONE consistent
        free choice per step, so `edge east (posx>=316)` implies `inRect [86..333]`
        unavoidably. onControl stays opaque (control-map, not a function of (x,y))."""
        if g[1] == "rect":
            a, b, c, d = g[2]
            parts = []
            if a > 0: parts.append(f"posx >= {a}")
            if c < 319: parts.append(f"posx <= {c}")
            if b > 0: parts.append(f"posy >= {b}")
            if d < 189: parts.append(f"posy <= {d}")
            return "(" + " & ".join(parts) + ")" if parts else "TRUE"
        if g[1] == "edge":   # SCI edgeHit: 1=top, 2=right, 3=bottom, 4=left
            return {1: "posy <= 4", 2: "posx >= 316", 3: "posy >= 186",
                    4: "posx <= 4"}.get(g[2], self._permissive())
        return self._permissive()

    def gexpr(self, g, script):
        """External guard tree -> SMV; script gives the counter namespace for CTR. Opaques are
        existentially projected out (see _permissive): `_gx` may return the OPAQUE sentinel,
        which at the top level means the guard is freely satisfiable -> TRUE."""
        r = self._gx(g, script)
        return "TRUE" if r == "OPAQUE" else r

    def _gx(self, g, script):
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
        if isinstance(g, tuple) and g and g[0] == "POS":
            return self._posexpr(g)
        if isinstance(g, GAnd):
            ks = [self._gx(k, script) for k in g.kids]
            if "FALSE" in ks:
                return "FALSE"
            ks = [k for k in ks if k not in ("TRUE", "OPAQUE")]   # opaques projected out of AND
            return "(" + " & ".join(ks) + ")" if ks else "TRUE"
        if isinstance(g, GOr):
            ks = [self._gx(k, script) for k in g.kids]
            if "TRUE" in ks or "OPAQUE" in ks:   # an opaque disjunct is satisfiable -> TRUE
                return "TRUE"
            ks = [k for k in ks if k != "FALSE"]
            return "(" + " | ".join(ks) + ")" if ks else "FALSE"
        if isinstance(g, GNot):
            k = g.kid
            # push negation to leaves (NNF/De Morgan) so an opaque literal stays a leaf and its
            # OPAQUE sentinel is projected out correctly (¬opaque is also freely satisfiable).
            if isinstance(k, GAnd):
                return self._gx(GOr([GNot(x) for x in k.kids]), script)
            if isinstance(k, GOr):
                return self._gx(GAnd([GNot(x) for x in k.kids]), script)
            if isinstance(k, GNot):
                return self._gx(k.kid, script)
            inner = self._gx(k, script)
            if inner == "OPAQUE":
                return "OPAQUE"
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

        # flat movement edges. gexpr with the SOURCE room's script so a CTR-local guard on
        # the edge resolves (the room's own locals -- e.g. the disguise henchStatus gate).
        for e in self.ts.edges:
            g = self.gexpr(e.guard, e.src)
            if g == "FALSE":
                continue
            c = cond(f"action = {aid} & room = {e.src}", g)
            nxt["room"].append((c, str(e.dst)))
            room_change.append((c, e.dst))
            aid += 1
        # control_exits fallback: changeState exits the machine can't deliver, as GATED
        # flat edges (keeps the gate, e.g. rm65->70 gCurrentStatus!=12, without a bypass).
        for e in self.ts.cs_edges:
            if (e.src, e.dst) in self.machine_delivered:
                continue
            g = self.gexpr(e.guard, e.src)
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
            # ABSENT MID-SEQUENCE states fall through (advance to K+1) -- a genuine gap
            # between defined states (rm28Script: states 0,1,2,3,5 -- 4 absent; without this
            # s5 is unreachable). But NOT the START state: an absent start (reset target) is
            # left ONLY via the machine's gated ENTRIES (changeState or setScript). Falling
            # through it (0->1 free) was a BYPASS that skipped the entry gate -- rm63 jumped
            # the plane without opening the door (needs the Bobby_Pin), so items looked "not
            # required". Now safe to remove: setScript capture gave every machine real entries.
            allst = set(info["states"])
            if allst:
                for K in range(min(allst | {info["start"]}), max(allst) + 1):
                    if K not in allst and K != info["start"]:
                        nxt[ms].append((f"action = {aid} & room = {R} & {ms} = {K}", str(K + 1)))
                        aid += 1

        # player-action effects (handleEvent/doit register writes + item gets). gexpr with
        # the effect's own SCRIPT so a CTR-local guard (e.g. henchStatus==0) resolves.
        for room, script, gi, v, g in self.handler_writes:
            if gi not in self.reg_dom:
                continue
            ge = self.gexpr(g, script)
            if ge == "FALSE":
                continue
            nxt[self._gv(gi)].append((cond(f"action = {aid} & room = {room}", ge), str(v)))
            aid += 1
        for room, script, it, g in self.handler_gets:
            ge = self.gexpr(g, script)
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

        # init writes bundled onto every room-changing action, WITH their entry guards.
        # Source order + insert(0) => the last source write to a register sits FIRST (highest
        # priority); first-match-wins then reproduces "later assignment wins where its guard
        # holds" (rm79: g101:=11 if gIslandStatus==2, else the unconditional NormalEgo g101:=0).
        machines_by_room = defaultdict(list)
        for info in self.machines:
            machines_by_room[info["room"]].append(info)
        self._ms_arrival = defaultdict(list)     # ms -> [(arrival_cond, entry_state)]
        for c, target in room_change:
            for gi, v, g in self.init_seq.get(target, []):
                if gi not in self.reg_dom:
                    continue
                ge = self.gexpr(g, None)
                if ge == "FALSE":
                    continue
                cc = c if ge == "TRUE" else f"({c}) & {ge}"
                nxt[self._gv(gi)].insert(0, (cc, str(v)))
            # INIT-sourced machine entries run atomically with init -> fire on ARRIVAL,
            # entry guard evaluated on the PRE-entry (source-room) state (same state the init
            # writes above read). Emitted ahead of the ms reset-to-start (see _emit_ms_next).
            for info in machines_by_room.get(target, ()):
                ms = self._ms(info)
                for K, eg in info.get("init_entries", ()):
                    ge = self.gexpr(eg, info["script"])
                    if ge == "FALSE":
                        continue
                    cc = c if ge == "TRUE" else f"({c}) & {ge}"
                    self._ms_arrival[ms].append((cc, str(K)))

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
        L.append("  posx : 0 .. 319;")   # ego's free-but-consistent position (a player choice)
        L.append("  posy : 0 .. 189;")
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
            ms = self._ms(info)
            cand = list(info["states"]) + [info["start"]]
            # Include every state value this machine can actually be ASSIGNED (an ADVANCE off
            # the top state -> K_max+1, or a JUMP/SETSTATE target), so nuXmv never silently
            # DROPS an out-of-range next() write. Such a target has no handler, so it is an
            # absorbing no-op state -- faithful, and it removes the "cannot assign value"
            # warnings that otherwise mask a dropped assignment.
            for c, v in nxt.get(ms, []) + getattr(self, "_ms_arrival", {}).get(ms, []):
                if isinstance(v, str) and v.lstrip("-").isdigit():
                    cand.append(int(v))
            lo, hi = min(cand), max(cand)
            if hi == lo:                # a collapsed cutscene has one state -> 0..0, which nuXmv
                hi = lo + 1             # rejects; widen to a valid 2-value range (extra value unreachable)
            L.append(f"  {ms} : {lo} .. {hi};")

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
        # INIT entries fire on arrival (room is still the source here, != R) and must win over
        # the reset-to-start below, so they come FIRST.
        for c, v in getattr(self, "_ms_arrival", {}).get(ms, []):
            L.append(f"    {c} : {v};")
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
