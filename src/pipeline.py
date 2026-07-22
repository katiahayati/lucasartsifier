"""End-to-end: a Sierra SCI game directory in, a softlock patch out.

    python -m pipeline /path/to/game            # decompile, analyse, patch
    python -m pipeline /path/to/game --report   # analyse only, write nothing

Stages, each one runnable on its own if you want to poke at the middle:

    1. DECOMPILE   sci-tools (our fork) reads RESOURCE.MAP/00x and emits both a `.sc` tree and a
                   typed-AST JSON IR.                                    -> <out>/ir/
    2. ANALYSE     lift room scripts to state machines, build a gate-aware movement model, and
                   find items that are REQUIRED and IRREVERSIBLY MISSABLE.
    3. DERIVE      turn each stranding into a guard condition taken from the winning region, and
                   each item-destroying dead-end action into a removal.
    4. PATCH       edit the `.sc` sources, compile with scicompile, and wrap the changed scripts
                   as ScummVM loose patch files.                          -> <out>/patch/

The game's own resources are never modified: `script.NNN` files dropped in the game folder
override the mapped resource, and deleting them reverts.

Anchors (start room, victory room) are DISCOVERED -- see anchors.py -- so a new title needs no
room numbers declared. Two things still are game-specific: the death signal and the debug globals,
both in config.py. The run warns when it is falling back to LSL2's.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SNUFFER = os.path.join(_ROOT, "vendor", "sci-tools", "Snuffer", "bin", "Release",
                       "net8.0", "Snuffer.dll")


def step(n, title):
    print(f"\n\033[1m[{n}] {title}\033[0m", flush=True)


def decompile(game_dir, out_dir):
    """sci-tools -> .sc tree + <game>.ir.json. Requires the ORIGINAL resources, not a .sc tree."""
    if not os.path.exists(SNUFFER):
        raise SystemExit(f"decompiler not built: {SNUFFER}\n"
                         f"  run: tools/sci-tools-fork/build.sh")
    os.makedirs(out_dir, exist_ok=True)
    t0 = time.time()
    p = subprocess.run(["dotnet", SNUFFER, "-d", "--json", game_dir, out_dir],
                       capture_output=True, text=True, timeout=1800)
    tail = [l for l in (p.stdout + p.stderr).splitlines() if "%" in l or "TIME" in l]
    for l in tail[-5:]:
        print("   ", l.strip())
    irs = [f for f in os.listdir(out_dir) if f.endswith(".ir.json")]
    if not irs:
        raise SystemExit("decompilation produced no IR:\n" + (p.stdout + p.stderr)[-1500:])
    print(f"    -> {out_dir}/{irs[0]}  ({time.time() - t0:.1f}s)")
    return os.path.join(out_dir, irs[0])


def configure(ir_path, game_dir):
    """Point the analysis at this game and BLANK the anchors so they get discovered."""
    import config
    cfg = dataclasses.replace(config.ACTIVE,
                              src_dir=os.path.join(os.path.dirname(ir_path), "src"),
                              ir_path=ir_path,
                              resource_dir=game_dir,
                              start_room=0, goal_rooms=frozenset())
    config.ACTIVE = cfg
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find and patch softlocks in a Sierra SCI game.")
    ap.add_argument("game_dir", help="game directory (RESOURCE.MAP + RESOURCE.00x)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "build"), help="output root")
    ap.add_argument("--report", action="store_true", help="analyse only; write no patch")
    ap.add_argument("--skip-decompile", action="store_true", help="reuse <out>/ir")
    a = ap.parse_args(argv)

    if not os.path.isdir(a.game_dir):
        raise SystemExit(f"no such game directory: {a.game_dir}")
    ir_dir = os.path.join(a.out, "ir")

    step(1, "DECOMPILE")
    if a.skip_decompile:
        irs = [f for f in os.listdir(ir_dir) if f.endswith(".ir.json")]
        ir_path = os.path.join(ir_dir, irs[0])
        print(f"    reusing {ir_path}")
    else:
        ir_path = decompile(a.game_dir, ir_dir)

    cfg = configure(ir_path, a.game_dir)
    import missability as M
    import guards as G

    step(2, "ANALYSE")
    t0 = time.time()
    s = M.load(cfg=cfg)
    print(f"    anchors: start rm{s.em.cfg.start_room}, victory "
          f"{sorted(s.em.cfg.goal_rooms)}  (discovered)")
    print(f"    {len(s.rooms)} rooms, {len(s.comps)} strongly-connected components, "
          f"{len(s.regs)} gating registers")
    cands = s.analyze()
    joints = s.joint_strandings()
    items = sorted({c["item"] for c in cands} | {j["item"] for j in joints})
    groups = s.group_strandings()
    print(f"    softlocks: {len(items)} items"
          + (f" + {len(groups)} disjunctive group(s)" if groups else ""))
    for i in items:
        print(f"      - {s.g.item_name(i)}")
    for r in groups:
        print(f"      - {' or '.join(r['item_names'])}  (needed at rm{r['need_room']})")
    for j in joints:
        if j["item"] not in {c["item"] for c in cands}:
            print(f"      - {j['item_name']}  (behind a one-time window: {j['flags']})")

    step(3, "DERIVE")
    specs = G.guard_specs(s)
    sinks = G.sink_remedies(s)
    edges = [x for x in specs if x["site"] == "edge" and not x["refused"]]
    for sp in edges:
        print(f"    rm{sp['from_room']} -> rm{sp['to_room']}: {sp['condition']}")
    for sk in sinks:
        if not sk["refused"]:
            print(f"    rm{sk['room']}: {sk['edit']} ({s.g.item_name(sk['item'])})")
    refused = [x for x in specs + sinks if x["refused"]]
    for x in refused:
        print(f"    REFUSED: {x['refused']}")
    print(f"    verifying against the guarded model...")
    v = G.verify(s, specs)
    ok = not v["remaining"] and not v["NEW"] and not v["groups_new"]
    print(f"    fixed {len(v['fixed'])} + {len(v['groups_fixed'])} group(s); "
          f"NEW softlocks introduced: {[s.g.item_name(i) for i in v['NEW']] or 'none'}")
    if not ok:
        print("    \033[31mFAIL: the guards do not close every softlock, or create one\033[0m")
        return 1
    print(f"    analysis took {time.time() - t0:.1f}s")

    if a.report:
        print("\n--report: stopping before writing anything.")
        return 0

    step(4, "PATCH")
    import patcher as P
    dest = os.path.join(a.out, "patch_project")
    out_dir = os.path.join(a.out, "patch")
    nums = P.assemble(dest, cfg)
    titles = {n: t for t, n in nums.items()}
    edits = P.apply_sink_remedies(dest, sinks, titles)
    gedits = P.apply_guards(dest, specs, titles, nums, s_drops=lambda it: s.drops.get(it, set()))
    for e in edits + gedits:
        where = e.get("title") or (f"rm{e['from_room']}->rm{e['to_room']}" if "from_room" in e
                                   else f"script{e.get('script', '?')}")
        why = "" if e["applied"] else f"  ({e.get('why', 'not placed')})"
        print(f"    [{'ok ' if e['applied'] else 'SKIP'}] {where}{why}")
    touched = sorted({e["title"] for e in edits + gedits if e["applied"]})
    r = P.compile_project(dest)
    print(f"    compiled {r['compiled']}/{r['total']} scripts")
    broken = [t for t, _ in r["failures"] if t in touched]
    if broken:
        print(f"    \033[31mREFUSING to emit: edited script failed to compile: {broken}\033[0m")
        return 1
    written = P.emit_patches(dest, touched, nums, out_dir)
    for w in written:
        print(f"    script.{w['script']:03d}  {w['title']}"
              + (f"  {w['bytes']} bytes" if w["ok"] else f"  FAILED {w['error']}"))

    print(f"\n\033[1mDone.\033[0m {len(written)} patch files in {out_dir}")
    print(f"  install:  cp {out_dir}/script.* <copy-of-game>/")
    print(f"  revert :  delete those files (the game's own resources were never touched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
