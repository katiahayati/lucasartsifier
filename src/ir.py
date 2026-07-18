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


def is_global(n, index=None):
    return (n and n["t"] == "Variable" and n["vtype"] == "Global"
            and (index is None or n["index"] == index))


def as_int(n):
    return n["value"] if n and n["t"] == "Number" else None


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
        os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "lsl2_decomp", "lsl2.ir.json")
    ir = load_ir(path)
    print(f"game={ir.game} scripts={len(ir.scripts)} selectors={len(ir.selectors)}")
    print("globals (script 0 locals):", len(ir.script(0).locals))
    print("Script class found:", ir.find_class("Script") is not None)
    print("Actor class found:", ir.find_class("Actor") is not None)
