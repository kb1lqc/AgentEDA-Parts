import importlib.util
import inspect
import math
import os
import unittest

from lib import eqrender as q

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INA = os.path.join(ROOT, "components/TexasInstruments/INA821IDGK/calc.py")
LTC = os.path.join(ROOT, "components/AnalogDevices/LTC4364MS/calc.py")
WSK = os.path.join(ROOT, "components/Vishay/WSK2512R0250D/calc.py")
PARTS3 = [INA, LTC, WSK]


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load(path):
    spec = importlib.util.spec_from_file_location("calc_" + str(abs(hash(path))), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def r(src, name, **kw):
    return q.render(src, name, **kw)


def ev(rendered, **kw):
    ns = {"math": math}
    ns["_error"] = lambda m="": (_ for _ in ()).throw(ValueError(m))
    return eval(rendered.expr_py, ns, kw)


class TestIna821(unittest.TestCase):
    def setUp(self):
        self.by = {x.name: x for x in q.render_part(INA)}

    def test_gain(self):
        g = self.by["gain"]
        self.assertEqual((g.kind, g.status), ("ds", "math"))
        self.assertIn("display:inline-block", g.html)       # stacked fraction
        self.assertIn("border-bottom", g.html)
        self.assertEqual(g.expr_py, "1 + 49400.0 / rg")
        self.assertAlmostEqual(ev(g, rg=49.4e3), 2.0)

    def test_rg_for_gain_is_algebra(self):
        a = self.by["rg_for_gain"]
        self.assertEqual((a.kind, a.status), ("algebra", "math"))
        self.assertEqual(a.expr_py, "49400.0 / (g - 1)")
        self.assertIn("49400 / (g - 1)", a.text)

    def test_power_and_sqrt(self):
        for n in ("dvos_rti", "en_rti"):
            x = self.by[n]
            self.assertEqual(x.status, "math")
            self.assertIn("&radic;", x.html)
            self.assertIn("border-top", x.html)
            self.assertIn("<sup>2</sup>", x.html)
        self.assertAlmostEqual(ev(self.by["dvos_rti"], dvosi=3.0, dvoso=4.0, g=1.0), 5.0)

    def test_engineering_kind(self):
        self.assertEqual(self.by["gain_actual"].kind, "engineering")

    def test_examples_table_uses_function_result(self):
        mod = load(INA)
        x = q.render(_read(INA), "gain", examples=mod.EXAMPLES, fn=mod.gain)
        self.assertIn("OK", x.html)
        self.assertNotIn("FAIL", x.html)
        y = q.render(_read(INA), "vout")
        self.assertIn("no worked example", y.html)


class TestShapes(unittest.TestCase):
    def test_if_function_is_cases(self):
        x = r("def f(a, b):\n    '''DS p.1.'''\n    if a > b:\n        return a - b\n    return b - a\n", "f")
        self.assertEqual(x.status, "cases")
        self.assertIn("otherwise", x.html)
        self.assertEqual(ev(x, a=1, b=5), 4)
        self.assertEqual(ev(x, a=5, b=1), 4)

    def test_elif_chain_flattens(self):
        x = r("def f(a):\n    if a < 0:\n        return -a\n    elif a < 1:\n        return a * 2\n    else:\n"
              "        return 7\n", "f")
        self.assertEqual(x.status, "cases")
        self.assertEqual([ev(x, a=v) for v in (-2, 0.5, 3)], [2, 1.0, 7])
        self.assertEqual(x.html.count("otherwise"), 1)
        self.assertIn("<i>a</i> &lt; 1", x.html)

    def test_ifexp_cases(self):
        x = r("def f(a):\n    return 1 if a else 2\n", "f")
        self.assertEqual(x.status, "cases")

    def test_guard_listed_not_inlined(self):
        mod = load(LTC)
        x = {y.name: y for y in q.render_part(LTC)}["p2t_transient"]
        self.assertEqual(x.status, "math")
        self.assertEqual(x.where[0], "a = vreg_v - vin")
        self.assertEqual(len(x.where), 2)
        self.assertEqual(len(x.guards), 1)
        self.assertIn("error when a <= 0 or b <= a", x.guards[0])
        self.assertIn("where", x.html)
        self.assertIn("error when", x.html)
        # the display keeps a and b as names; only expr_py substitutes
        self.assertIn("<i>a</i>", x.html)
        self.assertNotIn("vreg_v", x.text.split(" = ", 1)[1].split("where")[0])
        kw = dict(i_load=2.0, tr=1e-3, tau=5e-3, vpk=80.0, vin=12.0, vreg_v=30.0)
        self.assertAlmostEqual(ev(x, **kw), mod.p2t_transient(**kw), delta=1e-12)

    def test_for_function_is_source_only(self):
        x = r("def f(n):\n    t = 0\n    for i in range(n):\n        t += i\n    return t\n", "f")
        self.assertEqual((x.status, x.kind), ("source_only", "helper"))
        self.assertIn("not rendered as math: read the source", x.html)
        self.assertIn("for i in range", x.html)
        self.assertEqual(x.expr_py, "")

    def test_fstring_is_helper_source_only(self):
        x = r("def mpn(a):\n    return f'X{a}'\n", "mpn")
        self.assertEqual((x.status, x.kind), ("source_only", "helper"))

    def test_nested_powers(self):
        x = r("def f(a, b, c):\n    return (a ** 2 + b) ** 3 / c ** (a ** 2)\n", "f")
        self.assertEqual(x.expr_py, "(a ** 2 + b) ** 3 / c ** a ** 2")
        self.assertIn("<sup>3</sup>", x.html)
        self.assertIn("<sup><i>a</i><sup>2</sup></sup>", x.html)
        self.assertAlmostEqual(ev(x, a=1.5, b=0.5, c=1.1), (1.5 ** 2 + .5) ** 3 / 1.1 ** (1.5 ** 2))
        y = r("def f(a):\n    return (-a) ** 2 + -a ** 2\n", "f")
        self.assertEqual(ev(y, a=3), 9 - 9)
        self.assertIn("(-a) ** 2", y.expr_py)

    def test_precedence_parenthesization(self):
        x = r("def f(a, b, c):\n    return (a * b / (a + b)) * c\n", "f")
        self.assertEqual(x.expr_py, "a * b / (a + b) * c")
        self.assertEqual(x.text, "f(a, b, c) = a * b / (a + b) * c")
        y = r("def f(a, b, c):\n    return a * (b / c) - (a - b) - (b - c) * (a + b)\n", "f")
        self.assertEqual(y.expr_py, "a * (b / c) - (a - b) - (b - c) * (a + b)")
        z = r("def f(a, b, c):\n    return a - (b + c) + a / (b * c) + a / b * c\n", "f")
        self.assertEqual(z.expr_py, "a - (b + c) + a / (b * c) + a / b * c")
        self.assertAlmostEqual(ev(z, a=2.5, b=3.5, c=0.7), 2.5 - (3.5 + .7) + 2.5 / (3.5 * .7) + 2.5 / 3.5 * .7)

    def test_float_literals_no_auto_prefix(self):
        x = r("def f(a):\n    return a * 49.4e3 + 1e-6 + 0.001 + 2.5e-9\n", "f")
        self.assertIn("49400", x.text)
        self.assertIn("10^-6", x.text)
        self.assertIn("&times; 10<sup>-9</sup>", x.html)
        self.assertIn("0.001", x.text)
        for bad in (" k", "kohm", " u", " n"):
            self.assertNotIn(bad, x.text)
        self.assertEqual(x.expr_py, "a * 49400.0 + 1e-06 + 0.001 + 2.5e-09")

    def test_abs_log_names(self):
        x = r("def f(a, b):\n    return abs(a) + math.log10(b) + math.log(b) + math.exp(a) + b ** 0.5\n", "f")
        self.assertIn("|<i>a</i>|", x.html)
        self.assertIn("log<sub>10</sub>", x.html)
        self.assertIn("ln(", x.html)
        self.assertAlmostEqual(ev(x, a=-1.0, b=4.0), 1 + math.log10(4) + math.log(4) + math.exp(-1) + 2)

    def test_local_variable_where_list(self):
        x = r("def f(a, b):\n    s = a + b\n    return s * s / a\n", "f")
        self.assertEqual(x.where, ["s = a + b"])
        self.assertEqual(x.expr_py, "(a + b) * (a + b) / a")
        self.assertIn("where", x.html)

    def test_unsupported_statement_reports_reason(self):
        x = r("def f(a):\n    a += 1\n    return a\n", "f")
        self.assertEqual(x.status, "source_only")
        self.assertTrue(x.warnings)

    def test_deterministic(self):
        s = _read(INA)
        self.assertEqual(q.render(s, "gain").html, q.render(s, "gain").html)

    def test_kind_prefixes(self):
        d = "def f(a):\n    '''%s'''\n    return a\n"
        self.assertEqual(r(d % "Algebra on DS p.2, Eq 1.", "f").kind, "algebra")
        self.assertEqual(r(d % "Not a DS equation: x.", "f").kind, "engineering")
        self.assertEqual(r(d % "y. DS p.2.", "f").kind, "ds")


class TestEvaluationAgainstRealFunctions(unittest.TestCase):
    def check_part(self, path):
        mod = load(path)
        ns = vars(mod)
        examples = getattr(mod, "EXAMPLES", [])
        seen = 0
        for x in q.render_part(path):
            if x.status not in ("math", "cases"):
                continue
            fn = getattr(mod, x.name)
            rows = [kw for f, kw, *_ in examples if f == x.name]
            issues = q.validate(x, fn, ns, rows)
            self.assertEqual(issues, [], x.name)
            seen += x.samples_checked
        self.assertGreater(seen, 10)

    def test_ina821(self):
        self.check_part(INA)

    def test_ltc4364(self):
        self.check_part(LTC)

    def test_wsk(self):
        self.check_part(WSK)

    def test_validate_detects_mismatch(self):
        x = r("def f(a):\n    return a * 2\n", "f")
        x.expr_py = "a * 3"
        self.assertTrue(q.validate(x, lambda a: a * 2, {}, [{"a": 1.0}]))

    def test_every_example_row_evaluates(self):
        for path in PARTS3:
            mod = load(path)
            by = {x.name: x for x in q.render_part(path)}
            for f, kw, exp, tol, cite in getattr(mod, "EXAMPLES", []):
                x = by[f]
                if x.status not in ("math", "cases"):
                    continue
                ns = dict(vars(mod))
                ns["_error"] = lambda m="": 1 / 0
                b = inspect.signature(getattr(mod, f)).bind(**kw)
                b.apply_defaults()
                self.assertTrue(math.isclose(eval(x.expr_py, ns, dict(b.arguments)), getattr(mod, f)(**kw),
                                             rel_tol=1e-12), (path, f, kw))


if __name__ == "__main__":
    unittest.main()
