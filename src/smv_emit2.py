"""Emit the new extractor's transition system (extract2.TS) as SMV for nuXmv.

Clean re-implementation decoupled from the old FixModel: consumes TS (rooms, edges,
acqs, items) + guard trees. This first cut is the BASE model (items bind; globals/opaque
atoms are permissive nondeterministic inputs, satisfiable in both polarities -- the
player can do them). Registers/machine-state/deaths come next.
"""
from __future__ import annotations

import os
import subprocess

from model import GAnd, GOr, GNot, Pred


class Emitter:
    def __init__(self, ts, start, goals, pin=()):
        self.ts = ts
        self.start = start
        self.goals = sorted(goals)
        self.rooms = sorted(ts.rooms)
        self.items = sorted(ts.items)
        self.pin = set(pin)          # items forced permanently FALSE (requirements probe)
        self.n_opaque = 0

    def _permissive(self):
        k = self.n_opaque
        self.n_opaque += 1
        return f"opq{k}"

    def expr(self, g):
        if g is None:
            return "TRUE"
        if isinstance(g, GAnd):
            ks = [self.expr(k) for k in g.kids]
            if "FALSE" in ks:
                return "FALSE"
            ks = [k for k in ks if k != "TRUE"]
            return "(" + " & ".join(ks) + ")" if ks else "TRUE"
        if isinstance(g, GOr):
            ks = [self.expr(k) for k in g.kids]
            if "TRUE" in ks:
                return "TRUE"
            ks = [k for k in ks if k != "FALSE"]
            return "(" + " | ".join(ks) + ")" if ks else "FALSE"
        if isinstance(g, GNot):
            inner = self.expr(g.kid)
            if inner == "TRUE":
                return "FALSE"
            if inner == "FALSE":
                return "TRUE"
            return f"!({inner})"
        if isinstance(g, Pred):
            if g.kind == "OWN":
                return f"item{g.var}"
            return self._permissive()      # CMP/SAID/POS/OPAQUE: permissive in base
        return "TRUE"

    def emit(self):
        moves = [(e.src, e.dst, self.expr(e.guard)) for e in self.ts.edges]
        acqs = [(a.room, a.item, self.expr(a.guard)) for a in self.ts.acqs]
        n_act = len(moves) + len(acqs)

        L = ["MODULE main", "IVAR", f"  action : 0 .. {max(0, n_act - 1)};"]
        for k in range(self.n_opaque):
            L.append(f"  opq{k} : boolean;")
        L.append("VAR")
        L.append("  room : {" + ", ".join(str(r) for r in self.rooms) + "};")
        for it in self.items:
            L.append(f"  item{it} : boolean;")

        L.append("ASSIGN")
        L.append(f"  init(room) := {self.start};")
        for it in self.items:
            L.append(f"  init(item{it}) := FALSE;")

        L.append("  next(room) := case")
        for k, (a, b, ge) in enumerate(moves):
            cond = f"action = {k} & room = {a}"
            if ge != "TRUE":
                cond += " & " + ge
            L.append(f"    {cond} : {b};")
        L.append("    TRUE : room;")
        L.append("  esac;")

        base = len(moves)
        by_item = {}
        for j, (room, it, ge) in enumerate(acqs):
            by_item.setdefault(it, []).append((base + j, room, ge))
        for it in self.items:
            if it in self.pin:
                L.append(f"  next(item{it}) := FALSE;")   # unobtainable (requirements probe)
                continue
            L.append(f"  next(item{it}) := case")
            for aid, room, ge in by_item.get(it, []):
                cond = f"action = {aid} & room = {room}"
                if ge != "TRUE":
                    cond += " & " + ge
                L.append(f"    {cond} : TRUE;")
            L.append(f"    TRUE : item{it};")
            L.append("  esac;")

        goals = " | ".join(f"room = {r}" for r in self.goals)
        L.append(f"INVARSPEC !({goals});")
        return "\n".join(L) + "\n"


def _find_nuxmv():
    for c in (os.environ.get("NUXMV"),
              os.path.join(os.environ.get("CLAUDE_JOB_DIR", ""), "tmp",
                           "nuXmv-2.0.0-Linux", "bin", "nuXmv")):
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("nuXmv not found; set $NUXMV")


def winnable(ts, start, goals, pin_items_off=(), timeout=600):
    smv = Emitter(ts, start, goals, pin=pin_items_off).emit()
    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "ts.smv")
    with open(tmp, "w") as f:
        f.write(smv)
    cmds = f"read_model -i {tmp}\ngo_msat\ncheck_invar_ic3\nquit\n"
    p = subprocess.run([_find_nuxmv(), "-int"], input=cmds, capture_output=True,
                       text=True, timeout=timeout)
    out = p.stdout + p.stderr
    for line in out.splitlines():
        low = line.lower()
        if "is false" in low:
            return True
        if "is true" in low:
            return False
    raise RuntimeError("no verdict:\n" + out[-1500:])
