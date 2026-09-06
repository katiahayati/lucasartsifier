"""The SCI2 back end: GK1's version is DERIVED, and the resource it produces would LOAD.

Two rules landed together on 2026-09-06 to give GK1 its first patch, and this file is what stops
either from rotting.

⭐ **THE VERSION IS DERIVED FROM THE VOLUME HEADER, NOT THE MAP.** GK1's resource map is
SCI1-shaped -- ScummVM says so itself ("Resource map version: Late SCI1") and SCICompanion's own
SCI2 map test (a section type byte below 0x80) does not fire on it. What separates GK1 from KQ6
is the VOLUME header: SCI32 widened the packed/unpacked sizes to 32 bits, so the header is 13
bytes where SCI1.1's is 9.

⛔ AND THE TYPE AND NUMBER DO NOT SEPARATE THEM. They sit at the same two offsets in both
layouts, so an SCI32 header read as SCI1.1 MATCHES -- GK1's script 0 came back with
`method = 5150` and the reader accepted it. The compression method is what refutes it: it is
drawn from a closed set. That is the rule this file pins, in both directions.

Why it matters, measured: with the version wrong the compiler cannot read GK1 at all --
"Failed to load selector names from vocab resource" (the SCI1.1 package reader cannot find the
bodies) and "Script number must be less than 16384: 64921" (SCI1.1's resource-number ceiling,
which GK1's 64xxx system scripts are above).

⭐ **AND A COMPILER'S EXIT CODE IS NOT A LOADABLE RESOURCE.** `tools/verify_sci_script.py`
transcribes ScummVM's own `Script::init` / `identifyOffsets` / `getRelocationTableSci0Sci21`
checks, so it fails where the engine refuses and nowhere else. A checker that accepts everything
is worth nothing, so the corruptions are pinned beside the clean pairs -- the same discipline
that caught the first draft of the live probe reading "Script N is currently not loaded" as a
pass ([[instruments-lie-run-the-control]]).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                "tools"))
import sci_resource as R                                              # noqa: E402
import verify_sci_script as V                                         # noqa: E402

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           ("  -- %s" % detail) if detail and not cond else ""))


def _game(p):
    p = os.path.expanduser(p)
    return R.Sci0Game(p) if os.path.isdir(p) else None


# One generation per row, and the resource directory comes from `config`, not from a path
# spelled here: the corpus does not live in one place (LSL2 and KQ4 are on the Windows drive)
# and a hardcoded `~/sierra/Games/...` silently SKIPPED KQ4 on the build box, where the games
# sit elsewhere. A gate that skips is not a gate.
_WANT = {"LSL2": ("sci0", "sci0"),
         "KQ4": ("sci0", "sci0"),
         "kq5": ("sci11", "sci1"),
         "KQ6": ("sci11", "sci11"),
         "dagger": ("sci11", "sci11"),
         "gk1": ("sci32", "sci2")}


def test_version_is_derived():
    """Each generation's volume layout is recognised, and GK1 alone lands on SCI2."""
    print("\n-- the SCI version is derived from the volume header --")
    import config
    for name, (layout, scheme) in _WANT.items():
        cfg = config.by_name(name)
        g = _game(cfg.resource_dir) if cfg else None
        if g is None:
            print("  (skip %s: game files not present)" % name)
            continue
        got = (g.volume_format(), g.patch_scheme()["name"])
        check("%s -> volume %s, patch scheme %s" % (name, layout, scheme),
              got == (layout, scheme), str(got))


def test_sci11_layout_is_refuted_on_gk1():
    """⛔ THE FALSE MATCH. GK1's script-0 header read as SCI1.1 agrees on type AND number; only
    the compression method refutes it. Without that check the reader returns a header whose
    `method` is 5150 and whose body is garbage -- silently."""
    print("\n-- an SCI32 header read as SCI1.1 is refuted, and only the method refutes it --")
    import config
    g = _game(config.by_name("gk1").resource_dir)
    if g is None:
        print("  (skip: GK1 files not present)")
        return
    pkg, off = g.entries[(R.SCRIPT, 0)]
    vol = g.volumes[pkg]
    as11 = g._read_volume_header(vol, off, "sci11")
    check("the SCI1.1 layout is REFUSED on GK1's script 0", as11 is None, repr(as11))

    # ...and the refutation is the method, not the type/number: read the same bytes by hand.
    with open(vol, "rb") as f:
        f.seek(off)
        hdr = f.read(13)
    rtype = hdr[0] & 0x7F
    number, _comp, _decomp, method11 = struct.unpack_from("<HHHH", hdr, 1)
    check("...because type and number MATCH under the wrong layout too",
          rtype == R.SCRIPT and number == 0, "type=%d number=%d" % (rtype, number))
    check("...and it is the compression method that is impossible",
          method11 not in R._METHODS, "method read as SCI1.1 = %d" % method11)

    as32 = g._read_volume_header(vol, off, "sci32")
    check("the SCI32 layout is ACCEPTED, with a real compression method",
          as32 is not None and as32["method"] in R._METHODS,
          repr(as32 and as32["method"]))


def test_shipped_pairs_would_load():
    """Sierra's OWN loose patches are the control: the checker must accept real Sierra bytes."""
    print("\n-- Sierra's own GK1 loose patches load (the checker accepts real bytes) --")
    import config
    d = os.path.expanduser(config.by_name("gk1").resource_dir)
    if not os.path.isdir(d):
        print("  (skip: GK1 files not present)")
        return
    for n in (391, 64921, 64929):
        scr, hep = os.path.join(d, "%d.SCR" % n), os.path.join(d, "%d.HEP" % n)
        if not (os.path.exists(scr) and os.path.exists(hep)):
            print("  (skip %d: not shipped)" % n)
            continue
        problems = V.verify(open(scr, "rb").read(), open(hep, "rb").read(), n)
        check("Sierra's own %d.SCR/%d.HEP verifies clean" % (n, n), not problems,
              "; ".join(problems))


def test_the_checker_has_teeth():
    """⛔ THE CONTROL. Four corruptions, each the shape of a real back-end bug, each refused."""
    print("\n-- and it refuses the four ways a script/heap pair goes wrong --")
    import config
    d = os.path.expanduser(config.by_name("gk1").resource_dir)
    if not os.path.isdir(d):
        print("  (skip: GK1 files not present)")
        return
    scr = open(os.path.join(d, "64921.SCR"), "rb").read()
    hep = open(os.path.join(d, "64921.HEP"), "rb").read()
    other = os.path.join(d, "391.HEP")
    check("the clean pair passes (so a refusal below means something)",
          not V.verify(scr, hep))

    if os.path.exists(other):
        check("a script paired with ANOTHER script's heap is refused",
              bool(V.verify(scr, open(other, "rb").read())))

    check("a truncated heap is refused", bool(V.verify(scr, hep[:-40])))

    h = bytearray(hep)
    at = V.PATCH_HEADER + struct.unpack_from("<H", h, V.PATCH_HEADER)[0]
    n = struct.unpack_from("<H", h, at)[0]
    struct.pack_into("<H", h, at, n + 40)
    check("a relocation table that overruns the heap is refused", bool(V.verify(scr, bytes(h))))

    s = bytearray(scr)
    if struct.unpack_from("<H", s, V.PATCH_HEADER + V.NUM_EXPORTS_OFF)[0]:
        struct.pack_into("<H", s, V.PATCH_HEADER + V.EXPORT_TABLE_OFF, 0xF000)
        check("an export pointing past the end of the script is refused",
              bool(V.verify(bytes(s), hep)))


def run():
    print("=== test_sci2_backend: GK1's version is derived, and its resources would load ===")
    test_version_is_derived()
    test_sci11_layout_is_refuted_on_gk1()
    test_shipped_pairs_would_load()
    test_the_checker_has_teeth()
    print("\n%d passed, %d failed%s"
          % (len(PASS), len(FAIL), ("  FAILURES: %s" % FAIL) if FAIL else ""))
    return not FAIL


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
