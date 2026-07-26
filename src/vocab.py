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
    `extract._global_room_values` already does for a revolving-door room's destinations.

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
        its = _literal_items(params[i])
        if not its:
            return None
        it = its[0] if len(its) == 1 else tuple(its)
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


def lower_death_sends(ir, sites, death_value=1):
    """Inject a synthetic death-flag write into each death dialog's `changeState` so that RUNNING the
    script means death, regardless of how it was armed. The write goes into state 0 (the entry), so
    the machine lift reads the machine as fatal from its start. Synthetic global one past the highest,
    exactly as `lower_death_procs`. Returns (synth_index, count)."""
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
    for (script_num, obj_name) in sites:
        obj = ir.scripts[script_num].by_name.get(obj_name)
        cs = obj.methods.get("changeState") if obj else None
        if cs is None:
            continue
        injected = False
        for node in I.walk(cs):
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
        if not injected:                               # no state-0 case: run on every entry
            old = dict(cs)
            cs.clear()
            cs["t"] = "List"
            cs["kids"] = [write(), old]
        n += 1
    return synth, n


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


def lower_death_sci11(ir, dialogs, death_procs, death_value=1):
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
    for (sn, obj_name) in dialogs:                     # (1) inline dialogs -> death write at state 0
        obj = ir.scripts[sn].by_name.get(obj_name)
        cs = obj.methods.get("changeState") if obj else None
        if cs is None:
            continue
        injected = False
        for node in I.walk(cs):
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
            old = dict(cs); cs.clear(); cs["t"] = "List"; cs["kids"] = [write(), old]
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
    for node in calls:
        op = flag_procs[node["name"]]
        flags = [I.as_int(k) for k in (node.get("kids") or []) if I.as_int(k) is not None]
        if op == "toggle" or not flags:
            skipped += 1
            continue
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
    receivers (bare `self`), non-literal arguments and chained sends are left alone -- a sound
    gap, since an unmodelled condition can only miss a stranding, never invent one."""
    if not accessors:
        return 0, 0, 0
    max_gi, sites = 0, []
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
                if len(msgs) != 1:
                    continue                          # chained send -- rewriting it would drop the rest
                sel, params = msgs[0]
                if sel not in accessors:
                    continue
                rid = _flag_receiver_id(recv)
                args = [I.as_int(p) for p in params]
                if rid is None or len(args) < 2 or any(a is None for a in args):
                    continue
                bits = [(args[0], b) for m in args[1:] for b in range(16) if (m & 0xFFFF) >> b & 1]
                if bits:
                    sites.append((node, accessors[sel], [(rid, w, b) for (w, b) in bits]))
    synth_base, index = max_gi + 1, {}
    for _n, _op, keys in sites:
        for k in keys:
            index.setdefault(k, synth_base + len(index))
    BOOL_GLOBALS.update(index.values())
    lowered = 0
    for node, op, keys in sites:
        gis = [index[k] for k in keys]
        if op == "test":
            reads = [{"t": "Variable", "vtype": "Global", "index": g} for g in gis]
            new = reads[0] if len(reads) == 1 else {"t": "Or", "kids": reads}
        else:
            val = 1 if op == "set" else 0
            asg = [{"t": "Assignment",
                    "kids": [{"t": "Variable", "vtype": "Global", "index": g},
                             {"t": "Number", "value": val}]} for g in gis]
            new = asg[0] if len(asg) == 1 else {"t": "List", "kids": asg}
        node.clear()
        node.update(new)
        lowered += 1
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
                tgt = ir.script_id_target(recv)
                if not tgt:
                    continue
                for sel, ps in msgs:
                    if sel is None:
                        continue
                    if ps and I.as_int(ps[0]) is not None:
                        writes[(tgt[0], sel)] += 1
                    elif not ps:
                        reads[(tgt[0], sel)] += 1
    return set(reads) & set(writes)


def lower_obj_props(ir, pairs):
    """Rewrite resolved `(ScriptID s n) <prop>:` reads and constant writes into synthetic globals,
    so object-property state reaches the register machinery as ordinary registers.

    Same shape as `lower_flags` / `lower_prop_flags`, and deliberately so: every store we model
    ends up as a global, and nothing downstream learns a new concept. Chained sends and
    non-constant writes are left alone -- an unmodelled write can only miss a stranding, never
    invent one."""
    if not pairs:
        return 0, 0
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
                tgt = ir.script_id_target(recv)
                if not tgt:
                    continue
                sel, ps = msgs[0]
                key = (tgt[0], sel)
                if key not in pairs:
                    continue
                if not ps:
                    sites.append((node, key, None))
                elif I.as_int(ps[0]) is not None:
                    sites.append((node, key, I.as_int(ps[0])))
    base, index = max_gi + 1, {}
    for _n, key, _v in sites:
        index.setdefault(key, base + len(index))
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
    voc = Vocabulary.from_ir(ir)
    if voc is None:
        return {}
    base = ir.find_class(voc.store_class)
    if base is None:
        return {}
    sup = {o.species: o.super for s in ir.scripts.values() for o in s.objects if o.is_class}

    def is_item(sp, seen=()):
        if sp == base.species:
            return True
        if sp in seen or sp not in sup:
            return False
        return is_item(sup[sp], seen + (sp,))

    fam = {sp for sp in sup if is_item(sp)} | {base.species}
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
