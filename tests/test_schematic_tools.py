import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "schematic"))
import kicad_sexpr as kx  # noqa: E402
import overlap  # noqa: E402
import place  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "schematic" / "transforms.kicad_sch"
INA = Path("/Users/brycesalmiconsulting/dev/ina229/benches/INA229HighSideMonitor/eda")


def sheet_from(body):
    """A sheet with one 2-pin symbol 'R' (pins at (+-2.54, 0), body box 4 x 1.5) plus `body` items."""
    return place.Sheet(kx.loads(
        '(kicad_sch\n\t(version 20260306)\n\t(paper "A4")\n\t(lib_symbols\n\t\t(symbol "R"\n\t\t\t(symbol "R_0_1"\n'
        '\t\t\t\t(rectangle\n\t\t\t\t\t(start -1 0.75)\n\t\t\t\t\t(end 1 -0.75)\n\t\t\t\t)\n\t\t\t)\n'
        '\t\t\t(symbol "R_1_1"\n\t\t\t\t(pin passive line\n\t\t\t\t\t(at -2.54 0 0)\n\t\t\t\t\t(length 1.54)\n'
        '\t\t\t\t\t(name "A")\n\t\t\t\t\t(number "1")\n\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n' + body + ")\n"), "t")


class TestSexpr(unittest.TestCase):
    def test_roundtrip_odd_whitespace(self):
        t = '(a  "b\\"c\\nd" (e 1.50 -0)\n\t(f)  )\n'
        self.assertEqual(kx.dumps(kx.loads(t)), t)

    def test_roundtrip_fixture_and_ina(self):
        for p in [FIX] + ([INA / "INA.kicad_sch", INA / "INA229HighSideMonitor_bench.kicad_sch"] if INA.exists() else []):
            t = p.read_text(newline="")
            self.assertEqual(kx.dumps(kx.loads(t)), t, p.name)

    def test_values(self):
        n = kx.loads('(x "a\\"b\\nc" (at 1.5 2 90))')
        self.assertEqual(n.atoms()[1].value, 'a"b\nc')
        self.assertEqual(n.get("at").nums(), [1.5, 2, 90])
        self.assertEqual(kx.fmt(133.35 + 1.27), "134.62")


class TestTransforms(unittest.TestCase):
    def test_all_rotations_and_mirrors_match_kicad(self):
        """The fixture's labels sit on the pin ends that kicad-cli's netlist assigned (verified 36 of 36)."""
        sh = place.Sheet.load(FIX)
        labels = {}
        for l in sh.root.nodes("label"):
            at = l.get("at").nums()
            labels[l.atoms()[1].value] = (at[0], at[1])
        self.assertEqual(len(sh.symbols()), 12)
        for s in sh.symbols():
            i = s.ref[1:]
            pts = sh.pin_points(s.ref)
            for num, ab in (("1", "A"), ("2", "B"), ("3", "C")):
                self.assertEqual(pts[num], labels["U%s_%s" % (i, ab)], (s.ref, s.rot, s.mirror, num))

    def test_literal_cases(self):
        # pin A at lib (-5.08, 2.54): rot 90 CCW sends "left" to "down"; mirror x flips screen y AFTER rotation
        self.assertEqual(place.pin_endpoint((-5.08, 2.54), (50, 50), 0), (44.92, 47.46))
        self.assertEqual(place.pin_endpoint((-5.08, 2.54), (50, 50), 90), (47.46, 55.08))
        self.assertEqual(place.pin_endpoint((-5.08, 2.54), (50, 50), 90, "x"), (47.46, 44.92))
        self.assertEqual(place.pin_endpoint((-5.08, 2.54), (50, 50), 180, "y"), (44.92, 52.54))
        self.assertEqual(place.pin_endpoint((-5.08, 2.54), (50, 50), 270, "y"), (47.46, 44.92))

    def test_pin_direction(self):
        self.assertEqual(place.pin_direction(90), 90)  # a VCC symbol pin points up into the symbol
        self.assertEqual(place.pin_direction(0, 180), 180)
        self.assertEqual(place.pin_direction(0, 0, "y"), 180)

    def test_snap(self):
        self.assertEqual(place.snap(133.4), 133.35)
        self.assertEqual(place.snap(133.4, place.GRID), 134.62)


class TestEmitters(unittest.TestCase):
    def test_label_justification(self):
        self.assertEqual(place.label_style(0), (0, "left bottom"))
        self.assertEqual(place.label_style(90), (90, "left bottom"))
        self.assertEqual(place.label_style(180), (180, "right bottom"))
        self.assertEqual(place.label_style(270), (270, "right bottom"))
        self.assertEqual(place.label_style(180, hier=True), (180, "right"))
        self.assertEqual(place.label_style(0, hier=True), (0, "left"))

    def test_deterministic_uuids_and_idempotent_emit(self):
        def build(ns, key):
            sh = sheet_from("")
            sh.ns = place.uuid.uuid5(place.uuid.NAMESPACE_URL, ns)
            sh.wire([(0, 0), (10, 0)], "w")
            sh.hlabel("BUS_OUT", 10, 0, 0, key)
            sh.hlabel("BUS_OUT", 10, 0, 0, key)  # same key: replaces, no duplicate
            return sh
        a, b = kx.dumps(build("n", "k").root), kx.dumps(build("n", "k").root)
        self.assertEqual(a, b)
        self.assertEqual(a.count("(hierarchical_label"), 1)
        self.assertNotEqual(a, kx.dumps(build("other", "k").root))
        self.assertNotEqual(a, kx.dumps(build("n", "k2").root))
        self.assertRegex(a, r'\(uuid "[0-9a-f-]{36}"\)')

    def test_paper_and_title_block(self):
        sh = sheet_from("")
        sh.set_paper(place.PAPER_TABLOID)
        sh.set_title_block(title="T", rev="A", comments={1: "repo @ abc1234"})
        sh.set_title_block(comments={1: "repo @ def5678"})
        out = kx.dumps(sh.root)
        self.assertIn('(paper "USLedger")', out)
        self.assertEqual(out.count("(comment 1"), 1)
        self.assertIn('(comment 1 "repo @ def5678")', out)
        kx.loads(out)


class TestChecks(unittest.TestCase):
    SYM = ('\t(symbol\n\t\t(lib_id "R")\n\t\t(at 50 50 0)\n\t\t(unit 1)\n\t\t(property "Reference" "R1"\n'
           '\t\t\t(at 50 46 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
           '\t\t(property "Value" "10k"\n\t\t\t(at 50 54 0)\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size 1.27 1.27)\n'
           '\t\t\t\t)\n\t\t\t)\n\t\t)\n\t)\n')

    def test_text_over_wire_is_reported_and_clear_text_is_not(self):
        sh = sheet_from("")
        sh.wire([(10, 10), (40, 10)], "w")
        sh.label("OK", 10, 10, 0, "ok")  # sits on top of its own wire, anchor at the wire end
        self.assertEqual(overlap.check_overlap(sh), [])
        sh.text("NOTE OVER WIRE", 15, 10, "t")
        found = overlap.check_overlap(sh)
        self.assertEqual([f[0] for f in found], ["text-wire"], found)
        sh.text("NOTE OVER WIRE", 16, 10.5, "t2")
        self.assertIn("text-text", [f[0] for f in overlap.check_overlap(sh)])

    def test_hlabel_at_wire_end_and_symbol_field_overlap(self):
        sh = sheet_from("")
        sh.wire([(10, 10), (30, 10)], "w")
        sh.hlabel("PORT", 30, 10, 0, "h")  # text runs away from the wire
        self.assertEqual(overlap.check_overlap(sh), [])
        sh.hlabel("PORT_BACK", 30, 10, 180, "h2")  # text runs back over the wire
        self.assertIn("text-wire", [f[0] for f in overlap.check_overlap(sh)])
        sh2 = sheet_from(self.SYM)
        self.assertEqual(overlap.check_overlap(sh2), [])
        sh2.text("note", 50, 50, "n", "center")  # over the body box
        self.assertIn("text-body", [f[0] for f in overlap.check_overlap(sh2)])

    def test_dangling(self):
        sh = sheet_from(self.SYM)
        kinds = lambda: sorted(f[0] for f in overlap.check_dangling(sh))
        self.assertEqual(kinds(), ["pin-unconnected"])
        sh.wire([(47.46, 50), (40, 50)], "w")  # pin 1 end is (47.46, 50)
        self.assertEqual(kinds(), ["wire-end"])
        sh.label("NET", 40, 50, 0, "l")
        self.assertEqual(kinds(), [])
        sh.label("STRAY", 20, 20, 0, "s")
        sh.wire([(60, 60), (70, 60)], "x")
        self.assertEqual(kinds(), ["label-unconnected", "wire-end", "wire-end"])

    def test_cli_exit_codes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            sh = sheet_from("")
            sh.wire([(10, 10), (40, 10)], "w")
            sh.label("A", 10, 10, 0, "a")
            sh.label("B", 40, 10, 180, "b")
            p = str(Path(d) / "a.kicad_sch")
            sh.save(p)
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(overlap.main([p]), 0)
                sh.text("OVER", 20, 10, "t")
                sh.save(p)
                self.assertEqual(overlap.main(["--overlap", p]), 1)
                self.assertEqual(overlap.main([]), 2)


class TestMoveAndPower(unittest.TestCase):
    def test_move_keeps_fields_readable(self):
        sh = sheet_from(TestChecks.SYM)
        sh.place_symbol("R1", 60, 70, rot=90)
        s = sh.symbol("R1")
        self.assertEqual((s.at, s.rot), ((60, 70), 90))
        ref = s._prop("Reference").get("at").nums()
        self.assertEqual(ref[:2], [60, 66])
        self.assertEqual(ref[2], 270)  # stored relative to the 90 degree symbol: visual angle still 0
        sh.place_symbol("R1", 60, 70, mirror="y")
        self.assertEqual(sh.symbol("R1").mirror, "y")
        sh.place_symbol("R1", 60, 70, mirror=None)
        self.assertIsNone(sh.symbol("R1").mirror)


if __name__ == "__main__":
    unittest.main()
