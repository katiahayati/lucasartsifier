"""What does the CURRENT gate-generation half produce on a game?

    MEASURE_OUT=/tmp/m python3 tools/measure_specs.py KQ6

Dumps every spec/remedy shape guards.py knows plus the raw findings, so the plan is
written against measurement rather than memory. Streams progress (see the memory note on
long-running scripts).
"""
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_ROOT, "src"))
OUT = os.environ.get("MEASURE_OUT", "/tmp/measure")
os.makedirs(OUT, exist_ok=True)

import config          # noqa: E402
import missability as M  # noqa: E402
import guards as G     # noqa: E402

T0 = time.time()


def log(*a):
    print("[%6.1fs]" % (time.time() - T0), *a, flush=True)


def run(cfg):
    log("loading", cfg.name)
    s = M.load(cfg=cfg)
    log("loaded: %d rooms, %d comps, %d regs; start=%s goal=%s"
        % (len(s.rooms), len(s.comps), len(s.regs), s.em.cfg.start_room,
           sorted(s.em.cfg.goal_rooms)))
    out = {"name": cfg.name, "start": s.em.cfg.start_room,
           "goal": sorted(s.em.cfg.goal_rooms)}

    cands = s.analyze()
    log("analyze -> %d candidates" % len(cands))
    out["candidates"] = [{"item": s.g.item_name(c["item"]), "raw": c.get("kind"),
                          "from": c.get("from_room"), "to": c.get("to_room"),
                          "why": c.get("why")} for c in cands]

    for nm, fn in [("edge_strandings", s.edge_strandings),
                   ("joint", s.joint_strandings), ("groups", s.group_strandings),
                   ("tolls", s.toll_strandings),
                   ("register_flips", s.register_flip_strandings),
                   ("dangerous_sinks", s.dangerous_sinks),
                   ("fatal_uses", s.fatal_uses),
                   ("resource_exhaustion", s.resource_exhaustion)]:
        try:
            r = fn()
        except Exception as e:                       # noqa: BLE001
            r = [{"ERROR": repr(e)}]
        log("%s -> %d" % (nm, len(r)))
        out[nm] = [{k: (s.g.item_name(v) if k == "item" and isinstance(v, int) else v)
                    for k, v in x.items() if not k.startswith("_")} for x in r]

    log("guard_specs...")
    specs = G.guard_specs(s)
    log("guard_specs -> %d" % len(specs))
    out["specs"] = specs
    out["sinks"] = G.sink_remedies(s)
    out["resource_remedies"] = G.resource_remedies(s)
    log("sinks -> %d, resource -> %d" % (len(out["sinks"]), len(out["resource_remedies"])))
    return out, s, specs


def sweep_config(name):
    """A GameConfig for any decompiled game under build/sweep/<name>/ -- paths only, every
    anchor left blank so the derivations run. Lets this tool reach a title config.py does not
    name (Dagger, Camelot, ...) without hand-rolling a config per game."""
    import glob
    d = os.path.join(_ROOT, "build", "sweep", name)
    irs = glob.glob(os.path.join(d, "*.ir.json"))
    if not irs:
        raise SystemExit("no IR under %s" % d)
    title = os.path.basename(irs[0])[:-len(".ir.json")]
    res = os.path.expanduser(os.path.join("~", "sierra", "Games", title))
    return config.GameConfig(name=title, src_dir=os.path.join(d, "src"), ir_path=irs[0],
                             resource_dir=res, start_room=0, goal_rooms=frozenset(),
                             death_signal=(), debug_globals=frozenset())


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "KQ6"
    cfg = getattr(config, which, None) or sweep_config(which)
    out, s, specs = run(cfg)
    dest = os.path.join(OUT, "%s_specs.json" % which.lower())
    with open(dest, "w") as f:
        json.dump(out, f, indent=2, default=str)
    log("wrote", dest)

    # PLACEMENT: what would today's patcher do with those specs on this game's own sources?
    log("placement pass (assemble + apply, no compile)...")
    import patcher as P
    P.configure(s.em.ir)
    pdest = os.path.join(OUT, "_proj_%s" % which.lower())
    nums = P.assemble(pdest, cfg)
    titles = {n: t for t, n in nums.items()}
    log("assembled %d scripts -> %s" % (len(nums), pdest))
    edits = P.apply_sink_remedies(pdest, G.sink_remedies(s), titles)
    gedits = P.apply_guards(pdest, specs, titles, nums,
                            s_drops=lambda it: s.drops.get(it, set()))
    place = [{"where": e.get("title") or "rm%s->rm%s" % (e.get("from_room"), e.get("to_room")),
              "applied": e["applied"], "kind": e.get("placement", {}).get("kind"),
              "why": e.get("why"), "cond": e.get("condition")}
             for e in edits + gedits]
    with open(dest.replace(".json", "_placements.json"), "w") as f:
        json.dump(place, f, indent=2, default=str)
    log("placements: %d applied / %d total"
        % (sum(1 for p in place if p["applied"]), len(place)))
    for p in place:
        log("   [%s] %-24s %-12s %s" % ("ok " if p["applied"] else "SKIP", p["where"],
                                        p["kind"], (p["why"] or "")[:70]))


if __name__ == "__main__":
    main()
