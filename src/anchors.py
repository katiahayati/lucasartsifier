"""Discover the two reachability anchors -- START and GOAL -- from the game itself.

These were the last hand-declared, game-specific values in the pipeline. Everything else is
derived from the binary, so a new SCI title needed a human to read the scripts and name two room
numbers before the analysis could run at all.

Both turn out to be structural:

  START  the engine enters at Main's own `newRoom:` call, but that is the copy-protection screen
         and the intro, which are CUTSCENES. Walk forward through rooms with no player input until
         the first one the player can actually act in. Several may qualify (LSL2: rm23 and rm90),
         so take the one whose forward reachability covers the most of the game -- a free-roam
         anchor should see the whole map, whereas rm90 is an intro-cutscene tangle that reaches
         only 42 of 88 rooms and would silently analyse half a game.

  GOAL   the ending is the room you can reach, cannot leave, and do not die in: TERMINAL (no
         outgoing edges) + reachable + never raises the death signal. Deaths are terminal too, so
         excluding them is what makes the rule work. LSL2 yields rm86, entered from the rm178
         wedding cutscene.

Validated on LSL2: the derived pair (start rm23, goal rm86) reproduces the hand-tuned pair
(start rm21, goal rm178) EXACTLY -- 15 stranded items plus the Ashes/Sand group. The user
independently confirmed rm23 is "the first real screen".
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
    """First room the player can ACT in, preferring the one that sees the most of the game."""
    edges = edges if edges is not None else movement_edges(em)
    entries = entries or engine_entry(em, edges)
    if not entries:
        entries = set(edges)                       # degenerate graph: consider everywhere
    cutscenes = em._cutscene_room_set()
    seen, q, candidates = set(entries), deque(entries), set()
    for r in list(entries):
        if r not in cutscenes:
            candidates.add(r)
    while q:
        u = q.popleft()
        for v in edges.get(u, ()):
            if v in seen:
                continue
            seen.add(v)
            if v in cutscenes:
                q.append(v)                        # keep walking through the intro
            else:
                candidates.add(v)                  # first room with player input
    if not candidates:
        return None
    # widest forward reach wins; rm90 (an intro-cutscene tangle) sees 42 rooms, rm23 sees 88
    return max(sorted(candidates), key=lambda r: len(reachable(edges, {r})))


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
