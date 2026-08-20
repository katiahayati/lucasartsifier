"""S-expression reader for decompiled Sierra Script (.sc) files.

The decompiled sources (sluicebox / SCICompanion syntax) are Lisp-like. This
reader turns a .sc file into nested Python lists of typed atoms. We deliberately
keep it faithful to *lexical* structure and let a later pass (sci_model.py)
impose meaning (classes, methods, message sends, guards, effects).

Atom types:
  Sym      - a symbol/identifier/operator, incl. selectors written `foo:`
             (trailing colon preserved) and keyword args written `#foo`.
  int      - a number (decimal, negative, or $hex)
  Str      - a brace string literal  {like this}   (message text; usually discarded)
  Said     - a parser Said spec       'get/lotion'  (kept raw; the effect is what
             matters, the string is dropped downstream per the plan)

Lists are plain Python lists. Comments (`;` to end of line) are dropped, except
they never terminate inside a {..} or '..' literal.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Sym:
    name: str

    def __repr__(self) -> str:
        return self.name

    def is_selector(self) -> bool:
        return self.name.endswith(":")

    @property
    def sel(self) -> str:
        """Selector name without the trailing colon."""
        return self.name[:-1] if self.name.endswith(":") else self.name


@dataclass(frozen=True)
class Str:
    text: str

    def __repr__(self) -> str:
        return "{%s}" % self.text


@dataclass(frozen=True)
class Said:
    spec: str

    def __repr__(self) -> str:
        return "'%s'" % self.spec


class SexprError(Exception):
    pass


_DELIMS = "(){}';\""
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_WS = " \t\r\n\f"


class _Lexer:
    def __init__(self, text: str, filename: str = "<str>"):
        self.s = text
        self.n = len(text)
        self.i = 0
        self.filename = filename

    def tokens(self):
        s, n = self.s, self.n
        while self.i < n:
            c = s[self.i]
            if c in _WS:
                self.i += 1
                continue
            if c == ";":  # line comment
                nl = s.find("\n", self.i)
                self.i = n if nl < 0 else nl + 1
                continue
            if c == "(":
                self.i += 1
                yield ("(", None)
                continue
            if c == ")":
                self.i += 1
                yield (")", None)
                continue
            if c == "{":  # brace string, honoring backslash escapes
                yield ("atom", self._read_delimited("{", "}", Str))
                continue
            if c == '"':  # EricOakford-dialect double-quote string, e.g. name "Magic Hen"
                yield ("atom", self._read_delimited('"', '"', Str))
                continue
            if c == "'":  # Said spec (opaque: may contain parens, commas, slashes)
                yield ("atom", self._read_delimited("'", "'", Said))
                continue
            # bare atom: read until whitespace or a structural delimiter
            j = self.i
            while j < n and s[j] not in _WS and s[j] not in _DELIMS:
                j += 1
            if j == self.i:  # at an unhandled delimiter (e.g. a stray '}'): skip it, never spin
                self.i += 1
                continue
            raw = s[self.i:j]
            self.i = j
            # `ownedBy:self` -- a selector and its argument with no space between.
            # SCI's compiler does not care; our reader did, silently. Reading to the
            # next whitespace made one Sym named "ownedBy:self", which `is_selector()`
            # rejects (it does not END with ':'), so the message send simply was not
            # there. 155 sites in KQ4, 12 in LSL2 -- including `Actor::has` itself:
            #     (= theItem (inventory at:what))
            #     (return (and theItem (theItem ownedBy:self)))
            # i.e. the definition of possession, unreadable on a whitespace
            # convention. Split it: the colon is the selector marker, not part of a
            # name.
            head, sep, rest = raw.partition(":")
            if sep and rest and _IDENT.match(head):
                yield ("atom", Sym(head + ":"))
                yield ("atom", self._classify(rest))
                continue
            yield ("atom", self._classify(raw))

    def _read_delimited(self, open_c: str, close_c: str, ctor):
        s, n = self.s, self.n
        assert s[self.i] == open_c
        self.i += 1  # consume opener
        start = self.i
        buf = []
        while self.i < n:
            c = s[self.i]
            if c == "\\" and self.i + 1 < n:  # escape: keep next char verbatim
                buf.append(s[self.i + 1])
                self.i += 2
                continue
            if c == close_c:
                self.i += 1  # consume closer
                return ctor("".join(buf))
            buf.append(c)
            self.i += 1
        raise SexprError(f"unterminated {open_c}..{close_c} literal at {self.filename} "
                         f"(started offset {start})")

    @staticmethod
    def _classify(raw: str):
        # numbers: decimal, negative decimal, or $hex
        if raw and (raw[0].isdigit() or (raw[0] == "-" and raw[1:2].isdigit())):
            try:
                return int(raw, 10)
            except ValueError:
                pass
        if raw.startswith("$"):
            try:
                return int(raw[1:], 16)
            except ValueError:
                pass
        return Sym(raw)


def read_all(text: str, filename: str = "<str>") -> list:
    """Parse a whole file, returning the list of top-level forms."""
    lx = _Lexer(text, filename)
    stack = [[]]  # stack[0] is the top-level form list
    for kind, val in lx.tokens():
        if kind == "(":
            new = []
            stack[-1].append(new)
            stack.append(new)
        elif kind == ")":
            if len(stack) == 1:
                raise SexprError(f"unbalanced ')' in {filename}")
            stack.pop()
        else:  # atom
            stack[-1].append(val)
    if len(stack) != 1:
        raise SexprError(f"unbalanced '(' in {filename} (depth {len(stack) - 1} at EOF)")
    return stack[0]


def read_file(path: str) -> list:
    with open(path, "r", encoding="latin-1") as f:
        return read_all(f.read(), path)


# --- WHAT IS NOT CODE, in one place ------------------------------------------------------------
#
# The reader above tokenises; the PATCHER and the TRIGGER placement layer do not -- they compute
# spans by walking raw source text, because a guard is inserted into bytes and has to come back
# out as bytes. Both therefore need the same answer to one question: is this offset really code?
# They each grew their own answer, and the 2026-08-20 review found what that costs -- one of them
# filtered its span walk and not the scan that fed it (R1), and the other filtered its span walk
# and not its region search at all (live on KQ6 and LB2). One rule, one home, two importers
# ([[same-rule-two-places]]).

def skip_noncode(text, j, end):
    """If `text[j]` opens a comment or a quoted form, the offset just past it; else None.

    Four constructs look like code and are not, and the taxonomy matters because only one of them
    carries parens in this corpus. Measured 2026-08-20 across the five source trees:

      * `;` LINE COMMENTS -- everywhere, and they eat to end of line;
      * `{...}` MESSAGE TEXT -- everywhere, may span lines, free to contain a lone paren, and on
        KQ6 and LB2 free to contain WHOLE SCI SOURCE (`WriteFeature.sc` writes scripts);
      * `'...'` SAID AND MENU SPECS -- 3,100 in code position on LSL2 and KQ4, and the only
        non-code form here that legitimately carries parens (`'(get,take)/lamp'` is a grouped
        alternation). All 3,100 balance today, none contains a `;` or a `{`, and no line carries
        a stray quote -- so handling them changes not one span in the corpus. "Balanced today" is
        a fact about these five games, not a property of the arithmetic;
      * `"..."` -- DEAD. Every double quote in the corpus is inside a `{...}` message, which is
        consumed above it. Kept, line-bounded, for a decompiler that emits one.

    The quoted forms are bounded to their own LINE, so an unterminated one is an ordinary
    character rather than a skip that runs to the end of the file -- or, in the inline copy this
    replaced in `trigger`, a `find` returning -1, an index of 0, and a walk that restarts from
    the top of the file forever. Every `'...'` in the corpus is on one line, measured: no line
    carries a stray quote."""
    c = text[j]
    if c == ";":
        k = text.find("\n", j)
        return end if k < 0 else min(k + 1, end)
    if c == "{":
        k = text.find("}", j + 1)
        return end if k < 0 else min(k + 1, end)
    if c in "'\"":
        nl = text.find("\n", j + 1)
        stop = end if nl < 0 else min(nl, end)
        k = j + 1
        while k < stop and text[k] != c:
            k += 2 if text[k] == "\\" else 1
        return min(k + 1, end) if k < stop else None
    return None


def noncode_spans(text):
    """Every `(start, end)` in `text` that `skip_noncode` consumes whole, in order.

    One linear pass, so a scanner can ask "is this match really code?" by bisection rather than
    re-deriving the answer per candidate."""
    out, j, n = [], 0, len(text)
    while j < n:
        nxt = skip_noncode(text, j, n)
        if nxt is not None:
            out.append((j, nxt))
            j = max(nxt, j + 1)
            continue
        j += 1
    return out


def code_finditer(text, pattern, spans=None):
    """`re.finditer`, minus every match that STARTS inside a comment or a quoted form.

    ⛔ THE SCAN AND THE SPAN WALK MUST AGREE. Filtering one half of a two-half arithmetic is not
    a fix: `patcher._enclosing_if_test` skipped strings when it measured a span and not when it
    chose which span to measure, so an `(if` written inside a message was picked as the arming
    and the demand was written into the message -- with the placement row reporting
    `applied: True`. `trigger._find_region` had the same shape and a live instance."""
    import bisect
    if spans is None:
        spans = noncode_spans(text)
    starts = [s for (s, _e) in spans]
    for m in re.finditer(pattern, text):
        i = bisect.bisect_right(starts, m.start()) - 1
        if i >= 0 and m.start() < spans[i][1]:
            continue
        yield m


def code_search(text, pattern, spans=None):
    """The first match of `pattern` that is really code, or None -- `re.search`'s replacement
    wherever a raw first-match-wins scan chooses a region to rewrite."""
    return next(code_finditer(text, pattern, spans), None)
