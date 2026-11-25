"""Reading OpenSCAD files as bodies (PLAN item 101). No Qt here.

The constructive part of the language is read and built with the kernel:

* solids: cube, sphere, cylinder (r, d, r1/r2, d1/d2, center), polyhedron;
* flat shapes: square, circle, polygon (with holes through ``paths``), turned into solids by
  linear_extrude (height, center, scale) and rotate_extrude (angle);
* transforms: translate, rotate (angles or angle about an axis), scale, mirror, multmatrix,
  resize is not read; color and render pass their children on;
* union, difference, intersection (and the implicit union of a block);
* variables, arithmetic, vectors, ranges, comparisons, ``? :``, the usual maths functions (degrees,
  as in OpenSCAD), ``for`` and ``if`` / ``else``, and modules and functions the file defines.

Each top-level object is one body. hull, minkowski, offset, text, import and surface are not read:
the error names the line.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

import numpy as np


class ScadError(Exception):
    pass


# ---- reading the text ------------------------------------------------------------------------

_TOKEN = re.compile(r"""
    (?P<ws>\s+|//[^\n]*|/\*.*?\*/)
  | (?P<num>(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)
  | (?P<str>"(?:[^"\\]|\\.)*")
  | (?P<id>\$?[A-Za-z_][A-Za-z0-9_]*)
  | (?P<op>==|!=|<=|>=|&&|\|\||[-+*/%^<>!?:;,=(){}\[\]#.])
""", re.S | re.X)


@dataclass
class Tok:
    kind: str
    text: str
    line: int


def tokens(src: str) -> list[Tok]:
    out, i, line = [], 0, 1
    while i < len(src):
        m = _TOKEN.match(src, i)
        if not m:
            raise ScadError(f"line {line}: cannot read {src[i:i + 12]!r}")
        kind = m.lastgroup
        if kind != "ws":
            out.append(Tok(kind, m.group(), line))
        line += m.group().count("\n")
        i = m.end()
    out.append(Tok("end", "", line))
    return out


# ---- the tree ----------------------------------------------------------------------------------

@dataclass
class Call:  # a module call: name(args) child or { children }
    name: str
    args: list  # [(name or None, expr)]
    children: list
    line: int


@dataclass
class Assign:
    name: str
    expr: object
    line: int


@dataclass
class For:
    vars: list  # [(name, expr)]
    body: list
    line: int


@dataclass
class If:
    cond: object
    then: list
    other: list
    line: int


@dataclass
class ModuleDef:
    name: str
    params: list  # [(name, default expr or None)]
    body: list


@dataclass
class FuncDef:
    name: str
    params: list
    expr: object


class _Parser:
    def __init__(self, toks: list[Tok]):
        self.t, self.i = toks, 0
        self.modules: dict[str, ModuleDef] = {}
        self.functions: dict[str, FuncDef] = {}

    @property
    def cur(self) -> Tok:
        return self.t[self.i]

    def take(self, text: str | None = None, kind: str | None = None) -> Tok:
        tok = self.cur
        if (text is not None and tok.text != text) or (kind is not None and tok.kind != kind):
            want = text or kind
            raise ScadError(f"line {tok.line}: expected {want!r}, found {tok.text or 'the end'!r}")
        self.i += 1
        return tok

    def at(self, text: str) -> bool:
        return self.cur.text == text and self.cur.kind in ("op", "id")

    # statements
    def statements(self, until: str = "") -> list:
        out = []
        while not (until and self.at(until)) and self.cur.kind != "end":
            st = self.statement()
            if st is not None:
                out.append(st)
        if until:
            self.take(until)
        return out

    def block(self) -> list:
        if self.at("{"):
            self.take("{")
            return self.statements("}")
        st = self.statement()
        return [st] if st is not None else []

    def statement(self):
        tok = self.cur
        if self.at(";"):
            self.take(";")
            return None
        if self.at("{"):
            self.take("{")
            return Call("union", [], self.statements("}"), tok.line)
        if tok.kind == "op" and tok.text in "!#%*":  # modifiers: debug marks, ignored (* drops it)
            self.take()
            st = self.statement()
            return None if tok.text == "*" else st
        if tok.kind != "id":
            raise ScadError(f"line {tok.line}: unexpected {tok.text!r}")
        if tok.text == "module":
            self.take()
            name = self.take(kind="id").text
            params = self.params()
            self.modules[name] = ModuleDef(name, params, self.block())
            return None
        if tok.text == "function":
            self.take()
            name = self.take(kind="id").text
            params = self.params()
            self.take("=")
            self.functions[name] = FuncDef(name, params, self.expr())
            self.take(";")
            return None
        if tok.text == "include" or tok.text == "use":
            raise ScadError(f"line {tok.line}: {tok.text} <file> is not read; put the file's parts in this one")
        if tok.text == "for":
            self.take()
            self.take("(")
            vs = []
            while not self.at(")"):
                name = self.take(kind="id").text
                self.take("=")
                vs.append((name, self.expr()))
                if self.at(","):
                    self.take(",")
            self.take(")")
            return For(vs, self.block(), tok.line)
        if tok.text == "if":
            self.take()
            self.take("(")
            cond = self.expr()
            self.take(")")
            then = self.block()
            other = []
            if self.at("else"):
                self.take("else")
                other = self.block()
            return If(cond, then, other, tok.line)
        # assignment or module call
        name = self.take(kind="id").text
        if self.at("="):
            self.take("=")
            e = self.expr()
            self.take(";")
            return Assign(name, e, tok.line)
        self.take("(")
        args = self.args(")")
        return Call(name, args, self.block() if not self.at(";") else (self.take(";") and []), tok.line)

    def params(self) -> list:
        self.take("(")
        out = []
        while not self.at(")"):
            name = self.take(kind="id").text
            default = None
            if self.at("="):
                self.take("=")
                default = self.expr()
            out.append((name, default))
            if self.at(","):
                self.take(",")
        self.take(")")
        return out

    def args(self, close: str) -> list:
        out = []
        while not self.at(close):
            if self.cur.kind == "id" and self.t[self.i + 1].text == "=" and self.t[self.i + 2].text != "=":
                name = self.take().text
                self.take("=")
                out.append((name, self.expr()))
            else:
                out.append((None, self.expr()))
            if self.at(","):
                self.take(",")
            elif not self.at(close):
                raise ScadError(f"line {self.cur.line}: expected ',' or {close!r}, found {self.cur.text!r}")
        self.take(close)
        return out

    # expressions: a tiny tree of tuples
    def expr(self):
        c = self.binary(0)
        if self.at("?"):
            self.take("?")
            a = self.expr()
            self.take(":")
            b = self.expr()
            return ("?", c, a, b)
        return c

    _LEVELS = [("||",), ("&&",), ("==", "!="), ("<", "<=", ">", ">="), ("+", "-"), ("*", "/", "%"), ("^",)]

    def binary(self, level: int):
        if level == len(self._LEVELS):
            return self.unary()
        left = self.binary(level + 1)
        while self.cur.kind == "op" and self.cur.text in self._LEVELS[level]:
            op = self.take().text
            left = (op, left, self.binary(level + 1))
        return left

    def unary(self):
        if self.cur.kind == "op" and self.cur.text in ("-", "+", "!"):
            op = self.take().text
            return ("neg" if op == "-" else "not" if op == "!" else "pos", self.unary())
        return self.postfix(self.primary())

    def postfix(self, e):
        while True:
            if self.at("["):
                self.take("[")
                k = self.expr()
                self.take("]")
                e = ("index", e, k)
            elif self.at(".") and self.t[self.i + 1].kind == "id":
                self.take(".")
                e = ("index", e, ("num", "xyz".index(self.take().text)))
            else:
                return e

    def primary(self):
        tok = self.cur
        if tok.kind == "num":
            self.take()
            return ("num", float(tok.text))
        if tok.kind == "str":
            self.take()
            return ("str", tok.text[1:-1])
        if self.at("("):
            self.take("(")
            e = self.expr()
            self.take(")")
            return e
        if self.at("["):
            self.take("[")
            if self.at("]"):
                self.take("]")
                return ("vec", [])
            if self.at("for"):
                raise ScadError(f"line {tok.line}: list comprehensions are not read")
            first = self.expr()
            if self.at(":"):
                self.take(":")
                second = self.expr()
                if self.at(":"):
                    self.take(":")
                    third = self.expr()
                    self.take("]")
                    return ("range", first, second, third)
                self.take("]")
                return ("range", first, ("num", 1.0), second)
            items = [first]
            while self.at(","):
                self.take(",")
                if self.at("]"):
                    break
                items.append(self.expr())
            self.take("]")
            return ("vec", items)
        if tok.kind == "id":
            self.take()
            if tok.text in ("true", "false"):
                return ("num", 1.0 if tok.text == "true" else 0.0)
            if tok.text == "undef":
                return ("undef",)
            if tok.text == "PI":
                return ("num", math.pi)
            if self.at("("):
                self.take("(")
                return ("call", tok.text, self.args(")"), tok.line)
            return ("var", tok.text, tok.line)
        raise ScadError(f"line {tok.line}: unexpected {tok.text or 'end of file'!r}")


# ---- working out values ------------------------------------------------------------------------

def _deg(f):
    return lambda x: f(math.radians(x))


_FUNCS = {
    "sin": _deg(math.sin), "cos": _deg(math.cos), "tan": _deg(math.tan),
    "asin": lambda x: math.degrees(math.asin(x)), "acos": lambda x: math.degrees(math.acos(x)),
    "atan": lambda x: math.degrees(math.atan(x)), "atan2": lambda y, x: math.degrees(math.atan2(y, x)),
    "sqrt": math.sqrt, "abs": abs, "floor": math.floor, "ceil": math.ceil, "round": round,
    "pow": pow, "exp": math.exp, "ln": math.log, "log": lambda x, b=10: math.log(x, b),
    "sign": lambda x: (x > 0) - (x < 0),
    "min": lambda *a: min(a[0]) if len(a) == 1 else min(a), "max": lambda *a: max(a[0]) if len(a) == 1 else max(a),
    "len": len, "norm": lambda v: math.sqrt(sum(c * c for c in v)),
    "concat": lambda *a: [x for v in a for x in (v if isinstance(v, list) else [v])],
    "cross": lambda a, b: list(np.cross(a, b)), "str": lambda *a: "".join(map(str, a)),
}


@dataclass
class Scope:
    vars: dict = field(default_factory=dict)
    parent: Scope | None = None

    def get(self, name: str):
        s = self
        while s is not None:
            if name in s.vars:
                return s.vars[name]
            s = s.parent
        return None


class _Eval:
    def __init__(self, parser: _Parser):
        self.p = parser

    def value(self, e, sc: Scope):
        k = e[0]
        if k == "num" or k == "str":
            return e[1]
        if k == "undef":
            return None
        if k == "var":
            v = sc.get(e[1])
            if v is None and not e[1].startswith("$"):
                raise ScadError(f"line {e[2]}: {e[1]} has no value")
            return v
        if k == "vec":
            return [self.value(x, sc) for x in e[1]]
        if k == "range":
            a, s, b = (self.value(x, sc) for x in e[1:])
            if s == 0:
                raise ScadError("a range's step cannot be 0")
            n = int(math.floor((b - a) / s + 1e-9)) + 1
            if n > 100000:
                raise ScadError("a range of more than 100000 values")
            return [a + s * i for i in range(max(0, n))]
        if k == "neg":
            v = self.value(e[1], sc)
            return [-x for x in v] if isinstance(v, list) else -v
        if k == "pos":
            return self.value(e[1], sc)
        if k == "not":
            return 0.0 if self.value(e[1], sc) else 1.0
        if k == "?":
            return self.value(e[2] if self.value(e[1], sc) else e[3], sc)
        if k == "index":
            v, i = self.value(e[1], sc), self.value(e[2], sc)
            try:
                return v[int(i)]
            except (IndexError, TypeError):
                return None
        if k == "call":
            return self.call(e, sc)
        a, b = self.value(e[1], sc), self.value(e[2], sc)
        return _binop(k, a, b)

    def call(self, e, sc: Scope):
        _, name, args, line = e
        vals = [(n, self.value(x, sc)) for n, x in args]
        if name in self.p.functions:
            f = self.p.functions[name]
            inner = Scope(parent=sc)
            bind(f.params, vals, inner, self, sc)
            return self.value(f.expr, inner)
        fn = _FUNCS.get(name)
        if fn is None:
            raise ScadError(f"line {line}: unknown function {name}()")
        try:
            return fn(*[v for _, v in vals])
        except (TypeError, ValueError) as exc:
            raise ScadError(f"line {line}: {name}(): {exc}") from None


def _binop(op, a, b):
    if op in ("+", "-") and isinstance(a, list) and isinstance(b, list):
        return [x + y if op == "+" else x - y for x, y in zip(a, b)]
    if op == "*" and isinstance(a, list) and not isinstance(b, list):
        return [x * b for x in a]
    if op == "*" and isinstance(b, list) and not isinstance(a, list):
        return [a * x for x in b]
    if op == "*" and isinstance(a, list) and isinstance(b, list):
        return float(np.dot(np.array(a, float), np.array(b, float))) if not isinstance(a[0], list) else \
            np.array(a, float).dot(np.array(b, float)).tolist()
    if op == "/" and isinstance(a, list):
        return [x / b for x in a]
    ops = {"+": lambda: a + b, "-": lambda: a - b, "*": lambda: a * b, "/": lambda: a / b, "%": lambda: math.fmod(a, b),
           "^": lambda: a ** b, "==": lambda: float(a == b), "!=": lambda: float(a != b), "<": lambda: float(a < b),
           "<=": lambda: float(a <= b), ">": lambda: float(a > b), ">=": lambda: float(a >= b),
           "&&": lambda: float(bool(a) and bool(b)), "||": lambda: float(bool(a) or bool(b))}
    try:
        return ops[op]()
    except (TypeError, ZeroDivisionError) as exc:
        raise ScadError(f"cannot work out {op}: {exc}") from None


def bind(params, vals, inner: Scope, ev: _Eval, outer: Scope) -> None:
    """Arguments into a module's or function's own scope: by position, then by name, else default."""
    names = [n for n, _ in params]
    k = 0
    for n, v in vals:
        if n is None:
            if k < len(names):
                inner.vars[names[k]] = v
            k += 1
        else:
            inner.vars[n] = v
    for n, d in params:
        if n not in inner.vars and d is not None:
            inner.vars[n] = ev.value(d, inner)


# ---- building ----------------------------------------------------------------------------------

class Builder:
    """Shapes from the tree, with OCP. ``fn`` is the number of sides OpenSCAD would use; here round
    things are exact, so it only matters for flat polygons given as points."""

    def __init__(self, parser: _Parser):
        self.p = parser
        self.ev = _Eval(parser)
        self.counts: dict[str, int] = {}

    def run(self, stmts: list) -> list:
        return self.objects(stmts, Scope(vars={"$fn": 0.0, "$fa": 12.0, "$fs": 2.0}))

    def objects(self, stmts: list, sc: Scope) -> list:
        # OpenSCAD: assignments in a block apply to the whole block (the last one wins)
        local = Scope(parent=sc)
        for st in stmts:
            if isinstance(st, Assign):
                local.vars[st.name] = None
        for st in stmts:
            if isinstance(st, Assign):
                local.vars[st.name] = self.ev.value(st.expr, local)
        out = []
        for st in stmts:
            if isinstance(st, Call):
                out += self.call(st, local)
            elif isinstance(st, For):
                out += self.loop(st, st.vars, local)
            elif isinstance(st, If):
                out += self.objects(st.then if self.ev.value(st.cond, local) else st.other, local)
        return out

    def loop(self, st: For, vs: list, sc: Scope) -> list:
        if not vs:
            return self.objects(st.body, sc)
        name, e = vs[0]
        seq = self.ev.value(e, sc)
        if not isinstance(seq, list):
            seq = [seq]
        out = []
        for v in seq:
            inner = Scope({name: v}, sc)
            out += self.loop(st, vs[1:], inner)
        return out

    def call(self, c: Call, sc: Scope) -> list:
        vals = [(n, self.ev.value(x, sc)) for n, x in c.args]
        named = {n: v for n, v in vals if n}
        pos = [v for n, v in vals if n is None]

        def arg(name, i, default=None):
            if name in named:
                return named[name]
            return pos[i] if i < len(pos) else default

        kids = lambda: self.objects(c.children, sc)  # noqa: E731
        name = c.name
        self.counts[name] = self.counts.get(name, 0) + 1
        try:
            if name in self.p.modules:
                m = self.p.modules[name]
                inner = Scope(parent=sc)
                bind(m.params, vals, inner, self.ev, sc)
                inner.vars["$children"] = float(len(c.children))
                self._children_stack.append((c.children, sc))
                try:
                    return self.objects(m.body, inner)
                finally:
                    self._children_stack.pop()
            if name == "children":
                if not self._children_stack:
                    return []
                ch, csc = self._children_stack[-1]
                k = arg("index", 0)
                if k is None:
                    return self.objects(ch, csc)
                calls = [s for s in ch if isinstance(s, (Call, For, If))]
                return self.objects([calls[int(k)]], csc) if 0 <= int(k) < len(calls) else []
            from . import scad_build as sb

            return sb.build(name, arg, named, kids, c.line)
        except ScadError:
            raise
        except sb_errors() as exc:
            raise ScadError(f"line {c.line}: {name}: {exc}") from None

    _children_stack: list = []


def sb_errors():
    from . import scad_build as sb

    return (sb.BuildError,)


def read(src: str) -> tuple[list, dict[str, int]]:
    """The file's top-level objects as shapes, and how many of each call it made."""
    pr = _Parser(tokens(src))
    tree = pr.statements()
    b = Builder(pr)
    b._children_stack = []
    shapes = b.run(tree)
    return shapes, b.counts
