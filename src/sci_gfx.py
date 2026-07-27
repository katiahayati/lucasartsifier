"""SCI0 EGA graphics decoding for the softlock oracle: rasterize a PIC's CONTROL
plane (the walkable-region bitmap the engine uses for movement) and decode VIEW
cels (sprite footprints, e.g. doors). This is what lets us reason about *where the
ego can walk* -- a fact that lives in the game's resources, not the script AST.

Both decoders are faithful ports of ScummVM (engines/sci/graphics/picture.cpp +
screen.cpp + view.cpp), validated: the control renderer matches SCICompanion's
reference control planes pixel-for-pixel, and every compressed resource decodes to
its exact stated size. See tools/pic-oracle/ for the standalone validation.
"""
from __future__ import annotations

from sci_resource import Sci0Game, PIC, VIEW

W, H = 320, 190
VIS, PRI, CON = 1, 2, 4          # GFX_SCREEN_MASK_*
WHITE = 15

_DEFAULT_EGA_PAL = [
    0x00,0x11,0x22,0x33,0x44,0x55,0x66,0x77, 0x88,0x99,0xaa,0xbb,0xcc,0xdd,0xee,0x88,
    0x88,0x01,0x02,0x03,0x04,0x05,0x06,0x88, 0x88,0xf9,0xfa,0xfb,0xfc,0xfd,0xfe,0xff,
    0x08,0x19,0x2a,0x3b,0x4c,0x5d,0x6e,0x88]
_PAT_PENSIZE, _PAT_RECT, _PAT_TEXTURE = 0x07, 0x10, 0x20
_CIRCLES = [
    [0x01],[0x72,0x02],[0xCE,0xF7,0x7D,0x0E],
    [0x1C,0x3E,0x7F,0x7F,0x7F,0x3E,0x1C,0x00],
    [0x38,0xF8,0xF3,0xDF,0x7F,0xFF,0xFD,0xF7,0x9F,0x3F,0x38],
    [0x70,0xC0,0x1F,0xFE,0xE3,0x3F,0xFF,0xF7,0x7F,0xFF,0xE7,0x3F,0xFE,0xC3,0x1F,0xF8,0x00],
    [0xF0,0x01,0xFF,0xE1,0xFF,0xF8,0x3F,0xFF,0xDF,0xFF,0xF7,0xFF,0xFD,0x7F,0xFF,0x9F,0xFF,0xE3,0xFF,0xF0,0x1F,0xF0,0x01],
    [0xE0,0x03,0xF8,0x0F,0xFC,0x1F,0xFE,0x3F,0xFE,0x3F,0xFF,0x7F,0xFF,0x7F,0xFF,0x7F,0xFF,0x7F,0xFF,0x7F,0xFE,0x3F,0xFE,0x3F,0xFC,0x1F,0xF8,0x0F,0xE0,0x03]]


# ===================== PIC control-plane rasterizer =========================
class _Screen:
    def __init__(self):
        self.vis = bytearray([0x0F]) * (W * H)   # white
        self.pri = bytearray(W * H)              # 0
        self.con = bytearray(W * H)              # 0

    def _mask(self, color, prio, control):
        f = 0
        if color != 255: f |= VIS
        if prio != 255:  f |= PRI
        if control != 255: f |= CON
        return f

    def _put(self, x, y, m, color, prio, control):
        if 0 <= x < W and 0 <= y < H:
            o = y * W + x
            if m & VIS: self.vis[o] = color
            if m & PRI: self.pri[o] = prio
            if m & CON: self.con[o] = control

    def _fill_match(self, x, y, m, cC, cP, cK):
        o = y * W + x
        r = 0
        if m & VIS:
            ega = self.vis[o]
            ega = ((ega ^ (ega >> 4)) & 0x0F) if ((x ^ y) & 1) else (ega & 0x0F)
            if ega == cC: r |= VIS
        if (m & PRI) and self.pri[o] == cP: r |= PRI
        if (m & CON) and self.con[o] == cK: r |= CON
        return r

    def line(self, x0, y0, x1, y1, color, prio, control):
        maxW, maxH = W - 1, H - 1
        left = min(max(x0, 0), maxW); top = min(max(y0, 0), maxH)
        right = min(max(x1, 0), maxW); bottom = min(max(y1, 0), maxH)
        m = self._mask(color, prio, control)
        if top == bottom:
            if right < left: left, right = right, left
            for i in range(left, right + 1): self._put(i, top, m, color, prio, control)
            return
        if left == right:
            if top > bottom: top, bottom = bottom, top
            for i in range(top, bottom + 1): self._put(left, i, m, color, prio, control)
            return
        dy = bottom - top; dx = right - left
        stepy = -1 if dy < 0 else 1; stepx = -1 if dx < 0 else 1
        dy = abs(dy) << 1; dx = abs(dx) << 1
        self._put(left, top, m, color, prio, control)
        self._put(right, bottom, m, color, prio, control)
        if dx > dy:
            frac = dy - (dx >> 1)
            while left != right:
                if frac >= 0: top += stepy; frac -= dx
                left += stepx; frac += dy
                self._put(left, top, m, color, prio, control)
        else:
            frac = dx - (dy >> 1)
            while top != bottom:
                if frac >= 0: left += stepx; frac -= dy
                top += stepy; frac += dx
                self._put(left, top, m, color, prio, control)

    def fill(self, x, y, color, prio, control):
        screenMask = self._mask(color, prio, control)
        if not (0 <= x < W and 0 <= y < H): return
        o = y * W + x
        sC = self.vis[o]; sP = self.pri[o]; sK = self.con[o]
        sC = ((sC ^ (sC >> 4)) & 0x0F) if ((x ^ y) & 1) else (sC & 0x0F)
        if screenMask & VIS:
            if color == WHITE or sC != WHITE: return
        elif screenMask & PRI:
            if prio == 0 or sP != 0: return
        elif screenMask & CON:
            if control == 0 or sK != 0: return
        if (screenMask & VIS) and sC == color: screenMask &= ~VIS
        if (screenMask & PRI) and sP == prio: screenMask &= ~PRI
        if (screenMask & CON) and sK == control: screenMask &= ~CON
        if not screenMask: return
        matchMask = VIS if (screenMask & VIS) else (PRI if (screenMask & PRI) else CON)
        bR, bB = W - 1, H - 1
        stack = [(x, y)]
        while stack:
            px, py = stack.pop()
            if self._fill_match(px, py, matchMask, sC, sP, sK) == 0: continue
            self._put(px, py, screenMask, color, prio, control)
            cl = cr = px
            while cl > 0 and self._fill_match(cl - 1, py, matchMask, sC, sP, sK):
                cl -= 1; self._put(cl, py, screenMask, color, prio, control)
            while cr < bR and self._fill_match(cr + 1, py, matchMask, sC, sP, sK):
                cr += 1; self._put(cr, py, screenMask, color, prio, control)
            i = cl; a = b = 0
            while i <= cr:
                if py > 0 and self._fill_match(i, py - 1, matchMask, sC, sP, sK):
                    if a == 0: stack.append((i, py - 1)); a = 1
                else: a = 0
                if py < bB and self._fill_match(i, py + 1, matchMask, sC, sP, sK):
                    if b == 0: stack.append((i, py + 1)); b = 1
                else: b = 0
                i += 1

    def pattern(self, x, y, color, prio, control, code, texture):
        size = code & _PAT_PENSIZE
        bl, bt, br, bb = x - size, y - size, x + size + 2, y + size + 1
        if bl < 0: br -= bl; bl = 0
        if bt < 0: bb -= bt; bt = 0
        if br > W + 1:
            width = br - bl; bl = W + 1 - width; br = W + 1
        if bb > H:
            height = bb - bt; bt = H - height; bb = H
        m = self._mask(color, prio, control)
        if code & _PAT_RECT:
            for yy in range(bt, bb):
                for xx in range(bl, br):
                    if 0 <= xx < W and 0 <= yy < H:
                        self._put(xx, yy, m, color, prio, control)
        else:
            data = _CIRCLES[size]; bitmap = data[0]; bitNo = 0; di = 0
            for yy in range(bt, bb):
                for xx in range(bl, br):
                    if bitNo == 8:
                        di += 1; bitmap = data[di] if di < len(data) else 0; bitNo = 0
                    if bitmap & 1 and 0 <= xx < W and 0 <= yy < H:
                        self._put(xx, yy, m, color, prio, control)
                    bitNo += 1; bitmap >>= 1


def _render(pic_bytes):
    d = pic_bytes
    i = 0
    while i < len(d) and d[i] < 0xF0: i += 1   # skip any header bytes to first opcode
    s = _Screen()
    pal = list(_DEFAULT_EGA_PAL)
    pic_color, pic_pri, pic_ctl = 0, 255, 255
    pat_code = pat_tex = 0
    x = y = 0

    def rd():
        nonlocal i
        b = d[i]; i += 1; return b
    def nonop(): return i < len(d) and d[i] < 0xF0
    def getAbs():
        p = rd(); return rd() + ((p & 0xF0) << 4), rd() + ((p & 0x0F) << 8)
    def getRel(cx, cy):
        p = rd()
        cx += -((p >> 4) & 7) if (p & 0x80) else (p >> 4)
        cy += -(p & 7) if (p & 0x08) else (p & 7)
        return cx, cy
    def getRelMed(cx, cy):
        p = rd(); cy += -(p & 0x7F) if (p & 0x80) else p
        p = rd(); cx += -(128 - (p & 0x7F)) if (p & 0x80) else p
        return cx, cy
    def getTex():
        nonlocal pat_tex
        if pat_code & _PAT_TEXTURE: pat_tex = (rd() >> 1) & 0x7F

    while i < len(d):
        op = rd()
        if op == 0xF0:
            c = rd()
            if c < len(pal):
                pic_color = pal[c]; pic_color ^= (pic_color << 4) & 0xFF; pic_color &= 0xFF
            else:
                pic_color = c        # VGA: a direct palette index, no EGA dither pair. Only the
            #                          VISUAL plane cares, and we are here for the control one.
        elif op == 0xF1: pic_color = 255
        elif op == 0xF2: pic_pri = rd() & 0x0F
        elif op == 0xF3: pic_pri = 255
        elif op == 0xFB: pic_ctl = rd() & 0x0F
        elif op == 0xFC: pic_ctl = 255
        elif op == 0xF7:
            x, y = getAbs()
            while nonop(): ox, oy = x, y; x, y = getRel(x, y); s.line(ox, oy, x, y, pic_color, pic_pri, pic_ctl)
        elif op == 0xF5:
            x, y = getAbs()
            while nonop(): ox, oy = x, y; x, y = getRelMed(x, y); s.line(ox, oy, x, y, pic_color, pic_pri, pic_ctl)
        elif op == 0xF6:
            x, y = getAbs()
            while nonop(): ox, oy = x, y; x, y = getAbs(); s.line(ox, oy, x, y, pic_color, pic_pri, pic_ctl)
        elif op == 0xF8:
            while nonop(): x, y = getAbs(); s.fill(x, y, pic_color, pic_pri, pic_ctl)
        elif op == 0xF9: pat_code = rd()
        elif op == 0xF4:
            getTex(); x, y = getAbs(); s.pattern(x, y, pic_color, pic_pri, pic_ctl, pat_code, pat_tex)
            while nonop(): getTex(); x, y = getRel(x, y); s.pattern(x, y, pic_color, pic_pri, pic_ctl, pat_code, pat_tex)
        elif op == 0xFD:
            getTex(); x, y = getAbs(); s.pattern(x, y, pic_color, pic_pri, pic_ctl, pat_code, pat_tex)
            while nonop(): getTex(); x, y = getRelMed(x, y); s.pattern(x, y, pic_color, pic_pri, pic_ctl, pat_code, pat_tex)
        elif op == 0xFA:
            while nonop(): getTex(); x, y = getAbs(); s.pattern(x, y, pic_color, pic_pri, pic_ctl, pat_code, pat_tex)
        elif op == 0xFE:
            sub = rd()
            if sub == 0:
                while nonop():
                    px = rd(); v = rd()
                    if px < len(pal): pal[px] = v
            elif sub == 1:
                pn = rd()
                for k in range(40):
                    v = rd()
                    if pn == 0 and k < len(pal): pal[k] = v
            elif sub == 2: i += 41
            elif sub in (3, 5): i += 1
            elif sub in (4, 6): pass
            elif sub == 7:
                getAbs(); sz = d[i] | (d[i + 1] << 8); i += 2 + sz
            elif sub == 8: i += 14
        elif op == 0xFF: break
        else: raise ValueError(f"bad pic opcode {op:#x} at {i}")
    return s


def _vector_data(d):
    """The opcode stream that draws a PIC's control/priority planes.

    SCI0 EGA pics ARE that stream. SCI1.1 VGA pics wrap it: the visible image became a compressed
    cel, but the control and priority planes stayed VECTOR data, in a chunk a header points at
    (ScummVM `GfxPicture::drawSci11Vga` -- `vector_dataPos = READ_LE_UINT32(inbuffer + 16)`, then
    the very same `drawVectorData`). So one interpreter serves both and only the framing differs.

    Told apart by the first byte, not by asking which SCI version the game is: an opcode stream
    starts with one (>= 0xF0), an SCI1.1 header starts with its size fields."""
    if not d or d[0] >= 0xF0:
        return d
    if len(d) >= 20:
        vp = int.from_bytes(bytes(d[16:20]), "little")
        if 0 < vp < len(d) and d[vp] >= 0xF0:
            return d[vp:]
    return d


def render_control(game: Sci0Game, pic_num: int) -> bytearray:
    """Return the 320x190 control plane of a PIC (one byte per pixel, control color 0..15)."""
    return _render(_vector_data(game.get(PIC, pic_num))).con


# ============================== VIEW decoder ================================
class Cel:
    __slots__ = ("width", "height", "dx", "dy", "clearKey", "pix")

    def rect(self, x, y):
        """Screen rect (left, top, right, bottom) when placed at posn (x,y). SCI0 getCelRect."""
        left = x + self.dx - (self.width >> 1)
        bottom = y + self.dy + 1
        return left, bottom - self.height, left + self.width, bottom

    def footprint(self, x, y):
        """Set of opaque screen pixels the cel covers when placed at posn (x,y)."""
        left, top, _, _ = self.rect(x, y)
        pts = set()
        for cy in range(self.height):
            base = cy * self.width
            for cx in range(self.width):
                if self.pix[base + cx] != self.clearKey:
                    sx, sy = left + cx, top + cy
                    if 0 <= sx < W and 0 <= sy < H:
                        pts.add((sx, sy))
        return pts


def _decode_cel(d, off):
    c = Cel()
    c.width = d[off] | (d[off + 1] << 8)
    c.height = d[off + 2] | (d[off + 3] << 8)
    c.dx = d[off + 4] - 256 if d[off + 4] >= 128 else d[off + 4]   # signed
    c.dy = d[off + 5]
    c.clearKey = d[off + 6]
    n = c.width * c.height
    pix = bytearray(n)
    p = off + 7
    i = 0
    while i < n:
        b = d[p]; p += 1
        run = b >> 4
        col = b & 0x0F
        end = min(i + run, n)
        for k in range(i, end):
            pix[k] = col
        i += run
    c.pix = pix
    return c


def _u16(d, o):
    return d[o] | (d[o + 1] << 8)


def _i16(d, o):
    v = _u16(d, o)
    return v - 0x10000 if v >= 0x8000 else v


def _u32(d, o):
    return int.from_bytes(bytes(d[o:o + 4]), "little")


def _is_sci11_view(d):
    """SCI1.1 views begin with `headerSize-2`; SCI0's first byte is the loop COUNT.

    Told apart structurally: for SCI1.1 the header size is at least 16 and its loop/cel entry
    sizes (bytes 12 and 13) are at least 16 and 32 -- ScummVM asserts exactly those three, which
    makes them a recogniser as well as a sanity check. An SCI0 view has a small loop count there
    and arbitrary bytes at 12/13, so it does not accidentally satisfy all of them."""
    return (len(d) > 16 and _u16(d, 0) + 2 >= 16 and d[2] > 0
            and d[12] >= 16 and d[13] >= 32)


def _decode_cel_sci11(d, off, celSize):
    """One SCI1.1 cel: a 32+ byte descriptor plus TWO streams -- a run/skip control stream and a
    literal pixel stream (`unpackCelData`, ViewType kViewVga11)."""
    c = Cel()
    c.width, c.height = _i16(d, off), _i16(d, off + 2)
    c.dx, c.dy = _i16(d, off + 4), _i16(d, off + 6)
    if c.dy < 0:
        c.dy += 255                      # Sierra's own adjustment in the SCI1.1 getCelRect
    c.clearKey = d[off + 8]
    rle, lit = _u32(d, off + 24), _u32(d, off + 28)
    if rle and not lit:                  # uncompressed content stores the stream in the other slot
        rle, lit = lit, rle
    n = c.width * c.height
    pix = bytearray([c.clearKey]) * n
    if not rle:                          # no control stream: the cel is raw pixels
        pix[:n] = bytes(d[lit:lit + n])
    else:
        p, q, i = rle, lit, 0
        while i < n and p < len(d):
            b = d[p]; p += 1
            run = b & 0x3F
            kind = b & 0xC0
            if kind == 0x40:             # a copy run of 64..127 -- then fall into the copy case
                run += 64
                kind = 0x00
            if kind == 0x00:             # copy `run` literal pixels
                src = q if lit else p
                take = min(run, n - i)
                pix[i:i + take] = bytes(d[src:src + take])
                if lit:
                    q += run
                else:
                    p += run
            elif kind == 0x80:           # fill `run` pixels with one colour
                col = d[q] if lit else d[p]
                if lit:
                    q += 1
                else:
                    p += 1
                for k in range(i, min(i + run, n)):
                    pix[k] = col
            # 0xC0 = skip, leaving the clear colour already in place
            i += run
    c.pix = pix
    return c


def decode_view(game: Sci0Game, view_num: int):
    """Return list of loops; each loop is a dict {cels: [Cel], mirror: bool}.

    Two resource layouts, recognised (see `_is_sci11_view`) rather than declared. SCI1.1 replaced
    SCI0's offset tables with fixed-stride loop and cel records whose strides are in the header,
    and its cels carry two data streams instead of one nibble-RLE stream."""
    d = game.get(VIEW, view_num)
    if _is_sci11_view(d):
        headerSize = _u16(d, 0) + 2
        loopCount, loopSize, celSize = d[2], d[12], d[13]
        loops = []
        for L in range(loopCount):
            lo = headerSize + L * loopSize
            mirror = d[lo] != 255
            seen = set()
            while d[lo] != 255:          # a mirrored loop points at the one it copies
                seek = d[lo]
                if seek >= loopCount or seek in seen:
                    break                # a cycle would hang the walk; ScummVM errors, we stop
                seen.add(seek)
                lo = headerSize + seek * loopSize
            celCount = d[lo + 2]
            base = _u32(d, lo + 12)
            loops.append({"cels": [_decode_cel_sci11(d, base + c * celSize, celSize)
                                   for c in range(celCount)],
                          "mirror": mirror})
        return loops
    loopCount = d[0]
    mirrorBits = d[2] | (d[3] << 8)
    loops = []
    for L in range(loopCount):
        loopOff = d[8 + L * 2] | (d[8 + L * 2 + 1] << 8)
        celCount = d[loopOff] | (d[loopOff + 1] << 8)
        cels = []
        for cn in range(celCount):
            co = d[loopOff + 4 + cn * 2] | (d[loopOff + 4 + cn * 2 + 1] << 8)
            cels.append(_decode_cel(d, co))
        loops.append({"cels": cels, "mirror": bool((mirrorBits >> L) & 1)})
    return loops
