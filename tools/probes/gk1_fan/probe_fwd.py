"""Probe: for GK1's day-4 crossing at rm370, what does `fwd` hold structurally, and what
would a LIVE-step fixpoint hold (docs GK1 1.55)?  Product-level, no src/ edit."""
import sys, time
sys.path.insert(0, "/home/hayati/coding/sierra_softlock/src")
import config, missability as M

t0 = time.time()
cfg = config.by_name("gk1")
s = M.load(cfg=cfg)
print(f"model loaded in {time.time()-t0:.1f}s", flush=True)

R, w, r = 123, 4, 370
print("goal rooms:", sorted(s.em.cfg.goal_rooms))
print("R in _counters:", R in getattr(s, "_counters", ()))
print("reg_vals[123]:", sorted(s.em.reg_vals.get(R, ())))
print("_inroom[123]:", {k: sorted(v) for k, v in s._inroom.get(R, {}).items() if v})
steps = {}
for room, sts in s._rstep.get(R, {}).items():
    steps[room] = sorted(sts)
print("_rstep[123] rooms:", len(steps))
for room in sorted(steps):
    clam = [(f, t) for (f, t) in steps[room] if (R, room, t) in getattr(s, "_clamp_steps", ())]
    print(f"   rm{room}: {steps[room]}   clamp_targets={sorted({t for _f,t in clam})}")

# --- the CURRENT fwd, verbatim from producible_seal -------------------------------------
fwd = {w}
grew = True
while grew:
    grew = False
    for _r3, sts3 in s._rstep.get(R, {}).items():
        for (f3, t3) in sts3:
            if f3 in fwd and t3 not in fwd:
                fwd.add(t3); grew = True
for vs3 in s._inroom.get(R, {}).values():
    fwd |= set(vs3)
print("\nCURRENT fwd:", sorted(fwd), flush=True)

# --- the crosser -------------------------------------------------------------------------
t0 = time.time()
s._rp_xcache = {}
pre_g, conf_g = s._staged_pre(R, w - 1, {}, require_steps=True)
print(f"staged_pre in {time.time()-t0:.1f}s -> {'None' if pre_g is None else 'ok'}", flush=True)
pvw = dict(pre_g[1]); pvw[R] = set(pvw.get(R, {0})) | {w}
conf_g = s._apply_neco(R, w, pvw, conf_g)

def allowed(pv, confine, reg):
    b = set(pv.get(reg, {0}))
    c = confine.get(reg)
    return (b & c) if c is not None else b

def write_live(room, frm, to, rooms, pv, confine, items):
    if room not in rooms:
        return "room-unreachable"
    brs = s._wbranch.get((R, room, to))
    if not brs:
        return "no-branch-row(permissive)"
    for (d, cost, _co) in brs:
        if frm is not None and frm not in d.get(R, {frm}):
            continue
        if not set(cost) <= set(items):
            continue
        if all(set(vs) & allowed(pv, confine, S) for S, vs in d.items() if S != R):
            return f"LIVE deps={ {k: sorted(v) for k, v in d.items()} } cost={sorted(cost)}"
    return None

# --- the LIVE fixpoint --------------------------------------------------------------------
live = {w}
it = 0
while True:
    it += 1
    conf = {k2: v2 for k2, v2 in conf_g.items() if k2 != R}
    conf[R] = set(live)
    t0 = time.time()
    rooms, pv, items = s._pclose({r}, pvw, pre_g[2], conf, refine=False)
    print(f"\n-- iter {it}: fwd={sorted(live)} closure {len(rooms)} rooms, "
          f"{len(items)} items in {time.time()-t0:.1f}s; goal in closure: "
          f"{bool(set(s.em.cfg.goal_rooms) & rooms)}", flush=True)
    grew = False
    for room, sts in sorted(s._rstep.get(R, {}).items()):
        for (f3, t3) in sorted(sts):
            if f3 not in live or t3 in live:
                continue
            v = write_live(room, f3, t3, rooms, pv, conf, items)
            if v and v != "room-unreachable":
                print(f"     admit {f3}->{t3} @rm{room}: {v}")
                live.add(t3); grew = True
    if not grew:
        break
print("\nLIVE fwd:", sorted(live))
print("CURRENT fwd:", sorted(fwd))
