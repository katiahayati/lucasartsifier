import sys, os
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C = 123
s._rp_xcache = {}
pre, conf = s._staged_pre(C, 3, {}, require_steps=True)
rooms, pv, items = pre
print("day-3 closure rooms:", len(rooms))
for q in (50, 510, 500, 520, 530, 540, 550, 480, 490, 372, 205):
    print(f"   rm{q} in closure: {q in rooms}")
print("\npv[12] (prevRoom) contains 510?", 510 in pv.get(12, ()), " | 750?", 750 in pv.get(12, ()))
print("pv[12] size:", len(pv.get(12, ())))
print("\n--- who writes prevRoom := 510 in the closure tables? ---")
writes, grants, gets, edges, _gr = s._closure_tables()
for (gi, v, room, g, _a, _b) in writes:
    if gi == 12 and v == 510:
        print(f"   write 12:=510 @rm{room} guard={str(g)[:120]}")
for e in edges:
    if e[3].get(12) == 510:
        print(f"   edge {e[0]} -> {e[1]} sets 12:=510  guard={str(e[2])[:120]}")
print("\n--- rm490 (mask room) and flag 216 ---")
print("   rm490 in day-3 closure:", 490 in rooms, " | croc mask (21) held:", 21 in items)
print("   flag216 (458) in pv:", sorted(pv.get(458, ())), " flag299 (541):", sorted(pv.get(541, ())))
print("   reg 545 (flag303) in pv:", sorted(pv.get(545, ())), " reg 521:", sorted(pv.get(521, ())))
