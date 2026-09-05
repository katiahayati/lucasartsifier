"""CENSUS before building (GK1 §1.59): how many locals in the corpus are assigned by a
SWITCH/COND tree whose leaves are all integer literals -- the shape `drumInset`'s `local0` has,
which is where flag 268's day-6 gate lives."""
import sys, collections
sys.path.insert(0, "/home/hayati/coding/sierra_softlock/src")
import config
import ir as I
import missability as M

def leaves(node):
    """(ok, [values]) for a switch/cond tree whose every arm yields one integer literal."""
    t = node.get("t") if isinstance(node, dict) else None
    if t == "Number":
        return True, [node["value"]]
    if t == "List":
        ks = [k for k in (node.get("kids") or []) if isinstance(k, dict)]
        if len(ks) != 1:
            return False, []
        return leaves(ks[0])
    if t == "If":
        ks = [k for k in (node.get("kids") or []) if isinstance(k, dict)]
        if len(ks) < 3:
            return False, []
        g1, v1 = leaves(ks[1])
        g2, v2 = leaves(ks[2])
        return (g1 and g2), (v1 + v2)
    if t in ("Switch", "Cond"):
        out, ok = [], False
        for c in (node.get("kids") or [])[1:] if t == "Switch" else (node.get("kids") or []):
            if not isinstance(c, dict) or c.get("t") not in ("Case", "CondArm", "Else"):
                continue
            ks = [k for k in (c.get("kids") or []) if isinstance(k, dict)]
            if not ks:
                return False, []
            g, vals = leaves(ks[-1])
            if not g:
                return False, []
            out += vals
            ok = True
        return ok, out
    return False, []

def subjects(node, acc):
    if not isinstance(node, dict):
        return
    if node.get("t") in ("Switch", "Cond"):
        ks = node.get("kids") or []
        if ks and isinstance(ks[0], dict) and ks[0].get("t") == "Variable" \
                and ks[0].get("vtype") == "Global":
            acc.add(ks[0]["index"])
    for k in (node.get("kids") or []):
        subjects(k, acc)

for name in ("LSL2", "KQ4", "kq6", "kq5", "dagger", "gk1"):
    cfg = config.by_name(name)
    s = M.load(cfg=cfg)
    ir = s.em.ir
    rooms = set(getattr(s.em, "rooms", ()) or [])
    hits, in_rooms, with_glob = [], 0, 0
    for sn, sc in sorted(ir.scripts.items()):
        if not getattr(sc, "locals", None):
            continue
        bodies = [(o.name, mn, b) for o in sc.objects for mn, b in o.methods.items()]
        bodies += [("proc", pn, b) for pn, b in (getattr(sc, "procs", None) or {}).items()]
        for (on, mn, body) in bodies:
            for n in I.walk(body):
                if not isinstance(n, dict) or n.get("t") != "Assignment":
                    continue
                ks = n.get("kids") or []
                if len(ks) < 2 or not isinstance(ks[0], dict):
                    continue
                if ks[0].get("t") != "Variable" or ks[0].get("vtype") != "Local":
                    continue
                ok, vals = leaves(ks[1])
                if not ok or len(vals) < 2:
                    continue
                subj = set(); subjects(ks[1], subj)
                hits.append((sn, ks[0]["index"], on, mn, sorted(set(vals)), sorted(subj)))
                if sn in rooms:
                    in_rooms += 1
                if subj:
                    with_glob += 1
    print(f"\n=== {name}: {len(hits)} switch-valued local assignment(s); "
          f"{in_rooms} in ROOM scripts, {with_glob} switching on a GLOBAL")
    for h in hits[:12]:
        print(f"    script {h[0]} local{h[1]} in {h[2]}::{h[3]} -> values {h[4]} "
              f"on globals {h[5]}")
    if len(hits) > 12:
        print(f"    ... and {len(hits) - 12} more")
