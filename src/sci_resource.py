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

    # -- resource extraction ------------------------------------------------
    def _read_volume_header(self, vol_path, offset):
        with open(vol_path, "rb") as f:
            f.seek(offset)
            hdr = f.read(8)
            if len(hdr) < 8:
                return None
            rid, comp, decomp, method = struct.unpack("<HHHH", hdr)
            body = f.read(comp - 4)   # comp includes the 4 bytes of decomp+method
            return {"id": rid, "number": rid & 0x7FF, "type": rid >> 11,
                    "comp": comp, "decomp": decomp, "method": method, "body": body}

    def _resolve_volume(self, package, offset, want_type, want_num):
        """The package field's mapping to resource.00N varies; try the obvious
        candidates and accept the one whose header id matches."""
        for vnum in (package, package + 1, 1):
            if vnum in self.volumes:
                h = self._read_volume_header(self.volumes[vnum], offset)
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
        return _decompress(h["method"], h["body"], h["decomp"])

    def get_script(self, n):
        return self.get(SCRIPT, n)

    def get_vocab(self, n):
        return self.get(VOCAB, n)

    def list_type(self, rtype):
        return sorted(num for (t, num) in self.entries if t == rtype)


def _decompress(method, body, decomp_size):
    """SCI0: method 0 = none, 1 = LZW, 2 = Huffman."""
    if method == 0:
        return body[:decomp_size] if decomp_size else body
    if method == 1:
        return _decompress_lzw(body, decomp_size)
    if method == 2:
        return _decompress_huffman(body, decomp_size)
    raise NotImplementedError(f"SCI0 compression method {method} not implemented")


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
