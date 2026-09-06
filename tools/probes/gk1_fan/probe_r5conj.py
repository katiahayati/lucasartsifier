import sys
sys.path.insert(0, sys.argv[1] + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
a, b, it = 490, 480, 21
u = frozenset({it})
print("edge_kind[(490,480)]:", sorted(s.edge_kind.get((a, b), set())))
print("490 in reach_rooms:", a in s.reach_rooms)
print("_freely_reversible(490,480):", s._freely_reversible(a, b))
print("comp_of[480]:", s.comp_of.get(b))
fwd = s.rooms_after(b)
print("rooms_after(480):", len(fwd), "rooms; goal reachable:", bool(s.goal_rooms_set() & fwd))
print("   is 490 in rooms_after(480)?", a in fwd)
print("   sample:", sorted(fwd)[:16])
reob = s.reobtainable_rooms(it)
print("reobtainable_rooms(mask): 490 in:", a in reob, " 480 in:", b in reob, f"({len(reob)} rooms)")
need = s._unit_need_rooms(u)
print("need rooms:", sorted(need), " need & fwd:", sorted(need & fwd))
