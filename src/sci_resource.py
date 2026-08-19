"""SCI0 resource reader — extract packed resources (scripts, vocab) from a real
Sierra game's RESOURCE.MAP + RESOURCE.00x volumes.

Needed for the Phase-B fidelity gate: pull the ORIGINAL compiled `script.NNN`
bytecode out of the game so we can byte-compare it against a recompile, and read
`vocab.997` (the selector table). Format is authoritative, per SCICompanion's
ResourceBlob.h:

  resource.map : array of 6-byte entries, terminated by all-0xFF
      uint16  id     = (number:11) | (type:5)          # low 11 bits number, top 5 type
      uint32  packed = (offset:26) | (package:6)        # low 26 bits offset, top 6 bits volume
  volume header (RESOURCEHEADER_SCI0, 8 bytes at the offset):
      uint16 id ; uint16 cbCompressed ; uint16 cbDecompressed ; uint16 method
      data follows: (cbCompressed - 4) bytes  (the -4 covers cbDecompressed+method)

ResourceType: View=0 Pic=1 Script=2 Text=3 Sound=4 Memory=5 Vocab=6 Font=7 Cursor=8 Patch=9
"""

from __future__ import annotations

import os
import struct
import glob

VIEW, PIC, SCRIPT, TEXT, SOUND, MEMORY, VOCAB, FONT, CURSOR, PATCH = range(10)
HEAP = 17                      # SCI1.1 splits a script's data half into its own resource type
_TYPE_NAME = {SCRIPT: "script", VOCAB: "vocab", VIEW: "view", PIC: "pic", TEXT: "text",
              SOUND: "sound", FONT: "font", CURSOR: "cursor", PATCH: "patch", MEMORY: "memory"}


class Sci0Game:
    def __init__(self, game_dir):
        self.dir = game_dir
        self.map_path = self._find("resource.map")
        self.volumes = self._volume_files()
        self.entries = self._parse_map()          # (type, number) -> (package, offset)

    # -- path helpers (case-insensitive; games ship UPPERCASE names) --------
    def _find(self, name):
        for f in os.listdir(self.dir):
            if f.lower() == name.lower():
                return os.path.join(self.dir, f)
        raise FileNotFoundError(f"{name} not in {self.dir}")

    def _volume_files(self):
        vols = {}
        for f in os.listdir(self.dir):
            low = f.lower()
            if low.startswith("resource.") and low[9:].isdigit():
                vols[int(low[9:])] = os.path.join(self.dir, f)
        return vols

    def _parse_map(self):
        data = open(self.map_path, "rb").read()
        secs = self._sci1_sections(data)
        # The map's shape is also the PIC dialect: an SCI1 map means SCI1 pics, whose 0xFE
        # extended-op table differs from SCI0's (sci_gfx._render dispatches on this). Recorded
        # here because it is RECOGNISED from the same evidence, not declared per game.
        self.sci1 = secs is not None
        if secs is not None:
            return self._parse_map_sci1(data, secs)
        entries = {}
        for i in range(0, len(data) - 5, 6):
            rid, packed = struct.unpack_from("<HI", data, i)
            if rid == 0xFFFF and packed == 0xFFFFFFFF:
                break
            number = rid & 0x07FF
            rtype = rid >> 11
            offset = packed & 0x03FFFFFF
            package = packed >> 26
            entries[(rtype, number)] = (package, offset)
        return entries

    @staticmethod
    def _sci1_sections(data):
        """[(type, offset, length)] if this is an SCI1/SCI1.1 map, else None.

        SCI0 stores one flat array of 6-byte (id, packed) entries. SCI1 replaced it with a
        DIRECTORY -- `byte type, uint16 offset` repeated, terminated by type 0xFF whose offset is
        the end of the map -- followed by one section of entries per type. Recognised by that
        shape rather than declared, so a game is not asked which SCI version it is: the
        terminator must land exactly on the file length and every offset must be inside it, which
        an SCI0 map does not satisfy (KQ4's first "offset" alone is past its 7,476 bytes)."""
        dirs, i = [], 0
        while i + 3 <= len(data):
            t = data[i]
            off = struct.unpack_from("<H", data, i + 1)[0]
            i += 3
            if off > len(data):
                return None
            if t == 0xFF:
                if off != len(data) or not dirs:
                    return None
                bounds = [o for _t, o in dirs] + [off]
                return [(dirs[k][0] & 0x1F, bounds[k], bounds[k + 1] - bounds[k])
                        for k in range(len(dirs))]
            dirs.append((t, off))
        return None

    def _parse_map_sci1(self, data, secs):
        """SCI1 entries are `uint16 number` plus an offset whose WIDTH is the version:
        4 bytes with the volume in the top nibble (SCI1), or 3 bytes pre-shifted right by one
        (SCI1.1). DERIVED, not declared -- the only size that divides every section evenly, and
        then confirmed by resolving an entry against a real volume header. KQ5 lands on 6 (its
        VIEW section, 3,078 bytes, is not a multiple of 5); KQ6 and Dagger land on 5 (their PIC
        sections, 485 and 455 bytes, are not multiples of 6)."""
        sizes = [n for n in (5, 6) if all(ln % n == 0 for _t, _o, ln in secs if ln > 0)]
        for esz in sizes or (5, 6):
            entries = {}
            for (rtype, off, ln) in secs:
                for k in range(ln // esz):
                    p = off + k * esz
                    number = struct.unpack_from("<H", data, p)[0]
                    if esz == 5:
                        o = struct.unpack_from("<H", data, p + 2)[0] | (data[p + 4] << 16)
                        entries[(rtype, number)] = (0, o << 1)
                    else:
                        packed = struct.unpack_from("<I", data, p + 2)[0]
                        entries[(rtype, number)] = (packed >> 28, packed & 0x0FFFFFFF)
            if len(sizes) == 1 or self._entries_resolve(entries):
                return entries
        return {}

    def _entries_resolve(self, entries):
        """Does a sample of these entries actually point at its own header in a volume?
        The tiebreak when both entry widths divide every section evenly."""
        sample = sorted(entries)[:8]
        return bool(sample) and all(
            self._resolve_volume(pkg, off, t, n)[1] is not None
            for (t, n), (pkg, off) in ((k, entries[k]) for k in sample))

    # -- resource extraction ------------------------------------------------
    def _read_volume_header(self, vol_path, offset, layout="sci0"):
        """One resource's header + body. Three layouts, all validated by the caller against the
        (type, number) the map asked for, so the right one is RECOGNISED rather than declared:

            sci0   uint16 id(type:5|number:11), uint16 comp, uint16 decomp, uint16 method
                   -- `comp` counts the 4 header bytes after it, so the body is comp-4
            sci1   byte type|0x80, uint16 number, uint16 comp, uint16 decomp, uint16 method
                   -- same comp convention as sci0
            sci11  the sci1 header, but `comp` is the body length outright
        """
        with open(vol_path, "rb") as f:
            f.seek(offset)
            hdr = f.read(9)
            if len(hdr) < 9:
                return None
            if layout == "sci0":
                rid, comp, decomp, method = struct.unpack_from("<HHHH", hdr)
                rtype, number, skip, blen = rid >> 11, rid & 0x7FF, 8, comp - 4
            else:
                rtype = hdr[0] & 0x7F
                number, comp, decomp, method = struct.unpack_from("<HHHH", hdr, 1)
                skip, blen = 9, (comp if layout == "sci11" else comp - 4)
            if blen < 0 or decomp > 0xFFFF:
                return None
            f.seek(offset + skip)
            return {"number": number, "type": rtype, "comp": comp, "decomp": decomp,
                    "method": method, "body": f.read(blen)}

    def _resolve_volume(self, package, offset, want_type, want_num):
        """The package field's mapping to resource.00N varies; try the obvious
        candidates and accept the one whose header id matches."""
        for vnum in (package, package + 1, 1, 0):
            if vnum not in self.volumes:
                continue
            for layout in ("sci0", "sci11", "sci1"):
                h = self._read_volume_header(self.volumes[vnum], offset, layout)
                if h and h["type"] == want_type and h["number"] == want_num:
                    return self.volumes[vnum], h
        return None, None

    def get(self, rtype, number):
        key = (rtype, number)
        if key not in self.entries:
            raise KeyError(f"{_TYPE_NAME.get(rtype, rtype)}.{number} not in map")
        package, offset = self.entries[key]
        vol, h = self._resolve_volume(package, offset, rtype, number)
        if h is None:
            raise IOError(f"could not locate {_TYPE_NAME.get(rtype,rtype)}.{number} "
                          f"(package={package} offset={offset})")
        if h["method"] == 0:
            return h["body"][:h["decomp"]] if h["decomp"] else h["body"]
        out = _decompress(h["method"], h["body"], h["decomp"])
        # THE RESOURCE SAYS HOW BIG IT DECOMPRESSES TO, SO CHECK IT. Without this a decoder
        # that is wrong for the game's SCI version returns a short or scrambled buffer and
        # every consumer treats it as art: `sci_gfx` renders a control plane from garbage,
        # `control_oracle` reads "the exit does NOT force the rect" off it, and the run
        # reports fewer gates with nothing amiss. MEASURED on titles outside the corpus,
        # where the SCI0-only method table is wrong: Police Quest 640/830 and Quest for
        # Glory 2 687/968 resources decoded to the wrong size, silently. Our four games are
        # clean (LSL2 650, KQ4 963, KQ6 1397, LB2 980 resources, zero mismatches), so this
        # costs them nothing and turns the next title's format gap into an error that names
        # the resource instead of a quiet loss of detection.
        if h["decomp"] and len(out) != h["decomp"]:
            raise ValueError(
                "%s.%d decompressed to %d bytes, not the %d the map declares (method %d). "
                "The decompressor is wrong for this game's SCI version -- see "
                "ScummVM resource.cpp, where methods 1 and 2 are version-dependent and "
                "3/4 exist too." % (_TYPE_NAME.get(rtype, rtype), number, len(out),
                                    h["decomp"], h["method"]))
        return out

    def get_script(self, n):
        return self.get(SCRIPT, n)

    def get_vocab(self, n):
        return self.get(VOCAB, n)

    def list_type(self, rtype):
        return sorted(num for (t, num) in self.entries if t == rtype)

    def patch_scheme(self):
        """How this game wants a replaced script written as a LOOSE PATCH, derived from its map.

        Three answers, and the map itself distinguishes them -- the same "recognised by shape
        rather than declared" rule `_sci1_sections` already follows:

            no SCI1 directory              -> ('script.%03d', script only)      SCI0: LSL2, KQ4
            SCI1 directory, no type 17     -> ('%d.SCR',      script only)      SCI1:  KQ5
            SCI1 directory, type 17 present-> ('%d.SCR' + '%d.HEP')             SCI1.1: KQ6, LB2

        A type-17 (HEAP) section means every script is stored as a script/heap PAIR, and shipping
        the script half alone is a crash rather than a partial patch -- the interpreter reads
        objects out of the heap at offsets the new code assumes.

        ScummVM's `readResourcePatches` accepts both naming schemes at any version, so this is a
        convention choice, not a compatibility one: use the scheme the game itself uses.
        """
        if self._sci1_sections(open(self.map_path, "rb").read()) is None:
            return {"name": "sci0", "script": "script.%03d", "heap": None}
        if not self.list_type(HEAP):
            return {"name": "sci1", "script": "%d.SCR", "heap": None}
        return {"name": "sci11", "script": "%d.SCR", "heap": "%d.HEP"}


def _decompress(method, body, decomp_size):
    """method 0 = none, 1 = LZW, 2 = Huffman (SCI0); 18/19/20 = DCL implode (SCI1.1)."""
    if method == 0:
        return body[:decomp_size] if decomp_size else body
    if method == 1:
        return _decompress_lzw(body, decomp_size)
    if method == 2:
        return _decompress_huffman(body, decomp_size)
    if method in (18, 19, 20):
        return _decompress_dcl(body, decomp_size)
    raise NotImplementedError(f"compression method {method} not implemented")


# PKWARE DCL "implode" -- what SCI1.1 packs its resources with (methods 18/19/20). Ported from
# ScummVM `common/compression/dcl.cpp`; the three prefix trees are that file's BN/LN macro tables,
# machine-translated rather than retyped (BN(l,r) = l<<12|r, LN(v) = v|LEAF).
_DCL_LEAF = 0x40000000
_LENGTH_TREE = [
    4098, 12292, 20486, 28680, 36874, 45068, 1073741825, 53262, 61456, 69650, 1073741827,
    1073741826, 1073741824, 77844, 86038, 94232, 1073741830, 1073741829, 1073741828, 102426,
    110620, 1073741834, 1073741833, 1073741832, 1073741831, 118814, 1073741837, 1073741836,
    1073741835, 1073741839, 1073741838,
]
_DISTANCE_TREE = [
    4098, 12292, 20486, 28680, 36874, 45068, 1073741824, 53262, 61456, 69650, 77844, 86038,
    94232, 102426, 110620, 118814, 127008, 135202, 143396, 151590, 159784, 167978, 176172,
    1073741826, 1073741825, 184366, 192560, 200754, 208948, 217142, 225336, 233530, 241724,
    249918, 258112, 266306, 274500, 282694, 290888, 299082, 307276, 1073741830, 1073741829,
    1073741828, 1073741827, 315470, 323664, 331858, 340052, 348246, 356440, 364634, 372828,
    381022, 389216, 397410, 405604, 413798, 421992, 430186, 438380, 446574, 1073741845,
    1073741844, 1073741843, 1073741842, 1073741841, 1073741840, 1073741839, 1073741838,
    1073741837, 1073741836, 1073741835, 1073741834, 1073741833, 1073741832, 1073741831,
    454768, 462962, 471156, 479350, 487544, 495738, 503932, 512126, 1073741871, 1073741870,
    1073741869, 1073741868, 1073741867, 1073741866, 1073741865, 1073741864, 1073741863,
    1073741862, 1073741861, 1073741860, 1073741859, 1073741858, 1073741857, 1073741856,
    1073741855, 1073741854, 1073741853, 1073741852, 1073741851, 1073741850, 1073741849,
    1073741848, 1073741847, 1073741846, 1073741887, 1073741886, 1073741885, 1073741884,
    1073741883, 1073741882, 1073741881, 1073741880, 1073741879, 1073741878, 1073741877,
    1073741876, 1073741875, 1073741874, 1073741873, 1073741872,
]


class _LsbBits:
    """DCL reads its bit stream least-significant-bit first, refilling a 32-bit window."""
    __slots__ = ("d", "i", "bits", "n")

    def __init__(self, data):
        self.d, self.i, self.bits, self.n = data, 0, 0, 0

    def get(self, n):
        while self.n < n:
            b = self.d[self.i] if self.i < len(self.d) else 0
            self.i += 1
            self.bits |= b << self.n
            self.n += 8
        v = self.bits & ((1 << n) - 1)
        self.bits >>= n
        self.n -= n
        return v

    def huff(self, tree):
        pos = 0
        while not tree[pos] & _DCL_LEAF:
            pos = (tree[pos] & 0xFFF) if self.get(1) else (tree[pos] >> 12)
        return tree[pos] & 0xFFFF


def _decompress_dcl(body, out_len):
    bs = _LsbBits(bytes(body))
    mode, dict_type = bs.get(8), bs.get(8)
    if mode != 0:
        # ASCII mode literals go through a third (511-node) tree. No SCI1.1 resource we have
        # uses it -- KQ6 and Dagger pack every resource in binary mode -- so it is not carried.
        raise NotImplementedError(f"DCL ASCII mode ({mode}) not implemented")
    if dict_type not in (4, 5, 6):
        raise ValueError(f"DCL bad dictionary type {dict_type}")
    out = bytearray()
    while len(out) < out_len:
        if bs.get(1):                                   # a (length, distance) back-reference
            v = bs.huff(_LENGTH_TREE)
            ln = v + 2 if v < 8 else 8 + (1 << (v - 7)) + bs.get(v - 7)
            if ln == 519:
                break                                   # end-of-stream marker
            v = bs.huff(_DISTANCE_TREE)
            off = ((v << 2) | bs.get(2)) if ln == 2 else ((v << dict_type) | bs.get(dict_type))
            off += 1
            if off > len(out):
                raise ValueError("DCL back-reference before start of stream")
            # Byte-at-a-time, because a run may overlap itself (off < ln).
            for _ in range(ln):
                out.append(out[-off])
        else:
            out.append(bs.get(8))
    return bytes(out[:out_len])


def _decompress_huffman(src, out_len):
    """SCI0 Huffman (comp method 2, used by PICs). Faithful port of SCICompanion
    Src/Util/Codec.cpp getc2/decompressHuffman. A prefix tree of `numnodes` 2-byte
    nodes (value, branch); a '1' bit follows the low nibble, '0' the high nibble; a
    zero branch is a leaf (or an escaped raw byte). Terminator = escaped `term`."""
    src = bytes(src)
    complength = len(src)
    numnodes, terminator = src[0], src[1]
    nodes_base = 2
    bytectr = 2 + (numnodes << 1)
    bitctr = 0
    out = bytearray()

    def getc2():
        nonlocal bytectr, bitctr
        node = nodes_base
        while src[node + 1] != 0:
            value = (src[bytectr] << bitctr) & 0xFFFF
            bitctr += 1
            if bitctr == 8:
                bitctr = 0
                bytectr += 1
            if value & 0x80:
                nxt = src[node + 1] & 0x0F
                if nxt == 0:
                    result = (src[bytectr] << bitctr) & 0xFFFF
                    bytectr += 1
                    if bytectr > complength:
                        return -1
                    elif bytectr < complength:
                        result |= src[bytectr] >> (8 - bitctr)
                    return (result & 0xFF) | 0x100
            else:
                nxt = src[node + 1] >> 4
            node += nxt << 1
        return src[node]

    stop = 0x100 | terminator
    while True:
        c = getc2()
        if c == stop or c < 0:
            break
        out.append(c & 0xFF)
        if len(out) > out_len + 8:
            break
    return bytes(out)


def _decompress_lzw(src, out_len):
    """SCI0 9-12 bit LZW (ported verbatim from SCICompanion Src/Util/Codec.cpp
    decompressLZW). Tokens < 0x100 are literals; 0x100 resets, 0x101 ends; tokens
    from 0x102 up index a growing dictionary that records (start, length) into the
    output already produced."""
    dest = bytearray(out_len)
    bitlen, bitmask, bitctr, bytectr = 9, 0x01ff, 0, 0
    maxtoken, tokenctr, tokenlastlength, destctr = 0x200, 0x102, 0, 0
    tokenlist = [0] * 4096
    tokenlengthlist = [0] * 4096
    n = len(src)
    while bytectr < n:
        tokenmaker = src[bytectr] >> bitctr
        bytectr += 1
        if bytectr < n:
            tokenmaker |= src[bytectr] << (8 - bitctr)
        if bytectr + 1 < n:
            tokenmaker |= src[bytectr + 1] << (16 - bitctr)
        token = tokenmaker & bitmask
        bitctr += bitlen - 8
        while bitctr >= 8:
            bitctr -= 8
            bytectr += 1
        if token == 0x101:
            break
        if token == 0x100:
            maxtoken, bitlen, bitmask, tokenctr = 0x200, 9, 0x01ff, 0x102
            continue
        if token > 0xff:
            if token >= tokenctr:
                raise ValueError(f"LZW: bad token {token:#x} (ctr {tokenctr:#x})")
            tokenlastlength = tokenlengthlist[token] + 1
            start = tokenlist[token]
            for i in range(tokenlastlength):
                if destctr >= out_len:
                    break
                dest[destctr] = dest[start + i]
                destctr += 1
        else:
            tokenlastlength = 1
            if destctr < out_len:
                dest[destctr] = token
                destctr += 1
        if tokenctr == maxtoken:
            if bitlen < 12:
                bitlen += 1
                bitmask = (bitmask << 1) | 1
                maxtoken <<= 1
            else:
                continue  # dictionary full
        tokenlist[tokenctr] = destctr - tokenlastlength
        tokenlengthlist[tokenctr] = tokenlastlength
        tokenctr += 1
    return bytes(dest)


if __name__ == "__main__":
    import sys
    d = sys.argv[1] if len(sys.argv) > 1 else "/mnt/i/sierra/lsl2"
    g = Sci0Game(d)
    print(f"game: {d}")
    print(f"volumes: {sorted(g.volumes)}")
    print(f"scripts: {len(g.list_type(SCRIPT))}  vocab: {g.list_type(VOCAB)}")
    for n in (0, 26, 31, 118):
        try:
            b = g.get_script(n)
            print(f"  script.{n}: {len(b)} bytes  head={b[:8].hex()}")
        except Exception as e:
            print(f"  script.{n}: ERROR {e}")
    try:
        v = g.get_vocab(997)
        print(f"  vocab.997 (selectors): {len(v)} bytes")
    except Exception as e:
        print(f"  vocab.997: ERROR {e}")
