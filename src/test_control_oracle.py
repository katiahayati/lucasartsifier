"""Fast (no-nuXmv) tests for the control-map oracle and its wiring into OpEmitter.

Covers what was added for the rm82 door-Prop gate: the pure helpers, the real-LSL2
derivation (find_gates -> exactly the rm82 elevator gate), the VIEW-715 footprint facts,
and that OpEmitter._apply_control_gates actually gates the machine EXIT->83 on the derived
door-open latch. All structural -- the slow winnability confirmation is a separate run.

Run: python3 test_control_oracle.py   (skips the real-LSL2 checks if the IR/resources
are absent).
"""
import os
import sys

sys.path.insert(0, ".")
import ir as I
import config
import control_oracle as CO
import sci_gfx

PASS, FAIL = [], []
def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"  -- {detail}" if detail and not cond else ""))

_IR = None
def real_ir():
    global _IR
    if _IR is None:
        p = config.ACTIVE.ir_path
        _IR = I.load_ir(p) if os.path.exists(p) else False
    return _IR

def have_resources():
    return bool(config.LSL2.resource_dir) and os.path.isdir(config.LSL2.resource_dir)


# ---- Part 1: pure helpers (no AST) --------------------------------------
def test_pure():
    print("Part 1: pure helpers")
    check("_mask_to_color: $0004 -> color 2", CO._mask_to_color(4) == 2)
    check("_mask_to_color: $0008 -> color 3", CO._mask_to_color(8) == 3)
    check("_mask_to_color: $2000 -> color 13", CO._mask_to_color(0x2000) == 13)
    check("_mask_to_color: non-power-of-2 -> None", CO._mask_to_color(6) is None)
    # nearest walkable on a tiny synthetic control plane: block a cross, seed inside it
    W, H = sci_gfx.W, sci_gfx.H
    con = bytearray(W * H)                       # all control-0 (walkable)
    blocked = {15}
    for x in range(W):                           # a wall row at y=100 (control-15)
        con[100 * W + x] = 15
    # a point ON the wall snaps to a neighbor off it
    nx, ny = CO._nearest_walkable(con, blocked, 50, 100)
    check("_nearest_walkable snaps off a blocked pixel", con[ny * W + nx] not in blocked, f"({nx},{ny})")
    # a point off-grid (y beyond H) clamps then finds walkable
    r = CO._nearest_walkable(con, blocked, 50, H + 40)
    check("_nearest_walkable clamps off-grid y", r is not None and 0 <= r[1] < H, str(r))


# ---- Part 2: real-LSL2 AST helpers (rm82) -------------------------------
def test_ast_helpers():
    print("Part 2: real-LSL2 AST helpers (rm82)")
    ir = real_ir()
    if not ir:
        print("  [SKIP] LSL2 IR not present"); return
    s82 = ir.script(82)
    # the opener state's persistent write is the derived latch (causedEruption = local 3)
    check("_state_latch(rm82Script, 16) = causedEruption L3:=1",
          CO._state_latch(s82, "rm82Script", 16) == ("L", 3, 1),
          str(CO._state_latch(s82, "rm82Script", 16)))
    # onControl $0004 -> changeState -> ... -> newRoom 83
    check("_gated_room(rm82, $0004) = 83", CO._gated_room(s82, 4) == 83, str(CO._gated_room(s82, 4)))
    # solid-Prop detection from AST flags: aDoor solid, steam Props not (isExtra), bottle not (ignoreActors)
    rm = CO._room_object(s82)
    props = CO._props_in(rm.methods["init"])
    door = [p for p in props if p["view"] == 715 and p["loop"] == 0]
    steam = [p for p in props if p["view"] == 715 and p["loop"] in (1, 2, 3)]
    check("aDoor (view715 loop0) detected as SOLID", door and door[0]["solid"], str(door))
    check("steam Props (isExtra) detected as NON-solid", steam and not any(p["solid"] for p in steam),
          str([p["solid"] for p in steam]))


# ---- Part 3: entry seed is DERIVED (fix #1) -----------------------------
def test_entry_seed():
    print("Part 3: derived entry seed (generality fix #1)")
    ir = real_ir()
    if not ir or not have_resources():
        print("  [SKIP] IR/resources not present"); return
    game = CO.Sci0Game(config.LSL2.resource_dir)
    s82 = ir.script(82); rm = CO._room_object(s82); init = rm.methods["init"]
    con = sci_gfx.render_control(game, 82)
    blocked = CO._walkable_grid(con, CO._ego_illegal(init))
    seed = CO._entry_seed(rm, init, con, blocked)
    check("rm82 entry seed is non-empty", len(seed) > 0, str(len(seed)))
    # it must be derived, not the last-resort floor band (which is y>=160 only):
    ys = [y for _, y in seed]
    check("rm82 entry seed is derived (extends above y=160, not just the fallback band)",
          min(ys) < 160, f"y-range [{min(ys)},{max(ys)}]")


# ---- Part 4: full derivation + VIEW footprints --------------------------
def test_derivation():
    print("Part 4: full oracle derivation (rm82 elevator gate)")
    ir = real_ir()
    if not ir or not have_resources():
        print("  [SKIP] IR/resources not present"); return
    gates = CO.find_gates(config.LSL2, ir)
    prop = [g for g in gates if g.get("kind") == "prop"]
    check("sweep derives exactly one prop-gate", len(prop) == 1, str([(g["room"], g["gated_room"]) for g in gates]))
    g = prop[0] if prop else {}
    check("prop-gate is rm82 onControl $0004 -> rm83", g.get("room") == 82 and g.get("control_bit") == 4
          and g.get("gated_room") == 83, str(g))
    check("prop-gate opener = rm82Script state 16", g.get("opener_states") == [("rm82Script", 16)])
    check("prop-gate latch = causedEruption L3==1", g.get("opener_latch") == ("L", 3, 1))
    # VIEW 715 door footprints: closed covers the elevator control-2, open does not
    game = CO.Sci0Game(config.LSL2.resource_dir)
    con = sci_gfx.render_control(game, 82)
    elev = {(i % sci_gfx.W, i // sci_gfx.W) for i in range(sci_gfx.W * sci_gfx.H) if con[i] == 2}
    door = sci_gfx.decode_view(game, 715)[0]["cels"]
    closed = door[0].footprint(75, 146); opened = door[-1].footprint(75, 146)
    check("closed door cel covers ALL 57 elevator-floor px", len(elev & closed) == len(elev) == 57,
          f"{len(elev & closed)}/{len(elev)}")
    check("open door cel covers 0 elevator-floor px", len(elev & opened) == 0, str(len(elev & opened)))


# ---- Part 5: OpEmitter applies the gate (structural, no nuXmv) -----------
def test_emitter_gate():
    print("Part 5: OpEmitter._apply_control_gates wires the gate")
    ir = real_ir()
    if not ir or not have_resources():
        print("  [SKIP] IR/resources not present"); return
    import smv_emit3 as E
    em = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)
    check("em.control_gates has the rm82 gate",
          any(g["room"] == 82 and g["gated_room"] == 83 for g in getattr(em, "control_gates", [])))
    check("latch local (82,'L',3) is now TRACKED in loc_dom", (82, "L", 3) in em.loc_dom)
    # state 21's EXIT-83 transitions now carry the latch guard
    s21 = None
    for info in em.machines:
        if info["room"] == 82 and info["inst"] == "rm82Script":
            s21 = info["states"][21]
    latch_guard = ("CTR", ("L", 3), "==", 1)
    check("rm82Script state 21 (EXIT 83) guarded on the latch",
          s21 is not None and all(latch_guard in list(p[0]) for p in s21 if p[4] == ("EXIT", 83)),
          str([p[0] for p in (s21 or [])]))
    # the emitted SMV delivers room:=83 only under the latch
    smv, _ = em.emit()
    d83 = [l.strip() for l in smv.splitlines() if l.strip().endswith(": 83;")]
    check("emitted room:=83 delivery is gated on c_82_L_3 = 1",
          d83 and all("c_82_L_3 = 1" in l for l in d83), str(d83))


# ---- Part 6: rm47 crossing-gate (disguise) ------------------------------
def test_crossing_gate():
    print("Part 6: rm47 crossing-gate (disguise)")
    ir = real_ir()
    if not ir or not have_resources():
        print("  [SKIP] IR/resources not present"); return
    rect = (86, 2, 333, 140)
    # the geometric proof: east (win-ward) forces the rect; west (retreat) does not
    check("crossing_forces_rect rm47 east = True", CO.crossing_forces_rect(config.LSL2, ir, 47, rect, "east"))
    check("crossing_forces_rect rm47 west = False", not CO.crossing_forces_rect(config.LSL2, ir, 47, rect, "west"))
    # the derived gate: only the east exit (47->48), keyed on henchStatus (L2) != 0
    cg = CO.crossing_gates(config.LSL2, ir, 47)
    east = [g for g in cg if g["gated_room"] == 48]
    check("crossing_gates(47) gates east exit 47->48", len(east) == 1, str([(g["exit_dir"], g["gated_room"]) for g in cg]))
    check("... does NOT gate the retreat exit 47->42", not any(g["gated_room"] == 42 for g in cg))
    check("... does NOT emit a phantom south->0 exit", not any(g["gated_room"] == 0 for g in cg))
    if east:
        check("crossing gate keyed on henchStatus L2, bad=0",
              east[0]["safe_local"] == ("L", 2) and east[0]["bad_value"] == 0, str(east[0]))
    # full sweep has BOTH gate kinds
    kinds = {(g["kind"], g["room"], g["gated_room"]) for g in CO.find_gates(config.LSL2, ir)}
    check("full sweep = rm47 crossing + rm82 prop",
          ("crossing", 47, 48) in kinds and ("prop", 82, 83) in kinds, str(kinds))
    # emitter: 47->48 carries the safe guard, and henchStatus can be != 0 (satisfiable -> winnable)
    # the gate is the derived DISGUISE CONDITION (gBodyWaxed & egoView==151), not henchStatus,
    # so it makes the bikini items required (egoView==151 is item-gated) and can't be met by arming
    east = [g for g in cg if g["gated_room"] == 48]
    check("crossing gate carries a disguise condition (safe_guard)", east and east[0].get("safe_guard") is not None)
    check("... safe_value is the disguise value 8", east and east[0].get("safe_value") == 8)
    import smv_emit3 as E
    em = E.OpEmitter(ir, config.LSL2, lambda gi, v: gi == 101 and v == 1001)
    e48 = [e for e in em.ts.edges if e.src == 47 and e.dst == 48]
    g48 = repr(e48[0].guard).replace(" ", "") if e48 else ""
    check("emitter gates 47->48 on the disguise condition (egoView==151)", "102==151" in g48, g48)


def run():
    print("=== test_control_oracle ===")
    test_pure()
    test_ast_helpers()
    test_entry_seed()
    test_derivation()
    test_emitter_gate()
    test_crossing_gate()
    print(f"\n{len(PASS)} passed, {len(FAIL)} failed" + (f"  FAILURES: {FAIL}" if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
