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
    # The size ratio this used to test (`cand*2 >= wide`) is the right IDEA stated as a magic
    # number, and the number is what breaks: a genuine start scores ~1.0 and a sink a small
    # fraction, but KQ6's rm140 scores 0.62 and squeaks past a 0.5 bar, losing 29 rooms including
    # the whole sacred-mountain/catacombs/realm half of the game.
    #
    # State it structurally instead: preferring the candidate is only safe if it COSTS NOTHING.
    # Discounting the entry rooms themselves -- a pass-through root's sole contribution is itself,
    # which is exactly what we are trying to drop -- keep the candidate unless the widest room
    # reaches real rooms the candidate cannot. LSL2's rm10 adds only rm10, so rm11 still wins;
    # KQ6's rm320 adds 29 real rooms, so it wins. No threshold to tune.
    if (cand_reach & wide_reach) and not ((wide_reach - entries) - (cand_reach - entries)):
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


def _conjuncts(g):
    """Top-level conjuncts of a guard, flattening nested GAnd and lists."""
    from guard_ast import GAnd
    if g is None:
        return []
    if isinstance(g, list):
        return [c for x in g for c in _conjuncts(x)]
    if isinstance(g, GAnd):
        return [c for k in g.kids for c in _conjuncts(k)]
    return [g]


def _mutually_exclusive(a, b):
    """Do these two guards contradict -- does one ASSERT a conjunct the other NEGATES?

    Sound but incomplete, and that is the right direction: a missed contradiction leaves the
    candidate goal where it was, while a false one would invent a branch. KQ6's two weddings are
    `12 == 180` against `AND(NOT(12 == 180), NOT(12 == 790), 338 != 0)`, which this catches on the
    first conjunct."""
    from guard_ast import GNot
    def split(g):
        cs = _conjuncts(g)
        return ({repr(x) for x in cs if not isinstance(x, GNot)},
                {repr(x.kid) for x in cs if isinstance(x, GNot)})
    pa, na = split(a)
    pb, nb = split(b)
    return bool((pa & nb) or (pb & na))


def _machine_guards(info):
    return ([g for _K, paths in info["states"].items() for (g, _w, _gg, _c, _tr) in paths]
            + [eg for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ()))])


def _machine_tests_achievement(info):
    """Does this machine ask what the player is CARRYING? See `_tests_achievement`, which is the
    same question asked of a whole room."""
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
    return owns(_machine_guards(info))


def _entry_rooms(info, prev):
    """The rooms you must have come FROM for this machine to be armed, if that is what its entry
    says. `prev` is the previous-room register. A machine whose entry is `prevRoom == N` is armed
    exactly by arriving from rm N, so a goal expressed as that machine is the goal room N."""
    from guard_ast import GNot, Pred
    out = set()
    for _K, eg in list(info.get("entries", ())) + list(info.get("init_entries", ())):
        for c in _conjuncts(eg):
            pol, node = True, c
            if isinstance(node, GNot):
                pol, node = False, node.kid
            if not (isinstance(node, Pred) and node.kind == "CMP" and node.var == prev):
                continue
            # `x == v`, and `not (x != v)`, both assert v -- SCI writes the negated spelling often
            # enough that reading only the first would miss half of them.
            if (node.op == "==") != pol:
                continue
            try:                              # CMP values arrive as strings; same as `_atoms`
                out.add(int(node.value))
            except (TypeError, ValueError):
                pass
    return out


def _resolve_pass_through(em, edges, terminals):
    """Replace a terminal that merely REPORTS the outcome with the state that DECIDES it.

    A terminal with a single predecessor tells you nothing its predecessor does not: you cannot
    arrive at it any other way, so reaching it is reaching the predecessor. KQ6's rm94 is the
    credits, entered only from rm740, and rm740 runs one of three ending scripts with the credits
    following ANY of them -- so "can you still reach rm94" was answered yes by DEFEAT.

    Where the outcome is actually decided is a branch, and a branch looks like RIVAL machines:
    two or more armed in the same room whose entry conditions CONTRADICT, so at most one can run.
    If the achievement test -- the same "does this ending ask what you are carrying" that
    `_tests_achievement` applies to rooms -- separates those rivals, splitting them into some that
    do and some that do not, then it has told us which branch is the win and the goal is that
    machine. If every rival tests achievement, or none does, it has told us nothing and the
    terminal stands.

    The goal must then be expressible as a ROOM, because that is what `goal_rooms` is. It is when
    the winning machine's entry is a condition on the previous-room register: KQ6's `alexWedding`
    is armed by `12 == 180`, so the goal is rm180, the post-fight cutscene that is the only way to
    enter rm740 having won. A winner gated on a FLAG instead has no room-set equivalent and is
    left alone -- see TODO 6.1, where the goal becomes a predicate.

    Measured on all three oracle games. LSL2's rm86 and KQ4's rm694 each have a single predecessor
    holding ONE machine, so there is no branch and neither moves; KQ6's rm740 holds `alexWedding`
    (`12 == 180`, and the only machine there with an OWN predicate anywhere in it) against
    `vizierWedding` (`AND(NOT(12 == 180), ...)`, none), so it resolves to rm180.

    PROVISIONAL -- see docs/KQ6-GOAL.md. The achievement signal itself is confirmed on two games
    only, and KQ6 is the one it was designed against."""
    import extract as X
    prev = X.prev_room_global(getattr(em, "ir", None)) if getattr(em, "ir", None) else None
    if prev is None:
        return terminals
    preds_of = {}
    for a, bs in edges.items():
        for b in bs:
            if a != b:
                preds_of.setdefault(b, set()).add(a)
    won = set()
    for t in sorted(terminals):
        p = preds_of.get(t) or set()
        if len(p) != 1:                        # more than one way in: the terminal is a choice
            continue
        room = next(iter(p))
        armed = [i for i in em.machines
                 if i["room"] == room and (i.get("entries") or i.get("init_entries"))]
        rivals = [i for i in armed
                  if any(_mutually_exclusive(g, h)
                         for j in armed if j is not i
                         for _K, g in list(i.get("entries", ())) + list(i.get("init_entries", ()))
                         for _K2, h in list(j.get("entries", ())) + list(j.get("init_entries", ())))]
        if len(rivals) < 2:
            continue
        tests = [i for i in rivals if _machine_tests_achievement(i)]
        if not tests or len(tests) == len(rivals):
            continue                           # the signal separates nothing here
        rooms = set().union(*(_entry_rooms(i, prev) for i in tests))
        won |= {r for r in rooms if r in set(em.rooms)}
    # An ending that tests what you achieved beats one that does not -- the rule KQ4's fallback
    # already runs over terminals, applied once more to the resolved set. Without it KQ6 keeps
    # rm205, the sail-home ending, alongside the win.
    return frozenset(won) if won else terminals


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
        return _resolve_pass_through(em, edges, frozenset(out))
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
    return _resolve_pass_through(em, edges, frozenset(_tests_achievement(em, excluded)))


def discover(em):
    """(start_room, goal_rooms) derived from the game."""
    edges = movement_edges(em)
    start = discover_start(em, edges)
    return start, discover_goal(em, edges, start)
