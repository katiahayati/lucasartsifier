import sys, json
sys.path.insert(0, sys.argv[1] + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
goal = s.goal_rooms_set()
bad = {}
for R in s.proj:
    starts = {p for p in s._pstates[R] if p[0] == 480}
    if not starts:
        continue
    rooms = {r for r, _ in s._walk(R, frozenset(), starts)}
    if not (goal & rooms):
        bad[str(R)] = {"n_starts": len(starts), "n_rooms": len(rooms),
                       "start_vals": sorted({v for (_r, v) in starts})[:8]}
print(json.dumps({"projections_missing_the_goal_from_480": bad}, indent=1))
