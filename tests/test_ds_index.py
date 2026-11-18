import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))
import ds_index  # noqa: E402
import phase3b_pdf as fx  # noqa: E402


def run_index(pdf, out, *extra):
    p = subprocess.run([sys.executable, str(ROOT / "tools" / "ds_index.py"), str(pdf), "--out", str(out), *extra],
                       capture_output=True, text=True)
    idx = json.loads((Path(out) / "index.json").read_text()) if (Path(out) / "index.json").exists() else None
    return p.returncode, p.stdout, idx


def item(idx, key):
    return [i for i in idx["items"] if i["key"] == key][0]


class TestDsIndex(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))

    def pdf(self, name, data):
        p = self.tmp / name
        p.write_bytes(data)
        return p

    def test_good_datasheet_statuses(self):
        pdf = self.pdf("good.pdf", fx.build_pdf(fx.datasheet_pages()))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        self.assertEqual(rc, 0)
        self.assertEqual(item(idx, "abs_max")["status"], "OK")
        self.assertEqual(item(idx, "abs_max")["hits"][0]["printed_page"], 1)
        self.assertEqual(item(idx, "pin_config")["status"], "OK")
        self.assertEqual(item(idx, "pin_config")["hits"][0]["printed_page"], 4)
        self.assertEqual(item(idx, "rec_op")["status"], "UNSURE")        # found twice
        self.assertEqual(item(idx, "electrical")["status"], "UNSURE")    # continued table
        self.assertIn("continued", item(idx, "electrical")["reason"])

    def test_missing_table_is_listed_never_complete(self):
        pdf = self.pdf("good.pdf", fx.build_pdf(fx.datasheet_pages()))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        self.assertIn("esd", idx["not_found"])
        self.assertFalse(idx["complete"])
        self.assertEqual(item(idx, "esd")["status"], "UNSURE")
        self.assertIn("not_found=[", out.splitlines()[-1])
        self.assertIn("esd", out.splitlines()[-1])

    def test_summary_line_counts(self):
        pdf = self.pdf("good.pdf", fx.build_pdf(fx.datasheet_pages()))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        last = out.strip().splitlines()[-1]
        self.assertTrue(last.startswith("summary: OK="))
        self.assertEqual(idx["summary"]["OK"], sum(1 for i in idx["items"] if i["status"] == "OK"))
        self.assertEqual(idx["summary"]["UNSURE"], sum(1 for i in idx["items"] if i["status"] == "UNSURE"))

    def test_no_printed_page_number_is_unsure(self):
        pages = [[t for t in pg if not (t[0] == 300 and t[1] == 760)] for pg in fx.datasheet_pages()]
        pdf = self.pdf("nopage.pdf", fx.build_pdf(pages))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        it = item(idx, "abs_max")
        self.assertEqual(it["status"], "UNSURE")
        self.assertIn("printed page", it["reason"])

    def test_rotated_page_is_never_ok(self):
        pdf = self.pdf("rot.pdf", fx.build_pdf(fx.datasheet_pages(), rotate=(1, 2, 3, 4)))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        self.assertNotIn("OK", [i["status"] for i in idx["items"] if i["kind"] == "section"] or [])

    def test_subtitle_title_is_unsure(self):
        pages = fx.datasheet_pages()
        pages[0].append((40, 600, 14, "6.2 ESD Ratings - HBM only"))
        rc, out, idx = run_index(self.pdf("s.pdf", fx.build_pdf(pages)), self.tmp / "o")
        self.assertEqual(item(idx, "esd")["status"], "UNSURE")

    def test_scanned_pdf_fails(self):
        pdf = self.pdf("scan.pdf", fx.build_pdf(fx.datasheet_pages(), scanned=(1, 2, 3, 4)))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        self.assertEqual(rc, 1)
        self.assertEqual(idx["status"], "FAIL")
        self.assertIn("no text layer", idx["reason"])
        self.assertFalse(idx["complete"])

    def test_missing_file_fails(self):
        rc, out, idx = run_index(self.tmp / "nope.pdf", self.tmp / "o")
        self.assertEqual(rc, 1)
        self.assertEqual(idx["status"], "FAIL")

    def test_empty_and_truncated_files_fail(self):
        good = fx.build_pdf(fx.datasheet_pages())
        for name, data in (("empty.pdf", b""), ("trunc.pdf", good[: len(good) // 2]), ("junk.pdf", b"hello" * 100)):
            rc, out, idx = run_index(self.pdf(name, data), self.tmp / ("o_" + name))
            self.assertEqual(rc, 1, name)
            self.assertEqual(idx["status"], "FAIL", name)

    def test_zero_matches_fails(self):
        pages = [[(40, 80, 12, "Some unrelated prose " + "word " * 12), (300, 760, 9, str(n))] for n in range(1, 5)]
        rc, out, idx = run_index(self.pdf("none.pdf", fx.build_pdf(pages)), self.tmp / "o")
        self.assertEqual(rc, 1)
        self.assertEqual(idx["status"], "FAIL")
        self.assertIn("zero titles", idx["reason"])

    def test_crops_and_dpi(self):
        pdf = self.pdf("good.pdf", fx.build_pdf(fx.datasheet_pages()))
        rc, out, idx = run_index(pdf, self.tmp / "o")
        h = item(idx, "abs_max")["hits"][0]
        self.assertGreaterEqual(h["dpi"], 200)
        self.assertTrue((self.tmp / "o" / h["crop"]).is_file())
        self.assertEqual((self.tmp / "o" / h["crop"]).read_bytes()[:4], b"\x89PNG")

    def test_deterministic_bytes(self):
        pdf = self.pdf("good.pdf", fx.build_pdf(fx.datasheet_pages()))
        h = []
        for n in ("a", "b"):
            run_index(pdf, self.tmp / n)
            d = hashlib.sha256()
            for f in sorted((self.tmp / n).rglob("*")):
                if f.is_file():
                    d.update(f.relative_to(self.tmp / n).as_posix().encode() + f.read_bytes())
            h.append(d.hexdigest())
        self.assertEqual(h[0], h[1])

    def test_classify_rejects_toc_and_prose(self):
        self.assertEqual(ds_index.classify("7.1 Absolute Maximum Ratings ........ 5"), ())
        self.assertEqual(ds_index.classify("See the Electrical Characteristics table for details"), ())
        self.assertEqual(ds_index.classify("Electrical characteristics are given in the table below"), ())
        self.assertEqual(ds_index.classify("7.5 Electrical Characteristics")[0][1], "electrical")

    def test_no_space_text_layer_is_unsure(self):
        self.assertEqual(ds_index.classify("Table2Maximumratings")[0][2], "nospace")


if __name__ == "__main__":
    unittest.main()
