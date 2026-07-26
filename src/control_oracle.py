"""Control-map gate oracle (engine-general).

Some softlock gates are NOT in the script AST or as a script guard -- they live in
the engine's use of the game RESOURCES: which pixels the ego may stand on (the PIC
control plane) and which pixels a solid Prop covers (its VIEW cel). This module
renders those resources and derives edge gates the rest of the engine can consume:

  (A) crossing gate (rm47):  a room's win-ward exit cannot be reached without
      passing through a doit death/hazard rect -> taking the exit forces the rect
      (so the exit inherits the rect's safe-branch requirement, e.g. the disguise).

  (B) prop gate (rm82): an `onControl` trigger that delivers a room transition sits
      on a control region a SOLID Prop covers in its initial cel; the Prop opens
      (cel change) only in a machine state -> the trigger is gated on that state.

Everything is read, nothing declared: solidity comes from the Prop's own AST flags
(`isExtra`/`ignoreActors`), the cel-per-state from the lifted machine's `setCycle`,
the footprint from the VIEW, the walkable region from the PIC control plane.
"""
from __future__ import annotations

import config

import os
from collections import deque

import ir as I
from sci_resource import Sci0Game
import sci_gfx
from sci_gfx import W, H
from guard_ast import GAnd, GOr, GNot
from extract import atom

# control bit N ($ mask 1<<N) blocks the ego iff N is in its illegalBits.
# Actor default illegalBits = $8000 (control color 15). Rooms may add more via
# observeControl; we take the default plus any observeControl:<mask> on gEgo.
_DEFAULT_ILLEGAL = 0x8000


# ----------------------------------------------------------------- AST facts
def _int_prop(obj, name):
    v = obj.props.get(name)
    return v if isinstance(v, int) else None

def _room_object(script):
    """The Rm instance: the object carrying a `picture` property (and exits)."""
    for o in script.objects:
        if not o.is_class and "picture" in o.props:
            return o
    return None

def _new_class(node):
    """If node is `(<Class> new:)`, return the class name, else None."""
    if I.t(node) != "Send":
        return None
    recv, msgs = I.send_pairs(node)
    if any(sel == "new" for sel, _ in msgs) and I.t(recv) in ("Object", "Ident", "Class"):
        return recv.get("name")
    return None

def _props_in(method_ast):
    """Sprites created in a method: [{name?, view, loop, posn, solid}]. A sprite is a
    Send whose receiver assigns `(<Class> new:)` (Prop/Act/View); solid = the ego can
    collide with it = it sets neither isExtra nor ignoreActors."""
    out = []
    for send in I.sends(method_ast):
        recv, msgs = I.send_pairs(send)
        cls = None
        local_index = None
        if I.t(recv) == "Assignment":
            dest, source = I.kids(recv)[0], I.kids(recv)[1]
            cls = _new_class(source)
            if I.is_local_or_temp(dest):
                local_index = (dest["vtype"][0], dest["index"])
        elif I.t(recv) == "Send":
            cls = _new_class(recv)
        if cls not in ("Prop", "Act", "Actor", "View"):
            continue
        sel = {s: p for s, p in msgs}
        view = loop = None
        posn = None
        extra = ignore = False
        for s, p in msgs:
            if s == "view" and p: view = I.as_int(p[0])
            elif s in ("setLoop", "loop") and p: loop = I.as_int(p[0])
            elif s == "posn" and len(p) >= 2: posn = (I.as_int(p[0]), I.as_int(p[1]))
            elif s == "isExtra": extra = True
            elif s == "ignoreActors": ignore = True
            elif s == "illegalBits" and p and I.as_int(p[0]) == 0: ignore = True
        out.append({"local": local_index, "cls": cls, "view": view, "loop": loop or 0,
                    "posn": posn, "solid": (not extra and not ignore)})
    return out

def _ego_illegal(method_ast):
    bits = _DEFAULT_ILLEGAL
    for send in I.sends(method_ast):
        recv, msgs = I.send_pairs(send)
        if I.is_global(recv, 0):   # gEgo
            for s, p in msgs:
                if s == "observeControl" and p:
                    m = I.as_int(p[0])
                    if m: bits |= m
    return bits

def _oncontrol_bits(node):
    """control-color bits tested by `(& (gEgo onControl:) <mask>)` inside `node`."""
    bits = set()
    for send in I.sends(node):
        recv, msgs = I.send_pairs(send)
        if I.is_global(recv, 0) and any(s == "onControl" for s, _ in msgs):
            pass  # the mask is on the enclosing (& ...), handled by caller scan
    # simpler: scan BinAnd nodes whose one side is (gEgo onControl:) and other an int
    for n in I.walk(node):
        if I.t(n) not in ("And", "BinAnd", "BitAnd"):
            continue
        ks = I.kids(n)
        if len(ks) != 2:
            continue
        a, b = ks
        av = _is_ego_oncontrol(a)
        bv = _is_ego_oncontrol(b)
        if av and I.as_int(b) is not None:
            bits.add(I.as_int(b))
        elif bv and I.as_int(a) is not None:
            bits.add(I.as_int(a))
    return bits

def _is_ego_oncontrol(n):
    if I.t(n) != "Send":
        return False
    recv, msgs = I.send_pairs(n)
    return I.is_global(recv, 0) and any(s == "onControl" for s, _ in msgs)


def _changestate_target(body):
    for send in I.sends(body):
        _r, msgs = I.send_pairs(send)
        for sel, ps in msgs:
            if sel == "changeState" and ps:
                return I.as_int(ps[0])
    return None

def _newroom_in(body):
    for send in I.sends(body):
        _r, msgs = I.send_pairs(send)
        for sel, ps in msgs:
            if sel in ("newRoom", "entranceTo") and ps:
                r = I.as_int(ps[0])
                if r is not None:
                    return r
    return None

def _gated_room(script, mask):
    """Trace the `onControl <mask>` doit branch to the room it delivers: find its
    `changeState T`, then follow the changeState gauntlet from T (advancing) to a
    `newRoom`. For rm82: onControl $0004 -> changeState 19 -> ...20...21 newRoom 83."""
    for o in script.objects:
        doit = o.methods.get("doit")
        if not doit:
            continue
        for n in I.walk(doit):
            if I.t(n) not in ("Case", "If"):
                continue
            ks = I.kids(n)
            if len(ks) < 2:
                continue
            test, body = ks[0], ks[1]
            if not any(I.t(a) in ("And", "BinAnd", "BitAnd") and len(I.kids(a)) == 2
                       and ((_is_ego_oncontrol(I.kids(a)[0]) and I.as_int(I.kids(a)[1]) == mask)
                            or (_is_ego_oncontrol(I.kids(a)[1]) and I.as_int(I.kids(a)[0]) == mask))
                       for a in I.walk(test)):
                continue
            T = _changestate_target(body)
            if T is None:
                continue
            for inst_o in script.objects:
                cs = inst_o.methods.get("changeState")
                if not cs:
                    continue
                cases = dict(_cases(cs))
                if T not in cases:
                    continue
                st, seen = T, set()
                while st in cases and st not in seen:
                    seen.add(st)
                    nr = _newroom_in(cases[st])
                    if nr is not None:
                        return nr
                    st += 1
    return None

def _setcycle_states(script):
    """Which locals get `setCycle:` in which changeState Case -> {local_index: [state]}.
    A Prop that receives setCycle in a state is (potentially) opened there."""
    out = {}
    for o in script.objects:
        for mname, ast in o.methods.items():
            if mname != "changeState":
                continue
            for case in _cases(ast):
                st, body = case
                for send in I.sends(body):
                    recv, msgs = I.send_pairs(send)
                    if I.is_local_or_temp(recv) and any(s == "setCycle" for s, _ in msgs):
                        key = (recv["vtype"][0], recv["index"])
                        out.setdefault(key, []).append((o.name, st))
    return out

def _cases(changestate_ast):
    """Yield (state_int, body_node) for each Case in a changeState switch."""
    for n in I.walk(changestate_ast):
        if I.t(n) != "Switch":
            continue
        for k in I.kids(n)[1:]:
            if I.t(k) == "Case":
                test, body = I.kids(k)[0], I.kids(k)[1]
                sv = I.as_int(test)
                if sv is not None:
                    yield sv, body


def _state_latch(script, inst, state):
    """The persistent write the given changeState Case makes: a `(= <local/global> <int>)`
    assignment. This is the derived 'the gate has opened' latch -- for rm82 state 16 that
    is `(= causedEruption 1)` (local #3). Returns (vtype_char, index, value) or None."""
    obj = script.by_name.get(inst)
    if obj is None or "changeState" not in obj.methods:
        return None
    for st, body in _cases(obj.methods["changeState"]):
        if st != state:
            continue
        for n in I.walk(body):
            if I.t(n) == "Assignment":
                dest, src = I.kids(n)[0], I.kids(n)[1]
                v = I.as_int(src)
                if v is not None and (I.is_global(dest) or I.is_local_or_temp(dest)):
                    vt = "G" if I.is_global(dest) else dest["vtype"][0]
                    return (vt, dest["index"], v)
    return None


# ----------------------------------------------------------------- geometry
def _walkable_grid(con, illegal_bits):
    blocked = {c for c in range(16) if (1 << c) & illegal_bits}
    return blocked

def _nearest_walkable(con, blocked, x, y):
    """Nearest walkable pixel to (x,y), clamped onto the grid first (ego is often placed
    off-screen and walks in). Spiral out until a control-walkable pixel is found."""
    x = min(max(x, 0), W - 1)
    y = min(max(y, 0), H - 1)
    if con[y * W + x] not in blocked:
        return (x, y)
    for r in range(1, max(W, H)):
        for dx in range(-r, r + 1):
            for dy in (-r, r):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and con[ny * W + nx] not in blocked:
                    return (nx, ny)
        for dy in range(-r + 1, r):
            for dx in (-r, r):
                nx, ny = x + dx, y + dy
                if 0 <= nx < W and 0 <= ny < H and con[ny * W + nx] not in blocked:
                    return (nx, ny)
    return None

def _entry_seed(rm, init_ast, con, blocked):
    """Where the ego can be standing on room entry -- the seed for the gate reachability.
    Derived, not assumed: (1) the explicit `(gEgo posn: x y)` in init (ego's placement),
    snapped to the nearest walkable pixel; (2) a band along each screen edge the room has
    an exit on, since you arrive from any edge you can leave by. Falls back to the floor
    band only if a room exposes neither."""
    seeds = set()
    if init_ast:
        for send in I.sends(init_ast):
            recv, msgs = I.send_pairs(send)
            if I.is_global(recv, 0):                      # gEgo
                for sel, ps in msgs:
                    if sel == "posn" and len(ps) >= 2:
                        x, y = I.as_int(ps[0]), I.as_int(ps[1])
                        if x is not None and y is not None:
                            w = _nearest_walkable(con, blocked, x, y)
                            if w:
                                seeds.add(w)
    horizon = _int_prop(rm, "horizon") or 0
    bands = {
        "east":  [(x, y) for x in range(W - 5, W) for y in range(H)],
        "west":  [(x, y) for x in range(0, 5) for y in range(H)],
        "north": [(x, y) for x in range(W) for y in range(horizon, horizon + 5)],
        "south": [(x, y) for x in range(W) for y in range(H - 5, H)],
    }
    for d, band in bands.items():
        if _int_prop(rm, d) is not None:
            seeds.update((x, y) for (x, y) in band if con[y * W + x] not in blocked)
    if not seeds:                                         # last resort
        seeds.update((x, y) for x in range(W) for y in range(160, H)
                     if con[y * W + x] not in blocked)
    return list(seeds)


def _arrival_seed(rm, init_ast, con, blocked):
    """Ego's DEFAULT arrival point -- the `(gEgo posn: x y)` / `(gEgo x: .. y: ..)` in init,
    snapped to the nearest walkable pixel. Unlike `_entry_seed` this does NOT include the
    exit-edge bands, so it can be used to prove 'you can't reach exit E from where you start'
    without trivially seeding at E."""
    seeds = set()
    if not init_ast:
        return list(seeds)
    gx = gy = None
    for send in I.sends(init_ast):
        recv, msgs = I.send_pairs(send)
        if not I.is_global(recv, 0):
            continue
        for sel, ps in msgs:
            if sel == "posn" and len(ps) >= 2:
                x, y = I.as_int(ps[0]), I.as_int(ps[1])
                if x is not None and y is not None:
                    w = _nearest_walkable(con, blocked, x, y)
                    if w:
                        seeds.add(w)
            elif sel == "x" and ps:
                gx = I.as_int(ps[0])
            elif sel == "y" and ps:
                gy = I.as_int(ps[0])
    if gx is not None:
        w = _nearest_walkable(con, blocked, gx, gy if gy is not None else H // 2)
        if w:
            seeds.add(w)
    return list(seeds)

def _edge_pixels(exit_dir, con, blocked, horizon=0):
    """Walkable pixels along a screen edge (the region an `east`/`west`/`north`/`south`
    room exit is taken from)."""
    if exit_dir == "east":
        band = [(x, y) for x in range(W - 4, W) for y in range(H)]
    elif exit_dir == "west":
        band = [(x, y) for x in range(0, 4) for y in range(H)]
    elif exit_dir == "north":
        band = [(x, y) for x in range(W) for y in range(horizon, horizon + 4)]
    elif exit_dir == "south":
        band = [(x, y) for x in range(W) for y in range(H - 4, H)]
    else:
        return []
    return [(x, y) for (x, y) in band if con[y * W + x] not in blocked]

def crossing_forces_rect(cfg, ir, room, rect, exit_dir):
    """PROVE (over the PIC control plane) that the ego cannot reach the `exit_dir` screen
    edge from its arrival point without entering `rect`. If so, taking that exit forces the
    doit death-rect -> the exit inherits the rect's safe-branch requirement (rm47: the
    disguise). This is the derived replacement for the ASSUMED henchmen catch."""
    if not cfg.resource_dir or not os.path.isdir(cfg.resource_dir):
        return False
    script = ir.script(room)
    rm = _room_object(script) if script else None
    if rm is None or _int_prop(rm, "picture") is None:
        return False
    try:
        con = sci_gfx.render_control(Sci0Game(cfg.resource_dir), _int_prop(rm, "picture"))
    except (OSError, KeyError, ValueError):     # missing / corrupt resource, not code bugs
        return False
    init = rm.methods.get("init")
    blocked = _walkable_grid(con, _ego_illegal(init))
    starts = _arrival_seed(rm, init, con, blocked)
    targets = _edge_pixels(exit_dir, con, blocked, _int_prop(rm, "horizon") or 0)
    if not starts or not targets:
        return False
    a, b, c, d = rect
    reached = _bfs_reach(con, blocked, set(), starts, targets,
                         avoid=lambda x, y: a <= x <= c and b <= y <= d)
    return reached == 0


def _inrect_in(node):
    for send in I.sends(node):
        recv, msgs = I.send_pairs(send)
        if I.is_global(recv, 0):
            for sel, ps in msgs:
                if sel == "inRect" and len(ps) >= 4:
                    cs = [I.as_int(p) for p in ps[:4]]
                    if all(c is not None for c in cs):
                        return tuple(cs)
    return None

def _local_eq_in(node):
    """A `(== <local> <int>)` in the test -> (vtype_char, index, value). The disguise's
    distinguishing local (rm47: henchStatus==0)."""
    for n in I.walk(node):
        if I.t(n) != "Eq":
            continue
        ks = I.kids(n)
        if len(ks) != 2:
            continue
        a, b = ks
        if I.is_local_or_temp(a) and I.as_int(b) is not None:
            return (a["vtype"][0], a["index"], I.as_int(b))
        if I.is_local_or_temp(b) and I.as_int(a) is not None:
            return (b["vtype"][0], b["index"], I.as_int(a))
    return None

def _has_setscript(node):
    for send in I.sends(node):
        _r, msgs = I.send_pairs(send)
        if any(sel == "setScript" for sel, _ in msgs):
            return True
    return False

def _cond_to_guard(node):
    """Build a guard tree from a condition AST (And/Or/Not over atoms), reusing the
    extractor's atom() so item/global/position atoms come out the same as everywhere else."""
    t = I.t(node)
    if t == "And":
        return GAnd([_cond_to_guard(k) for k in I.kids(node)])
    if t == "Or":
        return GOr([_cond_to_guard(k) for k in I.kids(node)])
    if t == "Not":
        return GNot(_cond_to_guard(I.kids(node)[0]))
    return atom(node)

def _disguise_condition(script, local, bad):
    """The persistent condition that makes the room SAFE, read from the init write that sets
    the arm-local to a non-bad ('disguised') value: rm47 `(if (and gBodyWaxed (== egoView 151))
    (= henchStatus 8))`. Returns (guard_tree, safe_value). Gating the forced exit on this guard
    -- rather than on henchStatus!=bad -- is what makes the disguise ITEMS required (egoView==151
    is item-gated via the bikini chain), and it can't be satisfied by ARMING (henchStatus==1)."""
    rm = _room_object(script)
    init = rm.methods.get("init") if rm else None
    if init is None:
        return None, None
    for n in I.walk(init):
        if I.t(n) != "If":
            continue
        ks = I.kids(n)
        if len(ks) < 2:
            continue
        cond, then = ks[0], ks[1]
        for a in I.walk(then):
            if I.t(a) == "Assignment":
                dest, src = I.kids(a)[0], I.kids(a)[1]
                if I.is_local_or_temp(dest) and (dest["vtype"][0], dest["index"]) == local:
                    v = I.as_int(src)
                    if v is not None and v != bad:
                        return _cond_to_guard(cond), v
    return None, None

def crossing_gates(cfg, ir, room):
    """rm47-style crossing gate. A doit branch that (a) tests `(gEgo inRect: rect)`, (b) is
    guarded by a local `L==bad`, and (c) arms a reactive machine (`setScript`) is a positional
    death gate keyed on the disguise local L. If a win-ward room exit cannot be reached from
    the ego's arrival point without entering that rect (PROVEN over the control plane), the
    exit inherits the safe requirement L!=bad. This DERIVES (proves, per-exit) what a doit
    death-branch heuristic could only ASSUME, and does NOT over-gate the retreat exit."""
    script = ir.script(room)
    rm = _room_object(script) if script else None
    if rm is None or _int_prop(rm, "picture") is None:
        return []
    seen, gates = set(), []
    for o in script.objects:
        doit = o.methods.get("doit")
        if not doit:
            continue
        for n in I.walk(doit):
            if I.t(n) not in ("Case", "If"):
                continue
            ks = I.kids(n)
            if len(ks) < 2:
                continue
            test, body = ks[0], ks[1]
            rect = _inrect_in(test)
            loc = _local_eq_in(test)
            if rect is None or loc is None or not _has_setscript(body):
                continue
            for d in ("east", "west", "north", "south"):
                dst = _int_prop(rm, d)
                if not dst or (d, dst) in seen:      # 0/None = no exit in that direction
                    continue
                if crossing_forces_rect(cfg, ir, room, rect, d):
                    seen.add((d, dst))
                    safe_guard, safe_val = _disguise_condition(script, (loc[0], loc[1]), loc[2])
                    gates.append({
                        "kind": "crossing", "room": room, "exit_dir": d, "gated_room": dst,
                        "rect": rect, "safe_local": (loc[0], loc[1]), "bad_value": loc[2],
                        "safe_guard": safe_guard, "safe_value": safe_val,
                    })
    return gates


def _bfs_reach(con, blocked, extra_block, starts, targets, avoid=None):
    seen = bytearray(W * H)
    dq = deque()
    def ok(x, y):
        if not (0 <= x < W and 0 <= y < H):
            return False
        if con[y * W + x] in blocked:
            return False
        if (x, y) in extra_block:
            return False
        if avoid and avoid(x, y):
            return False
        return True
    for (x, y) in starts:
        if ok(x, y) and not seen[y * W + x]:
            seen[y * W + x] = 1; dq.append((x, y))
    while dq:
        x, y = dq.popleft()
        for nx, ny in ((x+1, y), (x-1, y), (x, y+1), (x, y-1)):
            if ok(nx, ny) and not seen[ny * W + nx]:
                seen[ny * W + nx] = 1; dq.append((nx, ny))
    return sum(1 for (tx, ty) in targets if seen[ty * W + tx])


# ----------------------------------------------------------------- gate B (prop)
def prop_gate(game, ir, room):
    """rm82-style: is an onControl trigger's control region covered by a solid Prop's
    initial cel, and freed only when that Prop opens? Returns a list of gate dicts."""
    script = ir.script(room)
    if script is None:
        return []
    rm = _room_object(script)
    if rm is None or _int_prop(rm, "picture") is None:
        return []
    pic = _int_prop(rm, "picture")
    try:
        con = sci_gfx.render_control(game, pic)
    except Exception:
        return []
    init = rm.methods.get("init")
    props = _props_in(init) if init else []
    solid = [p for p in props if p["solid"] and p["view"] is not None and p["posn"]]
    if not solid:
        return []
    # onControl bits tested anywhere in the room object's methods
    bits = set()
    for ast in rm.methods.values():
        bits |= _oncontrol_bits(ast)
    for o in script.objects:
        for ast in o.methods.values():
            bits |= _oncontrol_bits(ast)
    if not bits:
        return []
    illegal = _ego_illegal(init) if init else _DEFAULT_ILLEGAL
    blocked = _walkable_grid(con, illegal)
    setcyc = _setcycle_states(script)

    # ego "standing" seed: where the ego actually arrives (init posn + exit-edge bands),
    # derived per-room. The gate test is reachability, not raw coverage: a Prop gates a
    # trigger iff its CLOSED cel makes the trigger's control region unreachable from that
    # seed while its OPEN cel leaves it reachable. (Clipping a few edge pixels does not
    # disconnect a region.)
    starts = _entry_seed(rm, init, con, blocked)

    gates = []
    for p in solid:
        loops = sci_gfx.decode_view(game, p["view"])
        if p["loop"] >= len(loops):
            continue
        cels = loops[p["loop"]]["cels"]
        if not cels or any(c is None for c in p["posn"]):
            continue          # a Prop positioned at runtime has no static footprint to read
        closed_fp = cels[0].footprint(*p["posn"])
        open_fp = cels[-1].footprint(*p["posn"])
        for bit in bits:
            color = _mask_to_color(bit)
            if color is None:
                continue
            region = [(i % W, i // W) for i in range(W * H) if con[i] == color]
            if not region:
                continue
            r_closed = _bfs_reach(con, blocked, closed_fp, starts, region)
            r_open = _bfs_reach(con, blocked, open_fp, starts, region)
            # gated iff the closed Prop disconnects the region (all of it) but the open
            # Prop does not -- i.e. the ONLY way onto the trigger is with the Prop open.
            if r_closed == 0 and r_open > 0:
                opener = setcyc.get(p["local"]) or []
                latch = None
                for inst, st in opener:
                    latch = _state_latch(script, inst, st)
                    if latch:
                        break
                gates.append({
                    "room": room, "kind": "prop", "control_bit": bit,
                    "control_color": color, "prop_local": p["local"], "prop_view": p["view"],
                    "region_px": len(region), "reach_open": r_open,
                    "opener_states": opener, "opener_latch": latch,
                    "gated_room": _gated_room(script, bit),
                })
    return gates


def _mask_to_color(mask):
    """A control mask $XXXX is a single control-color bit; return the color index."""
    if mask and (mask & (mask - 1)) == 0:
        return mask.bit_length() - 1
    return None


def find_gates(cfg, ir, rooms=None):
    """All control-map gates: prop-gates (rm82 door) + crossing-gates (rm47 disguise).
    Narrow excepts (resource/parse only) so code bugs surface instead of silently
    dropping a room."""
    if not cfg.resource_dir or not os.path.isdir(cfg.resource_dir):
        return []
    game = Sci0Game(cfg.resource_dir)
    rooms = rooms or sorted(ir.scripts)
    out = []
    for r in rooms:
        try:
            out.extend(prop_gate(game, ir, r))
            out.extend(crossing_gates(cfg, ir, r))
        except (OSError, KeyError, ValueError, IndexError):   # bad/missing resource, not a code bug
            pass
    return out


if __name__ == "__main__":
    import config
    ir = I.load_ir(config.ACTIVE.ir_path)
    gates = find_gates(config.LSL2, ir)
    print(f"found {len(gates)} prop-gates:")
    for g in gates:
        print(f"  rm{g['room']}: onControl ${1<<(g['control_color']):04x} (color {g['control_color']}) "
              f"region {g['region_px']}px reachable ONLY with solid Prop view{g['prop_view']} {g['prop_local']} "
              f"open ({g['reach_open']}px open / 0 closed); opens at {g['opener_states']}")
