"""Install a built patch into a playable COPY of a game, and prove each file landed.

    python3 tools/install_patch.py <game> <patch dir> [<game copy>]

`<game copy>` defaults to ~/sierra/patched/<game>. Every file goes over the copy's own loose
version of that resource wherever it lives -- the game folder or its `patches` directory -- so
it is the one the interpreter reads (`patcher.install_patches`). The stock game is never written.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

import config                                                            # noqa: E402
import patcher as P                                                      # noqa: E402

game, patch_dir = sys.argv[1], sys.argv[2]
cfg = config.by_name(game)
dest = sys.argv[3] if len(sys.argv) > 3 else os.path.expanduser("~/sierra/patched/%s" % cfg.name)
rows = P.install_patches(patch_dir, dest, stock_dir=cfg.resource_dir)
for r in rows:
    print("[%s] %s -> %s" % ("ok" if r["ok"] else "MISMATCH", r["file"], r["dest"]))
bad = [r for r in rows if not r["ok"]]
print("%d file(s) installed into %s, %d mismatch(es)" % (len(rows), dest, len(bad)))
sys.exit(1 if bad or not rows else 0)
