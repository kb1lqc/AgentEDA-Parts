import os
import tempfile
import unittest

from lib import Param, plot_band, table, wca
from lib.wca import sweep


def divider(vin, r1, r2):
    return vin * r2 / (r1 + r2)


class TestWca(unittest.TestCase):
    def setUp(self):
        self.vin = Param.exact(5.0, "V")
        self.r1 = Param.tol(10, 0.01, "kohm")
        self.r2 = Param.tol(10, 0.01, "kohm")

    def test_divider_corners(self):
        out = wca(divider, vin=self.vin, r1=self.r1, r2=self.r2)
        # Hand corners: R2 high, R1 low gives the max; R2 low, R1 high gives the min.
        self.assertAlmostEqual(out.max, 5 * 10100 / (9900 + 10100))  # 2.525
        self.assertAlmostEqual(out.min, 5 * 9900 / (10100 + 9900))  # 2.475
        self.assertAlmostEqual(out.typ, 2.5)

    def test_float_is_exact(self):
        out = wca(divider, vin=5.0, r1=10e3, r2=10e3)
        self.assertEqual((out.min, out.typ, out.max), (2.5, 2.5, 2.5))

    def test_missing_typ_gives_none(self):
        out = wca(divider, vin=5.0, r1=Param(min=9e3, max=11e3), r2=10e3)
        self.assertIsNone(out.typ)
        self.assertIsNotNone(out.min)

    def test_missing_bound_is_error_naming_input(self):
        with self.assertRaises(ValueError) as cm:
            wca(divider, vin=5.0, r1=Param(typ=10e3, max=11e3), r2=10e3)
        self.assertIn("r1", str(cm.exception))
        self.assertIn("min", str(cm.exception))

    def test_samples_find_interior_extremum(self):
        peak = lambda x: -(x - 1) ** 2
        p = Param(min=0, typ=1, max=2)
        self.assertEqual(wca(peak, x=p).max, -1)  # corners miss the peak
        self.assertAlmostEqual(wca(peak, x=p, samples=1).max, 0)  # midpoint is the peak

    def test_sweep_and_report(self):
        pts = sweep(divider, "vin", [1.0, 2.0], r1=self.r1, r2=self.r2)
        self.assertEqual([x for x, _ in pts], [1.0, 2.0])
        self.assertAlmostEqual(pts[1][1].max, 2 * 10100 / 20000)
        out = wca(divider, unit="V", vin=self.vin, r1=self.r1, r2=self.r2)
        text = table([("Vout", out, "1% resistors")])
        self.assertIn("| Vout | 2.475 | 2.5 | 2.525 | V | 1% resistors |", text)
        with tempfile.TemporaryDirectory() as d:
            png = plot_band(divider, "vin", [1, 2, 3], os.path.join(d, "a.png"), r1=self.r1, r2=self.r2)
            self.assertTrue(os.path.getsize(png) > 0)


if __name__ == "__main__":
    unittest.main()
