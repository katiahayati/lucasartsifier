"""Sanity check: parse every decompiled .sc and report failures + structure stats."""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from sexpr import read_file, Sym, Str, Said, SexprError  # noqa: E402

SRC = os.path.join(os.path.dirname(__file__), "..",
                   "vendor/sci-scripts/lsl2-dos-1.002.000/src")


def top_heads(forms):
    heads = []
    for f in forms:
        if isinstance(f, list) and f and isinstance(f[0], Sym):
            heads.append(f[0].name)
    return heads


def main():
    files = sorted(glob.glob(os.path.join(SRC, "*.sc")))
    ok = 0
    fails = []
    head_counts = {}
    for path in files:
        try:
            forms = read_file(path)
            ok += 1
            for h in top_heads(forms):
                head_counts[h] = head_counts.get(h, 0) + 1
        except SexprError as e:
            fails.append((os.path.basename(path), str(e)))
        except Exception as e:  # noqa: BLE001
            fails.append((os.path.basename(path), f"{type(e).__name__}: {e}"))

    print(f"parsed OK: {ok}/{len(files)}")
    if fails:
        print("FAILURES:")
        for name, msg in fails:
            print(f"  {name}: {msg}")
    print("\ntop-level form heads (across all files):")
    for h, c in sorted(head_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {c:4d}  {h}")
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
