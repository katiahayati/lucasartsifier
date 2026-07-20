import os, collections, ir as I, config, smv_emit3 as E
ir = I.load_ir(os.path.join(os.environ["CLAUDE_JOB_DIR"], "tmp", "lsl2_decomp", "lsl2.ir.json"))
em = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)

# ---- 1. guard-IGNORING room reachability from start ----
g = collections.defaultdict(set)
md = em.machine_delivered
for e in em.ts.edges:      g[e.src].add(e.dst)
for e in em.ts.cs_edges:
    if (e.src, e.dst) not in md: g[e.src].add(e.dst)
for info in em.machines:
    for K, paths in info["states"].items():
        for (gd, w, gg, c, trans) in paths:
            if trans and trans[0] == "EXIT": g[info["room"]].add(trans[1])
seen, q = {em.cfg.start_room}, [em.cfg.start_room]
while q:
    r = q.pop()
    for d in g[r]:
        if d not in seen: seen.add(d); q.append(d)
for rm in (181, 82, 83, 84, 85, 92, 178):
    print(f"room {rm} reachable ignoring guards: {rm in seen}")

# who reaches 181?
print("\nin-deliveries to 181:")
for e in em.ts.edges:
    if e.dst == 181: print("   edge from", e.src, "guard", e.guard)
for e in em.ts.cs_edges:
    if e.dst == 181 and (e.src,181) not in md: print("   cs_edge from", e.src, "guard", e.guard)
for info in em.machines:
    for K, paths in info["states"].items():
        for (gd,w,gg,c,trans) in paths:
            if trans and trans[0]=="EXIT" and trans[1]==181:
                print(f"   EXIT {info['inst']}@s{K} (room {info['room']}) guard {gd}")

# ---- 2. rm82Script: states, entries, where is (L,3) [causedEruption] written? ----
print("\n=== rm82Script ===")
for info in em.machines:
    if info["inst"] == "rm82Script":
        print("start:", info["start"], "entries:", info.get("entries"),
              "init_entries:", info.get("init_entries"))
        for K in sorted(info["states"].keys()):
            for (gd, w, gg, c, trans) in info["states"][K]:
                notes = []
                for (nm, kind, val) in c:
                    if nm == ("L", 3): notes.append(f"L3<-{kind}:{val}")
                if gg: notes.append(f"gets={gg}")
                tag = ("  " + " ".join(notes)) if notes else ""
                print(f"  s{K}: trans={trans} guard={gd}{tag}")

# ---- 3. every write to (82,'L',3) anywhere ----
print("\nall (82,L,3) counter writes in machines:")
for info in em.machines:
    if info["script"] != 82: continue
    for K, paths in info["states"].items():
        for (gd,w,gg,c,trans) in paths:
            for (nm,kind,val) in c:
                if nm==("L",3): print(f"   {info['inst']}@s{K}: {kind}:{val} guard={gd}")
print("handler_locals touching (82,L,3):")
for (room,script,name,v,gd) in em.handler_locals:
    if script==82 and name==("L",3): print(f"   room{room}: v={v} guard={gd}")
