"""tools/ds_review.py against docs/spec/review.md: checks, records, images, incremental runs, guards, doc sizes."""
import ast
import contextlib
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import ds_review as R  # noqa: E402
import phase3b_pdf as fx  # noqa: E402
import table_xcheck as T  # noqa: E402

COMP = "components/Acme/X"
URL = "https://example.com/x.pdf"
STAMP = "tester 2026-11-20 page-image ds_review abc"
HEAD = ('[part]\nvalue = "X"\nmanufacturer = "Texas Instruments"\ndatasheet_url = "%s"\n'
        'datasheet_file = "docs/datasheets/x.pdf"\ndatasheet_rev = "REV A"\n' % URL)


def prow(key, symbol, unit, cite="DS p.2, 6.5 Electrical Characteristics, x", **kw):
    lines = ["", "[param.%s]" % key, 'name = "n %s"' % key, 'symbol = "%s"' % symbol, 'kind = "electrical"',
             'scope = "25C"', 'unit = "%s"' % unit, 'conditions = ""', 'cite = "%s"' % cite]
    lines += ["%s = %s" % (k, ('"%s"' % v) if isinstance(v, str) else str(v).lower() if isinstance(v, bool) else v)
              for k, v in kw.items()]
    return "\n".join(lines) + "\n"


BODY = (prow("vos", "VOS", "uV", typ=10, max=35, verified=STAMP)       # clean row: AGREE, auto crop, stamped
        + prow("vos_bad", "VOS", "uV", typ=10, max=36)                # DISAGREE must fire
        + prow("iq", "IQ", "mA", typ=1.2, max=2)                      # two IQ lines: UNSURE, fallback
        + prow("wrap", "WRAP", "V", typ=3, max=4)                     # continuation line: UNSURE, fallback
        + prow("nocite", "VOS", "uV", cite="somewhere", typ=10)       # NOT_FOUND
        + prow("aol", "AOL", "dB", min=100, typ=120)                  # footnote marker
        + prow("absr", "", "V", cite="DS p.1, 6.1 Absolute Maximum Ratings, x", max=6))  # no symbol: table


def encrypted(pdf):
    """The same PDF with a Standard security handler whose user password is not empty: poppler cannot open it."""
    enc = b"/Encrypt << /Filter /Standard /V 1 /R 2 /O <%s> /U <%s> /P -4 >> /ID [<%s> <%s>] >>" % (
        b"11" * 32, b"22" * 32, b"33" * 16, b"33" * 16)
    return pdf.replace(b"/Root 1 0 R >>", b"/Root 1 0 R " + enc)


def git(root, *args):
    subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-c", "commit.gpgsign=false",
                    "-C", str(root)] + list(args), check=True, capture_output=True)


class Base(unittest.TestCase):
    PDF = fx.build_pdf(fx.datasheet_pages())

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.make()

    def tearDown(self):
        self.tmp.cleanup()

    def make(self, body=BODY, pdf=None):
        (self.root / COMP).mkdir(parents=True, exist_ok=True)
        (self.root / COMP / "component.toml").write_text(HEAD + body)
        (self.root / "docs/datasheets").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/datasheets/x.pdf").write_bytes(self.PDF if pdf is None else pdf)
        (self.root / "docs/spec").mkdir(parents=True, exist_ok=True)
        (self.root / "docs/spec/review.md").write_text("contract")  # README links to it

    def run_r(self, *args):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = R.main(["--root", str(self.root)] + (list(args) or [COMP]))
        return rc, buf.getvalue()

    @property
    def rdir(self):
        return self.root / COMP / "review"

    @property
    def cdir(self):  # git-ignored local evidence cache
        return self.root / ".review-cache" / "Acme" / "X"

    def csnap(self):
        return {str(p.relative_to(self.cdir)): p.read_bytes() for p in sorted(self.cdir.rglob("*")) if p.is_file()}

    def ledger(self):
        return tomllib.loads((self.rdir / "review.toml").read_text())

    def rows(self):
        return self.ledger()["row"]

    def snap(self):
        out = {str(p.relative_to(self.rdir)): p.read_bytes() for p in sorted(self.rdir.rglob("*")) if p.is_file()}
        return {**out, **self.csnap()} if self.cdir.is_dir() else out  # committed record + local cache (no overlap)

    def edit(self, old, new):
        p = self.root / COMP / "component.toml"
        t = p.read_text()
        self.assertIn(old, t)
        p.write_text(t.replace(old, new, 1))


class TestChecks(Base):
    def test_disagree_fires_and_mutation_agrees(self):
        self.run_r()
        self.assertEqual(self.rows()["vos_bad"]["status"], "DISAGREE")
        self.assertIn("MAX", self.rows()["vos_bad"]["reason"])
        self.assertEqual(self.rows()["vos"]["status"], "AGREE_TEXT_CHECK")
        self.edit("max = 36", "max = 35")  # the mutation removes the defect: the check must flip
        self.run_r()
        self.assertEqual(self.rows()["vos_bad"]["status"], "AGREE_TEXT_CHECK")

    def test_missing_or_unparseable_cite_is_not_found(self):
        self.run_r()
        r = self.rows()["nocite"]
        self.assertEqual(r["status"], "NOT_FOUND")
        self.assertNotIn("image", r)
        self.make(BODY + prow("farpage", "VOS", "uV", cite="DS p.77, x", typ=10))
        self.run_r()
        self.assertEqual(self.rows()["farpage"]["status"], "NOT_FOUND")

    def test_ambiguous_and_continued_rows_are_unsure_with_fallback(self):
        self.run_r()
        for k in ("iq", "absr"):
            r = self.rows()[k]
            self.assertEqual(r["status"], "UNSURE", k)
            self.assertEqual(r["crop"], "fallback", k)
            self.assertTrue((self.cdir / r["image"]).is_file(), k)
        self.assertIn("on 2 lines", self.rows()["iq"]["reason"])
        w = self.rows()["wrap"]  # a wrapped row is cropped as its row group; the text check stays UNSURE
        self.assertEqual((w["status"], w["crop"]), ("UNSURE", "auto"))
        self.assertIn("row group of 2 lines", w["reason"])
        self.assertTrue(self.rows()["absr"]["image"].startswith("evidence/table_p1_"))

    def test_no_text_layer_is_unsure_full_page(self):
        self.make(pdf=fx.build_pdf(fx.datasheet_pages(), scanned=(1, 2, 3, 4)))
        self.assertEqual(self.run_r()[0], 0)
        r = self.rows()["vos"]
        self.assertEqual((r["status"], r["crop_box"], r["image"]), ("UNSURE", "full_page", "evidence/page_p2.png"))
        self.assertIn("no text layer", r["reason"])

    def test_bad_encrypted_pdf_fail(self):
        for pdf, why in ((self.PDF[:300], "truncated"), (b"hello" * 50, "not a PDF"),
                         (encrypted(self.PDF), "poppler cannot open")):
            self.make(pdf=pdf)
            rc, out = self.run_r()
            self.assertEqual(rc, 1, why)
            self.assertIn("FAIL:", out)
            self.assertIn(why, out)

    def test_missing_poppler_fails(self):
        env = dict(os.environ, PATH="/nonexistent")
        p = subprocess.run([sys.executable, str(ROOT / "tools/ds_review.py"), "--root", str(self.root), COMP],
                           capture_output=True, text=True, env=env)
        self.assertEqual(p.returncode, 1)
        self.assertIn("FAIL: poppler not found", p.stdout)
        self.assertIn("brew install poppler", p.stdout)

    def test_bad_dir_fails(self):
        rc, out = self.run_r("components/Acme/Nope")
        self.assertEqual(rc, 1)
        self.assertIn("not a component dir", out)

    def test_status_matches_table_xcheck(self):
        self.run_r()
        rows, fatal = T.check_rows(str(self.root / "docs/datasheets/x.pdf"), str(self.root / COMP / "component.toml"))
        self.assertIsNone(fatal)
        mapping = {"AGREE": "AGREE_TEXT_CHECK", "DISAGREE": "DISAGREE", "UNSURE": "UNSURE"}
        for k, st, _w in rows:
            if k != "nocite":
                self.assertEqual(self.rows()[k]["status"], mapping[st], k)


class TestRecords(Base):
    def test_one_image_and_params_file_per_param(self):
        self.run_r()
        params = tomllib.loads((self.root / COMP / "component.toml").read_text())["param"]
        self.assertEqual(sorted(p.stem for p in (self.cdir / "params").iterdir()), sorted(params))
        for k in params:
            r = self.rows()[k]
            if r["status"] != "NOT_FOUND":
                self.assertTrue((self.cdir / r["image"]).is_file(), k)
            if r.get("crop") == "auto":
                self.assertEqual(r["image"], "evidence/%s_p%d.png" % (k, r["pdf_page"]))
        autos = [r["image"] for r in self.rows().values() if r.get("crop") == "auto"]
        self.assertEqual(len(autos), len(set(autos)))

    def test_markdown_links_resolve(self):
        self.run_r()
        for md in list(self.rdir.rglob("*.md")) + list(self.cdir.rglob("*.md")):
            for target in re.findall(r"\]\(([^)#\s]+)\)", md.read_text()):
                if not target.startswith("http"):
                    self.assertTrue((md.parent / target).exists(), "%s -> %s" % (md.name, target))

    def test_toml_snippet_is_source_bytes(self):
        self.run_r()
        src = (self.root / COMP / "component.toml").read_text().split("\n")
        for k, r in self.rows().items():
            if "toml_lines" not in r:
                continue
            a, b = map(int, r["toml_lines"].split("-"))
            block = re.search(r"```toml\n(.*?)\n```", (self.cdir / "params" / (k + ".md")).read_text(), re.S).group(1)
            self.assertEqual(block, "\n".join(src[a - 1:b]), k)
            self.assertTrue(block.startswith("[param.%s]" % k))

    def test_hashes_recorded_and_component_untouched(self):
        ct = self.root / COMP / "component.toml"
        before = ct.read_bytes()
        self.run_r()
        self.assertEqual(ct.read_bytes(), before)
        inp = self.ledger()["inputs"]
        self.assertEqual(inp["pdf_sha256"], hashlib.sha256(self.PDF).hexdigest())
        self.assertEqual(inp["component_sha256"], hashlib.sha256(before).hexdigest())
        for k, r in self.rows().items():
            if r.get("image"):
                self.assertEqual(r["image_sha256"], hashlib.sha256((self.cdir / r["image"]).read_bytes()).hexdigest())
        self.assertFalse(list(self.root.rglob("*.pdf"))[1:])  # only the source PDF exists; none copied

    def test_issue_draft_present_only_with_questions(self):
        self.run_r()
        self.assertTrue((self.cdir / "github-issue.md").is_file())
        self.make(prow("vos", "VOS", "uV", typ=10, max=35))
        self.run_r()
        self.assertFalse((self.cdir / "github-issue.md").exists())
        self.assertIn("NOT_COVERED", self.ledger()["row"]["pins"]["state"])

    def test_page_links_and_stamp_template(self):
        self.run_r()
        t = (self.cdir / "params/vos.md").read_text()
        self.assertIn("(%s#page=2)" % URL, t)
        sha = hashlib.sha256(self.PDF).hexdigest()[:12]
        self.assertIn("`python3 tools/stamp.py X:vos`", t)
        self.assertIn("text layer, unverified, not a source", t)

    def test_deterministic_across_roots(self):
        self.run_r()
        a = self.snap()
        other = Base("setUp")
        other.setUp()
        try:
            other.run_r()
            self.assertEqual(a, other.snap())
        finally:
            other.tearDown()


class TestHardRules(Base):
    def test_writes_only_review_dir(self):
        outside = lambda: {str(p.relative_to(self.root)): p.read_bytes() for p in sorted(self.root.rglob("*"))
                           if p.is_file() and "/review/" not in str(p) and ".review-cache" not in str(p)}
        before = outside()
        self.run_r()
        self.assertEqual(before, outside())

    def test_pixels_are_the_pdftoppm_render(self):
        """No overlay or redraw: decode the PNG independently and compare with a fresh pdftoppm render."""
        import zlib
        self.run_r()
        r = self.rows()["vos"]
        b = (self.cdir / r["image"]).read_bytes()
        idat = b"".join(b[i + 8:i + 8 + int.from_bytes(b[i:i + 4], "big")] for i in self.chunks(b) if b[i + 4:i + 8] == b"IDAT")
        w, h = R.png_info(self.cdir / r["image"])["ihdr"][:2]
        raw, stride = zlib.decompress(idat), (w + 1) // 2 + 1
        got = []
        for y in range(h):
            row = raw[y * stride + 1:(y + 1) * stride]
            got += [v for byte in row for v in (byte >> 4, byte & 15)][:w]
        box, s = r["crop_box"], r["dpi"] / 72.0
        out = self.root / "fresh"
        subprocess.run(["pdftoppm", "-gray", "-r", str(r["dpi"]), "-f", "2", "-l", "2", "-x", str(int(box[0] * s)),
                        "-y", str(int(box[1] * s)), "-W", str(int((box[2] - box[0]) * s) + 1),
                        "-H", str(int((box[3] - box[1]) * s) + 1), "-singlefile",
                        str(self.root / "docs/datasheets/x.pdf"), str(out)], check=True)
        pgm = (self.root / "fresh.pgm").read_bytes()
        pix = pgm[len(pgm) - w * h:]
        self.assertEqual(got, [(v * 15 + 127) // 255 for v in pix])
        self.assertEqual(r["image_sha256"], hashlib.sha256(b).hexdigest())

    @staticmethod
    def chunks(b):
        i = 8
        while i < len(b):
            yield i
            i += 12 + int.from_bytes(b[i:i + 4], "big")

    def test_text_layer_cells_shown_raw(self):
        self.make(BODY + prow("vcm", "VCM", "V", min=-0.3, max=85))
        self.run_r()
        self.assertEqual(self.rows()["vcm"]["text_cells"]["min"], "–0.3")  # printed en dash kept, not normalised
        self.assertIn("| text layer | –0.3 |", (self.cdir / "params/vcm.md").read_text())


def tricky_pages():
    """datasheet_pages() with page 2 replaced: split symbol, footnote marker on the next line, merged unit cell."""
    hdr = [(40, 110, 8, "PARAMETER"), (330, 110, 8, "MIN"), (380, 110, 8, "TYP"), (430, 110, 8, "MAX"),
           (480, 110, 8, "UNIT")]
    p2 = [(40, 80, 14, "6.5 Electrical Characteristics")] + hdr + [
        (40, 130, 8, "V"), (45.4, 130, 8, "UV"), (80, 130, 8, "Hysteresis"), (330, 130, 8, "1"), (380, 130, 8, "2"),
        (430, 130, 8, "3"), (480, 130, 8, "mV"),
        (40, 160, 8, "TRR"), (80, 160, 8, "Recovery time"), (380, 160, 8, "50"), (480, 160, 8, "ns"),
        (134, 159, 6, "1)"),  # glued footnote marker, as Infineon prints "time 1)"
        (40, 190, 8, "TER"), (80, 190, 8, "Erase time"), (380, 190, 8, "10"), (430, 190, 8, "20"),
        (480, 215, 8, "s"),
        (40, 400, 7, "1)"), (52, 400, 7, "Defined by design."), fx.footer(2)]
    pages = fx.datasheet_pages()
    pages[1] = p2
    return pages


class TestReviewFindings(Base):
    BODY2 = (prow("vuv", "VUV", "mV", min=1, typ=2, max=3) + prow("trr", "TRR", "ns", typ=50)
             + prow("ter", "TER", "s", typ=10, max=20))

    def setUp(self):
        super().setUp()
        self.make(self.BODY2, pdf=fx.build_pdf(tricky_pages()))

    def test_split_symbol_row_line_in_text_block(self):
        self.run_r()
        r = self.rows()["vuv"]
        self.assertEqual((r["status"], r["crop"]), ("AGREE_TEXT_CHECK", "auto"))
        self.assertEqual(len(r["text_snippet"].split("\n")), 2, r["text_snippet"])
        self.assertIn("Hysteresis", r["text_snippet"])

    def test_footnote_marker_on_next_line_includes_footnotes(self):
        self.run_r()
        r = self.rows()["trr"]
        self.assertEqual(r["crop"], "auto")
        self.assertIn("footnotes shown", r["reason"])
        self.assertLess(r["crop_box"][3], 200)  # the row image is just the row
        self.assertLess(r["foot_box"][1], 400)
        self.assertGreater(r["foot_box"][3], 400)
        self.assertTrue((self.cdir / r["foot_image"]).is_file())

    def test_merged_unit_cell_falls_back(self):
        self.run_r()
        r = self.rows()["ter"]
        self.assertEqual((r["status"], r["crop"]), ("UNSURE", "fallback"))
        self.assertIn("no unit cell in the row group", r["reason"])

    def test_row_found_by_cite_label_without_symbol(self):
        self.make(self.BODY2 + prow("hyst", "", "mV", cite="DS p.2, 6.5 Electrical Characteristics, row Hysteresis",
                                    typ=2), pdf=fx.build_pdf(tricky_pages()))
        self.run_r()
        r = self.rows()["hyst"]
        self.assertEqual(r["crop"], "auto")
        self.assertIn("cite row label (Hysteresis)", r["reason"])
        self.assertEqual(r["crop_box"], self.rows()["vuv"]["crop_box"])


def matrix_pages(x_data=200):
    """datasheet_pages() with page 3 replaced by a matrix table. Unlabelled number lines start at x_data: left of the
    Typ heading (x 300) they are data rows; right of it they look like more column headings (TJ = 25 degC style)."""
    p3 = [(40, 80, 12, "Table 9. Matrix"), (40, 100, 8, "Symbol"), (100, 100, 8, "Code"), (300, 100, 8, "Typ"),
          (380, 100, 8, "Unit")]
    for n, y in enumerate((120, 135, 150, 165, 180)):
        p3 += [(x_data, y, 8, "55%d" % n), (x_data + 30, y, 8, "14%d" % n)]
    p3 += [(40, 195, 8, "IOO"), (100, 195, 8, "ITCM"), (300, 195, 8, "150"), (380, 195, 8, "mA"),
           (40, 210, 8, "IDD"), (100, 210, 8, "SRAM"), (300, 210, 8, "145"), (380, 210, 8, "mA"), fx.footer(3)]
    pages = fx.datasheet_pages()
    pages[2] = p3
    return pages


class TestLocateSafeguards(Base):
    def test_cite_label_match_must_show_committed_values(self):
        self.make(TestReviewFindings.BODY2 + prow("hyst_bad", "", "mV", typ=9,
                  cite="DS p.2, 6.5 Electrical Characteristics, row Hysteresis"), pdf=fx.build_pdf(tricky_pages()))
        self.run_r()
        r = self.rows()["hyst_bad"]
        self.assertEqual((r["crop"], r["status"]), ("fallback", "UNSURE"))
        self.assertIn("committed typ not printed in the matched row group", r["reason"])

    def test_unlabelled_data_rows_end_the_header(self):
        self.make(prow("idd", "IDD", "mA", typ=145, cite="DS p.3, Table 9. Matrix, row SRAM"), pdf=fx.build_pdf(matrix_pages()))
        self.run_r()
        r = self.rows()["idd"]
        self.assertEqual(r["crop"], "auto")
        self.assertLess(r["header_box"][3], 120)  # the header image stops above the first data line
        self.assertGreater(r["crop_box"][1], 200)  # the row image is the IDD line only

    def test_header_band_that_swallows_rows_falls_back(self):
        self.make(prow("idd", "IDD", "mA", typ=145, cite="DS p.3, Table 9. Matrix, row SRAM"),
                  pdf=fx.build_pdf(matrix_pages(x_data=320)))
        self.run_r()
        r = self.rows()["idd"]
        self.assertEqual(r["crop"], "fallback")
        self.assertIn("header band not found", r["reason"])

    def test_unvalidated_symbol_match_must_show_committed_values(self):
        # table_xcheck locates TRR but cannot compare (sym convention): the line is not validated, so the committed
        # number must be printed in the crop, else it is a wrong row (STM32 TRIM vs USER TRIM COVERAGE)
        self.make(prow("vuv", "VUV", "mV", min=1, typ=2, max=3) + prow("trr", "TRR", "ns", typ=99, sym=True),
                  pdf=fx.build_pdf(tricky_pages()))
        self.run_r()
        r = self.rows()["trr"]
        self.assertEqual(r["crop"], "fallback", r["reason"])
        self.assertIn("committed typ not printed", r["reason"])

    def test_cite_label_needs_every_word(self):
        self.make(TestReviewFindings.BODY2 + prow("hyst2", "", "mV", typ=2,
                  cite="DS p.2, 6.5 Electrical Characteristics, row Hysteresis Extra"), pdf=fx.build_pdf(tricky_pages()))
        self.run_r()
        self.assertEqual(self.rows()["hyst2"]["crop"], "fallback")


def ruled_pages():
    """A centred (TI-style) table: each symbol sits mid-group; full-width rules separate the rows (one light gray)."""
    p3 = [(40, 80, 12, "Table 9. Centred"), (40, 100, 8, "PARAMETER"), (330, 100, 8, "MIN"), (380, 100, 8, "TYP"),
          (430, 100, 8, "MAX"), (480, 100, 8, "UNIT")]
    p3 += [(180, 120, 8, "pkg A"), (380, 120, 8, "10"), (430, 120, 8, "35"),
           (40, 132, 8, "VA"), (70, 132, 8, "First"), (480, 132, 8, "uV"),
           (180, 144, 8, "pkg B"), (380, 144, 8, "10"), (430, 144, 8, "40")]
    ys = (158, 170, 182, 194, 206, 218, 230)  # even spacing: cond 1 is nearer VA's label than VB's (text alone fails)
    p3 += [t for n, y in enumerate(ys) for t in ((180, y, 8, "cond %d" % (n + 1)), (430, y, 8, str(75 + 5 * n)))]
    p3 += [(40, 194, 8, "VB"), (70, 194, 8, "Second"), (480, 194, 8, "uV"), fx.footer(3)]
    pages = fx.datasheet_pages()
    pages[2] = p3
    rules = [(3, 30, 106, 520, 0), (3, 30, 151, 520, 0.75), (3, 30, 238, 520, 0)]
    return fx.build_pdf(pages, rules=rules)


class TestRuledCells(Base):
    def test_row_group_is_the_ruled_cell(self):
        self.make(prow("va", "VA", "uV", typ=10, max=35, cite="DS p.3, Table 9. Centred, VA")
                  + prow("vb", "VB", "uV", max=90, cite="DS p.3, Table 9. Centred, VB"), pdf=ruled_pages())
        self.run_r()
        a, b = self.rows()["va"], self.rows()["vb"]
        self.assertEqual((a["crop"], b["crop"]), ("auto", "auto"), (a["reason"], b["reason"]))
        self.assertLessEqual(a["crop_box"][3], 152.5)  # VA stops at the light gray rule (151)
        self.assertGreaterEqual(b["crop_box"][1], 149.5)  # VB starts there: no line of VA in it, all 7 of its own
        self.assertGreaterEqual(b["crop_box"][3], 230)
        self.assertIn("row group of 7 lines", b["reason"])


class TestImages(Base):
    def test_header_shared_aligned_and_not_in_row_crop(self):
        self.run_r()
        a, b = self.rows()["vos"], self.rows()["vos_bad"]
        self.assertEqual(a["header_image"], b["header_image"])  # one header image per table
        self.assertEqual(a["header_sha256"], b["header_sha256"])
        hi, ri = R.png_info(self.cdir / a["header_image"]), R.png_info(self.cdir / a["image"])
        self.assertEqual(hi["ihdr"][0], ri["ihdr"][0])  # same pixel width: the columns line up when stacked
        self.assertEqual((a["header_box"][0], a["header_box"][2]), (a["crop_box"][0], a["crop_box"][2]))
        self.assertLessEqual(a["header_box"][3], a["crop_box"][1] + 0.1)  # the row image holds no header
        t = (self.cdir / "params/vos.md").read_text()
        self.assertLess(t.index(a["header_image"]), t.index(a["image"]))
        self.assertIn("MIN", a["text_snippet"])  # the header's text travels with the row

    def test_png_format_metadata_budget(self):
        self.run_r()
        for p in (self.cdir / "evidence").iterdir():
            info = R.png_info(p)
            self.assertEqual(info["ihdr"][2:], (4, 0), p.name)  # bit depth 4, grayscale
            self.assertEqual(sorted(info["text"]), sorted(["Source", "Title", "Revision", "Page", "Copyright", "SHA256"]))
            self.assertNotIn("time", info)
            self.assertFalse(re.search(r"\d{4}-\d{2}-\d{2}|\d\d:\d\d", " ".join(info["text"].values())), p.name)
            self.assertLessEqual(p.stat().st_size, R.BUDGET, p.name)
            self.assertEqual(info["text"]["Source"], URL)

    def test_full_page_only_for_fallbacks(self):
        self.make(pdf=fx.build_pdf(fx.datasheet_pages(), scanned=(2,)))
        self.run_r()
        for k, r in self.rows().items():
            if r.get("crop_box") == "full_page":
                self.assertEqual(r["crop"], "fallback", k)
            if r.get("crop") == "auto":
                self.assertIsInstance(r["crop_box"], list)
        self.make()
        self.run_r()
        self.assertEqual(self.rows()["vos"]["crop"], "auto")
        self.assertFalse((self.cdir / "evidence/page_p2.png").exists())  # unreferenced image removed


class TestIncremental(Base):
    def test_second_run_zero_renders_byte_identical(self):
        self.run_r()
        a = self.snap()
        rc, out = self.run_r()
        self.assertIn("0 render(s), 0 file(s) changed", out)
        self.assertEqual(a, self.snap())

    def test_edit_one_param_only_that_row_stale(self):
        self.run_r()
        self.assertEqual(self.rows()["vos"]["state"], "MACHINE_CHECKED")
        a, rows_a = self.snap(), self.rows()
        self.edit('conditions = ""\ncite = "DS p.2, 6.5 Electrical Characteristics, x"\ntyp = 10\nmax = 35\nverified',
                  'conditions = "TA = 25 degC"\ncite = "DS p.2, 6.5 Electrical Characteristics, x"\ntyp = 10\nmax = 35\nverified')
        self.run_r()
        rows_b = self.rows()
        self.assertEqual(rows_b["vos"]["state"], "STALE")
        self.assertEqual({k for k in rows_b if rows_b[k] != rows_a.get(k)}, {"vos"})
        changed = {k for k in set(a) | set(self.snap()) if a.get(k) != self.snap().get(k)}
        allowed = {"review.toml", "DELTA.md", "README.md", "github-issue.md", "params/vos.md", "evidence/vos_p2.png"}
        self.assertTrue(changed <= allowed, changed - allowed)
        # a machine-stamped row is not a delta (DELTA lists human-stamped rows only); the README index lists it
        self.assertEqual((self.cdir / "DELTA.md").read_text(), "no human-stamped row changed since its stamp\n")
        self.assertIn("| [vos](params/vos.md) | AGREE_TEXT_CHECK | STALE |", (self.cdir / "README.md").read_text())
        self.edit(STAMP, "tester 2026-11-21 page-image ds_review abc")  # re-stamp
        self.run_r()
        self.assertEqual(self.rows()["vos"]["state"], "MACHINE_CHECKED")
        self.assertEqual(self.rows()["vos"]["stamp_hash"], self.rows()["vos"]["hash"])

    def test_stamp_removed_is_unverified(self):
        self.run_r()
        self.edit('\nverified = "%s"' % STAMP, "")
        self.run_r()
        self.assertEqual(self.rows()["vos"]["state"], "UNVERIFIED")
        self.assertEqual(self.rows()["iq"]["state"], "NEW")

    def test_pdf_change_makes_every_row_pdf_changed(self):
        self.run_r()
        pages = fx.datasheet_pages()
        pages[0].append((40, 600, 9, "revised"))
        self.make(body=(self.root / COMP / "component.toml").read_text()[len(HEAD):], pdf=fx.build_pdf(pages))
        self.run_r()
        located = {k: r for k, r in self.rows().items() if r["state"] != "NOT_COVERED" and k != "nocite"}
        self.assertEqual({r["state"] for r in located.values()}, {"PDF_CHANGED"})

    def test_missing_pdf_updates_ledger_only(self):
        self.run_r()
        imgs = {k: v for k, v in self.snap().items() if k.startswith("evidence/")}
        (self.root / "docs/datasheets/x.pdf").unlink()
        rc, out = self.run_r()
        self.assertEqual(rc, 0)
        self.assertEqual(self.ledger()["inputs"]["render"], "complete")  # nothing to render: unchanged rows
        self.assertEqual(imgs, {k: v for k, v in self.snap().items() if k.startswith("evidence/")})
        self.edit("max = 36", "max = 37")
        rc, out = self.run_r()
        self.assertEqual(rc, 0)
        self.assertIn("NOT_RENDERED", out)
        self.assertEqual(self.ledger()["inputs"]["render"], "NOT_RENDERED")
        self.assertIn("not re-checked", self.rows()["vos_bad"]["reason"])
        self.assertEqual(imgs, {k: v for k, v in self.snap().items() if k.startswith("evidence/")})
        self.assertNotEqual(self.rows()["vos_bad"]["hash"], self.rows()["vos_bad"].get("stamp_hash"))
        a = self.snap()  # a second run without the PDF still says NOT_RENDERED and changes nothing
        self.run_r()
        self.assertEqual(self.ledger()["inputs"]["render"], "NOT_RENDERED")
        self.assertEqual(a, self.snap())
        self.make(body=(self.root / COMP / "component.toml").read_text()[len(HEAD):])  # PDF back: re-checked
        self.run_r()
        self.assertEqual(self.ledger()["inputs"]["render"], "complete")
        self.assertEqual(self.rows()["vos_bad"]["status"], "DISAGREE")

    def test_first_run_without_pdf(self):
        (self.root / "docs/datasheets/x.pdf").unlink()
        rc, out = self.run_r()
        self.assertEqual(rc, 0)
        self.assertEqual(self.rows()["vos"]["status"], "NOT_FOUND")
        self.assertIn("PDF not on this machine", self.rows()["vos"]["reason"])
        self.assertEqual(self.ledger()["inputs"]["render"], "NOT_RENDERED")

    def test_backfill_stale_after_stamp(self):
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "stamped")
        self.edit("typ = 10\nmax = 35\nverified", "typ = 11\nmax = 35\nverified")
        git(self.root, "commit", "-qam", "changed after the stamp")
        self.make(body=(self.root / COMP / "component.toml").read_text()[len(HEAD):]
                  + prow("fresh", "IB", "nA", typ=0.1, max=0.5, verified=STAMP))  # uncommitted stamp
        self.run_r()
        self.assertEqual(self.rows()["vos"]["state"], "STALE")
        self.assertNotIn("baseline", self.rows()["vos"])
        self.assertIn("typ = 10", self.rows()["vos"]["stamped_toml"])
        self.assertEqual((self.rows()["fresh"]["state"], self.rows()["fresh"]["baseline"]), ("MACHINE_CHECKED", True))
        self.assertEqual(self.ledger()["inputs"]["backfill"], "git blame")

    def test_backfill_unchanged_is_baseline(self):
        git(self.root, "init", "-q")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-qm", "stamped")
        self.run_r()
        self.assertEqual((self.rows()["vos"]["state"], self.rows()["vos"]["baseline"]), ("MACHINE_CHECKED", True))

    def test_tampered_or_missing_image_fails_lib_check(self):
        from lib import check
        self.run_r()
        img = self.cdir / self.rows()["vos"]["image"]
        img.write_bytes(img.read_bytes() + b"x")
        msgs = [m for lvl, m in check.check_component(self.root / COMP) if lvl == "ERROR"]
        self.assertTrue(any("sha256 differs" in m for m in msgs), msgs)
        img.unlink()
        msgs = [m for lvl, m in check.check_component(self.root / COMP) if lvl == "ERROR"]
        self.assertTrue(any("missing" in m and "vos" in m for m in msgs), msgs)

    def test_tampered_image_is_not_relaundered(self):
        self.run_r()
        img = self.cdir / self.rows()["vos"]["image"]
        sha = self.rows()["vos"]["image_sha256"]
        img.write_bytes(img.read_bytes() + b"x")
        self.run_r()
        self.assertEqual(self.rows()["vos"]["image_sha256"], sha)  # ledger keeps the approved hash

    def test_deleted_param_image_removed(self):
        self.run_r()
        self.assertTrue((self.cdir / "evidence/vos_bad_p2.png").is_file())
        self.make(BODY.replace(prow("vos_bad", "VOS", "uV", typ=10, max=36), ""))
        self.run_r()
        self.assertFalse((self.cdir / "evidence/vos_bad_p2.png").exists())
        self.assertFalse((self.cdir / "params/vos_bad.md").exists())
        self.assertNotIn("vos_bad", self.rows())


def code_free_lines(text):
    return [ln for ln in re.sub(r"```.*?```", "", text, flags=re.S).split("\n")]


class TestStates(unittest.TestCase):
    """HUMAN_VERIFIED needs a human: stamp bound to this row hash and PDF; anything else never reaches it."""
    H, P = "a" * 64, "b" * 64

    def state(self, stamp, h=None, P=None):
        h, P = h or self.H, P or self.P
        return R.ledger_state(h, stamp, P, {}, lambda: (h, "", True))["state"]

    def human(self, row=None, pdf=None):
        return "human:alice 2026-11-20 page-image ds_review %s row %s" % ((pdf or self.P)[:12], (row or self.H)[:12])

    def test_machine_stamps_never_human_verified(self):
        for stamp in ("sonnet-audit 2026-11-18 blind page-image reading, cross-model (x)",
                      "sonnet-audit 2026-11-18 page-image ds_review %s row %s" % (self.P[:12], self.H[:12]),
                      "manufacturer-export 2026-11-14 product list", "human 2026-11-20 x", "Human:alice 2026-11-20 x"):
            self.assertEqual(self.state(stamp), "MACHINE_CHECKED", stamp)

    def test_human_stamp_bound_to_row_and_pdf(self):
        self.assertEqual(self.state(self.human()), "HUMAN_VERIFIED")
        self.assertEqual(self.state(self.human(row="c" * 64)), "STALE")
        self.assertEqual(self.state(self.human(pdf="c" * 64)), "PDF_CHANGED")
        for bad in ("human:", "human:alice 2026-11-20 x", self.human() + " ", "human:al_ice" + self.human()[11:]):
            self.assertEqual(self.state(bad), "UNVERIFIED", bad)
        self.assertEqual(self.state(""), "NEW")


class TestCache(Base):
    """Page images and params/<key>.md live in the git-ignored .review-cache/; the committed record has none."""

    def test_only_review_toml_committed_and_legacy_removed(self):
        self.rdir.mkdir(parents=True)
        for name in ("README.md", "DELTA.md", "github-issue.md", "unmapped.md"):
            (self.rdir / name).write_text("old")
        (self.rdir / "evidence").mkdir(parents=True)
        (self.rdir / "evidence" / "old.png").write_bytes(b"x")
        (self.rdir / "params").mkdir()
        (self.rdir / "params" / "old.md").write_text("x")
        rc, out = self.run_r()
        self.assertEqual(rc, 0, out)
        self.assertEqual(sorted(str(p.relative_to(self.rdir)) for p in self.rdir.rglob("*")), ["review.toml"])
        for name in ("README.md", "DELTA.md", "github-issue.md", "unmapped.md", "params/vos.md"):
            self.assertTrue((self.cdir / name).is_file(), name)
        self.assertTrue((self.cdir / self.rows()["vos"]["image"]).is_file())

    def test_ledger_only_rerun_leaves_committed_record_identical(self):
        from unittest import mock
        committed = lambda: {str(p.relative_to(self.rdir)): p.read_bytes() for p in sorted(self.rdir.rglob("*")) if p.is_file()}
        with mock.patch.object(R, "BUDGET", 1):  # every image over budget, so the README lists them
            self.run_r()
            before = committed()
            self.assertEqual(sorted(before), ["review.toml"])
            self.assertIn("image_bytes", before["review.toml"].decode())  # the size lives in the ledger, not the cache
            shutil.rmtree(self.cdir)  # CI: no cache ...
            (self.root / "docs/datasheets/x.pdf").unlink()  # ... and no PDF
            rc, out = self.run_r()
        self.assertIn("ledger-only mode", out)
        self.assertEqual(committed(), before)

    def test_mode_lines_and_rerender_compared(self):
        rc, out = self.run_r()
        self.assertIn("review: evidence mode (PDF present) in 1 part(s)", out)
        img = self.cdir / self.rows()["vos"]["image"]
        img.unlink()  # a fresh clone with the PDF: unchanged key, file missing -> re-render and compare
        rc, out = self.run_r()
        self.assertRegex(out, r"evidence mode \(PDF present\) in 1 part\(s\): [1-9]\d* image\(s\) re-rendered with an "
                              r"unchanged key, \d+ matched the ledger, 0 differ")
        self.assertTrue(img.is_file())
        (self.root / "docs/datasheets/x.pdf").unlink()
        rc, out = self.run_r()
        self.assertEqual(rc, 0)
        self.assertIn("review: ledger-only mode (no local PDF) in 1 part(s): X", out)

    def test_lib_check_modes(self):
        from lib import check
        self.run_r()
        check.REVIEW_MODES.clear()
        self.assertEqual([m for lvl, m in check.check_ledger(self.root / COMP) if lvl == "ERROR"], [])
        self.assertRegex(check.review_mode_line(), r"^review: evidence mode \(PDF present\) in 1 part\(s\): [1-9]\d* cache image")
        shutil.rmtree(self.cdir)
        (self.root / "docs/datasheets/x.pdf").unlink()  # CI: no PDF, no cache: ledger structure and hashes only
        check.REVIEW_MODES.clear()
        self.assertEqual([m for lvl, m in check.check_ledger(self.root / COMP) if lvl == "ERROR"], [])
        self.assertEqual(check.review_mode_line(), "review: ledger-only mode (no local PDF) in 1 part(s): X")

    def test_lib_check_ledger_only_still_checks_hashes_stamps_and_pngs(self):
        from lib import check
        self.run_r()
        (self.root / "docs/datasheets/x.pdf").unlink()
        self.edit("typ = 1.2", "typ = 1.3")  # iq row edited, record not rerun
        msgs = [m for lvl, m in check.check_ledger(self.root / COMP) if lvl == "ERROR"]
        self.assertTrue(any("row iq is missing or older" in m for m in msgs), msgs)
        self.edit("typ = 1.3", "typ = 1.2")
        self.edit(STAMP, "tester 2026-11-21 page-image ds_review abc")
        msgs = [m for lvl, m in check.check_ledger(self.root / COMP) if lvl == "ERROR"]
        self.assertTrue(any("row vos: stamp differs" in m for m in msgs), msgs)
        self.edit("tester 2026-11-21 page-image ds_review abc", STAMP)
        (self.rdir / "evidence").mkdir()
        (self.rdir / "evidence" / "x.png").write_bytes(b"x")
        msgs = [m for lvl, m in check.check_ledger(self.root / COMP) if lvl == "ERROR"]
        self.assertTrue(any("only review/review.toml is committed" in m for m in msgs), msgs)


class TestDocSizes(unittest.TestCase):
    def test_limits(self):
        doc = ast.get_docstring(ast.parse((ROOT / "tools/ds_review.py").read_text()))
        self.assertLessEqual(len(doc.split("\n")), 15)
        self.assertIn("docs/spec/review.md", doc)
        for path, limit in (("docs/spec/review.md", 40), ("docs/briefs/ds-review.md", 15),
                            ("docs/briefs/ds-review-model-prompt.md", 40)):
            self.assertLessEqual(len((ROOT / path).read_text().rstrip("\n").split("\n")), limit, path)

    def test_generated_records_within_limits(self):
        b = Base("setUp")
        b.setUp()
        try:
            b.run_r()
            readme = (b.cdir / "README.md").read_text()
            self.assertLessEqual(len(readme.split("## Rows to review")[0].rstrip("\n").split("\n")), 25)
            for p in (b.cdir / "params").iterdir():
                self.assertLessEqual(len(code_free_lines(p.read_text())), 40, p.name)
            for part in (ROOT / ".review-cache").glob("*/*/README.md"):
                self.assertLessEqual(len(part.read_text().split("## Rows to review")[0].rstrip("\n").split("\n")), 25)
        finally:
            b.tearDown()

    def test_rules_are_wired(self):
        """The prose rules that live outside this tool: CLAUDE.md, briefs, SPEC index, verify step."""
        self.assertIn("--datasheet-url", (ROOT / "CLAUDE.md").read_text())
        self.assertIn(".review-cache/<Mfr>/<Value>/DELTA.md", (ROOT / "CLAUDE.md").read_text())
        for brief in ("extractor.md", "verifier.md"):
            self.assertIn("docs/briefs/ds-review.md", (ROOT / "docs/briefs" / brief).read_text())
        self.assertIn("docs/spec/review.md", (ROOT / "docs/SPEC.md").read_text())
        self.assertIn("tools/ds_review.py", (ROOT / "tools/verify.py").read_text())


if __name__ == "__main__":
    unittest.main()
