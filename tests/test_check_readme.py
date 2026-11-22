import tempfile
from unittest import mock
import unittest
from pathlib import Path
from shutil import copytree

from lib import Param, load, readme
from lib.check import check_component

FIX = Path(__file__).parent / "fixtures" / "Acme"


def messages(folder):
    return [f"{lvl}: {msg}" for lvl, msg in check_component(folder)]


class TestCheck(unittest.TestCase):
    def test_good_fixture_passes(self):
        self.assertEqual(messages(FIX / "LDO1"), [])

    def test_bad_fixture_fails(self):
        text = "\n".join(messages(FIX / "BAD1"))
        self.assertIn("ERROR: param vin_abs: min <= typ <= max violated", text)
        self.assertIn("ERROR: param vref: missing 'cite'", text)
        self.assertIn("ERROR: pin 3: name mismatch, TOML 'VOUT' vs symbol 'OUT'", text)
        self.assertIn("ERROR: pin 2: type mismatch, TOML 'input' vs symbol 'power_in'", text)
        self.assertIn("ERROR: example vout", text)

    def test_missing_calc_is_warning(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            (copy / "calc.py").unlink()
            self.assertEqual(messages(copy), ["WARN: no calc.py"])

    def test_unknown_unit_and_missing_pad(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            toml = copy / "component.toml"
            toml.write_text(toml.read_text().replace('unit = "mV"', 'unit = "furlong"'))
            fp = copy / "LDO1.kicad_mod"
            fp.write_text(fp.read_text().replace('(pad "3"', '(pad "9"'))
            text = "\n".join(messages(copy))
            self.assertIn("unknown unit 'furlong'", text)
            self.assertIn("pin 3: no footprint pad", text)


def copy_fixture(tmp, edits=None, calc_edits=None):
    """Copy LDO1 into tmp, applying (old, new) text replacements to component.toml / calc.py."""
    copy = Path(tmp) / "LDO1"
    copytree(FIX / "LDO1", copy)
    for name, pairs in (("component.toml", edits or []), ("calc.py", calc_edits or [])):
        path = copy / name
        text = path.read_text()
        for old, new in pairs:
            assert old in text, old
            text = text.replace(old, new)
        path.write_text(text)
    return copy


class TestNewChecks(unittest.TestCase):
    def run_edit(self, edits=None, calc_edits=None):
        with tempfile.TemporaryDirectory() as d:
            return "\n".join(messages(copy_fixture(d, edits, calc_edits)))

    def test_sym_needs_max_and_no_min(self):
        text = self.run_edit([("typ = 10\nmax = 40\nsym = true", "typ = 10\nmin = -5\nmax = 40\nsym = true")])
        self.assertIn("param vos: sym = true needs max and no min", text)
        text = self.run_edit([("typ = 10\nmax = 40\nsym = true", "typ = 10\nsym = true")])
        self.assertIn("param vos: sym = true needs max and no min", text)

    def test_text_xor_numbers(self):
        self.assertIn("either min/typ/max or text", self.run_edit([('text = "Continuous"', 'text = "Continuous"\nmax = 1')]))
        self.assertIn("either min/typ/max or text", self.run_edit([('text = "Continuous"\n', "")]))

    def test_partial_scope_ok_and_bad_scope(self):
        self.assertEqual(self.run_edit(), "")  # fixture already uses scope = "partial"
        self.assertIn("scope 'sometimes'", self.run_edit([('scope = "partial"', 'scope = "sometimes"')]))

    def test_duplicate_pin_numbers(self):
        text = self.run_edit([('number = "3"', 'number = "2"')])
        self.assertIn("pin 2: number appears more than once", text)

    def test_bad_ref(self):
        self.assertIn("min_ref 'VSS' is not a [[pin]] name", self.run_edit([('min_ref = "GND"', 'min_ref = "VSS"')]))

    def test_cite_format_is_error(self):
        text = self.run_edit([("DS p.5, Electrical Characteristics, TC", "page 5, TC")])
        self.assertIn("ERROR: [cite-format] param tc: cite 'page 5, TC'", text)

    def test_datasheet_file_missing_is_warning(self):
        text = self.run_edit([('step = "none"', 'step = "none"\ndatasheet_file = "docs/datasheets/nope.pdf"')])
        self.assertIn("WARN: datasheet_file not found", text)
        self.assertNotIn("ERROR", text)

    def test_cite_naming_a_sheet_without_brackets_is_error(self):
        from lib import check
        cite = "DS p.5, Electrical Characteristics, TC"
        with mock.patch.object(check, "sheet_names", return_value={"other-sheet.pdf"}):
            text = self.run_edit([(cite, "DS p.5, other-sheet table, TC")])
            self.assertIn("ERROR: [cite-sheet-bracket] param tc: cite names other-sheet", text)
            self.assertIn("DS p.<n> (other-sheet.pdf), ...", text)
            self.assertNotIn("ERROR", self.run_edit([(cite, "DS p.5 (other-sheet.pdf), table, TC")]))

    def test_sheet_names_from_review_toml_and_local_datasheets(self):
        from lib import check
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            folder = root / "components" / "Acme" / "X"
            (folder / "review").mkdir(parents=True)
            (folder / "review" / "review.toml").write_text('[inputs]\nsheets = { "a-sheet.pdf" = "1" }\n')
            self.assertEqual(check.sheet_names(folder, root), {"a-sheet.pdf"})  # CI: no docs/datasheets/
            (root / "docs" / "datasheets").mkdir(parents=True)
            (root / "docs" / "datasheets" / "b-sheet.pdf").write_bytes(b"%PDF")
            (root / "docs" / "datasheets" / "note.html").write_text("x")
            self.assertEqual(check.sheet_names(folder, root), {"a-sheet.pdf", "b-sheet.pdf"})

    def test_datasheet_url_empty_is_tolerated_warn(self):
        text = self.run_edit([('datasheet_url = "https://example.com/ldo1.pdf"', 'datasheet_url = ""')])
        self.assertIn("WARN: datasheet_url empty (record the vendor URL; open item)", text)
        self.assertNotIn("missing field", text)
        self.assertNotIn("ERROR", text)

    def test_datasheet_url_bad_scheme_is_error(self):
        text = self.run_edit([('datasheet_url = "https://example.com/ldo1.pdf"', 'datasheet_url = "www.ti.com/x.pdf"')])
        self.assertIn("ERROR: datasheet_url must start with http:// or https://", text)

    def test_tolerated_warnings_do_not_fail_main(self):
        import contextlib
        import io
        from lib import check
        with tempfile.TemporaryDirectory() as d:
            copy = copy_fixture(d, [('datasheet_url = "https://example.com/ldo1.pdf"', 'datasheet_url = ""')])
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with mock.patch.object(check.rules, "wiring_findings", return_value=[]):
                    code = check.main([str(copy)])
        self.assertEqual(code, 0, out.getvalue())
        self.assertIn("0 errors, 0 warnings, 1 tolerated", out.getvalue())

    def test_bad_import(self):
        text = self.run_edit(calc_edits=[("def vout", "import os\nfrom math import pi\n\n\ndef vout")])
        self.assertIn("ERROR: calc.py imports 'os'", text)
        self.assertNotIn("'math'", text)

    def test_missing_example_function(self):
        text = self.run_edit(calc_edits=[('("vout", {"vref"', '("nofn", {"vref"')])
        self.assertIn("ERROR: example function 'nofn' does not exist", text)

    def test_inputs_good_missing_and_bad(self):
        self.assertEqual(self.run_edit(), "")
        self.assertIn("WARN: calc.py has no INPUTS", self.run_edit(calc_edits=[('    "vout": {"vref": "vref"},\n', "")]))
        bad = self.run_edit(calc_edits=[('"vout": {"vref": "vref"}', '"nofn": {}, "vout": {"vref": "nokey", "zz": "vref"}')])
        self.assertIn("INPUTS: function 'nofn' does not exist", bad)
        self.assertIn("INPUTS: vout.vref -> unknown param key 'nokey'", bad)
        self.assertIn("INPUTS: vout has no argument 'zz'", bad)

    def test_inputs_field_syntax(self):
        self.assertEqual(self.run_edit(calc_edits=[('"vout": {"vref": "vref"}', '"vout": {"vref": "vref.max"}')]), "")
        bad = self.run_edit(calc_edits=[('"vout": {"vref": "vref"}', '"vout": {"vref": "vref.mid"}')])
        self.assertIn("field must be min, typ or max", bad)


class TestSymbolFormat(unittest.TestCase):
    """The symbol must be KiCad 10 format (version 20251024 or newer): pcb apply rejects older libraries."""
    HEADER = "(kicad_symbol_lib (version 20251024)"

    def run_header(self, new_header):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            sym = copy / "LDO1.kicad_sym"
            text = sym.read_text()
            assert self.HEADER in text
            sym.write_text(text.replace(self.HEADER, new_header, 1))
            return messages(copy)

    def test_kicad6_symbol_is_error(self):
        out = self.run_header("(kicad_symbol_lib (version 20211014)")
        self.assertEqual(len(out), 1)
        self.assertIn("ERROR: LDO1.kicad_sym: format version 20211014; KiCad 10 format (20251024 or newer)", out[0])
        self.assertIn("kicad-cli sym upgrade --force", out[0])

    def test_kicad10_symbol_is_clean(self):
        self.assertEqual(messages(FIX / "LDO1"), [])
        self.assertEqual(self.run_header(self.HEADER), [])

    def test_missing_version_is_error(self):
        out = self.run_header("(kicad_symbol_lib")
        self.assertEqual(len(out), 1)
        self.assertIn("ERROR: LDO1.kicad_sym: no integer (version N) in its header", out[0])

    def test_footprint_is_not_checked_for_version(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            fp = copy / "LDO1.kicad_mod"
            fp.write_text(fp.read_text().replace("(version 20241229)", "(version 20211014)", 1))
            self.assertEqual(messages(copy), [])


class TestExampleTolerance(unittest.TestCase):
    def test_relative_and_absolute(self):
        from lib.component import run_example
        calc = type("C", (), {"f": staticmethod(lambda x: x)})
        self.assertTrue(run_example(calc, ("f", {"x": 100.05}, 100.0, 1e-3, ""))[1])  # relative
        self.assertFalse(run_example(calc, ("f", {"x": 100.5}, 100.0, 1e-3, ""))[1])
        self.assertTrue(run_example(calc, ("f", {"x": 0.0005}, 0, 1e-3, ""))[1])  # absolute at 0
        self.assertFalse(run_example(calc, ("f", {"x": 0.005}, 0, 1e-3, ""))[1])


class TestLoad(unittest.TestCase):
    def test_load_si(self):
        part = load(str(FIX / "LDO1"))
        self.assertEqual(part.info["mpn"], "LDO1R")
        self.assertEqual(len(part.pins), 3)
        self.assertAlmostEqual(part.param("vref").max, 1.01)
        self.assertEqual(part.param("vref").unit, "V")
        self.assertEqual(part.calc.vout(1.0, 10e3, 10e3), 2.0)
        with self.assertRaises(KeyError):
            part.param("nope")


class TestLoadNew(unittest.TestCase):
    def setUp(self):
        self.part = load(str(FIX / "LDO1"))

    def test_inputs_helper(self):
        whole = self.part.inputs("vout")["vref"]
        self.assertAlmostEqual(whole.max, 1.01)
        self.assertEqual(self.part.inputs("nofn"), {})

    def test_sym(self):
        p = self.part.param("vos")
        self.assertEqual((p.min, p.typ, p.max), (-40e-6, 0.0, 40e-6))  # sym typ is centred
        self.assertAlmostEqual(p.typ_spread, 10e-6)

    def test_typ_pm(self):
        p = self.part.param("gain_err")
        self.assertEqual((p.typ, p.typ_spread, p.unit), (0.0, 0.00025, "1"))
        self.assertAlmostEqual(p.max, 0.001)

    def test_text_and_ppm(self):
        self.assertEqual(self.part.param("io_cont").text, "Continuous")
        self.assertAlmostEqual(self.part.param("tc").max, 50e-6)
        self.assertEqual(self.part.param("tc").unit, "1/degC")

    def test_resolve_floats(self):
        p = self.part.resolve("vcm", {"GND": 0.0, "IN": 15.0})
        self.assertEqual((p.min, p.max, p.min_ref), (2.0, 13.0, None))

    def test_resolve_params(self):
        gnd = Param(min=-0.1, max=0.1)
        rail = Param(min=14.0, max=16.0)
        p = self.part.resolve("vcm", {"GND": gnd, "IN": rail})
        self.assertAlmostEqual(p.min, 2.1)  # offset + rail.max
        self.assertAlmostEqual(p.max, 12.0)  # offset + rail.min

    def test_resolve_errors_and_passthrough(self):
        with self.assertRaises(ValueError) as cm:
            self.part.resolve("vcm", {"GND": 0.0})
        self.assertIn("'IN'", str(cm.exception))
        self.assertIs(self.part.resolve("vref", {}), self.part.param("vref"))

    def test_sym_load_error(self):
        from lib.component import to_param
        with self.assertRaises(ValueError):
            to_param({"sym": True, "min": 1, "unit": "V"})


class TestLedger(unittest.TestCase):
    """lib.check on review/: ledger-only checks always; cache images only when the PDF is on this machine."""

    def ledger(self, d, rows=None, files=None, pdf=True, raw=None, stamps=None, raw_inputs=""):
        """root/components/Acme/LDO1 with a review.toml holding a correct row per Param, `rows` merged in (key ->
        fields), cache files in root/.review-cache/Acme/LDO1/, and the PDF in docs/datasheets/ unless pdf=False."""
        import json
        import tomllib
        from lib.component import pinout_hash, row_hash
        root = Path(d)
        copy = root / "components" / "Acme" / "LDO1"
        copy.parent.mkdir(parents=True)
        copytree(FIX / "LDO1", copy, ignore=lambda *_: ["__pycache__"])
        ct = copy / "component.toml"
        for key, stamp in (stamps or {}).items():  # a `verified` line after the row's header
            ct.write_text(ct.read_text().replace(f"[param.{key}]\n", f'[param.{key}]\nverified = "{stamp}"\n', 1))
        params = tomllib.loads(ct.read_text())["param"]
        table = {k: {"state": "NEW", "hash": row_hash(t)} for k, t in params.items()}
        for k, stamp in (stamps or {}).items():
            table[k].update(state="MACHINE_CHECKED", stamp=stamp, stamp_hash=table[k]["hash"])
        for k, extra in (rows or {}).items():
            table.setdefault(k, {}).update(extra)
        text = raw if raw is not None else '[inputs]\ndatasheet_file = "docs/datasheets/ldo1.pdf"\n' + raw_inputs + "".join(
            f"[row.{k}]\n" + "".join(f"{f} = {json.dumps(v)}\n" for f, v in r.items()) for k, r in table.items())
        pins = tomllib.loads(ct.read_text()).get("pin")
        if raw is None and pins:  # the pinout record (docs/spec/review-view.md "Pinout stamp")
            text += f'[pinout]\nstate = "NEW"\nhash = "{pinout_hash(pins)}"\n'
        (copy / "review").mkdir()
        (copy / "review" / "review.toml").write_text(text)
        for name, data in (files or {}).items():
            f = root / ".review-cache" / "Acme" / "LDO1" / name
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
        if pdf:
            (root / "docs" / "datasheets").mkdir(parents=True)
            (root / "docs" / "datasheets" / "ldo1.pdf").write_bytes(b"%PDF")
        return copy

    def errors(self, copy):
        return "\n".join(m for m in messages(copy) if m.startswith("ERROR") and "review" in m)

    def test_stale_note_not_counted(self):
        import contextlib
        import io
        from lib import check
        with tempfile.TemporaryDirectory() as d:
            copy = self.ledger(d, {"vref": {"state": "STALE", "stamp_hash": "old"},
                                   "vos": {"state": "PDF_CHANGED", "pdf_sha256": "pin"}},
                               stamps={"vref": "bob 2026-01-01 page image", "vin_abs": "bob 2026-01-01 page image"},
                               raw_inputs='sheets = { "ldo1.pdf" = "now" }\n')
            self.assertEqual(self.errors(copy), "")
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                with mock.patch.object(check.rules, "wiring_findings", return_value=[]):
                    check.main([str(copy)])
        text = out.getvalue()
        self.assertIn("REVIEW: LDO1: vref is STALE", text)
        self.assertIn("REVIEW: LDO1: vos is PDF_CHANGED", text)
        self.assertNotIn("vin_abs", text)
        self.assertIn("review: evidence mode (PDF present) in 1 part(s)", text)

    def test_cache_image_missing_and_hash_mismatch_with_pdf(self):
        import hashlib
        good = hashlib.sha256(b"png").hexdigest()
        row = {"vref": {"image": "evidence/a.png", "image_sha256": good, "header_image": "evidence/h.png",
                        "header_sha256": good}}
        with tempfile.TemporaryDirectory() as d:
            text = self.errors(self.ledger(d, row, {"evidence/h.png": b"png"}))
        self.assertIn(".review-cache/Acme/LDO1/evidence/a.png missing (vref; PDF present): rerun python3 tools/ds_review.py", text)
        with tempfile.TemporaryDirectory() as d:
            text = self.errors(self.ledger(d, row, {"evidence/a.png": b"other", "evidence/h.png": b"png"}))
        self.assertIn("evidence/a.png sha256 differs from review.toml (vref): delete it and rerun", text)
        self.assertNotIn("h.png", text)
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.errors(self.ledger(d, row, {"evidence/a.png": b"png", "evidence/h.png": b"png"})), "")

    def test_ledger_only_mode_without_pdf(self):
        from lib import check
        row = {"vref": {"image": "evidence/a.png", "image_sha256": "0" * 64}}
        with tempfile.TemporaryDirectory() as d:
            check.REVIEW_MODES.clear()
            self.assertEqual(self.errors(self.ledger(d, row, pdf=False)), "")  # no cache, no PDF: images not checked
            self.assertEqual(check.review_mode_line(), "review: ledger-only mode (no local PDF) in 1 part(s): LDO1")

    def test_row_hash_stamp_and_committed_png(self):
        with tempfile.TemporaryDirectory() as d:
            text = self.errors(self.ledger(d, {"vref": {"hash": "x"}, "vos": {"stamp": "bob 2026-11-20 x"}}, pdf=False))
        self.assertIn("row vref is missing or older than component.toml", text)
        self.assertIn("row vos: stamp differs from its verified line", text)
        with tempfile.TemporaryDirectory() as d:
            copy = self.ledger(d, pdf=False)
            for name in ("evidence/a.png", "params/vref.md", "DELTA.md", "github-issue.md", "unmapped.md", "README.md"):
                (copy / "review" / name).parent.mkdir(exist_ok=True)
                (copy / "review" / name).write_bytes(b"x")
            (copy / "review" / ".DS_Store").write_bytes(b"x")  # OS litter (git-ignored) is not a finding
            text = self.errors(copy)
            for name in ("evidence/a.png", "params/vref.md", "DELTA.md", "github-issue.md", "unmapped.md", "README.md"):
                self.assertIn(f"review/{name}: only review/review.toml is committed", text)
            self.assertNotIn(".DS_Store", text)

    def test_state_is_recomputed_never_trusted(self):
        machine = "sonnet-audit 2026-11-18 blind page-image reading"
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(self.errors(self.ledger(d, stamps={"vref": machine}, pdf=False)), "")
        cases = ({"vref": {"state": "HUMAN_VERIFIED"}}, {"vref": {"state": "BOGUS"}}, {"vos": {"state": "HUMAN_VERIFIED"}},
                 {"pins": {"state": "HUMAN_VERIFIED"}})
        for rows in cases:
            with self.subTest(rows=rows), tempfile.TemporaryDirectory() as d:
                text = self.errors(self.ledger(d, rows, stamps={"vref": machine}, pdf=False))
                key = next(iter(rows))
                self.assertIn(f"row {key}: ", text)
                self.assertTrue("but the stamp and pins give" in text or "must be 'NOT_COVERED'" in text, text)

    def test_invalid_toml_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            text = self.errors(self.ledger(d, raw="[row.vref\nstate = "))
        self.assertIn("ERROR: review/review.toml or component.toml is not valid TOML", text)


class TestPinoutName(unittest.TestCase):
    def test_param_pinout_is_reserved_and_the_error_states_the_fix(self):
        with tempfile.TemporaryDirectory() as d:
            copy = copy_fixture(d, [("[param.vref]", "[param.pinout]")])
            errs = [m for m in messages(copy) if "pinout" in m and m.startswith("ERROR")]
        self.assertTrue(any("[param.pinout]" in m and "reserved" in m and "rename" in m for m in errs), errs)


class TestReadme(unittest.TestCase):
    def test_datasheet_url_is_link(self):
        text = readme.build(FIX / "LDO1")
        self.assertIn("- **datasheet_url**: [https://example.com/ldo1.pdf](https://example.com/ldo1.pdf)", text)

    def test_new_rendering(self):
        text = readme.build(FIX / "LDO1")
        self.assertIn("| Output offset | VOS |  | \u00b110 | \u00b140 | uV |", text)  # sym
        self.assertIn("| Gain error |  | -0.1 | \u00b10.025 | 0.1 | % |", text)  # typ_pm
        self.assertIn("| Output current rating |  |  | Continuous |  | A | TA <= 70 degC |", text)  # text
        self.assertIn("| Common-mode range |  | 2 (rel. GND) |  | -2 (rel. IN) | V |", text)
        self.assertIn("Inputs:\n\n- `vref` -> `vref` (min 990 typ 1000 max 1010 mV)", text)

    def test_curve_marked(self):
        with tempfile.TemporaryDirectory() as d:
            copy = copy_fixture(d, [('unit = "ppm/degC"', 'unit = "ppm/degC"\ncurve = true')])
            self.assertIn("(curve) |", readme.build(copy))


    def test_generated_text(self):
        text = readme.build(FIX / "LDO1")
        self.assertTrue(text.startswith("<!-- GENERATED - do not edit"))
        self.assertIn("| 3 | OUT | power_out | Output | DS p.3, Pin Functions, OUT |", text)
        self.assertIn("## Parameters: abs_max", text)
        self.assertIn("| Reference voltage |  | 990 | 1000 | 1010 | mV | TA = 25 degC \\| IL = 1 mA Note: Characterized |", text)
        self.assertIn("### `vout`", text)
        self.assertNotIn("_hidden", text)
        self.assertIn("| vout(vref=1, r1=10000, r2=10000) | 2 | 2 | 0.001 | pass |", text)

    def test_deterministic_and_written(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            readme.main([str(copy)])
            first = (copy / "README.md").read_text()
            readme.main([str(copy / "component.toml")])
            self.assertEqual(first, (copy / "README.md").read_text())


if __name__ == "__main__":
    unittest.main()
