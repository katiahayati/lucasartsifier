"""BDD engine spike -- does symbolic reachability handle the LSL2 n=40 SHAPE?

DELIBERATELY synthetic. We generate a transition system with the same shape as LSL2
all-40 (89 rooms, 32 items, 40 registers with the measured domains, ~173 edges, ~737
register writes, tunable coupling) and run BDD reachability on it. Because the model is
generated NATIVELY (no translation of any real game), there is no game-encoding to get
wrong -- this measures the BDD engine's CAPABILITY at this scale, nothing else.

Trust: the BDD reachability code is validated against an explicit BFS on SMALL instances
(where the full state space is enumerable). If BDD == BFS there, the reachability code is
correct; the full-scale numbers then measure only performance.

Reachability uses per-action in-place image (no primed vars, no monolithic transition
relation): each action reassigns only the few bits it touches.
"""
import itertools
import math
import random
import time

from dd.cudd import BDD

# ---- LSL2 n=40 shape (measured) ------------------------------------------
# register VALUE counts = domain+1 (the tested values plus the NOTTRACKED bucket)
LSL2_REG_VALUES = ([24, 9, 8, 7, 7, 6, 4, 4, 4] + [3] * 6 + [2] * 25)  # 40 registers
LSL2_SHAPE = dict(nrooms=89, nitems=32, reg_values=LSL2_REG_VALUES,
                  nedges=173, nwrites=737)


def bits_for(n):
    return max(1, math.ceil(math.log2(n)))


class Model:
    """A synthetic transition system: rooms, latching items, multi-valued registers,
    gated movement edges, gated register writes, gated item pickups. Generated with a
    seed so it is reproducible and so a BFS oracle can be built for small instances."""
    def __init__(self, nrooms, nitems, reg_values, nedges, nwrites,
                 gate_frac, seed=0):
        rnd = random.Random(seed)
        self.nrooms = nrooms
        self.nitems = nitems
        self.reg_values = list(reg_values)   # reg -> #distinct values
        self.start = 0
        self.goal = nrooms - 1

        def rand_guard():
            # a small conjunction of atoms, present with prob gate_frac
            atoms = []
            if rnd.random() < gate_frac:
                for _ in range(rnd.randint(1, 2)):
                    if self.reg_values and rnd.random() < 0.6:
                        r = rnd.randrange(len(self.reg_values))
                        atoms.append(("reg", r, rnd.randrange(self.reg_values[r])))
                    elif nitems:
                        atoms.append(("item", rnd.randrange(nitems)))
            return atoms

        # movement edges -- an ungated random TREE rooted at 0 (every room reachable,
        # LOW diameter ~log n, unlike a linear spine), then random extra gated edges.
        self.edges = []            # (a, b, guard)
        for i in range(1, nrooms):
            self.edges.append((rnd.randrange(i), i, []))     # parent < i: reaches all, shallow
        for _ in range(max(0, nedges - (nrooms - 1))):
            a, b = rnd.randrange(nrooms), rnd.randrange(nrooms)
            self.edges.append((a, b, rand_guard()))

        # register writes: (room, reg, value, guard)
        self.writes = []
        for _ in range(nwrites):
            r = rnd.randrange(len(self.reg_values)) if self.reg_values else 0
            self.writes.append((rnd.randrange(nrooms), r,
                                rnd.randrange(self.reg_values[r]) if self.reg_values else 0,
                                rand_guard()))

        # item pickups: (room, item, guard)
        self.pickups = []
        for it in range(nitems):
            self.pickups.append((rnd.randrange(nrooms), it, rand_guard()))


# ---- explicit BFS oracle (small instances only) --------------------------
def explicit_reach(m):
    """Ground truth by enumeration. Only call on SMALL models (state space tiny)."""
    init = (m.start, tuple([0] * len(m.reg_values)), 0)  # (room, reg-vals, item-bitmask)
    seen = {init}
    frontier = [init]

    def guard_ok(guard, regs, items):
        for atom in guard:
            if atom[0] == "reg" and regs[atom[1]] != atom[2]:
                return False
            if atom[0] == "item" and not (items >> atom[1]) & 1:
                return False
        return True

    while frontier:
        room, regs, items = frontier.pop()
        succ = []
        for a, b, g in m.edges:
            if a == room and guard_ok(g, regs, items):
                succ.append((b, regs, items))
        for rr, reg, val, g in m.writes:
            if rr == room and guard_ok(g, regs, items):
                nr = list(regs); nr[reg] = val
                succ.append((room, tuple(nr), items))
        for rr, it, g in m.pickups:
            if rr == room and guard_ok(g, regs, items):
                succ.append((room, regs, items | (1 << it)))
        for s in succ:
            if s not in seen:
                seen.add(s); frontier.append(s)
    rooms = {s[0] for s in seen}
    return rooms, (m.goal in rooms)


# ---- BDD symbolic reachability -------------------------------------------
class BddReach:
    """Symbolic reachability with a PARTITIONED transition relation: one relation per
    'group' (movement, each register, each item), each built ONCE. Per iteration we do
    ONE relational image per group (~1+40+32 groups), not one per action (~942). Uses
    primed variables for the group being updated."""
    def __init__(self, m):
        self.m = m
        self.bdd = BDD()
        self.room_bits = [f"room{i}" for i in range(bits_for(m.nrooms))]
        self.proom = [f"P{b}" for b in self.room_bits]
        self.item_bits = [f"item{i}" for i in range(m.nitems)]
        self.pitem = [f"P{b}" for b in self.item_bits]
        self.reg_bits = [[f"r{r}_{i}" for i in range(bits_for(m.reg_values[r]))]
                         for r in range(len(m.reg_values))]
        self.preg = [[f"P{b}" for b in bits] for bits in self.reg_bits]
        # INTERLEAVE current/primed bits (x0, x0', x1, x1', ...) -- the standard ordering
        # for transition relations; all-current-then-all-primed blows the relation BDD up.
        # Reordering OFF: dynamic reordering was thrashing the growing BDD.
        self.bdd.configure(reordering=False)
        pairs = list(zip(self.room_bits, self.proom)) + list(zip(self.item_bits, self.pitem))
        for cbits, pbits in zip(self.reg_bits, self.preg):
            pairs += list(zip(cbits, pbits))
        for c, p in pairs:
            self.bdd.declare(c, p)

    def _num(self, bits, value):
        u = self.bdd.true
        for i, b in enumerate(bits):
            lit = self.bdd.var(b)
            u &= lit if (value >> i) & 1 else ~lit
        return u

    def room_is(self, v, p=False):
        return self._num(self.proom if p else self.room_bits, v)

    def reg_is(self, r, v, p=False):
        return self._num(self.preg[r] if p else self.reg_bits[r], v)

    def item1(self, i, p=False):
        return self.bdd.var((self.pitem if p else self.item_bits)[i])

    def guard(self, g):
        u = self.bdd.true
        for atom in g:
            u &= self.reg_is(atom[1], atom[2]) if atom[0] == "reg" else self.item1(atom[1])
        return u

    def run(self):
        bdd = self.bdd
        m = self.m
        # Build one relation per group, ONCE. Each relates current state to the primed
        # copy of just that group's variables.
        T_move = bdd.false
        for a, b, g in m.edges:
            T_move |= self.room_is(a) & self.guard(g) & self.room_is(b, p=True)
        T_reg = []
        for r in range(len(m.reg_values)):
            t = bdd.false
            for rr, reg, val, g in m.writes:
                if reg == r:
                    t |= self.room_is(rr) & self.guard(g) & self.reg_is(r, val, p=True)
            T_reg.append(t)
        T_item = []
        for it in range(m.nitems):
            t = bdd.false
            for rr, i2, g in m.pickups:
                if i2 == it:
                    t |= self.room_is(rr) & self.guard(g) & self.item1(it, p=True)
            T_item.append(t)

        # image over a group: exist current group vars from (frontier & T), rename primed->current
        groups = ([(self.room_bits, self.proom, T_move)]
                  + [(self.reg_bits[r], self.preg[r], T_reg[r]) for r in range(len(m.reg_values))]
                  + [([self.item_bits[i]], [self.pitem[i]], T_item[i]) for i in range(m.nitems)])

        def image(frontier, cur, pri, T):
            img = bdd.exist(cur, frontier & T)
            return bdd.let(dict(zip(pri, cur)), img)

        init = self.room_is(m.start)
        for r in range(len(m.reg_values)):
            init &= self.reg_is(r, 0)
        for b in self.item_bits:
            init &= ~bdd.var(b)
        reached = frontier = init
        iters = 0
        while frontier != bdd.false:
            iters += 1
            new = bdd.false
            for cur, pri, T in groups:
                if T != bdd.false:
                    new |= image(frontier, cur, pri, T)
            frontier = new & ~reached
            reached |= frontier

        proj = bdd.exist(self.item_bits + sum(self.reg_bits, []), reached)
        rooms = {v for v in range(m.nrooms) if (proj & self.room_is(v)) != bdd.false}
        winnable = (reached & self.room_is(m.goal)) != bdd.false
        return rooms, winnable, iters, len(bdd)


def main():
    print("=== 1. VALIDATE BDD reachability against explicit BFS (small) ===")
    ok = True
    for seed in range(6):
        small = Model(nrooms=6, nitems=3, reg_values=[3, 2, 2],
                      nedges=10, nwrites=12, gate_frac=0.7, seed=seed)
        er, ew = explicit_reach(small)
        br, bw, _, _ = BddReach(small).run()
        match = (er == br and ew == bw)
        ok = ok and match
        print(f"   seed {seed}: BFS rooms={len(er)} win={ew} | BDD rooms={len(br)} "
              f"win={bw} | {'MATCH' if match else 'MISMATCH !!!'}")
    if not ok:
        print("   BDD reachability code is WRONG -- full-scale numbers meaningless. STOP.")
        return
    print("   -> BDD reachability validated correct.\n")

    print("=== 2. FULL LSL2-n40 SHAPE: BDD performance vs coupling ===")
    S = LSL2_SHAPE
    for gate_frac in (0.0, 0.5, 1.0):
        m = Model(S["nrooms"], S["nitems"], S["reg_values"],
                  S["nedges"], S["nwrites"], gate_frac=gate_frac, seed=1)
        t = time.time()
        rooms, win, iters, nodes = BddReach(m).run()
        dt = time.time() - t
        print(f"   gate_frac={gate_frac:.2f}: rooms={len(rooms)}/{S['nrooms']} win={win} "
              f"iters={iters} peakBDDnodes={nodes} time={dt:.2f}s", flush=True)


if __name__ == "__main__":
    main()
