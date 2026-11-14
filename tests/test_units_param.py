import unittest

from lib import Param
from lib.units import eng, to_si


class TestUnits(unittest.TestCase):
    def test_prefixes(self):
        self.assertEqual(to_si(5.49, "kohm"), (5490.0, "ohm"))
        self.assertEqual(to_si(80, "uV"), (8e-5, "V"))
        self.assertEqual(to_si(2, "Mohm"), (2e6, "ohm"))
        self.assertEqual(to_si(3, "mohm"), (0.003, "ohm"))
        self.assertEqual(to_si(10, "ms"), (0.01, "s"))
        self.assertEqual(to_si(5, "pA"), (5e-12, "A"))

    def test_length_mass(self):
        self.assertEqual(to_si(2.5, "mm"), (0.0025, "m"))
        self.assertEqual(to_si(500, "mg"), (0.0005, "kg"))
        self.assertEqual(to_si(2, "g"), (0.002, "kg"))

    def test_unscaled(self):
        self.assertEqual(to_si(-40, "degC"), (-40.0, "degC"))
        self.assertEqual(to_si(2.5, "V/us"), (2.5e6, "V/s"))
        self.assertEqual(to_si(3, "degC/W"), (3.0, "degC/W"))
        self.assertEqual(to_si(9, ""), (9.0, ""))

    def test_suffixes(self):
        self.assertEqual(to_si(1.5, "uVpp"), (1.5e-6, "Vpp"))
        self.assertEqual(to_si(100, "fA/rtHz"), (100e-15, "A/rtHz"))
        value, base = to_si(0.4, "uV/degC")
        self.assertAlmostEqual(value, 0.4e-6, delta=1e-18)
        self.assertEqual(base, "V/degC")
        self.assertEqual(to_si(2, "kV/us"), (2e9, "V/s"))
        self.assertEqual(to_si(100, "Gohm"), (100e9, "ohm"))
        self.assertEqual(eng(100e-15, "A/rtHz"), "100 fA/rtHz")

    def test_fractions(self):
        self.assertEqual(to_si(0.5, "%"), (0.005, "1"))
        self.assertEqual(to_si(35, "ppm"), (35e-6, "1"))
        self.assertEqual(to_si(50, "ppm/degC"), (50e-6, "1/degC"))

    def test_suffixes(self):
        self.assertEqual(to_si(10, "nV/rtHz"), (1e-8, "V/rtHz"))
        self.assertEqual(to_si(2, "uVpp"), (2e-6, "Vpp"))
        self.assertEqual(to_si(3, "fA/rtHz"), (3e-15, "A/rtHz"))

    def test_ratio_units(self):
        self.assertAlmostEqual(to_si(0.5, "uV/V")[0], 0.5e-6)
        self.assertAlmostEqual(to_si(0.25, "mV/V")[0], 0.25e-3)
        self.assertAlmostEqual(to_si(2, "m%")[0], 2e-5)
        self.assertEqual(to_si(7.8125, "mdegC"), (0.0078125, "degC"))
        self.assertEqual(to_si(20, "bits"), (20.0, "bits"))

    def test_unknown(self):
        for bad in ("furlong", "kohm/rtHz/degC", "Kohm", "kdegC", "pp"):
            with self.assertRaises(ValueError):
                to_si(1, bad)
        with self.assertRaises(ValueError):
            to_si("1", "V")

    def test_eng(self):
        self.assertEqual(eng(5490, "ohm"), "5.49 kohm")
        self.assertEqual(eng(80e-6, "V"), "80 uV")
        self.assertEqual(eng(0, "V"), "0 V")
        self.assertEqual(eng(-0.5, "A"), "-500 mA")
        self.assertEqual(eng(12.5, "degC"), "12.5 degC")
        self.assertEqual(eng(None, "V"), "-")
        self.assertEqual(eng(0.0015, "1"), "0.0015")
        self.assertEqual(eng(3.5e-5, "1/degC"), "3.5e-05 1/degC")
        self.assertEqual(eng(2e-8, "V/rtHz"), "20 nV/rtHz")


class TestParam(unittest.TestCase):
    def test_tol(self):
        p = Param.tol(5.49, 0.01, "kohm")
        self.assertAlmostEqual(p.min, 5435.1)
        self.assertAlmostEqual(p.max, 5544.9)
        self.assertEqual(p.typ, 5490.0)
        self.assertEqual(p.unit, "ohm")

    def test_tol_negative_nominal(self):
        p = Param.tol(-10, 0.1, "V")
        self.assertEqual((p.min, p.max), (-11.0, -9.0))

    def test_exact(self):
        p = Param.exact(3.3, "V")
        self.assertEqual((p.min, p.typ, p.max), (3.3, 3.3, 3.3))

    def test_text_repr_and_wca(self):
        from lib import wca
        p = Param(text="Continuous", unit="A")
        self.assertEqual(repr(p), "Param(text='Continuous')")
        with self.assertRaises(ValueError) as cm:
            wca(lambda x: x, x=p)
        self.assertIn("text rating", str(cm.exception))

    def test_repr(self):
        self.assertEqual(repr(Param(max=80e-6, unit="V")), "Param(max=80 uV)")
        self.assertEqual(repr(Param.tol(5.49, 0.001, "kohm")), "Param(min=5.485 kohm, typ=5.49 kohm, max=5.495 kohm)")


if __name__ == "__main__":
    unittest.main()


class TestWithTyp(unittest.TestCase):
    def test_with_typ_keeps_bounds(self):
        from lib.param import Param
        p = Param(min=-0.005, max=0.005, unit="1").with_typ(0.0)
        self.assertEqual((p.min, p.typ, p.max), (-0.005, 0.0, 0.005))
