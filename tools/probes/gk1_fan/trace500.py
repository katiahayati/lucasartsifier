"""How does the day projection reach rm500 at day 2? BFS the projection and record the first
(room, value) predecessor for each state, then walk the chain back."""
import sys, os
WT = os.path.dirname(os.path.abspath(__file__)) + "/wt134"
sys.path.insert(0, WT + "/src")
import config, missability as M
s = M.load(cfg=config.by_name("gk1"))
C = 123
start = (s.em.cfg.start_room, 0)
seen = {start: None}
q = [start]
while q:
    u = q.pop(0)
    for v in s._psucc(C, u, frozenset()):
        if v not in seen:
            seen[v] = u
            q.append(v)
for target in [(500, 2), (510, 2), (750, 2), (500, 3), (480, 6)]:
    if target not in seen:
        print(f"{target}: unreachable")
        continue
    chain, cur = [], target
    while cur is not None and len(chain) < 30:
        chain.append(cur)
        cur = seen[cur]
    print(f"\n{target} reached via (nearest first):")
    print("   " + " <- ".join(f"rm{r}@{v}" for (r, v) in chain[:14]))
