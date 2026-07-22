"""Extraction over the sci-tools typed IR (Phase 3 of PLAN-v2 / ENGINE-DIRECTION Plan A).

Walks each room's typed control-flow AST and composes PATH CONDITIONS along the control
flow into a gated transition system: movement edges, item acquisitions, register writes,
deaths. Because the AST is typed and complete, effect-timing follows the machine's own
control flow -- there is no ENTRY/SELF/EXIT reconstruction heuristic (the seam that lost
the parachute).

Guards reuse model.py's tree (GAnd/GOr/GNot/Pred), but identifiers are IR-canonical:
Pred.var is a global INDEX for CMP, an item number for OWN.

This is built incrementally; this first cut does movement + item acquisitions (guards over
OWN/SAID/POS/CMP/opaque), validated against the old model before registers/machine-state.
"""
from __future__ import annotations

import config

import os
from dataclasses import dataclass, field

import ir as I
import vocab as V
from guard_ast import GAnd, GOr, GNot, Pred

G_EGO = 0        # gEgo   (get:/put:/has: receiver)  -- confirmed by IR survey
G_ROOMOBJ = 2    # gCurRoom, the room OBJECT (the `newRoom:` receiver) -- not the room NUMBER

NAV_SELECTORS = ("north", "south", "east", "west")


# ---- guard atoms from a test expression ----------------------------------
def atom(n):
    """A boolean test node -> a guard tree (Pred / GAnd / GOr / GNot). Unknown player
    actions (Said, position) and anything we cannot decide become opaque preds."""
    if n is None:
        return None
    tp = n["t"]
    if tp == "Not":
        return GNot(atom(n["kids"][0])) if n["kids"] else Pred("OPAQUE")
    if tp == "And":
        return GAnd([atom(k) for k in n["kids"]])
    if tp == "Or":
        return GOr([atom(k) for k in n["kids"]])
    if tp == "Said":
        return Pred("SAID")
    if tp == "Send":
        return _send_atom(n)
    if tp in ("Eq", "Ne", "Gt", "Ge", "Lt", "Le", "Ugt", "Uge", "Ult", "Ule"):
        return _cmp_atom(n, tp)
    if tp == "Variable" and n["vtype"] == "Global":
        return Pred("CMP", var=n["index"], op="!=", value="0")   # truthiness of a global
    if tp == "Number":
        return None if n["value"] != 0 else Pred("OPAQUE")       # constant test
    return Pred("OPAQUE")


_OPS = {"Eq": "==", "Ne": "!=", "Gt": ">", "Ge": ">=", "Lt": "<", "Le": "<=",
        "Ugt": ">", "Uge": ">=", "Ult": "<", "Ule": "<="}
_REV = {"==": "==", "!=": "!=", ">": "<", ">=": "<=", "<": ">", "<=": ">="}


def _cmp_atom(n, tp):
    """A comparison test -> a guard. Global vs literal -> Pred CMP; LOCAL/Temp vs literal ->
    a CTR tuple `("CTR", (vt_char, idx), op, val)` (same format compile uses for machine
    bodies), so gexpr resolves it against the tracked local. `henchStatus==0` and the like
    used to fall through to OPAQUE -- the 'everything means everything' local-guard hole."""
    ks = n["kids"]
    if len(ks) < 2:
        return Pred("OPAQUE")
    a, b = ks[0], ks[1]
    op = _OPS[tp]
    # GLOBAL vs literal (op reversed if the global is on the right, e.g. `(< 5 gX)` = gX>5)
    if I.is_global(a) and I.as_int(b) is not None:
        return Pred("CMP", var=a["index"], op=op, value=str(I.as_int(b)))
    if I.is_global(b) and I.as_int(a) is not None:
        return Pred("CMP", var=b["index"], op=_REV[op], value=str(I.as_int(a)))
    # LOCAL/TEMP vs literal -> tracked-local CTR guard (the previously-dropped 196)
    if I.is_local_or_temp(a) and I.as_int(b) is not None:
        return ("CTR", (a["vtype"][0], a["index"]), op, I.as_int(b))
    if I.is_local_or_temp(b) and I.as_int(a) is not None:
        return ("CTR", (b["vtype"][0], b["index"]), _REV[op], I.as_int(a))
    # `(== ((Inv at: 17) loop:) 1)` -- the FOURTH store: state living in an item's own property.
    # Went to OPAQUE, which threw the fact away; carried as IPROP it is at least preserved.
    ip = item_prop_read(a)
    if ip is not None and I.as_int(b) is not None:
        return Pred("IPROP", var=ip, op=op, value=I.as_int(b))
    ip = item_prop_read(b)
    if ip is not None and I.as_int(a) is not None:
        return Pred("IPROP", var=ip, op=_REV[op], value=I.as_int(a))
    # `(edgeHit) == N` -> the ego is at screen edge N (a POSITION guard over (x,y)).
    if _is_ego_edgehit(a) and I.as_int(b) is not None and op == "==":
        return ("POS", "edge", I.as_int(b))
    if _is_ego_edgehit(b) and I.as_int(a) is not None and op == "==":
        return ("POS", "edge", I.as_int(a))
    # property / onControl / distance compares -> opaque (control-map / undecidable)
    return Pred("OPAQUE")


def _is_ego_edgehit(n):
    """`(gEgo edgeHit:)` -- returns which screen edge the ego is at."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        if I.is_global(recv, G_EGO):
            return any(sel == "edgeHit" for sel, _ in msgs)
    return False


G_CURROOM = 11   # gCurRoomNum -- compared against room numbers all over the scripts


def item_prop_read(n):
    """`((Inv at: 17) loop:)` -> `(item, property)` if that pair is tracked state, else None.

    Only pairs the game both writes and reads count -- a `view:` read is cosmetic, a `loop:` read
    on the fishing pole is asking whether it is baited. The distinction is discovered, not listed.
    """
    if not (isinstance(n, dict) and n.get("t") == "Send"):
        return None
    recv, msgs = I.send_pairs(n)
    it = _at_item(recv)
    if it is None:
        return None
    for sel, params in msgs:
        if not params and (it, sel) in _IPROPS:
            return (it, sel)
    return None


def _at_item(n):
    """`(gInv at: N)` -> N. The object handle for inventory item N."""
    if isinstance(n, dict) and n.get("t") == "Send":
        recv, msgs = I.send_pairs(n)
        for sel, params in msgs:
            if sel == "at" and params:
                return I.as_int(params[0])
    return None


# ---- the item-LOCATION store: DERIVED, not catalogued ---------------------
# We used to hand-write a recogniser per spelling -- `gEgo get:`, `gEgo put:`, `(Inv at: N)
# moveTo:`, a raw `owner:` write -- and each new game produced another one. They are not four
# idioms. They are ONE property write, and the game says so in its own class table:
#
#     (class InvI of Obj  (properties ... owner 0 loop 0 ...)
#       (method (ownedBy param1) (return (== owner param1)))       ; READ  the location
#       (method (moveTo param1)  (= owner param1) (return self)))  ; WRITE the location
#
#     (class Ego ... (method (put param1 param2) ((global9 at: param1) moveTo: ...)))
#
# vocab.Vocabulary reads that and derives which selectors move an item and where the item and
# destination sit in each. Both games independently yield the same table, and the two exclusions
# the hand-written version made by eye (Window's same-named `moveTo: x y`) fall out of the
# receiver and arity of the class's own method. See docs/HOW-IT-WORKS and TODO A0.
EGO = V.EGO      # destination sentinel: the item is now HELD

_VOCAB = None    # installed by extract(); one game per process
_IPROPS = {}     # (item, property) -> values written -- the FOURTH store, discovered
#   the same way gating registers are: written AND read. See vocab.item_property_registers.


def install_vocabulary(ir):
    """Derive this game's item-location vocabulary. Returns it, or None if the game has no
    recognisable store -- which is a finding, not something to paper over with a default."""
    global _VOCAB, _IPROPS
    _VOCAB = V.Vocabulary.from_ir(ir)
    _IPROPS = (V.item_property_registers(ir, _VOCAB.store_class, _VOCAB.prop, _at_item)
               if _VOCAB else {})
    return _VOCAB


def item_transfer(recv, sel, params):
    """An inventory-transfer send -> `(item, dest)`, else None. `dest` is EGO or an int
    (a room number, real or pseudo; -1 = nowhere, SCI's own idiom).

    The selector table is DERIVED per game -- see install_vocabulary. What stays here is the one
    structural fact that is not vocabulary: how an item is REFERRED to, `(<inv> at: N)`."""
    if _VOCAB is None:
        return None
    return _VOCAB.transfer(recv, sel, params, _at_item)


def walk_stream(node, pc, on_leaf, on_loop=None, undecided=None):
    """Visit every statement under `node`, carrying the composed path condition.

    The control flow comes from `ir.control_shape`, so this function -- and every walker built on
    it -- learns a new statement form the moment that classifier does. `on_leaf(node, pc)` gets
    each effect/operand node and decides what it means; that part is the caller's and SHOULD
    differ between walkers.

    Loop policy here is "visit everything inside it", which is the permissive reading a streaming
    walker wants. compile makes the other choice on the same shape.
    """
    shape = I.control_shape(node)
    kind = shape[0]
    if kind == "seq":
        for k in shape[1]:
            walk_stream(k, pc, on_leaf)
        return
    if kind == "branch":
        for conds, body in shape[1]:
            ext = []
            for (test, pol) in conds:
                a = atom(test)
                ext.append(a if pol else (GNot(a) if a is not None else None))
            walk_stream(body, pc + ext, on_leaf)
        return
    if kind == "loop":
        # `on_loop` lets a caller note that it is INSIDE a loop and restore afterwards -- the
        # bulk-inventory walk needs that context and nothing else does.
        restore = on_loop(node) if on_loop else None
        lpc = pc + ([undecided] if undecided is not None else [])
        for k in shape[1:]:
            walk_stream(k, lpc, on_leaf, on_loop, undecided)
        if restore is not None:
            restore()
        return
    if node is None:
        return
    on_leaf(node, pc)
    for k in node.get("kids", ()):
        walk_stream(k, pc, on_leaf, on_loop, undecided)


def _send_atom(n):
    ip = item_prop_read(n)          # `(if ((Inv at: 15) loop:) {Broken Shovel} ...)`
    if ip is not None:
        return Pred("IPROP", var=ip, op="!=", value=0)
    recv, msgs = I.send_pairs(n)
    for sel, params in msgs:
        if sel == "has" and I.is_global(recv, G_EGO):
            it = I.as_int(params[0]) if params else None
            if it is not None:
                return Pred("OWN", var=it)
        if sel in ("said",):
            return Pred("SAID")
        # `(gInv at: X) ownedBy: <where>` -- "item X is currently AT <where>". The SCI idiom for a
        # one-time pickup, used 77 times in LSL2 and previously lost as an opaque. It matters
        # because destroying an item sets its owner to NOWHERE, so the test can never hold again
        # (barfing into the Airsick_Bag).
        #
        # The two games spell <where> differently, as usual: LSL2 writes `gCurRoomNum` (60 sites),
        # KQ4 writes the room number as a LITERAL (`ownedBy: 78` inside Room78, where the Magic
        # Fruit hangs on the tree). Carry the destination through rather than deciding here --
        # only the caller knows which room it is standing in. See missability._loc_required.
        if sel == "ownedBy":
            it = _at_item(recv)
            if it is not None:
                where = "other"
                if params and I.is_global(params[0], G_CURROOM):
                    where = "room"
                elif params and I.as_int(params[0]) is not None:
                    where = I.as_int(params[0])
                return Pred("LOC", var=it, op="ownedBy", value=where)
        # `(gEgo inRect: a b c d)` -> a POSITION guard over the ego's (x,y). Coordinates are
        # in the AST, so this is derivable; ONE consistent (x,y) is what makes "cross east =>
        # inRect" unavoidable: one consistent (x,y) per step, not a fresh choice per guard.
        if sel == "inRect" and I.is_global(recv, G_EGO) and len(params) >= 4:
            cs = [I.as_int(p) for p in params[:4]]
            if all(c is not None for c in cs):
                return ("POS", "rect", tuple(cs))
    # onControl (PIC control-map), distanceTo, posn-relative, other sends -> opaque residue
    return Pred("OPAQUE")


# ---- transition system ---------------------------------------------------
@dataclass
class Edge:
    src: int
    dst: int
    guard: object = None       # guard tree; None = free
    via: str = ""              # object whose method emitted it -- see Extractor._inherit_arming


@dataclass
class Acq:
    item: int
    room: int
    guard: object = None


@dataclass
class TS:
    rooms: set = field(default_factory=set)
    edges: list = field(default_factory=list)
    acqs: list = field(default_factory=list)
    items: set = field(default_factory=set)
    cs_edges: list = field(default_factory=list)   # changeState newRoom exits (room,dst,
    #   guard). The MACHINE owns these; used as a GATED fallback only where the machine
    #   walk can't deliver the exit (control_exits) -- avoids a false dead-end without
    #   reintroducing a free bypass.
    bulk_moves: list = field(default_factory=list)  # (room, dest, guard) -- a transfer of the
    #   WHOLE inventory at once, written as a walk of the Inv list. No item number appears
    #   anywhere, so this is the one case where "no constant" must mean "all of them".
    item_prop_writes: list = field(default_factory=list)  # (room, item, prop, value, guard);
    #   value is an int or "inc". The FOURTH store -- state living in an item's own property.
    #   Breaking the shovel and spending an arrow are written here, and they mean the same thing
    #   as losing the item: its uses stop accepting it.


def _conj(pc):
    pc = [g for g in pc if g is not None]
    if not pc:
        return None
    return pc[0] if len(pc) == 1 else GAnd(list(pc))


_ROOM_SPECIES = {}          # ir id -> species number of the Rm/Room base class


def _room_species(ir):
    """Species of the game's Room base class, found by NAME in the class table.

    Room detection used to be `name == f"rm{script.number}"`, which is a decompiler NAMING
    CONVENTION, not a fact about the game. sci-tools emits `rm47` for LSL2 but `Room63` for KQ4,
    so every KQ4 room failed the test and the extractor saw 4 rooms out of 159 scripts -- silently
    analysing almost nothing. Inheritance is the real signal, and it is what the docstring always
    claimed. The name check stays as a fallback."""
    key = id(ir)
    if key in _ROOM_SPECIES:
        return _ROOM_SPECIES[key]
    species = None
    for s in ir.scripts.values():
        for o in s.objects:
            if o.is_class and o.name in ("Rm", "Room"):
                species = o.species
                break
        if species is not None:
            break
    _ROOM_SPECIES[key] = species
    return species


def pending_room_global(ir):
    """The global that IS `newRoom:` at the engine level, or None.

    DISCOVERED, not declared. Every SCI0 Game loop contains the same shape --

        (if (!= <pending> <current>) (self newRoom: <pending>))

    -- so the pending-room global is the one that is (a) compared against another global and
    (b) handed to `newRoom:` inside that comparison's body. Both LSL2 and KQ4 land on global13,
    but by derivation rather than coincidence, and the test does not confuse it with a plain
    room-valued global like LSL2's revolving-door `gRmAfter40`: that one is never compared
    against the current-room global."""
    for s in ir.scripts.values():
        for o in s.objects:
            for body in o.methods.values():
                for n in I.walk(body):
                    if n.get("t") != "If":
                        continue
                    ks = n.get("kids") or []
                    test = ks[0] if ks else None
                    if not test or test.get("t") != "Ne":
                        continue
                    tk = test.get("kids") or []
                    if len(tk) < 2 or not (I.is_global(tk[0]) and I.is_global(tk[1])):
                        continue
                    pair = {tk[0]["index"], tk[1]["index"]}
                    for m in I.walk(ks[1] if len(ks) > 1 else None):
                        if m.get("t") != "Send":
                            continue
                        _recv, msgs = I.send_pairs(m)
                        for sel, params in msgs:
                            if (sel == "newRoom" and params and I.is_global(params[0])
                                    and params[0]["index"] in pair):
                                return params[0]["index"]
    return None


def _walks_a_list(loop):
    """Does this Loop iterate a linked list -- `(for ((= v (L first:))) v ((= v (L next: v))))`?

    That control shape is what makes an `owner:` write inside the body a BULK transfer rather than
    a single item's: there is no item number anywhere in

        (for ((= local6 (global9 first:))) local6 ((= local6 (global9 next: local6)))
          (if (and (= local5 (NodeValue local6)) (== (local5 owner:) gEgo))
              (local5 owner: 89)))                            ; KQ4 Room92 -- Lolotte's guards
                                                              ; take EVERYTHING you are carrying
    Only the init and increment are inspected, never the body, so a body that happens to send
    `next:` to something cannot make itself bulk."""
    kids = loop.get("kids") or []
    for k in kids[:3]:                          # init, test, increment -- NOT the body
        for n in I.walk(k):
            if n.get("t") != "Send":
                continue
            _recv, msgs = I.send_pairs(n)
            if any(sel in ("first", "next") for sel, _p in msgs):
                return True
    return False


def _room_object(script, ir=None):
    """The Room instance of a room script: an instance of the Rm/Room class, else named rm<N>."""
    if ir is not None:
        sp = _room_species(ir)
        if sp is not None:
            for o in script.objects:
                if not o.is_class and o.super == sp:
                    return o
    want = f"rm{script.number}"
    for o in script.objects:
        if o.name == want and not o.is_class:
            return o
    return None


class Extractor:
    def __init__(self, ir):
        self.ir = ir
        self.ts = TS()
        self._cur_obj = ""                  # object whose method is being walked
        self._armed = {}                    # room -> {object name: [guard, ...]}
        self._pending = pending_room_global(ir)
        self._list_loop = False             # inside a `for` that walks a linked list
        self.procs_by = {}
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body

    def region_members(self):
        """region-script -> the rooms that activate it, from `(self setRegions: R)` in a room.

        The same map `opmodel` builds. It lives in both because both walk: opmodel picks up a
        region's HANDLER effects, and this walker picks up its edges, acquisitions and item
        properties -- and until now this half simply did not run, so `regUnicorn`'s arrow spend
        was invisible and `resource_exhaustion` reported the bow's direction backwards."""
        out = {}
        for rn, s in self.ir.scripts.items():
            room = _room_object(s, self.ir)
            if room is None:
                continue
            for _mn, a in room.methods.items():
                for n in I.walk(a):
                    if n.get("t") != "Send":
                        continue
                    recv, msgs = I.send_pairs(n)
                    for sel, params in msgs:
                        if sel == "setRegions":
                            for p in params:
                                v = I.as_int(p)
                                if v is not None:
                                    out.setdefault(v, set()).add(rn)
        return out

    def scriptid_refs(self):
        """`(target script, room, guard)` for every `(ScriptID N)` -- SCI's dynamic script load.

        A fourth scope, after Main / region / room. `Main.sc:1116` answers `Said 'launch'` ANYWHERE
        with `(gEgo setScript: (ScriptID 305 0))`, and script 305 (`shootBow`) is where the arrow is
        actually spent -- so firing into the air costs an arrow and we could not see it. Two deaths
        hide the same way: `timeOut` (the 24-hour deadline) and `openPbox` both write the game-over
        global from scripts that are neither rooms nor regions.

        The reference's PATH CONDITION comes with it, which is what keeps `DebugMenu` (script 801,
        loaded from Main under a debug gate) from handing the player every item.

        KQ4 has 8 such scripts; LSL2 has ZERO `ScriptID` call sites, so this cannot move it."""
        out, seen = [], set()
        for rn, sc in self.ir.scripts.items():
            if _room_object(sc, self.ir):
                rooms = [rn]
            elif rn == 0:
                rooms = [0]            # Main is a SCOPE; consumers widen room 0 to everywhere
            else:
                continue
            bodies = list(sc.procs.values()) + [b for o in sc.objects for b in o.methods.values()]
            for b in bodies:
                def leaf(n, pc, _rooms=rooms):
                    if n.get("t") != "KernelCall" or n.get("name") != "ScriptID":
                        return
                    ks = n.get("kids") or []
                    tgt = I.as_int(ks[0]) if ks else None
                    if tgt is None:
                        return
                    for room in _rooms:
                        key = (tgt, room)
                        if key not in seen:
                            seen.add(key)
                            out.append((tgt, room, list(pc)))
                walk_stream(b, [], leaf)
        return out

    def run(self):
        # room universe: any script that has an rm<N> Room instance
        room_scripts = {n: s for n, s in self.ir.scripts.items() if _room_object(s, self.ir)}
        for n in room_scripts:
            self.ts.rooms.add(n)
        # A region's scripts run in the rooms that activate it -- SCI's middle dispatch scope.
        # Walked with the DECLARING room as context, so an acquisition or a property write inside
        # a region is attributed where the player actually is.
        regions = self.region_members()
        for rgn, members in sorted(regions.items()):
            rs = self.ir.scripts.get(rgn)
            if rs is None or rgn in room_scripts:
                continue
            for room in sorted(members):
                for o in rs.objects:
                    self._cur_obj = o.name
                    for mname, meth_ast in o.methods.items():
                        self._walk(room, meth_ast, [], rgn, set(),
                                   movement=(mname != "changeState"))
                self._cur_obj = ""
        # SCRIPTS LOADED BY `ScriptID` -- see scriptid_refs. Walked with the referencing site's
        # path condition, in the scope that loaded them.
        for tgt, room, pc in self.scriptid_refs():
            ts_ = self.ir.scripts.get(tgt)
            # `(ScriptID 0 N)` is how a room reaches MAIN's public procedures -- Main is already
            # its own scope, and walking it into every referencing room attributed its debug
            # cheat block to 25 rooms.
            if ts_ is None or tgt == 0 or tgt in room_scripts or tgt in regions:
                continue
            for o in ts_.objects:
                self._cur_obj = o.name
                for mname, meth_ast in o.methods.items():
                    self._walk(room, meth_ast, list(pc), tgt, set(),
                               movement=(mname != "changeState"))
            self._cur_obj = ""
        for n, s in room_scripts.items():
            self._nav_edges(n, s)
            for o in s.objects:
                self._cur_obj = o.name
                for mname, meth_ast in o.methods.items():
                    # changeState newRoom exits belong to the MACHINE (gated); don't
                    # duplicate them as free flat edges. Items still captured. Procedures
                    # are FOLLOWED in-context (below), not walked standalone -- a proc
                    # walked context-free would emit its newRoom as a free bypass.
                    self._walk(n, meth_ast, [], n, set(), movement=(mname != "changeState"))
            self._cur_obj = ""
            self._inherit_arming(n)
        # add any newRoom target we saw as a room
        for e in self.ts.edges:
            self.ts.rooms.add(e.dst)
        return self.ts

    # selectors that make an object animate/move/run, i.e. that end in a `cue` back to it
    ARMING = ("setCycle", "setMotion", "setScript", "cue", "setReal", "setTimer")

    def _inherit_arming(self, room):
        """A cue-driven edge inherits the guard of whatever ARMED it.

        SCI's door idiom splits one player action across two objects:

            ((Said 'open/door')                          ; Room22.handleEvent
              (cond ((not global100)                     ; <-- the gate: daytime only
                     (doorSound number: 300 play: door)  ; arms the door (sound cues its client)
                     (door setCycle: End))               ; ...and animates it
                    (else (proc255_0 22 9))))            ; "We're all asleep here!"

            (instance door of Prop                       ; and, separately:
              (method (cue)
                (if (!= (door cel:) (door lastCel:)) (self setCycle: End self)
                  else (global2 newRoom: 54))))          ; <-- the edge

        Walked object-by-object, the edge carries only the cel test -- opaque, so free -- and
        `not global100` is nowhere near it. In KQ4 that is the difference between seeing and not
        seeing that the dwarves' house and the fisherman's shanty LOCK AT NIGHTFALL, with the
        Diamond_Pouch and the Fishing_Pole behind them.

        Same principle as the existing setScript capture: an object that only runs when something
        starts it cannot be freer than its starter. The arming guards are OR-ed, since any of them
        will do, and a single unguarded arming site makes the disjunction vacuous -- which is the
        permissive answer, and the right one.

        Deliberately narrow, because adding a guard REMOVES movement and that is the unsafe
        direction: applied only to objects that emitted an edge, only from arming sends found in
        OTHER objects' methods (an object re-arming itself is the animation loop, not a gate), and
        never when no arming site was found at all."""
        armed = self._armed.get(room)
        if not armed:
            return
        for e in self.ts.edges + self.ts.cs_edges:
            if e.src != room or not e.via:
                continue
            gs = armed.get(e.via)
            if not gs:
                continue
            starter = gs[0] if len(gs) == 1 else GOr(list(gs))
            e.guard = starter if e.guard is None else GAnd([e.guard, starter])

    def _nav_edges(self, room_num, script):
        obj = _room_object(script, self.ir)
        if obj is not None:
            for sel in NAV_SELECTORS:
                dst = obj.props.get(sel)
                if dst and dst != 0xffff:
                    self.ts.edges.append(Edge(room_num, dst))   # walk-off exit, free
        # static entranceTo on any object (rooms + Doors): walking it goes to that room
        for o in script.objects:
            et = o.props.get("entranceTo", 0)
            if et and et != 0xffff:
                self.ts.edges.append(Edge(room_num, et))

    def _walk(self, room, node, pc, script, seen, movement=True):
        """Compose path conditions and record effects (newRoom, item transfers), FOLLOWING calls
        in context. `movement=False` for a changeState body: the MACHINE owns those newRoom exits,
        so a free flat duplicate would bypass the gate. Items are always captured (duplicate
        acquisition is monotone).

        Control flow comes from `walk_stream` / `ir.control_shape`. This used to re-implement
        If/Cond/Switch/Loop itself, in code all but identical to opmodel's and machine's --
        which is how `Loop` came to be missing from two of the three."""
        def enter_loop(n):
            prev = self._list_loop
            self._list_loop = prev or _walks_a_list(n)
            def restore():
                self._list_loop = prev
            return restore

        def leaf(n, p):
            tp = n["t"]
            if tp == "Send":
                self._send_effect(room, n, p, movement)
            elif tp == "Assignment" and movement:
                self._nav_assignment(room, n, p)
                self._pending_room_assignment(room, n, p)
            elif tp in ("PublicCall", "LocalCall"):
                tgt = n.get("script", script)
                name = n.get("name")
                body = self.procs_by.get((tgt, name))
                if tgt != 255 and body is not None and name not in seen:
                    self._walk(room, body, p, tgt, seen | {name}, movement)

        walk_stream(node, pc, leaf, enter_loop)

    def _pending_room_assignment(self, room, node, pc):
        """`(= gNewRoomNum 57)` -- a room change written at the engine level instead of as
        `newRoom:`.

        SCI's Game loop is literally

            (if (!= global13 global11)          ; Game.sc, in both LSL2 and KQ4
                (self newRoom: global13))

        so assigning that global IS `newRoom:`, one layer down. KQ4 uses it 20 times and LSL2
        never, which is why it went unnoticed -- and it is not a corner case there: rm6 enters the
        witches' cave with `(= global13 57)` on a control-colour test, so rm57 had NO in-edges at
        all. That in turn made rm57 look "sealed" in the day/night analysis and, worse, let start
        discovery anchor on a room nothing can reach.

        Same family as the revolving door (`newRoom: <global>`) we already resolve, approached from
        the other side: there the destination was in a variable, here the whole call is."""
        if self._pending is None:
            return
        kids = node.get("kids") or []
        if len(kids) < 2 or not I.is_global(kids[0], self._pending):
            return
        dst = I.as_int(kids[1])
        if dst is None or dst == 0 or dst == 0xffff:
            return
        self.ts.edges.append(Edge(room, dst, _conj(pc), self._cur_obj))

    def _nav_assignment(self, room, node, pc):
        """`(= north 5)` -- a walk-off exit set by ASSIGNING the room's own property.

        The other idiom, declaring it in the properties block, is handled by `_nav_edges`. Both
        mean the same thing and games pick one: LSL2 uses the properties block 98 times and the
        assignment form NEVER; KQ4 uses the assignment form 162 times. Supporting only the first
        left 35 KQ4 rooms with no extractable exit at all and shattered its map into 64 components,
        so the analysis was reasoning about a game it could not walk across.

        Captured here rather than in `_nav_edges` so the path condition applies: an exit opened
        only under some condition becomes a GUARDED edge, and `(= east 0)` (closing an exit) is
        correctly not an edge at all."""
        kids = node.get("kids") or []
        if len(kids) < 2:
            return
        dest, src = kids[0], kids[1]
        if not (isinstance(dest, dict) and dest.get("t") == "Property"
                and dest.get("name") in NAV_SELECTORS):
            return
        dst = I.as_int(src)
        if not dst or dst == 0xffff:
            return                      # 0 CLOSES the exit; it does not open one
        self.ts.edges.append(Edge(room, dst, _conj(pc)))

    def _record_arming(self, room, node, pc):
        """Note that this send ARMS some object, and under what condition. Two spellings:
        `(door setCycle: End)` -- the object is the receiver -- and `(doorSound play: door)`,
        where the object is handed to something that will cue it when it finishes."""
        recv, msgs = I.send_pairs(node)
        rname = recv.get("name") if isinstance(recv, dict) else None
        targets = set()
        for sel, params in msgs:
            if sel in self.ARMING and rname:
                targets.add(rname)
            for p in params:
                if isinstance(p, dict) and p.get("t") == "Object" and p.get("name"):
                    targets.add(p["name"])
        for t in targets:
            if t and t != self._cur_obj:      # self-arming is the animation loop, not a gate
                self._armed.setdefault(room, {}).setdefault(t, []).append(_conj(pc))

    def _send_effect(self, room, node, pc, movement=True):
        self._record_arming(room, node, pc)
        recv, msgs = I.send_pairs(node)
        for sel, params in msgs:
            # A WRITE to a tracked item property -- the FOURTH store. `(Inv at: 15) loop: 1`
            # breaks the shovel; `(Inv at: 14) loop: (+ (loop:) 1)` spends an arrow. Both mean
            # the same thing as losing the item, because its uses stop accepting it:
            #   Room16:249  (if (and (gEgo has: 15) (== 0 ((Inv at: 15) loop:))) ... dig ...)
            it = _at_item(recv)
            if params and it is not None and (it, sel) in _IPROPS:
                v = I.as_int(params[0])
                if v is None and any(y.get("t") in ("Add", "Sub") for y in I.walk(params[0])):
                    v = "inc"
                if v is not None:
                    self.ts.item_prop_writes.append((room, it, sel, v, _conj(pc)))
            # The store property written DIRECTLY, bypassing its own accessor -- and inside a
            # list walk, so it means the whole inventory at once: KQ4's Room92 confiscates
            # everything to room 89 and Room89's cupboard hands it all back. The property name
            # comes from the derived vocabulary, not from us; `owner:` is also a Sound property
            # (`(trollMusic owner: self)`), which the destination test excludes.
            if _VOCAB is not None and sel == _VOCAB.prop and params and self._list_loop:
                d = params[0]
                dest = (EGO if I.is_global(d, G_EGO)
                        else I.as_int(d) if I.as_int(d) is not None else None)
                if dest is not None:
                    self.ts.bulk_moves.append((room, dest, _conj(pc)))
            if sel in ("newRoom", "entranceTo") and params:
                dsts = [I.as_int(params[0])]
                if dsts[0] is None and I.is_global(params[0]):
                    # INDIRECT destination `newRoom: <global>` -- a routing room whose next
                    # room is held in a global (rm40's revolving door: gRmAfter40 cycles
                    # 42..45). Resolve to the room numbers that global can hold; dropping it
                    # made rm43 (the Knife) and its cluster unreachable -> endgame sealed.
                    dsts = self._global_room_values(room, params[0]["index"])
                for dst in dsts:
                    if dst is not None:
                        (self.ts.edges if movement else self.ts.cs_edges).append(
                            Edge(room, dst, _conj(pc), self._cur_obj))
            else:
                # ACQUISITION -- the last hardcoded `sel == "get"` here is gone too: whether a
                # send hands the player an item is a question for the derived vocabulary, not a
                # selector name we happen to know.
                tr = item_transfer(recv, sel, params)
                if tr is not None and tr[1] == EGO:
                    self.ts.items.add(tr[0])
                    self.ts.acqs.append(Acq(tr[0], room, _conj(pc)))

    def _global_room_values(self, room, gi):
        """Room numbers a `newRoom:` global can hold, from switch-on-G case labels and
        `(= G lit)` assignments anywhere in this room's script. Filtered to real rooms
        (an rm<N> Room instance exists), so cycle counters like 0 are excluded."""
        vals = set()
        s = self.ir.scripts.get(room)
        if s is None:
            return vals

        def is_room(v):
            rs = self.ir.scripts.get(v)
            return rs is not None and _room_object(rs) is not None

        for o in s.objects:
            for _mn, ast in o.methods.items():
                for n in I.walk(ast):
                    if n["t"] == "Switch":
                        head = n["kids"][0]
                        if head.get("t") == "Variable" and head.get("vtype") == "Global" \
                                and head.get("index") == gi:
                            for c in n["kids"][1:]:
                                if c["t"] == "Case":
                                    v = I.as_int(c["kids"][0])
                                    if v is not None and is_room(v):
                                        vals.add(v)
                    elif n["t"] == "Assignment" and I.is_global(n["kids"][0]) \
                            and n["kids"][0].get("index") == gi:
                        v = I.as_int(n["kids"][1])
                        if v is not None and is_room(v):
                            vals.add(v)
        return vals


def extract(ir):
    install_vocabulary(ir)      # derive this game's item-transfer selectors first
    return Extractor(ir).run()


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else config.ACTIVE.ir_path
    ir = I.load_ir(path)
    ts = extract(ir)
    print(f"rooms={len(ts.rooms)} edges={len(ts.edges)} acqs={len(ts.acqs)} items={len(ts.items)}")
    free = sum(1 for e in ts.edges if e.guard is None)
    print(f"  free edges={free} gated edges={len(ts.edges)-free}")
    print("  items acquired:", sorted(ts.items))
