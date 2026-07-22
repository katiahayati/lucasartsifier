"""Load and query the sci-tools JSON IR (see tools/sci-tools-fork/).

The IR is the typed control-flow AST that sci-tools builds from bytecode, serialized
losslessly. This module is the Python side of the A2 seam: it loads the IR and offers
small helpers to walk the typed AST. Identifiers are bytecode-canonical -- globals and
locals by INDEX, selectors by number (the selector table resolves names).

AST node shape (dict): {"t": <NodeType>, ...typed scalars..., "kids": [child nodes]}.
Child positions mirror sci-tools' AST getters, e.g.:
  If:          kids = [test, then, (else?)]
  Switch:      kids = [head, Case*, (Else?)]     head is `(= state param1)` for changeState
  Case:        kids = [test, body]
  Send:        kids = [receiver, SendMessage*]
  SendMessage: kids = [selectorNode, param*]
  Assignment:  kids = [dest, source]
"""
from __future__ import annotations

import config

import json
import os


class Obj:
    __slots__ = ("name", "is_class", "species", "super", "props", "prop_sel",
                 "methods", "method_sel")

    def __init__(self, d):
        self.name = d["name"]
        self.is_class = d["isClass"]
        self.species = d["species"]
        self.super = d["super"]
        self.props = {p["name"]: p["value"] for p in d["properties"]}
        self.prop_sel = {p["sel"]: p for p in d["properties"]}
        self.methods = {m["name"]: m["ast"] for m in d["methods"]}
        self.method_sel = {m["sel"]: m for m in d["methods"]}

    def __repr__(self):
        return f"Obj({self.name}{'/class' if self.is_class else ''})"


class Script:
    __slots__ = ("number", "locals", "objects", "procs", "by_name")

    def __init__(self, d):
        self.number = d["number"]
        self.locals = d["locals"]                       # [{index, value}] (script 0 = globals)
        self.objects = [Obj(o) for o in d["objects"]]
        self.procs = {p["name"]: p["ast"] for p in d["procedures"]}
        self.by_name = {o.name: o for o in self.objects}

    def __repr__(self):
        return f"Script({self.number}: {[o.name for o in self.objects]})"


class IR:
    def __init__(self, d):
        self.game = d["game"]
        self.selectors = d["selectors"]                 # index -> name
        self.sel_num = {n: i for i, n in enumerate(self.selectors)}
        self.scripts = {s["number"]: Script(s) for s in d["scripts"]}

    def script(self, n):
        return self.scripts.get(n)

    def find_class(self, name):
        for s in self.scripts.values():
            o = s.by_name.get(name)
            if o is not None and o.is_class:
                return o
        return None


def load_ir(path):
    with open(path) as f:
        return IR(json.load(f))


# ---- AST helpers ---------------------------------------------------------
def t(n):
    return n["t"] if n else None


def kids(n):
    return n.get("kids", []) if n else []


def walk(n):
    """Depth-first over a node and all descendants."""
    if n is None:
        return
    yield n
    for k in n.get("kids", ()):
        yield from walk(k)


def sends(n):
    """All Send nodes in the subtree."""
    return (x for x in walk(n) if x["t"] == "Send")


def send_pairs(send):
    """A Send node -> (receiver, [(selector_name, [param nodes]), ...])."""
    ks = send["kids"]
    receiver = ks[0]
    msgs = []
    for m in ks[1:]:
        if m["t"] != "SendMessage":
            continue
        selnode = m["kids"][0]
        selname = selnode.get("name") if selnode["t"] == "Selector" else None
        msgs.append((selname, m["kids"][1:]))
    return receiver, msgs


# ---- SCI's statement forms, named ONCE --------------------------------------
# Four walkers used to each re-derive how a branch composes path conditions -- extract._walk,
# opmodel._hwalk, machine._ops and compile._paths_of, in near-identical code. That is not a
# style problem, it is where three of this project's bugs came from: a node type handled in one
# copy and not another silently drops whatever it contains, and only a game noticing gives it
# away. `Loop` cost us that twice.
#
# So the LANGUAGE knowledge lives here and the walkers keep only their own effect handling, which
# is the part that should differ. Adding a statement form is one line, and every walker gets it.
#
# The other half is that an UNRECOGNISED form must be loud. `KNOWN_NODES` is the full inventory
# over both shipped games; anything outside it makes `control_shape` return ("unknown", t) so a
# third title fails visibly rather than quietly analysing less. See test_walkers.

# LEAF nodes carry no control flow of their own: effects, operands, operators, and the
# no-body jumps. Everything NOT listed here and not handled as control below comes back as
# ("unknown", t) -- LOUD.
#
# The split matters. An earlier cut had one KNOWN_NODES set doing double duty ("we have seen it"
# AND "treat it as a leaf"), which means adding a new CONTROL form to silence an error would
# quietly make its contents vanish. That is exactly what `Loop` did to us twice. Here a control
# form you have not classified cannot be silenced by adding it to a list -- it has to be
# classified.
LEAF_NODES = frozenset({
    # effects
    "Send", "SendMessage", "Assignment", "Increment", "Decrement", "PublicCall", "LocalCall",
    "KernelCall", "AssignmentAdd", "AssignmentSub", "AssignmentXor", "AssignmentBinOr",
    "AssignmentBinAnd",
    # jumps with no contained statements
    "Break", "BreakIf", "Continue", "Return",
    # operands / expressions
    "Number", "String", "Variable", "ComplexVariable", "Property", "Object", "Self", "Super",
    "Selector", "Class", "AddressOf", "Rest", "Said",
    # operators
    "Not", "And", "Or", "Eq", "Ne", "Lt", "Le", "Gt", "Ge", "Ult", "Ule", "Ugt", "Uge",
    "Add", "Sub", "Mul", "Div", "Mod", "Neg", "BinAnd", "BinOr", "BinNot", "Xor", "Shr", "Shl",
})


def control_shape(node):
    """How a node composes CONTROL FLOW. The single place SCI's statement forms are named.

        ("seq",    [kids])                    run in order
        ("branch", [(conds, body), ...])      alternatives; conds is [(test_node, polarity)]
        ("loop",   init, test, incr, body)    kids in SCI's order -- policy is the caller's
        ("leaf",)                             an effect or an operand; the caller decides
        ("unknown", t)                        a form we have never seen: handle it LOUDLY

    A branch arm carries a LIST of conditions rather than one, because `cond` arms run only if
    every prior case failed -- that accumulation used to be re-implemented in every walker.

    `loop` deliberately stays a shape rather than being desugared: a streaming walker wants to
    visit everything inside it, while a path enumerator wants to fan out "runs" and "skipped".
    Those are different POLICIES over the same SHAPE, and only the shape was ever duplicated."""
    if node is None:
        return ("leaf",)
    t = node.get("t")
    ks = node.get("kids") or []
    if t == "List":
        return ("seq", ks)
    if t == "If":
        test = ks[0] if ks else None
        arms = [([(test, True)], ks[1] if len(ks) > 1 else None)]
        arms.append(([(test, False)], ks[2] if len(ks) > 2 else None))
        return ("branch", arms)
    if t == "Cond":
        arms, priors = [], []
        for c in ks:
            ck = c.get("kids") or []
            if c.get("t") == "Case" and ck:
                arms.append((priors + [(ck[0], True)], ck[1] if len(ck) > 1 else None))
                priors = priors + [(ck[0], False)]
            elif c.get("t") == "Else" and ck:
                arms.append((list(priors), ck[0]))
        return ("branch", arms)
    if t == "Switch":
        # switch TESTS are not modelled (the head is `(= state param1)` in the machine idiom and
        # a value match elsewhere); each case body is an unconditional alternative.
        arms = []
        for c in ks[1:]:
            ck = c.get("kids") or []
            if c.get("t") == "Case" and len(ck) > 1:
                arms.append(([], ck[1]))
            elif c.get("t") == "Else" and ck:
                arms.append(([], ck[0]))
        return ("branch", arms)
    if t == "Loop":
        return ("loop", ks[0] if len(ks) > 0 else None, ks[1] if len(ks) > 1 else None,
                ks[2] if len(ks) > 2 else None, ks[3] if len(ks) > 3 else None)
    if t in ("Case", "Else"):
        # normally consumed by their Cond/Switch parent; classified so a direct visit descends
        return ("seq", ks)
    if t in LEAF_NODES:
        return ("leaf",)
    return ("unknown", t)


def is_global(n, index=None):
    return (n and n["t"] == "Variable" and n["vtype"] == "Global"
            and (index is None or n["index"] == index))


def is_local_or_temp(n):
    return n and n.get("t") == "Variable" and n.get("vtype") in ("Local", "Temp")


def as_int(n):
    return n["value"] if n and n["t"] == "Number" else None


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = load_ir(path)
    print(f"game={ir.game} scripts={len(ir.scripts)} selectors={len(ir.selectors)}")
    print("globals (script 0 locals):", len(ir.script(0).locals))
    print("Script class found:", ir.find_class("Script") is not None)
    print("Actor class found:", ir.find_class("Actor") is not None)
