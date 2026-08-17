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


_INSTANCE_POLYS = {}


def instance_polygons(script):
    """`{objname: (type, points)}` -- THE SECOND SPELLING of the same fact.

    KQ6 and QFG build the layout inline, as one expression per obstacle, which is what `_polygon`
    reads. KQ5 declares the polygons as INSTANCES and fills them from a local array literal:

        (instance poly1 of Polygon (properties type 2))       ; the type is a property...
        ...
        (self addObstacle: poly1 poly2 poly3 poly4 poly5)     ; ...the layout names them...
        (poly1 points: @local3 size: 6)                       ; ...and the points arrive by
        [local3 12] = [319 48 223 77 103 72 183 51 247 0 319 0]   ;   ADDRESS of a local array

    Same three facts (type, point count, coordinates), all still literals in the AST, just taken
    apart across three statements. Reading only the inline form meant KQ5's obstacle layout did
    not exist for us: MEASURED, 84 `addObstacle:` sites across 67 rooms and `room_obstacles`
    returned polygons for NONE of them, so every KQ5 room looked like open floor. LSL2 and KQ4
    have no obstacles at all, and KQ6/QFG/LB2 pass expressions rather than named instances, so
    this spelling is (measured) KQ5's alone -- but it is a SPELLING, not a game quirk, which is
    why it is read structurally rather than keyed on the game.

    Refusals, both in the direction of having no layout rather than a wrong one: an instance
    given points TWICE with different arrays is ambiguous (we do not know which assignment the
    engine sees last, and a room that re-points a polygon is choosing between layouts), and an
    array whose every slot is not a literal integer is not a polygon we can trust.

    `size:` is the point COUNT, so the array must supply twice that many integers -- reading it
    as a length in words would silently halve every polygon."""
    hit = _INSTANCE_POLYS.get(id(script))
    if hit is not None and hit[0] is script:
        return hit[1]
    lits = {d["index"]: d["value"] for d in (getattr(script, "locals", None) or [])
            if isinstance(d, dict) and isinstance(d.get("value"), int)}
    seen = {}
    for o in script.objects:
        for body in o.methods.values():
            for n in I.walk(body):
                if not (isinstance(n, dict) and n.get("t") == "Send"):
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                               # noqa: BLE001
                    continue
                if not (isinstance(recv, dict) and recv.get("t") == "Object"):
                    continue
                base = npts = None
                for sel, ps in msgs:
                    if sel == "points" and ps and isinstance(ps[0], dict) \
                            and ps[0].get("t") == "AddressOf":
                        v = (ps[0].get("kids") or [None])[0]
                        if isinstance(v, dict) and v.get("vtype") == "Local":
                            base = v.get("index")
                    elif sel == "size" and ps:
                        npts = I.as_int(ps[0])
                if base is not None and npts:
                    seen.setdefault(recv["name"], set()).add((base, npts))
    byname = {o.name: o for o in script.objects}
    out = {}
    for name, got in seen.items():
        if len(got) != 1 or name not in byname:
            continue                                            # two layouts for one instance
        (base, npts), = got
        vals = [lits.get(base + i) for i in range(2 * npts)]
        if npts < 3 or any(v is None for v in vals):
            continue
        out[name] = (byname[name].props.get("type"), list(zip(vals[0::2], vals[1::2])))
    _INSTANCE_POLYS[id(script)] = (script, out)
    return out


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
        inst = instance_polygons(s)
        for name, body in s.procs.items():
            found = []
            walk_stream(body, [], lambda n, pc, _f=found, _i=inst: _collect(n, pc, _f, _i))
            if found:
                out[name] = found
    try:
        ir._poly_procs = out
    except Exception:                                       # noqa: BLE001
        pass
    return out


def _collect(n, pc, out, inst=None):
    """`addObstacle:` sites in one statement, with the path condition that reaches them.

    `inst` is the script's `instance_polygons` map, so an argument that NAMES a polygon resolves
    to the same `(type, points)` an inline one produces -- one shape downstream, two spellings
    read here."""
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
            if got is None and inst and isinstance(p, dict) and p.get("t") == "Object":
                got = inst.get(p.get("name"))
            if got:
                polys.append(got)
    if polys:
        out.append((list(pc), polys))


def room_obstacles(ir, script):
    """[(guard, [(type, points), ...])] -- each `addObstacle:` site in the room's init, with the
    path condition under which it runs. One entry per branch, so the two layouts stay separate."""
    from extract import walk_stream
    procs = _proc_polygons(ir)
    inst = instance_polygons(script)
    out = []

    def leaf(n, pc):
        if n.get("t") in ("PublicCall", "LocalCall") and n.get("name") in procs:
            # A helper installs these layouts. Its own branch condition ANDs with the condition
            # that reached the call -- so `(proc343_0)` called unconditionally still contributes
            # two layouts, one per branch, not their union.
            for (inner, polys) in procs[n["name"]]:
                out.append((list(pc) + list(inner), polys))
            return
        _collect(n, pc, out, inst)

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


def _room_object(script, ir=None):
    """The Rm instance -- `extract._room_object`, not a second answer to the same question.

    This file used to identify the room as "the object carrying a `picture` property", which is
    a different rule and gives different answers: measured across the four games it picks up
    INSETS (LB2's `inNotebook` and `clockInset`, KQ6's `keyHole` and `lampSellerInset` all carry
    a picture and are not rooms) and misses rooms that carry none (ten of LSL2's). Reading nav
    properties off an inset is how a dead-nav row -- an EDGE DELETION -- could be raised against
    an object that has no exits at all.

    Both answers agree on every row today (measured: LB2 keeps rm240-east and rm330-south, the
    other three stay empty), so this is the duplicate collapsing while the answer is the same,
    which is the only comfortable time to do it. `extract`'s version is the derived one: it
    resolves the game's own Rm/Room class closure and falls back to the `rm<N>` name.
    [[same-rule-two-places]] -- the same lookup living in two modules cost this project KQ4's
    26 region scripts once already."""
    from extract import _room_object as _canonical
    return _canonical(script, ir)


_EDGE_BANDS = {}


def edge_bands(ir):
    """`{"south": y, "east": x, "west": x}` -- the coordinates at which THIS GAME hands the ego
    off at a screen edge, read from its own ego class. None when the game does not spell them.

    The rule is the game's, not the engine's, and it is written down in one place: the ego's
    `doit` assigns `edgeHit` from a cond over its own position. All four titles here spell it
    identically --

        (= edgeHit (cond ((<= x 0) 4) ((>= x 319) 2) ((>= y 189) 3)
                         ((<= y (global2 horizon:)) 1) (else 0)))

    -- which is exactly why it must be derived rather than pinned: agreement across four games
    is what a hardcoded 320x190 assumption looks like right up until the game that disagrees,
    and this rule DELETES edges, so a band that is wrong in the small direction seals a room
    the player can leave. Found as a hand-picked `H - 6` / `W - 40` by the v1.0-lb2 review
    (§1.1) and re-derived here.

    NORTH IS NOT RETURNED even though the cond carries it: its bound is `(global2 horizon:)`, a
    property read rather than a literal -- the game itself declines to state a number -- and the
    ego's height would be needed on top of it. The refusal `dead_nav_exits` documents is thus
    the game's own, not a modelling shortcut."""
    hit = _EDGE_BANDS.get(id(ir))
    if hit is not None:
        return hit[1]
    out = {}
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if not (isinstance(n, dict) and n.get("t") == "Assignment"):
                        continue
                    ks = n.get("kids") or []
                    if not (ks and isinstance(ks[0], dict)
                            and ks[0].get("name") == "edgeHit" and len(ks) > 1):
                        continue
                    for c in I.walk(ks[1]):
                        if not (isinstance(c, dict) and c.get("t") in ("Le", "Ge")):
                            continue
                        kk = c.get("kids") or []
                        var = kk[0].get("name") if kk and isinstance(kk[0], dict) else None
                        lit = I.as_int(kk[1]) if len(kk) > 1 else None
                        if lit is None or var not in ("x", "y"):
                            continue
                        key = ("west" if c["t"] == "Le" else "east") if var == "x" else \
                              ("south" if c["t"] == "Ge" else None)
                        if key and key not in out:
                            out[key] = lit
    got = out if {"south", "east", "west"} <= set(out) else None
    _EDGE_BANDS[id(ir)] = (ir, got)
    return got


def _arrival_seeds(rm):
    """The literal `(gEgo posn: x y)` points in the room's init -- where the player ARRIVES.

    One per direction the room is entered from, which is the whole reason a room states them."""
    out = []
    init = rm.methods.get("init")
    for send in (I.sends(init) if init else ()):
        recv, msgs = I.send_pairs(send)
        if not I.is_global(recv, 0):
            continue
        for sel, ps in msgs:
            if sel == "posn" and len(ps) >= 2:
                x, y = I.as_int(ps[0]), I.as_int(ps[1])
                if x is not None and y is not None:
                    out.append((x, y))
    return out


def _exit_zones(ir, gw, gh, step):
    """`{edge: [cells]}` -- the engine's handoff zone for each edge, in the ego's BASE coords.

    The BANDS come from the game (`edge_bands`, the ego's own `edgeHit` cond); the SLACK on top
    of them is ours, an over-approximation in the KEEPING direction -- the zone is made easier
    to reach than the engine makes it, so an edge is called unusable only when the walkable
    area falls well short of it. 40px stands in for a wide scaled ego's footprint on the sides.

    ⛔ NORTH IS NEVER HERE -- the engine tests the ego's bounding RECT against the horizon, so
    the north handoff fires when `base_y - ego_height <= horizon`, and the ego's height is a
    scaled VIEW fact this module does not model. Returns None when the game never spells its
    handoff at all."""
    bands = edge_bands(ir)
    if bands is None:
        return None
    slack_ew, slack_s = 40, 6
    return {
        "south": [(gx, gy) for gx in range(gw) for gy in range(gh)
                  if gy * step + step // 2 >= bands["south"] - slack_s],
        "east":  [(gx, gy) for gx in range(gw) for gy in range(gh)
                  if gx * step + step // 2 >= bands["east"] - slack_ew],
        "west":  [(gx, gy) for gx in range(gw) for gy in range(gh)
                  if gx * step + step // 2 <= bands["west"] + slack_ew],
    }


def _walk_from_arrival(polys, seeds_px, discs=(), step=4):
    """Flood the walkable area from the arrival points, treating `discs` as solid.

    `discs` are `(cx, cy, r)` LETHAL ZONES. A zone is modelled as an obstacle because that is
    exactly what it is for a player who intends to survive: ground you may step onto and not
    come back from is ground you may not cross. A seed INSIDE a zone is dropped rather than
    flooded -- arriving there is dying there, so it is not a place any live walk begins.

    Returns `(reached_cells, gw, gh, live_seeds)`."""
    blocked, gw, gh = _blocked_mask(polys, step)
    b = bytearray(blocked)
    for (cx, cy, r) in discs:
        rr = r * r
        for gy in range(gh):
            for gx in range(gw):
                dx = gx * step + step // 2 - cx
                dy = gy * step + step // 2 - cy
                if dx * dx + dy * dy < rr:
                    b[gy * gw + gx] = 1
    seeds = []
    for (x, y) in seeds_px:
        gx = min(max(x // step, 0), gw - 1)
        gy = min(max(y // step, 0), gh - 1)
        if not b[gy * gw + gx]:
            seeds.append((gx, gy))
    q, seen = deque(seeds), set(seeds)
    while q:
        gx, gy = q.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = gx + dx, gy + dy
            if (0 <= nx < gw and 0 <= ny < gh and (nx, ny) not in seen
                    and not b[ny * gw + nx]):
                seen.add((nx, ny))
                q.append((nx, ny))
    return seen, gw, gh, seeds


def hazard_barred_exits(ir, room, discs):
    """`{edge: declared_room}` -- exits the ego can walk to, but not while `discs` are lethal.

    The geometric half of a positional death gate. `discs` are `(x, y, radius)` circles around a
    stationary hazard whose `doit` kills the ego inside that radius. The question is the one
    `control_oracle.crossing_forces_rect` asks of the PIC control plane for SCI0 -- *can the ego
    get from where it arrives to the exit without entering the killing zone?* -- asked of the
    obstacle polygons instead, because that is where an SCI1 room keeps its walkable area.

    An edge is reported ONLY when it is reachable with the hazard gone and unreachable with it
    present, so the barring is attributed to the hazard and not to the room's own walls.

    Everything refuses toward NOT barring, because barring removes movement:
      * only UNCONDITIONAL `addObstacle:` sites are used. A conditional layout is a layout we
        may not be looking at, and leaving its walls out can only make the exit look MORE
        reachable, i.e. less likely to be called barred.
      * no polygons at all -> no walkable-area model -> no claim. (This is why LSL2 and KQ4,
        which have no obstacles, can never produce one of these; their positional gates come
        from the control plane instead.)
      * no literal arrival point, or no derivable edge bands -> no claim.
      * north is never claimed (`_exit_zones`).

    A `setRegions:` does NOT refuse the room, and the asymmetry is the point: `dead_nav_exits`
    refuses on it because a region's own polygons could make an edge reachable that the room's
    layout alone does not, and that rule DELETES the edge outright. Here extra walls can only
    SHRINK both walks, and shrinking the hazard-free walk is what stops a gate being emitted --
    so an unread region layout costs coverage, never soundness."""
    script = ir.scripts.get(room)
    rm = _room_object(script, ir) if script else None
    if rm is None or not discs:
        return {}
    from extract import NAV_SELECTORS
    declared = [(d, rm.props.get(d)) for d in NAV_SELECTORS
                if rm.props.get(d) and rm.props.get(d) != 0xffff]
    if not declared:
        return {}
    polys = [p for pc, ps in room_obstacles(ir, script)
             if not any(a is not None for a in pc) for p in ps]
    seeds_px = _arrival_seeds(rm)
    if not polys or not seeds_px:
        return {}
    step = 4
    free, gw, gh, _s = _walk_from_arrival(polys, seeds_px, (), step)
    hurt, _gw, _gh, _s2 = _walk_from_arrival(polys, seeds_px, discs, step)
    zones = _exit_zones(ir, gw, gh, step)
    if zones is None:
        return {}
    out = {}
    for d, dst in declared:
        if d not in zones:
            continue
        if any(c in free for c in zones[d]) and not any(c in hurt for c in zones[d]):
            out[d] = dst
    return out


def dead_nav_exits(ir, room):
    """[{room, edge, declared_room}] -- declared s/e/w props whose engine trigger zone the
    room's own unconditional obstacle layout never lets the ego reach. A dead letter: the
    edge handoff fires off the ego's position, and a polygon whose boundary stops short of the
    trigger zone means no ego ever fires it -- so reading the property at face value invents a
    free edge. LB2's rm330 is the case that demanded it (docs/LB2-ORACLE.md §7z): `south 250`
    is the ONLY free way from the museum steps back to the street, and the init polygon's
    lower boundary sits at y<=169 while the south handoff needs the ego's base at y~189. Same
    family as the death-screen and walk-icon rules (`extract._no_walk_rooms`): a declared exit
    the player cannot use.

    ⛔ NORTH IS REFUSED, ALWAYS -- the engine tests the ego's bounding RECT against the
    horizon, so the north handoff fires when `base_y - ego_height <= horizon`, and the ego's
    height is a scaled VIEW fact this module does not model. MEASURED before that was
    understood (2026-08-10): a horizon-band reading killed LB2 rm290's `north 295` (walkable
    corridor tops at y~84, horizon 15 -- fires through the ~70px ego) and five KQ6 Realm
    norths with it; every one was a false removal. South is the ego's BASE row and east/west
    its x +- half-width, so those three stay provable from base geometry, with a conservative
    40px margin standing in for the half-width.

    REMOVING movement is the unsafe direction, so everything refuses toward keeping the edge:
      * every `addObstacle:` site must be UNCONDITIONAL (an empty path condition) -- a room
        that swaps layouts under a condition keeps all its exits here (`polygon_gates` is the
        machinery for those);
      * a `setRegions:` anywhere in the file refuses the whole room -- a region swap can
        install a different layout than the one read;
      * no arrival seed (no literal `gEgo posn:` in init), no polygons at all, or a layout
        that blocks every seed -> refuse."""
    script = ir.scripts.get(room)
    rm = _room_object(script, ir) if script else None
    if rm is None:
        return []
    from extract import NAV_SELECTORS
    declared = [(d, rm.props.get(d)) for d in NAV_SELECTORS
                if rm.props.get(d) and rm.props.get(d) != 0xffff]
    if not declared:
        return []
    sites = room_obstacles(ir, script)
    if not sites or any(any(a is not None for a in pc) for pc, _p in sites):
        return []
    for o in script.objects:
        for ast in o.methods.values():
            if any(I.t(n) == "Selector" and n.get("name") == "setRegions"
                   for n in I.walk(ast)):
                return []
    polys = [p for _pc, ps in sites for p in ps]
    step = 4
    seen, gw, gh, seeds = _walk_from_arrival(polys, _arrival_seeds(rm), (), step)
    if not seeds:
        return []
    zones = _exit_zones(ir, gw, gh, step)
    if zones is None:
        return []                     # the game never spells its handoff: keep every edge
    out = []
    for d, dst in declared:
        if d in zones and not any(cell in seen for cell in zones[d]):
            out.append({"kind": "dead-nav", "room": room, "edge": d, "declared_room": dst})
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
