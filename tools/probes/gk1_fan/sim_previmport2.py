import sys, os, time
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C, w, r = 123, 4, 370
flag44 = s.em.ir.flag_synth_base + 44
prev = s._prev_reg_id()
dom = sorted(set(s.em.reg_vals.get(C, ())) | {0})

def seal(tag):
    s._cfd_memo = {}
    t0 = time.time()
    v = s.producible_seal(C, w, r, flag44, 0)
    print(f"  {tag}: producible_seal = {v!r}   ({time.time()-t0:.0f}s)", flush=True)
    return v

print("STEP 0 -- baseline (cures A+B, §1.34, nothing else)")
seal("baseline")

# ---- STEP 1: the prev-import into _emeta -------------------------------------------------
def cand_reqs(p, a):
    if a not in s.edges.get(p, ()):
        return None
    metas = s._emeta.get((p, a))
    return [rq for (rq, _st, _al) in metas] if metas else [None]

changed = 0
for (a, b), metas in list(s._emeta.items()):
    for idx, (rq, st, al) in enumerate(metas):
        P = set(rq.get(prev, ()))
        if not P:
            continue
        cands, dead = [], False
        for p in P:
            cr = cand_reqs(p, a)
            if cr is None:
                dead = True; break
            cands.extend(cr)
        if dead or not cands or not all(cr and cr.get(C) for cr in cands):
            continue
        lo = min(min(cr[C]) for cr in cands)
        keep = {v for v in dom if v >= lo}
        cur = set(rq.get(C, dom))
        if cur & keep != cur:
            rq2 = dict(rq); rq2[C] = cur & keep
            s._emeta[(a, b)][idx] = (rq2, st, al)
            changed += 1
s._psucc_cache = {}
s._pstates[C] = s._walk(C, frozenset())
print(f"\nSTEP 1 -- prev-import applied to {changed} edge meta(s); "
      f"rm550 days now {sorted({v for (q, v) in s._pstates[C] if q == 550})}")
seal("after prev-import")

# ---- STEP 2: a counter write cannot happen at a value its ROOM cannot hold ---------------
attain = {}
for (q, v) in s._pstates[C]:
    attain.setdefault(q, set()).add(v)
pruned_wb, pruned_rs = 0, 0
for (Rk, room, v), brs in list(s._wbranch.items()):
    if Rk != C:
        continue
    ok = attain.get(room, set())
    keep = []
    for (d, cost, co) in brs:
        froms = set(d.get(C, dom))
        if froms & ok:
            keep.append((d, cost, co))
        else:
            pruned_wb += 1
    if keep:
        s._wbranch[(Rk, room, v)] = keep
    else:
        del s._wbranch[(Rk, room, v)]
for room, sts in list(s._rstep.get(C, {}).items()):
    ok = attain.get(room, set())
    gone = {(f, t) for (f, t) in sts if f not in ok}
    if gone:
        sts -= gone
        pruned_rs += len(gone)
s._psucc_cache = {}
print(f"\nSTEP 2 -- pruned {pruned_wb} _wbranch branch(es) and {pruned_rs} _rstep step(s) "
      f"whose room cannot hold the from-value")
for q in (370, 480, 500, 550, 750, 800):
    print(f"   rm{q} steps now: {sorted(s._rstep.get(C, {}).get(q, ()))}")
print("   neco(3,4) =", {k: v for k, v in sorted(s._step_neco(C, 3, 4).items())})
seal("after room-bound writes")
