"""Operational SMV emitter (promote EVERYTHING, no counter/register judgment).

Instead of compiling machines to guards (which forces resolving loop counters concretely
-- the counter-vs-register judgment), this emits each machine's `state`, its counters, and
its gating locals as TRACKED SMV variables and lets nuXmv run the loops symbolically.
Uniform treatment: `day`, `henchStatus`, `state`, and every written global are all just
tracked variables; the abstraction (IC3) deals with them.

Per gating machine M in room R (an object with a changeState that has an EXIT/WRITE/DEATH/
GET effect): a state var msM (reset to M.start whenever room!=R), and its gating locals as
promoted vars (reset when away). A step action at (room=R, msM=K) fires one path of state
K: applies its writes/gets/counters and transitions msM (ADVANCE->K+1, JUMP j, SETSTATE
j+1, EXIT->room:=r, DEATH->dead). Player entries (handleEvent changeState:K, guarded) set
msM. init writes are forced on entry. Movement/item edges come from extract (flat).

Guards: OWN->item; CMP on a promoted global-> the tracked var; CTR (Local vs literal)->
the tracked counter var; opaque/untracked-> a fresh nondet input (satisfiable both ways).
"""
from __future__ import annotations

import collections
import os
import subprocess

import ir as I
import machine as M
import compile as C
import vocab
import extract as X
from extract import extract, atom, item_transfer, item_transfers, _room_object, verb_param_scope, EGO
from guard_ast import GAnd, GOr, GNot, Pred


MAIN_SCRIPT = 0     # script 0 -- the Game subclass. A dispatch SCOPE, never a room.
                    # missability.GLOBAL_SCRIPTS is the consumer-side half of the same fact.


def _int(x):
    try:
        return int(x)
    except (TypeError, ValueError):
        return None


def _cmp_const(cur, op, val):
    op = "==" if op == "=" else op
    return {"==": cur == val, "!=": cur != val, ">": cur > val, ">=": cur >= val,
            "<": cur < val, "<=": cur <= val}.get(op, True)


_WARNED = set()


def _degraded(what, exc):
    """Say out loud that a LAYER OF DETECTION just went missing.

    These paths used to swallow and return an empty list, which reads downstream as "this
    title has no positional gates" -- identical to a clean run, so a single undecodable PIC
    could remove the whole geometric layer of a 100-room game and nothing would say so. The
    project's rule is that a failure must be visible; degrading quietly to "found less" is
    the failure mode it exists to prevent.

    A warning rather than a raise, deliberately: one bad room should not abort an analysis
    that is sound everywhere else. Deduplicated so a per-room loop cannot spam. Measured
    2026-08-06: fires on none of LSL2/KQ4/KQ6/LB2 -- the SCI1.1 games find zero prop gates
    because the sprite recogniser is the SCI0 idiom, not because anything raises."""
    key = (what, type(exc).__name__, str(exc)[:80])
    if key in _WARNED:
        return
    _WARNED.add(key)
    import sys as _sys
    print("  [degraded] %s unavailable: %s: %s" % (what, type(exc).__name__, str(exc)[:200]),
          file=_sys.stderr)


def _has_pos_edge(guard, codes, edge_regs=()):
    """Does this guard test "the ego left by one of `codes`"?

    TWO SPELLINGS. The direct one is the ego's own `edgeHit:`, which `atom` renders as the POS
    atom ("POS","edge",N). The other is a register the game COPIES that into, which is what a room
    does when something outside it needs to know the direction later -- see `edge_hit_registers`.
    `edge_regs` names those, so `R == N` counts as the same test."""
    found = []

    def w(g):
        if isinstance(g, tuple) and len(g) == 3 and g[0] == "POS" and g[1] == "edge":
            found.append(g[2])
        elif isinstance(g, Pred) and g.kind == "CMP" and g.op == "==" and g.var in edge_regs:
            try:
                found.append(int(g.value))
            except (TypeError, ValueError):
                pass
        elif isinstance(g, list):
            for k in g:
                w(k)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                w(k)
        elif isinstance(g, GNot):
            w(g.kid)
    w(guard)
    return any(c in codes for c in found)


def _conj_atoms(atoms):
    atoms = [a for a in atoms if a is not None]
    if not atoms:
        return None
    return atoms[0] if len(atoms) == 1 else GAnd(list(atoms))


class OpEmitter:
    def __init__(self, ir, cfg, is_death):
        self.ir = ir
        self.cfg = cfg
        self.is_death = is_death
        # ORDER MATTERS HERE, and it is the reverse of what it looks like. The room-valued
        # globals change what `(== gX gCurRoom)` MEANS (see extract.room_valued_globals), so
        # they have to be settled before any guard is lowered -- including the extraction's own.
        # The builder is constructed first because the derivation asks it where an object is in
        # the cast; `prime` comes last because it is the NARROWING pass and must run against the
        # settled map.
        self.mb = M.MachineBuilder(ir, is_death)
        self.mb.derive_room_valued()
        self.ts = extract(ir)
        # `prime` settles the casts/entries mutual recursion before anything reads either, so the
        # machines this emitter lifts are the second-pass ones. See MachineBuilder.prime.
        self.mb.prime()
        self.n_opaque = 0
        self._collect()

    def _homeless(self, sn):
        """Does script `sn` have no scope at all -- not a room, not a region, nothing arms it?

        Read only by the icon-bar pass, which will not take a script that already earned a home
        somewhere: its per-room evidence is real and must not be widened away."""
        return (sn not in self.ts.rooms and sn not in self.region_rooms
                and not self.armed_rooms.get(sn))

    # ---- collection --------------------------------------------------
    def _collect(self):
        ir = self.ir
        self.rooms = sorted(self.ts.rooms)
        self.items = sorted(self.ts.items)
        # machines with an effect, per room; each -> (room, inst, states-as-paths, entries, start)
        self.machines = []          # list of dict
        self.global_machines = []   # ...lifted from an ALWAYS-LIVE scope (the icon bar). Register
        #   effects and their costs only -- see where they are appended, and `global_homed`.
        self.reg_vals = {}          # global index -> set of int values (domain)
        self.loc_vals = {}          # (script, 'L'/'T', idx) -> set of int values
        self._loc_inc = set()       # counter keys with an inc op (need +1 saturation headroom)
        self._loc_dec = set()       # counter keys with a dec op (need -1 headroom)
        self.init_writes = {}       # room -> {gi: val} UNCONDITIONAL entry writes (initial value)
        self.init_seq = {}          # room -> ordered [(gi, val, guard)] entry writes, source order.
        self.init_deaths = set()    # rooms whose `init` writes DEATH -- arriving there kills you
        #   Conditional init writes (inside if/cond) keep their guard instead of being FORCED --
        #   the rm79 seal: `(NormalEgo)` g101:=0 unconditional, then `(= gCurrentStatus 11)` only
        #   `if gIslandStatus==2`; flattening forced g101=11 always -> every win edge (needs
        #   g101==0) sealed. Emitted as ordered guarded cases (last source wins where guard holds).
        self.deaths = []            # (room, guard) flat/machine deaths
        self.dropped_entries = []   # (room, guard) -- entry guards of machines we do NOT model.
        #   Requirement evidence only: the machine does nothing we track, but you still had to be
        #   holding something to start it. LSL2 has 66 such machines and NONE with an own() guard;
        #   KQ4 has 101 and four that matter (doBread/1, witchEye+witchMoan/6, shootLolotte/14).
        self.procs_by = {}          # (script, proc-name) -> body AST, for call-following
        for rn, s in ir.scripts.items():
            for name, body in s.procs.items():
                self.procs_by[(rn, name)] = body
        # REGIONS: a room's `(setRegions: R)` activates region script R while you are in
        # that room. Region-script effects (e.g. rm300.handleEvent's gWearingSunscreen:=3
        # on the ship voyage) apply in the rooms that set the region, NOT in an unreachable
        # "room R". region_rooms: region-script -> {rooms that activate it}.
        #
        # The room lookup here used to be `by_name["rm<N>"]` -- the LSL2 decompiler naming
        # convention, which extract._room_object stopped relying on when KQ4 turned out to
        # name its rooms `Room<N>`. That fix never reached this copy, so KQ4 mapped 0 region
        # scripts and every one of its 26 regions was dropped whole (LSL2: 9 regions over 62
        # rooms). SCI dispatches at three scopes -- Main, region, room -- and this is the
        # middle one; losing it silently loses every guard and effect that lives there.
        #
        # SCI1.1 hoists the whole map into ONE dispatcher in Main, keyed on the room being
        # entered (`(proc999_5 param1 600 605 ...) -> ((ScriptID param1) setRegions: 70)`), so
        # the per-room scan below found NOTHING on KQ6 -- zero regions, and with them the entire
        # `rLab` catacombs controller, `rgDead` and `rgCastle` went unlifted. Both spellings now
        # derive in vocab.derive_region_map, which reproduces LSL2's 9 and KQ4's 25 exactly.
        self.region_rooms = vocab.derive_region_map(ir, lambda s: _room_object(s, ir))
        # A CUTSCENE script is neither a room nor a region: it is a bag of Scripts that other
        # rooms arm with `setScript: (ScriptID s n)`. It still runs somewhere -- in the room that
        # armed it -- so it gets lifted there, on exactly the principle regions already use ("the
        # same machine really is live in each of those rooms"). Without this, script 344's
        # `nightMare` holds the ONLY newRoom into the realm of the dead and is never lifted at all.
        # Rooms/regions keep priority, so this only ever adds scripts that had no home.
        self.armed_rooms = {}
        # ...and a script whose object another script puts IN THE CAST. `setScript:` is one way to
        # bring a foreign script to life; `init:` is the other, and it is the one an NPC or a prop
        # arrives by. KQ6 needs both, twice over:
        #
        #     rm240.init                (ScriptID 241 lampSeller) init:     -- the pawn-shop seller
        #     enterDungeon.changeState  (ScriptID 822 boyGhost)   init:     -- the dungeon ghost boy
        #
        # Script 241 is where the old lamp is TRADED AWAY and script 822 is the handkerchief's only
        # use, so both items had a source and a use in the game and neither in our model. Counting
        # only `setScript:` left 183 of KQ6's 341 scripts with no home at all.
        #
        # Recognised through `extract.init_selectors`, the same per-class derivation `cast_conditions`
        # uses, so a game's own aliases (`addToPic:` on the View family) come along and a `Cursor`'s
        # `setLoop:` does not. Kept SEPARATE from `mb.arms` deliberately: that index answers "what
        # are this machine's entries", which is a `setScript:` question, while this one answers
        # "where does this script's code run", which is a scope question.
        cast_refs = {}
        isel = X.init_selectors(ir)
        for rn, sc in ir.scripts.items():
            for o in sc.objects:
                for _mn, body in o.methods.items():
                    for n in I.walk(body):
                        if n.get("t") != "Send":
                            continue
                        try:
                            recv, msgs = I.send_pairs(n)
                        except Exception:                      # noqa: BLE001
                            continue
                        tgt = ir.script_id_target(recv)
                        if not tgt or tgt[0] == rn:
                            continue                           # same script: not a cross-script home
                        to = ir.scripts.get(tgt[0])
                        obj = to.by_name.get(tgt[1]) if to else None
                        if obj is None:
                            continue
                        sels = isel.get(obj.species if obj.is_class else obj.super) or {"init"}
                        if any(sel in sels for sel, _p in msgs):
                            cast_refs.setdefault(tgt[0], set()).add(rn)
        for (tgt_script, _inst), sites in self.mb.arms.items():
            for (arm_script, _oname, _mn, _body) in sites:
                cast_refs.setdefault(tgt_script, set()).add(arm_script)
        for tgt_script, arms in cast_refs.items():
            for arm_script in arms:
                if arm_script in self.ts.rooms:
                    self.armed_rooms.setdefault(tgt_script, set()).add(arm_script)
                for r in self.region_rooms.get(arm_script, ()):
                    self.armed_rooms.setdefault(tgt_script, set()).add(r)
        # ...and a helper reached by CALLING its public procedures. `(proc441_2)` runs minoTrigger's
        # code, which is where the minotaur-defeated flag is SET; `(proc483_x)` is where the lettuce
        # and the potion are picked up. Neither script is a room or a region, so both went unwalked
        # entirely -- the flag was never WRITTEN in our model and so never qualified as a gating
        # register, and the two items had no source at all.
        #
        # Same principle as regions and armed scripts: the code runs in the rooms that invoke it.
        # Naturally selective rather than capped -- 9 of KQ6's 10 effectful helpers are called from
        # exactly ONE room. The tenth is the flag library itself, skipped because `lower_flags`
        # already rewrote every call to it into synthetic globals, so its body is redundant by
        # construction and lifting it would re-add the raw bit-array writes we just abstracted.
        # ...and TRANSITIVELY. A helper is often reached through another helper: KQ6's pawn
        # counter is rm280 -> counterInset -> placeOnCounter, and that last script holds the
        # `get:`/`put:` that actually hands the tinderbox over. Resolving one level left it
        # homeless, so three traded items had no source at all.
        for _round in range(6):
            grew = False
            for tgt, arms in cast_refs.items():
                for arm in arms:
                    via = self.armed_rooms.get(arm)
                    if via and not (via <= self.armed_rooms.get(tgt, set())):
                        self.armed_rooms.setdefault(tgt, set()).update(via)
                        grew = True
            if not grew:
                break
        flag_procs = set((vocab.derive_flags(ir) or (None, {}))[1])
        for sn, sc in ir.scripts.items():
            if sn in self.ts.rooms or sn in self.region_rooms or not sc.procs:
                continue
            if sc.procs and set(sc.procs) <= flag_procs:
                continue
            for cn, csc in ir.scripts.items():
                if cn == sn:
                    continue
                bodies = [b for o in csc.objects for b in o.methods.values()] + list(csc.procs.values())
                if not any(n.get("t") in ("PublicCall", "LocalCall") and n.get("name") in sc.procs
                           for b in bodies for n in I.walk(b)):
                    continue
                if cn in self.ts.rooms:
                    self.armed_rooms.setdefault(sn, set()).add(cn)
                for r in self.region_rooms.get(cn, ()):
                    self.armed_rooms.setdefault(sn, set()).add(r)
        # ...and the ALWAYS-LIVE dispatch scope SCI1 added: THE ICON BAR. An inventory item's
        # `doVerb` -- "use this item on that one" -- is dispatched by the icon bar, so nothing in
        # the game ever arms the script the item objects live in: no room sets it, no cutscene
        # casts it, no procedure calls it, and every pass above leaves it homeless. KQ6 mixes the
        # magic paint there (`KqInv doVerb 30` -> `(gCurRoom setScript: 915)` -> `mixPaintScr`),
        # which is the whole reason flag 22 had no writer at all and an EMPTY teacup opened the
        # long castle door. Derived in `vocab.inventory_scripts` from the item class table -- LSL2
        # and KQ4 declare their items in script 0, which IS `MAIN_SCRIPT`, so both are inert here.
        #
        # It runs WHEREVER YOU ARE, so it is homed to every room. What that must NOT buy is a
        # per-room REQUIREMENT: an action available everywhere is evidence about no room in
        # particular, and reading it as one turns every item into "needed here" in all 86 rooms --
        # measured, that costs five confirmed softlocks and gains thirteen false positives. The
        # scripts homed this way are recorded in `global_homed`, and `missability.build_maps`
        # refuses to read their guards as requirement evidence. Keep the EFFECT, drop the CLAIM.
        #
        # Only genuinely homeless scripts are taken, and transitively -- `mixPaintScr` is armed
        # from the inventory and lives nowhere else either. A script something else already arms
        # keeps the home it earned, and with it its per-room evidence.
        #
        # SIBLING, not replacement: `missability.GLOBAL_SCRIPTS` is the OTHER always-live scope
        # (Main, hardcoded {0} because script 0 is Main in every dialect). Neither consults the
        # other; see the comment there for why that is currently inert rather than wrong.
        self.global_homed = set()
        frontier = [s for s in sorted(vocab.inventory_scripts(ir)) if self._homeless(s)]
        while frontier:
            sn = frontier.pop()
            if sn in self.global_homed:
                continue
            self.global_homed.add(sn)
            self.armed_rooms[sn] = set(self.ts.rooms)
            frontier += [t for t, arms in sorted(cast_refs.items())
                         if sn in arms and t not in self.global_homed and self._homeless(t)]
        # Hoisted above the init/machine pass: `_init_writes` records room-LOCAL
        # seeds too, and it runs first.
        self.handler_writes = []       # (room, script, gi, val, guard)  -- script for CTR-local resolve
        self.handler_gets = []         # (room, script, item, guard)
        self.handler_drops = []        # (room, script, item, guard, dest) -- `gEgo put: N <dest>`
        #   handler. Consuming an item requires owning it; the Pamphlet handed to the bore on
        #   the plane (rm62) is a Said-handler consumption, invisible to the machine-body scan.
        self.handler_moves = []        # (room, script, item, dest, guard) -- the same transfers as
        #   gets/drops, but keeping the DESTINATION that `put:`/`moveTo:` carry. KQ4 uses
        #   pseudo-room numbers as item states (206 unplaced, 666 on the hook, 777 eaten,
        #   999 destroyed), so `where did it go` separates "elsewhere" from "gone" -- see
        #   `item_moves_to_world`, which is what keeps a bird placing a worm out of the
        #   dangerous-sink report.
        self.handler_locals = []       # (room, script, (vt,idx), val, guard)

        for rn, s in ir.scripts.items():
            # A region's machines run in the rooms that activate it, exactly as its handlers do
            # (below). Lifting them only for real rooms dropped 12 of KQ4's region scripts whole
            # -- among them regUnicorn's `uniActions`, the ONLY place the Golden_Bridle is ever
            # required. The duplication is not an approximation: the same machine really is live
            # in each of those rooms.
            # ...and MAIN is a SCOPE, not a room -- the fourth case, which the HANDLER pass
            # below spells out and this one did not. LSL2's script 0 happens to land in
            # `ts.rooms` so it was walked here by luck; KQ4's does not, so this pass hit
            # `continue` and `_init_writes(0, script0)` never ran. Lost with it: the whole of
            # KQ4's `Main::init` seeding -- global50=7, global26=1, global169=1, global205=1,
            # global16=230, global160=8, global116=1, the day/night clock among them -- while
            # register promotion, the per-room projections, the arrival commit and start-room
            # seeding all modelled those registers as starting at 0. Same rule, two places,
            # one of them fixed 90 lines below this one and not here.
            targets = (self.region_rooms.get(rn) or ({rn} if rn in self.ts.rooms else None)
                       or ({0} if rn == MAIN_SCRIPT else None)
                       or self.armed_rooms.get(rn))
            if not targets:
                continue
            if rn in self.ts.rooms or rn == MAIN_SCRIPT:
                self._init_writes(rn if rn in self.ts.rooms else 0, s)
                # A lowered ROOM LOCAL resets when the script reloads, i.e. on every entry --
                # exactly an unconditional entry write, so it rides the same channel (and the
                # same commit semantics) as any other arrival write. vocab.lower_room_locals
                # recorded the declared initial values per room.
                for gi, v in getattr(ir, "_room_local_resets", {}).get(rn, {}).items():
                    self.init_writes.setdefault(rn, {}).setdefault(gi, v)
            for m in self.mb.machines(s):
                for room in sorted(targets):
                    info = self._machine_info(room, m)
                    if info:
                        # AN ALWAYS-LIVE SCOPE CONTRIBUTES REGISTER EFFECTS AND THEIR COSTS. THAT
                        # IS ALL IT CONTRIBUTES, AND KEEPING IT OUT OF `machines` IS HOW WE SAY SO.
                        #
                        # Every other thing `machines` feeds is a claim about a PLACE, and the icon
                        # bar has no place. Measured on KQ6, one consumer at a time, each of which
                        # broke something real when the machine was left in the main list:
                        #   `required`   -> every item needed in all 86 rooms; the rm340->rm155
                        #                   guard grew to 45 items and five softlocks vanished
                        #   `sources`/`drops` -> `feather` acquired 86 destruction sites
                        #   EXIT         -> `newRoom:` from anywhere; two fabricated ways out of
                        #                   the pitch-dark rm406
                        #   `death_traps`-> an inventory action in a trap room read as an ESCAPE
                        #                   from it, so the tinderbox stopped being needed to
                        #                   survive the dark and a confirmed softlock vanished
                        # A separate list settles all four at once and, more to the point, settles
                        # the ones nobody has thought of: a new consumer of `machines` is right by
                        # default instead of needing to remember to ask. See
                        # [[same-rule-two-places]] -- this is that bug shape, four deep.
                        #
                        # The register build reads BOTH lists; nothing else reads this one.
                        #
                        # ⚠️ THE `doVerb`-ONLY BOUND DOES NOT APPLY HERE, and the handler pass
                        # below says so in a way that reads as if it did. There, the icon-bar
                        # scope is narrowed to `doVerb` because a `cue` is a callback and where it
                        # fires is the caller's business. HERE the machine is the whole point:
                        # `mixPaintScr` is a `changeState` machine armed from the inventory, and
                        # narrowing this pass the same way would drop the one write the scope
                        # exists to capture. So the two passes bound the scope DIFFERENTLY and on
                        # purpose -- what protects this one is not the method name but the list
                        # it lands in, which is why the separation above has to carry the weight.
                        info["global_scope"] = rn in self.global_homed
                        (self.global_machines if info["global_scope"]
                         else self.machines).append(info)
                    elif rn not in self.global_homed:
                        # ...and for the same reason, a GLOBAL machine we do not model contributes
                        # no dropped-entry evidence either. `dropped_entries` exists to say "you
                        # still had to be holding something to start it HERE", and "here" is the
                        # whole game for an inventory action.
                        # A machine with no effect WE TRACK is not modelled -- but being ENTERED
                        # under a guard is still evidence about what the player must be carrying.
                        # rm82's `shootLolotte` writes no global, gets no item and exits nowhere;
                        # all it does is start `lolotteDead`. Dropping it took the `has: 14` on
                        # its entry with it, so the Cupid's Bow had no recorded use at rm82 at
                        # all and `resource_exhaustion` could only report the unicorn rooms.
                        # The SLOT and the machine's name come along too: a machine we do not
                        # model is still a player action competing for the room's script, so it can
                        # be what CANCELS a timed death. KQ6's `lightItUp` is exactly that -- its
                        # entry is `own(tinderBox)`, and all it does is start a palette fade, so it
                        # is dropped and the only escape from the dark room went with it. The name
                        # is what lets `death_traps` still ask whether it re-arms the death.
                        for i, (K, eg) in enumerate(list(m.entries)):
                            if eg is not None:
                                recv = m.entry_recv[i] if i < len(m.entry_recv) else None
                                self.dropped_entries.append((room, eg, m.inst, recv))
                        for K, eg in list(m.init_entries):
                            if eg is not None:
                                self.dropped_entries.append((room, eg, m.inst, None))
        # player-action effects in handleEvent/doit: register writes + item get/put that
        # the game does NOT do via a changeState machine (e.g. `(= gLoweredLifeboats 1)`
        # when the player says "lower lifeboats"). Guard = the path condition (Said/opaque
        # permissive). Without these, promoted gates like `gLoweredLifeboats!=0` can never
        # open. Same shape as the disguise's gCurrentEgoView.
        for rn, s in ir.scripts.items():
            # target rooms: a region script's effects apply in the rooms that activate it;
            # a real room's in itself. (A region "room" R is never entered directly.)
            if rn in self.region_rooms:
                targets = self.region_rooms[rn]
            elif rn in self.ts.rooms:
                targets = {rn}
            elif rn == MAIN_SCRIPT:
                # Main is a SCOPE, not a room: its Game subclass's handleEvent/doit/newRoom run
                # everywhere. LSL2's script 0 happens to land in ts.rooms and so was walked;
                # KQ4's is not, so every effect in its Main was dropped -- including
                # `(gEgo put: 25 999)` at Main.sc:1246, the Magic Fruit being eaten. Recorded
                # against room 0 (as LSL2's already was); consumers that know Main is global
                # widen it -- see missability.GLOBAL_SCRIPTS.
                targets = {0}
            elif self.armed_rooms.get(rn):
                # ...and a script with no home of its own runs in the rooms that bring it to life,
                # exactly as the MACHINE pass above already decided. This copy of the same rule was
                # missing the fourth scope, so a foreign script's cutscenes were lifted while its
                # `doVerb`/`handleEvent` effects were dropped on the floor. KQ6's old lamp is the
                # case: `lampTradeScr::doVerb 5` does `(global0 put: 19)` -- no destination, i.e.
                # SCI's NOWHERE -- which is the trade that destroys it, and the only reason the
                # lamp can strand at all.
                targets = self.armed_rooms[rn]
            else:
                continue
            for room in targets:
                for o in s.objects:
                    # THE WALK STARTS AT THE OBJECT'S PRESENCE CONDITION -- the third and last
                    # site that attributes an object's methods, and the second that was missing
                    # it (see machine._build's two entry scans). An object that is not `init:`ed
                    # cannot be clicked, so its handler's effects are gated on whatever gated
                    # its init; walking the body from an EMPTY path condition asserts instead
                    # that every object in a script is live in every room the script serves.
                    #
                    # KQ5's Mordack-castle region is what this costs. `castle.sc` runs in all
                    # 16 castle rooms, `theCat`'s handleEvent answers the fish with
                    # `(gRoom setScript: theThrowFishScript)` and the pea bag with the bagging
                    # script -- so BOTH items were recorded as used in every one of those rooms,
                    # rm683 (`cdCassimaToon`, the cutscene after Cassima takes the locket)
                    # included, and `toll_strandings` demanded the player carry them into it.
                    # The cat is placed by `proc550_16` in three rooms and is nowhere near.
                    og = X.cast_guard(self.mb._cast(s), o.name)
                    for mn, body in o.methods.items():
                        # changeState -> machine; init -> forced entry write. EVERY other
                        # method's effects captured here (globals + locals + gets),
                        # FOLLOWING calls into other scripts, so nothing is absent.
                        if mn in ("changeState", "init"):
                            continue
                        # WHAT THE ICON BAR DISPATCHES IS `doVerb`, AND ONLY `doVerb` -- IN THIS
                        # PASS. That send -- `(feature doVerb: (curIcon message:))`, the contract
                        # `extract` and `vocab.doverb_item_messages` already key on -- is the
                        # entire reason this script is live everywhere, so it is the extent of the
                        # claim a HANDLER may make. The other methods are CALLBACKS: `cue` fires
                        # when whatever the item was waiting on completes, and WHERE that happens
                        # is the caller's business.
                        #
                        # The MACHINE pass above deliberately does NOT apply this bound -- its
                        # `changeState` machines are exactly what the scope is lifted for -- and
                        # is protected instead by landing them in `global_machines`. Two passes,
                        # two different bounds, each stated where it is enforced.
                        # Without this line the scope asserts that every method of the inventory
                        # script is something the player can do in any room, which is not true of a
                        # callback -- KQ6's `skull::cue` clears the ember bit
                        # (`state: (& (self state:) $fff7)`), and lifted whole it says the skull
                        # can be emptied anywhere.
                        #
                        # ⚠️ MEASURED INERT on today's corpus: removed, the KQ6 verdicts,
                        # `reobtainable_rooms` and both goldens are unchanged. It is here because
                        # it BOUNDS a claim this change introduces, not because a finding rests on
                        # it -- so what it asserts is pinned directly (the `cue` write is not
                        # attributed to every room), never via an item list.
                        if rn in self.global_homed and mn != "doVerb":
                            continue
                        # A `doVerb` body dispatches on the item the player used, so its guards
                        # only read as OWN inside that context -- `extract._walk` sets it and this
                        # walk did not, which is the same rule in two places. Without it KQ6's
                        # `(switch param1 (72 ((ScriptID 30 0) scarfOnMino: 1)))` records the write
                        # that kills the minotaur as UNGUARDED, so the escape from the catacombs
                        # needs no red scarf and the whole carry-IN class cannot strand.
                        with verb_param_scope(mn):
                            self._hwalk(room, rn, body, [] if og is None else [og], set())
                # ...AND A PROCEDURE IS NOT A HANDLER. The engine dispatches METHODS -- `doit`,
                # `handleEvent`, `doVerb`, `changeState`; nothing ever dispatches a script-level
                # procedure, which runs only where something CALLS it. `_hwalk` (and the machine
                # lift, and `extract._walk`) already follow those calls in the caller's own room
                # context, so walking every proc standalone here added nothing for a called one
                # and FABRICATED a scope for an uncalled one.
                #
                # In MAIN that fabrication is the whole game: LB2's `proc0_13`..`proc0_17` are the
                # debug jump-to-act setup, called only from `whereTo` (script 29, a room with no
                # in-edges), and they hand over nine items each -- `(ego get: -1 25 16 17 30 27 26
                # 12 31 13)`. Walked as Main handlers they became sources at room 0, which
                # `_sink_rooms` widens to EVERY room, so half the inventory was obtainable
                # anywhere. That is what made the variadic `get:` read a net regression when it
                # was first built (docs/LB2-ORACLE.md §7o): the read is right, and this was the
                # thing it was uncovering.
                #
                # Nothing here is a debug-detection rule -- it never asks what a script is FOR.
                # `whereTo`'s own methods still walk these procs, in room 29, where they belong.
        self._walk_game_newroom(ir)
        for room, script, gi, v, g in self.handler_writes:
            self.reg_vals.setdefault(gi, {0}).add(v)
            self._scan_domains_guard(g, script)      # CTR-local values in the guard
        for room, script, key, v, g in self.handler_locals:
            k = (script,) + key
            self.loc_vals.setdefault(k, {0})
            if isinstance(v, int):
                self.loc_vals[k].add(v)
            elif v == ("inc",):
                self._loc_inc.add(k)
            elif v == ("dec",):
                self._loc_dec.add(k)
            self._scan_domains_guard(g, script)
        for room, script, it, g in self.handler_gets:
            self._scan_domains_guard(g, script)
        # domains: include compared values for globals/locals too (scan all machine guards).
        # BOTH lists: a register an always-live scope writes has to be in the domain or it can
        # never be promoted, which is the whole point of lifting that scope (KQ6's flag 22, the
        # magic paint, is written nowhere else). The other consumers below take `self.machines`
        # alone, deliberately -- see where `global_machines` is filled.
        for info in self.machines + self.global_machines:
            for K, paths in info["states"].items():
                for (guard, writes, gets, counters, trans) in paths:
                    for gi, v in writes:
                        self.reg_vals.setdefault(gi, {0}).add(v)
                    for name, kind, val in counters:
                        key = (info["script"],) + name
                        self.loc_vals.setdefault(key, {0})
                        if val is not None:
                            self.loc_vals[key].add(val)
                        if kind == "inc":
                            self._loc_inc.add(key)
                        elif kind == "dec":
                            self._loc_dec.add(key)
                    self._scan_domains(guard, info["script"])
            for K, eg in info["entries"]:
                self._scan_domains_guard(eg, info["script"])
        for room, seq in self.init_seq.items():
            for gi, v, g in seq:
                self.reg_vals.setdefault(gi, {0}).add(v)
                self._scan_domains_guard(g, None)   # guard values (e.g. gIslandStatus==2)
        # exits the machines can deliver -> which changeState newRoom targets DON'T need a
        # flat fallback (the rest do, gated by their extract path condition).
        self.machine_delivered = set()
        for info in self.machines:
            for dst in info.get("delivered", ()):
                self.machine_delivered.add((info["room"], dst))
        # ...and the ACQUISITIONS they make, keyed the same way. `extract` walks a changeState body
        # for items too (`movement=False` suppresses only its exits), so the same `get:` arrives
        # twice: once flat and guardless, once through the machine, which knows what arming the
        # cutscene costs. Only the second reading can tell a first pickup from a take-back.
        self.machine_gets = set()
        for info in self.machines:
            for paths in info["states"].values():
                for (_g, _w, gg, _c, _tr) in paths:
                    for it in gg:
                        self.machine_gets.add((info["room"], info["inst"], it))
        # EVERY item transfer a machine makes, destination kept: (room, script, item, guard, dest),
        # the shape `handler_moves` already uses so a reader can concatenate the two without
        # caring which scope moved the item. A cutscene that hands an item BACK to the world --
        # KQ4's Cupid parking his bow in limbo 202 until he next flies past -- is invisible in
        # `machine_gets` (item only, and this one is not a get) and in `handler_moves` (it is not
        # a handler), so the only reading of "the item went somewhere" was the flat one that
        # cannot say WHERE. See `drop_is_permanent`.
        self.machine_moves = []
        for info in self.machines:
            for (it, dest, g) in info.get("moves", ()):
                self.machine_moves.append((info["room"], info["script"], it, g, dest))

        # Control-map oracle FIRST (reads the PIC control plane + VIEW cels, not declared):
        #  - prop-gate  (rm82): machine EXIT->83 requires causedEruption (the aDoor Prop covers
        #    the onControl-$0004 floor until the bomb opens it);
        #  - crossing-gate (rm47): the win-ward exit that PROVABLY forces the doit death-rect
        #    inherits the disguise requirement, per-exit (does not over-gate the retreat).
        self._apply_control_gates()
        self._apply_polygon_gates()
        self._apply_dead_nav()

        # finalize domains; single-value dims fold to constants (SMV rejects init on them)
        self.reg_dom, self.reg_const = {}, {}
        for gi, vs in self.reg_vals.items():
            lo, hi = min(vs), max(vs)
            (self.reg_const if lo == hi else self.reg_dom)[gi] = lo if lo == hi else (lo, hi)
        self.loc_dom, self.loc_const = {}, {}
        for k, vs in self.loc_vals.items():
            lo, hi = min(vs), max(vs)
            # saturation headroom: a saturating inc emits `lv+1` (static range up to hi+1) that
            # the `>= hi ? hi` ternary clamps at runtime -- declare hi+1 (unreachable sentinel)
            # so nuXmv's static range check doesn't false-warn "cannot assign hi+1". Ditto dec.
            hi += 1 if k in self._loc_inc else 0
            lo -= 1 if k in self._loc_dec else 0
            (self.loc_const if lo == hi else self.loc_dom)[k] = lo if lo == hi else (lo, hi)

    def _inline_calls(self, node, script, seen, depth=0):
        """Return a copy of the AST with PublicCall/LocalCall replaced by the callee's
        body (across scripts), so effects in shared procedures (e.g. proc0_2's
        gCurrentStatus:=0 reset at a changeState cutscene end) are captured in the
        machine's control flow. Params are not substituted -- we capture concrete-valued
        effects; param-valued writes drop out (conservative)."""
        if node is None or depth > 6:
            return node
        if node["t"] in ("PublicCall", "LocalCall"):
            kids = node.get("kids") or []
            if kids and isinstance(kids[-1], dict) and kids[-1].get("t") == "Self":
                # a CUE call `(procN ... self)` -- its meaning is "run, then cue -> ADVANCE" (SCI1
                # prints messages via a proc), NOT "splice the proc's effects here". Inlining it
                # would erase the cue and PARK the state, so `_interp`'s proc-cue rule never fires.
                return node
            tgt, name = I.proc_ref(self.ir, node, script)
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                return self._inline_calls(body, tgt, seen | {name}, depth + 1)
            return node
        new = dict(node)
        new["kids"] = [self._inline_calls(k, script, seen, depth) for k in node.get("kids", [])]
        return new

    def _machine_info(self, room, m):
        states = {}
        has_effect = False
        steps_by_state = {}
        for K, body in m.bodies.items():
            body = self._inline_calls(body, m.script, set())
            steps_by_state[K] = [C._interp(p, self.is_death, state_k=K)
                                 for p in C._paths_of(body)]
        C.carry_cues(steps_by_state, m.start)   # SCI cross-state cue carry (PARK -> ADVANCE)
        entry_states = {k for k, _ in m.entries} | {k for k, _ in m.init_entries}
        C.compress_chains(steps_by_state, entry_states, m.start)   # collapse effect-free ADVANCE runs
        for K, steps in steps_by_state.items():
            paths = []
            for st in steps:
                if C.step_effects(st) or st.trans[0] in ("EXIT", "DEATH"):
                    has_effect = True
                # one tuple normally; several when the step counts a global up or down, or
                # computes its destination (`newRoom: <var>`) -- one branch per room it can hold
                paths.extend(C.step_paths(st, m.glob_dom, m.var_dests))
            states[K] = paths
        # Items CONSUMED (`gEgo put: N -1`) on a SURVIVABLE path: consuming an item requires
        # owning it (the Flower at rm50 has no own() guard at all, only the consumption). Skip
        # death-bound paths -- consuming on the way to a death is a TRAP, not a requirement.
        succ, deadK = {}, set()
        for K, steps in steps_by_state.items():
            for st in steps:
                t = st.trans
                if t[0] == "DEATH":
                    deadK.add(K)
                elif t[0] == "ADVANCE":
                    succ.setdefault(K, set()).add(K + 1)
                elif t[0] == "JUMP":
                    succ.setdefault(K, set()).add(t[1])
                elif t[0] == "SETSTATE":
                    succ.setdefault(K, set()).add(t[1] + 1)
        dr, changed = set(deadK), True
        while changed:
            changed = False
            for K, ss in succ.items():
                if K not in dr and (ss & dr):
                    dr.add(K); changed = True
        drops = set()
        # ...and the same transfers WITH their destination and path condition. `drops` answers
        # "was this item consumed here"; `moves` answers "where did it GO, and from what owner" --
        # the two facts an owner-graph needs and the reason `machine_gets` (item only) could not
        # supply them. Same survivable-path filter, so the two readings cannot disagree about
        # which steps count.
        moves = []
        for K, steps in steps_by_state.items():
            for st in steps:
                if not (st.drops or st.moves):
                    continue
                t = st.trans
                tgt = (K + 1 if t[0] == "ADVANCE" else t[1] if t[0] == "JUMP" else
                       t[1] + 1 if t[0] == "SETSTATE" else None)
                if t[0] == "DEATH" or (tgt is not None and tgt in dr):
                    continue
                drops |= set(st.drops)
                for (it, dest) in st.moves:
                    moves.append((it, dest, list(st.guard)))
        if not has_effect:
            return None
        # ...and it must be able to RUN. A machine whose `start` is not among its own states and
        # which nothing ever enters can never execute, so modelling it would contribute phantom
        # edges, sources and requirements -- the very bypass the start-state fall-through hack
        # used to create. Separate question from `has_effect`, and keeping them separate is what
        # surfaced this: widening the effect test alone resurrected rm43's MDscript, which drops
        # an item and has no way in.
        if m.start not in states and not m.entries and not m.init_entries:
            return None
        # which exits this machine can actually DELIVER (control_exits): a changeState
        # newRoom target the machine cannot walk to needs a flat fallback so the room
        # isn't a false dead-end.
        try:
            exits, _d = C.compile_machine(m, self.is_death)
            delivered = set(r for r, g, w in exits)
        except Exception:
            delivered = set()
        return {"room": room, "inst": m.inst, "script": m.script, "states": states,
                "entries": m.entries, "init_entries": m.init_entries,
                "entry_locals": m.entry_locals, "init_entry_locals": m.init_entry_locals,
                "entry_armers": m.entry_armers, "entry_recv": m.entry_recv,
                "entry_sources": m.entry_sources, "entry_site": m.entry_site,
                "local_regs": dict(getattr(m, "local_regs", None) or {}),
                "restores_control": set(getattr(m, "restores_control", None) or ()),
                "chase_states": set(getattr(m, "chase_states", None) or ()),
                "start": m.start, "delivered": delivered, "drops": drops, "moves": moves}

    def edge_hit_registers(self):
        """Registers that carry the ego's `edgeHit` CODE, discovered from identity copies.

        A room that has to remember which way the ego left stores the direction somewhere the next
        room can read. KQ6's labyrinth does exactly that, because the maze walker needs the
        direction to work out which cell you arrive in:

            (method (doit)
                (cond ...
                      ((== (global0 edgeHit:) 3) (rLab prevEdgeHit: 3) ...)
                      ((== (global0 edgeHit:) 1) (rLab prevEdgeHit: 1) ...)))

        Those two writes are the proof: a register assigned the constant N under the guard
        `edgeHit == N` is carrying edgeHit's own numbering, so `R == K` elsewhere means the same
        thing as the POS atom for K -- INCLUDING codes never written that way. rLab also sets
        prevEdgeHit 2 and 4 from `onControl` colours (the maze uses control regions for left and
        right), and those inherit the same code space once the identity writes establish it.

        Requires TWO witnesses. One identity write could be coincidence -- a register that happens
        to take the value 3 inside a branch testing for 3 -- while two different codes agreeing is
        the register tracking the selector. Nothing here names a selector or a game."""
        if hasattr(self, "_edge_regs"):
            return self._edge_regs
        witnesses = collections.defaultdict(set)
        for room, script, gi, v, g in self.handler_writes:
            if v is not None and _has_pos_edge(g, {v}):
                witnesses[gi].add(v)
        for info in self.machines:
            for K, paths in info["states"].items():
                for (g, w, gg, c, tr) in paths:
                    for (gi, v) in w:
                        if v is not None and _has_pos_edge(g, {v}):
                            witnesses[gi].add(v)
        self._edge_regs = frozenset(gi for gi, vs in witnesses.items() if len(vs) >= 2)
        return self._edge_regs

    def _apply_dead_nav(self):
        """Consume polygons.dead_nav_exits: a declared s/e/w prop whose engine trigger zone the
        room's own UNCONDITIONAL obstacle layout seals off is a dead letter, and the free flat
        edge `_nav_edges` invented from it is REMOVED -- by its `via` provenance ("nav:<dir>"),
        so a scripted crossing to the same destination is untouched. LB2's rm330 `south 250` is
        the case (docs/LB2-ORACLE.md §7z): the only free way from the museum steps back into
        the street, at every act, in a room whose polygon stops the ego 20px short of the south
        trigger. Removal is the unsafe direction; every refusal lives in `dead_nav_exits`
        (unconditional layouts only, no setRegions, base-geometry directions only -- north
        needs the ego's rect height and is never claimed)."""
        self.dead_nav = []
        try:
            import polygons as PG
        except Exception as e:                              # noqa: BLE001
            _degraded("dead-nav (whole game)", e)
            return
        for room in sorted({e.src for e in self.ts.edges if e.via.startswith("nav:")}):
            try:
                rows = PG.dead_nav_exits(self.ir, room)
            except Exception as e:                          # noqa: BLE001
                _degraded("dead-nav for rm%s" % room, e)
                continue
            for row in rows:
                gone = [e for e in self.ts.edges
                        if e.src == room and e.dst == row["declared_room"]
                        and e.via == "nav:" + row["edge"]]
                if gone:
                    self.ts.edges = [e for e in self.ts.edges if not any(e is g for g in gone)]
                    self.dead_nav.append(row)

    def _apply_polygon_gates(self):
        """Consume polygons.polygon_gates: a screen edge a room's obstacle layout only OPENS
        under some condition is a real gate on the positional exit that leaves by it.

        SCI1.1 blocks with pathfinder polygons rather than the PIC control plane, so this is the
        SCI1.1 half of what `_apply_control_gates` does for SCO0. The exit is recognised by its own
        `edgeHit` test -- `atom` already renders that as a POS atom carrying the edge code -- so
        nothing here needs to know which room or which edge; both come from the data."""
        self.polygon_gates = []
        try:
            import polygons as PG
        except Exception as e:                              # noqa: BLE001
            _degraded("polygon gates (whole game)", e)
            return
        by_room = {}
        for info in self.machines:
            by_room.setdefault(info["room"], []).append(info)
        for room in sorted(by_room):
            try:
                gates = PG.polygon_gates(self.ir, room)
            except Exception as e:                          # noqa: BLE001
                _degraded("polygon gates for rm%s" % room, e)
                continue
            for gate in gates:
                self.polygon_gates.append(gate)
                want = [c for c, nm in PG.EDGES.items() if nm == gate["edge"]]
                eregs = self.edge_hit_registers()
                for info in by_room[room]:
                    ents = info.get("entries") or []
                    for i, (K, eg) in enumerate(ents):
                        if not _has_pos_edge(eg, want, eregs):
                            continue
                        ents[i] = (K, GAnd(list(gate["guard"]) + [eg]) if eg is not None
                                   else (gate["guard"][0] if len(gate["guard"]) == 1
                                         else GAnd(list(gate["guard"]))))
                    # ...and on the EXIT itself, because a room need not decide the direction on
                    # the way IN. KQ6's labyrinth reads it in the state body instead --
                    # `(switch ((ScriptID 30 0) prevEdgeHit:) (2 (global2 newRoom: 440)))` -- so
                    # the entry carries no edge test and only the exit path does. Same rule, the
                    # other place a machine can ask the question; the prop-gate branch of
                    # _apply_control_gates gates exits exactly this way.
                    for K, paths in list(info["states"].items()):
                        newp = []
                        for path in paths:
                            g, rest, trans = path[0], path[1:], path[4]
                            if (trans and trans[0] == "EXIT"
                                    and _has_pos_edge(g, want, eregs)):
                                g = list(g) + list(gate["guard"])
                            newp.append((g,) + rest)
                        info["states"][K] = newp

    def _apply_control_gates(self):
        """Consume control_oracle.find_gates: for each prop-gate, AND the derived door-open
        latch onto the machine EXIT that the gated onControl trigger delivers. Everything is
        read (PIC control plane, VIEW cel footprints, the opener state's own write), nothing
        declared; the latch is the persistent write the opener state makes (rm82: causedEruption
        L3:=1 in state 16). This is the general Sierra door/gate/movable-block mechanism."""
        self.control_gates = []
        if not getattr(self.cfg, "resource_dir", ""):
            return
        try:
            import control_oracle as CO
            gates = CO.find_gates(self.cfg, self.ir)
        except Exception as e:                              # noqa: BLE001
            # ONE exception here used to remove every positional gate in the game, silently.
            _degraded("control-plane gates (whole game)", e)
            return
        self.control_gates = gates
        for gate in gates:
            room = gate["room"]
            if gate.get("kind") == "prop":
                # prop-gate (rm82 door): gate the machine EXIT->gated_room on the opener latch.
                latch = gate.get("opener_latch")
                gr = gate.get("gated_room")
                if not latch or gr is None:
                    continue
                vt, idx, val = latch
                self.loc_vals.setdefault((room, vt, idx), {0}).add(val)   # give the latch a domain
                guard = ("CTR", (vt, idx), "==", val)
                for info in self.machines:
                    if info["room"] != room:
                        continue
                    for K, paths in list(info["states"].items()):
                        newp = []
                        for path in paths:
                            g, rest, trans = path[0], path[1:], path[4]
                            if trans[0] == "EXIT" and trans[1] == gr:
                                g = list(g) + [guard]
                            newp.append((g,) + rest)
                        info["states"][K] = newp
            elif gate.get("kind") == "crossing":
                # crossing-gate (rm47 disguise): the win-ward flat exit (proven to force the
                # doit rect) requires the safe local value, i.e. NOT(L==bad). Only this exit is
                # gated -- only this proven-forced exit; the retreat exit is left free.
                dst = gate.get("gated_room")
                vt, idx = gate["safe_local"]
                bad = gate["bad_value"]
                if dst is None:
                    continue
                self.loc_vals.setdefault((room, vt, idx), {0}).add(bad)
                # Prefer the derived DISGUISE CONDITION (persistent globals, e.g. gBodyWaxed &
                # egoView==151) -- it makes the disguise ITEMS required (egoView is item-gated)
                # and can't be satisfied by ARMING the henchmen (henchStatus==1). Fall back to
                # the local's safe value only if the init disguise-write wasn't found.
                safe = gate.get("safe_guard") or GNot(("CTR", (vt, idx), "==", bad))
                for e in self.ts.edges:
                    if e.src == room and e.dst == dst:
                        e.guard = safe if e.guard is None else GAnd([e.guard, safe])

    def _walk_game_newroom(self, ir):
        """`Game::newRoom` runs on EVERY room change, so its effects belong in every room.

        This is the one method whose scope is neither "this room" nor "pseudo-room 0": the engine
        calls it as the player leaves anywhere for anywhere. KQ4's nightfall lives here and
        nowhere else --

            (method (newRoom param1)                              ; Main.sc:924
              (if (and (== global100 0) (== global101 0) ... (< 20 global160 30))
                  (= global100 1) ...))                           ; NIGHT

        -- so recorded against room 0 it could never gate anything, and night simply never fell in
        the model. Recorded in every room it becomes what it actually is: a transition available
        wherever you are, whose trigger (the wall clock) the player does not control. The product
        already treats in-room register writes as unguarded and free, which is exactly the right
        reading for an adversarial one -- see missability._psucc.

        LSL2's `Main::newRoom` does the same thing with `(= global127 0)`, a real gating register
        it clears on every transition; modelling it only in room 0 was wrong there too."""
        main = ir.script(MAIN_SCRIPT)
        if main is None:
            return
        rooms = sorted(self.ts.rooms)
        for o in main.objects:
            body = o.methods.get("newRoom")
            if body is None:
                continue
            for room in rooms:
                self._hwalk(room, MAIN_SCRIPT, body, [], set())

    def _hwalk(self, room, script, node, pc, seen):
        """Path-condition walk of a handler; record global + local writes + item transfers,
        FOLLOWING PublicCall/LocalCall into their procedures (across scripts).

        Control flow comes from `extract.walk_stream` / `ir.control_shape` -- this used to
        re-implement If and Cond itself, in code identical to extract's and machine's, and
        handled neither Switch nor Loop, so both were silently dropped here."""
        from extract import walk_stream
        walk_stream(node, pc, lambda n, p: self._heffect(room, script, n, p, seen))

    def _heffect(self, room, script, node, pc, seen):
        """What one statement MEANS to the handler model. The part that is ours, not shared."""
        tp = node["t"]
        if tp == "Assignment":
            dst, src = node["kids"][0], node["kids"][1]
            v = _int(src.get("value"))
            if I.is_global(dst) and v is not None and not self.is_death(dst["index"], v):
                self.handler_writes.append((room, script, dst["index"], v, _conj_atoms(pc)))
            elif I.is_local_or_temp(dst):
                self.handler_locals.append((room, script, (dst["vtype"][0], dst["index"]),
                                            v, _conj_atoms(pc)))
        elif tp == "Increment" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("inc",), _conj_atoms(pc)))
        elif tp == "Decrement" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("dec",), _conj_atoms(pc)))
        elif tp == "Send":
            recv, msgs = I.send_pairs(node)
            for sel, params in msgs:
                for (it, dest) in item_transfers(recv, sel, params):
                    # AN ITEM TRANSFER IS A FACT ABOUT A PLACE, AND THE ICON BAR HAS NO PLACE.
                    # `sources`, `drops` and every sink detector read these rows as "the game
                    # hands X over / invites you to spend X *here*". An inventory `doVerb` is
                    # dispatched wherever you are standing, so lifting it into all 86 rooms does
                    # not make that reading true 86 times over -- it makes it meaningless, and
                    # measured on KQ6 it is what collapses the analysis (the catacombs frontier
                    # loses its brick guard, `feather` acquires 86 destruction sites).
                    #
                    # A REGISTER write from the same scope is a different claim and is kept: "you
                    # can make flag 22 true in this room, at this cost" is true in every room, and
                    # the cost path (`cheapest`) is exactly where the teacup's Styx water belongs.
                    # That asymmetry is the whole point of the scope -- see `global_homed`.
                    #
                    # KNOWN LIMIT, stated rather than hidden: an item obtainable ONLY by an
                    # inventory combination has no source here. That is the pre-existing
                    # behaviour (the scope was not walked at all), not a new loss.
                    if script in self.global_homed:
                        continue
                    g = _conj_atoms(pc)
                    self.handler_moves.append((room, script, it, dest, g))
                    if dest == EGO:
                        self.handler_gets.append((room, script, it, g))
                    else:
                        self.handler_drops.append((room, script, it, g, dest))
        elif tp in ("PublicCall", "LocalCall"):
            self._follow_call(room, script, node, pc, seen)

    def _follow_call(self, room, script, node, pc, seen):
        # PublicCall carries its script; Local = same. `proc_ref` resolves a local proc's
        # REGISTRY key from the call's offset -- see ir.proc_ref.
        tgt_script, name = I.proc_ref(self.ir, node, script)
        if tgt_script == 255:                      # script 255 = Print/Dialog: text, no effect
            return
        body = self.procs_by.get((tgt_script, name))
        if body is None or name in seen:
            return
        self._hwalk(room, tgt_script, body, pc, seen | {name})

    def _init_writes(self, room, script):
        # `by_name["rm<N>"]` -- the LSL2 decompiler naming convention, for the FOURTH time. KQ4
        # names its rooms `Room<N>`, so NO KQ4 room's `init` was ever walked: every entry write,
        # global or local, was missing. `_room_object` asks about inheritance instead.
        obj = _room_object(script, self.ir)
        if obj is None or "init" not in obj.methods:
            return
        # Entry global writes WITH their path condition, FOLLOWING calls (e.g. proc0_2 =
        # the hands-on reset gCurrentStatus:=0, called from 66 room inits). Records the full
        # ordered guarded sequence; UNCONDITIONAL writes ALSO feed init_writes (initial value).
        self._init_walk(room, script.number, obj.methods["init"], [], set())

    def _init_walk(self, room, script, node, pc, seen):
        """Entry writes with their path condition. Control flow is shared (walk_stream); the one
        policy that is ours is `undecided=OPAQUE`: a write inside a switch case or a loop must be
        POSSIBLE, never FORCED. Forcing them is the rm79 seal -- init set gIslandStatus:=3
        unconditionally and every win edge needing g101==0 died."""
        from extract import walk_stream
        walk_stream(node, pc, lambda n, p: self._init_leaf(room, script, n, p, seen),
                    undecided=Pred("OPAQUE"))

    def _init_leaf(self, room, script, node, pc, seen):
        tp = node["t"]
        # ROOM LOCALS set in init. Dropped until now, and that is where a room's own state is
        # seeded: KQ4's ocean (rm31) is a 2-D grid in local1/local2, and `init` chooses the cell
        # from `(switch global12 ...)` -- which previous room you came from. With switch case
        # labels now modelled as guards (see ir.control_shape), those seeds carry
        # `global12 == 44` and the like, which is exactly the fact that the whale's belly puts
        # you one step from the island.
        if tp == "Assignment" and I.is_local_or_temp(node["kids"][0]):
            d, src = node["kids"][0], node["kids"][1]
            v = _int(src.get("value"))
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        v, _conj_atoms(pc)))
        elif tp == "Increment" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("inc",), _conj_atoms(pc)))
        elif tp == "Decrement" and I.is_local_or_temp(node["kids"][0]):
            d = node["kids"][0]
            self.handler_locals.append((room, script, (d["vtype"][0], d["index"]),
                                        ("dec",), _conj_atoms(pc)))
        if tp == "Assignment" and I.is_global(node["kids"][0]):
            gi, v = node["kids"][0]["index"], _int(node["kids"][1].get("value"))
            # A DEATH written by a room's own `init` means ARRIVING HERE KILLS YOU, and it is not
            # an ordinary entry write -- so it stays out of `init_seq`/`init_writes` (modelling it
            # as "entering sets register R" would be nonsense) but it must not vanish either. It
            # used to do exactly that: LB2's death screen is a ROOM, its death lives in `init`,
            # and with no machine for it the game ended up with ZERO deaths. Nothing noticed until
            # the room was made terminal and `discover_goal` -- "terminal, reachable, never fatal"
            # -- promoted the Restore/Restart screen to a WINNING ENDING.
            if v is not None and self.is_death(gi, v):
                self.init_deaths.add(room)
            if v is not None and not self.is_death(gi, v):
                g = _conj_atoms(pc)
                self.init_seq.setdefault(room, []).append((gi, v, g))
                if g is None:                    # unconditional -> also the initial value
                    self.init_writes.setdefault(room, {})[gi] = v
        elif tp in ("PublicCall", "LocalCall"):
            tgt, name = I.proc_ref(self.ir, node, script)
            body = self.procs_by.get((tgt, name))
            if tgt != 255 and body is not None and name not in seen:
                self._init_walk(room, tgt, body, pc, seen | {name})

    def _scan_domains(self, guard, script):
        for a in guard:
            if isinstance(a, tuple) and a and a[0] == "CTR":
                key = (script,) + a[1]
                self.loc_vals.setdefault(key, {0}).add(a[3])
            else:
                self._scan_domains_guard(a, script)

    def _scan_domains_guard(self, g, script):
        if isinstance(g, tuple) and g and g[0] == "CTR":       # local-compare guard
            if script is not None:
                self.loc_vals.setdefault((script,) + g[1], {0}).add(g[3])
        elif isinstance(g, Pred) and g.kind == "CMP":
            v = _int(g.value)
            if v is not None:
                self.reg_vals.setdefault(g.var, {0}).add(v)
        elif isinstance(g, (GAnd, GOr)):
            for k in g.kids:
                self._scan_domains_guard(k, script)
        elif isinstance(g, GNot):
            self._scan_domains_guard(g.kid, script)

    # ---- guard -> SMV ------------------------------------------------
    def _permissive(self):
        # An opaque (unresolvable) guard atom. Opaques are INDEPENDENT fresh free choices, so a
        # guard `real & f(opaques)` is enabled exactly when `real` holds -- f is always
        # satisfiable by some opaque assignment. We therefore EXISTENTIALLY PROJECT the opaques
        # out: `_gx` propagates this OPAQUE sentinel (dropped in AND, absorbs OR to TRUE, stays
        # OPAQUE under NOT) and the public `gexpr` maps a surviving OPAQUE to TRUE. The result is
        # reachability-IDENTICAL to a free-input encoding but emits ZERO free booleans -- the
        # dominant width reduction for nuXmv (was ~1500 opaque IVARs on LSL2).
        return "OPAQUE"

    def _posexpr(self, g):
        """A POS guard -> SMV over the ego's free (x,y) (posx/posy IVARs). ONE consistent
        free choice per step, so `edge east (posx>=316)` implies `inRect [86..333]`
        unavoidably. onControl stays opaque (control-map, not a function of (x,y))."""
        if g[1] == "rect":
            a, b, c, d = g[2]
            parts = []
            if a > 0: parts.append(f"posx >= {a}")
            if c < 319: parts.append(f"posx <= {c}")
            if b > 0: parts.append(f"posy >= {b}")
            if d < 189: parts.append(f"posy <= {d}")
            return "(" + " & ".join(parts) + ")" if parts else "TRUE"
        if g[1] == "edge":   # SCI edgeHit: 1=top, 2=right, 3=bottom, 4=left
            return {1: "posy <= 4", 2: "posx >= 316", 3: "posy >= 186",
                    4: "posx <= 4"}.get(g[2], self._permissive())
        return self._permissive()

    def gexpr(self, g, script):
        """External guard tree -> SMV; script gives the counter namespace for CTR. Opaques are
        existentially projected out (see _permissive): `_gx` may return the OPAQUE sentinel,
        which at the top level means the guard is freely satisfiable -> TRUE."""
        r = self._gx(g, script)
        return "TRUE" if r == "OPAQUE" else r

    def _gx(self, g, script):
        if g is None:
            return "TRUE"
        if isinstance(g, tuple) and g and g[0] == "CTR":
            key = (script,) + g[1]
            if key in self.loc_dom:
                op = "=" if g[2] == "==" else g[2]
                return f"{self._lv(key)} {op} {g[3]}"
            if key in self.loc_const:
                return "TRUE" if _cmp_const(self.loc_const[key], g[2], g[3]) else "FALSE"
            return self._permissive()
        if isinstance(g, tuple) and g and g[0] == "POS":
            return self._posexpr(g)
        if isinstance(g, GAnd):
            ks = [self._gx(k, script) for k in g.kids]
            if "FALSE" in ks:
                return "FALSE"
            ks = [k for k in ks if k not in ("TRUE", "OPAQUE")]   # opaques projected out of AND
            return "(" + " & ".join(ks) + ")" if ks else "TRUE"
        if isinstance(g, GOr):
            ks = [self._gx(k, script) for k in g.kids]
            if "TRUE" in ks or "OPAQUE" in ks:   # an opaque disjunct is satisfiable -> TRUE
                return "TRUE"
            ks = [k for k in ks if k != "FALSE"]
            return "(" + " | ".join(ks) + ")" if ks else "FALSE"
        if isinstance(g, GNot):
            k = g.kid
            # push negation to leaves (NNF/De Morgan) so an opaque literal stays a leaf and its
            # OPAQUE sentinel is projected out correctly (¬opaque is also freely satisfiable).
            if isinstance(k, GAnd):
                return self._gx(GOr([GNot(x) for x in k.kids]), script)
            if isinstance(k, GOr):
                return self._gx(GAnd([GNot(x) for x in k.kids]), script)
            if isinstance(k, GNot):
                return self._gx(k.kid, script)
            inner = self._gx(k, script)
            if inner == "OPAQUE":
                return "OPAQUE"
            if inner == "TRUE":
                return "FALSE"
            if inner == "FALSE":
                return "TRUE"
            return f"!({inner})"
        if isinstance(g, Pred):
            if g.kind == "OWN":
                return f"item{g.var}"
            if g.kind == "CMP":
                v = _int(g.value)
                if v is None:
                    return self._permissive()
                if g.var in self.reg_dom:
                    op = "=" if g.op == "==" else g.op
                    return f"{self._gv(g.var)} {op} {v}"
                if g.var in self.reg_const:
                    return "TRUE" if _cmp_const(self.reg_const[g.var], g.op, v) else "FALSE"
            return self._permissive()
        return "TRUE"

    def _gv(self, gi):
        return f"g_{gi}"

    def _lv(self, key):
        return f"c_{key[0]}_{key[1]}_{key[2]}"

    def _inc(self, key):
        lo, hi = self.loc_dom[key]
        lv = self._lv(key)
        return f"({lv} >= {hi} ? {hi} : {lv} + 1)"    # saturate at hi (no SMV overflow)

    def _dec(self, key):
        lo, hi = self.loc_dom[key]
        lv = self._lv(key)
        return f"({lv} <= {lo} ? {lo} : {lv} - 1)"

    def _ms(self, info):
        safe = "".join(ch if ch.isalnum() else "_" for ch in info["inst"])
        return f"ms_{info['room']}_{safe}"

    # ---- emit --------------------------------------------------------
    def emit(self):
        from collections import defaultdict
        nxt = defaultdict(list)          # var -> [(cond, value)]
        room_change = []                 # (aid, src_cond, target_room) for init-write bundling
        aid = 0

        def cond(base, guard):
            return base + (" & " + guard if guard not in ("TRUE", "") else "")

        # flat movement edges. gexpr with the SOURCE room's script so a CTR-local guard on
        # the edge resolves (the room's own locals -- e.g. the disguise henchStatus gate).
        for e in self.ts.edges:
            g = self.gexpr(e.guard, e.src)
            if g == "FALSE":
                continue
            c = cond(f"action = {aid} & room = {e.src}", g)
            nxt["room"].append((c, str(e.dst)))
            room_change.append((c, e.dst))
            aid += 1
        # control_exits fallback: changeState exits the machine can't deliver, as GATED
        # flat edges (keeps the gate, e.g. rm65->70 gCurrentStatus!=12, without a bypass).
        for e in self.ts.cs_edges:
            if (e.src, e.dst) in self.machine_delivered:
                continue
            g = self.gexpr(e.guard, e.src)
            if g == "FALSE":
                continue
            c = cond(f"action = {aid} & room = {e.src}", g)
            nxt["room"].append((c, str(e.dst)))
            room_change.append((c, e.dst))
            aid += 1
        # flat item acquisitions
        for a in self.ts.acqs:
            g = self.gexpr(a.guard, None)
            if g == "FALSE":
                continue
            nxt[f"item{a.item}"].append((cond(f"action = {aid} & room = {a.room}", g), "TRUE"))
            aid += 1
        # machine steps + entries
        for info in self.machines:
            ms = self._ms(info)
            R = info["room"]
            for K, paths in info["states"].items():
                for (guard, writes, gets, counters, trans) in paths:
                    ext = [a for a in guard]
                    g = self._conj_expr(ext, info["script"])
                    if g == "FALSE":
                        continue
                    base = cond(f"action = {aid} & room = {R} & {ms} = {K}", g)
                    tk = trans[0]
                    if tk == "EXIT":
                        nxt["room"].append((base, str(trans[1])))
                        room_change.append((base, trans[1]))
                    elif tk == "DEATH":
                        nxt["dead"].append((base, "TRUE"))
                    elif tk == "ADVANCE":
                        nxt[ms].append((base, str(K + 1)))
                    elif tk == "JUMP":
                        nxt[ms].append((base, str(trans[1])))
                    elif tk == "SETSTATE":
                        nxt[ms].append((base, str(trans[1] + 1)))
                    for gi, v in writes:
                        if gi in self.reg_dom:
                            nxt[self._gv(gi)].append((base, str(v)))
                    for it in gets:
                        nxt[f"item{it}"].append((base, "TRUE"))
                    for name, kind, val in counters:
                        key = (info["script"],) + name
                        if key in self.loc_dom:
                            lv = self._lv(key)
                            if kind == "inc":
                                nxt[lv].append((base, self._inc(key)))
                            elif kind == "dec":
                                nxt[lv].append((base, self._dec(key)))
                            elif kind == "set" and val is not None:
                                nxt[lv].append((base, str(val)))
                    aid += 1
            for K, eg in info["entries"]:
                g = self.gexpr(eg, info["script"])
                if g == "FALSE":
                    continue
                nxt[ms].append((cond(f"action = {aid} & room = {R}", g), str(K)))
                aid += 1
            # ABSENT MID-SEQUENCE states fall through (advance to K+1) -- a genuine gap
            # between defined states (rm28Script: states 0,1,2,3,5 -- 4 absent; without this
            # s5 is unreachable). But NOT the START state: an absent start (reset target) is
            # left ONLY via the machine's gated ENTRIES (changeState or setScript). Falling
            # through it (0->1 free) was a BYPASS that skipped the entry gate -- rm63 jumped
            # the plane without opening the door (needs the Bobby_Pin), so items looked "not
            # required". Now safe to remove: setScript capture gave every machine real entries.
            allst = set(info["states"])
            if allst:
                for K in range(min(allst | {info["start"]}), max(allst) + 1):
                    if K not in allst and K != info["start"]:
                        nxt[ms].append((f"action = {aid} & room = {R} & {ms} = {K}", str(K + 1)))
                        aid += 1

        # player-action effects (handleEvent/doit register writes + item gets). gexpr with
        # the effect's own SCRIPT so a CTR-local guard (e.g. henchStatus==0) resolves.
        for room, script, gi, v, g in self.handler_writes:
            if gi not in self.reg_dom:
                continue
            ge = self.gexpr(g, script)
            if ge == "FALSE":
                continue
            nxt[self._gv(gi)].append((cond(f"action = {aid} & room = {room}", ge), str(v)))
            aid += 1
        for room, script, it, g in self.handler_gets:
            ge = self.gexpr(g, script)
            if ge == "FALSE":
                continue
            nxt[f"item{it}"].append((cond(f"action = {aid} & room = {room}", ge), "TRUE"))
            aid += 1
        for room, script, name, v, g in self.handler_locals:
            key = (script,) + name
            if key not in self.loc_dom:
                continue
            ge = self.gexpr(g, script)
            if ge == "FALSE":
                continue
            lv = self._lv(key)
            if v == ("inc",):
                val = self._inc(key)
            elif v == ("dec",):
                val = self._dec(key)
            elif isinstance(v, int):
                lo, hi = self.loc_dom[key]
                if not (lo <= v <= hi):
                    continue
                val = str(v)
            else:
                continue
            nxt[lv].append((cond(f"action = {aid} & room = {room}", ge), val))
            aid += 1

        # init writes bundled onto every room-changing action, WITH their entry guards.
        # Source order + insert(0) => the last source write to a register sits FIRST (highest
        # priority); first-match-wins then reproduces "later assignment wins where its guard
        # holds" (rm79: g101:=11 if gIslandStatus==2, else the unconditional NormalEgo g101:=0).
        machines_by_room = defaultdict(list)
        for info in self.machines:
            machines_by_room[info["room"]].append(info)
        self._ms_arrival = defaultdict(list)     # ms -> [(arrival_cond, entry_state)]
        for c, target in room_change:
            for gi, v, g in self.init_seq.get(target, []):
                if gi not in self.reg_dom:
                    continue
                ge = self.gexpr(g, None)
                if ge == "FALSE":
                    continue
                cc = c if ge == "TRUE" else f"({c}) & {ge}"
                nxt[self._gv(gi)].insert(0, (cc, str(v)))
            # INIT-sourced machine entries run atomically with init -> fire on ARRIVAL,
            # entry guard evaluated on the PRE-entry (source-room) state (same state the init
            # writes above read). Emitted ahead of the ms reset-to-start (see _emit_ms_next).
            for info in machines_by_room.get(target, ()):
                ms = self._ms(info)
                for K, eg in info.get("init_entries", ()):
                    ge = self.gexpr(eg, info["script"])
                    if ge == "FALSE":
                        continue
                    cc = c if ge == "TRUE" else f"({c}) & {ge}"
                    self._ms_arrival[ms].append((cc, str(K)))

        n_act = max(1, aid)
        return self._render(nxt, n_act)

    def _conj_expr(self, atoms, script):
        parts = [self.gexpr(a, script) for a in atoms]
        if "FALSE" in parts:
            return "FALSE"
        parts = [p for p in parts if p != "TRUE"]
        return "(" + " & ".join(parts) + ")" if parts else "TRUE"

    def _render(self, nxt, n_act):
        L = ["MODULE main", "IVAR", f"  action : 0 .. {n_act - 1};"]
        L.append("  posx : 0 .. 319;")   # ego's free-but-consistent position (a player choice)
        L.append("  posy : 0 .. 189;")
        for k in range(self.n_opaque):
            L.append(f"  opq{k} : boolean;")
        L.append("VAR")
        L.append("  room : {" + ", ".join(str(r) for r in self.rooms) + "};")
        L.append("  dead : boolean;")
        for it in self.items:
            L.append(f"  item{it} : boolean;")
        for gi, (lo, hi) in self.reg_dom.items():
            L.append(f"  {self._gv(gi)} : {lo} .. {hi};")
        for key, (lo, hi) in self.loc_dom.items():
            L.append(f"  {self._lv(key)} : {lo} .. {hi};")
        for info in self.machines:
            ms = self._ms(info)
            cand = list(info["states"]) + [info["start"]]
            # Include every state value this machine can actually be ASSIGNED (an ADVANCE off
            # the top state -> K_max+1, or a JUMP/SETSTATE target), so nuXmv never silently
            # DROPS an out-of-range next() write. Such a target has no handler, so it is an
            # absorbing no-op state -- faithful, and it removes the "cannot assign value"
            # warnings that otherwise mask a dropped assignment.
            for c, v in nxt.get(ms, []) + getattr(self, "_ms_arrival", {}).get(ms, []):
                if isinstance(v, str) and v.lstrip("-").isdigit():
                    cand.append(int(v))
            lo, hi = min(cand), max(cand)
            if hi == lo:                # a single-state machine gives 0..0, which nuXmv rejects;
                hi = lo + 1             # widen to a valid 2-value range (extra value unreachable)
            L.append(f"  {ms} : {lo} .. {hi};")

        L.append("ASSIGN")
        start = self.cfg.start_room
        L.append(f"  init(room) := {start};")
        L.append("  init(dead) := FALSE;")
        for it in self.items:
            L.append(f"  init(item{it}) := FALSE;")
        for gi, (lo, hi) in self.reg_dom.items():
            iv = self.init_writes.get(start, {}).get(gi)
            iv = iv if (iv is not None and lo <= iv <= hi) else self._reg_init(gi, lo, hi)
            L.append(f"  init({self._gv(gi)}) := {iv};")
        for key, (lo, hi) in self.loc_dom.items():
            L.append(f"  init({self._lv(key)}) := {0 if lo <= 0 <= hi else lo};")
        for info in self.machines:
            L.append(f"  init({self._ms(info)}) := {info['start']};")

        # next() for each variable
        self._emit_next(L, "room", nxt, "room")
        self._emit_next(L, "dead", nxt, "dead", latch=True)
        for it in self.items:
            self._emit_next(L, f"item{it}", nxt, f"item{it}", latch=True)
        for gi in self.reg_dom:
            self._emit_next(L, self._gv(gi), nxt, self._gv(gi))
        for key in self.loc_dom:
            self._emit_counter_next(L, key, nxt)
        for info in self.machines:
            self._emit_ms_next(L, info, nxt)

        goals = " | ".join(f"room = {r}" for r in sorted(self.cfg.goal_rooms))
        L.append(f"INVARSPEC !(({goals}) & !dead);")
        return "\n".join(L) + "\n", n_act

    def _reg_init(self, gi, lo, hi):
        for iv0 in self.ir.script(0).locals:
            if iv0["index"] == gi:
                v = iv0["value"]
                return v if lo <= v <= hi else lo
        return 0 if lo <= 0 <= hi else lo

    def _emit_next(self, L, var, nxt, key, latch=False):
        cases = nxt.get(key, [])
        if not cases:
            return
        L.append(f"  next({var}) := case")
        for c, v in cases:
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {var};")
        L.append("  esac;")

    def _emit_counter_next(self, L, key, nxt):
        lv = self._lv(key)
        script = key[0]
        rooms = [info["room"] for info in self.machines if info["script"] == script]
        L.append(f"  next({lv}) := case")
        if rooms:  # reset to 0 when not in the owning room(s)
            away = " & ".join(f"room != {r}" for r in sorted(set(rooms)))
            L.append(f"    {away} : 0;")
        for c, v in nxt.get(lv, []):
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {lv};")
        L.append("  esac;")

    def _emit_ms_next(self, L, info, nxt):
        ms = self._ms(info)
        R = info["room"]
        L.append(f"  next({ms}) := case")
        # INIT entries fire on arrival (room is still the source here, != R) and must win over
        # the reset-to-start below, so they come FIRST.
        for c, v in getattr(self, "_ms_arrival", {}).get(ms, []):
            L.append(f"    {c} : {v};")
        L.append(f"    room != {R} : {info['start']};")   # reset/park to start when away
        for c, v in nxt.get(ms, []):
            L.append(f"    {c} : {v};")
        L.append(f"    TRUE : {ms};")
        L.append("  esac;")


def _find_nuxmv():
    for c in (os.environ.get("NUXMV"),
              os.path.join(os.environ.get("CLAUDE_JOB_DIR", ""), "tmp",
                           "nuXmv-2.0.0-Linux", "bin", "nuXmv")):
        if c and os.path.exists(c):
            return c
    raise FileNotFoundError("nuXmv not found")


def winnable(em, pin_items_off=(), timeout=900):
    smv, _ = em.emit()
    for it in pin_items_off:
        # force item permanently FALSE: replace its next-block with a constant
        lines = smv.splitlines()
        out, i = [], 0
        while i < len(lines):
            if lines[i].strip() == f"next(item{it}) := case":
                out.append(f"  next(item{it}) := FALSE;")
                i += 1
                while i < len(lines) and lines[i].strip() != "esac;":
                    i += 1
                i += 1
                continue
            out.append(lines[i]); i += 1
        smv = "\n".join(out) + "\n"
    tmp = os.path.join(os.environ.get("CLAUDE_JOB_DIR", "/tmp"), "tmp", "op.smv")
    with open(tmp, "w") as f:
        f.write(smv)
    cmds = f"read_model -i {tmp}\ngo_msat\ncheck_invar_ic3\nquit\n"
    p = subprocess.run([_find_nuxmv(), "-int"], input=cmds, capture_output=True,
                       text=True, timeout=timeout)
    out = p.stdout + p.stderr
    for line in out.splitlines():
        low = line.lower()
        if "is false" in low:
            return True
        if "is true" in low:
            return False
    raise RuntimeError("no verdict:\n" + out[-2000:])
