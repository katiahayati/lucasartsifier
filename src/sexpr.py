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


_DELIMS = "(){}';"
_WS = " \t\r\n\f"


class _Lexer:
    def __init__(self, text: str, filename: str = "<str>"):
        self.s = text
        self.n = len(text)
        self.i = 0
        self.filename = filename

    def _pos(self) -> str:
        line = self.s.count("\n", 0, self.i) + 1
        col = self.i - (self.s.rfind("\n", 0, self.i))
        return f"{self.filename}:{line}:{col}"

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
            if c == "'":  # Said spec (opaque: may contain parens, commas, slashes)
                yield ("atom", self._read_delimited("'", "'", Said))
                continue
            # bare atom: read until whitespace or a structural delimiter
            j = self.i
            while j < n and s[j] not in _WS and s[j] not in _DELIMS:
                j += 1
            raw = s[self.i:j]
            self.i = j
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
