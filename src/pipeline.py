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

Nothing about the title is declared on this path. The anchors (start room, victory room) are
DISCOVERED -- see anchors.py -- and so are the death signal and the debug globals, from the
game's own Game class and menu code (vocab.derive_death / derive_debug, via `configure` below).
The run prints all four, so what it derived is on the report rather than in a config file.
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
    """Point the analysis at this game and BLANK everything game-specific so it gets DERIVED.

    All four anchors, not just the two, and the two new ones are a GUARANTEE rather than a fix.
    `dataclasses.replace(config.ACTIVE, ...)` starts from whatever config is ACTIVE -- LSL2
    unless something changed it -- so a declared death signal or debug set on that entry would
    ride into every other game analysed through this CLI, judging King's Quest IV's deaths by
    Larry's `gCurrentStatus`. MEASURED before writing this (2026-08-14, and the first version of
    this note asserted the bug without measuring it): no entry in config.py declares either
    field today -- LSL2, KQ4 and KQ6 all carry `death_signal=()` and `debug_globals=frozenset()`
    -- so the CLI already derived them, and blanking here changes no output on any game. KQ4
    through this path derives `global127` and debug `{215}` and reports the same seven items as
    `config.KQ4` does, before the change and after it.

    It is still worth stating in code rather than trusting: what makes the derivation happen is
    the field being EMPTY (`missability.load` fills it from `vocab.derive_death` /
    `derive_death_sci11` / `derive_debug`), and this is the one entry point whose game arrives
    as a path with no config entry behind it. A future declared override on ACTIVE would
    otherwise leak here silently, which is the same class of mistake as the anchors this
    function already blanks.

    (The module docstring used to say "the run warns when it is falling back to LSL2's". No such
    warning existed anywhere in this file. What the run does instead is PRINT the derived death
    signal and debug globals, which is the fact that claim was reaching for.)"""
    import config
    cfg = dataclasses.replace(config.ACTIVE,
                              src_dir=os.path.join(os.path.dirname(ir_path), "src"),
                              ir_path=ir_path,
                              resource_dir=game_dir,
                              start_room=0, goal_rooms=frozenset(),
                              death_signal=(), debug_globals=frozenset())
    config.ACTIVE = cfg
    return cfg


def main(argv=None):
    ap = argparse.ArgumentParser(description="Find and patch softlocks in a Sierra SCI game.")
    ap.add_argument("game_dir", help="game directory (RESOURCE.MAP + RESOURCE.00x)")
    ap.add_argument("--out", default=os.path.join(_ROOT, "build"), help="output root")
    ap.add_argument("--report", action="store_true", help="analyse only; write no patch")
    ap.add_argument("--emit-unclosed", action="store_true",
                    help="emit even when some findings have no placeable guard (they are listed). "
                         "A guard that INTRODUCES a softlock still stops the run.")
    ap.add_argument("--skip-decompile", action="store_true", help="reuse <out>/ir")
    a = ap.parse_args(argv)
    # scicompile runs with the project dir as its cwd, so a RELATIVE --out makes every output
    # path resolve twice -- the whole emission fails with "Failed to open output file" while
    # placement and compilation report success. Absolutize once, here.
    a.out = os.path.abspath(a.out)

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
    # ...and the other two derived anchors, printed for the same reason: they decide what counts
    # as dying and what counts as a debug-only acquisition, so a reader has to be able to see
    # which globals this run picked without opening a config file. `load` writes both back into
    # the config it returns precisely so they can be reported.
    print(f"    death signal: global{s.em.cfg.death_signal[0]}"
          + (f" == {s.em.cfg.death_signal[1]}" if s.em.cfg.death_signal[1] is not None
             else " (any nonzero)")
          + f", debug globals: {sorted(s.em.cfg.debug_globals) or 'none'}  (derived)")
    print(f"    {len(s.rooms)} rooms, {len(s.comps)} strongly-connected components, "
          f"{len(s.regs)} gating registers")
    cands = s.analyze()
    joints = s.joint_strandings()
    tolls = s.toll_strandings()
    # EVERY DETECTOR, not the three stranding ones. This line used to union analyze/joint/toll
    # and stop, so the run reported five findings where the frozen surface (`snapshot.py`, the
    # thing the goldens freeze) had seven -- KQ4's Diamond Pouch and Fishing Pole are
    # register-flip strandings, sealed behind a plot flag rather than behind a door, and the
    # command in the README never mentioned them. A detector whose findings the tool's own
    # report omits is a detector emitting into the dark, which is the argument `snapshot.py`
    # makes for itself.
    extra = {"sealed by a plot flag": s.register_flip_strandings(),
             "wasted by a dangerous action": s.dangerous_sinks(),
             "fatal to use here": s.fatal_uses(),
             "sealed by a register flip": s.register_strandings()}
    items = sorted({c["item"] for c in cands} | {j["item"] for j in joints}
                   | {t["item"] for t in tolls}
                   | {r["item"] for rows in extra.values() for r in rows})
    groups = s.group_strandings()
    print(f"    softlocks: {len(items)} items"
          + (f" + {len(groups)} disjunctive group(s)" if groups else ""))
    why = {}
    for label, rows in extra.items():
        for r in rows:
            why.setdefault(r["item"], label)
    stranding = {c["item"] for c in cands} | {j["item"] for j in joints} \
        | {t["item"] for t in tolls}
    for i in items:
        print(f"      - {s.g.item_name(i)}"
              + ("" if i in stranding else f"  ({why.get(i, 'other detector')})"))
    for r in groups:
        print(f"      - {' or '.join(r['item_names'])}  (needed at rm{r['need_room']})")
    for j in joints:
        if j["item"] not in {c["item"] for c in cands}:
            print(f"      - {j['item_name']}  (behind a one-time window: {j['flags']})")
    for t in tolls:
        print(f"      - {t['item_name']}  (one-visit pocket rm{t['pocket']}, "
              f"toll {t['toll_item_name']} spent at rm{t['toll_edge'][0]})")

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
    introduced = bool(v["NEW"] or v["groups_new"])
    ok = not v["remaining"] and not introduced
    print(f"    fixed {len(v['fixed'])} + {len(v['groups_fixed'])} group(s); "
          f"NEW softlocks introduced: {[s.g.item_name(i) for i in v['NEW']] or 'none'}")
    if introduced:
        # NEVER overridable. Converting a softlock into a different softlock -- or into a wall --
        # is the one outcome this project treats as worse than shipping nothing.
        print("    \033[31mFAIL: a guard INTRODUCES a softlock\033[0m")
        return 1
    if not ok:
        remaining = [s.g.item_name(i) for i in v["remaining"]]
        if not a.emit_unclosed:
            print(f"    \033[31mFAIL: no guard closes {remaining}\033[0m")
            print("    (--emit-unclosed patches the rest anyway and lists what is left open)")
            return 1
        print(f"    \033[33m--emit-unclosed: NOT closed by any guard: {remaining}\033[0m")
        for x in refused:
            print(f"      still open, guard refused: {x['refused'][0][:110]}")
    print(f"    analysis took {time.time() - t0:.1f}s")

    if a.report:
        print("\n--report: stopping before writing anything.")
        return 0

    step(4, "PATCH")
    import patcher as P
    P.configure(s.em.ir)      # derive this game's object-global layout (ego/game/room)
    dest = os.path.join(a.out, "patch_project")
    out_dir = os.path.join(a.out, "patch")
    nums = P.assemble(dest, cfg)
    titles = {n: t for t, n in nums.items()}
    # The mode CHOOSER goes in first -- it is the mode's feasibility gate. A game that cannot
    # host a picker gets no mode plumbing at all (see install_mode_chooser: LB2's WrapMusic
    # species collision is what a needlessly recompiled Main costs).
    cedits = P.install_mode_chooser(dest, titles)
    for e in cedits:
        print(f"    [{'ok ' if e['applied'] else 'SKIP'}] mode-ui {e.get('title', '?')}"
              + (f"  ({e['why']})" if e.get("why") else ""))
    edits = P.apply_sink_remedies(dest, sinks, titles)
    gedits = P.apply_guards(dest, specs, titles, nums, s_drops=lambda it: s.drops.get(it, set()),
                            rooms=set(s.rooms),
                            entry_frontier=lambda r: G.commit_entry_frontier(s, r),
                            defer_info=lambda sp: G.defer_to_entry(s, sp))
    for e in edits + gedits:
        where = e.get("title") or (f"rm{e['from_room']}->rm{e['to_room']}" if "from_room" in e
                                   else f"script{e.get('script', '?')}")
        why = "" if e["applied"] else f"  ({e.get('why', 'not placed')})"
        print(f"    [{'ok ' if e['applied'] else 'SKIP'}] {where}{why}")
    # The mode/warned global DECLARATIONS -- AFTER every apply pass (the globals exist only in
    # emitted text), and NEVER merged into the apply_* rows (those are a frozen snapshot
    # surface). The chooser itself went in before the applies; see install_mode_chooser.
    uedits = cedits + P.declare_mode_globals(dest)
    for e in uedits[len(cedits):]:
        print(f"    [{'ok ' if e['applied'] else 'SKIP'}] mode-ui {e.get('title', '?')}"
              + (f"  ({e['why']})" if e.get("why") else ""))
    # A row edits ONE file -- except an entry-frontier row, which wraps every crossing into the
    # commit room. Collecting only `title` dropped rm320 from the v13 emission the moment rm300's
    # nav-assign joined the same row: the wrap compiled into the project and silently never
    # shipped. Every edited file must reach the patch set.
    touched = sorted({e["title"] for e in edits + gedits + uedits
                      if e["applied"] and e.get("title")}
                     | {p["title"] for e in gedits if e["applied"]
                        for p in e.get("entry_sites", ())}
                     | {p["title"] for e in gedits if e["applied"]
                        for p in e.get("award_gated", ())})
    r = P.compile_project(dest)
    print(f"    compiled {r['compiled']}/{r['total']} scripts")
    broken = [t for t, _ in r["failures"] if t in touched]
    if broken:
        # An edit is only guilty if the PRISTINE script compiles. KQ6's rm880 is one of the 5
        # decompiler-dialect failures (336/341) -- it fails to recompile edited or not -- so
        # blaming the edit would block the whole emission on an upstream gap. Such an edit is
        # REVERTED (pristine text restored), its rows downgraded to SKIP with the reason
        # stated, and the rest of the set still ships. An edit that broke a COMPILING script
        # still refuses the whole emission: that one is ours.
        import shutil
        ours = []
        for t in broken:
            shutil.copy(os.path.join(cfg.src_dir, t + ".sc"),
                        os.path.join(dest, "src", t + ".sc"))
            ok, _o = P.compile_one(dest, t, os.path.join(dest, t + ".chk"))
            if ok:
                ours.append(t)
            else:
                print(f"    [SKIP] {t}  (host script does not recompile even unedited -- "
                      f"pre-existing decompiler gap; edit reverted)")
                for e in edits + gedits:
                    if e.get("title") == t and e["applied"]:
                        e["applied"] = False
                        e["why"] = "host script does not recompile (pre-existing decompiler gap)"
                touched.remove(t)
        if ours:
            print(f"    \033[31mREFUSING to emit: edited script failed to compile: {ours}\033[0m")
            return 1
    written = P.emit_patches(dest, touched, nums, out_dir)
    for w in written:
        name = (" + ".join(os.path.basename(p) for p in w["paths"]) if w["ok"]
                else f"script {w['script']}")
        print(f"    {name}  {w['title']}"
              + (f"  {w['bytes']} bytes" if w["ok"] else f"  FAILED {w['error']}"))

    print(f"\n\033[1mDone.\033[0m {len(written)} patch files in {out_dir}")
    print(f"  install:  cp {out_dir}/* <copy-of-game>/")
    print(f"  revert :  delete those files (the game's own resources were never touched)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
