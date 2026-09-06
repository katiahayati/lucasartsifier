"""Would the INTERPRETER accept this script/heap pair? -- SCI1.1 through SCI2.1.

    python3 tools/verify_sci_script.py <a.SCR> <a.HEP> [...]
    python3 tools/verify_sci_script.py --dir ~/sierra/patched/gk1

A compiler that returns 0 has said the SOURCE was well formed. It has not said the RESOURCE is
loadable: the script and the heap are two files that have to agree about where every object,
method body and string lives, and a disagreement is a crash inside `Script::init`, not a compile
error. `emit_patches` shipped GK1's first SCI2 bytes with nothing between the compiler's exit
code and the game ([[measure-the-emitted-bytes]] is the same lesson one level down: the source is
not the bytecode, and the bytecode is not a loadable resource).

EVERY CHECK HERE IS ONE OF ScummVM'S OWN. They are transcribed from `engines/sci/engine/
script.cpp` -- `Script::init`, `identifyOffsets` and `getRelocationTableSci0Sci21` -- and each
carries the `error()`/`warning()` text it stands in for, so this file claims no authority of its
own: it fails exactly where the engine would refuse to load, and nowhere else. That is what makes
a PASS here evidence rather than an opinion.

⛔ It is a STRUCTURAL check, not a behavioural one. It says the resource loads; it says nothing
about whether the guard inside it is the right guard, or fires. Only play does.

The layout, from the same source:

    script  [0]=heap-relative something, [6]=numExports, [8..]=export offsets (uint16 each)
    heap    [0]=offset of the end of the strings == the RELOCATION TABLE
            [2]=locals count; objects begin at [2]*2+4
            object := 0x1234 magic, uint16 numProperties, ... then numProperties*2 bytes
            strings run from the end of the last object to heap[0], each NUL-terminated
            relocation table := uint16 count, then `count` uint16 positions
"""
import argparse
import os
import struct
import sys

MAGIC = 0x1234
NUM_EXPORTS_OFF = 6          # kSci11NumExportsOffset
EXPORT_TABLE_OFF = 8         # kSci11ExportTableOffset
PATCH_HEADER = 2             # [0x80|type][0x00] on a loose patch file


def _u16(b, at):
    if at + 2 > len(b):
        raise IndexError("read past end at %d (size %d)" % (at, len(b)))
    return struct.unpack_from("<H", b, at)[0]


def _strip_patch_header(data, want_type):
    """A loose patch carries `[0x80|type][0x00]`; a raw compiler output does not."""
    if len(data) > PATCH_HEADER and data[0] == (0x80 | want_type) and data[1] == 0x00:
        return data[PATCH_HEADER:]
    return data


def verify(script, heap, number=None):
    """[] if the pair loads, else a list of the engine refusals it would hit."""
    bad, warn = [], []
    scr = _strip_patch_header(script, 2)
    hep = _strip_patch_header(heap, 17)

    # cmdVerifyScripts: "script and heap %d together are larger than 64KB"
    if len(scr) + len(hep) > 65535:
        bad.append("script+heap is %d bytes, over the 64KB the interpreter allows"
                   % (len(scr) + len(hep)))

    # Script::init -- the export table must fit inside the script.
    try:
        n_exports = _u16(scr, NUM_EXPORTS_OFF)
    except IndexError as e:
        return ["script is too short to hold a header: %s" % e]
    end_exports = EXPORT_TABLE_OFF + n_exports * 2
    if end_exports > len(scr):
        bad.append("export table of %d entries runs to %d, past the %d-byte script"
                   % (n_exports, end_exports, len(scr)))
        return bad
    exports = [_u16(scr, EXPORT_TABLE_OFF + 2 * i) for i in range(n_exports)]
    for i, off in enumerate(exports):
        # export 0 may legitimately be 0 ("no such export") in some games; a nonzero one that
        # points outside the script is the KQ5-CD class of failure -- a call into garbage.
        if off and off >= len(scr):
            bad.append("export %d points to %d, past the %d-byte script" % (i, off, len(scr)))

    # identifyOffsets: the heap's two header words bound everything after them.
    try:
        end_of_strings = _u16(hep, 0)          # == the relocation table offset
        locals_count = _u16(hep, 2)
    except IndexError as e:
        return bad + ["heap is too short to hold a header: %s" % e]
    obj_start = locals_count * 2 + 4
    if obj_start > len(hep):
        bad.append("object start %d is beyond the %d-byte heap "
                   "(\"object start is beyond heap size\")" % (obj_start, len(hep)))
    if end_of_strings > len(hep):
        bad.append("end of strings %d is beyond the %d-byte heap "
                   "(\"end of string is beyond heap size\")" % (end_of_strings, len(hep)))
    if bad:
        return bad

    # The object walk. It runs on BOTH files at once: the heap holds each object's property
    # VALUES, the script holds its property and method DICTIONARIES, and the walk advances a
    # pointer into each. They must run out together -- that is the invariant a mismatched
    # script/heap pair breaks, and the reason a script may never ship without its heap.
    at = obj_start
    hunk = EXPORT_TABLE_OFF + n_exports * 2
    objects, methods_seen = 0, 0
    while True:
        if at + 2 > len(hep):
            bad.append("unexpected end of heap while walking objects (at %d)" % at)
            return bad
        if _u16(hep, at) != MAGIC:
            break
        at += 2
        if at + 2 > len(hep):
            bad.append("unexpected end of heap reading property count (at %d)" % at)
            return bad
        n_props = _u16(hep, at)
        block = n_props * 2
        if block < 4:
            bad.append("object %d declares %d properties -- \"invalid block size\""
                       % (objects, n_props))
            return bad
        at += 2
        if at + 6 > len(hep):
            bad.append("unexpected end of heap reading object header (at %d)" % at)
            return bad
        script_num = _u16(hep, at + 6)          # 0xFFFF = a CLASS, which owns no property dict
        if script_num != 0xFFFF:
            hunk += n_props * 2
        if hunk + 2 > len(scr):
            bad.append("object %d's method dictionary starts at %d, past the %d-byte script"
                       % (objects, hunk, len(scr)))
            return bad
        n_methods = _u16(scr, hunk)
        hunk += 2 + n_methods * 4
        if hunk > len(scr):
            bad.append("object %d's %d method(s) run to %d, past the %d-byte script"
                       % (objects, n_methods, hunk, len(scr)))
            return bad
        # Every method's code pointer must land inside the script. This is the check that a
        # heap written against a DIFFERENT script's code fails.
        for m in range(n_methods):
            code = _u16(scr, hunk - n_methods * 4 + m * 4 + 2)
            if code >= len(scr):
                bad.append("object %d method %d starts at %d, past the %d-byte script"
                           % (objects, m, code, len(scr)))
        methods_seen += n_methods
        at += block - 4
        objects += 1

    if at > end_of_strings:
        bad.append("objects end at %d but the strings were declared to end at %d "
                   "(\"string block / end-of-string block mismatch\")" % (at, end_of_strings))
        return bad

    # The relocation table: `numEntries` positions, and it is the last thing in the heap.
    if end_of_strings + 2 > len(hep):
        bad.append("relocation table offset %d leaves no room for its count" % end_of_strings)
        return bad
    n_reloc = _u16(hep, end_of_strings)
    table_end = end_of_strings + 2 + n_reloc * 2
    if table_end != len(hep):
        warn.append("relocation table of %d entries ends at %d, not the heap's %d bytes "
                    "(\"unexpected relocation table size\")" % (n_reloc, table_end, len(hep)))
    if table_end > len(hep):
        bad.append("relocation table of %d entries runs past the %d-byte heap"
                   % (n_reloc, len(hep)))
        return bad
    for i in range(n_reloc):
        pos = _u16(hep, end_of_strings + 2 + 2 * i)
        # relocateBlock: "Attempt to relocate odd variable" -- a relocation lands on a word.
        if pos % 2:
            bad.append("relocation entry %d points at odd offset %d" % (i, pos))
        if pos >= len(hep):
            bad.append("relocation entry %d points at %d, past the %d-byte heap"
                       % (i, pos, len(hep)))

    return bad + ["(warning) " + w for w in warn]


def _pairs_in(d):
    out = []
    for fn in sorted(os.listdir(d)):
        stem, _, ext = fn.rpartition(".")
        if ext.upper() == "SCR" and stem.isdigit():
            hep = os.path.join(d, stem + ".HEP")
            if os.path.exists(hep):
                out.append((int(stem), os.path.join(d, fn), hep))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*", help="alternating <n>.SCR <n>.HEP paths")
    ap.add_argument("--dir", help="verify every <n>.SCR/<n>.HEP pair in a directory")
    a = ap.parse_args(argv)

    pairs = _pairs_in(a.dir) if a.dir else [
        (None, a.files[i], a.files[i + 1]) for i in range(0, len(a.files) - 1, 2)]
    if not pairs:
        ap.error("nothing to verify")

    failed = 0
    for num, scr_path, hep_path in pairs:
        problems = verify(open(scr_path, "rb").read(), open(hep_path, "rb").read(), num)
        hard = [p for p in problems if not p.startswith("(warning)")]
        failed += bool(hard)
        name = os.path.basename(scr_path)
        print("%-14s %s" % (name, "OK" if not problems else
                            ("REFUSED" if hard else "ok, with a warning")))
        for p in problems:
            print("    %s" % p)
    print("\n%d pair(s) verified, %d would be refused by the interpreter"
          % (len(pairs), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
