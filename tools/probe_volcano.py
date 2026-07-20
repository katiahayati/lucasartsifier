import os, ir as I, config, smv_emit3 as E
ir = I.load_ir(os.path.join(os.environ["CLAUDE_JOB_DIR"], "tmp", "lsl2_decomp", "lsl2.ir.json"))
em = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)

def indeliveries(dst):
    """All ways the model enters `dst`: flat edges, cs_edges, machine EXITs."""
    hits = []
    for e in em.ts.edges:
        if e.dst == dst: hits.append(("edge", e.src, e.guard))
    for e in em.ts.cs_edges:
        if e.dst == dst: hits.append(("cs_edge", e.src, e.guard))
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, trans) in paths:
                if trans and trans[0] == "EXIT" and trans[1] == dst:
                    hits.append((f"EXIT {info['inst']}@s{K}", info["room"], g))
    return hits

for rm in (82, 83, 84):
    print(f"\n=== in-deliveries to room {rm} ===")
    hs = indeliveries(rm)
    if not hs: print("   (NONE) <-- nothing enters this room")
    for kind, src, g in hs:
        print(f"   via {kind}  from room {src}   guard={g}")

# rm84Script: how does it reach state 81 (the g_148:=100 setter)?
print("\n=== rm84Script structure ===")
for info in em.machines:
    if info["room"] == 84:
        print("inst:", info["inst"], "script:", info["script"], "start:", info["start"])
        print("states:", sorted(info["states"].keys()))
        print("entries:", info.get("entries"))
        print("init_entries:", info.get("init_entries"))
        # trace transitions around 81
        for K in sorted(info["states"].keys()):
            for (g, w, gg, c, trans) in info["states"][K]:
                mark = "  <== sets g_148:=100" if any(x[0]==148 and x[1]==100 for x in w) else ""
                print(f"  s{K}: trans={trans} writes={w} gets={gg} guard={g}{mark}")
