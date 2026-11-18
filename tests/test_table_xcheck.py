import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import phase3b_pdf as fx  # noqa: E402
import table_xcheck as T  # noqa: E402

HEAD = '[part]\nvalue = "X"\nmanufacturer = "Texas Instruments"\n'


def row(key, symbol, unit, cite="DS p.2, 6.5 Electrical Characteristics, x", **kw):
    lines = ["[param.%s]" % key, 'name = "n"', 'symbol = "%s"' % symbol, 'kind = "electrical"', 'scope = "25C"',
             'unit = "%s"' % unit, 'conditions = ""', 'cite = "%s"' % cite]
    for k, v in kw.items():
        lines.append("%s = %s" % (k, v if not isinstance(v, str) else '"%s"' % v))
    return "\n".join(lines) + "\n"


class TestTableXcheck(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp())
        cls.pdf = cls.tmp / "ds.pdf"
        cls.pdf.write_bytes(fx.build_pdf(fx.datasheet_pages()))

    @classmethod
    def tearDownClass(cls):
        __import__("shutil").rmtree(cls.tmp, ignore_errors=True)

    def check(self, body, head=HEAD, pdf=None):
        t = self.tmp / "component.toml"
        t.write_text(head + body)
        return T.check_rows(str(pdf or self.pdf), str(t))

    def status(self, body, key, **kw):
        rows, fatal = self.check(body, **kw)
        self.assertIsNone(fatal)
        return [(s, w) for k, s, w in rows if k == key][0]

    def test_agree_with_micro_normalised(self):
        s, w = self.status(row("vos", "VOS", "uV", typ=10, max=35), "vos")
        self.assertEqual(s, "AGREE", w)

    def test_agree_negative_en_dash(self):
        self.assertEqual(self.status(row("vcm", "VCM", "V", min=-0.3, max=85), "vcm")[0], "AGREE")

    def test_disagree_when_number_differs(self):
        s, w = self.status(row("vos_bad", "VOS", "uV", typ=10, max=36), "vos_bad")
        self.assertEqual(s, "DISAGREE")
        self.assertIn("MAX", w)

    def test_disagree_when_table_has_extra_number(self):
        s, w = self.status(row("ib_x", "IB", "nA", max=0.5), "ib_x")
        self.assertEqual(s, "DISAGREE")
        self.assertIn("TYP", w)

    def test_unsure_cases(self):
        body = (row("aol", "AOL", "dB", min=100, typ=120)               # footnote marker 120(1)
                + row("iq", "IQ", "mA", typ=1.2, max=2)                # symbol on two lines
                + row("ge", "GE", "%", typ=0.01, max=0.05)             # percent
                + row("vn", "VN", "nV/rtHz", typ=5)                    # odd unit
                + row("wrap", "WRAP", "V", typ=3, max=4)               # continuation line
                + row("sym", "VOS", "uV", typ=10, max=35, sym="true")  # convention
                + row("unitdiff", "VOS", "mV", typ=10, max=35)         # unit differs
                + row("nosym", "", "uV", typ=10, max=35)
                + row("badpage", "VOS", "uV", cite="DS p.77, x", typ=10, max=35)
                + row("nocite", "VOS", "uV", cite="somewhere", typ=10, max=35)
                + row("missing", "NOPE", "uV", typ=10)
                + row("nounit", "NOUNIT", "V", typ=7)                  # no unit cell on the value line
                + row("ib_nomax", "IB", "nA", typ=0.1))                # committed lacks max but... table has it
        rows, fatal = self.check(body)
        got = {k: (s, w) for k, s, w in rows}
        for k in ("aol", "iq", "ge", "vn", "wrap", "nounit", "sym", "unitdiff", "nosym", "badpage", "nocite", "missing"):
            self.assertEqual(got[k][0], "UNSURE", (k, got[k]))
        self.assertEqual(got["ib_nomax"][0], "DISAGREE")  # printed max the row lacks: flagged, never AGREE

    def test_permuted_columns_are_unsure(self):
        # committed holds the printed numbers in other columns (sign/order convention): never DISAGREE
        s, w = self.status(row("vos_p", "VOS", "uV", min=10, max=35), "vos_p")
        self.assertEqual(s, "UNSURE")

    def test_unknown_vendor_is_unsure(self):
        s, w = self.status(row("vos", "VOS", "uV", typ=10, max=35), "vos",
                           head='[part]\nvalue = "X"\nmanufacturer = "Acme"\n')
        self.assertEqual(s, "UNSURE")
        self.assertIn("tested set", w)

    def test_agree_output_prints_no_numbers(self):
        t = self.tmp / "c2.toml"
        t.write_text(HEAD + row("vos", "VOS", "uV", typ=10, max=35))
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "table_xcheck.py"), str(self.pdf), str(t)],
                           capture_output=True, text=True)
        line = [l for l in p.stdout.splitlines() if l.startswith("vos:")][0]
        self.assertEqual(line, "vos: AGREE one clean line; min/typ/max and unit equal")
        self.assertEqual(p.returncode, 0)

    def test_exit_codes(self):
        t = self.tmp / "c3.toml"
        t.write_text(HEAD + row("vos_bad", "VOS", "uV", typ=10, max=36))
        p = subprocess.run([sys.executable, str(ROOT / "tools" / "table_xcheck.py"), str(self.pdf), str(t)],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("DISAGREE=1", p.stdout)

    def test_fail_closed(self):
        ok = HEAD + row("vos", "VOS", "uV", typ=10, max=35)
        scanned = self.tmp / "scan.pdf"
        scanned.write_bytes(fx.build_pdf(fx.datasheet_pages(), scanned=(1, 2, 3, 4)))
        good = self.pdf.read_bytes()
        trunc = self.tmp / "trunc.pdf"
        trunc.write_bytes(good[: len(good) // 2])
        notable = self.tmp / "notable.pdf"
        notable.write_bytes(fx.build_pdf([[(40, 80, 12, "prose " * 10), (300, 760, 9, str(n))] for n in range(1, 5)]))
        for name, pdf in (("scanned", scanned), ("truncated", trunc), ("no table", notable),
                          ("missing", self.tmp / "none.pdf")):
            rows, fatal = self.check(ok, pdf=pdf)
            self.assertIsNotNone(fatal, name)
            self.assertEqual(rows, [], name)
        t = self.tmp / "empty.toml"
        t.write_text("")
        self.assertIsNotNone(T.check_rows(str(self.pdf), str(t))[1])
        t.write_text("[part\nbroken")
        self.assertIsNotNone(T.check_rows(str(self.pdf), str(t))[1])
        self.assertIsNotNone(T.check_rows(str(self.pdf), str(self.tmp / "absent.toml"))[1])
        t.write_text(HEAD)
        self.assertIsNotNone(T.check_rows(str(self.pdf), str(t))[1])  # no [param] rows

    def test_unit_normalisation(self):
        self.assertEqual(T.norm_unit("µV"), "uV")
        self.assertEqual(T.norm_unit("kΩ"), "kohm")
        self.assertEqual(T.norm_unit("°C/W"), "degC/W")

    def test_deterministic(self):
        t = self.tmp / "c4.toml"
        t.write_text(HEAD + row("vos", "VOS", "uV", typ=10, max=35) + row("ib", "IB", "nA", typ=0.1, max=0.5))
        outs = [subprocess.run([sys.executable, str(ROOT / "tools" / "table_xcheck.py"), str(self.pdf), str(t)],
                               capture_output=True, text=True).stdout for _ in range(2)]
        self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
