"""Discover the two reachability anchors -- START and GOAL -- from the game itself.

These were the last hand-declared, game-specific values in the pipeline. Everything else is
derived from the binary, so a new SCI title needed a human to read the scripts and name two room
numbers before the analysis could run at all.

Both turn out to be structural:

  START  the free-roam world the engine's entry paths funnel into. The entries (the graph ROOTS)
         include copy-protection and intro screens that reach the whole game, so widest-reach alone
         picks one of those; instead prefer the room reached by the MOST entries -- a pass-through
         root is reached only by itself. LSL2 lands in the LA cluster (rm11), KQ4 on rm99. See
         discover_start.

  GOAL   the ending is the room you can reach, cannot leave, and do not die in: TERMINAL (no
         outgoing edges) + reachable + never raises the death signal. Deaths are terminal too, so
         excluding them is what makes the rule work. LSL2 yields rm86, entered from the rm178
         wedding cutscene.

Validated on LSL2: the derived pair (start rm11, goal rm86) yields the SAME findings as the old
hand-set pair (start rm21, goal rm178) -- 15 stranded items plus the Ashes/Sand group -- though the
anchor ROOMS differ (discovery lands on a free-roam LA room and the ending's terminal, not the
human-tidy rm21/rm178). Confirmed identical 2026-07-22 by diffing the full output surface (snapshot.py).
"""
from __future__ import annotations

from collections import deque


def movement_edges(em):
    """Room -> rooms, from every movement construct. Deliberately guard-IGNORING: anchors are
    about which rooms EXIST downstream, and being permissive here cannot hide one."""
    edges = {}
    def add(a, b):
        edges.setdefault(a, set()).add(b)
    for e in em.ts.edges:
        add(e.src, e.dst)
    for e in em.ts.cs_edges:
        add(e.src, e.dst)
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "EXIT":
                    add(info["room"], tr[1])
    return edges


def reachable(edges, start_set):
    seen = set(start_set)
    q = deque(seen)
    while q:
        u = q.popleft()
        for v in edges.get(u, ()):
            if v not in seen:
                seen.add(v)
                q.append(v)
    return seen


def death_rooms(em):
    """Rooms that can raise the death signal -- via a lifted DEATH transition or a direct write."""
    out = set()
    for info in em.machines:
        for K, paths in info["states"].items():
            for (g, w, gg, c, tr) in paths:
                if tr and tr[0] == "DEATH":
                    out.add(info["room"])
                for (gi, v) in w:
                    if em.is_death(gi, v):
                        out.add(info["room"])
    for room, script, gi, v, g in em.handler_writes:
        if em.is_death(gi, v):
            out.add(room)
    return out


def engine_entry(em, edges=None):
    """Rooms the game enters at startup = the movement graph's ROOTS (no in-edges).

    Main drives the first transition with `self newRoom:`, which is a send to the Game object
    rather than a room-to-room edge, so it never appears in the graph. But it does not need to:
    the room the engine drops you into is by definition the one nothing else leads to. On LSL2
    this yields exactly {10, 99} -- precisely Main's two `newRoom:` targets, recovered without
    reading Main at all."""
    edges = edges if edges is not None else movement_edges(em)
    has_in = {b for bs in edges.values() for b in bs}
    return {r for r in em.rooms if r not in has_in and edges.get(r)}


def discover_start(em, edges=None, entries=None):
    """First room the player can ACT in -- the free-roam world the engine entries funnel into.

    The engine entries (`engine_entry`, the graph ROOTS) include copy-protection and intro screens
    you pass through once and never return to. Widest-reach alone picks one of those, because it
    reaches the whole game (LSL2's copy-protection rm10 reaches 89 rooms) -- and that pulls the
    intro into the analysed graph, inventing guard specs on edges out of it.

    So prefer the rooms reached by the MOST engine entries. A pass-through root is reached only by
    ITSELF; the free-roam world every entry path leads into is reached by all of them, so it wins
    and the roots drop out. When a game's real start simply IS a single root (KQ4's rm99, with no
    second entry converging elsewhere) nothing is excluded and this degrades to widest-reach, which
    is right. Tie broken by widest reach, so the anchor still sees the most of the game. On LSL2
    this lands in the free-roam LA cluster (identical findings to the old hand-set rm21, and no
    intro-tangle guard); on KQ4, rm99."""
    edges = edges if edges is not None else movement_edges(em)
    entries = entries or engine_entry(em, edges)
    if not entries:
        entries = set(edges)                       # degenerate graph: consider everywhere
    from collections import Counter
    reached_by = Counter()
    for r in entries:
        for room in reachable(edges, {r}):
            reached_by[room] += 1
    if not reached_by:
        return None
    most = max(reached_by.values())
    pool = [room for room, c in reached_by.items() if c == most]
    candidate = max(sorted(pool), key=lambda r: len(reachable(edges, {r})))
    # Fragmentation guard. When the entries funnel into a small cluster that is a DISJOINT component
    # from the free-roam world -- Camelot's intro reaches rm51's 3-room cluster, while the overland
    # map hub is a separate 24-room component the graph joins only through a Main `newRoom:` it never
    # sees -- the candidate reaches almost none of the game. Swap to the widest-reaching room ONLY
    # when the two reaches share NO room, i.e. they are genuinely different components. Any overlap
    # means the same region and the candidate stays right: SQ3 rm900 shares 36 rooms with the wider
    # rm40; LSL2 rm11 lies inside rm10's reach. (A pure subset test would wrongly swap SQ3.)
    widest = max(sorted(em.rooms), key=lambda r: len(reachable(edges, {r})), default=candidate)
    cand_reach = reachable(edges, {candidate})
    wide_reach = reachable(edges, {widest})
    # Swap to the widest room in two cases. (a) DISJOINT component -- Camelot's intro reaches a
    # 3-room cluster while the overland hub is a separate component (no shared room). (b) SINK --
    # the candidate is reached by the most entries yet itself reaches almost nothing, so it is a
    # dead-end the entries funnel into, not the free-roam world. KQ6's uncaptured labyrinth rooms
    # are spurious roots that all flow to rm400 (a maze dead-end), making it "reached by most"
    # while it reaches only itself. A genuine free-roam start reaches about as much as the widest
    # room does (LSL2 ratio .99, KQ4 1.0); a sink is a small fraction. Any overlap with a candidate
    # that reaches a comparable amount keeps the candidate (SQ3 rm900 shares 36 rooms with rm40).
    if (cand_reach & wide_reach) and len(cand_reach) * 2 >= len(wide_reach):
        return candidate
    return widest


def _tests_achievement(em, rooms):
    """Of `rooms`, those whose ending asks WHAT THE PLAYER IS CARRYING.

    A death does not check your inventory; it just ends. A victory does -- that is what makes it a
    victory rather than a stop. KQ4's rm694 is `(if (gEgo has: 25) <cure your father> else <watch
    him die>)`, while rm692, the marry-Edgar ending, tests nothing at all.

    Tested against a rival hypothesis and kept. The rival: a losing end offers the player
    Restore/Restart/Quit and a winning one does not, which would ground the test in engine
    vocabulary instead of an inference about game design. It is false -- NO ending room offers that
    dialog in either game, because it is centralised in `Main::doit` behind the game-over global,
    which is the same reason goal discovery needed a fallback at all. What the comparison did show
    is that `has:` occurs in KQ4's winning ending and nowhere in its losing one, and that the
    winner alone CONSUMES what it asked for (`Room694.sc:197`, `(gEgo put: 25 999)`). So this is
    the only structural difference between the two, not a convenient one. A third game would
    stress it properly."""
    from guard_ast import GAnd, GOr, GNot, Pred
    def owns(g):
        if isinstance(g, list):
            return any(owns(x) for x in g)
        if isinstance(g, Pred):
            return g.kind == "OWN"
        if isinstance(g, (GAnd, GOr)):
            return any(owns(k) for k in g.kids)
        if isinstance(g, GNot):
            return owns(g.kid)
        return False
    out = set()
    for info in em.machines:
        if info["room"] not in rooms:
            continue
        guards = [g for _K, paths in info["states"].items() for (g, _w, _gg, _c, _tr) in paths]
        guards += [eg for _K, eg in list(info.get("entries", ()))
                   + list(info.get("init_entries", ()))]
        if any(owns(g) for g in guards):
            out.add(info["room"])
    return out


def discover_goal(em, edges=None, start=None):
    """Terminal, reachable, and never fatal -- the room you reach, cannot leave, and survive."""
    edges = edges if edges is not None else movement_edges(em)
    start = start if start is not None else discover_start(em, edges)
    if start is None:
        return frozenset()
    reach = reachable(edges, {start})
    deadly = death_rooms(em)
    rooms = set(em.rooms)
    out, excluded = set(), set()
    for r in sorted(reach):
        if r not in rooms or r == 0:               # script 0 is Main, not a location
            continue
        if set(edges.get(r, ())) - {r}:            # still has somewhere to go
            continue
        (excluded if r in deadly else out).add(r)
    if out:
        return frozenset(out)
    # FALLBACK for a game that ends the run through the SAME flag it uses for death. KQ4's
    # global127 does not mean "you died", it means "the game is over": it is set in 33 death rooms
    # AND in both endings, so the deadly filter above throws victory out with the losses and
    # returns nothing. That is the whole reason KQ4's goal has been a declared prototype.
    #
    # Among the terminals we just excluded, the ending that TESTS WHAT YOU ACHIEVED is the win.
    # KQ4's two are rm694 -- `(if (gEgo has: 25) <cure your father> else <watch him die>)` -- and
    # rm692, the marry-Edgar ending, which asks nothing. Note this makes victory a STATE and not
    # really a room: rm694 holds both outcomes, and it is the Magic Fruit requirement, captured
    # separately, that distinguishes them. Naming the room is the honest half of that; see
    # TODO 6.1 for making the goal a predicate.
    return frozenset(_tests_achievement(em, excluded))


def discover(em):
    """(start_room, goal_rooms) derived from the game."""
    edges = movement_edges(em)
    start = discover_start(em, edges)
    return start, discover_goal(em, edges, start)
