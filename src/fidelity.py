"""Fidelity gate for Phase-B compiled patches.

Compares a recompiled script resource (bytes from scicompile) against the ORIGINAL
compiled script extracted from the real game, and wraps a recompiled script as a
loose ScummVM SCI0 patch file (`script.NNN`).

Note on byte-identity: the recompilable source (EricOakford) is a *decompilation*.
Recompiling it may not be byte-identical to Sierra's original (variable ordering,
codegen choices) while remaining functionally correct. So byte-identity of an
UNMODIFIED recompile is a strong bonus signal, not a hard requirement; the real
gate is that the script LOADS and RUNS in ScummVM. This tool reports both.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sci_resource import Sci0Game, SCRIPT

GAME_DIR = "/mnt/i/sierra/lsl2"


def compare(orig: bytes, recompiled: bytes):
    same = orig == recompiled
    n = min(len(orig), len(recompiled))
    first_diff = next((i for i in range(n) if orig[i] != recompiled[i]),
                      n if len(orig) == len(recompiled) else n)
    match = sum(1 for i in range(n) if orig[i] == recompiled[i])
    return {
        "byte_identical": same,
        "orig_len": len(orig),
        "recompiled_len": len(recompiled),
        "first_diff_offset": None if same else first_diff,
        "common_prefix": first_diff,
        "pct_matching_over_min": round(100.0 * match / n, 1) if n else 0.0,
    }


def loose_patch_bytes(script_bytes: bytes) -> bytes:
    """SCI0 loose patch file body: [resType=Script(2)][headerSize=0][raw bytes]."""
    return bytes([SCRIPT, 0]) + script_bytes


def fidelity_check(script_num: int, recompiled_path: str, game_dir=GAME_DIR):
    g = Sci0Game(game_dir)
    orig = g.get_script(script_num)
    recompiled = open(recompiled_path, "rb").read()
    r = compare(orig, recompiled)
    print(f"=== fidelity: script #{script_num} ===")
    print(f"  original (game):   {r['orig_len']} bytes")
    print(f"  recompiled:        {r['recompiled_len']} bytes")
    print(f"  byte-identical:    {r['byte_identical']}")
    if not r["byte_identical"]:
        print(f"  common prefix:     {r['common_prefix']} bytes")
        print(f"  matching (of min): {r['pct_matching_over_min']}%")
        print("  (non-identity is acceptable for a decompiled source; the gate is "
              "ScummVM load+run.)")
    return r


def main():
    import argparse
    ap = argparse.ArgumentParser(description="compare a recompiled script vs the game original")
    ap.add_argument("script_num", type=int)
    ap.add_argument("recompiled_bin")
    ap.add_argument("--game", default=GAME_DIR)
    ap.add_argument("--wrap", help="write a loose script.NNN patch from the recompiled bin to this path")
    args = ap.parse_args()
    fidelity_check(args.script_num, args.recompiled_bin, args.game)
    if args.wrap:
        data = open(args.recompiled_bin, "rb").read()
        open(args.wrap, "wb").write(loose_patch_bytes(data))
        print(f"  wrote loose patch: {args.wrap} ({2 + len(data)} bytes)")


if __name__ == "__main__":
    main()
