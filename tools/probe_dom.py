import os, re, ir as I, config, smv_emit3 as E
ir = I.load_ir(os.path.join(os.environ["CLAUDE_JOB_DIR"], "tmp", "lsl2_decomp", "lsl2.ir.json"))
em = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)
smv, _ = em.emit()
lines = smv.splitlines()

# 1) declared ranges for every ms_ variable
rng = {}
for ln in lines:
    m = re.match(r"\s*(ms_\w+)\s*:\s*(-?\d+)\s*\.\.\s*(-?\d+);", ln)
    if m:
        rng[m.group(1)] = (int(m.group(2)), int(m.group(3)))

# 2) walk next(ms_..) := case blocks, collect integer targets, flag out-of-range
cur = None
oor = {}   # var -> set of out-of-range target values
i = 0
while i < len(lines):
    m = re.match(r"\s*next\((ms_\w+)\)\s*:=\s*case", lines[i])
    if m:
        cur = m.group(1); i += 1
        while i < len(lines) and lines[i].strip() != "esac;":
            mm = re.match(r"\s*(.*?)\s*:\s*(-?\d+)\s*;\s*$", lines[i])
            if mm and cur in rng:
                v = int(mm.group(2)); lo, hi = rng[cur]
                if not (lo <= v <= hi):
                    oor.setdefault(cur, {}).setdefault(v, []).append(mm.group(1)[:90])
            i += 1
        cur = None
    i += 1

print("machines total:", len(rng))
print("machines with OUT-OF-RANGE ms targets:", len(oor))
for var in sorted(oor):
    lo, hi = rng[var]
    print(f"\n{var}  declared {lo}..{hi}")
    for v in sorted(oor[var]):
        print(f"   -> assigns {v}  ({len(oor[var][v])} case(s)); e.g. guard: {oor[var][v][0]}")

# 3) is any out-of-range machine on the endgame path? print those rooms' scripts
print("\nendgame-relevant scripts among the flagged:",
      [v for v in oor if any(s in v for s in ("_82","_83","_84","_85","_92","_78","_77","_75"))] or "NONE")
