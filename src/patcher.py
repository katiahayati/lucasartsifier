"""Emit a patched game from the guard specs -- the 'prevent' half, made real.

Pipeline, all on ONE decompilation (ours):

    build/ir/src/*.sc            our sluicebox decompilation (regenerate: tools/sci-tools-fork/build.sh)
      -> assemble()              a compilable project: sources + game.ini + the game's resources
      -> apply_*()               the edits guards.py derived
      -> scicompile --sco/--all  interface files, then compile
      -> emit_patches()          script.NNN loose patch files ScummVM reads in preference

Nothing here decides WHAT to patch: `guards.py` owns that, and every edit carries the spec that
justified it. This module only turns specs into bytes.

The loose-patch format (SCI0), per SCICompanion's own writer and ScummVM's reader:

    byte 0 : 0x80 | ResourceType   -> 0x80 | 2 (Script) = 0x82
    byte 1 : 0x00                  -> SCI0 has no extra resource header
    byte 2+: the raw compiled script

Dropping `script.NNN` into the game folder overrides the mapped resource, so the original
RESOURCE.MAP/volumes are never touched and the patch is trivially reversible: delete the files.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys

import config
import guards as G
import missability as M
from sexpr import read_file
from trigger import find_trigger, wrap_trigger_in_source

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
SCICOMPILE = os.path.join(_ROOT, "tools", "scicompile", "build", "scicompile")
RES_TYPE_SCRIPT = 2


def _script_numbers(src_dir):
    """title -> script number, read from each source's own `(script# N)` declaration."""
    out = {}
    for fn in sorted(os.listdir(src_dir)):
        if not fn.endswith(".sc"):
            continue
        m = re.search(r"\(script#\s*(\d+)\)", open(os.path.join(src_dir, fn), errors="replace").read())
        if m:
            out[fn[:-3]] = int(m.group(1))
    return out


def assemble(dest, cfg=None):
    """Build a compilable project directory from our decompilation + the pristine resources."""
    cfg = cfg or config.ACTIVE
    src = cfg.src_dir
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    os.makedirs(os.path.join(dest, "src"))
    for fn in os.listdir(src):
        if fn.endswith(".sc"):
            shutil.copy(os.path.join(src, fn), os.path.join(dest, "src", fn))
    # the compiler reads vocab.997/996/000 out of the game's own volumes
    for fn in os.listdir(cfg.resource_dir):
        if fn.lower().startswith("resource."):
            shutil.copy(os.path.join(cfg.resource_dir, fn), os.path.join(dest, fn))

    nums = _script_numbers(os.path.join(dest, "src"))
    with open(os.path.join(dest, "game.ini"), "w") as f:
        f.write("[Game]\nLanguage=sci\nName=%s\n[Script]\n" % cfg.name)
        for title, n in sorted(nums.items(), key=lambda kv: kv[1]):
            f.write("n%03d=%s\n" % (n, title))
    _declare_missing_globals(os.path.join(dest, "src"))
    return nums


def _declare_missing_globals(src_dir):
    """Extend script 0's local block to cover every global the game actually reads.

    Globals ARE script 0's locals. LSL2 reads `global480` while the block declares 0..479, so the
    compiler rejects rm63 -- a patch site. The decompilation is faithful; the declaration is just
    short. Compile-time only: a room compiles to an absolute global index that the interpreter
    resolves against its own array, which the shipped game already indexes this far."""
    main = os.path.join(src_dir, "Main.sc")
    if not os.path.exists(main):
        return 0
    txt = open(main, errors="replace").read()
    highest = max((int(m) for m in re.findall(r"\bglobal(\d+)\b", _all_sources(src_dir))), default=-1)
    declared = set(int(m) for m in re.findall(r"^\s*global(\d+)\s*$", txt, re.M))
    missing = [g for g in range(highest + 1) if g not in declared and g > max(declared or {0})]
    if not missing:
        return 0
    lines = txt.splitlines(True)
    start = next(i for i, l in enumerate(lines) if l.startswith("(local"))
    depth = 0
    end = start
    for i in range(start, len(lines)):
        depth += lines[i].count("(") - lines[i].count(")")
        if depth == 0:
            end = i
            break
    for g in reversed(missing):
        lines.insert(end, "\tglobal%d\n" % g)
    open(main, "w").write("".join(lines))
    return len(missing)


def _all_sources(src_dir):
    parts = []
    for fn in sorted(os.listdir(src_dir)):
        if fn.endswith(".sc"):
            parts.append(open(os.path.join(src_dir, fn), errors="replace").read())
    return "\n".join(parts)


def apply_sink_remedies(dest, sinks, titles_by_num):
    """Delete the item consumption in each dangerous PURE SINK.

    Safe by construction: a pure sink is a clause that does nothing EXCEPT destroy the item (it
    arms no machine state and writes no register any guard reads), so removing its one effect
    cannot perturb anything else. The joke and the score penalty stay; the player keeps the item."""
    edits = []
    seen = set()
    for sk in sinks:
        if sk["refused"]:
            continue
        # One CLAUSE can be reported at several rooms: the airsick-bag sink is script 600, a
        # REGION covering rm61/62/63, so the same `put: 27 -1` shows up three times. Edit once.
        key = (sk["script"], sk["item"])
        if key in seen:
            continue
        seen.add(key)
        title = titles_by_num.get(sk["script"])
        if title is None:
            continue
        path = os.path.join(dest, "src", title + ".sc")
        lines = open(path, errors="replace").read().splitlines(True)
        pat = re.compile(r"^\s*\(global0\s+put:\s*%d\s+-1\)\s*$" % sk["item"])
        hits = [i for i, l in enumerate(lines) if pat.match(l)]
        if len(hits) != 1:
            edits.append({**sk, "applied": False,
                          "why": "expected exactly one `put: %d -1` in %s, found %d"
                                 % (sk["item"], title, len(hits))})
            continue
        i = hits[0]
        # Replace the consumption with a LINE OF TEXT, not silence. The clause has just announced
        # an IRREVERSIBLE act -- "You carefully pour your bottle ... on the padlock", "You dump the
        # bottle ... on the ice", "You do so and immediately discard the now-soiled airsick bag" --
        # so deleting only the `put:` leaves the game insisting you lost something you are still
        # holding. Reported from live play, twice. A retraction cannot be "you thought better of
        # it" either: you cannot un-pour a bottle. It has to be an explicit joke, which is well
        # within this game's register. Wording is the user's.
        # No apostrophes: a single quote opens a Said spec.
        indent = re.match(r"[ \t]*", lines[i]).group(0)
        lines[i] = ("%s(proc255_0 {Just kidding! You hold on to it because you still need it.})\n"
                    % indent)
        open(path, "w").write("".join(lines))
        edits.append({**sk, "applied": True, "title": title, "line": i + 1})
    return edits


REFUSE = "(proc0_15)"
# `NotNow` -- the standard SCI refusal. In this decompilation Main's procedures are numbered, and
# proc0_15 prints script 0 message 134, "Not now!" (dumped from the game's text.000; the whole
# family is proc0_N -> message N+119).
#
# NOT proc0_20 (message 139, "You don't have it."), which was the first choice and LIES: reported
# from live play at rm26, "give passport to man" answered "you don't have it" while the player was
# holding the passport. What they lacked was something else entirely, needed later. A refusal that
# misdescribes the reason sends the player hunting for the wrong thing.

def to_source_syntax(cond):
    """Our specs say `gEgo`; this decompilation names the ego `global0`."""
    return cond.replace("(gEgo has:", "(global0 has:")


DIRECTIONS = ("north", "south", "east", "west")


EDGEHIT = {"north": 1, "east": 2, "south": 3, "west": 4}   # Game.sc Rm.doit switch


def guard_edgehit_clause(text, direction, cond):
    """Guard a room script's own `edgeHit` reaction, which is the real trigger for a
    room-property exit.

    `Rm.doit` runs `(script doit:)` BEFORE it reads the direction property, so a room whose script
    reacts to the edge (rm47 awards 12 points and prints "You made it!") will fire that reaction
    even when the exit is closed -- and since nothing moves the ego off the edge, `edgeHit` stays
    set and it repeats forever. That is a real loop, found by play-testing, and it is why closing
    the property alone is NOT enough here.

    So: wrap the clause body, and on refusal clear `edgeHit` (exactly as `Rm.init` does) and step
    the ego back from the boundary so the flag cannot immediately re-arm."""
    n = EDGEHIT.get(direction)
    if n is None:
        return text, 0
    m = re.search(r"\(\(==\s*%d\s*\(global0\s+edgeHit:\)\)" % n, text)
    if not m:
        return text, 0
    # body = everything between the clause condition and the clause's closing paren
    depth, i = 1, m.end()
    while i < len(text) and depth:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
        i += 1
    body = text[m.end():i - 1]
    wrapped = ("\n\t\t\t\t(if %s%s\n\t\t\t\telse\n"
               "\t\t\t\t\t(global0 setMotion: 0)\n"
               "\t\t\t\t\t(global0 x: (- (global0 x:) 12))\n"
               "\t\t\t\t\t(global0 edgeHit: 0)   ; else the clause re-fires every cycle\n"
               "\t\t\t\t\t(proc0_15)  ; softlock-guard\n\t\t\t\t)\n\t\t\t" % (cond, body))
    return text[:m.end()] + wrapped + text[i - 1:], 1


def guard_edge_exit(text, inst_name, to_room, cond):
    """Guard a ROOM-PROPERTY exit (`east 48`), which no `newRoom:` call can be wrapped around.

    Walking off-screen is engine-handled: the Rm instance names the neighbour in a property, so
    there is no call site for `trigger.find_trigger` to find. The game's own idiom for closing such
    an exit is `(global2 <dir>: 0)` -- used in rm15, rm42, rm74 and rm77 -- so we re-evaluate the
    guard on every room entry and close the exit when it fails.

    Silent by nature: a disabled edge behaves as a wall, with no refusal text. That is how the game
    already does it, and it is the only lever available for this kind of exit."""
    m = re.search(r"\(instance\s+%s\s+of\s+Rm\b" % re.escape(inst_name), text)
    if not m:
        return text, 0, None
    props = re.search(r"\(properties(.*?)\)", text[m.start():], re.S)
    if not props:
        return text, 0, None
    direction = None
    for d in DIRECTIONS:
        pm = re.search(r"\b%s\s+(\d+)\b" % d, props.group(1))
        if pm and int(pm.group(1)) == to_room:
            direction = d
            break
    if direction is None:
        return text, 0, None
    # If the room's script reacts to this edge, guard THAT clause instead: closing the property
    # would let the reaction fire on a loop (see guard_edgehit_clause).
    new_text, n = guard_edgehit_clause(text, direction, cond)
    if n:
        return new_text, n, direction + " (edgeHit clause)"
    init = re.search(r"\(method\s+\(init\)", text[m.start():])
    if not init:
        return text, 0, None
    sup = re.search(r"\n(\s*)\(super init:\)", text[m.start() + init.start():])
    if not sup:
        return text, 0, None
    at = m.start() + init.start() + sup.end()
    indent = sup.group(1)
    ins = ("\n%s; [softlock-guard] close this exit until the player can survive past it\n"
           "%s(if (not %s)\n%s\t(global2 %s: 0)\n%s)" % (indent, indent, cond, indent, direction, indent))
    return text[:at] + ins + text[at:], 1, direction


def apply_guards(dest, specs, titles_by_num, nums, s_drops=lambda it: set()):
    """Place each EDGE guard at its CONTROLLABLE TRIGGER.

    A frontier `newRoom: N` usually sits at the last state of a changeState cutscene -- an
    UNCONTROLLABLE transition that has already consumed resources and started animating. Guarding
    it there hangs the game. `trigger.find_trigger` walks back to the player-facing handler that
    STARTS the cutscene and we guard that instead, so the refusal happens before anything runs.
    `wrap_trigger_in_source` wraps the whole enclosing cond-clause, not just the changeState, so
    side-effecting siblings (score, sounds, flag sets) cannot fire ahead of the refusal."""
    out_unplaced = []
    by_title = {}
    for sp in specs:
        if sp["site"] != "edge" or sp["refused"] or not sp.get("condition"):
            continue
        by_title.setdefault(titles_by_num.get(sp["from_room"]), []).append(sp)

    # A prohibition's droppability frontier may be UNCONTROLLABLE. rm131 -> rm138 is: the ship
    # sequence is `setScript:` at room init and runs itself to `newRoom: 138`, so there is no
    # player action to refuse and refusing an automatic cutscene would hang the game. Fall back to
    # the nearest EARLIER commit that is both controllable and still lets the player comply --
    # rm38 -> rm131, whose source room is itself a drop site for the dip.
    deferred = []
    for title, group in list(by_title.items()):
        keep = []
        for sp in group:
            if sp.get("forbid") and title:
                forms = read_file(os.path.join(dest, "src", title + ".sc"))
                if find_trigger(forms, sp["to_room"])["kind"] not in ("trigger", "direct"):
                    deferred.append(sp)
                    continue
            keep.append(sp)
        by_title[title] = keep
    for sp in deferred:
        item = sp["forbid"][0]
        host = None
        for cand in specs:
            if (cand["site"] == "edge" and not cand.get("forbid") and not cand["refused"]
                    and cand["from_room"] in s_drops(item)):
                host = cand
                break
        if host is None:
            out_unplaced.append({**sp, "applied": False,
                                 "why": "no controllable commit where the item is still droppable"})
            continue
        host["condition"] = "(and %s %s)" % (host["condition"], sp["condition"])
        host.setdefault("merged", []).append(sp["condition"])

    out = out_unplaced
    for title, group in sorted((k, v) for k, v in by_title.items() if k):
        path = os.path.join(dest, "src", title + ".sc")
        for sp in group:
            try:
                forms = read_file(path)
            except Exception as e:
                out.append({**sp, "applied": False, "why": "parse failed: %s" % e})
                continue
            placement = find_trigger(forms, sp["to_room"])
            if placement["kind"] not in ("trigger", "direct"):
                # fall back to the room-property exit idiom before giving up
                text = open(path, errors="replace").read()
                new_text, n, direction = guard_edge_exit(
                    text, title, sp["to_room"], to_source_syntax(sp["condition"]))
                if n:
                    open(path, "w").write(new_text)
                    out.append({**sp, "applied": True, "title": title, "sites": n,
                                "placement": {"kind": "edge-exit", "instance": title,
                                              "trigger_method": "init", "trigger_state": direction}})
                    continue
                out.append({**sp, "applied": False,
                            "why": "no controllable trigger (%s) and no room-property exit"
                                   % placement["kind"],
                            "placement": placement})
                continue
            text = open(path, errors="replace").read()
            new_text, n = wrap_trigger_in_source(
                text, placement, to_source_syntax(sp["condition"]), REFUSE)
            if n == 0:
                out.append({**sp, "applied": False, "why": "trigger found but no site rewritten",
                            "placement": placement})
                continue
            open(path, "w").write(new_text)
            out.append({**sp, "applied": True, "title": title, "sites": n,
                        "placement": placement})
    return out


def run(args, cwd):
    p = subprocess.run([SCICOMPILE] + args, cwd=cwd, capture_output=True, text=True, timeout=1800)
    return p.returncode, p.stdout + p.stderr


def compile_project(dest):
    """--sco (interfaces from source + game) then --all (compile everything)."""
    parent, name = os.path.dirname(dest) or ".", os.path.basename(dest)
    rc, out = run(["--sco", name], parent)
    sco = re.search(r"Generate SCO: (\d+) written", out)
    rc2, out2 = run(["--all", name], parent)
    allr = re.search(r"result: (\d+)/(\d+) scripts compiled", out2)
    failed = re.findall(r"^  (\S+)\s+line \d+: Error: (.*)$", out2, re.M)
    return {"sco_written": int(sco.group(1)) if sco else 0,
            "compiled": int(allr.group(1)) if allr else 0,
            "total": int(allr.group(2)) if allr else 0,
            "failures": failed}


def compile_one(dest, title, out_bin):
    """Compile a single script to its raw resource bytes (--all only writes .sco)."""
    parent, name = os.path.dirname(dest) or ".", os.path.basename(dest)
    rc, out = run([name, os.path.join(name, "src", title + ".sc"), out_bin], parent)
    return os.path.exists(out_bin), out


def emit_patches(dest, titles, nums, out_dir):
    """Compile each edited script and wrap it as a ScummVM loose patch `script.NNN`."""
    os.makedirs(out_dir, exist_ok=True)
    written = []
    for title in sorted(titles):
        num = nums[title]
        raw = os.path.join(dest, "%s.bin" % title)
        ok, log = compile_one(dest, title, raw)
        if not ok:
            written.append({"title": title, "script": num, "ok": False,
                            "error": log.strip().splitlines()[-1] if log.strip() else "no output"})
            continue
        data = open(raw, "rb").read()
        dst = os.path.join(out_dir, "script.%03d" % num)
        with open(dst, "wb") as f:
            f.write(bytes([0x80 | RES_TYPE_SCRIPT, 0x00]))
            f.write(data)
        written.append({"title": title, "script": num, "ok": True,
                        "path": dst, "bytes": len(data) + 2})
    return written


def main():
    dest = os.path.join(_ROOT, "build", "patch_project")
    out_dir = os.path.join(_ROOT, "build", "patch")

    print("loading analysis...")
    s = M.load()
    sinks = G.sink_remedies(s)

    print("assembling project from %s" % config.ACTIVE.src_dir)
    nums = assemble(dest)
    titles_by_num = {n: t for t, n in nums.items()}

    print("\napplying %d sink remedies:" % len(sinks))
    edits = apply_sink_remedies(dest, sinks, titles_by_num)
    for e in edits:
        mark = "ok " if e["applied"] else "SKIP"
        where = e.get("title", "script%s" % e["script"])
        print("  [%s] %-10s %s" % (mark, where, e["why"]))
    specs = G.guard_specs(s)
    print("\napplying %d guard specs:" % sum(1 for x in specs if x["site"] == "edge"))
    gedits = apply_guards(dest, specs, titles_by_num, nums,
                          s_drops=lambda it: s.drops.get(it, set()))
    for e in gedits:
        mark = "ok " if e["applied"] else "SKIP"
        pl = e.get("placement", {})
        how = ("%s @ %s.%s state %s" % (pl.get("kind"), pl.get("instance"),
                                        pl.get("trigger_method", pl.get("method")),
                                        pl.get("trigger_state", "-"))) if e["applied"] else e["why"]
        print("  [%s] rm%s->rm%s  %s" % (mark, e["from_room"], e["to_room"], how))
        if e["applied"]:
            print("        %s" % to_source_syntax(e["condition"]))
    touched = sorted({e["title"] for e in edits + gedits if e["applied"]})

    print("\ncompiling...")
    r = compile_project(dest)
    print("  .sco written: %d;  compiled: %d/%d" % (r["sco_written"], r["compiled"], r["total"]))
    for t, err in r["failures"]:
        print("  FAILED %-10s %s" % (t, err))
    unpatchable = [t for t, _ in r["failures"] if t in touched]
    if unpatchable:
        print("\nREFUSING to emit: an edited script failed to compile: %s" % unpatchable)
        return 1

    print("\nemitting loose patch files for %d edited scripts:" % len(touched))
    for w in emit_patches(dest, touched, nums, out_dir):
        if w["ok"]:
            print("  script.%03d  %-10s %d bytes" % (w["script"], w["title"], w["bytes"]))
        else:
            print("  FAILED script.%03d %s: %s" % (w["script"], w["title"], w["error"]))
    print("\npatch files in: %s" % out_dir)
    print("copy them into a COPY of the game folder; delete them to revert.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
