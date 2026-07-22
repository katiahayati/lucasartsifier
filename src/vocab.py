"""DERIVE the game's own vocabulary for an abstract store, instead of cataloguing spellings.

SPIKE -- proven on both games, NOT yet wired into extraction. See TODO section A.

The problem this answers: we had accumulated four hand-written recognisers for what turned out to
be one operation. `gEgo get:`, `gEgo put:`, `(Inv at: N) moveTo:` and a raw `owner:` write are not
four idioms; they are one property write reached through wrappers the game itself defines --

    (class InvI of Obj                              ; Inventory.sc, engine class library
      (properties ... owner 0 loop 0 cel 0 ...)
      (method (ownedBy param1) (return (== owner param1)))      ; READ  the location
      (method (moveTo param1)  (= owner param1) (return self)))  ; WRITE the location

    (class Ego of Act                               ; Actor.sc
      (method (get param1 ...)   ((global9 at: [param1 temp0]) moveTo: self))
      (method (put param1 param2) (if (self has: param1) ((global9 at: param1) moveTo: ...)))
      (method (has param1 &tmp temp0) (if (= temp0 (global9 at: param1)) (temp0 ownedBy: self))))

Adding a recogniser per discovery is fitting-shaped: it works for the game in front of you and
tells you nothing about the next one. The game already contains the answer -- its class table
says which selector writes the store and which reads it -- so read that instead of guessing.

Run standalone to see what it derives:  python3 vocab.py
"""
from __future__ import annotations

import ir as I


def _nparams(body):
    """How many parameters a method body reads -- the highest Parameter index it mentions."""
    hi = 0
    for n in I.walk(body):
        if isinstance(n, dict) and n.get("vtype") == "Parameter":
            hi = max(hi, n.get("index", 0))
    return hi


def _prop_name(node):
    return node.get("name") if isinstance(node, dict) and node.get("t") == "Property" else None


def find_stores(ir):
    """Classes with a property that behaves like a LOCATION: written from a parameter by one
    method, compared against a parameter by another.

    That pair is what distinguishes a location from a counter or a flag -- you can put a thing
    somewhere, and you can ask whether it is there. No selector or property name is assumed;
    both games independently yield (InvI, owner, moveTo, ownedBy)."""
    out = []
    for s in ir.scripts.values():
        for o in s.objects:
            if not o.is_class:
                continue
            written, compared = {}, {}
            for mname, body in o.methods.items():
                for n in I.walk(body):
                    t = n.get("t")
                    ks = n.get("kids") or []
                    if t == "Assignment" and len(ks) >= 2:
                        p = _prop_name(ks[0])
                        if p and isinstance(ks[1], dict) and ks[1].get("vtype") == "Parameter":
                            written.setdefault(p, set()).add(mname)
                    elif t in ("Eq", "Ne") and len(ks) >= 2:
                        params = any(isinstance(k, dict) and k.get("vtype") == "Parameter"
                                     for k in ks[:2])
                        for k in ks[:2]:
                            p = _prop_name(k)
                            if p and params:
                                compared.setdefault(p, set()).add(mname)
            for p in set(written) & set(compared):
                out.append({"class": o.name, "script": s.number, "prop": p,
                            "writers": sorted(written[p]), "readers": sorted(compared[p])})
    return out


def find_wrappers(ir, store):
    """The game's own convenience spellings: methods that forward to a store selector.

    Two discriminators, both taken from the class definitions rather than from us:

      * RECEIVER -- a class sending the selector to `self` is using its own method of that name.
        `moveTo:` is also Window's screen-position selector, so Dialog::center and Dialog::setSize
        forward to "moveTo" without meaning anything of the kind.
      * ARITY -- the store's `moveTo:` takes one argument (a destination); Window's takes two
        (x, y). Gauge::init and SRDialog::init are excluded by this and not by the receiver test,
        since they send to a sub-object rather than to self.

    Those are exactly the two exclusions the hand-written recogniser made by eye."""
    core = set(store["writers"]) | set(store["readers"])
    cls = ir.find_class(store["class"])
    arity = {m["name"]: _nparams(m["ast"]) for m in cls.method_sel.values()
             if m["name"] in core} if cls else {}
    out, seen = [], set()
    for s in ir.scripts.values():
        for o in s.objects:
            if not o.is_class:
                continue
            for mname, body in o.methods.items():
                if mname in core:
                    continue
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    try:
                        recv, msgs = I.send_pairs(n)
                    except Exception:                      # noqa: BLE001 -- malformed send
                        continue
                    for pair in msgs:
                        if not pair or pair[0] not in core:
                            continue
                        if recv.get("t") == "Self" and o.name != store["class"]:
                            continue
                        want = arity.get(pair[0])
                        if want is not None and len(pair[1]) != want:
                            continue
                        key = (o.name, mname, pair[0])
                        if key not in seen:
                            seen.add(key)
                            out.append({"class": o.name, "selector": mname,
                                        "forwards_to": pair[0],
                                        "kind": "write" if pair[0] in store["writers"] else "read"})
    return out


def derive(ir):
    """{store, wrappers} for every location-like store the game defines."""
    return [{"store": st, "wrappers": find_wrappers(ir, st)} for st in find_stores(ir)]


if __name__ == "__main__":
    import config
    for cfg in (config.LSL2, config.KQ4):
        print("=" * 68)
        print(cfg.name.split(":")[0])
        for d in derive(I.load_ir(cfg.ir_path)):
            st = d["store"]
            print(f"  STORE  class {st['class']} . {st['prop']}"
                  f"   write via {st['writers']}   read via {st['readers']}")
            for w in d["wrappers"]:
                print(f"    {w['kind']:5s}  {w['class']}::{w['selector']} -> {w['forwards_to']}")
