"""Is the ENGINE running our patch? -- the check that was missing for GK1 until 2026-11-14.

    PATCH_DIR=build/gk1_patch_v4/patch .venv-x/bin/python tools/sci_console.py \
        --game ~/sierra/patched/gk1 --id gk1 --binary <text-console scummvm> \
        --script tools/probes/patch_is_live.py

For every script/heap file in PATCH_DIR, ask the running interpreter for that resource's hash
(`resource_info`) and compare it with the file we built. "It compiles", "the files are in the
folder" and "every script instantiates" all passed for two months while ScummVM ran Sierra's
own PATCHES/ copies instead of ours; only this comparison can tell the difference.

STATE ONLY -- every command here is a query.
"""
import hashlib
import os
import re

patch_dir = os.environ["PATCH_DIR"]
c.resume(seconds=4)                                                       # noqa: F821 -- injected
ok, n = True, 0
for fn in sorted(os.listdir(patch_dir)):
    m = re.match(r"^(\d+)\.(SCR|HEP)$", fn, re.I)
    if not m:
        continue
    typ = "script" if m.group(2).upper() == "SCR" else "heap"
    want = hashlib.md5(open(os.path.join(patch_dir, fn), "rb").read()[2:]).hexdigest()
    out = c.cmd("resource_info %s %s" % (typ, m.group(1))) or ""          # noqa: F821
    got = (re.search(r"hash \(decompressed\): ([0-9a-f]+)", out) or [None, "?"])[1]
    n += 1
    ok &= (got == want)
    print("  %-9s %s -- %s" % (fn, got[:12], "ours" if got == want
                               else "NOT OURS (built %s)" % want[:12]))
print("VERDICT: %s" % ("the engine is running all %d of our files" % n if ok and n
                       else "the engine is NOT running our patch"))
