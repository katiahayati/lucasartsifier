"""Cures A+B are in, `257: 0` is forced back, and the seal is STILL False. Which half fails,
and by which write?"""
import sys, os, types
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C, w, r = 123, 4, 370
flag44 = s.em.ir.flag_synth_base + 44
goal = set(s.em.cfg.goal_rooms)

_orig = s._step_neco.__func__
def sn(self, C2, f, t, depth=3):
    out = dict(_orig(self, C2, f, t, depth))
    if C2 != C:
        return out
    own = None
    for (Ck, room, tk), brs in self._wbranch.items():
        if Ck != C2 or tk != t or room != 370:
            continue
        for (d, _c, co) in brs:
            if f not in d.get(C2, {f}):
                continue
            cs = {R: v for (R, v) in co if R != C2}
            own = cs if own is None else {R: v for R, v in own.items() if cs.get(R) == v}
    for R, v in (own or {}).items():
        out.setdefault(R, v)
    return out
s._step_neco = types.MethodType(sn, s)

fwd = {w}; grew = True
while grew:
    grew = False
    for _r3, sts3 in s._rstep.get(C, {}).items():
        for (f3, t3) in sts3:
            if f3 in fwd and t3 not in fwd:
                fwd.add(t3); grew = True
for vs3 in s._inroom.get(C, {}).values():
    fwd |= set(vs3)

def post(extra, tag):
    s._rp_xcache = {}
    pre, conf = s._staged_pre(C, w - 1, extra, require_steps=True)
    if pre is None:
        print(f"{tag}: NO CROSSER"); return None
    pv = dict(pre[1]); pv[C] = set(pv.get(C, {0})) | {w}
    conf = s._apply_neco(C, w, pv, conf)
    cp = {k: v for k, v in conf.items() if k not in (C,) and k not in extra}
    cp[C] = set(fwd)
    out = s._pclose({r}, pv, pre[2], cp, refine=False)
    print(f"{tag}: {len(out[0])} rooms, pv[123]={sorted(out[1].get(C, ()))}, "
          f"pv[257]={sorted(out[1].get(257, ()))}, goal={bool(goal & out[0])}")
    return out, cp

g = post({}, "post_g (unconstrained)")
b = post({flag44: {0}}, "post_b (flag44 == 0)")
if not b:
    sys.exit()
(rooms, pv, items), cp = b
def allowed(reg):
    base = set(pv.get(reg, {0})); c = cp.get(reg)
    return (base & c) if c is not None else base
print("\n--- day writes LIVE for the flag-44-less crosser ---")
seen = set()
for (Rk, room, v), brs in sorted(s._wbranch.items(), key=str):
    if Rk != C or room not in rooms:
        continue
    for (d, cost, co) in brs:
        if set(cost) <= set(items) and all(set(vs) & allowed(S) for S, vs in d.items() if S != C):
            k = (room, v, tuple(sorted((a, tuple(sorted(x))) for a, x in d.items())))
            if k in seen: continue
            seen.add(k)
            print(f"   123:={v} @rm{room} deps={ {a: sorted(x) for a, x in sorted(d.items())} }")
print("\n--- how flag 257 (day-end) got back into hand ---")
for (Rk, room, v), brs in sorted(s._wbranch.items(), key=str):
    if Rk != 257 or v != 1 or room not in rooms:
        continue
    for (d, cost, co) in brs:
        if set(cost) <= set(items) and all(set(vs) & allowed(S) for S, vs in d.items() if S != 257):
            print(f"   257:=1 @rm{room} deps={ {a: sorted(x) for a, x in sorted(d.items())} } cost={sorted(cost)}")
