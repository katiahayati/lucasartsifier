"""Both gaps at once: (a) flag 268's write gets its day-6 gate (what lowering
`drumInset.local0` would give), (b) `_consumer_windows` collects wants from EDGE reqs too."""
import sys, os, time, types
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C, w, r = 123, 4, 370
R268 = s.em.ir.flag_synth_base + 268
flag44 = s.em.ir.flag_synth_base + 44
days = lambda q: sorted({v for (q2, v) in s._pstates[C] if q2 == q})

# (a)
del s._wbranch[(R268, 800, 1)]
s._wbranch[(R268, 410, 1)] = [({R268: {0}, C: {6}}, frozenset(), frozenset())]
wbd = getattr(s, "_wbranch_dom", None) or {}
wbd.pop((R268, 800, 1), None)
wbd[(R268, 410, 1)] = [({R268: {0}, C: {6}}, frozenset(), frozenset())]

# (b) widen `want` to every value the model DEMANDS, edges included
_orig_cw = s._consumer_windows.__func__
def cw(self):
    got = getattr(self, "_cwin_memo", None)
    if got is not None:
        return got
    out = {}
    for Ck in sorted(getattr(self, "_counters", ())):
        dom = sorted(set(self.em.reg_vals.get(Ck, ())) | {0})
        want = set()
        for tbl in (self._wbranch, self._wbranch_dom):
            for (_g, _rm, _v), brs in tbl.items():
                for (d, _c, _co) in brs:
                    for S, vs in d.items():
                        if S != Ck:
                            want.update((S, v) for v in vs)
        for _key, metas in self._emeta.items():           # ⭐ the addition
            for (rq, _st, _al) in metas:
                for S, vs in rq.items():
                    if S != Ck:
                        want.update((S, v) for v in vs)
        if not want:
            continue
        win = {}
        for k in dom:
            try:
                (_rooms, pv, _items), _conf = self._staged_pre(Ck, k, {})
            except Exception:
                win = None
                break
            for (S, v) in want:
                if v in pv.get(S, {0}):
                    win.setdefault((S, v), set()).add(k)
        if win:
            out[Ck] = win
    self._cwin_memo = out
    return out
s._consumer_windows = types.MethodType(cw, s)
s._cwin_memo = None
s._psucc_cache = {}
s._apply_consumer_windows()
s._psucc_cache = {}
s._pstates[C] = s._walk(C, frozenset())

print("win[268=1] =", sorted(s._consumer_windows().get(C, {}).get((R268, 1), [])) or "(none)")
print("edge 372->490 req:", [{k: sorted(v) for k, v in rq.items()}
                             for rq, _s, _a in (s._emeta.get((372, 490)) or [])])
print("rm410", days(410), " rm490", days(490), " rm480", days(480), " rm550", days(550))
print("rm480 day steps:", sorted(s._rstep.get(C, {}).get(480, ())))
s._cfd_memo = {}
t0 = time.time()
print(f"\nproducible_seal(123,4,370,flag44,0) = {s.producible_seal(C, w, r, flag44, 0)!r}"
      f"   ({time.time()-t0:.0f}s)")
