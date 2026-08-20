"""The built-model cache: a cache hit must be indistinguishable from a fresh build.

WHY THIS FILE EXISTS (2026-08-06). `missability.load` rebuilds the whole model on every call
-- measured LSL2 27s, KQ4 78s, KQ6 171s -- and the suite asks for the same three models 26
times across six processes, which was ~96% of a 39-minute run. Caching the model cut that to
14.5 minutes.

THE HAZARD THE CACHE INTRODUCES, and the only one worth a test file: a build does not just
return a model, it INSTALLS module-level state that queries read later (`extract`'s derived
vocabulary, `missability._IPROP_SPEC`, `vocab.BOOL_GLOBALS`). Hand back a cached model without
that state and the model answers against whichever game was loaded last. The first cut missed
`_IPROP_SPEC` and four KQ4 resource-exhaustion checks in `test_scopes` went empty -- caught by
the suite, which is the right net but a 14-minute one. This file catches it in ~30 seconds by
diffing the state a cache hit restores against the state a fresh build installs.

The second hazard is aliasing: `guards.apply_guards` mutates the model IN PLACE to build the
guarded world it verifies against, so every caller must get its own copy.
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config                                                            # noqa: E402
import missability as M                                                  # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           "" if cond else ("  -- " + detail)))


def _fingerprint(state):
    """A comparable summary of the installed module state (the objects themselves are big and
    not all equality-comparable; their shape is what has to match)."""
    mods, bools = state
    out = {}
    for mod, names in sorted(mods.items()):
        for k, v in sorted(names.items()):
            if isinstance(v, dict):
                out["%s.%s" % (mod, k)] = ("dict", len(v), sorted(map(repr, list(v)[:20])))
            elif isinstance(v, (set, frozenset)):
                out["%s.%s" % (mod, k)] = ("set", len(v), sorted(map(repr, v))[:20])
            elif hasattr(v, "__dict__") or hasattr(v, "__slots__"):
                # a rebuilt object is a different instance with the same content, so compare
                # its shape rather than its repr (which carries the address)
                attrs = sorted(vars(v)) if hasattr(v, "__dict__") else sorted(v.__slots__)
                out["%s.%s" % (mod, k)] = ("obj", type(v).__name__, attrs)
            else:
                out["%s.%s" % (mod, k)] = ("val", repr(v)[:200])
    out["vocab.BOOL_GLOBALS"] = ("set", len(bools), sorted(bools)[:20])
    return out


def run():
    if not os.path.exists(config.LSL2.ir_path):
        print("  (skip: no LSL2 IR)")
        return True
    print("\n-- a cache hit installs the same state a fresh build does --")
    # fresh build, cache bypassed entirely
    fresh = M.load(cfg=config.LSL2, cache=False)
    fresh_state = _fingerprint(M._vocab_state())
    fresh_verdicts = sorted({c["item"] for c in fresh.analyze()})

    # now poison the module state the way a second game would, then take a cache hit
    M._restore_vocab_state(({mod: {k: None for k in names} for mod, names in M._BUILD_STATE},
                            {999999}))
    cached = M.load(cfg=config.LSL2)
    cached_state = _fingerprint(M._vocab_state())

    missing = [k for k in fresh_state if fresh_state[k] != cached_state.get(k)]
    check("the cache restores every module global a build installs", not missing,
          "differs: %s" % missing)
    check("_IPROP_SPEC specifically is restored (the one the first cut missed)",
          fresh_state.get("missability._IPROP_SPEC") ==
          cached_state.get("missability._IPROP_SPEC"),
          repr(cached_state.get("missability._IPROP_SPEC"))[:200])
    check("verdicts from a cache hit match the fresh build",
          sorted({c["item"] for c in cached.analyze()}) == fresh_verdicts)

    print("\n-- every caller gets its own copy --")
    a = M.load(cfg=config.LSL2)
    b = M.load(cfg=config.LSL2)
    check("two loads are distinct objects", a is not b)
    import guards as G
    G.apply_guards(a, G.guard_specs(a))            # the real in-place mutation
    c = M.load(cfg=config.LSL2)
    check("a mutated copy does not leak into the next load", c._pstates is not a._pstates)
    check("the next load still answers like a fresh build",
          sorted({x["item"] for x in c.analyze()}) == fresh_verdicts)

    print("\n-- the key covers the things that invalidate a model --")
    k1 = M._model_cache_key(config.LSL2, config.LSL2.ir_path)
    import dataclasses
    k2 = M._model_cache_key(dataclasses.replace(config.LSL2, start_room=99),
                            config.LSL2.ir_path)
    check("a different config is a different key", k1 != k2)
    check("the key is stable for the same inputs",
          k1 == M._model_cache_key(config.LSL2, config.LSL2.ir_path))
    # ⛔ THIS ASSERTED NOTHING (2026-08-20 third review). It read the module's bytes and then
    # checked `len(src) > 0 and k1 is not None` -- true of any key, from any inputs, whatever
    # the hash covered. The claim is that a source change MISSES the cache, so make one: a new
    # non-test module in this directory must move the key, and taking it away must put the key
    # back (which also proves the hash is content-derived and not, say, a directory mtime).
    # ⛔ AND IT IS MEASURED ON A COPY (2026-08-20 fourth review, P7). Proving it by writing
    # `_cache_probe_tmp.py` into the LIVE `src/` changes every game's cache key for as long as
    # the file is there -- any model loaded in that window is keyed to a source tree that is
    # about to stop existing -- and a process killed between the write and the cleanup leaves a
    # stray module behind that silently invalidates every cached model from then on. The test
    # may not edit the tree it is testing. `_model_cache_key` takes `here` so the same question
    # can be asked of a copy.
    src_here = os.path.dirname(os.path.abspath(M.__file__))
    before = sorted(os.listdir(src_here))
    tmp = tempfile.mkdtemp(prefix="cache_key_probe_")
    try:
        for fn in os.listdir(src_here):
            if fn.endswith(".py"):
                shutil.copy(os.path.join(src_here, fn), os.path.join(tmp, fn))
        k_copy = M._model_cache_key(config.LSL2, config.LSL2.ir_path, here=tmp)
        with open(os.path.join(tmp, "_cache_probe_tmp.py"), "w") as f:
            f.write("# a source file this directory did not have a moment ago\n")
        k3 = M._model_cache_key(config.LSL2, config.LSL2.ir_path, here=tmp)
        os.remove(os.path.join(tmp, "_cache_probe_tmp.py"))
        k4 = M._model_cache_key(config.LSL2, config.LSL2.ir_path, here=tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    check("the key covers this directory's source (edit -> miss -> rebuild)",
          k1 is not None and k3 != k1 and k4 == k1,
          "adding a non-test .py must change the key (%r -> %r) and removing it must restore "
          "it (%r). A cached model is only sound while every module that builds or queries it "
          "is byte-identical to the one that produced the pickle." % (k1, k3, k4))
    check("...and the hash is CONTENT-derived, so a byte-identical copy keys the same",
          k_copy == k1,
          "a copy of src/ elsewhere on disk gave %r against the live tree's %r. If these differ "
          "the hash has picked up a path or an mtime, and the check above would be measuring "
          "the copy rather than the rule." % (k_copy, k1))
    check("...and the live src/ was not touched to find that out",
          sorted(os.listdir(src_here)) == before,
          "src/ gained or lost %r" % (set(os.listdir(src_here)) ^ set(before),))
    return not FAIL


if __name__ == "__main__":
    ok = run()
    print("\n%d passed, %d failed" % (len(PASS), len(FAIL)))
    sys.exit(0 if ok else 1)
