"""Obstacle-polygon gates -- positional blocking read from the SCRIPT, not from a resource.

`control_oracle` answers the same question ("can the ego get from where it arrives to the exit?")
from the PIC control plane. SCI1.1 rooms mostly do not use the control plane for this: they hand
the pathfinder POLYGONS instead --

    (method (init)
        (if (proc913_0 1)
            (global2 addObstacle: ((Polygon new:) type: 2 init: 149 148 102 148 ... yourself:) ...)
        else
            (proc402_2)))                         ; a different, sealing layout

-- so the walkable area, and therefore which screen edges you can leave by, is chosen by a
CONDITION the script states outright. KQ6's catacombs entrance is exactly this: while the minotaur
lives the room walls off its south edge, and that is the only thing stopping you strolling back out
the front door. The polygon coordinates are literals in the AST, so no game resource is needed;
LSL2 and KQ4 contain zero `addObstacle` sends, so this is inert on both.

Polygon semantics are the interpreter's (ScummVM `kpathing.cpp:54-57`): type 0 total access,
1 nearest access, 2 BARRED (may not enter), 3 CONTAINED (may not leave).
"""
from __future__ import annotations

from collections import deque

import ir as I
from extract import atom

W, H = 320, 190              # SCI play area, as sci_gfx has it
BARRED, CONTAINED = 2, 3
EDGES = {1: "north", 2: "east", 3: "south", 4: "west"}      # SCI edgeHit codes


def _polygon(node):
    """`((Polygon new:) type: T init: x1 y1 x2 y2 ... yourself:)` -> (type, [(x,y), ...])."""
    if not (isinstance(node, dict) and node.get("t") == "Send"):
        return None
    try:
        recv, msgs = I.send_pairs(node)
    except Exception:                                       # noqa: BLE001
        return None
    if not (isinstance(recv, dict) and recv.get("t") == "Send"):
        return None                                          # the `(Polygon new:)` receiver
    typ, pts = None, None
    for sel, ps in msgs:
        if sel == "type" and ps:
            typ = I.as_int(ps[0])
        elif sel == "init":
            vals = [I.as_int(p) for p in ps]
            if vals and all(v is not None for v in vals) and len(vals) >= 6:
                pts = list(zip(vals[0::2], vals[1::2]))
    return (typ, pts) if pts else None


def _proc_polygons(ir):
    """proc name -> [(guard, polygons), ...] -- the layouts it installs, one per BRANCH.

    A room often keeps its SEALED layout in a shared helper (`(proc402_2)`) and only its open
    layout inline, so without following the call one branch looks like it has no obstacles at all,
    and two layouts are needed to see a gate.

    The helper's OWN branches have to survive the trip, which is the whole point. KQ6's rm340
    calls `(proc343_0)` unconditionally, and the proc is nothing but the choice:

        (procedure (proc343_0)
            (if (proc913_0 1) (global2 addObstacle: <minotaur dead>)
                         else (global2 addObstacle: <minotaur alive>)))

    Flattened to one list, the two layouts UNION -- and a union blocks everything that either
    layout blocks, which walled off the whole cliff face and made the room look like it had a
    single unconditional layout. So this walks the proc the same way `room_obstacles` walks an
    init, and the call site composes the two conditions."""
    from extract import walk_stream
    cache = getattr(ir, "_poly_procs", None)
    if cache is not None:
        return cache
    out = {}
    for s in ir.scripts.values():
        for name, body in s.procs.items():
            found = []
            walk_stream(body, [], lambda n, pc: _collect(n, pc, found))
            if found:
                out[name] = found
    try:
        ir._poly_procs = out
    except Exception:                                       # noqa: BLE001
        pass
    return out


def _collect(n, pc, out):
    """`addObstacle:` sites in one statement, with the path condition that reaches them."""
    if n.get("t") != "Send":
        return
    try:
        _recv, msgs = I.send_pairs(n)
    except Exception:                                       # noqa: BLE001
        return
    polys = []
    for sel, ps in msgs:
        if sel != "addObstacle":
            continue
        for p in ps:
            got = _polygon(p)
            if got:
                polys.append(got)
    if polys:
        out.append((list(pc), polys))


def room_obstacles(ir, script):
    """[(guard, [(type, points), ...])] -- each `addObstacle:` site in the room's init, with the
    path condition under which it runs. One entry per branch, so the two layouts stay separate."""
    from extract import walk_stream
    procs = _proc_polygons(ir)
    out = []

    def leaf(n, pc):
        if n.get("t") in ("PublicCall", "LocalCall") and n.get("name") in procs:
            # A helper installs these layouts. Its own branch condition ANDs with the condition
            # that reached the call -- so `(proc343_0)` called unconditionally still contributes
            # two layouts, one per branch, not their union.
            for (inner, polys) in procs[n["name"]]:
                out.append((list(pc) + list(inner), polys))
            return
        _collect(n, pc, out)

    for o in script.objects:
        body = o.methods.get("init")
        if body is not None:
            walk_stream(body, [], leaf)
    return out


def _inside(pt, poly):
    """Even-odd ray cast."""
    x, y = pt
    n, inside = len(poly), False
    j = n - 1
    for i in range(n):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > y) != (yj > y):
            xc = xi + (y - yi) * (xj - xi) / float(yj - yi if yj != yi else 1)
            if x < xc:
                inside = not inside
        j = i
    return inside


def _blocked_mask(polys, step=4):
    """A coarse walkability grid: True where the ego may NOT stand.

    Sampled every `step` pixels -- we are asking whether a whole screen edge is reachable, not
    placing a sprite, and a 4px lattice over 320x190 is 80x48 cells."""
    gw, gh = W // step, H // step
    blocked = bytearray(gw * gh)
    contained = [p for (t, p) in polys if t == CONTAINED]
    barred = [p for (t, p) in polys if t == BARRED]
    for gy in range(gh):
        for gx in range(gw):
            pt = (gx * step + step // 2, gy * step + step // 2)
            bad = any(_inside(pt, p) for p in barred)
            if not bad and contained:
                bad = not any(_inside(pt, p) for p in contained)
            if bad:
                blocked[gy * gw + gx] = 1
    return blocked, gw, gh


def reachable_edges(polys, seeds=None, step=4):
    """Which screen edges the ego can walk to, given this obstacle layout.

    Flood from the room's middle band (an arrival point we do not know exactly) rather than from
    a declared position: we are comparing two LAYOUTS of the same room, so the same seeding
    applies to both and a difference between them is the layout's doing."""
    blocked, gw, gh = _blocked_mask(polys, step)
    if seeds is None:
        seeds = [(gx, gh // 2) for gx in range(gw)] + [(gw // 2, gy) for gy in range(gh)]
    q = deque()
    seen = set()
    for (gx, gy) in seeds:
        if 0 <= gx < gw and 0 <= gy < gh and not blocked[gy * gw + gx]:
            seen.add((gx, gy))
            q.append((gx, gy))
    while q:
        gx, gy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = gx + dx, gy + dy
            if 0 <= nx < gw and 0 <= ny < gh and (nx, ny) not in seen \
                    and not blocked[ny * gw + nx]:
                seen.add((nx, ny))
                q.append((nx, ny))
    out = set()
    for (gx, gy) in seen:
        if gy == 0:
            out.add("north")
        if gy == gh - 1:
            out.add("south")
        if gx == 0:
            out.add("west")
        if gx == gw - 1:
            out.add("east")
    return out


def polygon_gates(ir, room):
    """[{room, edge, guard}] -- a screen edge this room's obstacle layout OPENS only under a
    condition, i.e. a positional exit that is really gated.

    Emitted only where the layouts genuinely DIFFER on that edge, so a room whose obstacles are
    unconditional (the overwhelming majority) yields nothing. The guard reported is the branch
    that OPENS the edge -- derived by comparing reachability, never assumed from which branch
    installs more polygons."""
    script = ir.scripts.get(room)
    if script is None:
        return []
    sites = room_obstacles(ir, script)
    if len(sites) < 2:
        return []                                # nothing to compare: one layout, or none
    per = [(pc, reachable_edges(polys)) for pc, polys in sites]
    out = []
    for edge in ("north", "south", "east", "west"):
        opens = [pc for pc, edges in per if edge in edges]
        closes = [pc for pc, edges in per if edge not in edges]
        if not opens or not closes:
            continue                             # every layout agrees -> not a gate
        for pc in opens:
            g = [a for a in pc if a is not None]     # walk_stream already built these atoms
            if g:
                out.append({"room": room, "edge": edge, "guard": g})
    return out
