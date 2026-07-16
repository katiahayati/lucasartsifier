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
from config import ACTIVE as CFG

SRC_DEFAULT = CFG.src_dir

# selectors we treat as effects / guards
ACQUIRE_SEL, DROP_SEL, OWN_SEL, SCORE_SEL = "get", "put", "has", "changeScore"
ROOM_SELS = {"newRoom", "startRoom"}
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
        if self.kind == "SAID":
            return "Said"
        if self.kind == "POS":
            return f"pos({self.text})"
        return f"opaque({self.text})"


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
    guards: list = field(default_factory=list)       # list[Pred]
    effects: list = field(default_factory=list)       # list[Effect]

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


@dataclass
class Game:
    globals: dict                    # name -> index
    global_inits: dict               # name -> initial value (if any)
    items: dict                      # index -> name
    scripts: dict                    # num -> Script
    name_by_num: dict                # script num -> name (from game.ini)
    item_ids: dict = field(default_factory=dict)   # item-constant name -> number

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
        self.transitions.append(Transition(self.num, context, preds, [eff]))

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
            for clause in form[2:]:
                if isinstance(clause, list) and clause:
                    for b in clause[1:]:
                        self._walk(b, guards, context)
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
                elif sel == SCORE_SEL and isinstance(a0, int):
                    self._emit(Effect("SCORE", arg=a0, receiver=recv), guards, context)
                elif sel in ROOM_SELS and isinstance(a0, int):
                    self._emit(Effect("GOTO", arg=a0, receiver=recv), guards, context)
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
            for sub in form[1:]:
                self._walk(sub, guards, context)
            return

        for sub in form:
            self._walk(sub, guards, context)


def _script_num(forms):
    for f in forms:
        if head_is(f, "script#") and len(f) > 1 and isinstance(f[1], int):
            return f[1]
    return -1


EXIT_DIRS = {"north", "south", "east", "west", "northEast", "northWest",
             "southEast", "southWest"}


def _final_room_int(v):
    """Room number of an exit assignment, following chained `(= north (= east 80))`
    -> 80. None if the value isn't an integer literal (e.g. a computed exit)."""
    while isinstance(v, list) and len(v) >= 3 and head_is(v, "="):
        v = v[2]
    return v if isinstance(v, int) else None


def _extract_nav(forms):
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
        for i, tok in enumerate(form):
            if isinstance(tok, Sym) and i + 1 < len(form) and isinstance(form[i + 1], int) \
                    and form[i + 1] > 0:
                if tok.name == "entranceTo:":
                    doors.append(form[i + 1])
                elif tok.name == "setRegions:":
                    regions.add(form[i + 1])
        for sub in form:
            walk(sub)

    for f in forms:
        # only consider Rm-derived instances for edge props, but doors can be any instance
        walk(f)
    return exits, doors, regions


def load_game(src_dir=SRC_DEFAULT):
    main = read_file(os.path.join(src_dir, "Main.sc"))
    globals_, inits = _parse_globals(main)
    enum_items, item_ids = _parse_item_enum(src_dir)   # EricOakford game.sh enum (KQ4)
    items = enum_items or _parse_items(main)            # else sluicebox Iitem instances (LSL2)
    name_by_num = _parse_game_ini(src_dir)
    game = Game(globals_, inits, items, {}, name_by_num, item_ids)
    for path in sorted(glob.glob(os.path.join(src_dir, "*.sc"))):
        forms = read_file(path)
        num = _script_num(forms)
        base = os.path.splitext(os.path.basename(path))[0]
        sc = Script(num, name_by_num.get(num, base))
        sc.transitions = _Walker(game, num).run(forms)
        sc.exits, sc.doors, sc.regions = _extract_nav(forms)
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
