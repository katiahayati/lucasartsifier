"""Emit the SAME synthetic n=40 shape as SMV and let nuXmv's engine do reachability.

This removes MY hand-written BDD driver from the equation: nuXmv is a mature, tuned
symbolic model checker. Same synthetic Model as bdd_spike (correct-by-construction,
validated shape), same one-action-per-step semantics, encoded with an `action` input
that nondeterministically selects which transition fires each step.

We time nuXmv's `compute_reachable` (forward symbolic reachability) and read the
reachable-state count. Reachable ROOMS aren't printed by nuXmv directly, so we also add
an INVARSPEC on the goal so a reachable goal shows up as a found counterexample.
"""
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(__file__))
from bdd_spike import Model, LSL2_SHAPE  # noqa: E402

NUXMV = open(os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp",
                          "nuxmv_path.txt")).read().strip()
NUXMV = os.path.abspath(os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp",
                                     "nuXmv-2.0.0-Linux", "bin", "nuXmv"))
TMP = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp")


def guard_expr(g):
    parts = []
    for atom in g:
        parts.append(f"reg{atom[1]} = {atom[2]}" if atom[0] == "reg" else f"item{atom[1]}")
    return " & ".join(parts)


def emit_smv(m, path):
    nreg = len(m.reg_values)
    edges = m.edges
    writes = m.writes
    pickups = m.pickups
    # action ids: edges [0..), writes, pickups
    n_act = len(edges) + len(writes) + len(pickups)
    L = []
    L.append("MODULE main")
    L.append("IVAR")
    L.append(f"  action : 0 .. {n_act - 1};")
    L.append("VAR")
    L.append(f"  room : 0 .. {m.nrooms - 1};")
    for i in range(m.nitems):
        L.append(f"  item{i} : boolean;")
    for r in range(nreg):
        L.append(f"  reg{r} : 0 .. {max(1, m.reg_values[r] - 1)};")
    L.append("ASSIGN")
    L.append("  init(room) := 0;")
    for i in range(m.nitems):
        L.append(f"  init(item{i}) := FALSE;")
    for r in range(nreg):
        L.append(f"  init(reg{r}) := 0;")

    # next(room): movement edges
    L.append("  next(room) := case")
    for k, (a, b, g) in enumerate(edges):
        cond = f"action = {k} & room = {a}"
        gx = guard_expr(g)
        if gx:
            cond += " & " + gx
        L.append(f"    {cond} : {b};")
    L.append("    TRUE : room;")
    L.append("  esac;")

    # next(regR): writes to R
    for r in range(nreg):
        L.append(f"  next(reg{r}) := case")
        for j, (rr, reg, val, g) in enumerate(writes):
            if reg != r:
                continue
            aid = len(edges) + j
            cond = f"action = {aid} & room = {rr}"
            gx = guard_expr(g)
            if gx:
                cond += " & " + gx
            L.append(f"    {cond} : {val};")
        L.append(f"    TRUE : reg{r};")
        L.append("  esac;")

    # next(itemI): pickups of I
    for it in range(m.nitems):
        L.append(f"  next(item{it}) := case")
        for j, (rr, i2, g) in enumerate(pickups):
            if i2 != it:
                continue
            aid = len(edges) + len(writes) + j
            cond = f"action = {aid} & room = {rr}"
            gx = guard_expr(g)
            if gx:
                cond += " & " + gx
            L.append(f"    {cond} : TRUE;")
        L.append(f"    TRUE : item{it};")
        L.append("  esac;")

    L.append(f"INVARSPEC room != {m.goal};")   # reachable goal -> spec violated -> counterexample
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")


def run(gate_frac, timeout_s=600):
    S = LSL2_SHAPE
    m = Model(S["nrooms"], S["nitems"], S["reg_values"], S["nedges"], S["nwrites"],
              gate_frac=gate_frac, seed=1)
    smv = os.path.join(TMP, f"model_g{gate_frac}.smv")
    emit_smv(m, smv)
    cmds = (f"read_model -i {smv}\ngo\ncompute_reachable\n"
            f"print_reachable_states\ncheck_invar\nquit\n")
    t = time.time()
    try:
        p = subprocess.run([NUXMV, "-int"], input=cmds, capture_output=True,
                           text=True, timeout=timeout_s)
        dt = time.time() - t
        out = p.stdout + p.stderr
    except subprocess.TimeoutExpired:
        return gate_frac, None, f">{timeout_s}s TIMEOUT", ""
    # parse "reachable states: ..." and invar result
    reach = "?"
    for line in out.splitlines():
        low = line.lower()
        if "reachable states" in low or "diameter" in low or "is true" in low or "is false" in low:
            reach += " | " + line.strip()
    return gate_frac, dt, reach, out


def main():
    print(f"nuXmv: {NUXMV}\n")
    for gf in (0.0, 0.5, 1.0):
        gate_frac, dt, info, out = run(gf)
        if dt is None:
            print(f"gate_frac={gf}: {info}", flush=True)
        else:
            print(f"gate_frac={gf}: time={dt:.2f}s  {info}", flush=True)
            # show the key lines
            for line in out.splitlines():
                if any(k in line.lower() for k in
                       ("reachable states", "diameter", "specification", "is false", "is true")):
                    print("      " + line.strip())
        print(flush=True)


if __name__ == "__main__":
    main()
