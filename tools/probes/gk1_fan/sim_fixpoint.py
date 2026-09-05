"""The windows need a bounded fan; the fan needs the windows. Iterate the pair to a fixpoint."""
import sys, os, time
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C, flag44 = 123, None
flag44 = s.em.ir.flag_synth_base + 44
days = lambda q: sorted({v for (q2, v) in s._pstates[C] if q2 == q})

def show(tag):
    print(f"\n{tag}")
    print("   rm480", days(480), " rm500", days(500), " rm510", days(510), " rm550", days(550))
    for room in (370, 480, 500, 550):
        print(f"   rm{room} steps: {sorted(s._rstep.get(C, {}).get(room, ()))}")
    print("   neco(3,4) =", {k: v for k, v in sorted(s._step_neco(C, 3, 4).items())})

show("PASS 0 (as built)")
for it in range(1, 6):
    s._cwin_memo = None
    s._apply_consumer_windows()
    s._psucc_cache = {}
    s._entrance_rooms_memo = None
    for R in s.proj:
        if R == C or (isinstance(R, tuple) and C in R):
            s._pstates[R] = s._walk(R, frozenset())
    before = {q: tuple(days(q)) for q in (480, 500, 510, 550)}
    steps_before = {r: frozenset(v) for r, v in s._rstep.get(C, {}).items()}
    s._prune_unattainable_steps()
    after = {q: tuple(days(q)) for q in (480, 500, 510, 550)}
    steps_after = {r: frozenset(v) for r, v in s._rstep.get(C, {}).items()}
    show(f"PASS {it}")
    if before == after and steps_before == steps_after:
        print(f"\n   fixpoint reached at pass {it}")
        break
s._cfd_memo = {}
t0 = time.time()
print(f"\n⭐ producible_seal(123,4,370,flag44,0) = {s.producible_seal(C, 4, 370, flag44, 0)!r}"
      f"   ({time.time()-t0:.0f}s)")
