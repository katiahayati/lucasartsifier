import sys, os
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
writes, grants, gets, edges, _gr = s._closure_tables()
for t in (510, 490, 520, 530, 540, 700):
    print(f"=== closure edges INTO rm{t} ===")
    for e in edges:
        if e[1] == t:
            print(f"   {e[0]} -> {e[1]}  guard={e[2]}  sets={e[3]}")
print("\n=== who raises flag 299 (reg 541) and flag 216 (reg 458)? ===")
for R, nm in ((541, "flag299 tattoo"), (458, "flag216 mask-used")):
    for (Rk, room, v), brs in sorted(s._wbranch.items(), key=str):
        if Rk == R and v == 1:
            for (d, cost, co) in brs:
                print(f"   {nm}: :=1 @rm{room} deps={ {a: sorted(x) for a, x in sorted(d.items())} } cost={sorted(cost)}")
