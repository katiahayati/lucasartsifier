"""DERIVE the game's own vocabulary for an abstract store, instead of cataloguing spellings.

Now WIRED IN (commit below). See TODO A0.

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


# ---- the derived table, in the form extraction needs ---------------------
EGO = "ego"          # destination sentinel: the item is HELD (shared with extract2)


def _arg_roles(ir, wrapper_cls, selector, core):
    """Where the ITEM and the DESTINATION live in a wrapper's own argument list.

    Read off the forwarding send. `Ego::put param1 param2` forwards as
    `((global9 at: param1) moveTo: <param2 or -1>)`, so the item is argument 1 and the
    destination argument 2; `Ego::get param1` forwards as `(... moveTo: self)`, so the
    destination is the ego itself and there is no destination argument at all."""
    cls = ir.find_class(wrapper_cls)
    body = cls.methods.get(selector) if cls else None
    if body is None:
        return None
    for n in I.walk(body):
        if n.get("t") != "Send":
            continue
        try:
            recv, msgs = I.send_pairs(n)
        except Exception:                              # noqa: BLE001
            continue
        for pair in msgs:
            if not pair or pair[0] not in core:
                continue
            item_arg = None
            for k in I.walk(recv):                     # `(<inv> at: <Parameter i>)`
                if isinstance(k, dict) and k.get("vtype") == "Parameter":
                    item_arg = k.get("index")
                    break
            dest_arg, dest_fixed = None, None
            for p in pair[1]:
                if not isinstance(p, dict):
                    continue
                if p.get("t") == "Self":
                    dest_fixed = EGO
                elif p.get("vtype") == "Parameter":
                    dest_arg = p.get("index")
                else:
                    # `(if (== argc 1) -1 else param2)` -- SCI passes the argument COUNT as
                    # parameter 0, so skip it; a real destination is parameter 1 or later.
                    for k in I.walk(p):
                        if (isinstance(k, dict) and k.get("vtype") == "Parameter"
                                and k.get("index", 0) >= 1):
                            dest_arg = k.get("index")
                            break
            if item_arg is not None:
                return {"item_arg": item_arg, "dest_arg": dest_arg, "dest_fixed": dest_fixed}
    return None


def _class_globals(ir):
    """class name -> the globals holding an instance of it, from `(= globalN <instance>)`.

    `Ego::get` is only `Ego::get` when the receiver IS the ego. The game says which global that
    is -- `(= global0 ego)` in Main's init, where `ego` is `(instance ego of Ego)` -- so resolve
    it rather than assuming global 0."""
    species_name, inst_species = {}, {}
    for s in ir.scripts.values():
        for o in s.objects:
            if o.is_class:
                species_name[o.species] = o.name
            else:
                inst_species[o.name] = o.super
    out = {}
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "Assignment":
                        continue
                    ks = n.get("kids") or []
                    if len(ks) < 2 or not I.is_global(ks[0]):
                        continue
                    src = ks[1]
                    if not (isinstance(src, dict) and src.get("t") == "Object"):
                        continue
                    cn = species_name.get(inst_species.get(src.get("name")))
                    if cn:
                        out.setdefault(cn, set()).add(ks[0]["index"])
    return out


class Vocabulary:
    """How THIS game says "move an item" and "is the item here", derived from its class table.

    Replaces a hand-written catalogue of selector names. Everything below comes from the game:
    the store's class and property, the selectors that write and read it, the wrapper methods
    the game defines over them, and which argument of each carries the item and the destination.
    """

    def __init__(self, store, writes, reads, prop, store_class, holders=None):
        self.store = store                 # the raw derivation, for reporting
        self.writes = writes               # selector -> arg roles (or None = receiver is the item)
        self.reads = reads
        self.prop = prop                   # the property that IS the location ("owner")
        self.store_class = store_class
        self.holders = holders or {}       # wrapper selector -> globals that may receive it

    @classmethod
    def from_ir(cls, ir):
        found = derive(ir)
        if not found:
            return None
        d = max(found, key=lambda x: len(x["wrappers"]))
        st, core = d["store"], set(d["store"]["writers"]) | set(d["store"]["readers"])
        writes, reads = {}, {}
        for sel in st["writers"]:
            writes[sel] = None             # core form: the RECEIVER is the item, arg 1 the dest
        for sel in st["readers"]:
            reads[sel] = None
        cg = _class_globals(ir)
        holders = {}
        for w in d["wrappers"]:
            roles = _arg_roles(ir, w["class"], w["selector"], core)
            if roles:
                (writes if w["kind"] == "write" else reads)[w["selector"]] = roles
                holders[w["selector"]] = cg.get(w["class"], set())
        return cls(d, writes, reads, st["prop"], st["class"], holders)

    def describe(self):
        return (f"{self.store_class}.{self.prop}  write via {sorted(self.writes)}  "
                f"read via {sorted(self.reads)}")

    def transfer(self, recv, sel, params, item_of_receiver):
        """A send -> `(item, dest)` if it moves an item, else None.

        `item_of_receiver(recv)` resolves `(<inv> at: N)` to N -- the one structural fact that
        stays in the caller, because it is about how an item is REFERRED to, not about vocabulary.
        """
        roles = self.writes.get(sel, "missing")
        if roles == "missing":
            return None
        if roles is None:                              # core form: receiver is the item itself
            if len(params) != 1:
                return None
            it = item_of_receiver(recv)
            if it is None:
                return None
            d = params[0]
            if I.is_global(d, 0) or (isinstance(d, dict) and d.get("t") == "Self"):
                return (it, EGO)
            v = I.as_int(d)
            return (it, v) if v is not None else None
        # wrapper form -- but only if the RECEIVER is an instance of the wrapper's class.
        # `Ego::get` means an acquisition when the ego receives it and nothing at all otherwise.
        holders = self.holders.get(sel)
        if holders and not any(I.is_global(recv, g) for g in holders):
            return None
        i = roles["item_arg"] - 1
        if i < 0 or i >= len(params):
            return None
        it = I.as_int(params[i])
        if it is None:
            return None
        if roles["dest_fixed"] is not None:
            return (it, roles["dest_fixed"])
        j = (roles["dest_arg"] or 0) - 1
        if 0 <= j < len(params):
            if I.is_global(params[j], 0):
                return (it, EGO)
            v = I.as_int(params[j])
            return (it, v if v is not None else -1)
        return (it, -1)                                # destination omitted -- SCI means NOWHERE


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
