"""M6: lift a room's Script state machines into the transition system.

THE GAP THIS CLOSES. `closure.py` modelled guards on MOVEMENT EDGES only. It had
no model of *intra-room progression*, and LSL2's signature softlocks live entirely
there. The raft (rm138) is the proof:

    edge_requirements[(138,42)] == GAnd([opaque((>= day 9))])

-- so the fixpoint let you walk out of the lifeboat holding nothing. Everything
else was already right: past rm27 the closure correctly refuses to re-acquire the
Sunscreen and collapses `gWearingSunscreen` to {2}. It KNEW you could never wear
sunscreen, then let you survive anyway, because the day-3 check sits in state 6
while the exit sits in state 4. A room is not one node; it is a little transition
system, and its exit is reachable only along a path through that system:

    3 -> 4 -> (++day) -> 5 -> 6[the day's hazard] -> 7 -> 4 ...   exit at day >= 9

so you must survive day 3 (sunscreen), 4 (wig), 5 (Grotesque_Gulp) and 6
(Sewing_Kit OR Fruit, and NOT the Spinach_Dip, which is a TRAP: it is tested first
and jumps to the death chain).

WHY THE STATE LIFT ALONE IS NOT ENOUGH. `day` is a script-LOCAL. Unmodelled it is
OPAQUE -> UNKNOWN, so state 6's `else` branch (free survival) stays enabled and the
fixpoint finds a spurious path that skips every hazard. The bounded local counter
is load-bearing, not a detail. model.py's header is right that locals are not
CROSS-ROOM state (they reset on room reload) and wrong that they are irrelevant:
they are the machine's own state, and the machine gates the exit.

WHAT IS MODELLED
  * `switch (= state newState)` cases            -> states
  * if / cond nesting                            -> leaf path conditions
  * `(self changeState: K)`                      -> JUMP K
  * `(= state K)`                                -> SETSTATE K (then cue -> K+1)
  * `(= seconds N)` / `(= cycles N)` / `(self cue:)` /
    `setCycle:|setMotion: ... self` /
    `(otherInstance changeState: K)` (cues back)  -> ADVANCE to state+1
  * `(gCurRoom newRoom: R)`                      -> EXIT R
  * the death write (config.death_signal)        -> DEATH (an absorbing sink)
  * `(++ c)` / `(-- c)` / `(= c <literal>)`      -> bounded counter update

DIRECTION OF ERROR. Same as the rest of the core: we refuse a branch only on a
PROVABLY false guard (3-valued, UNKNOWN stays UNKNOWN), and we miss a stranding
rather than invent one. But the thing that BUYS us that guarantee is
`control_exits`, NOT permissiveness inside the walk -- and confusing the two cost
us a real softlock.

A Script's switch is NOT one chain. It is several SEGMENTS sharing a switch, one
per entry, because each entry is a different player action. So a state that arms no
cue PARKS; it does not fall into the next segment. Letting it fall through (which
this module did at first, on the theory that stalling might invent a dead end) walks
you around the very guard that gates the next segment. rm81, the glacier: six
entries (0,1,2,7,8,20), and only entry 8 -- "throw sand at the ice" -- is guarded by
`(or (has: Ashes) (has: Sand))`. The exit sits at state 19, downstream of 8. Falling
through carried entry 0 from state 0 to state 19 and out, handing you the exit
having thrown nothing, and overriding a flat edge guard that was already RIGHT.

The guarantee never needed that. If we cannot walk a machine, `control_exits` sees
it fail to deliver its exit even with everything granted, and closure falls back to
the flat movement edge. The fake dead end is impossible either way. So: be strict in
the walk, and let the trust gate handle what we do not understand.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(__file__))
from sexpr import Sym                                    # noqa: E402
from model import norm_tree, is_sym, head_is, GOr        # noqa: E402

# Control locals: these ARE the machine's program counter / cue mechanism, not
# data. Never treat them as bounded counters.
CONTROL_LOCALS = {"state", "seconds", "cycles", "ticks"}

# Widest counter domain we will enumerate. The domain is sized from the literals
# the counter is compared against (min-1 .. max+1), so `day` (tested 3..9) spans
# -1..10. A counter compared against nothing is not a candidate in the first place;
# one compared against a huge literal is left UNKNOWN rather than enumerated.
COUNTER_CAP = 64

# A counter may have several possible starting values (KQ4 rm77 sets jumpNum from a
# `switch prevRoomNum`). Cross-product them, but do not let a pathological machine
# explode the start set.
MAX_START_COMBOS = 32


@dataclass
class Machine:
    """One Script instance's changeState switch, as a transition system."""
    script: int
    inst: str
    states: dict = field(default_factory=dict)   # K -> [(guard_tree, [actions])]
    counters: dict = field(default_factory=dict)  # local name -> (lo, hi) inclusive domain
    inits: dict = field(default_factory=dict)     # counter -> {possible starting values}
    entries: list = field(default_factory=list)   # [(state, guard_tree)]
    item_refs: frozenset = frozenset()            # items its guards mention
    flag_refs: frozenset = frozenset()            # globals its guards mention

    def __repr__(self):
        return (f"Machine({self.inst}@{self.script}: {len(self.states)} states, "
                f"counters={self.counters}, entries={[e[0] for e in self.entries]})")

    def project(self, items, flags):
        """The ONLY part of the world this machine can see -- a cache key.

        A machine's answer depends solely on the items/globals its own guards
        mention, so `strandings` (which re-closes ~1400 times, mostly perturbing
        items this machine never looks at) hits the same handful of keys over and
        over. rm138's raft, for instance, sees only items {8,11,12,13} and globals
        {gWearingSunscreen, gWearingWig}.
        """
        return (frozenset(i for i in self.item_refs if i in items),
                tuple(sorted((g, frozenset(flags.get(g, ()))) for g in self.flag_refs)))


# --------------------------------------------------------------------------
# Leaf-path enumeration -> ordered OP SEQUENCES
#
# A path is a list of ops IN SOURCE ORDER, where `("TEST", expr)` sits exactly where
# the test happens. It used to be a (path-condition, actions) PAIR, with the whole
# condition evaluated once against the state's ENTRY counter store -- so a counter
# write earlier on the same path was invisible to a test after it. KQ4 rm78 `jump`
# state 1 is exactly that shape:
#
#     (-- jumpNum)  (if (== jumpNum -1) (curRoom newRoom: 77))
#
# The model demanded jumpNum == -1 at ENTRY, where the game demands 0 at entry and
# decrements first. jumpNum can never be -1 on entry, so the branch was pruned as
# provably false and the exit was swallowed. (`_find_counters`' comment credits the
# lo-clamp fix with rescuing this exit. It did not -- this was why.)
# --------------------------------------------------------------------------
def _leaf_paths(forms, pc=None):
    """Compose forms in sequence: every path through `forms`, ops in source order."""
    res = [list(pc) if pc else []]
    for f in forms:
        nxt = []
        for prefix in res:
            for suffix in _paths_of(f):
                nxt.append(prefix + suffix)
        res = nxt
    return res


def _paths_of(f):
    if not isinstance(f, list) or not f:
        return [[]]
    h = f[0]

    if is_sym(h, "if") and len(f) >= 2:
        test, body = f[1], f[2:]
        then_b, else_b, seen = [], [], False
        for b in body:
            if is_sym(b, "else"):
                seen = True
                continue
            (else_b if seen else then_b).append(b)
        return ([[("TEST", test)] + p for p in _leaf_paths(then_b)] +
                [[("TEST", [Sym("not"), test])] + p for p in _leaf_paths(else_b)])

    if is_sym(h, "cond"):
        out, prior = [], []
        for cl in f[1:]:
            if not (isinstance(cl, list) and cl):
                continue
            t = cl[0]
            tests = list(prior) if is_sym(t, "else") else list(prior) + [t]
            for p in _leaf_paths(cl[1:]):
                out.append([("TEST", x) for x in tests] + p)
            if not is_sym(t, "else"):
                prior = prior + [[Sym("not"), t]]
        return out

    # ---- message sends: exits, jumps, cues ----
    if len(f) >= 2 and isinstance(f[1], Sym) and f[1].is_selector():
        recv = f[0].name if isinstance(f[0], Sym) else "?"
        # `self` passed as an ARGUMENT is SCI's universal "cue me when you're done"
        # callback -- `(aDancer setMotion: MoveTo 46 111 self)`, `(theSound play: self)`,
        # `(aShip setCycle: End self)`. It is the single most common way a state
        # advances, so match the idiom rather than a list of selectors. `self` as the
        # RECEIVER (`(self changeState: 8)`) is not a cue, hence f[1:].
        has_self_arg = any(is_sym(x, "self") for x in f[1:])
        acts = []
        for i, tok in enumerate(f):
            if not (isinstance(tok, Sym) and tok.is_selector()):
                continue
            sel = tok.sel
            a0 = f[i + 1] if i + 1 < len(f) else None
            if sel in ("newRoom", "startRoom") and isinstance(a0, int):
                acts.append(("EXIT", a0))
            elif sel == "changeState" and isinstance(a0, int):
                # `(self changeState: K)` is a jump within THIS machine. Driving
                # another instance (`(calendarScript changeState: 1)`) hands off and
                # that machine cues us back when it finishes -- model it as our own
                # advance. If it never cues back the real machine stalls; treating it
                # as ADVANCE is the permissive direction (we miss, we don't invent).
                acts.append(("JUMP", a0) if recv == "self" else ("ADVANCE", None))
            elif sel == "cue" and recv in ("self", "?"):
                acts.append(("ADVANCE", None))
        if not acts and has_self_arg:
            acts.append(("ADVANCE", None))          # a plain cue callback
        return [acts]

    # ---- assignments: control flow, counters, death ----
    if isinstance(h, Sym) and h.name in ("=", "+=", "-=", "++", "--") \
            and len(f) >= 2 and isinstance(f[1], Sym):
        v, op = f[1].name, h.name
        if v in ("seconds", "cycles"):
            return [[("ADVANCE", None)]]
        if v == "state":
            # `state` is the program counter, never data. `(= state 24)` jumps;
            # `(-- state)` with the following cue re-runs THIS state (SCI's loop
            # idiom: decrement, then the cue's +1 lands you back where you were).
            # Treating `(-- state)` as a counter step -- which is what a naive
            # ++/-- rule does -- silently turns a loop into a fall-through.
            if op == "=" and len(f) >= 3 and isinstance(f[2], int):
                return [[("SETSTATE", f[2])]]
            if op in ("++", "--"):
                return [[("STATEREL", 1 if op == "++" else -1)]]
            return [[]]                              # computed state: leave control alone
        if op in ("++", "--"):
            return [[("STEP", (v, 1 if op == "++" else -1))]]
        if op == "=" and len(f) >= 3:
            # An int keeps its value (counters need it). A bare Sym is kept as its
            # NAME so `_as_death` can still recognise `(= dead TRUE)` -- KQ4's death
            # write. Requiring an int here meant KQ4 produced 0 DEATH actions against
            # LSL2's 41: all 57 `dead` writes sat in the machines as inert SETVARs, so
            # KQ4 machines walked straight THROUGH their death states and handed out
            # every exit downstream as if you had survived. `machine_val` is None only
            # for things we genuinely cannot read.
            if isinstance(f[2], int):
                return [[("SETVAR", (v, f[2]))]]
            if isinstance(f[2], Sym):
                return [[("SETVAR", (v, f[2].name))]]
        return [[("SETVAR", (v, None))]]         # non-literal -> unmodellable

    # A nested `switch` / `switchto` inside a case body. Recurse properly rather than
    # letting the generic fallback shred it: each case is an ALTERNATIVE (and we cannot
    # evaluate the discriminant, so all of them stay open), while the statements WITHIN
    # a case compose in sequence.
    if is_sym(h, "switch") or is_sym(h, "switchto"):
        out = []
        for cl in f[2:]:
            if isinstance(cl, list) and cl:
                out += _leaf_paths(cl[1:] if (isinstance(cl[0], int) or is_sym(cl[0], "else"))
                                   else cl)
        return out or [[]]

    # `while` / `repeat` / `for` bodies: the body may run or not, so both are paths.
    if is_sym(h, "while") and len(f) >= 2:
        return ([[("TEST", f[1])] + p for p in _leaf_paths(f[2:])] +
                [[("TEST", [Sym("not"), f[1]])]])
    if is_sym(h, "repeat"):
        return _leaf_paths(f[1:]) + [[]]
    if is_sym(h, "for") and len(f) >= 4:
        return ([[("TEST", f[2])] + p for p in _leaf_paths(list(f[4:]) + [f[3]])] + [[]])

    # Generic fallback: an unrecognised form. Its list children are SEQUENTIAL
    # statements, so COMPOSE them (_leaf_paths) -- do not union them.
    #
    # This used `out += _paths_of(sub, pc)`, which is the alternative-branch operator.
    # It split a case body into one path per statement: `(1 (= state 5) (= seconds 2))`
    # became `[SETSTATE 5]` (arms no cue -> PARKS, so the jump is lost) and `[ADVANCE]`
    # (-> st+1, a transition the engine never makes) -- never the real
    # `[SETSTATE 5, ADVANCE]` -> state 6. It hit 26 nested control forms in LSL2 and 68
    # in KQ4, every one walked with its actions on the wrong branches.
    subs = [sub for sub in f if isinstance(sub, list)]
    return _leaf_paths(subs) if subs else [[]]


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------
def _script_locals(forms):
    """Names in a script's `(local ...)` block (bare or `name = init`)."""
    out = []
    for f in forms:
        if head_is(f, "local"):
            for t in f[1:]:
                if isinstance(t, Sym) and t.name != "=":
                    out.append(t.name)
    return out


def _find_counters(states, locals_, game, starts):
    """Locals that can be modelled as BOUNDED COUNTERS.

    A local qualifies iff it is compared against an integer literal somewhere in a
    guard (otherwise modelling it buys nothing) AND every write to it is a literal
    assignment or a ++/-- step (otherwise we cannot track it, and guessing would
    invent constraints). Domain bound = the largest literal it meets, + 2.
    """
    cmp_lits, writes_ok, assign_lits = {}, {}, {}
    for _k, paths in states.items():
        for path in paths:
            for (kind, arg) in path:
                if kind == "TEST":
                    for (var, lit) in _cmp_literals(arg):
                        if var in locals_ and var not in CONTROL_LOCALS:
                            cmp_lits.setdefault(var, set()).add(lit)
                elif kind == "STEP":
                    writes_ok.setdefault(arg[0], True)
                elif kind == "SETVAR":
                    var, val = arg
                    if not isinstance(val, int):
                        # Not a number we can track -- None (a computed value) or a
                        # Sym (`(= dead TRUE)`, now carried this far so `_as_death`
                        # can see it). Either way this variable is not a counter, and
                        # guessing a value for it would invent constraints.
                        writes_ok[var] = False
                    else:
                        writes_ok.setdefault(var, True)
                        assign_lits.setdefault(var, set()).add(val)
    out = {}
    for var, lits in cmp_lits.items():
        if writes_ok.get(var) is False:
            continue
        if game.is_global(var):
            continue                                    # globals are the flags model's job
        # Domain must cover every literal the counter is COMPARED against AND every
        # literal ASSIGNED to it, plus its starting values -- INCLUDING negative ones.
        #
        # Comparisons alone are not enough, and clamping into too small a domain is
        # not harmless: a clamped value that is later STEPped re-enters the compared
        # range at the WRONG number. KQ4 rm54 `cleanTable` starts `i` at 7 with a
        # comparison-only domain of (-1,1), so `(-- i)` gave a model value of 1 where
        # the game has 6 -- and any `(!= i 1)` on that path then reads provably-FALSE
        # while the engine reads it true, pruning a branch the game really takes.
        # (Measured elsewhere: rm134 `(= egoPissing 255)` into (-1,2); KQ4 rm43
        # `(= local2 99)` into (-1,4).) This module already argues the mirror case
        # against clamping at 0 -- "one clamp at 0 = one lost exit" -- and then
        # committed the same error at the top of the range.
        span = set(lits) | assign_lits.get(var, set()) | starts.get(var, {0}) | {0}
        lo, hi = min(span) - 1, max(span) + 1
        if hi - lo > COUNTER_CAP:
            continue                                    # too wide to enumerate; leave it UNKNOWN
        out[var] = (lo, hi)
    return out


def _compile_path(path, game, counters):
    """Compile TEST exprs to guard trees, and death writes to DEATH, in place.

    Ops stay in SOURCE ORDER: `run()` applies counter writes and evaluates tests as
    it walks, so a test sees the writes that precede it on its own path.
    """
    out = []
    for (kind, arg) in path:
        if kind == "TEST":
            out.append(("TEST", norm_tree(arg, game, locals_=counters)))
        else:
            out.append(_as_death((kind, arg), game))
    return out


def _counter_inits(forms, counters, switch):
    """What value does each counter START at when the machine runs?

    NOT always 0. KQ4's rm77 sets `(= jumpNum 10)` in `init`, inside
    `(switch prevRoomNum (east ...) (west ...))` -- so the start depends on which
    way you walked in, and there are several possible values. Starting every
    counter at 0 makes state 1's `(== jumpNum 10)` provably false and silently
    swallows the room's only exit.

    So: any literal assignment OUTSIDE the machine's own switch (init / doit /
    handleEvent) is a possible start. If there is none, SCI0 zero-init gives 0.
    We take the UNION -- more starts can only open more paths, which is the
    permissive direction.
    """
    found = {c: set() for c in counters}

    def walk(f):
        if f is switch or not isinstance(f, list) or not f:
            return                      # the machine's own body: those are steps, not inits
        if is_sym(f[0], "=") and len(f) >= 3 and isinstance(f[1], Sym) \
                and f[1].name in found and isinstance(f[2], int):
            found[f[1].name].add(f[2])
        for sub in f:
            walk(sub)

    for f in forms:
        walk(f)
    return {c: (v or {0}) for c, v in found.items()}


def _cmp_literals(e):
    """(var, literal) pairs of integer comparisons anywhere in an expression."""
    out = []
    if not isinstance(e, list) or not e:
        return out
    h = e[0]
    if isinstance(h, Sym) and h.name in ("==", "!=", "<", ">", "<=", ">=") \
            and len(e) >= 3 and isinstance(e[1], Sym) and isinstance(e[2], int):
        out.append((e[1].name, e[2]))
    for sub in e:
        if isinstance(sub, list):
            out += _cmp_literals(sub)
    return out


def _switch_of(method_form):
    for x in method_form[2:]:
        if head_is(x, "switch") or head_is(x, "switchto"):
            return x
    return None


def machines_of(game, num):
    """Every Script instance in script `num` that has a changeState switch."""
    sc = game.scripts.get(num)
    forms = getattr(sc, "forms", None)
    if not forms:
        return {}
    locals_ = _script_locals(forms)
    out = {}
    for f in forms:
        if not (head_is(f, "instance") and len(f) > 1 and isinstance(f[1], Sym)):
            continue
        inst = f[1].name
        for sub in f[2:]:
            if not (head_is(sub, "method") and isinstance(sub[1], list) and sub[1]
                    and is_sym(sub[1][0], "changeState")):
                continue
            sw = _switch_of(sub)
            if sw is None:
                continue
            raw = {}
            seq = 0
            for cl in sw[2:]:
                if not (isinstance(cl, list) and cl):
                    continue
                if isinstance(cl[0], int):
                    st = cl[0]
                elif is_sym(cl[0], "else"):
                    continue
                else:
                    st = seq                       # switchto: implicit sequential cases
                seq += 1
                raw[st] = _leaf_paths(cl[1:], [])
            if not raw:
                continue
            m = Machine(script=num, inst=inst)
            # Init values are needed to SIZE the domains, so scan them for every
            # local first and narrow to the counters afterwards.
            starts = _counter_inits(forms, locals_, sw)
            m.counters = _find_counters(raw, locals_, game, starts)
            m.inits = {c: starts.get(c, {0}) for c in m.counters}
            # Compile path conditions to guard TREES now that we know the counters,
            # so `(== day 3)` becomes a LOCAL pred instead of an OPAQUE one.
            for st, paths in raw.items():
                m.states[st] = [_compile_path(p, game, m.counters) for p in paths]
            m.entries = _entries_of(game, num, inst, forms)
            items, glbs = set(), set()
            for paths in m.states.values():
                for path in paths:
                    for (kind, arg) in path:
                        if kind == "TEST":
                            _refs(arg, items, glbs)
            for (_st, gd) in m.entries:
                _refs(gd, items, glbs)
            m.item_refs, m.flag_refs = frozenset(items), frozenset(glbs)
            out[inst] = m
    return out


def _as_death(act, game):
    """Rewrite the death write into an explicit DEATH sink.

    Both games raise death by writing a global (LSL2 `gCurrentStatus 1001`, KQ4
    `dead TRUE`); config.death_signal names it. In practice a death state also has
    no cue, so it would stall anyway -- but relying on that is relying on an
    accident. Say it.

    Note the value may be a SYMBOL, not an int: KQ4's is literally `(= dead TRUE)`.
    `Game.is_death_write` already compares rendered values so both work; the bug was
    upstream, in refusing to carry a Sym this far.
    """
    if act[0] == "SETVAR" and act[1][1] is not None \
            and game.is_death_write(act[1][0], act[1][1]):
        return ("DEATH", None)
    return act


def _refs(node, items, glbs):
    """Items / globals a guard tree mentions, at any polarity or depth."""
    from model import GAnd, GOr, GNot, Pred
    if isinstance(node, (GAnd, GOr)):
        for k in node.kids:
            _refs(k, items, glbs)
    elif isinstance(node, GNot):
        _refs(node.kid, items, glbs)
    elif isinstance(node, Pred):
        if node.kind == "OWN":
            items.add(node.var)
        elif node.kind in ("FLAG", "CMP"):
            glbs.add(node.var)


def _entries_of(game, num, inst, forms):
    """Where does this machine start?

    Either `(X setScript: inst)` (state 0) or `(inst changeState: K)` from a
    doit/handleEvent (state K). model.py emits BOTH as STATE effects with their
    path condition attached, so both arrive here already guarded -- which is the
    whole point: KQ4's whale gates `(ego setScript: tickle)` behind the feather,
    so entry 0 is NOT free, and treating it as free hands you the exit for nothing.

    We take the UNION of entries. That is the permissive direction: more ways in
    can only yield more exits, i.e. miss a stranding rather than invent one.
    """
    ents, byk = [], {}
    for t in game.scripts[num].transitions:
        from analyze import _instance_of, _method_of
        for e in t.effects:
            if e.kind != "STATE" or not isinstance(e.arg, int):
                continue
            tgt = e.receiver if e.receiver and e.receiver != "self" else _instance_of(t.context)
            if tgt != inst:
                continue
            if e.receiver == "self" and _method_of(t.context) == "changeState":
                continue                     # a state advancing itself, not an entry
            # Several routes may kick the machine off at the SAME state; they are
            # ALTERNATIVES, so OR their guards. Keeping only the first-seen guard --
            # what `if e.arg not in seen` did -- is an over-restriction, and the exact
            # opposite of the union this docstring promises. It is also invisible to
            # `control_exits`, which grants every flag and so sees any entry guard as
            # T or U. KQ4 rm79's `h2Actions` kept `Room79:init:1` (guarded by
            # `flag(lolotteAlive)`) and threw away `Room79:init` -- which is
            # UNGUARDED -- so one missed setter collapsing that flag to {0} would have
            # refused both of rm79's trusted exits and invented a dead end on an entry
            # the game does not gate at all. analyze.edge_requirements already gets
            # this right ("several routes to the same K are ALTERNATIVES -> OR them").
            byk.setdefault(e.arg, []).append(t.guard_tree)
    for st in sorted(byk):
        routes = byk[st]
        # An unguarded route makes the whole entry unguarded -- no OR can be stricter
        # than one of its disjuncts being free.
        if any(g is None for g in routes):
            ents.append((st, None))
        elif len(routes) == 1:
            ents.append((st, routes[0]))
        else:
            ents.append((st, GOr(routes)))
    return ents or [(0, None)]




# --------------------------------------------------------------------------
# Reachability over (state, counters)
# --------------------------------------------------------------------------
def run(m: Machine, items, flags, eval_fn):
    """Which rooms can this machine deliver you to, and can it kill you?

    `eval_fn(tree, items, flags, locs) -> True/False/None` is injected so this
    module stays independent of closure's evaluator.
    """
    exits, deaths = set(), set()
    _last = max(m.states, default=-1)
    import itertools
    names = sorted(m.counters)
    combos = [tuple(zip(names, vals))
              for vals in itertools.product(*[sorted(m.inits.get(c, {0})) for c in names])]
    combos = (combos or [()])[:MAX_START_COMBOS]
    start = []
    for (st, guard) in m.entries:
        if guard is not None and eval_fn(guard, items, flags, {}) is False:
            continue                         # provably cannot start it this way
        for combo in combos:
            start.append((st, combo))
    seen, work = set(start), list(start)
    while work:
        st, ctr = work.pop()
        locs = dict(ctr)
        branches = m.states.get(st)
        if branches is None:
            # A state with NO case in the switch IS a pass-through, and this one is
            # real rather than invented: rm78 state 3 sends two actors with `self`, so
            # two cues arrive -- the first lands on the empty state 4, which does
            # nothing, and the second carries on to 5. An absent state cannot park
            # (there is no code to wait on), so falling through is the only reading.
            # Contrast a PRESENT state that arms no cue: that one parks. See below.
            if st + 1 <= _last:
                n = (st + 1, ctr)
                if n not in seen:
                    seen.add(n)
                    work.append(n)
            continue
        for path in branches:
            # Walk the ops IN SOURCE ORDER, so a TEST sees the counter writes that
            # precede it on this path (KQ4 rm78: `(-- jumpNum)` then
            # `(if (== jumpNum -1) ...)` -- the test must see the decrement).
            #
            # Run the WHOLE body before deciding where we go. A state's statements all
            # execute, so precedence is about WHEN each takes effect, not source order:
            #   newRoom / death / changeState act NOW;
            #   `(= seconds N)` / `(= cycles N)` / a `self` cue only ARM a callback.
            # So an immediate transfer preempts an armed cue. rm48 state 14 is exactly
            # this -- `(= cycles 0)` then `(gCurRoom newRoom: 50)` -- and stopping at
            # the first action swallowed the exit.
            nxt, nloc = st, dict(locs)
            exit_to = jump_to = None
            died = armed = pruned = False
            for (kind, arg) in path:
                if kind == "TEST":
                    if eval_fn(arg, items, flags, nloc) is False:
                        pruned = True        # provably-false: this path is not taken
                        break
                elif kind == "STEP":
                    var, d = arg
                    if var in m.counters:
                        lo, hi = m.counters[var]
                        nloc[var] = max(lo, min(nloc.get(var, 0) + d, hi))
                elif kind == "SETVAR":
                    var, val = arg
                    if var in m.counters and isinstance(val, int):
                        lo, hi = m.counters[var]
                        nloc[var] = max(lo, min(val, hi))
                elif kind == "SETSTATE":
                    nxt = arg
                elif kind == "STATEREL":
                    nxt = max(0, nxt + arg)
                elif kind == "JUMP":
                    jump_to = arg
                elif kind == "ADVANCE":
                    armed = True
                elif kind == "EXIT":
                    exit_to = arg
                elif kind == "DEATH":
                    died = True
            if pruned:
                continue
            if exit_to is not None:
                exits.add(exit_to)
                continue                     # the room changed; nothing else matters
            if died:
                deaths.add((st, tuple(sorted(nloc.items()))))
                continue                     # absorbing
            # A state moves on ONLY if it armed a cue. A state that armed nothing
            # PARKS -- rm57 state 1's `observeControl:` is waiting for the player, and
            # it is re-entered through an activator, which we already model as an entry.
            #
            # This used to fall through unconditionally, on the theory that stalling
            # would invent a fake dead end if we misread a cue idiom. That was wrong
            # twice over. `control_exits` ALREADY prevents the fake dead end: a machine
            # we cannot walk simply fails to deliver its exit, and closure falls back to
            # the flat movement edge. The two mechanisms were solving the same problem,
            # and the trust gate does it properly -- so the fall-through bought nothing
            # and cost real guards. A Script's switch is not one chain; it is several
            # segments sharing a switch, one per entry, and walking off the end of one
            # segment into the next INVENTS a transition the engine never makes.
            #
            # rm81 (the glacier) is what this destroyed. Six entries -- 0, 1, 2, 7, 8,
            # 20 -- one per player action, and only entry 8 ("throw sand at the ice") is
            # guarded by `(or (has: Ashes) (has: Sand))`. The exit to rm181 sits at
            # state 19, downstream of 8. Falling through walked entry 0 straight from 0
            # to 19 and out, so the machine handed you the exit having thrown nothing --
            # overriding a flat edge guard that was already correct. Being strict here
            # breaks the chain at state 7 (which arms nothing), the machine declines the
            # exit, and the flat guard wins. That is `rm79->rm80 must hold >=1 of
            # {Sand, Ashes}` -- a real, previously invisible softlock.
            goto = jump_to if jump_to is not None else (nxt + 1 if armed else None)
            if goto is not None and goto <= _last:
                n = (goto, tuple(sorted(nloc.items())))
                if n not in seen:
                    seen.add(n)
                    work.append(n)
    return exits, deaths


class _AllItems:
    """You hold everything."""
    def __contains__(self, _x):
        return True


class _AnyFlags(dict):
    """Every global can hold any value."""
    def get(self, _k, _d=None):
        from closure import ANY
        return {ANY}


def control_exits(m: Machine, eval_fn):
    """Exits reachable using ONLY control flow -- every item/flag condition assumed
    satisfiable, the bounded counters still real.

    This is the machine's own sanity check, and it is what makes the lift safe to
    trust. SCI0 has a long tail of cue idioms; where we fail to model one, a state
    chain breaks and the machine silently swallows an exit that the real game
    hands out freely. So: if a machine cannot deliver an exit even when nothing is
    denied to it, the fault is OURS, not the game's -- and closure falls back to
    the flat movement edge for that exit rather than inventing a dead end.

    The converse is the payload: an exit the machine CAN deliver permissively but
    cannot deliver from the current state is a REAL gate. That is the raft.
    """
    return run(m, _AllItems(), _AnyFlags(), eval_fn)[0]


def all_machines(game):
    """script num -> {instance: Machine}, for every script that has one."""
    return {num: ms for num in game.scripts
            if (ms := machines_of(game, num))}


# --------------------------------------------------------------------------
# Phase 3 -- COMPILE a machine to one guard formula per exit.
#
# A machine is an EXTRACTOR, not a runtime component. It answers "what does it take to
# get from rm138 to rm42?", and that answer does not depend on when you ask -- so ask
# once, here, and hand the fixpoint a formula. Running the machine inside the closure is
# what produced `Machine.project`, the `_mcache`, and the cache key that deleted KQ4's
# rm84 outright.
#
# The method is a TRUTH TABLE over the machine's own atoms, not a weakest precondition.
# WP over a loop is a loop-invariant problem, and the raft IS a loop (3->4->5->6->7->4,
# exit at day>=9). But the counters are bounded and internal, so we can simply enumerate
# the atoms the machine's guards mention and run it per assignment. Measured: rm138 is 8
# atoms -> 256 runs in 0.1s; rm34, the worst machine in either game, is 13 -> 8192 in
# 0.4s. Once.
#
# WHY THIS IS WORTH MORE THAN THE ARCHITECTURE: a truth table assumes NOTHING about
# monotonicity. `closure._atom3` must answer UNKNOWN for `(not (ego has: X))` to keep the
# fixpoint monotone in items, so it can never express "you must NOT be carrying this".
# Enumeration just asks whether an assignment reaches the exit -- and carrying the
# Spinach_Dip is death, so those rows do not satisfy. Measured on rm138: of the 18
# assignments that reach rm42, the dip is held in ZERO. The extracted guard REQUIRES not
# holding it. That is the trap that made the shipped patch break the game, and this is
# the only mechanism we have that can state it.
# --------------------------------------------------------------------------
ATOM_CAP = 16          # 2^16 = 65536 runs; nothing observed above 13


def _guard_atoms(mach):
    """Distinct decidable atoms in a machine's guards, in a stable order.

    LOCAL preds are excluded on purpose: counters are the machine's OWN state, stay
    concrete during the walk, and are not part of the world it is asking about.
    """
    from model import GAnd, GOr, GNot, Pred
    out, seen = [], set()

    def scan(n):
        if isinstance(n, (GAnd, GOr)):
            for k in n.kids:
                scan(k)
        elif isinstance(n, GNot):
            scan(n.kid)
        elif isinstance(n, Pred) and n.kind in ("OWN", "FLAG", "CMP"):
            k = (n.kind, n.var, n.op, str(n.value))
            if k not in seen:
                seen.add(k)
                out.append(n)

    for paths in mach.states.values():
        for path in paths:
            for (kind, arg) in path:
                if kind == "TEST":
                    scan(arg)
    for (_st, gd) in mach.entries:
        scan(gd)
    return out


def _key(p):
    return (p.kind, p.var, p.op, str(p.value))


def compile_exits(mach, local_eval):
    """exit room -> guard tree (or None = unguarded), by enumeration.

    Returns {} if the machine has more atoms than we will enumerate; the caller then
    treats every exit as un-modelled and falls back to the flat movement edge, which is
    the same contract `control_exits` had.
    """
    import itertools
    from model import GAnd, GOr, GNot, Pred

    ats = _guard_atoms(mach)
    if len(ats) > ATOM_CAP:
        return {}
    keys = [_key(p) for p in ats]

    def ev_for(assign):
        def ev(tree, _items, _flags, locs):
            def go(n, neg=False):
                if isinstance(n, GAnd):
                    vs = [go(k, neg) for k in n.kids]
                    return False if any(v is False for v in vs) else True
                if isinstance(n, GOr):
                    vs = [go(k, neg) for k in n.kids]
                    return True if any(v is True for v in vs) else False
                if isinstance(n, GNot):
                    return False if go(n.kid, neg) is True else True
                if isinstance(n, Pred):
                    if n.kind == "LOCAL":
                        return local_eval(n, locs)
                    k = _key(n)
                    if k in assign:
                        return assign[k]
                    return None          # SAID/POS/OPAQUE stay UNKNOWN -> permissive
                return None
            return go(tree)
        return ev

    sat = {}
    for bits in itertools.product((False, True), repeat=len(ats)):
        assign = dict(zip(keys, bits))
        exits, _deaths = run(mach, frozenset(), {}, ev_for(assign))
        for e in exits:
            sat.setdefault(e, []).append(bits)

    out = {}
    for e, rows in sat.items():
        if len(rows) == 2 ** len(ats):
            out[e] = None                        # every assignment delivers it: free
            continue
        # Project onto the atoms that can actually change the answer. rm34 has 13 atoms
        # of which only 4 are relevant -- without this the DNF is the blowup the plan
        # feared, and with it the formula is the size of the real condition.
        rowset = set(rows)
        rel = [i for i in range(len(ats))
               if any(r[:i] + (not r[i],) + r[i + 1:] not in rowset for r in rowset)]
        terms, seen = [], set()
        for r in rows:
            proj = tuple(r[i] for i in rel)
            if proj in seen:
                continue
            seen.add(proj)
            lits = [ats[i] if r[i] else GNot(ats[i]) for i in rel]
            terms.append(lits[0] if len(lits) == 1 else GAnd(lits))
        out[e] = terms[0] if len(terms) == 1 else GOr(terms)
    return out
