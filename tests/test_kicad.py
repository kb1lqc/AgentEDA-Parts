import unittest
from pathlib import Path

from lib import kicad

ROOT = Path(__file__).resolve().parent.parent
FIX = Path(__file__).parent / "fixtures" / "Acme" / "LDO1"
INA = ROOT / "components" / "TexasInstruments" / "INA821IDGK"


class TestParse(unittest.TestCase):
    def test_nested(self):
        self.assertEqual(kicad.parse('(a "b c" (d 1 2) "e\\"f")'), ["a", "b c", ["d", "1", "2"], 'e"f'])


class TestFixtures(unittest.TestCase):
    def test_symbol_pins(self):
        self.assertEqual(kicad.symbol_pins(FIX / "LDO1.kicad_sym"),
                         [("1", "IN", "power_in"), ("2", "GND", "power_in"), ("3", "OUT", "power_out")])

    def test_pads_ignore_empty_number(self):
        self.assertEqual(kicad.footprint_pads(FIX / "LDO1.kicad_mod"), {"1", "2", "3"})


@unittest.skipUnless((INA / "INA821IDGK.kicad_sym").exists(), "INA821 files not present")
class TestRealFiles(unittest.TestCase):
    def test_ina821(self):
        pins = kicad.symbol_pins(INA / "INA821IDGK.kicad_sym")
        self.assertEqual(len(pins), 8)
        self.assertEqual(sorted(p[0] for p in pins), [str(i) for i in range(1, 9)])
        self.assertIn(("1", "-IN", "input"), pins)
        self.assertEqual(kicad.footprint_pads(INA / "INA821IDGK.kicad_mod"), {str(i) for i in range(1, 9)})


if __name__ == "__main__":
    unittest.main()
