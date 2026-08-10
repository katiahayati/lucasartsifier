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

import collections
import copy
import re

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
EGO = "ego"          # destination sentinel: the item is HELD (shared with extract)


def _literal_items(node):
    """The item numbers a `get:`/`put:` argument can denote.

    Usually one literal. But a shop that sells several things writes ONE routine and picks the
    item from a slot: KQ6's pawn counter is `(gEgo get: (switch register (0 48) (3 27) (1 3)
    (2 14)))`, which is how the tinderbox, the painter's brush and the mechanical nightingale
    change hands -- and `as_int` on a Switch is None, so all three had no source at all and could
    never be judged missable. Reading a switch's case LABELS as data is what
    `extract._var_room_values` already does for a revolving-door room's destinations.

    Every case is returned: which one you get depends on runtime state we do not track, so the
    honest reading is that this site can yield any of them."""
    if not isinstance(node, dict):
        return []
    v = I.as_int(node)
    if v is not None:
        return [v]
    if node.get("t") != "Switch":
        return []
    def val(x):
        # a case body is a statement LIST even when it is a single expression
        if isinstance(x, dict) and x.get("t") == "List":
            ks = x.get("kids") or []
            return I.as_int(ks[0]) if len(ks) == 1 else None
        return I.as_int(x)

    out = []
    for c in (node.get("kids") or [])[1:]:
        ks = c.get("kids") or []
        n = val(ks[1]) if (c.get("t") == "Case" and len(ks) > 1) else (
            val(ks[0]) if (c.get("t") == "Else" and ks) else None)
        if n is not None:
            out.append(n)
    return out


class AllOf(tuple):
    """Several items moved by ONE statement, ALL of them -- as opposed to a plain tuple, which
    `_literal_items` uses for a run-time PICK of one (a shop counter's `(get: (switch slot ...))`).

    The two shapes reach `item_transfers` identically -- one entry per item, which is the right
    reading for "where can this come from" either way -- and part company at `item_menus`, whose
    whole job is the fact that one statement hands over one item. A variadic `get:` is the exact
    opposite claim, so it must not be filed as an exchange slot."""
    __slots__ = ()


def item_menus(ir, vocab, item_of_receiver):
    """Every transfer site whose ITEM is picked at run time -- `{frozenset(items), ...}`.

    `_literal_items` already reads the case labels of `(gEgo get: (switch reg (0 48) (3 27)
    (1 3) (2 14)))` and says the honest thing about them: "this site can yield any of them".
    Read for SOURCES that is right, and every consumer unions the arms. Read for POSSESSION it
    also quietly asserts you can walk away with all four, because the union is all the shape
    that survives -- and ONE statement moves ONE item. So the grouping is kept here, and
    `missability.exchange_slots` is what turns it into an exclusion.

    Deliberately blind to WHERE the site is. A menu is a fact about the statement; which room
    runs it is a question the callers already answer better (script 287 is reached by a nested
    `ScriptID`, so the flat room walk never attributes it at all -- only the machine lift does).

    MEASURED: 2 sites in KQ6, both the pawn counter's two halves (`getFromCounter`'s `get:` and
    `placeOnCounter`'s `put:`) over the same four items; ZERO in LSL2, KQ4 and the Dagger of
    Amon Ra, so nothing built on this can move their goldens."""
    if vocab is None:
        return set()
    out = set()
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if node.get("t") != "Send":
                    continue
                try:
                    recv, msgs = I.send_pairs(node)
                except Exception:                       # noqa: BLE001
                    continue
                for sel, params in msgs:
                    tr = vocab.transfer(recv, sel, params, item_of_receiver)
                    if (tr and isinstance(tr[0], tuple) and not isinstance(tr[0], AllOf)
                            and len(set(tr[0])) > 1):
                        out.add((frozenset(tr[0]), tr[1]))
    return out


def _argc_temps(body):
    """The temps a method uses as an ARGUMENT-LIST cursor: those it compares against parameter 0.

    SCI passes the argument COUNT as parameter 0 and lays the arguments out contiguously after it,
    so `(for ((= temp0 0)) (< temp0 argc) ((++ temp0)) ... [param1 temp0] ...)` is the language's
    one way to spell "for every argument I was given". Recognising the cursor is what tells a
    VARIADIC wrapper from one that indexes an ARRAY it was handed -- both spell the access
    `[param1 temp0]`, and only the first bounds the index by how many arguments there are."""
    out = set()
    for n in I.walk(body):
        if n.get("t") not in ("Lt", "Le", "Gt", "Ge", "Ne", "Eq"):
            continue
        ks = n.get("kids") or []
        for a, b in ((ks[0], ks[1]),) if len(ks) >= 2 else ():
            for x, y in ((a, b), (b, a)):
                if (isinstance(x, dict) and x.get("vtype") == "Temp"
                        and isinstance(y, dict) and y.get("vtype") == "Parameter"
                        and y.get("index") == 0):
                    out.add(x.get("index"))
    return out


def _variadic_item_arg(recv, argc_temps):
    """`[param<i> <argc cursor>]` inside the forwarding receiver -> i, else None.

    The wrapper does not take ONE item and a destination; it takes as many items as it was
    given. `Ego::get` in the Dagger of Amon Ra is exactly this --

        (method (get param1 &tmp temp0)
          (for ((= temp0 0)) (< temp0 argc) ((++ temp0))
            ((global9 at: [param1 temp0]) moveTo: self)))

    -- and read as a one-item wrapper it loses every argument but the first. That is not a corner
    case there: 13 of the game's acquisition sites are written `(gEgo get: -1 32)`, the `-1`
    being the "no sound" sentinel with the items after it."""
    for k in I.walk(recv):
        if not (isinstance(k, dict) and k.get("t") == "ComplexVariable"):
            continue
        ks = k.get("kids") or []
        if len(ks) != 2:
            continue
        base, idx = ks
        if (isinstance(base, dict) and base.get("vtype") == "Parameter"
                and isinstance(idx, dict) and idx.get("vtype") == "Temp"
                and idx.get("index") in argc_temps):
            return base.get("index")
    return None


def _arg_roles(ir, wrapper_cls, selector, core):
    """Where the ITEM and the DESTINATION live in a wrapper's own argument list.

    Read off the forwarding send. `Ego::put param1 param2` forwards as
    `((global9 at: param1) moveTo: <param2 or -1>)`, so the item is argument 1 and the
    destination argument 2; `Ego::get param1` forwards as `(... moveTo: self)`, so the
    destination is the ego itself and there is no destination argument at all.

    ...and `variadic` says the item argument is the FIRST of however many were passed, which the
    same body says too -- see `_variadic_item_arg`."""
    cls = ir.find_class(wrapper_cls)
    body = cls.methods.get(selector) if cls else None
    if body is None:
        return None
    argc_temps = _argc_temps(body)
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
            item_arg = _variadic_item_arg(recv, argc_temps)
            variadic = item_arg is not None
            if item_arg is None:
                for k in I.walk(recv):                 # `(<inv> at: <Parameter i>)`
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
                return {"item_arg": item_arg, "dest_arg": dest_arg, "dest_fixed": dest_fixed,
                        "variadic": variadic}
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


def item_property_registers(ir, store_class, location_prop, item_of_receiver):
    """(item, property) pairs the game uses as STATE -- the "fourth store".

    Discovered the same way `gating_registers` discovers globals: a thing is state if it is both
    WRITTEN and READ. Nothing here names `loop`; we ask which properties of the item class the
    game writes with a constant and also reads back, and the answer in KQ4 is the bow, the shovel
    and the fishing pole --

        (Inv at: 14) loop: {0,1}     Cupid's Bow      loaded / spent
        (Inv at: 15) loop: {1}       Shovel           `(if (self loop:) {Broken Shovel} ...)`
        (Inv at: 17) loop: {0,1}     Fishing Pole     baited with the worm, or not

    -- and in LSL2, nothing, which is why this store never came up until a second game.

    The location property is excluded: it is the same store `Vocabulary` already models, and
    reading it here would double-count it."""
    from collections import defaultdict
    cls = ir.find_class(store_class)
    props = set(cls.props) if cls else set()
    props.discard(location_prop)
    written, compared, counters = defaultdict(set), defaultdict(set), set()
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    try:
                        recv, msgs = I.send_pairs(n)
                    except Exception:                      # noqa: BLE001
                        continue
                    it = item_of_receiver(recv)
                    if it is None:
                        continue
                    for pair in msgs:
                        if not pair or pair[0] not in props:
                            continue
                        sel, ps = pair
                        if ps:                             # a WRITE
                            v = I.as_int(ps[0])
                            if v is not None:
                                written[(it, sel)].add(v)
                            elif any(y.get("t") in ("Add", "Sub") for y in I.walk(ps[0])):
                                # `loop: (+ (loop:) 1)` -- an INCREMENT, so this is a COUNTER, not
                                # a flag. Cupid's Bow counts arrows USED (shootBow.sc:48) and is
                                # tested `(>= (loop:) 2)`. A constants-only scan reports {0,1} and
                                # models a counter as a boolean, which is worse than not modelling
                                # it: the whole point of this store is that you can spend too many.
                                counters.add((it, sel))
                                written[(it, sel)].add(0)
                        else:                              # `loop:` -- a READ
                            compared[(it, sel)].add(s.number)
    out = {}
    for k in sorted(set(written) & set(compared)):
        if not written[k]:
            continue
        out[k] = {"values": sorted(written[k]), "counter": k in counters}
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
        """A send -> `(item, dest)` if it moves an item, else None. `item` is a TUPLE when the
        game picks the item at runtime from a fixed menu (see `_literal_items`).

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
        if roles.get("variadic"):
            # EVERY argument from here on is an item. A negative number is not an inventory index:
            # SCI spells "none" as -1 everywhere (the same sentinel `moveTo:` takes for NOWHERE),
            # and LB2's `get:` sites lead with one.
            per_arg = [[v for v in _literal_items(p) if v >= 0] for p in params[i:]]
        else:
            per_arg = [_literal_items(params[i])]
        per_arg = [a for a in per_arg if a]
        if not per_arg:
            return None
        # WHICH TUPLE THIS IS depends on the SITE, not on the wrapper. Several ARGUMENTS means
        # several items handed over at once (`AllOf`); ONE argument with several possible values
        # is still a run-time pick of one, i.e. an exchange slot -- KQ6's pawn counter is
        # `(gEgo get: (switch register (0 48) (3 27) ...))` through the very same variadic `get:`,
        # and reading it as "all four" is what `item_menus`/`exchange_slots` exist to prevent.
        its = [v for a in per_arg for v in a]
        it = (its[0] if len(its) == 1
              else AllOf(its) if len(per_arg) > 1 else tuple(its))
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


# ---- the last two declared constants, DERIVED ----------------------------
# config.py used to argue these could not be derived: "LSL2 raises death as
# `gCurrentStatus == 1001` while KQ4 uses a boolean -- they share neither index nor shape."
# That only holds if you have to GUESS the shape. Read the test itself and the shape comes with
# it. Both anchors are ENGINE vocabulary, which is why they survive the game boundary:
#
#   DEATH  the global the Game subclass tests on the way to offering Restore / Restart / Quit.
#          `restart:` / `restore:` are Game methods. LSL2 hands off through `dyingScript` while
#          KQ4 offers the dialog inline, so the hand-off is followed one `setScript:` hop -- the
#          same thing the machine lift already does.
#   DEBUG  a debug flag is TOGGLED, not set: `(^= <global> $0001)`, what a menu checkbox compiles
#          to. Nothing else in a game XORs a global with 1.
#
# Verified against the hand-declared values: death reproduces (101, 1001) and (127, None) EXACTLY.
# Debug derives {14, 100} for LSL2 where {100, 111} was declared -- not set-equal but
# BEHAVIOURALLY equal (same 15 items + 1 group): global111 is never written, so the model already
# pins it at 0, and global14 is inert. KQ4 derives {215} exactly. Dropping debug pinning entirely
# costs 3 items (rm82's `if gDebugging` hands you the whole bomb), so it is not cosmetic.
RESTART_SELECTORS = ("restart", "restore")


def derive_control_selectors(ir):
    """{selector: 'restore' | 'take'} -- the Game hierarchy's own player-control switches.

    The engine spells player control as properties of the User class, written by methods of the
    Game class -- SCI1.1's `Game::handsOn` is literally `(User canControl: 1 canInput: 1)` -- and
    a game subclass keeps the selector when it overrides the body (KQ6 adds icon-bar bookkeeping,
    LB2 routes through its own User global). So the selectors are DERIVED, not declared: a method
    of a Game-descendant class qualifies when its body writes constant 0/1 to a property the User
    class INTRODUCES (inherited props like `x` are other classes' business), on a receiver that
    IS the User class or a global holding one of its instances, and the constant says which way
    the switch points. Same evidence tier as `game_objects` / `RESTART_SELECTORS`: the engine
    class table, because `Game` and `User` are the engine's own names for these anchors.

    MEASURED: LSL2 {} and KQ4 {} (SCI0 rooms write User directly; everything built on this is
    inert there by construction); KQ6 and LB2 both {'handsOn': 'restore', 'handsOff': 'take'}."""
    user, game = ir.find_class("User"), ir.find_class("Game")
    if user is None or game is None:
        return {}
    # The control switches are User's own vocabulary in BOTH spellings: SCI0 declares `canInput`
    # as a property and `canControl` as a method; SCI1.1 makes both methods over a state word.
    # Either way the NAME is declared on the User class itself, which is the whole test.
    uprops = (_class_introduces(ir).get(user.species, frozenset())
              | frozenset(user.methods))
    if not uprops:
        return {}
    species = {game.species}
    changed = True
    while changed:                                     # Game's subclass closure
        changed = False
        for s in ir.scripts.values():
            for o in s.objects:
                if o.is_class and o.super in species and o.species not in species:
                    species.add(o.species)
                    changed = True
    ginst = _global_instances(ir)

    def _user_recv(recv):
        if isinstance(recv, dict) and recv.get("t") in ("Object", "Class"):
            return recv.get("name") == user.name
        if isinstance(recv, dict) and I.is_global(recv):
            hit = ginst.get(recv["index"])
            return hit is not None and (hit[0].species == user.species
                                        or hit[0].super == user.species)
        return False

    out = {}
    for s in ir.scripts.values():
        for o in s.objects:
            if not (o.species in species if o.is_class else o.super in species):
                continue
            for sel, body in o.methods.items():
                vals = set()
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    try:
                        recv, msgs = I.send_pairs(n)
                    except Exception:                  # noqa: BLE001
                        continue
                    if not _user_recv(recv):
                        continue
                    for s2, ps in msgs:
                        if s2 in uprops and ps and I.as_int(ps[0]) in (0, 1):
                            vals.add(I.as_int(ps[0]))
                if vals == {1}:
                    out[sel] = "restore"
                elif vals == {0}:
                    out.setdefault(sel, "take")
    return out


def game_objects(ir):
    """Objects whose class is (or descends from) the engine `Game` class."""
    game = ir.find_class("Game")
    if game is None:
        return []
    species = {game.species}
    changed = True
    while changed:                       # subclasses of Game, transitively
        changed = False
        for s in ir.scripts.values():
            for o in s.objects:
                if o.is_class and o.super in species and o.species not in species:
                    species.add(o.species); changed = True
    return [o for s in ir.scripts.values() for o in s.objects
            if o.super in species or o.species in species]


def test_shape(node):
    """A test expression -> (global index, required value or None for 'any non-zero')."""
    if I.is_global(node):
        return (node["index"], None)
    if node.get("t") == "Eq":
        ks = node.get("kids") or []
        if len(ks) >= 2:
            for a, b in ((ks[0], ks[1]), (ks[1], ks[0])):
                if I.is_global(a) and I.as_int(b) is not None:
                    return (a["index"], I.as_int(b))
    return None


def _script_named(ir, name):
    for s in ir.scripts.values():
        o = s.by_name.get(name)
        if o is not None:
            return o
    return None


def _offers_restart(ir, node, depth):
    """Does this branch reach Restore/Restart/Quit -- directly, or through a script it starts?

    LSL2 hands off: `(if (== gCurrentStatus 1001) (gCurRoom setScript: dyingScript))`, and it is
    dyingScript that offers the dialog. KQ4 offers it inline. Following `setScript:` one hop is
    the same thing the machine lift already does, so the anchor is shared even though the shape
    of the hand-off is not.

    Used only by the SCI0/SCI1 death path (`derive_death` / `derive_death_proc`), where Restart is
    offered ONLY on death -- so any reachable Restart offer is a death. SCI1.1 games surface Restart
    from an always-available control panel too, which would make this match the input handler; those
    are dispatched to `derive_death_sci11` in load() and never reach here (see is_sci11)."""
    for m in I.walk(node):
        if m.get("t") != "Send":
            continue
        try:
            _r, msgs = I.send_pairs(m)
        except Exception:                      # noqa: BLE001
            continue
        for pair in msgs:
            if not pair:
                continue
            if pair[0] in RESTART_SELECTORS:
                return True
            if pair[0] == "setScript" and depth < 2 and pair[1]:
                tgt = pair[1][0]
                if isinstance(tgt, dict) and tgt.get("t") == "Object":
                    obj = _script_named(ir, tgt.get("name"))
                    if obj is not None and any(
                            _offers_restart(ir, b, depth + 1) for b in obj.methods.values()):
                        return True
    return False


def derive_death(ir):
    """The global whose truth means the run is over: tested on the way to Restore/Restart/Quit."""
    hits = []
    for o in game_objects(ir):
        for mname, body in o.methods.items():
            for n in I.walk(body):
                if n.get("t") != "If":
                    continue
                ks = n.get("kids") or []
                if len(ks) < 2:
                    continue
                shape = test_shape(ks[0])
                if shape is None:
                    continue
                if _offers_restart(ir, ks[1], depth=0):
                    hits.append((shape, o.name, mname))
    return hits


def derive_death_proc(ir):
    """Imperative death -- a FREE PROCEDURE that shows Restore/Restart/Quit, invoked as a bare
    statement at each hazard site (Camelot `proc128_0`, TCB `proc0_19`, QFG2 `proc1_24`, KQ5 too).

    Distinct from the global-flag shape `derive_death` finds: there is no "you died" global at all;
    death is a control-flow event -- a call to the death dialog. We detect the dialog PROCEDURE
    (a script-level proc whose body offers restart:/restore:), and the caller lowers each call to it
    into a synthetic death-flag write so the existing `is_death` machinery applies unchanged. Only
    FREE procedures are considered, which is what separates the death routine from the menu-bar's
    own Restore/Restart/Quit (those live in Menu/Title OBJECT methods, not a proc). Returns the set
    of procedure names whose calls are deaths."""
    out = set()
    for s in ir.scripts.values():
        for name, body in s.procs.items():
            # the game-wide death routine is a PUBLIC proc -- it is called cross-script from every
            # hazard, which requires an export. A script-LOCAL restart-offering proc (`localproc_*`)
            # is the menu/title's own dialog code or an internal helper, not a death edge.
            if name.startswith("localproc"):
                continue
            if _offers_restart(ir, body, depth=0):
                out.add(name)
    return out


def lower_death_procs(ir, proc_names, death_value=1):
    """Rewrite every call to a death PROCEDURE into a synthetic death-flag global write, IN PLACE,
    so the (global,value)-based death machinery (`is_death`, death_rooms, the winnable filter)
    applies to imperative death with no other change. The synthetic global is one past the highest
    global the game references, so it cannot collide; it is only ever written the death value and
    that write is death, so `is_death` filters it out of the gating registers -- no state blow-up.
    A `(proc128_0 …)` becomes `(= gSYNTH 1)`. Returns (synth_index, sites_lowered)."""
    max_gi, targets = 0, []
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if I.is_global(node):
                    max_gi = max(max_gi, node["index"])
                elif node.get("t") in ("PublicCall", "LocalCall") and node.get("name") in proc_names:
                    targets.append(node)
    synth = max_gi + 1
    for node in targets:                                   # nodes are the AST dicts the parent holds
        node.clear()
        node["t"] = "Assignment"
        node["kids"] = [{"t": "Variable", "vtype": "Global", "index": synth},
                        {"t": "Number", "value": death_value}]
    return synth, len(targets)


def derive_death_send(ir):
    """SCI1.1 INLINE death: a non-Game object whose method offers BOTH restart: and restore: -- the
    death dialog a hazard shows (KQ6 `egoBeastScript`, `deathCartoonScr`, `deadInHereScript`,
    `noWayOut`). A third shape after `derive_death` (a Game-object global) and `derive_death_proc`
    (a free proc): SCI1.1 puts Restart/Restore in an ALWAYS-available control panel, so there is no
    "you died" global and no death proc -- a real death offers the dialog inline at the hazard.

    Requiring BOTH selectors is the discriminator: the control-panel/menu offers each through a
    SEPARATE button (`restartBut`/`restoreBut` -- one selector each), and a Window's own `restore:`
    is window-restore, a different meaning; only a death dialog sends both together. The Game object
    is skipped (its handleEvent reaches the menu). Returns [(script_num, object_name), ...]."""
    game = {o.name for o in game_objects(ir)}
    out = []
    for s in ir.scripts.values():
        for o in s.objects:
            if o.is_class or o.name in game:
                continue
            for body in o.methods.values():
                sels = set()
                for n in I.walk(body):
                    if n.get("t") == "Send":
                        try:
                            _r, msgs = I.send_pairs(n)
                        except Exception:              # noqa: BLE001
                            continue
                        for sel, _p in msgs:
                            if sel in RESTART_SELECTORS:
                                sels.add(sel)
                if all(x in sels for x in RESTART_SELECTORS):
                    out.append((s.number, o.name))
                    break
    return out


def is_sci11(ir):
    """Is this a SCI1.1 (heap-format) game? Instances carry the 0xffff species sentinel with the
    class species in `super`, where SCO0 and SCI1 put the class species directly in `species`. Same
    encoding `item_names` keys on. It selects the DEATH model, because SCI1.1 surfaces Restart/Restore
    from an always-available control panel, so "a reachable Restart offer" no longer means "a death"
    -- the SCO0/SCI1 assumption behind `derive_death`."""
    insts = [o for s in ir.scripts.values() for o in s.objects if not o.is_class]
    return bool(insts) and sum(1 for o in insts if o.species == 65535) * 2 > len(insts)


def derive_death_sci11(ir):
    """SCI1.1 death = reaching a DEATH DIALOG, with the always-available control panel excluded.

    Two mechanisms, both keyed on the death dialog (a non-Game object offering BOTH restart: and
    restore: -- `derive_death_send`; "both" excludes the single-button menu icons and Window-restore):
      (1) the dialog runs inline in a hazard script -- inject a death write (KQ6 egoBeastScript,
          deathCartoonScr, deadInHereScript, noWayOut);
      (2) a public PROC that `newRoom`s into a death-dialog's script (a death room) -- KQ6 `proc0_1`
          transports to rm640 (deathCartoonScr) from ~10 hazards. Its call sites keep their guards,
          so an item-gated hazard death (`(if (not (has shield)) (proc0_1 ...))`) becomes the
          requirement it is. `localproc` is menu/helper code, excluded.

    Returns (inline_dialogs, death_procs)."""
    dialogs = derive_death_send(ir)
    death_rooms = {sn for (sn, _o) in dialogs}
    # A SCI1.1 game may ALSO use the imperative-proc shape (QFG-VGA proc1_0 offers restart inline);
    # the control-panel Restart is a Game METHOD reached via a `#restart` selector reference, never a
    # public proc, so a public restart-offering proc is a death here just as in SCO0.
    death_procs = set(derive_death_proc(ir))
    for s in ir.scripts.values():
        for pname, body in s.procs.items():
            if pname.startswith("localproc"):
                continue
            for n in I.walk(body):
                if n.get("t") != "Send":
                    continue
                try:
                    _r, msgs = I.send_pairs(n)
                except Exception:                      # noqa: BLE001
                    continue
                for sel, params in msgs:
                    if sel == "newRoom" and params and I.as_int(params[0]) in death_rooms:
                        death_procs.add(pname)
    return dialogs, death_procs


_skipped_deaths = []          # dialogs with no reachable entry -- reported, never swallowed


def lower_death_sci11(ir, dialogs, death_procs, death_value=1, screens=()):
    """Both SCI1.1 death mechanisms lowered onto ONE synthetic death global (computed once, before
    any injection so the two passes agree): a death write into each inline dialog's state 0, and a
    death write in place of each call to a death proc."""
    max_gi = 0
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if I.is_global(n):
                    max_gi = max(max_gi, n["index"])
    synth = max_gi + 1

    def write():
        return {"t": "Assignment", "kids": [
            {"t": "Variable", "vtype": "Global", "index": synth},
            {"t": "Number", "value": death_value}]}

    n = 0
    for (sn, obj_name) in dialogs:                     # (1) inline dialogs -> death write at ENTRY
        obj = ir.scripts[sn].by_name.get(obj_name)
        # ⭐ THE OBJECT'S ENTRY -- which is what "reaching the death dialog" means. NOT where the
        # buttons are: the offer sits two Switch/Case levels deep in KQ6's dialogs, and injecting
        # there would put the death on the button-press path condition. Arriving at the dialog IS
        # the death; Restore/Restart is epilogue.
        #
        # `init` IS the SCI entry point, and `Script` overrides it to dispatch to `changeState(0)`
        # -- so case 0 is not a second rule, it is where `init` GOES for a Script that does not
        # define its own. One concept, two spellings, and the fallback is read off the class
        # protocol rather than asserted.
        #
        # MEASURED before writing this: KQ6's four dialogs (egoBeastScript, deathCartoonScr,
        # deadInHereScript, noWayOut) define no `init`, so every one keeps the case-0 path exactly
        # as before -- 66 DEATH transitions across 34 rooms, unchanged. LB2's `deathRoom` is a
        # ROOM whose offer lives in `init`, and it used to fall out of this loop SILENTLY: the
        # game ended up with zero deaths, `rm99` stayed an ordinary room with an exit to `rm350`,
        # and the model could travel by dying.
        own_init = obj.methods.get("init") if obj else None
        entry = own_init or (obj.methods.get("changeState") if obj else None)
        if entry is None:
            _skipped_deaths.append((sn, obj_name))
            continue
        injected = False
        # A state dispatcher hides its entry in case 0; a plain `init` runs top to bottom, and
        # searching IT for a "case 0" would land in whichever branch the buttons happen to be in.
        for node in (I.walk(entry) if own_init is None else ()):
            if node.get("t") != "Switch":
                continue
            for c in (node.get("kids") or [])[1:]:
                ck = c.get("kids") or []
                if c.get("t") == "Case" and ck and I.as_int(ck[0]) == 0 and len(ck) > 1:
                    body0 = ck[1]
                    if body0.get("t") == "List":
                        body0.setdefault("kids", []).insert(0, write())
                    else:
                        ck[1] = {"t": "List", "kids": [write(), body0]}
                    injected = True
            break
        if not injected:
            old = dict(entry); entry.clear(); entry["t"] = "List"; entry["kids"] = [write(), old]
        n += 1
    for s in ir.scripts.values():                      # (2) death-proc calls -> death write
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if node.get("t") in ("PublicCall", "LocalCall") and node.get("name") in death_procs:
                    node.clear()
                    node["t"] = "Assignment"
                    node["kids"] = [{"t": "Variable", "vtype": "Global", "index": synth},
                                    {"t": "Number", "value": death_value}]
                    n += 1
    # (3) `newRoom:` INTO A DEATH SCREEN is a death, not a journey. A screen is a room that IS the
    # Restore/Restart offer (`extract.death_screen_rooms`), so arriving is dying and there is
    # nothing on the other side to walk to. LB2 writes its deaths this way -- `sLauraDies` and 33
    # siblings end `(gRoom newRoom: 99)` -- and with only mechanisms (1) and (2) every one of them
    # was invisible: the game modelled ZERO deaths.
    #
    # Deliberately NOT "newRoom into a death ROOM": KQ6 has 34 of those, and they are ordinary
    # places you walk through where a hazard's cutscene may kill you. Marking every entrance to
    # them as a death would wall off a third of the game. Measured: 0 screens and 0 sites on KQ6,
    # so this is inert there by construction; 34 sites on LB2.
    if screens:
        for s in ir.scripts.values():
            bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
            for body in bodies:
                for node in I.walk(body):
                    if node.get("t") != "Send":
                        continue
                    try:
                        _r, msgs = I.send_pairs(node)
                    except Exception:                  # noqa: BLE001
                        continue
                    # only a send whose SOLE message is the fatal `newRoom:` -- a chained send
                    # does other work we would silently discard by replacing the whole node
                    if len(msgs) == 1 and msgs[0][0] == "newRoom" and msgs[0][1] \
                            and I.as_int(msgs[0][1][0]) in screens:
                        node.clear()
                        node["t"] = "Assignment"
                        node["kids"] = [{"t": "Variable", "vtype": "Global", "index": synth},
                                        {"t": "Number", "value": death_value}]
                        n += 1
    # LOUDLY. A death dialog we cannot lower is a whole game's worth of deaths going missing, and
    # deaths are in scope by the project's central rule -- LB2 lost every one of them to a silent
    # `continue` here and nobody knew until an unrelated change happened to expose it.
    if _skipped_deaths:
        import sys as _sys
        print("  [degraded] death dialog(s) with neither an own `init` nor a `changeState` -- NO "
              "death is modelled for them: %s" % (_skipped_deaths,), file=_sys.stderr)
        _skipped_deaths.clear()
    return synth, n


# ---- the game-flag store: a bit-array of booleans, DERIVED like every other store -------------
# Later Sierra games keep hundreds of one-bit progress flags packed into a global array and reach
# them through a tiny accessor: `[globalBASE (/ n 16)]` masked by a single bit `(<< 1 (mod n 16))`
# (or the mirror `(>> $8000 (mod n 16))`). This is NOT "the SCI1 flag system" to be gated behind a
# version check -- it is a STORE, recognised by its shape exactly as gating registers and the
# item-location store are. A game that has it yields one; a game that does not (LSL2, KQ4) yields
# nothing and nothing downstream changes. The single-bit shift-by-`(mod _ 16)` is the signature:
# nothing else in a game shifts 1 (or $8000) by a value mod 16.
#
# The accessor's PACKAGING varies and must not be assumed: KQ5 has ONE op-dispatched proc
# `localproc(op, n)` with thin public wrappers (`proc0_12(n) = localproc(1, n)`), while KQ6, Dagger
# and QFG1 expose THREE standalone procs (test/set/clear, no toggle). `derive_flags` classifies each
# touching proc by the OPERATOR it applies to the array word -- `&` reads (test), `|=` sets, `&= ~`
# clears, `^=` toggles -- and, for a dispatcher, follows its wrappers to fix each one's op.
_FLAG_WRITE_OPS = {"AssignmentBinOr": "set", "AssignmentBinAnd": "clear", "AssignmentXor": "toggle"}

# Globals WE synthesized from a flag store, so their domain is exactly {0, 1} -- our own lowering
# writes 1 for set and 0 for clear and nothing else. That makes `!= 0` and `== 1` the SAME
# constraint on them, which matters because "this flag is SET" is the natural way to gate progress
# and `required_values` otherwise ignores `!=` as unconstraining. Module-level, like extract's
# per-game vocabulary: one game per process.
BOOL_GLOBALS = set()


def _single_bit_mask(n):
    """`(<< 1 (mod X 16))` or `(>> $8000 (mod X 16))` -- one bit selected within a 16-bit word."""
    if not isinstance(n, dict):
        return False
    t, ks = n.get("t"), n.get("kids") or []
    if t == "Shl" and len(ks) == 2 and I.as_int(ks[0]) == 1:
        m = ks[1]
    elif t == "Shr" and len(ks) == 2 and I.as_int(ks[0]) in (-32768, 32768):
        m = ks[1]
    else:
        return False
    return isinstance(m, dict) and m.get("t") == "Mod" and I.as_int((m.get("kids") or [0, 0])[1]) == 16


def _flag_word_base(n):
    """`[globalBASE <wordindex>]` -> BASE, else None. The word of the flag array being addressed."""
    if isinstance(n, dict) and n.get("t") == "ComplexVariable":
        ks = n.get("kids") or []
        if ks and I.is_global(ks[0]):
            return ks[0]["index"]
    return None


def _flag_write_op(node, base):
    """This node writes the flag word of `base` in place -> 'set'/'clear'/'toggle', else None."""
    op = _FLAG_WRITE_OPS.get(node.get("t"))
    if op and any(_flag_word_base(k) == base for k in (node.get("kids") or [])):
        return op
    return None


def _proc_touches_flags(body):
    """(base, write_ops, reads) if `body` masks a global array word with a single bit, else None."""
    if not any(_single_bit_mask(n) for n in I.walk(body)):
        return None
    base = next((_flag_word_base(n) for n in I.walk(body) if _flag_word_base(n) is not None), None)
    if base is None:
        return None
    wops = {_flag_write_op(n, base) for n in I.walk(body)} - {None}
    reads = any(n.get("t") == "BinAnd" and any(_flag_word_base(k) == base for k in (n.get("kids") or []))
                for n in I.walk(body))
    return base, wops, reads


def _flag_switch_map(body, base):
    """A dispatcher's `(switch op ...)` -> {op-value: op-kind}. The op is the switched PARAMETER;
    each case's kind is read from the write it performs on the flag word (a break/read case is a
    test). KQ5's `localproc` dispatches op 0->set, 1->test, 2->clear, 3->toggle exactly this way."""
    for n in I.walk(body):
        if n.get("t") != "Switch":
            continue
        ks = n.get("kids") or []
        head = ks[0] if ks else None
        if not (head and head.get("t") == "Variable" and head.get("vtype") == "Parameter"):
            continue
        m = {}
        for c in ks[1:]:
            if c.get("t") != "Case":
                continue
            ck = c.get("kids") or []
            if len(ck) < 2 or I.as_int(ck[0]) is None:
                continue
            m[I.as_int(ck[0])] = next((_flag_write_op(x, base) for x in I.walk(ck[1])
                                       if _flag_write_op(x, base)), "test")
        return m
    return None


def _localproc_offset(name):
    """A local proc's registry key is `localproc_<hexoffset>`; a LocalCall targets it by that same
    offset (as a decimal `offset` field), NOT by the index name it also carries. Return the offset."""
    if name.startswith("localproc_"):
        try:
            return int(name.split("_", 1)[1], 16)
        except ValueError:
            return None
    return None


def derive_flags(ir):
    """The game's boolean-flag store: (base_global, {proc_name: op}) with op in
    test/set/clear/toggle, or None if the game keeps no bit-array flags (LSL2/KQ4).

    `proc_name` is a proc whose calls carry flag NUMBERS as arguments -- a standalone test/set/clear
    proc, or a public wrapper over an op-dispatched accessor. The caller (`lower_flags`) rewrites
    those calls into synthetic per-flag globals so the register machinery models each flag as an
    ordinary gating register, with no notion of 'flags' anywhere downstream."""
    acc = {}
    for s in ir.scripts.values():
        for name, body in s.procs.items():
            tr = _proc_touches_flags(body)
            if tr:
                acc[name] = (tr, body)
    if not acc:
        return None
    from collections import Counter
    base = Counter(v[0][0] for v in acc.values()).most_common(1)[0][0]
    procs, dispatchers = {}, {}
    for name, ((b, wops, reads), body) in acc.items():
        if b != base:
            continue
        if len(wops) > 1:               # applies several ops -> an op-dispatched accessor
            dispatchers[name] = body
        elif len(wops) == 1:            # a single-op writer: set / clear / toggle
            procs[name] = next(iter(wops))
        elif reads:                     # reads only: a test
            procs[name] = "test"
    for dname, dbody in dispatchers.items():
        sm = _flag_switch_map(dbody, base) or {}
        doff = _localproc_offset(dname)
        for s in ir.scripts.values():
            for name, body in s.procs.items():
                calls = [n for n in I.walk(body) if n.get("t") == "LocalCall"]
                if len(calls) != 1 or calls[0].get("offset") != doff:
                    continue
                a = calls[0].get("kids") or []
                if a and I.as_int(a[0]) in sm:
                    procs[name] = sm[I.as_int(a[0])]
    return base, procs


def lower_flags(ir, base_global, flag_procs):
    """Rewrite every call to a test/set/clear flag proc with LITERAL flag arguments into a
    synthetic per-flag global read or write, IN PLACE, so a flag becomes an ordinary global the
    gating-register machinery already promotes. Flag N maps to `synth_base + N`, one contiguous
    block past the highest global in use (so it clears both the real globals and any synthetic
    death flag lowered earlier). A `(proc0_12 15)` test becomes a read of that global; `(proc0_9 15)`
    set becomes `(= gSYNTH15 1)`; clear writes 0.

    Toggle calls and non-literal flag arguments are left unlowered -- a bounded, SOUND gap: an
    unmodelled write cannot invent a stranding, only miss one. Returns (synth_base, lowered, skipped)."""
    max_gi, calls = 0, []
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if I.is_global(node):
                    max_gi = max(max_gi, node["index"])
                elif node.get("t") in ("PublicCall", "LocalCall") and node.get("name") in flag_procs:
                    calls.append(node)
    synth_base = max_gi + 1
    lowered = skipped = 0
    seen_flags = set()
    for node in calls:
        op = flag_procs[node["name"]]
        flags = [I.as_int(k) for k in (node.get("kids") or []) if I.as_int(k) is not None]
        if op == "toggle" or not flags:
            skipped += 1
            continue
        seen_flags.update(flags)
        BOOL_GLOBALS.update(synth_base + f for f in flags)
        if op == "test":
            node.clear()
            node.update({"t": "Variable", "vtype": "Global", "index": synth_base + flags[0]})
        else:
            val = 1 if op == "set" else 0
            assigns = [{"t": "Assignment",
                        "kids": [{"t": "Variable", "vtype": "Global", "index": synth_base + f},
                                 {"t": "Number", "value": val}]} for f in flags]
            node.clear()
            node.update(assigns[0] if len(assigns) == 1 else {"t": "List", "kids": assigns})
        lowered += 1
    # WHICH flags this block actually covers, so a later store's registers cannot be mistaken
    # for flags. The block is allocated at `max_gi + 1` and every store lowered AFTER it takes
    # indices further up, but `guards.render_register`'s fallback was "anything at or past the
    # base is flag `R - base`" -- unbounded, so a mask-global register renders as a flag number
    # outside the game's array entirely (measured on KQ6: register 555 spelled `(proc913_0 383)`
    # where the highest real flag is 163). Recording the set makes the test exact rather than a
    # range guess, and it is free: these are the literals the lowering just consumed.
    try:
        ir.flag_indices = frozenset(seen_flags)
    except Exception:                                       # noqa: BLE001
        pass
    return synth_base, lowered, skipped


def _dyn_self_prop(node):
    """`(self <var>:)` -- a property access whose SELECTOR comes from a variable, so the property
    is chosen by the CALLER. Returns the SendMessage node, else None.

    This is the tell for a generic accessor: a method that manipulates whichever property its
    argument names. `send_pairs` reports such a selector as None (it is not a `Selector` node)."""
    if not (isinstance(node, dict) and node.get("t") == "Send"):
        return None
    ks = node.get("kids") or []
    if not (ks and isinstance(ks[0], dict) and ks[0].get("t") == "Self"):
        return None
    msgs = [m for m in ks[1:] if isinstance(m, dict) and m.get("t") == "SendMessage"]
    if len(msgs) != 1:
        return None
    sel = (msgs[0].get("kids") or [None])[0]
    return msgs[0] if isinstance(sel, dict) and sel.get("t") == "Variable" else None


def _prop_flag_op(body):
    """'test' / 'set' / 'clear' if `body` is a BIT ACCESSOR over a property named by its own
    parameter, else None.

    The identical store `derive_flags` finds in a global array, kept in an object's property
    WORDS instead -- `(self <sel>: (| (self <sel>:) <mask>))` sets, `(& (self <sel>:) (~ <mask>))`
    clears, a bare `(& (self <sel>:) <mask>)` tests. Discovered STRUCTURALLY, exactly as
    `_proc_touches_flags` discovers the proc-based spelling: no selector NAME is assumed, so a
    game that calls these something other than tstFlag/setFlag/clrFlag is still recognised."""
    ops, saw = set(), False
    for n in I.walk(body):
        m = _dyn_self_prop(n)
        if m is None:
            continue
        saw = True
        kids = m.get("kids") or []
        if len(kids) < 2:
            continue                                  # a READ: `(self <sel>:)`
        val = kids[1]                                 # a WRITE: `(self <sel>: <val>)`
        t = val.get("t") if isinstance(val, dict) else None
        if t == "BinOr":
            ops.add("set")
        elif t == "BinAnd":
            ops.add("clear" if any(isinstance(k, dict) and k.get("t") == "BinNot"
                                   for k in (val.get("kids") or [])) else "set")
    if not saw:
        return None
    if ops:
        return next(iter(ops)) if len(ops) == 1 else None    # mixed writer -> cannot classify
    return "test" if any(n.get("t") == "BinAnd" and any(_dyn_self_prop(k)
                                                        for k in (n.get("kids") or []))
                         for n in I.walk(body)) else None


def _flag_receiver_id(recv):
    """A STATIC identity for a flag-accessor receiver, or None when it cannot be pinned.

    `(ScriptID N M)` names script N's Mth object -- the SCI way to reach a singleton (a region)
    from another script, and the only receiver form that actually occurs in the corpus. `self`
    inside the accessor's own class is deliberately NOT pinned: it could be any instance, and
    guessing would merge distinct regions' flag words into one.

    A direct object reference (`(rgCastle setFlag: ...)`) would be equally resolvable and is the
    obvious extension point, but no game we have writes it, so it is left out rather than shipped
    untested. An unpinned receiver is skipped, which can only miss a gate, never invent one."""
    if not isinstance(recv, dict):
        return None
    if (recv.get("t") in ("KernelCall", "PublicCall", "LocalCall")
            and recv.get("name") == "ScriptID"):
        a = [I.as_int(k) for k in (recv.get("kids") or [])]
        if a and a[0] is not None:
            return (a[0], a[1] if len(a) > 1 and a[1] is not None else 0)
    return None


def derive_prop_flags(ir):
    """{selector_name: op} for the game's PROPERTY-word bit-flag store, or {} if it has none.

    A second, independent flag store from the one `derive_flags` finds: SCI1.1 regions keep their
    flags in their own property words rather than a global array. Same abstraction (a bit in a
    word), different container -- so it lowers to the same synthetic per-flag globals and nothing
    downstream learns a new concept. LSL2/KQ4/KQ5/QFG-VGA/Dagger have none; KQ6 has 329 sites."""
    out = {}
    for s in ir.scripts.values():
        for o in s.objects:
            for mname, body in o.methods.items():
                op = _prop_flag_op(body)
                if op and out.get(mname, op) == op:
                    out[mname] = op
    return out


def lower_prop_flags(ir, accessors):
    """Rewrite `(<recv> tstFlag: <word> <mask>...)` calls into synthetic per-flag globals, in
    place -- the property-store twin of `lower_flags`, so both stores reach the register
    machinery as ordinary globals.

    A flag's identity is the triple (receiver, word-selector, BIT). Masks are decomposed to
    single bits so a multi-bit `setFlag` and a single-bit `tstFlag` agree on identity; a
    multi-bit TEST becomes an `Or` over the bits, which `atom` already understands. Unresolvable
    receivers (bare `self`) and non-literal arguments are left alone -- a sound gap, since an
    unmodelled condition can only miss a stranding, never invent one.

    A CHAINED send keeps its other messages. `(<recv> clrFlag: 710 1 setFlag: 709 2)` used to be
    skipped whole, because replacing the node would have dropped `clrFlag`'s siblings -- and that
    is not a harmless gap: `rm880.sc:1505` is the only writer of KQ6's "the wedding has started"
    flag, the state that decides whether rm740 runs `alexWedding` or `vizierWedding`. With the
    write dropped, zero-init pins the flag at 0 and the vizier's wedding becomes unreachable, so
    the game's central branch was collapsed by a syntactic accident. The chain now lowers to a
    `List` in the ORIGINAL message order, flag messages becoming assignments and the rest staying
    as single-message sends on the same receiver.

    Only WRITES are lowered inside a chain. A chained `tstFlag` would need the send's VALUE, and a
    `List` has none; measured, KQ6 has no such site, so this refuses rather than guesses."""
    if not accessors:
        return 0, 0, 0
    def _bits(sel, params):
        """(op, [(rid, word, bit)]) for one flag message, or None if it cannot be pinned."""
        args = [I.as_int(p) for p in params]
        if len(args) < 2 or any(a is None for a in args):
            return None
        bits = [(args[0], b) for m in args[1:] for b in range(16) if (m & 0xFFFF) >> b & 1]
        return (accessors[sel], bits) if bits else None

    # THE SAME STORE HAS A SECOND SPELLING (play-derived 2026-08-04, the corral chase). The
    # accessor methods are selector-indirection -- `(setFlag: 709 m)` ORs m into the property
    # whose SELECTOR NUMBER is 709 (`rFlag1`; proof: rgCastle.sc:569 `rFlag1: (& rFlag1 $fffd)`
    # is bit-for-bit `clrFlag: 709 2`) -- so the game also reads and writes these words
    # DIRECTLY: `(|= rFlag1 $0004)` in the owning class, `(rgCastle rFlag1: (| ... $2000))` by
    # class name from a sibling script, `(RgBasement setFlag: 709 8)` by name instead of
    # ScriptID. Keying only on the accessor calls missed all of it -- measured: reg340, the
    # castle corral's own arming condition, had NO writer, and reg378 was missing one. The
    # name->export map below resolves name receivers to the SAME (script, export) identity the
    # ScriptID spelling lowers to (verified: rgCastle IS export 0 of script 80, RgBasement of
    # 81), and a second collection pass picks up the direct property arithmetic.
    obj_export = {}
    for s in ir.scripts.values():
        for xi, nm in enumerate(getattr(s, "exports", None) or []):
            if nm:
                obj_export.setdefault(nm, (s.number, xi))
    sel_value = {}
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") == "Selector" and isinstance(n.get("value"), int) \
                        and n.get("name"):
                    sel_value.setdefault(n["name"], n["value"])

    def _rid_of(recv):
        rid = _flag_receiver_id(recv)
        if rid is not None:
            return rid
        if isinstance(recv, dict) and recv.get("t") in ("Class", "Object") \
                and recv.get("name") in obj_export:
            return obj_export[recv["name"]]
        return None

    max_gi, sites = 0, []
    flag_words = set()
    for s in ir.scripts.values():
        bodies = [m for o in s.objects for m in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if I.is_global(node):
                    max_gi = max(max_gi, node["index"])
                    continue
                if node.get("t") != "Send":
                    continue
                recv, msgs = I.send_pairs(node)
                legacy_rid = _flag_receiver_id(recv)
                rid = legacy_rid if legacy_rid is not None else _rid_of(recv)
                if rid is None or not any(sel in accessors for sel, _p in msgs):
                    continue
                plan, usable = [], True
                for mnode, (sel, params) in zip([m for m in node["kids"][1:]
                                                 if m.get("t") == "SendMessage"], msgs):
                    if sel not in accessors:
                        plan.append(("keep", mnode))
                        continue
                    hit = _bits(sel, params)
                    if hit is None or (len(msgs) > 1 and hit[0] == "test"):
                        usable = False       # unpinnable, or a test whose value the chain needs
                        break
                    flag_words.update(w for (w, _b) in hit[1])
                    plan.append(("flag", hit[0], [(rid, w, b) for (w, b) in hit[1]]))
                if usable and any(p[0] == "flag" for p in plan):
                    sites.append((node, recv, plan, legacy_rid is not None))

    # SECOND PASS: the direct spellings, now that the flag WORDS are known. A site is one of:
    #   test   `(& <word-read> m)`            -- BinAnd over a read, either operand order
    #   set    `(|= prop m)` / `(<recv> w: (| <read> m))`
    #   clear  `(&= prop (~ m))` / `(<recv> w: (& <read> lit))` -- a literal AND clears ~lit
    # An unresolvable MASK stays sound by fanning to every known bit of the word in the op's
    # own direction only (an AND can only clear, an OR can only set) -- the permissive reading.
    # `bits=None` marks that case; it expands against the final index at rewrite time.
    def _mask_bits(v):
        return [b for b in range(16) if (v & 0xFFFF) >> b & 1]

    def _word_read(n, rid, word):
        """n is a read of (rid, word): a no-arg property send, or the bare property."""
        if not isinstance(n, dict):
            return False
        if n.get("t") == "Send":
            r2, m2 = I.send_pairs(n)
            if _rid_of(r2) == rid and len(m2) == 1 and not m2[0][1]:
                ks = [k for k in n["kids"] if k.get("t") == "SendMessage"]
                sel = (ks[0].get("kids") or [{}])[0] if ks else {}
                return sel.get("value") == word
        if n.get("t") == "Property":
            return sel_value.get(n.get("name")) == word
        return False

    def _write_expr_op(expr, rid, word):
        """('set'|'clear', bits|None) for a property-write RHS, or None if not flag-shaped."""
        t = expr.get("t") if isinstance(expr, dict) else None
        ks = (expr.get("kids") or []) if isinstance(expr, dict) else []
        if t == "BinOr" and any(_word_read(k, rid, word) for k in ks):
            lits = [I.as_int(k) for k in ks if I.as_int(k) is not None]
            return ("set", _mask_bits(lits[0]) if lits else None)
        if t == "BinAnd" and any(_word_read(k, rid, word) for k in ks):
            neg = [k for k in ks if isinstance(k, dict) and k.get("t") == "BinNot"]
            if neg:
                m = I.as_int((neg[0].get("kids") or [None])[0])
                return ("clear", _mask_bits(m) if m is not None else None)
            lits = [I.as_int(k) for k in ks if I.as_int(k) is not None]
            return ("clear", _mask_bits(~lits[0]) if lits else None)
        if t == "Number" and expr.get("value") == 0:
            return ("clear", None)                     # absolute zero: every known bit clears
        return None

    direct = []                                        # (node, [('flagop', op, rid, word, bits)
    param_clears = []                                  #         | ('keep', msgnode, recv)
    for s in ir.scripts.values():                      #         | ('keepwhole', snapshot)])
        owners = [(o, mn, body) for o in s.objects for mn, body in o.methods.items()]
        owners += [(None, None, body) for body in s.procs.values()]
        for owner, mname, body in owners:
            own_rid = obj_export.get(owner.name) if owner is not None else None
            for node in I.walk(body):
                t = node.get("t")
                ks = node.get("kids") or []
                if t in ("AssignmentBinOr", "AssignmentBinAnd") and ks \
                        and isinstance(ks[0], dict) and ks[0].get("t") == "Property" \
                        and own_rid is not None:
                    word = sel_value.get(ks[0].get("name"))
                    if word not in flag_words:
                        continue
                    val = ks[1] if len(ks) > 1 else None
                    if t == "AssignmentBinOr":
                        m = I.as_int(val)
                        direct.append((node, [("flagop", "set", own_rid, word,
                                               _mask_bits(m) if m is not None else None)]))
                    else:
                        if isinstance(val, dict) and val.get("t") == "BinNot":
                            inner = (val.get("kids") or [None])[0]
                            m = I.as_int(inner)
                            if m is None and isinstance(inner, dict) \
                                    and inner.get("t") == "Variable" \
                                    and inner.get("vtype") == "Parameter" and mname:
                                # `(&= rFlag1 (~ paramK))` -- the mask is the CALLER's literal.
                                # Fanning to every bit here invents clears that break real
                                # one-way flags (measured: RgBasement::resetGuard's callers all
                                # pass masks 1/2, and the fan made the corral flags 340/378
                                # reversible). Defer: the clears land at literal-arg call
                                # sites; only a caller-less method falls back to the fan.
                                param_clears.append((node, own_rid, word, mname,
                                                     inner.get("index")))
                                continue
                            bits = _mask_bits(m) if m is not None else None
                        else:
                            m = I.as_int(val)
                            bits = _mask_bits(~m) if m is not None else None
                        direct.append((node, [("flagop", "clear", own_rid, word, bits)]))
                elif t == "BinAnd" and len(ks) >= 2:
                    lits = [I.as_int(k) for k in ks if I.as_int(k) is not None]
                    if not lits:
                        continue
                    read = None
                    for k in ks:
                        if isinstance(k, dict) and k.get("t") == "Property" \
                                and own_rid is not None \
                                and sel_value.get(k.get("name")) in flag_words:
                            read = (own_rid, sel_value[k["name"]])
                        elif isinstance(k, dict) and k.get("t") == "Send":
                            r2, m2 = I.send_pairs(k)
                            rid2 = _rid_of(r2)
                            if rid2 is not None and len(m2) == 1 and not m2[0][1]:
                                sn = [x for x in k["kids"] if x.get("t") == "SendMessage"]
                                sv = (sn[0].get("kids") or [{}])[0].get("value") if sn else None
                                if sv in flag_words:
                                    read = (rid2, sv)
                    if read:
                        direct.append((node, [("flagop", "test", read[0], read[1],
                                               _mask_bits(lits[0]))]))
                elif t == "Send":
                    recv, msgs = I.send_pairs(node)
                    rid = _rid_of(recv)
                    if rid is None:
                        continue
                    mnodes = [m for m in ks[1:] if m.get("t") == "SendMessage"]
                    plan, hit = [], False
                    for mnode, (sel, params) in zip(mnodes, msgs):
                        sv = (mnode.get("kids") or [{}])[0].get("value")
                        if sv in flag_words and len(params) == 1:
                            op = _write_expr_op(params[0], rid, sv)
                            if op:
                                plan.append(("flagop", op[0], rid, sv, op[1]))
                                hit = True
                                continue
                        plan.append(("keep", mnode))
                    if hit:
                        direct.append((node, plan))
    # resolve deferred param-clears at their literal-arg call sites
    for (bnode, rid, word, mname, pidx) in param_clears:
        found = False
        for s in ir.scripts.values():
            bodies = [m for o in s.objects for m in o.methods.values()] \
                + list(s.procs.values())
            for body in bodies:
                for node in I.walk(body):
                    if node.get("t") != "Send":
                        continue
                    recv, msgs = I.send_pairs(node)
                    if _rid_of(recv) != rid:
                        continue
                    clears = []
                    for sel, params in msgs:
                        if sel != mname or pidx is None or len(params) < pidx:
                            continue
                        m = I.as_int(params[pidx - 1])
                        if m is not None:
                            clears.append(("flagop", "clear", rid, word, _mask_bits(m)))
                    if clears:
                        direct.append((node, [("keepwhole", copy.deepcopy(node))] + clears))
                        found = True
        if not found:
            direct.append((bnode, [("flagop", "clear", rid, word, None)]))

    # a node caught by both passes would be rewritten twice; phase 1 wins
    phase1 = {id(n) for n, _r, _p, _l in sites}
    direct = [(n, p) for (n, p) in direct if id(n) not in phase1]

    # ALLOCATION ORDER IS REGISTER IDENTITY. The keys the accessor spelling has always found,
    # in the order it has always found them, allocate FIRST -- the numbers the tests and docs
    # pin (338, 340, 378...) must not shift. Name-receiver accessor sites come next, then the
    # direct-spelling keys; only genuinely new bits get new numbers. (Measured the hard way:
    # letting the new sites interleave renumbered the whole store and the user-confirmed
    # letter row dissolved into noise.)
    synth_base, index = max_gi + 1, {}
    for want_legacy in (True, False):
        for _n, _r, plan, legacy in sites:
            if legacy != want_legacy:
                continue
            for p in plan:
                if p[0] == "flag":
                    for k in p[2]:
                        index.setdefault(k, synth_base + len(index))
    for _n, plan in direct:
        for p in plan:
            if p[0] == "flagop" and p[4]:
                for b in p[4]:
                    index.setdefault((p[2], p[3], b), synth_base + len(index))
    BOOL_GLOBALS.update(index.values())
    try:
        # The map back, for the same reason every other store records one: the ANALYSIS never
        # needs to know these registers were property-word bits, but a PATCH has to find and
        # spell the game's own `tstFlag:/setFlag: <word> <mask>` site -- and the flag-block
        # renderer needs to know these are NOT proc-flag numbers (the phantom-spelling class).
        ir._prop_flag_index = {gi: k for k, gi in index.items()}
        ir._prop_flag_sels = {op: sel for sel, op in accessors.items()}
        # ...and the selector number->NAME map as THIS pass saw it (pre-rewrite: the Selector
        # nodes carrying both die with the lowering, so a later walk cannot rebuild it). The
        # patcher needs it to spell the owner's DIRECT property write -- `(|= rFlag1 $0002)`
        # is matched by name in source while the store's identity is the number.
        ir._sel_names = {v: k for k, v in sel_value.items()}
    except Exception:                                      # noqa: BLE001
        pass

    def _lower_one(op, keys):
        gis = [index[k] for k in keys]
        if op == "test":
            reads = [{"t": "Variable", "vtype": "Global", "index": g} for g in gis]
            return [reads[0] if len(reads) == 1 else {"t": "Or", "kids": reads}]
        val = 1 if op == "set" else 0
        return [{"t": "Assignment",
                 "kids": [{"t": "Variable", "vtype": "Global", "index": g},
                          {"t": "Number", "value": val}]} for g in gis]

    lowered = 0
    for node, recv, plan, _legacy in sites:
        parts = []
        for p in plan:
            if p[0] == "flag":
                parts += _lower_one(p[1], p[2])
            else:
                # deep-copied: the receiver would otherwise be one dict shared by every kept
                # message, and the walkers assume a tree
                parts.append({"t": "Send", "kids": [copy.deepcopy(recv), p[1]]})
        new = parts[0] if len(parts) == 1 else {"t": "List", "kids": parts}
        node.clear()
        node.update(new)
        lowered += sum(1 for p in plan if p[0] == "flag")

    def _keys_for(rid, word, bits):
        """Concrete index keys for a flag op; a None mask fans over every known bit."""
        if bits is not None:
            return [(rid, word, b) for b in bits if (rid, word, b) in index]
        return sorted(k for k in index if k[0] == rid and k[1] == word)

    for node, plan in direct:
        parts = []
        for p in plan:
            if p[0] == "flagop":
                keys = _keys_for(p[2], p[3], p[4])
                if keys:
                    parts += _lower_one(p[1], keys)
                    lowered += 1
            elif p[0] == "keepwhole":
                parts.append(p[1])                     # the pre-rewrite snapshot of the call
            else:
                recv = node["kids"][0] if node.get("kids") else None
                parts.append({"t": "Send", "kids": [copy.deepcopy(recv), p[1]]})
        if not parts:
            continue
        new = parts[0] if len(parts) == 1 else {"t": "List", "kids": parts}
        node.clear()
        node.update(new)
    return synth_base, lowered, len(index)


def derive_oneof(ir):
    """Names of procedures that are MEMBERSHIP TESTS -- `f(x, a, b, c)` = "is x one of a,b,c?".

    SCI's system script ships one (KQ6 `proc999_5`), and games lean on it for both room-set
    dispatch and ordinary guards. Recognised STRUCTURALLY, never by name or number, because the
    proc's index differs per game: the body loops over the variadic argument list comparing the
    FIRST parameter against successive elements of the SECOND (`[param2 temp]`, the &rest block)
    and returns from inside the loop.

        (procedure (proc999_5 param1 param2 &tmp temp0)
            (for ((= temp0 0)) (< temp0 (- argc 1)) ((++ temp0))
                (if (== param1 [param2 temp0]) (return (or param1 1))))
            (return 0))
    """
    out = set()
    for s in ir.scripts.values():
        for name, body in s.procs.items():
            for lp in (n for n in I.walk(body) if I.control_shape(n)[0] == "loop"):
                inner = list(I.walk(lp))
                if not any(n.get("t") == "Return" for n in inner):
                    continue
                for n in inner:
                    if n.get("t") != "Eq":
                        continue
                    ks = n.get("kids") or []
                    if len(ks) < 2:
                        continue
                    sides = {0: None, 1: None}
                    for i, k in enumerate(ks[:2]):
                        if not isinstance(k, dict):
                            continue
                        if k.get("t") == "Variable" and k.get("vtype") == "Parameter":
                            sides[i] = ("param", k.get("index"))
                        elif k.get("t") == "ComplexVariable":
                            b = (k.get("kids") or [None])[0]
                            if (isinstance(b, dict) and b.get("t") == "Variable"
                                    and b.get("vtype") == "Parameter"):
                                sides[i] = ("rest", b.get("index"))
                    kinds = {v[0] for v in sides.values() if v}
                    if kinds == {"param", "rest"}:
                        out.add(name)
                        break
    return out


def oneof_terms(node, oneof):
    """`f(x, a, b, c)` with f a membership proc -> (x_node, [a, b, c]) of LITERAL values, else None."""
    if not (isinstance(node, dict) and node.get("t") in ("PublicCall", "LocalCall")):
        return None
    if node.get("name") not in oneof:
        return None
    ks = node.get("kids") or []
    if len(ks) < 2:
        return None
    vals = [I.as_int(k) for k in ks[1:]]
    if not vals or any(v is None for v in vals):
        return None
    return ks[0], vals


def derive_region_map(ir, room_object_of):
    """region-script -> {rooms that activate it}, covering BOTH spellings of `setRegions:`.

    SCI0 puts it in each room: `(self setRegions: 7)` inside room N means region 7 covers {N}.
    SCI1.1 hoists it into ONE central dispatcher keyed on the room being entered --

        ((proc999_5 param1 600 605 615 ... 690)      ; is the new room one of these?
            ((ScriptID param1) setRegions: 70))      ; then it is in the realm-of-the-dead region

    -- so the room set lives in the guard's membership test, not in the enclosing object. Both
    are the same fact; only the indirection differs. Detected by shape: a `setRegions:` whose
    receiver is selected by a VARIABLE takes its rooms from a membership test on that same
    variable in the path condition. `room_object_of(script)` supplies the SCI0 fallback.

    Without this KQ6 derives ZERO regions and every region script goes unlifted -- 17 machines,
    18 `newRoom` calls and 13 flag ops, including the whole `rLab` catacombs controller."""
    oneof = derive_oneof(ir)
    out = {}

    def var_key(n):
        """Identity of the variable selecting the room, so guard and receiver can be matched."""
        if isinstance(n, dict) and n.get("t") == "Variable":
            return (n.get("vtype"), n.get("index"))
        return None

    def receiver_var(recv):
        if not (isinstance(recv, dict) and recv.get("t") in
                ("KernelCall", "PublicCall", "LocalCall")):
            return None
        if recv.get("name") != "ScriptID":
            return None
        ks = recv.get("kids") or []
        return var_key(ks[0]) if ks else None

    def visit(node, tests, home):
        """Walk carrying the RAW condition nodes. `walk_stream` cannot serve here: it converts
        each test through `atom()`, which renders the membership call OPAQUE and throws away the
        very argument list we need."""
        shape = I.control_shape(node)
        kind = shape[0]
        if kind == "seq":
            for k in shape[1]:
                visit(k, tests, home)
            return
        if kind == "branch":
            for conds, body in shape[1]:
                visit(body, tests + [t for (t, pol) in conds if pol], home)
            return
        if kind == "loop":
            for k in shape[1:]:
                visit(k, tests, home)
            return
        if node is None:
            return
        if node.get("t") == "Send":
            recv, msgs = I.send_pairs(node)
            regs = [v for sel, ps in msgs if sel == "setRegions"
                    for v in (I.as_int(p) for p in ps) if v is not None]
            if regs:
                rv = receiver_var(recv)
                if rv is None:
                    # SCO0: the region covers the room this code lives in.
                    if home is not None:
                        for r in regs:
                            out.setdefault(r, set()).add(home)
                else:
                    # SCI1.1: the room set is in the membership test guarding this call.
                    rooms = set()
                    for t in tests:
                        for sub in I.walk(t):
                            got = oneof_terms(sub, oneof)
                            if got and var_key(got[0]) == rv:
                                rooms |= set(got[1])
                    for r in regs:
                        if rooms:
                            out.setdefault(r, set()).update(rooms)
        for k in node.get("kids", ()) or ():
            visit(k, tests, home)

    for snum, s in ir.scripts.items():
        home = snum if room_object_of(s) is not None else None
        for o in s.objects:
            for _mn, body in o.methods.items():
                visit(body, [], home)
    return out


def _prop_receiver_script(ir, recv):
    """The script whose object this send addresses, or None if it is not statically one object.

    TWO SPELLINGS of the same thing, and a game mixes them freely. `(ScriptID s n)` names script
    s's nth export. A bare Object reference names an object by NAME, and when that name belongs to
    exactly one object in the whole game it is just as static -- there is no second instance for it
    to be confused with, which is the only thing the restriction ever guarded against.

    KQ6's rm407 and rm409 address the SAME object both ways: `((ScriptID 30 0) seenByMino:)` and
    `(rLab seenSecretLatch: 1)`, rLab BEING script 30's export 0. Reading only the first spelling
    left half of that object's state invisible -- including `seenSecretLatch`, which is the whole
    reason the hole-in-the-wall matters: you put it up, watch the minotaur go behind the tapestry,
    and that is how the secret door to his lair opens. Both spellings must land on the SAME key or
    they become two registers and neither is the state the game keeps.

    Classes count, and are the case that matters. SCI1.1 regions are routinely declared
    `(class rLab of Rgn)` and used as singletons, and a class reference is its own node type --
    `{"t": "Class", "name": "rLab", "number": 146}` -- so a rule that only looked for `Object`
    dropped exactly the objects this is for. A class is unique BY CONSTRUCTION (one definition per
    species), so it needs no uniqueness test; a plain instance name does."""
    if not isinstance(recv, dict):
        return None
    tgt = ir.script_id_target(recv)
    if tgt:
        return tgt[0]
    if recv.get("t") not in ("Object", "Class") or not recv.get("name"):
        return None
    return _singleton_scripts(ir).get(recv["name"])


def _global_instances(ir):
    """global index -> the object it holds, for globals only ever assigned ONE object.

    The THIRD spelling of `_prop_receiver_script`'s "statically one object". A game keeps its
    long-lived singletons in globals and addresses them there -- `(= global0 ego)` in Main, then
    `(global0 wearingGown:)` in fourteen rooms -- and a global assigned exactly one object
    throughout the game resolves as surely as a `ScriptID` export or a unique name. It is the
    same derivation `_class_globals` already does for the item vocabulary, kept by GLOBAL rather
    than by class because here the question is which object a receiver denotes."""
    cache = getattr(ir, "_global_insts", None)
    if cache is not None:
        return cache
    by_name = {o.name: o for s in ir.scripts.values() for o in s.objects}
    scr = {o.name: s.number for s in ir.scripts.values() for o in s.objects}
    assigned = collections.defaultdict(set)
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") != "Assignment":
                    continue
                ks = n.get("kids") or []
                if len(ks) < 2 or not I.is_global(ks[0]):
                    continue
                src = ks[1]
                if (isinstance(src, dict) and src.get("t") in ("Object", "Class")
                        and src.get("name") in by_name):
                    assigned[ks[0]["index"]].add(src["name"])
    cache = {g: (by_name[next(iter(v))], scr[next(iter(v))])
             for g, v in assigned.items() if len(v) == 1}
    try:
        ir._global_insts = cache
    except Exception:                                      # noqa: BLE001
        pass
    return cache


def _introduced_unused(ir, obj):
    """The properties `obj`'s own class INTRODUCES and never itself mentions.

    The bound the global-receiver case needs, and the reason it needs one: a `ScriptID` receiver
    is a script the game WROTE -- a region controller, a cutscene director -- so every property on
    it is game state. A global-held singleton is usually the ENGINE's own instance (the ego, the
    icon bar, User, a Sound), and its property surface is the class library's machinery: `view`,
    `cel`, `loop`, `x`, `y`, `signal`, `scaler`. Lowering those would model the animation system.

    ONE question separates them, asked of the class table alone: *was the property introduced
    here, and does the class library leave it alone?* A property inherited from a more general
    class belongs to that generality's machinery, so only what THIS class adds is a candidate --
    that is what excludes `view`, `cel`, `loop`, `x`, `y`, `signal`, `scaler` in one stroke. And a
    property name that ANY class introducing it also reads or writes in its own methods is that
    library's vocabulary, whichever class you met it on -- which is what excludes `Ego::edgeHit`,
    `Body::currentSpeed`, `User::prevDir`, `IconBar::curInvIcon`, `Narrator::talkWidth` and
    `Sound::number` (Sound never touches it, but `Rgn` and `Locale` introduce the same name and
    do). What is left is a slot introduced at the leaf for OTHER code to use -- a state variable.

    MEASURED, whole corpus: LSL2 none, KQ4 none, KQ6 none, LB2 exactly two --
    `ego.wearingGown` (script 19) and `IconBar.walkIconItem`. The Dagger of Amon Ra gates its
    ACT 1 -> ACT 2 break on the first of them (`rm250.sc:71`, `(and (== global12 300) (global0
    wearingGown:)) -> sACTBREAK -> newRoom: 26`), and the only thing that sets it is the speakeasy
    restroom's `sLauraChanges`, which costs the evening gown. Three of the four games contribute
    nothing, which is what a real store looks like rather than a fitted one."""
    byspec = _class_index(ir)
    cls = obj if obj.is_class else byspec.get(obj.super)
    if cls is None:
        return frozenset()
    own = _class_introduces(ir).get(cls.species, frozenset())
    used = _library_used_props(ir)
    return frozenset(p for p in own if p not in used)


def _class_introduces(ir):
    """species -> the properties that class adds to what it inherits."""
    cache = getattr(ir, "_class_new_props", None)
    if cache is not None:
        return cache
    byspec = _class_index(ir)
    cache = {}
    for spec, o in byspec.items():
        inherited, cur = set(), byspec.get(o.super)
        while cur is not None and cur.species != o.species:
            inherited |= set(cur.props)
            nxt = byspec.get(cur.super)
            if nxt is cur:
                break
            cur = nxt
        cache[spec] = frozenset(set(o.props) - inherited)
    try:
        ir._class_new_props = cache
    except Exception:                                      # noqa: BLE001
        pass
    return cache


def _library_used_props(ir):
    """Property NAMES some class that introduces them also uses in its own methods."""
    cache = getattr(ir, "_lib_used_props", None)
    if cache is not None:
        return cache
    intro = _class_introduces(ir)
    byspec = _class_index(ir)
    cache = frozenset(p for spec, props in intro.items() for p in props
                      if _mentions_prop(byspec[spec], p))
    try:
        ir._lib_used_props = cache
    except Exception:                                      # noqa: BLE001
        pass
    return cache


def _class_index(ir):
    """species -> class object."""
    cache = getattr(ir, "_class_by_species", None)
    if cache is None:
        cache = {o.species: o for s in ir.scripts.values() for o in s.objects if o.is_class}
        try:
            ir._class_by_species = cache
        except Exception:                                  # noqa: BLE001
            pass
    return cache


def _mentions_prop(cls, prop):
    """Does any method of `cls` name `prop` -- as its own property, or as a selector?"""
    for body in cls.methods.values():
        for n in I.walk(body):
            if (isinstance(n, dict) and n.get("name") == prop
                    and n.get("t") in ("Variable", "Property", "Selector")):
                return True
    return False


def derive_global_props(ir):
    """`{(script, selector)}` for the property store reached through a GLOBAL-held singleton.

    Same store as `derive_obj_props` and the same discovery rule -- a property is state if the
    game both WRITES it with a constant and READS it back -- with the receiver resolved one more
    way (`_global_instances`) and the eligible properties bounded by `_introduced_unused`, which
    is where the whole justification for that widening lives."""
    reads, writes = collections.Counter(), collections.Counter()
    ginst = _global_instances(ir)
    if not ginst:
        return set()
    allowed = {g: (scr, _introduced_unused(ir, o)) for g, (o, scr) in ginst.items()}
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") != "Send":
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                          # noqa: BLE001
                    continue
                hit = allowed.get(recv["index"]) if I.is_global(recv) else None
                if hit is None:
                    continue
                scr, props = hit
                for sel, ps in msgs:
                    if sel not in props:
                        continue
                    if ps and I.as_int(ps[0]) is not None:
                        writes[(scr, sel)] += 1
                    elif not ps:
                        reads[(scr, sel)] += 1
    return set(reads) & set(writes)


def _global_prop_key(ir, recv, sel):
    """`(script, selector)` if this send addresses a global-held singleton's state property."""
    if not (isinstance(recv, dict) and I.is_global(recv)):
        return None
    hit = _global_instances(ir).get(recv["index"])
    if hit is None:
        return None
    obj, scr = hit
    return (scr, sel) if sel in _introduced_unused(ir, obj) else None


def _singleton_scripts(ir):
    """{name: script} for names that name exactly ONE object or class in the game."""
    cache = getattr(ir, "_singleton_objs", None)
    if cache is None:
        owners = collections.defaultdict(set)
        for s in ir.scripts.values():
            for o in s.objects:
                owners[o.name].add(s.number)
        cache = {n: next(iter(v)) for n, v in owners.items() if len(v) == 1}
        try:
            ir._singleton_objs = cache
        except Exception:                                  # noqa: BLE001
            pass
    return cache


def derive_obj_props(ir):
    """`{(script, export, selector)}` for object PROPERTIES the game uses as state.

    The third container for the same idea. We already model state kept in globals
    (`gating_registers`), in a bit-array (`derive_flags` / `derive_prop_flags`) and in an item's
    own property (`item_property_registers`); this is state kept in an ORDINARY object's property,
    which SCI1.1 leans on because a region object outlives the rooms inside it. KQ6's catacombs
    decide the minotaur fight entirely this way -- `(ScriptID 30 0) scarfOnMino: 1` when you show
    the scarf, `((ScriptID 30 0) seenByMino:)` to branch on it.

    Discovered by the SAME rule the other three use: a property is state if the game both WRITES
    it with a constant and READS it back. Nothing here names a selector, so a game's own property
    names need no catalogue. Only receivers that resolve statically -- `(ScriptID s n)`, a
    singleton reached from another script -- are eligible, because two instances of a class would
    otherwise be merged into one register."""
    reads, writes = collections.Counter(), collections.Counter()
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if n.get("t") != "Send":
                    continue
                try:
                    recv, msgs = I.send_pairs(n)
                except Exception:                          # noqa: BLE001
                    continue
                rs = _prop_receiver_script(ir, recv)
                if rs is None:
                    continue
                for sel, ps in msgs:
                    if sel is None:
                        continue
                    if ps and I.as_int(ps[0]) is not None:
                        writes[(rs, sel)] += 1
                    elif not ps:
                        reads[(rs, sel)] += 1
    return set(reads) & set(writes)


def _split_chained_writes(ir, pairs, split_chains):
    """Break `(recv a: 1 <prop>: 2 c: 3)` into `[(recv a: 1), <prop write>, (recv c: 3)]`, so a
    property write buried in a chain can be lowered like any other.

    Only in STATEMENT position -- a direct kid of a statement `List` -- which is the whole safety
    argument. There the send's value is discarded, so splitting one send into several changes
    nothing about what runs, in what order, or under what condition; in an EXPRESSION a `List`
    where a value was expected would be a lie. That position test is also why this cannot be done
    from inside the plain node walk: it is a fact about the parent, not the node.

    Runs are preserved rather than reordered (`a:` before the write, `c:` after) because sibling
    effects under one path condition are read as a sequence, and one of them may be a `newRoom:`
    or a `put:` whose order against the write is the whole content of the statement."""
    if not split_chains:
        return 0
    lists = []
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if node.get("t") == "List" and node.get("kids"):
                    lists.append(node)
    n_split = 0
    for lst in lists:
        out, changed = [], False
        for kid in lst["kids"]:
            pieces = _split_one(ir, kid, pairs, split_chains) if isinstance(kid, dict) else None
            if pieces is None:
                out.append(kid)
            else:
                out.extend(pieces)
                changed = True
                n_split += 1
        if changed:
            lst["kids"] = out
    return n_split


def _split_one(ir, node, pairs, split_chains):
    """One chained send -> the list it becomes, or None if there is nothing here to split."""
    if node.get("t") != "Send":
        return None
    kids = node.get("kids") or []
    if len(kids) < 3:                                      # receiver + one message: nothing to do
        return None
    recv = kids[0]
    try:
        msgs = I.send_pairs(node)[1]
    except Exception:                                      # noqa: BLE001
        return None
    if len(msgs) != len(kids) - 1:
        return None
    def key_of(sel, ps):
        if not ps or I.as_int(ps[0]) is None:              # only CONSTANT writes are lowerable
            return None
        k = _global_prop_key(ir, recv, sel)
        if k is None:
            rs = _prop_receiver_script(ir, recv)
            k = (rs, sel) if rs is not None else None
        return k if (k in pairs and k in split_chains) else None
    if not any(key_of(sel, ps) for sel, ps in msgs):
        return None
    out, run = [], []
    def flush():
        if run:
            out.append({"t": "Send", "kids": [copy.deepcopy(recv)] + run[:]})
            run.clear()
    for sm, (sel, ps) in zip(kids[1:], msgs):
        k = key_of(sel, ps)
        if k is None:
            run.append(sm)
            continue
        flush()
        # A one-message Send, not the final Assignment: the pass that follows resolves the key to
        # a register index, and there must be exactly ONE place that does that.
        out.append({"t": "Send", "kids": [copy.deepcopy(recv), sm]})
    flush()
    return out


def lower_obj_props(ir, pairs, split_chains=()):
    """Rewrite resolved `(ScriptID s n) <prop>:` reads and constant writes into synthetic globals,
    so object-property state reaches the register machinery as ordinary registers.

    Same shape as `lower_flags` / `lower_prop_flags`, and deliberately so: every store we model
    ends up as a global, and nothing downstream learns a new concept. Non-constant writes are
    left alone -- an unmodelled write can only miss a stranding, never invent one.

    ⚠️ CHAINED SENDS ARE THE EXCEPTION TO THAT REASSURANCE, and `split_chains` is why the
    argument exists. `(global0 put: 32 wearingGown: 1 setMotion: ...)` cannot be rewritten in
    place -- the node carries three messages and a Global node carries one -- so it used to be
    skipped, which is not "missing a write" but HALF A STORE: a register whose reads are modelled
    and whose only setter is not reads 0 forever, and a permanent 0 fabricates a seal. Exactly
    what `derive_room_locals` refuses to do for the same reason. Keys listed in `split_chains`
    are split instead (see `_split_chained_writes`), and the rest keep the old behaviour --
    curing those is a change with its own blast radius (283 more sites in KQ6, 90 in KQ4) and
    belongs to its own measurement, not to this one."""
    if not pairs:
        return 0, 0
    # FIRST, so the pass below sees plain one-message sends where a chain used to be.
    _split_chained_writes(ir, pairs, split_chains)
    max_gi, sites = 0, []
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for node in I.walk(body):
                if I.is_global(node):
                    max_gi = max(max_gi, node["index"])
                    continue
                if node.get("t") != "Send":
                    continue
                try:
                    recv, msgs = I.send_pairs(node)
                except Exception:                          # noqa: BLE001
                    continue
                if len(msgs) != 1:
                    continue                               # chained: rewriting drops the rest
                sel, ps = msgs[0]
                rs = _prop_receiver_script(ir, recv)
                # A `ScriptID`/named receiver keys on its script; a GLOBAL-held one resolves
                # through `_global_prop_key`, which also applies that case's property bound.
                # Never both: `_prop_receiver_script` only accepts Object/Class/ScriptID nodes.
                key = (rs, sel) if rs is not None else _global_prop_key(ir, recv, sel)
                if key is None or key not in pairs:
                    continue
                if not ps:
                    sites.append((node, key, None))
                elif I.as_int(ps[0]) is not None:
                    sites.append((node, key, I.as_int(ps[0])))
    base, index = max_gi + 1, {}
    for _n, key, _v in sites:
        index.setdefault(key, base + len(index))
    try:
        # Keep the map so a synthetic register can be named back to the property it stands for.
        # Every other store's registers are traceable (a flag has its number, a global its index);
        # these were anonymous, which makes any question about them start with re-deriving this.
        ir._obj_prop_index = {gi: key for key, gi in index.items()}
    except Exception:                                      # noqa: BLE001
        pass
    # A property the game only ever writes 0 or 1 to is a BOOLEAN, so `!= 0` is exactly `== 1`.
    # That is how SCI spells most of these -- `(if ((ScriptID 30 0) scarfOnMino:) ...)` -- and
    # without it a "this happened" property can never constrain anything, since `required_values`
    # ignores `!=`. Derived from the values actually written, not assumed.
    written = collections.defaultdict(set)
    for _n, key, v in sites:
        if v is not None:
            written[key].add(v)
    BOOL_GLOBALS.update(index[k] for k, vs in written.items() if vs <= {0, 1})
    for node, key, val in sites:
        gi = index[key]
        node.clear()
        if val is None:
            node.update({"t": "Variable", "vtype": "Global", "index": gi})
        else:
            node.update({"t": "Assignment",
                         "kids": [{"t": "Variable", "vtype": "Global", "index": gi},
                                  {"t": "Number", "value": val}]})
    return len(sites), len(index)


def derive_room_locals(ir, rooms):
    """`{(script, idx)}` -- ROOM-script LOCALs the game uses as cross-machine state.

    The FIFTH container for the same idea, and the 3rd-recorded gap it closes: a latch shared
    between a room's machines through a script local. KQ6's rm690 is the motivating case --
    `introScript` raises `local0` before the player's only window, `issueChallenge` (the gauntlet)
    is the one thing that clears it, and `lord::doVerb 13` arms `holdUpMirror` only while it is
    clear -- so the local IS the gauntlet's requirement, and a store we do not model made that
    link invisible (the earlier instances: `liftTapestry`'s L1, `huntersLamp`'s rm520 `doit`).

    Discovered by the same rule as every other store -- written with a CONSTANT and read back --
    plus the one discriminator this container needs: the value must CROSS a method scope (some
    scope reads it that did not write it, or writes it that did not read it). A loop counter or
    a cue-latch confined to one body is a machine-internal counter, which the machine compiler
    already carries as a CTR; lowering those too would re-plumb state that is modelled and
    validated. A local with any NON-constant write (`++`, arithmetic, a copied value) is skipped
    outright rather than half-lowered: a register missing one of its writes can fabricate a seal,
    and half a store is worse than none."""
    out = set()
    for sn in sorted(set(rooms) & set(ir.scripts)):
        s = ir.scripts[sn]
        if not s.locals:
            continue
        writes = collections.defaultdict(set)      # idx -> scopes writing a constant
        reads = collections.defaultdict(set)       # idx -> scopes reading it
        tainted = set()                            # idx with a non-constant write
        scopes = [((o.name, mn), b) for o in s.objects for mn, b in o.methods.items()]
        scopes += [(("proc", pn), b) for pn, b in s.procs.items()]
        for sid, body in scopes:
            def visit(n):
                if not isinstance(n, dict):
                    return
                kids = n.get("kids") or []
                # `(++ local1)` / `(-- local2)` are Increment/Decrement nodes, NOT Assignment* --
                # missing them is how KQ4's stepped ocean-grid locals (rm31's cell coordinates)
                # once derived as lowerable, which rewrote them out of `handler_locals` and killed
                # `grid.analyze` (gates {}), and with it every whale joint stranding. A stepped
                # local is a counter; counters are the machine compiler's, not this store's.
                if n.get("t") in ("Increment", "Decrement"):
                    for k in kids:
                        if (isinstance(k, dict) and k.get("t") == "Variable"
                                and k.get("vtype") == "Local"):
                            tainted.add(k["index"])
                if n.get("t", "").startswith("Assignment") and kids:
                    lhs = kids[0]
                    if (isinstance(lhs, dict) and lhs.get("t") == "Variable"
                            and lhs.get("vtype") == "Local"):
                        idx = lhs["index"]
                        rhs = kids[1] if len(kids) > 1 else None
                        v = I.as_int(rhs) if rhs is not None else None
                        # `(= local0 1)` is a constant write. A compound op (`AssignmentAdd`,
                        # `AssignmentSub`, ...) or a computed rhs taints the local outright.
                        if n["t"] == "Assignment" and v is not None:
                            writes[idx].add(sid)
                        else:
                            tainted.add(idx)
                        for k in kids[1:]:
                            visit(k)
                        return
                if (n.get("t") == "Variable" and n.get("vtype") == "Local"):
                    reads[n["index"]].add(sid)
                for k in kids:
                    visit(k)
            visit(body)
        for idx in sorted((set(writes) & set(reads)) - tainted):
            if len(writes[idx] | reads[idx]) <= 1:
                continue
            # A local whose EVERY write sits in an `init` scope is a per-visit CONSTANT, not
            # state: it is assigned on arrival and never changes mid-visit, so the entry reset IS
            # its entire semantics and lowering it models nothing new -- while destroying the
            # const-local SHAPE downstream readers depend on. KQ4's rm31 `local12` is the case
            # that forced this: it is the drown-counter's death threshold, and `grid._counter_bound`
            # derives the walk budget as "the room's largest const-local" (the compare itself is
            # local==local, deliberately opaque). Lowering it cost the grid its budget, the ocean
            # its gates, and the whale its every joint stranding. A LATCH is written from an
            # event -- a machine state, a handler -- and those still lower (rm690's local0).
            if all(mn == "init" for (_obj, mn) in writes[idx]):
                continue
            out.add((sn, idx))
    return out


def lower_room_locals(ir, keys):
    """Rewrite the derived room locals into synthetic globals, IN PLACE -- same shape as
    `lower_flags` / `lower_prop_flags` / `lower_obj_props`, so nothing downstream learns a new
    concept. Every `Variable Local` node of a lowered (script, idx) becomes the synthetic global,
    which turns constant assignments into register writes and guard reads into register tests.

    The one semantics a local adds: the script UNLOADS when the player leaves the room, so the
    local resets to its declared initial value on every entry. That is exactly an unconditional
    entry write, so the reset is recorded per room in `ir._room_local_resets` and opmodel merges
    it into `init_writes` -- the same channel arrival writes already use, commit semantics and
    all."""
    if not keys:
        return 0, 0
    max_gi = 0
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if I.is_global(n):
                    max_gi = max(max_gi, n["index"])
    base = max_gi + 1
    index = {k: base + i for i, k in enumerate(sorted(keys))}
    resets = {}
    written = collections.defaultdict(set)
    sites = 0
    for (sn, idx), gi in index.items():
        s = ir.scripts[sn]
        init = 0
        for l in s.locals:
            if l.get("index") == idx:
                v = l.get("value", 0)
                init = v - 65536 if isinstance(v, int) and v > 32767 else (v or 0)
                break
        resets.setdefault(sn, {})[gi] = init
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            for n in I.walk(body):
                if (isinstance(n, dict) and n.get("t") == "Assignment" and n.get("kids")):
                    lhs, rhs = n["kids"][0], (n["kids"][1] if len(n["kids"]) > 1 else None)
                    if (isinstance(lhs, dict) and lhs.get("t") == "Variable"
                            and lhs.get("vtype") == "Local" and lhs.get("index") == idx):
                        v = I.as_int(rhs) if rhs is not None else None
                        if v is not None:
                            written[gi].add(v)
                if (isinstance(n, dict) and n.get("t") == "Variable"
                        and n.get("vtype") == "Local" and n.get("index") == idx):
                    n["vtype"] = "Global"
                    n["index"] = gi
                    sites += 1
    for gi, vals in written.items():
        if vals <= {0, 1}:
            BOOL_GLOBALS.add(gi)
    try:
        ir._room_local_index = {gi: k for k, gi in index.items()}
        ir._room_local_resets = resets
    except Exception:                                      # noqa: BLE001
        pass
    return sites, len(index)


def _handle_aliases(body, item_of_receiver):
    """`{(vtype, index): item}` for SCI's cache-the-handle idiom, within ONE method body.

        (= temp0 (global9 at: 11))                      ; temp0 IS the skull from here on
        (temp0 setCursor: 990 0 9 loop: 0 cel: 10 state: (| (temp0 state:) $000c))

    Without this the send above has no recognisable receiver, so the bit-SET is invisible while
    the matching CLEAR (written `(self state: (& (self state:) $fff7))` inside the item's own
    `cue`) is captured -- and half a store is worse than none. A register whose only modelled
    write is the value every read REJECTS cannot open anything, so promoting it fabricates a
    seal: KQ6's skull is the case, and with only the clear captured `catchNiteMare` -- the ONLY
    way into the realm of the dead -- became unreachable.

    Deliberately the weakest form that settles it. A variable counts only if EVERY assignment to
    it in the body names the SAME item; one that is reassigned, or assigned anything else, is not
    an alias and is left alone. No flow analysis, no ordering: an alias that is re-pointed
    mid-body simply does not qualify.

    Same "resolve the alias through what the game itself says" discipline the store vocabulary is
    built on -- this is the local-variable spelling of it."""
    out, spoilt = {}, set()
    for n in I.walk(body):
        if n.get("t") != "Assignment":
            continue
        dst, src = (n.get("kids") or [None, None])[:2]
        if not (isinstance(dst, dict) and I.is_local_or_temp(dst)):
            continue
        key = (dst["vtype"][0], dst["index"])
        it = item_of_receiver(src)
        if it is None or (key in out and out[key] != it):
            spoilt.add(key)                 # assigned something else too -- not a stable alias
        else:
            out[key] = it
    return {k: v for k, v in out.items() if k not in spoilt}


def _alias_resolver(body, item_of_receiver):
    """`item_of_receiver` widened to see this body's cached item handles. See `_handle_aliases`."""
    aliases = _handle_aliases(body, item_of_receiver)
    if not aliases:
        return item_of_receiver

    def resolve(recv):
        it = item_of_receiver(recv)
        if it is not None:
            return it
        if isinstance(recv, dict) and I.is_local_or_temp(recv):
            return aliases.get((recv["vtype"][0], recv["index"]))
        return None
    return resolve


def derive_item_bit_flags(ir, item_of_receiver):
    """`{(item, prop, bit)}` for item state kept as BIT FLAGS in the item's own property.

    The fourth store again, in the spelling `item_property_registers` cannot see. That function
    looks only at `(Inv at: N) <prop>` sends, but an item maintains its OWN state from inside its
    OWN methods, where `self` is the item and a bare property reference is its own property:

        (instance skull of Kq6InvItem
          (method (cue)   (self ... state: (& (self state:) $fff7)))    ; clear bit 3
          (method (doVerb param1) (if (& state $0004) ...)))            ; read bit 2

    Measured on KQ6: the only `(Inv at: N) state:` WRITE is the lettuce and all five READS are the
    skull, so written-and-read never intersected and the whole store dropped out -- while the
    skull's bits are what gate the realm-of-the-dead cutscene.

    Same "written AND read" rule as every other store, and the same bit-in-a-word abstraction as
    `derive_prop_flags`; only the container differs. Returns the (item, prop, bit) triples that are
    both set/cleared and tested."""
    read, written = set(), set()

    def item_of(node, selfitem, of_recv):
        """The item whose property this reads, plus the property name -- or None."""
        if not isinstance(node, dict):
            return None
        if node.get("t") == "Property" and selfitem is not None:
            return (selfitem, node.get("name"))
        if node.get("t") != "Send":
            return None
        try:
            recv, msgs = I.send_pairs(node)
        except Exception:                                   # noqa: BLE001
            return None
        if len(msgs) != 1 or msgs[0][1] or not msgs[0][0]:
            return None
        if isinstance(recv, dict) and recv.get("t") == "Self" and selfitem is not None:
            return (selfitem, msgs[0][0])
        it = of_recv(recv)
        return (it, msgs[0][0]) if it is not None else None

    def bits(mask):
        return [b for b in range(16) if (mask & 0xFFFF) >> b & 1]

    names = {nm: i for i, nm in item_names(ir).items()}
    for s in ir.scripts.values():
        # procedures have no `self`, but `(Inv at: N)` still resolves there -- KQ6 tests the
        # skull's bit from `proc344_1`, so skipping procs lost the only READ of it.
        scopes = [(names.get(re.sub(r"[^0-9A-Za-z]+", "_", o.name).strip("_"))
                   if not o.is_class else None, list(o.methods.values())) for o in s.objects]
        scopes.append((None, list(s.procs.values())))
        for selfitem, bodies in scopes:
            for body in bodies:
                of_recv = _alias_resolver(body, item_of_receiver)
                for n in I.walk(body):
                    t = n.get("t")
                    if t == "BinAnd":                       # a TEST: `(& <prop> MASK)`
                        ks = n.get("kids") or []
                        for a, b in ((ks[0], ks[1]),) if len(ks) > 1 else ():
                            for x, y in ((a, b), (b, a)):
                                got, m = item_of(x, selfitem, of_recv), I.as_int(y)
                                if got and got[1] and m is not None:
                                    read.update((got[0], got[1], bit) for bit in bits(m))
                    elif t == "Send":                       # a WRITE: `(x prop: (| <prop> MASK))`
                        try:
                            recv, msgs = I.send_pairs(n)
                        except Exception:                   # noqa: BLE001
                            continue
                        holder = (selfitem if isinstance(recv, dict) and recv.get("t") == "Self"
                                  else of_recv(recv))
                        if holder is None:
                            continue
                        for sel, ps in msgs:
                            if not ps or not sel:
                                continue
                            v = ps[0]
                            if not (isinstance(v, dict) and v.get("t") in ("BinOr", "BinAnd")):
                                continue
                            for k in (v.get("kids") or []):
                                m = I.as_int(k)
                                if m is None:
                                    continue
                                # a clear is `& ~MASK`, so the literal is the COMPLEMENT
                                mm = m if v["t"] == "BinOr" else (~m) & 0xFFFF
                                written.update((holder, sel, bit) for bit in bits(mm))
    return read & written


def lower_item_bit_flags(ir, flags, item_of_receiver):
    """Rewrite item bit-flag reads and writes into synthetic globals, in place.

    Same destination as every other store -- an ordinary global the register machinery already
    promotes -- so nothing downstream learns a new concept. Two rewrites:

        (& <item.prop> MASK)            ->  a read of the bit's global
        (x ... prop: (| <read> MASK))   ->  the same send WITHOUT that message, followed by the
                                            assignments, so a CHAINED send keeps its other
                                            messages (the skull sets loop/cel/cursor in the very
                                            send that clears its bit).
    """
    if not flags:
        return 0, 0
    max_gi = 0
    for s in ir.scripts.values():
        for body in [b for o in s.objects for b in o.methods.values()] + list(s.procs.values()):
            for n in I.walk(body):
                if I.is_global(n):
                    max_gi = max(max_gi, n["index"])
    index, base = {}, max_gi + 1
    for k in sorted(flags):
        index[k] = base + len(index)
    BOOL_GLOBALS.update(index.values())

    def gread(gi):
        return {"t": "Variable", "vtype": "Global", "index": gi}

    def bits(mask):
        return [b for b in range(16) if (mask & 0xFFFF) >> b & 1]

    names = {nm: i for i, nm in item_names(ir).items()}
    n_read = n_write = 0
    for s in ir.scripts.values():
        scopes = [(names.get(re.sub(r"[^0-9A-Za-z]+", "_", o.name).strip("_"))
                   if not o.is_class else None, list(o.methods.values())) for o in s.objects]
        scopes.append((None, list(s.procs.values())))       # procs: no `self`, but `(Inv at: N)` works
        for selfitem, bodies in scopes:

            def prop_of(node, selfitem=selfitem, of_recv=None):
                if not isinstance(node, dict):
                    return None
                if node.get("t") == "Property" and selfitem is not None:
                    return (selfitem, node.get("name"))
                if node.get("t") != "Send":
                    return None
                try:
                    recv, msgs = I.send_pairs(node)
                except Exception:                           # noqa: BLE001
                    return None
                if len(msgs) != 1 or msgs[0][1] or not msgs[0][0]:
                    return None
                if isinstance(recv, dict) and recv.get("t") == "Self" and selfitem is not None:
                    return (selfitem, msgs[0][0])
                it = (of_recv or item_of_receiver)(recv)
                return (it, msgs[0][0]) if it is not None else None

            for body in bodies:
                # The same cached-handle resolution the DISCOVERY half uses, and it has to be
                # here too or the pair disagrees: a bit the discovery now calls state would have
                # its `(temp0 state: (| ...))` write left unlowered. See [[same-rule-two-places]].
                of_recv = _alias_resolver(body, item_of_receiver)
                for n in I.walk(body):
                    if n.get("t") == "BinAnd":
                        ks = n.get("kids") or []
                        if len(ks) < 2:
                            continue
                        for x, y in ((ks[0], ks[1]), (ks[1], ks[0])):
                            got, m = prop_of(x, of_recv=of_recv), I.as_int(y)
                            if not (got and got[1] and m is not None):
                                continue
                            gs = [index[(got[0], got[1], b)] for b in bits(m)
                                  if (got[0], got[1], b) in index]
                            if not gs:
                                continue
                            new = gread(gs[0]) if len(gs) == 1 else {
                                "t": "Or", "kids": [gread(g) for g in gs]}
                            n.clear()
                            n.update(new)
                            n_read += 1
                            break
                    elif n.get("t") == "Send":
                        try:
                            recv, msgs = I.send_pairs(n)
                        except Exception:                   # noqa: BLE001
                            continue
                        holder = (selfitem if isinstance(recv, dict) and recv.get("t") == "Self"
                                  else of_recv(recv))
                        if holder is None:
                            continue
                        keep, asg = [], []
                        for mnode in (n.get("kids") or [])[1:]:
                            sel = None
                            if isinstance(mnode, dict) and mnode.get("t") == "SendMessage":
                                sn_ = (mnode.get("kids") or [None])[0]
                                sel = sn_.get("name") if isinstance(sn_, dict) else None
                            ps = (mnode.get("kids") or [])[1:] if sel else []
                            v = ps[0] if ps else None
                            done = False
                            if sel and isinstance(v, dict) and v.get("t") in ("BinOr", "BinAnd"):
                                for k in (v.get("kids") or []):
                                    m = I.as_int(k)
                                    if m is None:
                                        continue
                                    mm = m if v["t"] == "BinOr" else (~m) & 0xFFFF
                                    val = 1 if v["t"] == "BinOr" else 0
                                    gs = [index[(holder, sel, b)] for b in bits(mm)
                                          if (holder, sel, b) in index]
                                    for gi in gs:
                                        asg.append({"t": "Assignment",
                                                    "kids": [gread(gi),
                                                             {"t": "Number", "value": val}]})
                                    if gs:
                                        done = True
                                    break
                            if not done:
                                keep.append(mnode)
                        if asg:
                            n_write += len(asg)
                            rest = [n.get("kids")[0]] + keep
                            n.clear()
                            n.update({"t": "List",
                                      "kids": ([{"t": "Send", "kids": rest}] if keep else []) + asg})
    return n_read, n_write


def derive_mask_globals(ir):
    """`{global: universe-of-bits}` for plain globals used ONLY as bit-mask words.

    The SIXTH container, and the simplest: the same bit-in-a-word abstraction as every flag
    store, kept in an ordinary global with no accessor at all -- written `(|= gN $mask)` /
    `(&= gN $mask)` / `(= gN <literal>)`, read by equality against a literal, by bit-test
    `(& gN $mask)`, or bare (truthiness). KQ6's global161 is the instance that forced it: the
    Make-Rain readiness word (bits: isle water $0001, sacred water $0002, tears $0004, the cast
    $0008), whose `== 15` is the other half of the cage sorter's survival condition -- and with
    the `|=` spelling invisible to extract's plain-assignment collection, every state read 0.

    Derived by SHAPE, refusing anything it cannot rewrite exactly:
      * at least one literal-mask `|=`/`&=` write (a counter or a scalar never has one);
      * EVERY appearance is a recognised mask idiom -- the writes above, `(== g lit)` /
        `(!= g lit)`, the already-set test `(== g (| g $mask))`, `(& g $mask)`, or a bare
        boolean read (a kid of Not/And/Or/an `if` test);
      * one arithmetic read, one non-literal write, one `<` compare -- and the global is
        REFUSED, because per-bit lowering would misstate it.

    MEASURED (2026-08-06, the census probe): exactly ONE global in the whole corpus matches --
    KQ6's g161. LSL2/KQ4/Dagger have zero `|=`-written globals at all, so the shape needs no
    extra tightening clauses and the pass is inert everywhere else by construction. The proc
    flag array cannot alias it: KQ6's flags top out at 163 (words g137..g147), short of g161."""
    evid = {}

    def rec(gi):
        return evid.setdefault(gi, {"mask": False, "bits": set(), "bad": False})

    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            consumed = set()
            for n in I.walk(body):
                if id(n) in consumed:
                    continue
                t, ks = n.get("t"), n.get("kids") or []
                shape = _mask_site(n)
                if shape is not None and shape[0] not in ("bare", "bad"):
                    kind, gi, val = shape
                    r = rec(gi)
                    if kind in ("or", "and"):
                        r["mask"] = True
                    if val is not None:
                        r["bits"].update(b for b in range(16) if (val & 0xFFFF) >> b & 1)
                    for k in I.walk(n):
                        consumed.add(id(k))
                    continue
                if shape is not None and shape[0] == "bad":
                    rec(shape[1])["bad"] = True
                    # and FALL THROUGH: a two-global compare condemns both sides, and only
                    # the kid loop below sees the second one
                # Not a shape owner: judge each DIRECT bare-global kid by where it sits. A
                # boolean context (`(not g)`, an `if`/`cond` test) reads truthiness, which
                # per-bit lowering expresses exactly (any observed bit). Anything else -- a
                # call argument, a copy into another variable, an array index, a `switch`
                # head, arithmetic -- consumes the VALUE, which per-bit lowering would
                # misstate, so the global is refused.
                for i, k in enumerate(ks):
                    if not (isinstance(k, dict) and I.is_global(k)):
                        continue
                    if t in ("Not", "And", "Or"):
                        continue
                    if t in ("If", "Case", "While") and i == 0:
                        continue
                    rec(k["index"])["bad"] = True
    return {gi: frozenset(r["bits"]) for gi, r in evid.items()
            if r["mask"] and not r["bad"] and r["bits"]}


def _const_or(n):
    """A literal, or a BinOr over literals, folded -- else None."""
    v = I.as_int(n)
    if v is not None:
        return v
    if isinstance(n, dict) and n.get("t") == "BinOr":
        vals = [_const_or(k) for k in (n.get("kids") or [])]
        if vals and all(v is not None for v in vals):
            out = 0
            for v in vals:
                out |= v
            return out
    return None


def _mask_site(n):
    """Classify one node as a mask-global idiom: `(kind, global, value)` or None.

    Kinds: 'or'/'and' (compound mask write), 'assign' (literal store), 'eq'/'ne' (literal
    compare), 'setq' (`(== g (| g mask))` -- the already-set test), 'test' (`(& g mask)`),
    'bare' (the global itself: truthiness, or an lvalue another shape owns), or ('bad', gi,
    None) for a global written or compared in a way per-bit lowering cannot express. A 'bare'
    at the top of a walk (not consumed by an enclosing shape) is a boolean read -- extract
    reads exactly that as `!= 0` -- so it stays lowerable; genuinely arithmetic uses all
    surface as literal-less compares/writes, which is what 'bad' catches."""
    if not isinstance(n, dict):
        return None
    t, ks = n.get("t"), n.get("kids") or []

    def g_of(x):
        return x["index"] if isinstance(x, dict) and I.is_global(x) else None
    if t in ("AssignmentBinOr", "AssignmentBinAnd") and ks and g_of(ks[0]) is not None:
        m = _const_or(ks[1]) if len(ks) > 1 else None
        gi = g_of(ks[0])
        return ("or" if t == "AssignmentBinOr" else "and", gi, m) if m is not None \
            else ("bad", gi, None)
    if t == "Assignment" and ks and g_of(ks[0]) is not None:
        v = I.as_int(ks[1]) if len(ks) > 1 else None
        # a non-literal store is only 'bad' for a global OTHER shapes made a candidate;
        # scalars assigned computed values simply never qualify (no mask write)
        return ("assign", g_of(ks[0]), v) if v is not None else ("bad", g_of(ks[0]), None)
    if t in ("AssignmentAdd", "AssignmentSub", "AssignmentMul", "AssignmentDiv",
             "AssignmentShl", "AssignmentShr", "AssignmentXor", "AssignmentMod",
             "Increment", "Decrement") and ks and g_of(ks[0]) is not None:
        return ("bad", g_of(ks[0]), None)
    if t in ("Eq", "Ne") and len(ks) == 2:
        for x, y in ((ks[0], ks[1]), (ks[1], ks[0])):
            gi = g_of(x)
            if gi is None:
                continue
            v = I.as_int(y)
            if v is not None:
                return ("eq" if t == "Eq" else "ne", gi, v)
            # `(== g (| g $mask))` -- "are these bits already set"
            if isinstance(y, dict) and y.get("t") == "BinOr":
                yks = y.get("kids") or []
                if any(g_of(k) == gi for k in yks):
                    lits = [_const_or(k) for k in yks if g_of(k) != gi]
                    if lits and all(v is not None for v in lits):
                        m = 0
                        for v in lits:
                            m |= v
                        return ("setq" if t == "Eq" else "setq_ne", gi, m)
            return ("bad", gi, None)
    if t in ("Lt", "Le", "Gt", "Ge", "Ugt", "Uge", "Ult", "Ule") and len(ks) == 2:
        for x in ks:
            if g_of(x) is not None:
                return ("bad", g_of(x), None)
    if t == "BinAnd" and len(ks) == 2:
        for x, y in ((ks[0], ks[1]), (ks[1], ks[0])):
            gi = g_of(x)
            if gi is not None:
                m = _const_or(y)
                return ("test", gi, m) if m is not None else ("bad", gi, None)
    if t == "Variable" and n.get("vtype") == "Global":
        return ("bare", n["index"], None)
    return None


def lower_mask_globals(ir, cands):
    """Rewrite a mask global's every site into per-bit synthetic globals, in place.

    Same destination as every other store: each bit becomes an ordinary boolean register, so a
    `|=` is a set of plain writes, `(== g 15)` is a conjunction of four bit reads, and nothing
    downstream learns a new concept. The identity map back (`ir._mask_global_index`) lets
    `guards.render_register` spell a bit in the game's own source -- `(& global161 $0001)` --
    because unlike every other lowered store these registers DO have a plain-global spelling."""
    if not cands:
        return 0, 0, 0
    max_gi = 0
    for s in ir.scripts.values():
        for body in [b for o in s.objects for b in o.methods.values()] + list(s.procs.values()):
            for n in I.walk(body):
                if I.is_global(n):
                    max_gi = max(max_gi, n["index"])
    base, index = max_gi + 1, {}
    for gi in sorted(cands):
        for b in sorted(cands[gi]):
            index[(gi, b)] = base + len(index)
    BOOL_GLOBALS.update(index.values())
    try:
        ir._mask_global_index = {sg: k for k, sg in index.items()}
    except Exception:                                      # noqa: BLE001
        pass

    def gread(sg):
        return {"t": "Variable", "vtype": "Global", "index": sg}

    def sets(gi, bs, val):
        return [{"t": "Assignment", "kids": [gread(index[(gi, b)]),
                                             {"t": "Number", "value": val}]} for b in bs]

    def conj(gi, want_pattern):
        """And over the universe: bit b read positively where the pattern has it, negated
        where it does not -- `(== g V)` is exactly 'the observed bits spell V'."""
        terms = [gread(index[(gi, b)]) if (want_pattern >> b) & 1
                 else {"t": "Not", "kids": [gread(index[(gi, b)])]}
                 for b in sorted(cands[gi])]
        return terms[0] if len(terms) == 1 else {"t": "And", "kids": terms}

    def disj(gi, bs):
        terms = [gread(index[(gi, b)]) for b in sorted(bs)]
        return terms[0] if len(terms) == 1 else {"t": "Or", "kids": terms}

    sites = 0
    for s in ir.scripts.values():
        bodies = [b for o in s.objects for b in o.methods.values()] + list(s.procs.values())
        for body in bodies:
            plan, consumed = [], set()
            for n in I.walk(body):
                if id(n) in consumed:
                    continue
                shape = _mask_site(n)
                if shape is None or shape[1] not in cands:
                    continue
                kind, gi, val = shape
                U = cands[gi]
                if kind == "or":
                    new = sets(gi, [b for b in sorted(U) if (val >> b) & 1], 1)
                elif kind == "and":
                    new = sets(gi, [b for b in sorted(U) if not (val >> b) & 1], 0)
                elif kind == "assign":
                    new = sets(gi, sorted(U), None)     # per-bit values fixed below
                    for a, b in zip(new, sorted(U)):
                        a["kids"][1]["value"] = (val >> b) & 1
                elif kind in ("eq", "setq", "ne", "setq_ne"):
                    if kind in ("eq", "ne"):
                        if val & ~sum(1 << b for b in U) & 0xFFFF:
                            body_new = {"t": "Number", "value": 0}   # unspellable value: never
                        else:
                            body_new = conj(gi, val)
                    else:
                        body_new = (disj(gi, [b for b in sorted(U) if (val >> b) & 1])
                                    if bin(val).count("1") == 1 else
                                    {"t": "And", "kids": [gread(index[(gi, b)])
                                                          for b in sorted(U) if (val >> b) & 1]})
                    new = [{"t": "Not", "kids": [body_new]}] if kind in ("ne", "setq_ne") \
                        else [body_new]
                elif kind == "test":
                    hit = [b for b in sorted(U) if (val >> b) & 1]
                    new = [disj(gi, hit) if hit else {"t": "Number", "value": 0}]
                elif kind == "bare":
                    new = [disj(gi, sorted(U))]         # truthiness: any observed bit set
                else:
                    continue
                for k in I.walk(n):
                    consumed.add(id(k))
                plan.append((n, new))
            for n, new in plan:
                rep = new[0] if len(new) == 1 else {"t": "List", "kids": new}
                n.clear()
                n.update(rep)
                sites += 1
    return base, sites, len(index)


def derive_walk_icon(ir):
    """(icon-bar global, walk-icon index, walk-icon object name), or None.

    SCI1's point-and-click interface is an `IconBar` whose icons are verbs, and one of them is
    WALK. The game names it itself, in the same send that builds the bar:

        ((= global69 Kq6IconBar)
            add: (icon0 cursor: cIcon0 yourself:) (icon1 ...) ... icon6
            curIcon: icon0
            useIconItem: icon4
            walkIconItem: icon0)              ; <-- walking is icon0, which `add:` puts at index 0

    so the walk icon is `walkIconItem:`'s argument and its INDEX is its position in `add:` --
    which is what a room needs, because `IconBar::disable` accepts either spelling:
    `(if (IsObject arg) arg else (self at: arg))`. A room that disables it has taken walking away
    (see extract's `_no_walk_rooms`).

    Returns None for a game with no icon bar at all, which is every SCI0 title -- LSL2, KQ4, SQ3
    and Camelot have no `walkIconItem:` anywhere, so everything built on this is inert there."""
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    recv, msgs = I.send_pairs(n)
                    sel = {}
                    for m, params in msgs:
                        sel.setdefault(m, params)
                    if not sel.get("walkIconItem"):
                        continue
                    w = sel["walkIconItem"][0]
                    name = w.get("name") if isinstance(w, dict) else None
                    if not name:
                        continue
                    order = []
                    for p in sel.get("add", ()):
                        if not isinstance(p, dict):
                            continue
                        if p.get("t") == "Send":        # `(icon0 cursor: c yourself:)`
                            p, _m = I.send_pairs(p)
                        order.append(p.get("name") if isinstance(p, dict) else None)
                    gi = None
                    for m in I.walk(recv):              # the receiver is `(= gN <IconBar>)`
                        if m.get("t") == "Assignment":
                            ks = m.get("kids") or []
                            if ks and I.is_global(ks[0]):
                                gi = ks[0]["index"]
                    if gi is None:
                        continue
                    return gi, (order.index(name) if name in order else None), name
    return None


def derive_debug(ir):
    """Globals TOGGLED with `^=` -- what a debug menu checkbox compiles to.

    Nothing else in a game XORs a global with 1. Both titles do exactly this:
    LSL2 `(^= gDebugging $0001)`, KQ4 `(^= global215 $0001)`."""
    out = {}
    for s in ir.scripts.values():
        for o in s.objects:
            for mname, body in o.methods.items():
                for n in I.walk(body):
                    if n.get("t") != "AssignmentXor":
                        continue
                    ks = n.get("kids") or []
                    if ks and I.is_global(ks[0]):
                        out.setdefault(ks[0]["index"], set()).add(f"{o.name}::{mname}")
    for name, body in ((n, b) for s in ir.scripts.values() for n, b in s.procs.items()):
        for n in I.walk(body):
            if n.get("t") != "AssignmentXor":
                continue
            ks = n.get("kids") or []
            if ks and I.is_global(ks[0]):
                out.setdefault(ks[0]["index"], set()).add(f"proc {name}")
    return out


def _item_family(ir):
    """The species set of the game's inventory-item class and every subclass of it.

    Shared by `item_names` and `inventory_scripts` so both agree on what an item IS; the base
    class comes from the class-table derivation `Vocabulary.store_class` performs, so no class
    name is assumed. Empty set when the game has no recognisable store class."""
    voc = Vocabulary.from_ir(ir)
    if voc is None:
        return set()
    base = ir.find_class(voc.store_class)
    if base is None:
        return set()
    sup = {o.species: o.super for s in ir.scripts.values() for o in s.objects if o.is_class}

    def is_item(sp, seen=()):
        if sp == base.species:
            return True
        if sp in seen or sp not in sup:
            return False
        return is_item(sup[sp], seen + (sp,))

    return {sp for sp in sup if is_item(sp)} | {base.species}


def inventory_scripts(ir):
    """The scripts that DECLARE the game's inventory items -- a dispatch SCOPE, never a room.

    SCI1 replaced SCO0's parser with an icon bar, and the icon bar is what dispatches an item's
    `doVerb`: "use this item on that one". So nothing in the game ever ARMS the script the item
    objects live in -- no room sets it, no cutscene casts it, no procedure calls it -- and
    `opmodel.armed_rooms` leaves it homeless, dropping every effect it holds. KQ6's magic paint is
    mixed there (`KqInv doVerb 30` -> `mixPaintScr`), which is the whole reason flag 22 had no
    writer.

    But "nothing arms it" is not "it never runs". An inventory action is available wherever the
    player is standing, which makes this the same kind of always-live dispatch scope `Main`
    already is (`opmodel.MAIN_SCRIPT`) -- and it must be lifted with the same care: its EFFECTS
    are real everywhere, while its guards are evidence about no room in particular. See
    `opmodel.global_homed` for the half that homes it and `missability.build_maps` for the half
    that refuses to read a global guard as a per-room requirement.

    Derived from the same species walk `item_names` does, so no script number and no game is
    named. SCO0 titles declare their items in script 0, which IS `MAIN_SCRIPT`, so this returns
    {0} on LSL2/KQ4 and the rule is inert on the goldens by construction. Measured: LSL2 {0},
    KQ4 {0}, KQ5 {0}, KQ6 {907}, Dagger {15}.

    A script counts only if it is where the items MOSTLY live: a game may declare a stray item
    instance beside the room that hands it over, and one such instance does not make that room an
    always-live scope. The threshold is a plurality of the declared items, which is what "the
    inventory script" means and is not a tunable -- an inventory split evenly across two scripts
    would return both."""
    fam = _item_family(ir)
    if not fam:
        return frozenset()
    per = {}
    for sn in sorted(ir.scripts):
        n = sum(1 for o in ir.scripts[sn].objects
                if not o.is_class and (o.super in fam or o.species in fam))
        if n:
            per[sn] = n
    if not per:
        return frozenset()
    top = max(per.values())
    return frozenset(sn for sn, n in per.items() if n == top)


def item_names(ir):
    """Item NUMBER -> readable name, derived per game (the last game-specific catalogue).

    An item's number is its 0-indexed position in DECLARATION ORDER among instances of the
    game's inventory-item class -- `InvI` or any subclass the game defines for its items
    (LSL2 `Iitem`, KQ4 `newInvItem`). The base class comes from the same class-table derivation
    the location store uses (`Vocabulary.store_class`), so no class name is assumed; membership
    is by the species hierarchy, so a game's own subclass is included without naming it.

    The JSON IR carries raw display names with spaces and punctuation (`Wad O' Dough`); runs of
    non-alphanumerics collapse to a single underscore. On LSL2 this reproduces the old
    hand-written `_NAMES` table bit-for-bit -- item 0 is the `NoInv` placeholder, which is never
    a real inventory item -- and on KQ4 it yields Obsidian_Scarab (7), Magic_Fruit (25),
    Magic_Hen (33), the Shovel (15): the names every KQ4 report used to hand-resolve from Main.sc.

    Numbering assumes item instances declare in one script in inventory order, as both known
    games do (all in script 0); scripts are visited in number order so this is deterministic."""
    fam = _item_family(ir)
    if not fam:
        return {}
    # AUTHORITATIVE when present: the order the game ADDS items to its inventory list. `get:`/
    # `has:`/`at:` index THAT list, and it need not match declaration order -- KQ6 declares `map`
    # 22nd but adds it FIRST, so every item before it was named one place off. That mislabels the
    # OUTPUT while every number stays right, which is the worst kind of wrong: `get: 10` is the
    # egg the White Queen hands over, and we called it the skull. Declaration order remains the
    # fallback for games whose list is built some other way (LSL2/KQ4 build theirs by declaring
    # in order, so both agree there).
    names, n = {}, 0
    for sn in sorted(ir.scripts):
        for o in ir.scripts[sn].objects:
            # An INSTANCE resolves its class via `super`: SCI1.1 (heap format) encodes an instance's
            # own `species` as 0xffff and puts the class species in `super`, while SCO0/SCI1(KQ5) put
            # the class species in BOTH. So `species` alone matched nothing on KQ6/QFG-VGA/Dagger.
            # Checking both mirrors the store-family resolver above (Vocabulary.find_stores) and is
            # byte-identical on LSL2/KQ4/KQ5 (there species==super for every item instance).
            if not o.is_class and (o.super in fam or o.species in fam):
                names[n] = re.sub(r"[^0-9A-Za-z]+", "_", o.name).strip("_")
                n += 1
    # AUTHORITATIVE when the game builds its inventory list explicitly: `get:`/`has:`/`at:` index
    # THAT list, and it need not match declaration order -- KQ6 declares `map` 22nd but adds it
    # FIRST, so every earlier item was named one place off. That mislabels the OUTPUT while every
    # number stays right, which is the worst kind of wrong: `get: 10` is the egg the White Queen
    # hands over, and we reported the skull.
    #
    # Only accepted when it accounts for EVERY item, since a partial `add:` is some other list --
    # a shop's stock, a sub-window's icons -- not the inventory. LSL2 and KQ4 both have such a
    # partial list (17 and 12 of their items), and both build the real inventory by declaring in
    # order, so they keep the fallback and stay byte-identical.
    ordered = _inv_list_order(ir, fam)
    if len(ordered) == len(names) and len(ordered) > 1:
        return {i: re.sub(r"[^0-9A-Za-z]+", "_", nm).strip("_") for i, nm in enumerate(ordered)}
    return names


def _inv_list_order(ir, fam):
    """The item names in the order the game ADDS them to its inventory list, or [] if no such
    list is built. This is the order `get:`/`has:`/`at:` index by.

    The idiom is one `(<inv> add: <item> <item> ...)` send -- often with each item wrapped in a
    configuring send that returns it (`(brick setCursor: 990 0 1 yourself:)`), so the item is the
    RECEIVER of that inner send rather than a bare reference. Only items of the inventory family
    count, so the trailing non-item arguments some games pass are ignored."""
    best = []
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "Send":
                        continue
                    try:
                        _recv, msgs = I.send_pairs(n)
                    except Exception:                       # noqa: BLE001
                        continue
                    for sel, params in msgs:
                        if sel != "add":
                            continue
                        got = []
                        for p in params:
                            nm = _item_ref_name(p, ir, fam)
                            if nm:
                                got.append(nm)
                        if len(got) > len(best):
                            best = got
    return best


def _item_ref_name(p, ir, fam):
    """An `add:` argument -> the inventory-item instance it denotes, else None."""
    if not isinstance(p, dict):
        return None
    if p.get("t") == "Object":
        nm = p.get("name")
    elif p.get("t") == "Send":
        recv = (p.get("kids") or [None])[0]
        nm = recv.get("name") if isinstance(recv, dict) and recv.get("t") == "Object" else None
    else:
        return None
    if not nm:
        return None
    for s in ir.scripts.values():
        o = s.by_name.get(nm)
        if o is not None and not o.is_class and (o.super in fam or o.species in fam):
            return nm
    return None


def _instance_class_species(o):
    """The species of the class an INSTANCE instantiates. SCI1.1 (heap format) stores 0xffff in an
    instance's own `species` and the class species in `super`; SCO0/SCI1 store the class species in
    both. So `super` is the class for a sentinel instance, `species` otherwise -- and they agree on
    SCO0 (see item_names)."""
    return o.super if o.species == 65535 else o.species


def doverb_item_messages(ir):
    """message-number -> inventory INDEX, for SCI1's `doVerb` item-use dispatch.

    SCI1 replaced SCO0's parser with a point-and-click icon bar: `(feature doVerb: (curIcon
    message:))`, so `doVerb`'s param1 is the SELECTED ICON's `message`. For a verb icon that message
    is a base verb (look / do / talk -- a free player choice); for an inventory item used AS the verb
    it is the item's own `message` property. So `(== param1 <item.message>)` inside a doVerb means the
    player is USING that item -- an OWN requirement, the same one `curInvIcon == N` yields, but keyed
    on the item's message instead of read from curInvIcon. In KQ6 this, not curInvIcon, is where the
    room puzzles express "use item X"; the guard was going OPAQUE (param1 is a method Parameter), so
    every such requirement was invisible.

    Returns message -> inventory index (the OWN key, = item_names declaration order). Only messages
    that UNIQUELY identify one inventory item and are NOT also a base-verb-icon message are kept, so a
    verb is never misread as an item (the two spaces do not overlap in KQ6, but the exclusion makes
    that a checked fact rather than an assumption). Empty on SCO0 -- no icon bar, items carry no
    `message` -- so the whole mechanism is inert on LSL2/KQ4/KQ5 (verified: 0 messages mapped)."""
    voc = Vocabulary.from_ir(ir)
    if voc is None:
        return {}
    invbase = ir.find_class(voc.store_class)
    if invbase is None:
        return {}
    sup = {o.species: o.super for s in ir.scripts.values() for o in s.objects if o.is_class}

    def descends(sp, target, seen=()):
        if target is None:
            return False
        if sp == target:
            return True
        if sp in seen or sp not in sup:
            return False
        return descends(sup[sp], target, seen + (sp,))

    invfam = {sp for sp in sup if descends(sp, invbase.species)} | {invbase.species}
    iconI = ir.find_class("IconI")   # the icon-bar base; a verb icon is an IconI that is NOT an item
    iconsp = iconI.species if iconI else None
    iconfam = {sp for sp in sup if descends(sp, iconsp)} | ({iconsp} if iconsp else set())

    # The index MUST be the one `get:`/`has:`/`at:` use, so take it from `item_names` by NAME
    # rather than counting declarations again here. Counting was this function's own copy of the
    # ordering rule, and it went stale the moment item_names started reading the game's inventory
    # LIST: KQ6 adds `map` first though it is declared 22nd, so every item before it came out one
    # place off -- `placeHoleScr` demanded the handkerchief instead of the hole-in-the-wall, and
    # `giveDagger` the old coins instead of the dagger.
    by_name = {nm: i for i, nm in item_names(ir).items()}
    base_verbs, counts, msg_idx = set(), {}, {}
    for sn in sorted(ir.scripts):
        for o in ir.scripts[sn].objects:
            if o.is_class:
                continue
            cls = _instance_class_species(o)
            if cls in invfam:
                m = o.props.get("message")
                i = by_name.get(re.sub(r"[^0-9A-Za-z]+", "_", o.name).strip("_"))
                if m is not None and i is not None:
                    counts[m] = counts.get(m, 0) + 1
                    msg_idx.setdefault(m, i)
            elif cls in iconfam:
                m = o.props.get("message")
                if m is not None and m != 65535:
                    base_verbs.add(m)
    return {m: i for m, i in msg_idx.items() if counts[m] == 1 and m not in base_verbs}


def lower_property_case_labels(ir):
    """A `switch` case label that is a PROPERTY, resolved to the literal it holds.

        (switch global12                 ; global12 = the previous room
            (north  <arrived from the north neighbour>)
            (south  <arrived from the south neighbour>)
            (330    <arrived from rm330>))

    `north` here is the ROOM OBJECT'S OWN `north` property -- a room number -- so the arm means
    `global12 == <that number>`, exactly as the numeric arms do. But `ir.control_shape` builds an
    `Eq` guard only for a `Number` label and hands a `Property` label back as an UNGUARDED arm, so
    the model reads every arrival-direction branch as taken unconditionally, all at once. LB2 mixes
    the two spellings inside a single switch (`rm350::init` has four Property arms and two numeric
    ones), which is how the asymmetry hid: the numeric arms ordered, the property arms did not.

    Rewriting the label is the whole fix -- `control_shape` then treats it like any other numeric
    case, including the `priors` accumulation that makes the arms mutually exclusive and gives the
    `else` its real condition.

    FOUR RESTRICTIONS, each one a claim about what a property label can be trusted to mean:

    * **INSTANCE methods only** (`not o.is_class`). In a CLASS method the label names whatever the
      RECEIVING INSTANCE holds, and the class's own value is only a default. LB2's `Door` is the
      case and it is not hypothetical: `Door.sc:20` declares `listenVerb 0` while `rm510`, `rm560`,
      `rm600` and `rm610` each override it to `38` (the water glass), and `Door::doVerb`'s
      `(listenVerb (self listen:))` is exactly this idiom. Resolving against the class would assert
      the wrong number for all four. That arm therefore stays unguarded and the eavesdrop mechanic
      stays free -- a KNOWN REMAINING GAP, and closing it needs per-instance specialisation of a
      class method, not this pass. See docs/LB2-ORACLE.md §7v.
    * **A property the object ASSIGNS is not a literal.** If anything writes that selector the
      declared value is an initial value, not an invariant.
    * **0 and $ffff are sentinels, never destinations.** `Door`'s `listenVerb 0` means "this door
      cannot be listened at"; a room's `north 0` means "no exit north". Resolving either would
      manufacture a guard on a value the game uses to mean ABSENT -- and on a `param1` dispatch
      head, where `_cmp_atom` turns `param1 == N` into OWN(N), `0` would invent a requirement to
      hold item 0.
    * **Only under a head `control_shape` treats as VALUED** -- a global, or a parameter/selected-
      item dispatch. Anywhere else the label yields no guard whether or not we resolve it, so
      rewriting would be noise in the IR with no consumer.

    Returns the census as `[(script, object, method, name, value, head)]` so the caller can print
    what it did; the IR is mutated in place."""
    sites = []
    for sn, sc in ir.scripts.items():
        for o in sc.objects:
            if o.is_class:                      # the value belongs to the instance, not the class
                continue
            props = o.props or {}
            if not props:
                continue
            written = _assigned_selectors(o)
            for mname, meth in o.methods.items():
                for node in I.walk(meth):
                    if node.get("t") != "Switch":
                        continue
                    ks = node.get("kids") or []
                    head = ks[0] if ks else None
                    if not isinstance(head, dict):
                        continue
                    glob = (head.get("t") == "Variable" and head.get("vtype") == "Global")
                    disp = (head.get("t") == "Variable" and head.get("vtype") == "Parameter") \
                        or I.is_selected_item(head)
                    if not (glob or disp):
                        continue
                    for c in ks[1:]:
                        ck = c.get("kids") or []
                        lbl = ck[0] if ck else None
                        if not (isinstance(lbl, dict) and lbl.get("t") == "Property"):
                            continue
                        name = lbl.get("name")
                        v = props.get(name)
                        if v is None or v in (0, 0xffff) or name in written:
                            continue
                        lbl.clear()
                        lbl["t"] = "Number"
                        lbl["value"] = v
                        sites.append((sn, o.name, mname, name, v,
                                      head.get("index") if glob else "dispatch"))
    return sites


def _assigned_selectors(obj):
    """Selectors this object writes -- as a property assignment or as a one-argument send to
    itself. Their declared value is an initial value, not a constant."""
    out = set()
    for m in obj.methods.values():
        for n in I.walk(m):
            t = n.get("t")
            ks = n.get("kids") or []
            if t == "Assignment" and ks and isinstance(ks[0], dict) \
                    and ks[0].get("t") == "Property":
                out.add(ks[0].get("name"))
            if t == "SendMessage" and ks and isinstance(ks[0], dict) \
                    and ks[0].get("t") == "Selector" and len(ks) > 1:
                out.add(ks[0].get("name"))
    return out
