"""Render a calc.py function as a readable equation (HTML fragment + plain text) built from its AST.

Pure, deterministic, stdlib only: no exec, no network, no JS, no fonts. Inline CSS only.
Display only: nothing here is committed or stamped.

Public API
    render(func_source_or_ast, name, inputs=None, examples=None, fn=None) -> Rendered
    render_part(path) -> list[Rendered]      (public functions of one calc.py, file order; ast only)
    validate(rendered, fn, namespace, samples=()) -> list[str]   (evaluates expr_py against the real function)

Rendered.status: math (one expression, guards allowed), cases (if/else returns or conditional expression),
source_only (anything not supported, e.g. for-loops, f-strings that build text), failed (renderer error or, after
validate(), a mismatch with the real function).
Rendered.kind: ds | algebra | engineering | helper, from the docstring cite prefix.
Rendered.expr_py: plain Python expression from the render's own tree, with local assignments substituted. It uses
the argument names, `math`, and the module's own functions and constants; a branch that can only raise is written
`_error("...")` (validate() supplies it). Guards (raise ifs) are NOT part of expr_py; they are listed in `guards`.
Parenthesization comes from the tree and Python precedence, never from layout. Float literals are printed as
written value (no SI prefixing): 49.4e3 -> 49400, 1e-6 -> 1 x 10^-6.
"""
import ast
import html as _html
import math
import re
from dataclasses import dataclass, field

# precedence levels (py / text). Html has its own hp because fractions, radicals and bars are visually atomic.
OR, AND, NOT, CMP, ADD, MUL, UNARY, POW, ATOM = 1, 2, 3, 4, 6, 7, 8, 9, 10


class Unsupported(Exception):
    pass


@dataclass
class Rendered:
    name: str
    kind: str = "engineering"
    status: str = "failed"
    html: str = ""
    text: str = ""
    expr_py: str = ""
    where: list = field(default_factory=list)
    guards: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    args: list = field(default_factory=list)
    doc: str = ""
    samples_checked: int = 0


class N:
    """One rendered sub-expression: html, text, py strings plus precedence of each."""
    def __init__(self, h, t, p, pp=ATOM, hp=None):
        self.h, self.t, self.p, self.pp = h, t, p, pp
        self.hp = pp if hp is None else hp
        self.cases = None  # (rows, other) when this node is a cases block


def _e(s):
    return _html.escape(str(s), quote=False)


def _wrap(n, minp):
    """(html, text, py) of n, parenthesized when its precedence is below minp."""
    h = n.h if n.hp >= minp else "(" + n.h + ")"
    t = n.t if n.pp >= minp else "(" + n.t + ")"
    p = n.p if n.pp >= minp else "(" + n.p + ")"
    return h, t, p


def _num(v):
    """(html, text, py) for a numeric literal. No SI prefix; exponent form only when %.12g uses one."""
    if isinstance(v, bool) or v is None or isinstance(v, str):
        return _e(repr(v)), repr(v), repr(v)
    py = repr(v)
    if isinstance(v, int):
        return str(v), str(v), py
    s = "%.12g" % v
    m = re.fullmatch(r"(-?[0-9.]+)e([+-])0*([0-9]+)", s)
    if m:
        ex = ("-" if m.group(2) == "-" else "") + m.group(3)
        mant = m.group(1)
        if mant == "1":
            return "10<sup>%s</sup>" % ex, "10^%s" % ex, py
        return "%s &times; 10<sup>%s</sup>" % (mant, ex), "%s*10^%s" % (mant, ex), py
    return s, s, py


_CMP = {ast.Lt: ("<", "&lt;", "<"), ast.LtE: ("<=", "&le;", "<="), ast.Gt: (">", "&gt;", ">"),
        ast.GtE: (">=", "&ge;", ">="), ast.Eq: ("==", "=", "="), ast.NotEq: ("!=", "&ne;", "!="),
        ast.In: ("in", "&isin;", "in"), ast.NotIn: ("not in", "&notin;", "not in"),
        ast.Is: ("is", "is", "is")}
_FUNCS_PLAIN = {"math.sin": "sin", "math.cos": "cos", "math.tan": "tan", "math.asin": "asin",
                "math.acos": "acos", "math.atan": "atan", "math.atan2": "atan2", "math.exp": "exp",
                "math.log": "ln", "math.floor": "floor", "math.ceil": "ceil", "math.hypot": "hypot",
                "math.sinh": "sinh", "math.cosh": "cosh", "math.tanh": "tanh", "min": "min", "max": "max",
                "round": "round", "math.fabs": "abs", "math.radians": "radians", "math.degrees": "degrees"}


def _dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        d = _dotted(node.value)
        return d + "." + node.attr if d else None
    return None


class _Conv:
    """AST -> N. subst=True replaces local assignments by their expressions (used only for expr_py)."""

    def __init__(self, subst):
        self.subst = subst
        self.env = {}
        self.where = []      # (name, N) in assignment order (display pass)
        self.guards = []     # (conds, message) (display pass)

    # ---- expressions
    def expr(self, node):
        m = getattr(self, "e_" + type(node).__name__, None)
        if m is None:
            raise Unsupported("expression %s" % type(node).__name__)
        return m(node)

    def e_Constant(self, n):
        v = n.value
        if isinstance(v, (int, float, bool)) or v is None:
            h, t, p = _num(v)
            return N(h, t, p)
        raise Unsupported("string constant in expression")

    def e_Name(self, n):
        if self.subst and n.id in self.env:
            sub = self.env[n.id]
            return N(sub.h, sub.t, sub.p, sub.pp, sub.hp)
        return N("<i>%s</i>" % _e(n.id), n.id, n.id)

    def e_Attribute(self, n):
        d = _dotted(n)
        if d == "math.pi":
            return N("&pi;", "pi", "math.pi")
        if d is None:
            raise Unsupported("attribute access")
        return N(_e(d), d, d)

    def e_UnaryOp(self, n):
        o = self.expr(n.operand)
        if isinstance(n.op, ast.Not):
            h, t, p = _wrap(o, NOT)
            return N("not " + h, "not " + t, "not " + p, NOT)
        sign = {ast.USub: "-", ast.UAdd: "+"}.get(type(n.op))
        if sign is None:
            raise Unsupported("unary op")
        h, t, p = _wrap(o, UNARY)
        return N(("&minus;" if sign == "-" else "+") + h, sign + t, sign + p, UNARY)

    def e_BinOp(self, n):
        op = type(n.op)
        l, r = self.expr(n.left), self.expr(n.right)
        if op is ast.Div:
            lh, lt, lp = _wrap(l, MUL)
            rh, rt, rp = _wrap(r, MUL + 1)
            frac = ('<span style="display:inline-block;vertical-align:middle;text-align:center">'
                    '<span style="display:block;padding:0 .3em;border-bottom:1px solid">%s</span>'
                    '<span style="display:block;padding:0 .3em">%s</span></span>' % (l.h, r.h))
            return N(frac, "%s / %s" % (lt, rt), "%s / %s" % (lp, rp), MUL, ATOM)
        if op is ast.Pow:
            if isinstance(n.right, ast.Constant) and n.right.value == 0.5 and not isinstance(n.right.value, bool):
                return N(self._radical(l.h), "sqrt(%s)" % l.t, "%s ** 0.5" % _wrap(l, POW + 1)[2], POW, ATOM)
            bh, bt, bp = _wrap(l, POW + 1)
            _, et, ep = _wrap(r, UNARY)
            return N("%s<sup>%s</sup>" % (bh, r.h), "%s^%s" % (bt, _wrap(r, UNARY)[1]), "%s ** %s" % (bp, ep), POW)
        sym = {ast.Add: (" + ", " + ", ADD, ADD + 1, ADD), ast.Sub: (" &minus; ", " - ", ADD, ADD + 1, ADD),
               ast.Mult: (" &middot; ", " * ", MUL, MUL + 1, MUL), ast.FloorDiv: (" // ", " // ", MUL, MUL + 1, MUL),
               ast.Mod: (" mod ", " % ", MUL, MUL + 1, MUL)}.get(op)
        if sym is None:
            raise Unsupported("binary op %s" % op.__name__)
        hs, ts, lm, rm, prec = sym
        lh, lt, lp = _wrap(l, lm)
        rh, rt, rp = _wrap(r, rm)
        tt = " mod " if op is ast.Mod else ts
        return N(lh + hs + rh, lt + tt + rt, lp + ts + rp, prec)

    @staticmethod
    def _radical(inner_h):
        return ('<span style="white-space:nowrap">&radic;<span style="border-top:1px solid;padding:0 2px">%s'
                "</span></span>" % inner_h)

    def e_BoolOp(self, n):
        word = "and" if isinstance(n.op, ast.And) else "or"
        prec = AND if word == "and" else OR
        parts = [_wrap(self.expr(v), prec + 1) for v in n.values]
        j = " %s " % word
        return N(j.join(p[0] for p in parts), j.join(p[1] for p in parts), j.join(p[2] for p in parts), prec)

    def e_Compare(self, n):
        items = [self.expr(n.left)] + [self.expr(c) for c in n.comparators]
        hh, tt, pp = [_wrap(items[0], CMP + 1)[0]], [_wrap(items[0], CMP + 1)[1]], [_wrap(items[0], CMP + 1)[2]]
        for op, it in zip(n.ops, items[1:]):
            sp, sh, st = _CMP[type(op)]
            h, t, p = _wrap(it, CMP + 1)
            hh += [sh, h]
            tt += [st, t]
            pp += [sp, p]
        return N(" ".join(hh), " ".join(tt), " ".join(pp), CMP)

    def e_Tuple(self, n):
        items = [self.expr(x) for x in n.elts]
        tail = "," if len(items) == 1 else ""
        return N("(" + ", ".join(i.h for i in items) + tail + ")", "(" + ", ".join(i.t for i in items) + tail + ")",
                 "(" + ", ".join(i.p for i in items) + tail + ")")

    def e_IfExp(self, n):
        return self._cases([(self.expr(n.test), self.expr(n.body))], self.expr(n.orelse))

    def e_Call(self, n):
        if n.keywords or any(isinstance(a, ast.Starred) for a in n.args):
            raise Unsupported("call with keywords or star args")
        fname = _dotted(n.func)
        if fname is None:
            raise Unsupported("call of a non-name")
        args = [self.expr(a) for a in n.args]
        if fname in ("abs", "math.fabs") and len(args) == 1:
            a = args[0]
            return N("|%s|" % a.h, "abs(%s)" % a.t, "abs(%s)" % a.p)
        if fname == "math.sqrt" and len(args) == 1:
            a = args[0]
            return N(self._radical(a.h), "sqrt(%s)" % a.t, "math.sqrt(%s)" % a.p)
        if fname == "math.log10" and len(args) == 1:
            a = args[0]
            return N("log<sub>10</sub>(%s)" % a.h, "log10(%s)" % a.t, "math.log10(%s)" % a.p)
        if fname == "math.log" and len(args) == 1:
            a = args[0]
            return N("ln(%s)" % a.h, "ln(%s)" % a.t, "math.log(%s)" % a.p)
        shown = _FUNCS_PLAIN.get(fname, fname)
        return N("%s(%s)" % (_e(shown), ", ".join(a.h for a in args)),
                 "%s(%s)" % (shown, ", ".join(a.t for a in args)),
                 "%s(%s)" % (fname, ", ".join(a.p for a in args)))

    def _cases(self, rows, other):
        """rows: [(cond N, value N)]; other: value N or None (a branch that only raises)."""
        trs, tl, py = [], [], None
        cell = 'style="padding:.1em .5em;text-align:left"'
        for c, v in rows:
            trs.append("<tr><td %s>%s</td><td %s>if %s</td></tr>" % (cell, v.h, cell, c.h))
            tl.append("%s  if %s" % (v.t, c.t))
        if other is not None:
            trs.append("<tr><td %s>%s</td><td %s>otherwise</td></tr>" % (cell, other.h, cell))
            tl.append("%s  otherwise" % other.t)
        else:
            trs.append("<tr><td %s><i>error</i></td><td %s>otherwise</td></tr>" % (cell, cell))
            tl.append("error  otherwise")
        py = _wrap(other, 0)[2] if other is not None else '_error("no branch applies")'
        for c, v in reversed(rows):
            py = "(%s if %s else %s)" % (_wrap(v, 0)[2], c.p, py)
        h = ('<span style="display:inline-flex;align-items:center;vertical-align:middle">'
             '<span style="font-size:2.6em;font-weight:100;line-height:1">{</span>'
             '<table style="border-collapse:collapse;display:inline-table">%s</table></span>' % "".join(trs))
        node = N(h, "{ " + " ; ".join(tl) + " }", py, ATOM)
        node.cases = (rows, other)
        return node

    # ---- statements
    def block(self, stmts, path):
        env_saved = dict(self.env)
        try:
            return self._block(stmts, path)
        finally:
            self.env = env_saved

    def _cond_text(self, path):
        parts = []
        for c, neg in path:
            parts.append(("not (%s)" % c.t) if neg else c.t)
        return " and ".join(parts)

    def _block(self, stmts, path):
        for i, s in enumerate(stmts):
            if isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant) and isinstance(s.value.value, str):
                continue
            if isinstance(s, ast.Assign):
                if len(s.targets) != 1 or not isinstance(s.targets[0], ast.Name):
                    raise Unsupported("assignment to a non-name target")
                name = s.targets[0].id
                val = self.expr(s.value)
                if self.subst:
                    self.env[name] = val
                else:
                    for w, wn in self.where:
                        if w == name and wn.t != val.t:
                            raise Unsupported("name %s assigned twice" % name)
                    if not any(w == name for w, _ in self.where):
                        self.where.append((name, val))
                    self.env[name] = None
                continue
            if isinstance(s, ast.Return):
                if s.value is None:
                    raise Unsupported("bare return")
                return self.expr(s.value)
            if isinstance(s, ast.Raise):
                self._guard(path, s)
                return None
            if isinstance(s, ast.If):
                cond = self.expr(s.test)
                if len(s.body) == 1 and isinstance(s.body[0], ast.Raise) and not s.orelse:
                    self._guard(path + [(cond, False)], s.body[0])
                    continue
                rows = [(cond, self.block(s.body, path + [(cond, False)]))]
                rest = s.orelse if s.orelse else stmts[i + 1:]
                other = self.block(rest, path + [(cond, True)])
                if rows[0][1] is None:
                    raise Unsupported("a case branch that only raises")
                if other is not None and other.cases:
                    rows += other.cases[0]
                    other = other.cases[1]
                return self._cases(rows, other)
            raise Unsupported("statement %s" % type(s).__name__)
        raise Unsupported("no return")

    def _guard(self, path, raise_node):
        if self.subst:
            return
        msg = ""
        exc = raise_node.exc
        if isinstance(exc, ast.Call) and exc.args:
            a = exc.args[0]
            msg = a.value if isinstance(a, ast.Constant) and isinstance(a.value, str) else ast.unparse(a)
        self.guards.append((list(path), msg))


# ---------------------------------------------------------------------------------------------------------------

def _find_func(src, name):
    if isinstance(src, ast.FunctionDef):
        return src, None
    text = None
    if isinstance(src, str):
        text = src
        tree = ast.parse(src)
    else:
        tree = src
    for n in tree.body if isinstance(tree, ast.Module) else [tree]:
        if isinstance(n, ast.FunctionDef) and n.name == name:
            return n, text
    raise KeyError("function %s not found" % name)


def classify(func):
    """kind from the docstring cite prefix (decisions3 C1)."""
    d = ast.get_docstring(func) or ""
    if func.name == "mpn" or any(isinstance(x, (ast.For, ast.While, ast.JoinedStr)) for x in _walk_noraise(func)):
        return "helper"
    if re.search(r"algebra (on|of|from)", d, re.I):
        return "algebra"
    if re.search(r"not a ds\b|docs/spec|\bSPEC\b|spec recipe", d, re.I):
        return "engineering"
    if re.search(r"\bDS\b", d):
        return "ds"
    return "engineering"


def _walk_noraise(func):
    """ast.walk over a function, skipping the messages inside raise statements."""
    stack = list(func.body)
    while stack:
        n = stack.pop()
        yield n
        if isinstance(n, ast.Raise):
            continue
        stack.extend(ast.iter_child_nodes(n))


def _signature(func):
    a = func.args
    names = [x.arg for x in a.posonlyargs + a.args + a.kwonlyargs]
    return names


def _badge(text, color):
    return ('<span style="font:600 .7em sans-serif;padding:.1em .5em;border:1px solid %s;color:%s;'
            'border-radius:.6em;margin-left:.5em">%s</span>' % (color, color, text))


_STATUS_COLOR = {"math": "#2a7", "cases": "#27a", "source_only": "#c60", "failed": "#c22"}


def render(func_source_or_ast, name, inputs=None, examples=None, fn=None):
    """Render one function. inputs: {arg: row key}; examples: EXAMPLES rows (fn name, kwargs, expected, tol, cite);
    fn: optional real callable, used only to show the value the function returns for each example."""
    r = Rendered(name=name)
    try:
        func, text = _find_func(func_source_or_ast, name)
    except Exception as ex:
        r.warnings.append("cannot find function: %s" % ex)
        return r
    r.kind = classify(func)
    r.args = _signature(func)
    doc = ast.get_docstring(func) or ""
    r.doc = doc.strip().splitlines()[0] if doc.strip() else ""
    try:
        disp, sub = _Conv(False), _Conv(True)
        node = disp.block(func.body, [])
        snode = sub.block(func.body, [])
        r.status = "cases" if node.cases is not None else "math"
        r.expr_py = snode.p
        r.where = ["%s = %s" % (n, v.t) for n, v in disp.where]
        r.guards = ["error when %s%s" % (_cond_join(c), (" (%s)" % m) if m else "") for c, m in disp.guards]
        body_h = node.h
        body_t = node.t
        where_h = ["<i>%s</i> = %s" % (_e(n), v.h) for n, v in disp.where]
        guards_h = ["error when %s%s" % (_cond_join(c, True), (" (%s)" % _e(m)) if m else "")
                    for c, m in disp.guards]
        used = _used_names(func)
        for n, _ in disp.where:
            if n not in used:
                r.warnings.append("assigned but unused: %s" % n)
    except Unsupported as ex:
        r.status = "source_only"
        r.warnings.append("not rendered as math: %s" % ex)
        src = ast.get_source_segment(text, func) if text else None
        src = src or ast.unparse(func)
        r.expr_py = ""
        r.text = src
        r.html = _card(r, None, [], [], src, inputs, examples, fn)
        return r
    except Exception as ex:  # renderer bug: report, never crash the page
        r.status = "failed"
        r.warnings.append("render error: %s: %s" % (type(ex).__name__, ex))
        return r
    lhs_t = "%s(%s) = " % (name, ", ".join(r.args))
    lines = [lhs_t + body_t]
    if r.where:
        lines.append("  where " + "; ".join(r.where))
    lines += ["  " + g for g in r.guards]
    r.text = "\n".join(lines)
    r.html = _card(r, body_h, where_h, guards_h, None, inputs, examples, fn)
    return r


def _cond_join(path, html=False):
    parts = []
    for c, neg in path:
        t = c.h if html else c.t
        parts.append(("not (%s)" % t) if neg else t)
    return " and ".join(parts) if parts else "always"


def _used_names(func):
    return {n.id for n in ast.walk(func) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}


def _card(r, body_h, where_h, guards_h, source, inputs, examples, fn):
    td = 'style="padding:.1em .6em;border:1px solid #ccc;text-align:left"'
    out = ['<div class="eqr" style="font-family:Georgia,serif;margin:.5em 0">']
    out.append('<div><b>%s</b>%s%s</div>' % (_e(r.name), _badge(r.kind, "#666"),
                                              _badge(r.status.replace("_", " "), _STATUS_COLOR.get(r.status, "#666"))))
    if r.doc:
        out.append('<div style="font-style:italic;color:#444">%s</div>' % _e(r.doc))
    if source is None:
        out.append('<div style="font-size:1.25em;margin:.4em 0"><i>%s</i>(%s) = %s</div>'
                   % (_e(r.name), _e(", ".join(r.args)), body_h))
        if where_h:
            out.append('<div style="margin-left:1em">where %s</div>' % "; ".join(where_h))
        for g in guards_h:
            out.append('<div style="margin-left:1em;color:#a40">%s</div>' % g)
    else:
        out.append('<div style="color:#c60"><b>not rendered as math: read the source</b></div>')
        out.append('<pre style="background:#f6f6f6;padding:.5em;overflow:auto">%s</pre>' % _e(source))
    for w in r.warnings:
        if not w.startswith("not rendered"):
            out.append('<div style="color:#c60">warning: %s</div>' % _e(w))
    if r.args:
        rows = []
        for a in r.args:
            b = (inputs or {}).get(a)
            rows.append("<tr><td %s>%s</td><td %s>%s</td></tr>"
                        % (td, _e(a), td, _e(b) if b else "free argument"))
        out.append('<table style="border-collapse:collapse;margin-top:.4em">'
                   "<tr><th %s>argument</th><th %s>bound row</th></tr>%s</table>" % (td, td, "".join(rows)))
    mine = [x for x in (examples or []) if x[0] == r.name]
    if not mine:
        out.append('<div style="color:#c60">no worked example</div>')
    else:
        rows = []
        for _f, kw, exp, tol, cite in mine:
            got = "not run"
            ok = ""
            if fn is not None:
                try:
                    g = fn(**kw)
                    got = "%.6g" % g
                    ok = "OK" if abs(g - exp) <= tol * abs(exp) else "FAIL"
                except Exception as ex:
                    got, ok = type(ex).__name__, "FAIL"
            rows.append("<tr><td %s>%s</td><td %s>%s</td><td %s>%s</td><td %s>%s</td><td %s>%s %s</td></tr>"
                        % (td, _e(kw), td, _e(exp), td, _e(tol), td, _e(cite), td, _e(got), ok))
        out.append('<table style="border-collapse:collapse;margin-top:.4em"><tr><th %s>arguments</th>'
                   "<th %s>expected</th><th %s>rel tol</th><th %s>cite</th><th %s>function returns</th></tr>%s</table>"
                   % (td, td, td, td, td, "".join(rows)))
    out.append("</div>")
    return "".join(out)


# ---------------------------------------------------------------------------------------------------------------

def _samples(func_names, examples_for_fn):
    """Deterministic argument sets: the EXAMPLES rows plus a few generated ones."""
    out = [dict(kw) for kw in examples_for_fn]
    for k in range(4):
        out.append({a: round(0.37 + 1.13 * (i + 1) * (k + 1) * (0.6 + 0.5 * k) + 0.05 * k, 6) / (1 + 0.5 * (i % 2))
                    for i, a in enumerate(func_names)})
    return out


def validate(rendered, fn, namespace, samples=()):
    """Evaluate rendered.expr_py against the real function. Returns mismatch messages (empty = agree).
    namespace: the module's globals (functions, constants, math). Samples where the real function raises are
    skipped; a sample where it returns but the expression raises or differs is a mismatch. Sets samples_checked."""
    if rendered.status not in ("math", "cases"):
        return []
    import inspect
    sig = inspect.signature(fn)
    params = list(sig.parameters)
    issues = []
    checked = 0

    def _error(msg="error"):
        raise ValueError(msg)
    ns = dict(namespace)
    ns["_error"] = _error
    ns.setdefault("math", math)
    code = compile(rendered.expr_py, "<expr_py>", "eval")
    for kw in list(samples) + _samples(params, []):
        kw = {k: v for k, v in kw.items() if k in params}
        try:
            bound = sig.bind_partial(**kw)
            bound.apply_defaults()
            kw = dict(bound.arguments)
        except TypeError:
            continue
        try:
            want = fn(**kw)
        except Exception:
            continue
        try:
            got = eval(code, dict(ns), dict(kw))
        except Exception as ex:
            issues.append("%s(%s): expression raised %s: %s" % (rendered.name, kw, type(ex).__name__, ex))
            continue
        checked += 1
        if not _same(got, want):
            issues.append("%s(%s): expression gives %r, function gives %r" % (rendered.name, kw, got, want))
    rendered.samples_checked = checked
    if checked == 0:
        rendered.warnings.append("no sample evaluated: expr_py not validated")
    return issues


def _same(a, b):
    if isinstance(a, (tuple, list)) and isinstance(b, (tuple, list)):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    if isinstance(a, bool) or isinstance(b, bool) or not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return a == b
    if math.isnan(a) and math.isnan(b):
        return True
    return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-300)


def _literal(tree, var):
    for n in tree.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name) \
                and n.targets[0].id == var:
            try:
                return ast.literal_eval(n.value)
            except Exception:
                return None
    return None


def render_part(path):
    """Render every public function of a calc.py (file order). ast only: nothing is executed."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    tree = ast.parse(text)
    inputs = _literal(tree, "INPUTS") or {}
    examples = _literal(tree, "EXAMPLES") or []
    out = []
    for n in tree.body:
        if isinstance(n, ast.FunctionDef) and not n.name.startswith("_"):
            out.append(render(text, n.name, inputs.get(n.name), examples))
    return out
