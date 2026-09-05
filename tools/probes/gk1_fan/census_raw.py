"""Census on the RAW ir -- before the lowering rewrites the Local nodes away."""
import sys
sys.path.insert(0, "/home/hayati/coding/sierra_softlock/src")
import config, vocab as V
import ir as I
for name in ("LSL2", "KQ4", "kq6", "kq5", "dagger", "gk1"):
    cfg = config.by_name(name)
    ir = I.load_ir(cfg.ir_path)
    keys = sorted(V.derive_switch_locals(ir))
    print(f"{name}: {len(keys)} -> {keys}")
