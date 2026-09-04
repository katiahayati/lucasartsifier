"""The closure arm tells one story once (2026-09-03, GK1 docs §1.49): rows of one crossing with one
sealed region that differ only in the register carried are the links of one chain, collapsed to
the root with the chain attached; independent roots stay separate rows. Synthetic, in memory."""
import sys

from missability import _collapse_value_chains

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f"\n         {detail}" if detail and not cond else ""))


def row(reg, sealed=frozenset({1, 2})):
    return {"pattern": "producible-dead-end", "register": 123, "value": 4, "reg": reg, "bad": [0],
            "accepted": [1], "demanded_at": [680], "via": "producible-closure", "raise_rooms": [],
            "flip_rooms": [370], "_sealed": sealed}


def main():
    print("=== test_value_chains: one story, told once ===")
    wb = {(240, 50, 1): [({42: {1}}, [], [])], (262, 50, 1): [({240: {1}}, [], [])],
          (263, 50, 1): [({262: {1}}, [], [])], (44, 50, 1): [({263: {1}}, [], [])],
          (42, 250, 1): [({42: {0}}, [], [])], (14, 330, 1): [({}, [], [])]}
    rows = [row(44), row(263), row(262), row(240), row(42), row(14)]
    out = _collapse_value_chains(rows, wb)
    check("six rows of one crossing collapse to the two roots", len(out) == 2, f"got {len(out)}")
    roots = {r["reg"]: r for r in out}
    check("the photo's flag 42 is a root, with the chain downstream in dependency order",
          42 in roots and roots[42].get("chain") == [42, 240, 262, 263, 44], f"got {roots.get(42, {}).get('chain')}")
    check("the Tulane icon's flag 14 is its own root (no link produces it, it produces none)",
          14 in roots and roots[14].get("chain") == [14], f"got {roots.get(14, {}).get('chain')}")
    check("the sealed region is kept for the second collapse", all("_sealed" in r for r in out))
    out2 = _collapse_value_chains([row(44), row(263, frozenset({9}))], wb)
    check("rows with different sealed regions do not merge", len(out2) == 2)
    other = {"pattern": "register-value-at-seal", "register": 5, "value": 1, "reg": 7, "bad": [0]}
    check("a non-closure row passes through", _collapse_value_chains([other], wb) == [other])
    print(f"\n  {len(PASS)} passed, {len(FAIL)} failed")
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
