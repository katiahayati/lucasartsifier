"""M1 (normalized IR): turn decompiled Sierra Script into a transition-system IR
with resolved names, typed guard predicates, and effect classification.

Pipeline:  .sc files --sexpr--> forms --model--> Game{globals, items, scripts[
             transitions[ guards:[Pred], effects:[Effect] ]]}

Design choices (per PLAN.md):
  * Parser `Said` specs and positional guards (inRect/onControl/posn/inRect) are
    *lifted away* -- we keep the fact that a handler is said/position gated but
    drop the string, because winnability is gated on item ownership + flags.
  * State = item ownership (bool per item) + global values + current location.
    Room-local script vars are NOT cross-room state (they reset on room reload),
    so SET effects to non-globals are dropped from the winnability IR (kept as
    raw only). Globals = script 0's (Main.sc) `(local ...)` block.
  * changeScore is a heuristic annotation, never a win oracle.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field

from sexpr import read_file, Sym, Str, Said
import config

# NOT `from config import ACTIVE as CFG`. That binds the game AT IMPORT, and callers
# swap `config.ACTIVE` at runtime (config.py's own comment invites it: "Swap this (or
# set it from run.py)"). The stale binding made _check_core's KQ4 leg build its Game
# with LSL2's death_signal -- `game.is_death_write` could never fire, so KQ4 went from
# 56 DEATH effects to 0 and the whole KQ4 half of the suite validated against the wrong
# game's config while printing green. Read through to the live config instead, exactly
# as analyze._LiveCfg already does.


def _cfg():
    return config.ACTIVE


def SRC_DEFAULT():          # noqa: N802  (kept callable so it cannot go stale again)
    return config.ACTIVE.src_dir

# selectors we treat as effects / guards
ACQUIRE_SEL, DROP_SEL, OWN_SEL, SCORE_SEL = "get", "put", "has", "changeScore"
# `(self changeState: K)` selects the next state of a Script state machine. It must
# be a modeled effect: guards are only recorded when they gate an emitted effect, and
# the protective condition for a death usually gates exactly this call (rm16:
# `((ego has: iScarab) (self changeState: 4))`). Without it the guard evaporates and
# every KQ4 death looks unprotected.
STATE_SEL = "changeState"
# `(X setScript: aScript)` STARTS that Script at state 0 -- it is `(aScript
# changeState: 0)` by another name, and it is guarded exactly like one. KQ4's whale:
#     ((Said 'tickle') (if (ego has: iFeather) (ego setScript: tickle) ...))
# so the feather gates the machine's ENTRY, not any of its states. Emitting it as a
# STATE(0) effect keeps the path condition (which _emit snapshots); scanning for the
# symbol instead -- as machine.py first did -- silently drops the guard and makes the
# whale's exit free.
SCRIPT_SEL = "setScript"
ROOM_SELS = {"newRoom", "startRoom"}
# Possession has TWO spellings and they are the same thing. `Actor::has` is defined
# (Actor.sc:608 / KQ4 Actor.sc:1092) as `((gInventory at: X) ownedBy: self)`, and
# `Inventory.sc:28` defines `(method (ownedBy id) (return (== owner id)))`. So:
#
#     (ego has: X)  ==  ((gInventory at: X) ownedBy: ego)  ==  (X.owner == ego)
#
# We recognised only the first spelling and rendered the second OPAQUE, which is why
# a census went looking for `ownedBy` as if it were a separate "possession channel".
# It is the definition. KQ4 rm18 writes possession the second way; LSL2 rm32's Fruit
# check is `((gInventory at: 11) ownedBy: gCurRoomNum)` -- "is it still lying here?".
OWNED_BY_SEL = "ownedBy"
EGO_NAMES = {"ego", "gEgo", "self"}


def _inv_item(expr, game):
    """`(gInventory at: X)` / `(Inventory at: iX)` -> item id, else None."""
    if not (isinstance(expr, list) and len(expr) >= 3 and isinstance(expr[1], Sym)
            and expr[1].sel == "at"):
        return None
    return game.resolve_item(expr[2])
# receivers / calls that are positional or parser gating -> lifted away
POSITIONAL_SELS = {"inRect", "onControl", "observeControl", "ignoreControl",
                   "distanceTo", "obstacles", "edgeHit", "at", "cantBeHere"}


def is_sym(x, name=None):
    return isinstance(x, Sym) and (name is None or x.name == name)


def head_is(form, name):
    return isinstance(form, list) and form and is_sym(form[0], name)


# --------------------------------------------------------------------------
# Typed predicates (normalized guards)
# --------------------------------------------------------------------------
@dataclass
class Pred:
    kind: str            # OWN | FLAG | CMP | SAID | POS | OPAQUE
    var: object = None   # item id (OWN) or global name (FLAG/CMP)
    op: str = ""         # comparison op for CMP; "" otherwise
    value: object = None # comparison value
    want: bool = True    # OWN/FLAG polarity (False = negated)
    text: str = ""       # printable fallback for OPAQUE

    def __repr__(self):
        if self.kind == "OWN":
            return f"{'' if self.want else '¬'}own({self.var})"
        if self.kind == "FLAG":
            return f"{'' if self.want else '¬'}flag({self.var})"
        if self.kind == "CMP":
            return f"{self.var}{self.op}{self.value}"
        if self.kind == "LOCAL":
            return f"local:{self.var}{self.op}{self.value}"
        if self.kind == "SAID":
            return "Said"
        if self.kind == "POS":
            return f"pos({self.text})"
        if self.kind == "OPAQUE":
            return f"opaque({self.text})"
        return f"{self.kind}({self.var}{self.op}{self.value})"   # never lie about a kind
        # ^ this used to fall through to `opaque(...)` for ANY unrecognized kind, so a
        #   LOCAL pred printed as `opaque()` -- i.e. as the one thing it is NOT. Cost an
        #   hour of chasing a "guard that evaluates False but reads as unknown".


# --------------------------------------------------------------------------
# Guard TREES. A guard is a boolean expression; the flat `guards` list below is a
# CONJUNCTION and cannot represent `or` -- it emits OPAQUE("or") and drops the
# disjuncts. That silently deletes real conditions: the LSL2 raft's day-3 check is
# `(or (== gWearingSunscreen 1) (== gWearingSunscreen 3))`, so the sunscreen simply
# vanishes and a solver concludes you can win without it. Same root cause as the
# glacier needing Sand OR Ashes. Trees keep the structure; `closure.eval3`
# evaluates them with 3-valued logic (unknown stays unknown, so we only ever block
# on a PROVABLY false guard).
# --------------------------------------------------------------------------
@dataclass
class GAnd:
    kids: list


@dataclass
class GOr:
    kids: list


@dataclass
class GNot:
    kid: object


@dataclass
class Effect:
    kind: str            # ACQUIRE | DROP | SCORE | GOTO | SET
    arg: object = None   # item id / room id / delta / global name
    value: object = None # SET value
    receiver: str = ""

    def __repr__(self):
        if self.kind in ("ACQUIRE", "DROP"):
            return f"{self.kind.lower()}(item {self.arg})"
        if self.kind == "GOTO":
            return f"goto(rm{self.arg})"
        if self.kind == "SCORE":
            return f"score(+{self.arg})"
        if self.kind == "SET":
            return f"set({self.arg}={self.value})"
        return f"{self.kind}({self.arg})"


@dataclass
class Transition:
    script: int
    context: str
    guards: list = field(default_factory=list)       # list[Pred] -- flat CONJUNCTION
    effects: list = field(default_factory=list)       # list[Effect]
    guard_tree: object = None    # GAnd/GOr/GNot/Pred -- the real boolean structure.
                                 # `guards` above cannot express `or` and silently
                                 # drops the disjuncts; keep both while the fixpoint
                                 # migration is in flight.

    @property
    def said_gated(self):
        return any(p.kind == "SAID" for p in self.guards)

    @property
    def state_guards(self):
        """Winnability-relevant guards only (OWN/FLAG/CMP)."""
        return [p for p in self.guards if p.kind in ("OWN", "FLAG", "CMP")]


@dataclass
class Script:
    num: int
    name: str
    transitions: list = field(default_factory=list)
    exits: dict = field(default_factory=dict)     # direction -> dest room (Rm edge props)
    doors: list = field(default_factory=list)      # entranceTo: dest rooms (Door edges)
    regions: set = field(default_factory=set)      # setRegions: N this room attaches to
    forms: list = field(default_factory=list)      # the parsed s-exprs, retained for
                                                   # machine.py: the transition list is a
                                                   # flat set of (guards -> one effect) and
                                                   # cannot express a state machine's
                                                   # control flow (the ORDER of actions on
                                                   # a path, and the `= seconds` cue that
                                                   # advances it). Intra-room progression
                                                   # needs the tree, so keep it.


@dataclass
class Game:
    globals: dict                    # name -> index
    global_inits: dict               # name -> initial value (if any)
    items: dict                      # index -> name
    scripts: dict                    # num -> Script
    name_by_num: dict                # script num -> name (from game.ini)
    item_ids: dict = field(default_factory=dict)   # item-constant name -> number
    death_signal: tuple = ()         # (global, value) whose write means death

    def item_name(self, i):
        return self.items.get(i, f"item{i}")

    def is_global(self, name):
        return name in self.globals

    def resolve_item(self, a0):
        """Item reference -> number. Accepts a raw int (sluicebox `has: 3`) or an
        item-constant Sym (EricOakford `has: iMagicHen`, resolved via game.sh)."""
        if isinstance(a0, int):
            return a0
        if isinstance(a0, Sym) and a0.name in self.item_ids:
            return self.item_ids[a0.name]
        return None

    def is_death_write(self, gname, value):
        """Does writing `value` to global `gname` mean DEATH? Per-game, from
        config.death_signal -- e.g. ("gCurrentStatus", 1001) / ("dead", "TRUE").
        Compares the _short()-rendered value so ints and Syms both work."""
        if not self.death_signal or gname != self.death_signal[0]:
            return False
        return str(value).strip() == str(self.death_signal[1]).strip()


# --------------------------------------------------------------------------
# Name resolution from Main.sc
# --------------------------------------------------------------------------
def _parse_globals(main_forms):
    """script 0's (local ...) block: names in index order, with = initializers."""
    for f in main_forms:
        if head_is(f, "local"):
            names, inits, idx = {}, {}, 0
            toks = f[1:]
            i = 0
            while i < len(toks):
                t = toks[i]
                if isinstance(t, Sym):
                    name = t.name
                    if i + 1 < len(toks) and is_sym(toks[i + 1], "="):
                        inits[name] = toks[i + 2]
                        i += 3
                    else:
                        i += 1
                    names[name] = idx
                    idx += 1
                else:
                    i += 1  # stray (shouldn't happen)
            return names, inits
    return {}, {}


def _parse_items(main_forms):
    """ordered (instance NAME of Iitem ...) -> index -> name."""
    items, idx = {}, 0
    for f in main_forms:
        if head_is(f, "instance") and len(f) >= 4 and is_sym(f[2], "of") and is_sym(f[3], "Iitem"):
            items[idx] = f[1].name
            idx += 1
    return items


def _parse_item_enum(src_dir):
    """EricOakford dialect: game.sh declares the inventory as an enum `iName ;N`.
    Returns ({num: name}, {name: num}); empty dicts if there is no such enum. This
    is how KQ4 (and LSL2's EricOakford tree) number items -- guards then reference
    the named constant, e.g. `(ego has: iMagicHen)`, not a raw integer."""
    import re
    items, name2num = {}, {}
    gsh = os.path.join(src_dir, "game.sh")
    if os.path.exists(gsh):
        for name, num in re.findall(r"(i[A-Za-z0-9_]+)\s*;\s*(\d+)",
                                    open(gsh, encoding="latin-1").read()):
            items[int(num)] = name
            name2num[name] = int(num)
    return items, name2num


def _parse_game_ini(src_dir):
    names = {}
    ini = os.path.join(src_dir, "..", "game.ini")
    if os.path.exists(ini):
        for line in open(ini, encoding="latin-1"):
            line = line.strip()
            if line.startswith("n") and "=" in line:
                k, v = line.split("=", 1)
                try:
                    names[int(k[1:])] = v.strip()
                except ValueError:
                    pass
    return names


# --------------------------------------------------------------------------
# Guard normalization
# --------------------------------------------------------------------------
def _norm_guard(expr, game, want=True, out=None):
    """Flatten a guard expression into a conjunction of typed Preds (best effort).

    `and` -> conjunction; `not` flips polarity; `or`/comparisons handled;
    Said/positional recognized and marked; everything else -> OPAQUE.
    """
    if out is None:
        out = []
    # bare symbol test: `gFoo` truthy
    if isinstance(expr, Sym):
        if game.is_global(expr.name):
            out.append(Pred("FLAG", var=expr.name, want=want))
        else:
            out.append(Pred("OPAQUE", text=expr.name, want=want))
        return out
    if isinstance(expr, (int, Str, Said)):
        if isinstance(expr, Said):
            out.append(Pred("SAID"))
        return out
    if not isinstance(expr, list) or not expr:
        return out
    head = expr[0]

    if is_sym(head, "not") and len(expr) == 2:
        return _norm_guard(expr[1], game, want=not want, out=out)
    if is_sym(head, "and"):
        for sub in expr[1:]:
            _norm_guard(sub, game, want=want, out=out)
        return out
    if is_sym(head, "or"):
        # keep OWN/FLAG atoms it mentions (as a disjunction marker) but don't
        # treat them as hard conjuncts; record an OPAQUE-or plus atoms for slicing
        atoms = []
        for sub in expr[1:]:
            _norm_guard(sub, game, want=want, out=atoms)
        out.append(Pred("OPAQUE", text="or", want=want))
        # keep referenced vars so the COI slice still sees them (as soft refs)
        for a in atoms:
            if a.kind in ("OWN", "FLAG"):
                a2 = Pred(a.kind, var=a.var, op=a.op, value=a.value, want=a.want)
                a2.text = "or-branch"
                out.append(a2)
        return out
    if is_sym(head, "Said"):
        out.append(Pred("SAID"))
        return out

    # message send: (RECV sel: args)
    if len(expr) >= 2 and isinstance(expr[1], Sym) and expr[1].is_selector():
        sel = expr[1].sel
        a0 = expr[2] if len(expr) >= 3 else None
        if sel == OWN_SEL:
            iid = game.resolve_item(a0)
            if iid is not None:
                out.append(Pred("OWN", var=iid, want=want))
                return out
        if sel in POSITIONAL_SELS:
            out.append(Pred("POS", text=sel))
            return out
        out.append(Pred("OPAQUE", text=f"{_short(expr[0])}.{sel}", want=want))
        return out

    # comparison: (== G v) (> G v) (< G v) (>= ..) (<= ..) (!= ..)
    if isinstance(head, Sym) and head.name in ("==", "!=", "<", ">", "<=", ">=", "u<", "u>"):
        if len(expr) >= 3 and isinstance(expr[1], Sym) and game.is_global(expr[1].name):
            op = head.name
            if not want:
                op = {"==": "!=", "!=": "==", "<": ">=", ">": "<=", "<=": ">", ">=": "<"}.get(op, op)
            out.append(Pred("CMP", var=expr[1].name, op=op, value=_short(expr[2])))
            return out
    # bitfield test (& X mask) -> positional/flags; mark opaque
    if is_sym(head, "&") or is_sym(head, "bit-and"):
        out.append(Pred("POS", text="bittest"))
        return out

    out.append(Pred("OPAQUE", text=_short(expr), want=want))
    return out


def _short(x):
    if isinstance(x, Said):
        return "Said"
    if isinstance(x, Str):
        return "<str>"
    if isinstance(x, Sym):
        return x.name
    if isinstance(x, int):
        return str(x)
    if isinstance(x, list):
        return "(" + " ".join(_short(e) for e in x) + ")"
    return repr(x)


# --------------------------------------------------------------------------
# Effect + transition extraction (guard-aware walk)
# --------------------------------------------------------------------------
class _Walker:
    def __init__(self, game, script_num):
        self.game = game
        self.num = script_num
        self.transitions = []

    def run(self, forms):
        for f in forms:
            self._walk(f, [], "<top>")
        return self.transitions

    def _emit(self, eff, guards, context):
        preds = []
        for g in guards:
            _norm_guard(g, self.game, out=preds)
        tree = GAnd([norm_tree(g, self.game) for g in guards]) if guards else GAnd([])
        self.transitions.append(Transition(self.num, context, preds, [eff], tree))

    def _walk(self, form, guards, context):
        if not isinstance(form, list) or not form:
            return
        head = form[0]
        if is_sym(head, "instance") or is_sym(head, "class"):
            name = form[1].name if len(form) > 1 and isinstance(form[1], Sym) else "?"
            for sub in form[2:]:
                self._walk(sub, guards, name)
            return
        if is_sym(head, "method"):
            sig = form[1]
            mname = sig[0].name if isinstance(sig, list) and sig and isinstance(sig[0], Sym) else "?"
            for sub in form[2:]:
                self._walk(sub, guards, f"{context}:{mname}")
            return
        if is_sym(head, "if") and len(form) >= 2:
            test, body = form[1], form[2:]
            then_b, else_b, seen = [], [], False
            for b in body:
                if is_sym(b, "else"):
                    seen = True
                    continue
                (else_b if seen else then_b).append(b)
            for b in then_b:
                self._walk(b, guards + [test], context)
            for b in else_b:
                self._walk(b, guards + [[Sym("not"), test]], context)
            return
        if is_sym(head, "cond"):
            prior_neg = []
            for clause in form[1:]:
                if isinstance(clause, list) and clause:
                    test = clause[0]
                    if is_sym(test, "else"):
                        g = guards + prior_neg
                    else:
                        g = guards + prior_neg + [test]
                    for b in clause[1:]:
                        self._walk(b, g, context)
                    if not is_sym(test, "else"):
                        prior_neg = prior_neg + [[Sym("not"), test]]
            return
        if is_sym(head, "while") and len(form) >= 2:
            for b in form[2:]:
                self._walk(b, guards + [form[1]], context)
            return
        if is_sym(head, "switch") or is_sym(head, "switchto"):
            # Record the case value in the context -> `rm57Script:changeState:7`.
            # A Script's states ARE its state machine, and we need to know which
            # state a GOTO lives in to tell which trigger leads to it (rm57Script
            # has many `(self changeState: K)` triggers; only one reaches state 7).
            seq = 0
            for clause in form[2:]:
                if isinstance(clause, list) and clause:
                    if isinstance(clause[0], int):
                        st = clause[0]
                    elif is_sym(clause[0], "else"):
                        st = None
                    else:
                        st = seq              # switchto: implicit sequential cases
                    seq += 1
                    ctx = context if st is None else f"{context}:{st}"
                    for b in clause[1:]:
                        self._walk(b, guards, ctx)
            return

        # message send?
        if len(form) >= 2 and isinstance(form[1], Sym) and form[1].is_selector():
            recv = _short(form[0])
            # split into (sel,args) groups
            groups, cur, args = [], None, []
            for tok in form[1:]:
                if isinstance(tok, Sym) and tok.is_selector():
                    if cur is not None:
                        groups.append((cur, args))
                    cur, args = tok.sel, []
                else:
                    args.append(tok)
            if cur is not None:
                groups.append((cur, args))
            for sel, a in groups:
                a0 = a[0] if a else None
                iid = self.game.resolve_item(a0)
                if sel == ACQUIRE_SEL and iid is not None:
                    self._emit(Effect("ACQUIRE", arg=iid, receiver=recv), guards, context)
                elif sel == DROP_SEL and iid is not None:
                    self._emit(Effect("DROP", arg=iid, receiver=recv), guards, context)
                elif sel == STATE_SEL and isinstance(a0, int):
                    self._emit(Effect("STATE", arg=a0, receiver=recv), guards, context)
                elif sel == SCRIPT_SEL and isinstance(a0, Sym):
                    # start that machine at state 0, carrying this path condition
                    self._emit(Effect("STATE", arg=0, receiver=a0.name), guards, context)
                elif sel == SCORE_SEL and isinstance(a0, int):
                    self._emit(Effect("SCORE", arg=a0, receiver=recv), guards, context)
                elif sel in ROOM_SELS and isinstance(a0, int):
                    self._emit(Effect("GOTO", arg=a0, receiver=recv), guards, context)
                elif sel in ROOM_SELS and isinstance(a0, Sym) \
                        and self.game.is_global(a0.name):
                    # A DYNAMIC exit: `(gCurRoom newRoom: gRmAfter40)`. The
                    # destination is data, not a literal, so it used to vanish --
                    # and rm43 (the Knife) has NO other way in, which silently made
                    # the whole LSL2 island unreachable. Emit it symbolically;
                    # movement_graph resolves the global to the rooms it can hold.
                    self._emit(Effect("GOTO", arg=a0.name, receiver=recv), guards, context)
                for x in a:
                    self._walk(x, guards, context)
            self._walk(form[0], guards, context)
            return

        # assignment to a global -> SET effect (locals dropped from IR)
        if isinstance(head, Sym) and head.name in ("=", "+=", "-=", "++", "--") and len(form) >= 2:
            tgt = form[1]
            if isinstance(tgt, Sym) and self.game.is_global(tgt.name):
                val = _short(form[2]) if len(form) >= 3 else head.name
                self._emit(Effect("SET", arg=tgt.name, value=val, receiver=head.name), guards, context)
                # Death is just a global write in both games (LSL2 gCurrentStatus=1001,
                # KQ4 dead=TRUE), raised from Main's doit -- never a terminal room. Emit
                # it as a first-class effect too; _emit snapshots the path condition, so
                # each death arrives with the guards that lead to it.
                if self.game.is_death_write(tgt.name, val):
                    self._emit(Effect("DEATH", arg=tgt.name, value=val, receiver=head.name),
                               guards, context)
            for sub in form[1:]:
                self._walk(sub, guards, context)
            return

        for sub in form:
            self._walk(sub, guards, context)


def _parse_script_consts(src_dir):
    """game.sh constants, for resolving a symbolic `(script# SWAMP)`. The header
    declares both `(define NAME N)` and enum members annotated `NAME ;N` (the same
    shape as the item enum). Returns {name: int}; empty if there is no game.sh."""
    import re
    consts = {}
    gsh = os.path.join(src_dir, "game.sh")
    if os.path.exists(gsh):
        txt = open(gsh, encoding="latin-1").read()
        for name, num in re.findall(r"\(define\s+([A-Za-z_][A-Za-z0-9_]*)\s+(-?\d+)\s*\)", txt):
            consts[name] = int(num)
        for name, num in re.findall(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*;\s*(\d+)\s*$", txt, re.M):
            consts.setdefault(name, int(num))
    return consts


def norm_tree(expr, game, locals_=()):
    """Normalize a guard expression into a TREE (GAnd/GOr/GNot/Pred), preserving
    the boolean structure that `_norm_guard` flattens away. Atoms it cannot
    interpret become Pred("OPAQUE"/"SAID"/"POS"), which `closure.eval3` reads as
    UNKNOWN rather than True -- so a negated unknown stays unknown instead of
    flipping to a false 'this is blocked'.

    `locals_` names the script-locals that machine.py models as bounded counters.
    Inside a state machine those are real state -- `(== day 3)` in the LSL2 raft is
    the whole reason the sunscreen matters -- so they become LOCAL preds that
    `closure.eval3` evaluates concretely instead of OPAQUE ones it must treat as
    UNKNOWN. Outside a machine `locals_` is empty and nothing changes.
    """
    if isinstance(expr, Sym):
        if expr.name in locals_:
            return Pred("LOCAL", var=expr.name, op="!=", value=0)
        if game.is_global(expr.name):
            return Pred("FLAG", var=expr.name, want=True)
        return Pred("OPAQUE", text=expr.name)
    if isinstance(expr, Said):
        return Pred("SAID")
    if isinstance(expr, (int, Str)):
        return Pred("OPAQUE", text=str(expr))
    if not isinstance(expr, list) or not expr:
        return Pred("OPAQUE", text="?")
    head = expr[0]

    if is_sym(head, "not") and len(expr) == 2:
        return GNot(norm_tree(expr[1], game, locals_))
    if is_sym(head, "and"):
        return GAnd([norm_tree(s, game, locals_) for s in expr[1:]])
    if is_sym(head, "or"):
        return GOr([norm_tree(s, game, locals_) for s in expr[1:]])
    if is_sym(head, "Said"):
        return Pred("SAID")

    if len(expr) >= 2 and isinstance(expr[1], Sym) and expr[1].is_selector():
        sel = expr[1].sel
        a0 = expr[2] if len(expr) >= 3 else None
        if sel == OWN_SEL:
            iid = game.resolve_item(a0)
            if iid is not None:
                return Pred("OWN", var=iid, want=True)
        if sel == OWNED_BY_SEL:
            # `((gInventory at: X) ownedBy: ego)` -- possession, the other spelling.
            iid = _inv_item(expr[0], game)
            if iid is not None and is_sym(a0) and a0.name in EGO_NAMES:
                return Pred("OWN", var=iid, want=True)
            # `ownedBy: <somewhere else>` asks where the item IS, not whether you hold
            # it -- that needs the per-item `owner` register (PLAN-v2 phase 4), so stay
            # honest and leave it unread rather than pretend it is a possession test.
        if sel in POSITIONAL_SELS:
            return Pred("POS", text=sel)
        return Pred("OPAQUE", text=f"{_short(expr[0])}.{sel}")

    if isinstance(head, Sym) and head.name in ("==", "!=", "<", ">", "<=", ">=", "u<", "u>"):
        if len(expr) >= 3 and isinstance(expr[1], Sym) and isinstance(expr[2], int) \
                and expr[1].name in locals_:
            return Pred("LOCAL", var=expr[1].name, op=head.name, value=expr[2])
        if len(expr) >= 3 and isinstance(expr[1], Sym) and game.is_global(expr[1].name):
            return Pred("CMP", var=expr[1].name, op=head.name, value=_short(expr[2]))
    if is_sym(head, "&") or is_sym(head, "bit-and"):
        return Pred("POS", text="bittest")
    return Pred("OPAQUE", text=_short(expr))


def _script_num(forms, consts=None):
    """Script number. EricOakford writes `(script# SWAMP)` using a game.sh constant;
    without resolving it every such script collapses to -1 and they silently
    overwrite each other in game.scripts (34 of them in KQ4, incl. every region
    script). sluicebox always writes an integer, so this is a no-op there."""
    for f in forms:
        if head_is(f, "script#") and len(f) > 1:
            v = f[1]
            if isinstance(v, int):
                return v
            if isinstance(v, Sym) and consts and v.name in consts:
                return consts[v.name]
    return -1


EXIT_DIRS = {"north", "south", "east", "west", "northEast", "northWest",
             "southEast", "southWest"}


def _final_room_int(v):
    """Room number of an exit assignment, following chained `(= north (= east 80))`
    -> 80. None if the value isn't an integer literal (e.g. a computed exit)."""
    while isinstance(v, list) and len(v) >= 3 and head_is(v, "="):
        v = v[2]
    return v if isinstance(v, int) else None


def _const_int(v, consts):
    """An int literal, or a game.sh constant resolved to one. KQ4 writes
    `setRegions: GENESTA`; LSL2 writes `setRegions: 200`. Without resolving the
    symbolic form, KQ4's regions are never attached -- which makes every region
    script look like global code and its effects available from anywhere (the
    peacock feather could then be picked up from inside the whale)."""
    if isinstance(v, int):
        return v
    if isinstance(v, Sym) and consts:
        return consts.get(v.name)
    return None


def _extract_nav(forms, consts=None):
    """Room navigation edges: Rm-instance edge properties (north/south/east/west
    -> dest room) and Door `entranceTo:` targets. These are how SCI0 encodes
    walk-off-the-edge and through-door movement -- they are NOT `newRoom` calls,
    so the effect walker misses them."""
    exits, doors, regions = {}, [], set()

    def scan_props(prop_form):
        # (properties k1 v1 k2 v2 ...) -> capture exit dirs with room-number values
        toks = prop_form[1:]
        i = 0
        while i + 1 < len(toks):
            k, v = toks[i], toks[i + 1]
            if isinstance(k, Sym) and k.name in EXIT_DIRS and isinstance(v, int) and v > 0:
                exits[k.name] = v
            if isinstance(k, Sym) and k.name == "entranceTo" and isinstance(v, int) and v > 0:
                doors.append(v)
            i += 2

    def walk(form):
        if not isinstance(form, list) or not form:
            return
        if head_is(form, "properties"):
            scan_props(form)
        # exits set in CODE (EricOakford/KQ4 idiom): (= north 80), (= south 30),
        # including chained (= north (= east 80)). LSL2 declares these in the
        # properties block instead; capture both dialects.
        if head_is(form, "=") and len(form) >= 3 and isinstance(form[1], Sym) \
                and form[1].name in EXIT_DIRS:
            v = _final_room_int(form[2])
            if v and v > 0:
                exits[form[1].name] = v
        # message-send forms:  ... entranceTo: 118 ... / ... setRegions: 200 ...
        # (KQ4 writes these as game.sh constants: `setRegions: GENESTA`)
        for i, tok in enumerate(form):
            if isinstance(tok, Sym) and i + 1 < len(form):
                val = _const_int(form[i + 1], consts)
                if not val or val <= 0:
                    continue
                if tok.name == "entranceTo:":
                    doors.append(val)
                elif tok.name == "setRegions:":
                    regions.add(val)
        for sub in form:
            walk(sub)

    for f in forms:
        # only consider Rm-derived instances for edge props, but doors can be any instance
        walk(f)
    return exits, doors, regions


def load_game(src_dir=None):
    # resolve the game at CALL time, never at import -- see the note by `import config`
    cfg = _cfg()
    src_dir = cfg.src_dir if src_dir is None else src_dir
    main = read_file(os.path.join(src_dir, "Main.sc"))
    globals_, inits = _parse_globals(main)
    enum_items, item_ids = _parse_item_enum(src_dir)   # EricOakford game.sh enum (KQ4)
    items = enum_items or _parse_items(main)            # else sluicebox Iitem instances (LSL2)
    name_by_num = _parse_game_ini(src_dir)
    game = Game(globals_, inits, items, {}, name_by_num, item_ids, cfg.death_signal)
    consts = _parse_script_consts(src_dir)
    unresolved = -1          # unique synthetic keys, so unnumbered scripts (the SCI
                             # class library, whose constants live in SCICompanion's
                             # includes) don't all collapse onto -1 and overwrite
                             # each other. They carry no rooms, so they stay inert.
    for path in sorted(glob.glob(os.path.join(src_dir, "*.sc"))):
        forms = read_file(path)
        num = _script_num(forms, consts)
        if num == -1:
            num, unresolved = unresolved, unresolved - 1
        base = os.path.splitext(os.path.basename(path))[0]
        sc = Script(num, name_by_num.get(num, base))
        sc.transitions = _Walker(game, num).run(forms)
        sc.exits, sc.doors, sc.regions = _extract_nav(forms, consts)
        sc.forms = forms
        game.scripts[num] = sc
    return game


if __name__ == "__main__":
    g = load_game()
    n_tr = sum(len(s.transitions) for s in g.scripts.values())
    print(f"globals: {len(g.globals)}   items: {len(g.items)}   scripts: {len(g.scripts)}   transitions: {n_tr}")
    kinds = {}
    for s in g.scripts.values():
        for t in s.transitions:
            for e in t.effects:
                kinds[e.kind] = kinds.get(e.kind, 0) + 1
    print("effect kinds:", kinds)
