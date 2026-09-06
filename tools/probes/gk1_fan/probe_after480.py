import sys, json
sys.path.insert(0, sys.argv[1] + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
fwd = s.rooms_after(480)
print(json.dumps({"n": len(fwd), "rooms": sorted(fwd),
                  "goal": sorted(s.goal_rooms_set()),
                  "goal_reachable": bool(s.goal_rooms_set() & fwd)}))
