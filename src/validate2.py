"""Validation harness: explicit reachability of the OPERATIONAL model's machine-stepping
(absent-state fall-through, park, entries, counters) with REGISTER gates permissive.

Purpose: separate the two failure modes cheaply, without per-room nuXmv.
  * If the goal is reachable here -> the machines/stepping are fine and the remaining
    winnability block is REGISTER value-flow (a promoted gate that can't be satisfied).
  * If not -> the frontier pinpoints a machine-walk discrepancy (a room whose machine
    can't deliver an exit compile2 says it can). Diffs those against compile2 per machine.

State = (room, ms per current-room machine, counters per current-room script). Machines
reset on room entry (script-locals reset), so only the current room's machines are live --
the state stays small. Guards: CTR (Local vs literal) resolved against tracked counters;
everything else (OWN/CMP/opaque) is permissive/satisfiable.
"""
from __future__ import annotations

from collections import defaultdict

import ir as I
import machine2 as M
import compile2 as C
import smv_emit3 as E


def _ctr_ok(guard, ctr, script):
    for a in guard:
        if isinstance(a, tuple) and a and a[0] == "CTR":
            key = (script,) + a[1]
            cur = ctr.get(key, 0)
            op, val = a[2], a[3]
            ok = {"==": cur == val, "!=": cur != val, ">": cur > val, ">=": cur >= val,
                  "<": cur < val, "<=": cur <= val}.get(op, True)
            if not ok:
                return False
    return True


def _apply_ctr(ctr, updates, script, loc_dom):
    c = dict(ctr)
    for (name, kind, val) in updates:
        key = (script,) + name
        if key not in loc_dom:
            continue
        lo, hi = loc_dom[key]
        if kind == "inc":
            c[key] = min(hi, c.get(key, 0) + 1)
        elif kind == "dec":
            c[key] = max(lo, c.get(key, 0) - 1)
        elif kind == "set" and val is not None:
            c[key] = val
    return c


def _eval3(node, regs, track):
    """3-valued: True/False if the tracked-register constraints decide it, else None
    (permissive: OWN/SAID/POS/opaque/untracked-CMP -- the player can satisfy them)."""
    from guard_ast import GAnd, GOr, GNot, Pred
    if node is None:
        return True
    if isinstance(node, tuple):          # a CTR atom is handled separately; treat as None
        return None
    if isinstance(node, GAnd):
        vs = [_eval3(k, regs, track) for k in node.kids]
        if any(v is False for v in vs):
            return False
        return None if any(v is None for v in vs) else True
    if isinstance(node, GOr):
        vs = [_eval3(k, regs, track) for k in node.kids]
        if any(v is True for v in vs):
            return True
        return None if any(v is None for v in vs) else False
    if isinstance(node, GNot):
        v = _eval3(node.kid, regs, track)
        return None if v is None else (not v)
    if isinstance(node, Pred):
        if node.kind == "CMP" and node.var in track:
            try:
                vi = int(node.value)
            except (TypeError, ValueError):
                return None
            cur = regs.get(node.var, 0)
            op = node.op
            return {"==": cur == vi, "!=": cur != vi, ">": cur > vi, ">=": cur >= vi,
                    "<": cur < vi, "<=": cur <= vi}.get(op, None)
        return None
    return None


def _guard_ok(guard, ctr, regs, script, track):
    """A machine-path guard (list of CTR-tuples and external guard-trees) holds iff CTR
    atoms match the counters AND no tracked-register atom is provably false."""
    for a in guard:
        if isinstance(a, tuple) and a and a[0] == "CTR":
            key = (script,) + a[1]
            cur = ctr.get(key, 0)
            op, val = a[2], a[3]
            if not {"==": cur == val, "!=": cur != val, ">": cur > val, ">=": cur >= val,
                    "<": cur < val, "<=": cur <= val}.get(op, True):
                return False
        elif _eval3(a, regs, track) is False:
            return False
    return True


def op_reach(em, cfg, track=frozenset(), cap=400000):
    """Track the registers in `track` faithfully; all others permissive."""
    track = frozenset(track)
    mbyroom = defaultdict(list)
    for info in em.machines:
        mbyroom[info["room"]].append(info)
    flat = defaultdict(list)
    for e in em.ts.edges:
        flat[e.src].append((e.dst, e.guard))
    for e in em.ts.cs_edges:
        if (e.src, e.dst) not in em.machine_delivered:
            flat[e.src].append((e.dst, e.guard))
    hwrites = defaultdict(list)   # room -> [(gi, v, guard)] for tracked regs
    for room, gi, v, g in em.handler_writes:
        if gi in track:
            hwrites[room].append((gi, v, g))

    def enter(room, regs):
        ms = tuple(sorted((info["inst"], info["start"]) for info in mbyroom[room]))
        nr = dict(regs)
        for gi, v in em.init_writes.get(room, {}).items():   # forced entry writes overwrite
            if gi in track:
                nr[gi] = v
        return (room, ms, (), tuple(sorted(nr.items())))

    reg0 = {gi: em._reg_init(gi, *em.reg_dom[gi]) for gi in track if gi in em.reg_dom}
    start = (cfg.start_room, tuple(sorted((info["inst"], info["start"]) for info in mbyroom[cfg.start_room])),
             (), tuple(sorted(reg0.items())))
    seen = {start}
    frontier = [start]
    reached = {cfg.start_room}
    op_delivers = defaultdict(set)

    while frontier:
        if len(seen) > cap:
            raise RuntimeError('cap')
        room, ms, ctr, regs = frontier.pop()
        msd, ctrd, rd = dict(ms), dict(ctr), dict(regs)
        succ = []
        for dst, guard in flat.get(room, ()):
            if _eval3(guard, rd, track) is not False:
                succ.append(enter(dst, rd))
        for gi, v, g in hwrites.get(room, ()):        # player-action register writes
            if _eval3(g, rd, track) is not False:
                nr = dict(rd); nr[gi] = v
                succ.append((room, ms, ctr, tuple(sorted(nr.items()))))
        for info in mbyroom[room]:
            inst = info["inst"]
            k = msd[inst]
            states = info["states"]
            if k not in states:
                if states and k <= max(states):
                    nms = dict(msd); nms[inst] = k + 1
                    succ.append((room, tuple(sorted(nms.items())), ctr, regs))
                continue
            for (guard, writes, gets, counters, trans) in states[k]:
                if not _guard_ok(guard, ctrd, rd, info["script"], track):
                    continue
                nc = tuple(sorted(_apply_ctr(ctrd, counters, info["script"], em.loc_dom).items()))
                nr = dict(rd)
                for gi, v in writes:
                    if gi in track:
                        nr[gi] = v
                nrt = tuple(sorted(nr.items()))
                tk = trans[0]
                if tk == "EXIT":
                    op_delivers[(room, inst)].add(trans[1])
                    succ.append(enter(trans[1], nr))
                elif tk == "DEATH":
                    pass
                elif tk == "ADVANCE":
                    nms = dict(msd); nms[inst] = k + 1
                    succ.append((room, tuple(sorted(nms.items())), nc, nrt))
                elif tk == "JUMP":
                    nms = dict(msd); nms[inst] = trans[1]
                    succ.append((room, tuple(sorted(nms.items())), nc, nrt))
                elif tk == "SETSTATE":
                    nms = dict(msd); nms[inst] = trans[1] + 1
                    succ.append((room, tuple(sorted(nms.items())), nc, nrt))
                elif writes or counters:
                    # a PARKing path still applies its writes (e.g. HandsOn g101:=0) and
                    # then waits in the same state for the next player action.
                    succ.append((room, ms, nc, nrt))
            for (K, eg) in info["entries"]:
                if _eval3(eg, rd, track) is not False:
                    nms = dict(msd); nms[inst] = K
                    succ.append((room, tuple(sorted(nms.items())), ctr, regs))
        for s in succ:
            reached.add(s[0])
            if s not in seen:
                seen.add(s)
                frontier.append(s)
    reg_seen = defaultdict(set)
    for (_r, _m, _c, rg) in seen:
        for gi, v in rg:
            reg_seen[gi].add(v)
    return reached, op_delivers, reg_seen


if __name__ == "__main__":
    import os
    import sys
    import config
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = I.load_ir(path)
    is_death = lambda gi, v: gi == 101 and v == 1001
    em = E.OpEmitter(ir, config.LSL2, is_death)
    reached, op_delivers, _ = op_reach(em, config.LSL2)
    goals = set(config.LSL2.goal_rooms)
    print(f"operational-permissive reachable rooms: {len(reached)}")
    print(f"goals reachable: {sorted(g in reached for g in goals)}  {sorted(goals & reached)}")
    print(f"unreachable (non-region <200): {sorted(r for r in em.rooms if r not in reached and r < 200)}")
    # DIFF vs compile2: per machine, exits compile2 delivers but the operational walk did not
    mb = M.MachineBuilder(ir, is_death)
    print("\n=== machines where compile2 delivers an exit the operational walk does NOT ===")
    n = 0
    for info in em.machines:
        s = ir.script(info["script"])
        mm = next((x for x in mb.machines(s) if x.inst == info["inst"]), None)
        if mm is None:
            continue
        ex, _de = C.compile_machine(mm, is_death)
        c2 = set(r for r, g, w in ex)
        opd = op_delivers.get((info["room"], info["inst"]), set())
        missing = c2 - opd
        if missing and info["room"] in reached:
            print(f"  rm{info['room']} {info['inst']}: compile2 delivers {sorted(c2)}, "
                  f"operational delivers {sorted(opd)}, MISSING {sorted(missing)}")
            n += 1
    print(f"total discrepant machines (in reachable rooms): {n}")

    # REGISTER VALUE-FLOW: values each promoted register can be WRITTEN to in a reachable
    # room, vs the values gates REQUIRE. A `== v` gate whose register never reaches v is a
    # candidate block (over-approximate: write may be in an unreached state of a reached room).
    from guard_ast import GAnd, GOr, GNot, Pred
    produced = defaultdict(set)
    for gi, (lo, hi) in em.reg_dom.items():
        produced[gi].add(em._reg_init(gi, lo, hi))
    for room, gi, v, g in em.handler_writes:
        if room in reached and gi in em.reg_dom:
            produced[gi].add(v)
    for room, wr in em.init_writes.items():
        if room in reached:
            for gi, v in wr.items():
                if gi in em.reg_dom:
                    produced[gi].add(v)
    for info in em.machines:
        if info["room"] not in reached:
            continue
        for K, paths in info["states"].items():
            for (guard, writes, gets, counters, trans) in paths:
                for gi, v in writes:
                    if gi in em.reg_dom:
                        produced[gi].add(v)

    def cmps(g, acc):
        if isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                cmps(k, acc)
        elif isinstance(g, GNot):
            cmps(g.kid, acc)
        elif isinstance(g, Pred) and g.kind == "CMP":
            acc.append((g.var, g.op, g.value))

    print("\n=== '== v' gates on reachable edges whose register never reaches v (block candidates) ===")
    blocks = set()
    for e in list(em.ts.edges) + list(em.ts.cs_edges):
        if e.src not in reached:
            continue
        acc = []
        cmps(e.guard, acc)
        for gi, op, v in acc:
            try:
                vi = int(v)
            except (TypeError, ValueError):
                continue
            if op == "==" and gi in em.reg_dom and vi not in produced.get(gi, set()):
                blocks.add((e.src, e.dst, gi, vi, tuple(sorted(produced.get(gi, set())))[:8]))
    for src, dst, gi, vi, prod in sorted(blocks):
        print(f"  {src}->{dst}: needs g{gi}=={vi}, produced={list(prod)}")
    print(f"total block-candidate gates: {len(blocks)}")

    # TRACKED value-flow: track key registers faithfully; does the goal stay reachable?
    # The smallest track set that blocks the goal names the culprit register(s).
    print("\n=== tracked-register reachability (finds the coupling block) ===")
    for tk in ({101}, {142}, {125}, {129}, {126}, {101, 142},
               {101, 142, 125, 129, 102, 126}):
        rr, _, rseen = op_reach(em, config.LSL2, track=tk)
        gr = sorted(goals & rr)
        vals={gi:sorted(rseen.get(gi,set())) for gi in tk}
        print(f"  track {sorted(tk)}: reachable={len(rr)}  goals={gr}  values={vals}"
              f"{'  <-- BLOCKS GOAL' if not gr else ''}")

    # frontier gates for the blocking registers: flat/cs edges from a reached room to an
    # unreached one, gated on the tracked register -- the value it can't reach.
    print("\n=== frontier gates for blocking registers ===")
    for tk in ({125}, {101}):
        rr, _, rseen = op_reach(em, config.LSL2, track=tk)
        shown = set()
        for e in list(em.ts.edges) + list(em.ts.cs_edges):
            if e.src in rr and e.dst not in rr:
                acc = []
                cmps(e.guard, acc)
                tg = [(gi, op, v) for gi, op, v in acc if gi in tk]
                key = (e.src, e.dst, tuple(tg))
                if tg and key not in shown:
                    shown.add(key)
                    print(f"  track {sorted(tk)}: {e.src}->{e.dst} gated {tg}")
        if not shown:
            print(f"  track {sorted(tk)}: no FLAT frontier gate -- block is a machine "
                  f"exit/entry gated on {sorted(tk)} (reached {len(rr)} rooms)")
