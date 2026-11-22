"""lib.review_status (checked / needs check / reference), the README Checked column and tools/review.py (page, server,
one-button stamp + PR with injected runners; no real git, gh or network)."""
import contextlib
import datetime
import io
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "tests"))
import review as RV  # noqa: E402
import stamp as S  # noqa: E402
from lib import readme  # noqa: E402
from lib import review_status as RS  # noqa: E402
from test_ds_review import COMP, Base, Pins, prow  # noqa: E402
import phase3b_pdf as fx  # noqa: E402
from test_stamp import DAY, no_agent  # noqa: E402


class Stamped(Base):
    """A real ds_review record with X:iq human-stamped by alice and re-pinned (HUMAN_VERIFIED)."""

    def setUp(self):
        no_agent(self)
        super().setUp()
        self.assertEqual(self.run_r()[0], 0)
        rc, out = S.stamp(self.root, "alice", ["X:iq"], today=DAY)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.run_r()[0], 0)
        self.d = self.root / COMP


CALC_ALL = 'INPUTS = {"f": {"a": "iq.typ", "b": "vos", "c": "wrap", "d": "vos_bad", "e": "nocite", "g": "absr.max"}}\n'


class Status(Stamped):
    def calc(self, text='INPUTS = {"f": {"a": "iq.typ"}}\n'):
        (self.d / "calc.py").write_text(text)

    def test_three_states_and_counts(self):
        self.calc('INPUTS = {"f": {"a": "iq.typ", "b": "vos.max"}}\n')
        r = RS.review(self.d, self.root)
        self.assertEqual((r["status"]["iq"], r["status"]["vos"], r["status"]["aol"]), (RS.CHECKED, RS.NEEDS, RS.REFERENCE))
        self.assertEqual((r["k"], r["n"], r["M"], r["released"]), (1, 2, 7, False))
        self.assertEqual(RS.summary("X", r), ("X: 1 of 2 rows that matter checked", False))
        self.calc()
        r = RS.review(self.d, self.root)
        self.assertEqual((r["k"], r["n"], r["released"]), (1, 1, True))
        self.assertEqual(RS.summary("X", r), ("X: 1 of 1 rows that matter checked", True))

    def test_nothing_matters_is_not_released(self):
        r = RS.review(self.d, self.root)
        self.assertEqual((r["k"], r["n"], r["M"], r["released"]), (0, 0, 7, False))

    def test_pinout_row_counts_and_needs_check(self):
        self.calc()
        p = self.d / "component.toml"
        p.write_text(p.read_text() + '\n[[pin]]\nnumber = "1"\nname = "IN"\ntype = "input"\nfunction = "Input"\ncite = "DS p.1"\n')
        r = RS.review(self.d, self.root)
        self.assertEqual(r["status"]["pinout"], RS.NEEDS)
        self.assertEqual((r["k"], r["n"], r["M"], r["released"]), (1, 2, 8, False))

    def test_used_not_covered_is_listed_not_counted(self):
        self.calc('INPUTS = {"f": {"a": "iq.typ", "g": "gain.typ", "c": "capacitance"}}\n')
        (self.d / "variants.toml").write_text('[variant.V1]\nmpn = "a"\n[variant.V1.param.gain]\ntyp = 10\n')
        (self.d / "catalog.csv").write_text("value,capacitance\n1,2\n")
        r = RS.review(self.d, self.root)
        self.assertEqual(r["not_covered"], {"catalog.csv": ["capacitance"], "variants.toml": ["gain"]})
        self.assertEqual((r["k"], r["n"]), (1, 1))

    def test_catalog_label_only_for_catalog_columns(self):
        self.calc('INPUTS = {"f": {"a": "iq.typ", "g": "gain.typ", "c": "capacitance"}}\n')
        (self.d / "catalog.csv").write_text("value,tol\n1,2\n")
        self.assertEqual(RS.review(self.d, self.root)["not_covered"], {"unknown": ["capacitance", "gain"]})
        (self.d / "catalog.csv").write_text("value,gain\n1,2\n")
        self.assertEqual(RS.review(self.d, self.root)["not_covered"], {"catalog.csv": ["gain"], "unknown": ["capacitance"]})
        self.assertIn("(catalog.csv, unknown)", RS.readme_line("X", RS.review(self.d, self.root)))

    def test_variant_override_of_a_row_that_matters_is_listed_not_counted(self):
        self.calc('INPUTS = {"f": {"a": "iq.typ"}}\n')  # iq matters (used); aol is only a reference row
        (self.d / "variants.toml").write_text('[variant.V1]\nmpn = "a"\n[variant.V1.param.iq]\ntyp = 9\n'
                                              '[variant.V1.param.aol]\ntyp = 9\n')
        r = RS.review(self.d, self.root)
        self.assertEqual(r["not_covered"], {"variants.toml": ["variant.V1.iq"]})
        self.assertEqual((r["k"], r["n"]), (1, 1))
        self.assertIn("; 1 used values not covered (variants.toml)", RS.readme_line("X", r))

    def test_readme_line_wording(self):
        self.calc()
        r = RS.review(self.d, self.root)
        self.assertEqual(RS.readme_line("X", r), "Released: all 1 rows that matter checked (7 rows in all).")
        self.calc('INPUTS = {"f": {"a": "iq.typ", "b": "vos"}}\n')
        r = RS.review(self.d, self.root)
        self.assertEqual(RS.readme_line("X", r), "Checked by a person: 1 of 2 rows that matter (7 rows in all). "
                                                 "Review: python3 tools/review.py X")
        (self.d / "catalog.csv").write_text("value,capacitance\n1,2\n")
        self.calc('INPUTS = {"f": {"a": "iq.typ", "b": "vos", "c": "capacitance"}}\n')
        r = RS.review(self.d, self.root)
        self.assertEqual(RS.readme_line("X", r), "Checked by a person: 1 of 2 rows that matter (7 rows in all). "
                                                 "Review: python3 tools/review.py X; 1 used values not covered (catalog.csv)")

    def test_checked_only_with_a_bound_stamp_and_human_verified(self):
        self.assertEqual(RS.checked_rows(self.d), {"iq": ("alice", "2026-11-20")})
        self.edit("typ = 1.2\nmax = 2", "typ = 1.2\nmax = 3")  # row changed after the stamp
        self.assertEqual(RS.checked_rows(self.d), {})
        self.edit("typ = 1.2\nmax = 3", "typ = 1.2\nmax = 2")
        led = self.rdir / "review.toml"
        text = led.read_text()
        led.write_text(text.replace('state = "HUMAN_VERIFIED"', 'state = "NEW"'))
        self.assertEqual(RS.checked_rows(self.d), {}, "ledger not HUMAN_VERIFIED: not checked")
        led.write_text(text)
        pdf = self.root / "docs/datasheets/x.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.assertEqual(RS.checked_rows(self.d), {})  # local PDF differs
        self.assertEqual(RS.checked_rows(self.d, local_pdf=False), {"iq": ("alice", "2026-11-20")})  # ledger only

    def test_used_rows_and_component_dir(self):
        fam = self.root / "components/Acme/FAM"
        fam.mkdir(parents=True)
        (fam / "component.toml").write_text("")
        (fam / "variants.toml").write_text('[variant.FAM-1]\nmpn = "a"\n[variant.FAM-1.param.vth]\nmax = 1\n')
        got = RS.used_rows(self.root, ["X:iq", "X[sel]:vos", "FAM-1:vth", "FAM-1:abs",
                                       {"value": "X", "key": "aol", "input": "X:aol", "dir": COMP}])
        self.assertEqual(got, {self.d: {"iq", "vos", "aol"}, fam: {"variant.FAM-1.vth", "abs"}})
        self.assertEqual(RS.component_dir(self.root, "FAM-1"), (fam, "FAM-1"))
        with self.assertRaises(ValueError):
            RS.used_rows(self.root, ["Gone:x"])


class PinStamped(Pins, Stamped):
    """The same record with two [[pin]] entries, so the part has a pinout row."""

    def stamp_pinout(self):
        rc, out = S.stamp(self.root, "alice", ["X:pinout"], today=DAY)
        self.assertEqual(rc, 0, out)
        self.assertEqual(self.run_r()[0], 0)


class PinoutStatus(PinStamped):
    def test_current_pinout_stamp_is_checked_and_counts(self):
        (self.d / "calc.py").write_text('INPUTS = {"f": {"a": "iq.typ"}}\n')
        r = RS.review(self.d, self.root)
        self.assertEqual(r["status"]["pinout"], RS.NEEDS)
        self.assertEqual((r["k"], r["n"], r["released"]), (1, 2, False))
        self.stamp_pinout()
        for local in (True, False):
            r = RS.review(self.d, self.root, local_pdf=local)
            self.assertEqual((r["status"]["pinout"], r["k"], r["n"], r["released"]), (RS.CHECKED, 2, 2, True))
        self.assertEqual(RS.checked_rows(self.d)["pinout"], ("alice", "2026-11-20"))
        self.assertEqual(RS.readme_line("X", RS.review(self.d, self.root)),
                         "Released: all 2 rows that matter checked (8 rows in all).")

    def test_stale_or_changed_pdf_needs_check_again(self):
        self.stamp_pinout()
        self.edit('function = "Input"', 'function = "In"')
        self.assertEqual(RS.review(self.d, self.root)["status"]["pinout"], RS.NEEDS)  # before and after the rerun
        self.run_r()
        self.assertEqual(RS.review(self.d, self.root)["status"]["pinout"], RS.NEEDS)
        self.edit('function = "In"', 'function = "Input"')
        self.run_r()
        self.assertEqual(RS.review(self.d, self.root)["status"]["pinout"], RS.CHECKED)
        pdf = self.root / "docs/datasheets/x.pdf"
        pdf.write_bytes(pdf.read_bytes() + b"\n% changed\n")
        self.assertEqual(RS.review(self.d, self.root)["status"]["pinout"], RS.NEEDS)
        self.assertEqual(RS.review(self.d, self.root, local_pdf=False)["status"]["pinout"], RS.CHECKED)


class PinoutPage(PinStamped):
    def setUp(self):
        super().setUp()
        (self.d / "calc.py").write_text(CALC_ALL)
        t = (self.d / "component.toml").read_text()
        i = t.index("[param.absr]")
        (self.d / "component.toml").write_text(t[:i] + t[i:].replace('kind = "electrical"', 'kind = "abs_max"', 1))
        self.assertEqual(self.run_r()[0], 0)

    def model(self, used=None):
        return RV.build_model(self.root, {self.d: used})

    def test_pinout_row_is_tickable_when_stamp_would_accept_it(self):
        (part,) = self.model()
        item = next(i for i in part["items"] if i["key"] == "pinout")
        self.assertEqual((item["tier"], item["section"]), ("tier 3", "Pins & package"))
        self.assertEqual(item["images"], [("evidence/pinout_p4.png", "pin table page 4")])
        self.assertTrue(item["statement"].startswith("Pinout of X: 1 IN (input): Input"))
        self.assertEqual(item["page"][0], "docs/datasheets/x.pdf, PDF page 4")
        self.assertIn("pinout", [i["ref"].split(":")[1] for i in part["items"]])
        (self.cdir / "evidence/pinout_p4.png").unlink()  # stamp.py would refuse: no tick box
        (part,) = self.model()
        item = next(i for i in part["items"] if i["key"] == "pinout")
        self.assertEqual((item["tier"], item["images"]), ("fix", []))
        self.assertIn("no local evidence image", item["why"])
        page = RV.render("t", [part], "TOK", self.root, images={})
        self.assertNotIn('value="X:pinout"', page)
        self.assertEqual(page.count('class="ok"'), 3)  # vos, wrap, absr

    def test_pinout_shows_every_page_its_pins_cite(self):
        self.edit('function = "Output"\ncite = "DS p.4, Pin Functions"', 'function = "Output"\ncite = "DS p.1, Pin Functions"')
        self.run_r()
        (part,) = self.model()
        item = next(i for i in part["items"] if i["key"] == "pinout")
        self.assertEqual(item["tier"], "tier 3")
        self.assertEqual(item["page"][0], "docs/datasheets/x.pdf, PDF pages 1, 4")
        self.assertEqual(item["images"], [("evidence/pinout_p1.png", "pin table page 1"),
                                          ("evidence/pinout_p4.png", "pin table page 4")])
        images = {}
        page = RV.render("t", [part], "TOK", self.root, images=images)
        self.assertEqual(page.count("pin table page 1"), 2)  # caption and alt
        self.assertEqual(page.count("pin table page 4"), 2)
        self.assertEqual(page.count("<img class=big "), 4)  # absr table crop (stamped evidence) + both pinout pages + absr's located page when unlocated
        (self.cdir / "evidence/pinout_p1.png").unlink()  # one page missing: stamp.py refuses, no tick box
        (part,) = self.model()
        item = next(i for i in part["items"] if i["key"] == "pinout")
        self.assertEqual(item["tier"], "fix")

    def test_sections_in_order_with_statements(self):
        part = self.model()[0]
        sec = {i["key"]: i["section"] for i in part["items"]}
        self.assertEqual((sec["absr"], sec["vos"], sec["wrap"], sec["pinout"]), ("Limits", "Used by equations",
                                                                                 "Used by equations", "Pins & package"))
        page = RV.render("t", [part], "TOK", self.root, images={})
        heads = [page.index(f"<h3>{h}") for h in ("Limits", "Used by equations", "Pins &amp; package")]
        self.assertEqual(heads, sorted(heads))
        self.assertLess(page.index('id="row-X:absr"'), page.index('id="row-X:vos"'))
        self.assertLess(page.index('id="row-X:vos"'), page.index('id="row-X:pinout"'))
        self.assertIn("<b>VOS \u2014 n vos</b>", page)
        self.assertIn("<tr><th>Value</th><td>typ 10, max 35 \u00b5V</td></tr>", page)
        self.assertIn("<tr><th>Used by</th><td>f (b)</td></tr>", page)
        self.assertNotIn("scope 25C", page)
        self.assertIn("<b>Pinout of X</b>", page)  # the pin table: number, name, type, function
        self.assertIn("<tr><td>1</td><td>IN</td><td>input</td><td>Input</td></tr>", page)
        self.assertIn("<tr><td>2</td><td>OUT</td><td>output</td><td>Output</td></tr>", page)
        self.assertNotIn("Check:", page)

    def test_parts_fewest_needs_check_first_and_released_folded(self):
        import copy
        x = self.model()[0]
        a = copy.deepcopy(x)
        a.update(value="A", line="A: 0 of 1 rows that matter checked", items=[x["items"][0]])
        for i in a["items"]:
            i.update(part="A", ref="A:" + i["key"])
        r = copy.deepcopy(x)
        r.update(value="R", line="R: 2 of 2 rows that matter checked", released=True, items=[], k=2, n=2)
        page = RV.render("t", [x, r, a], "TOK", self.root, images={})
        order = [page.index(s) for s in ('id="part-A"', 'id="part-X"')]
        self.assertEqual(order, sorted(order))
        self.assertLess(page.index('id="part-X"'), page.index("<details><summary>Released parts"))
        self.assertIn("R: 2 of 2 rows that matter checked", page.split("<details><summary>Released parts")[1])
        self.assertLess(page.index('id="summary"'), page.index('id="part-A"'))
        self.assertEqual(page.count("R: 2 of 2 rows that matter checked"), 2)  # status line + the fold

    def test_each_image_file_is_sent_once(self):
        (part,) = self.model()
        paths = [part_img for i in part["items"] for part_img, _ in i["images"]]
        self.assertGreater(len(paths) - len(set(paths)), 0, "the fixture must share an image between rows")
        paths += [i["locate"]["image"] for i in part["items"] if i.get("locate")]
        images = {}
        page = RV.render("t", [part], "TOK", self.root, images=images)
        self.assertNotIn("base64", page)
        self.assertEqual(sorted(p.name for p in images.values()), sorted({Path(p).name for p in paths}))
        ids = re.findall(r'src="/img/([0-9a-f]+)\?t=\{?TOK', page)
        self.assertEqual(set(ids), set(images))
        self.assertGreater(len(ids), len(images))  # shown more than once, one file each
        self.assertLess(len(page), 60_000)
        distinct = sum(p.stat().st_size for p in images.values())
        naive = sum((self.cdir / p).stat().st_size for p in paths)
        self.assertLess(distinct, naive)

    def test_server_serves_each_image_by_token(self):
        (part,) = self.model()
        images = {}
        page = RV.render("t", [part], "{TOKEN}", self.root, images=images)
        app = RV.App(page, [], lambda refs, emit: 0, images=images)
        t = threading.Thread(target=app.server.serve_forever, daemon=True)
        t.start()
        self.addCleanup(app.server.server_close)
        self.addCleanup(app.server.shutdown)
        iid, path = next(iter(images.items()))
        got = urllib.request.urlopen(urllib.request.Request(f"{app.origin}/img/{iid}?t={app.token}"))
        self.assertEqual((got.status, got.headers["Content-Type"]), (200, "image/png"))
        self.assertEqual(got.read(), path.read_bytes())
        for url, code in ((f"/img/{iid}?t=bad", 403), (f"/img/{'0' * 16}?t={app.token}", 404), (f"/img/../x?t={app.token}", 404)):
            with self.assertRaises(urllib.error.HTTPError) as e:
                urllib.request.urlopen(urllib.request.Request(app.origin + url))
            self.assertEqual(e.exception.code, code, url)
        self.assertIn(f'src="/img/{iid}?t={app.token}"', urllib.request.urlopen(app.url).read().decode())


class CardHtml(unittest.TestCase):
    """The statement card as the page shows it: title, label/value block, note folded, all text escaped."""

    def card(self, **kw):
        return {"title": "TCR \u2014 x", "lines": [("Value", "\u00b1100 ppm/\u00b0C"), ("Conditions", "a<b & \"c\"")], "note": "n<1",
                "note_open": False, "fix": "", **kw}

    def test_folded_note_and_escaping(self):
        h = RV.card_html(self.card())
        self.assertIn("<b>TCR \u2014 x</b>", h)
        self.assertIn("<tr><th>Value</th><td>\u00b1100 ppm/\u00b0C</td></tr>", h)
        self.assertIn("<td>a&lt;b &amp; &quot;c&quot;</td>", h)
        self.assertIn("<details><summary>How we read it</summary><p>n&lt;1</p></details>", h)
        self.assertNotIn("\u26a0", h)

    def test_open_with_warning_and_no_note_no_fold(self):
        h = RV.card_html(self.card(note_open=True))
        self.assertIn("<details open><summary>\u26a0 How we read it</summary>", h)
        self.assertNotIn("<details", RV.card_html(self.card(note="")))

    def test_fix_first_has_no_table(self):
        h = RV.card_html(self.card(lines=[], note="", fix="Fix first: the row has no min, typ or max"))
        self.assertIn("Fix first: the row has no min, typ or max", h)
        self.assertNotIn("<table", h)


class Readme(Stamped):
    def test_checked_column_and_summary_line(self):
        text = readme.build(self.d)
        self.assertEqual(text.splitlines()[4], "Checked by a person: 0 of 0 rows that matter (7 rows in all). "
                                               "Review: python3 tools/review.py X")
        (self.d / "calc.py").write_text('INPUTS = {"f": {"a": "iq.typ"}}\n')
        self.assertEqual(readme.build(self.d).splitlines()[4], "Released: all 1 rows that matter checked (7 rows in all).")
        text = readme.build(self.d)
        self.assertIn("| Cite | Checked |", text)
        iq = next(ln for ln in text.splitlines() if ln.startswith("| n iq |"))
        self.assertTrue(iq.endswith("| checked (alice, 2026-11-20) |"), iq)
        vos = next(ln for ln in text.splitlines() if ln.startswith("| n vos |"))
        self.assertTrue(vos.endswith("|  |"), vos)  # machine stamp: blank

    def test_top_table_and_markers(self):
        (self.d / "calc.py").write_text('INPUTS = {"f": {"a": "iq.typ"}}\n')
        self.assertEqual(readme.top_table(self.root),
                         "| Part | Status | Review command |\n|---|---|---|\n"
                         "| Acme/X | released | `python3 tools/review.py X` |\n")
        (self.d / "calc.py").write_text('INPUTS = {"f": {"a": "iq.typ", "b": "vos"}}\n')
        self.assertIn("| Acme/X | 1 of 2 |", readme.top_table(self.root))
        top = self.root / "README.md"
        self.assertFalse(readme.update_top(self.root))  # no file or no markers: nothing written
        top.write_text("hand\n<!-- review-status:start -->\nold\n<!-- review-status:end -->\ntail\n")
        self.assertTrue(readme.update_top(self.root))
        first = top.read_text()
        self.assertTrue(first.startswith("hand\n<!-- review-status:start -->\n| Part |"))
        self.assertTrue(first.endswith("<!-- review-status:end -->\ntail\n"))
        self.assertNotIn("old", first)
        readme.update_top(self.root)
        self.assertEqual(top.read_text(), first)

    def test_repo_readme_table_is_current(self):
        text = (ROOT / "README.md").read_text()
        self.assertIn("<!-- review-status:start -->\n" + readme.top_table(ROOT) + "<!-- review-status:end -->", text)

    def test_same_without_pdf_and_cache(self):
        before = readme.build(self.d)
        (self.root / "docs/datasheets/x.pdf").write_bytes(b"other")
        self.assertEqual(readme.build(self.d), before)
        (self.root / "docs/datasheets/x.pdf").unlink()
        shutil.rmtree(self.root / ".review-cache")
        self.assertEqual(readme.build(self.d), before)


class Matters(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.d = self.root / "components/Acme/Y"
        self.d.mkdir(parents=True)
        (self.root / "examples").mkdir()

    def part(self, rows, calc="", example="", pins=True):
        body = '[part]\nvalue = "Y"\n'
        for key, kw in rows.items():
            body += f'\n[param.{key}]\nname = "n {key}"\nkind = "{kw.pop("kind", "electrical")}"\nscope = "25C"\n'
            body += 'unit = "V"\nconditions = ""\ncite = "DS p.1"\nmax = 1\n'
            body += "".join(f"{k} = {v}\n" for k, v in kw.items())
        if pins:
            body += '\n[[pin]]\nnumber = "1"\nname = "IN"\ntype = "input"\nfunction = "Input"\ncite = "DS p.1"\n'
        (self.d / "component.toml").write_text(body)
        if calc:
            (self.d / "calc.py").write_text(calc)
        (self.root / "examples/e.py").write_text(example)

    def test_rules_one_to_four(self):
        self.part({"a": {"kind": "abs_max"}, "m": {"kind": "mechanical"},
                   "rjc": {"kind": "thermal", "symbol": '"RthJC(top)"'},
                   "zjc": {"kind": "thermal", "symbol": '"zthjc"'},
                   "tjmax": {"kind": "thermal", "symbol": '"T_J(max)"'},
                   "rja": {"kind": "thermal", "symbol": '"RthJA"'},
                   "tjs": {"kind": "thermal", "symbol": '"TJ"'},
                   "rec": {"kind": "rec_op"}, "calc": {}, "ex": {}, "zc": {"check_pins": '["P1"]'},
                   "amb": {"check_ambient": "true"}, "other": {}, "jcelec": {"symbol": '"RthJC"'}},
                  calc='INPUTS = {"f": {"x": "calc.typ", "y": "gone"}}\n',
                  example='p.param("ex")\n')
        got = RS.matters(self.d, self.root)
        self.assertEqual(sorted(got), sorted(["a", "m", "rjc", "zjc", "tjmax", "calc", "ex", "zc", "amb", "pinout"]))
        self.assertEqual(RS.review(self.d, self.root)["status"]["other"], RS.REFERENCE)
        self.assertEqual(RS.review(self.d, self.root)["status"]["rja"], RS.REFERENCE)

    def test_tjmax_symbol_normalised(self):
        for sym, want in (("TJMAX", True), ("T_J(MAX)", True), ("tj max", True), ("TJ", False), ("TJMAXX", False)):
            self.part({"t": {"kind": "thermal", "symbol": f'"{sym}"'}}, pins=False)
            self.assertEqual("t" in RS.matters(self.d, self.root), want, sym)

    def test_no_pins_no_pinout(self):
        self.part({"a": {"kind": "abs_max"}}, pins=False)
        self.assertEqual(list(RS.matters(self.d, self.root)), ["a"])

    def test_statement(self):
        self.part({"v": {"typ": 3, "symbol": '"VOS"', "note": '"hot"', "max_ref": '"VS"'}},
                  calc='INPUTS = {"fn": {"arg": "v.typ"}}\n', example='"v"\n')
        p = self.d / "component.toml"
        p.write_text(p.read_text().replace('max = 1\n', 'max = 4\n', 1).replace('conditions = ""', 'conditions = "TA = 25"'))
        want = ("n v (VOS): typ 3, max 4 (rel. VS) V; TA = 25; scope 25C. Note: hot. "
                "Used by: fn(arg), examples/e.py")
        self.assertEqual(RS.statement(self.d, "v", self.root), want)

    def test_statement_no_conditions_zener_and_fix_first(self):
        self.part({"v": {"check_pins": '["P1", "P2"]'}, "nounit": {}}, pins=False)
        p = self.d / "component.toml"
        self.assertEqual(RS.statement(self.d, "v", self.root),
                         "n v (): max 1 V; no conditions printed; scope 25C. Used by: Zener check on pins P1, P2")
        t = p.read_text()
        i = t.index("[param.nounit]")
        p.write_text(t[:i] + t[i:].replace('unit = "V"\n', "", 1))
        self.assertEqual(RS.statement(self.d, "nounit", self.root),
                         "n nounit (): max 1 unitless; no conditions printed; scope 25C.")  # not Fix first, not blank
        p.write_text(t[:i] + t[i:].replace("max = 1\n", "", 1))
        self.assertEqual(RS.statement(self.d, "nounit", self.root), "Fix first: the row has no min, typ or max")

    def test_statement_note_ending_in_a_period_gets_no_second_one(self):
        self.part({"v": {"note": '"hot."'}}, pins=False)
        self.assertEqual(RS.statement(self.d, "v", self.root), "n v (): max 1 V; no conditions printed; scope 25C. Note: hot.")
        self.part({"v": {"note": '"hot"'}}, pins=False)
        self.assertEqual(RS.statement(self.d, "v", self.root), "n v (): max 1 V; no conditions printed; scope 25C. Note: hot.")

    def test_pinout_statement(self):
        self.part({})
        self.assertEqual(RS.statement(self.d, "pinout", self.root), "Pinout of Y: 1 IN (input): Input")


class StatementCard(unittest.TestCase):
    """docs/spec/review-view.md "Statement card": structured data, display-only unit and sign prettifying."""
    setUp = Matters.setUp

    def row(self, key="v", pins=False, **kw):
        """Write one part Y with one [param.<key>] row; kw are TOML values (strings need their quotes)."""
        f = {"name": '"n"', "symbol": '"S"', "kind": '"electrical"', "scope": '"25C"', "unit": '"V"', "conditions": '""',
             "cite": '"DS p.1"', "max": "1"}
        f.update(kw)
        body = '[part]\nvalue = "Y"\n\n' + f"[param.{key}]\n" + "".join(f"{k} = {v}\n" for k, v in f.items() if v is not None)
        if pins:
            body += '\n[[pin]]\nnumber = "1"\nname = "IN"\ntype = "input"\nfunction = "Input"\ncite = "DS p.1"\n'
        (self.d / "component.toml").write_text(body)

    def card(self, key="v"):
        return RS.statement_card(self.d, key, self.root)

    def value(self, **kw):
        self.row(**kw)
        return dict(self.card()["lines"])["Value"]

    def test_lines_title_prettified_units_and_used_by(self):
        self.row(name='"Res, 10 ohm"', symbol='"TCR"', typ="3", max="4", max_ref='"VS"', unit='"ppm/degC"',
                 conditions='"10 ohm to 1 Mohm, 5 kohm; +/-1 %; 3 uV, 2 uA; at +25 degC"')
        (self.d / "calc.py").write_text('INPUTS = {"fn": {"arg": "v.typ"}}\n')
        (self.root / "examples/e.py").write_text('"v"\n')
        c = self.card()
        self.assertEqual(c["title"], "TCR \u2014 Res, 10 \u03a9")
        self.assertEqual(c["lines"], [
            ("Value", "typ 3, max 4 (rel. VS) ppm/\u00b0C"),
            ("Conditions", "10 \u03a9 to 1 M\u03a9, 5 k\u03a9; \u00b11 %; 3 \u00b5V, 2 \u00b5A; at +25 \u00b0C"),
            ("Temperature", "at 25 \u00b0C only"),
            ("Used by", "fn (arg), examples/e.py")])
        self.assertEqual((c["note"], c["note_open"]), ("", False))

    def test_pretty_leaves_words_alone(self):
        self.assertEqual(RS.pretty("unless unit use us ohms degCx"), "unless unit use us ohms degCx")
        self.assertEqual(RS.pretty("uVpp uF/uH 1 Mohm"), "\u00b5Vpp \u00b5F/\u00b5H 1 M\u03a9")

    def test_pretty_units_attached_to_numbers_and_prefixes(self):
        self.assertEqual(RS.pretty("-40degC to 125degC, mdegC, 5.1kohm, 2Mohm, 10ohm, 3uV, 5uA, 10uF"),
                         "-40°C to 125°C, m°C, 5.1kΩ, 2MΩ, 10Ω, 3µV, 5µA, 10µF")
        self.assertEqual(RS.pretty("x_uA x_degC y_kohm"), "x_uA x_degC y_kohm")  # identifiers stay
        self.assertEqual(RS.pretty("degCx Tdegree"), "degCx Tdegree")

    def test_temperature_scopes_and_none_printed(self):
        for scope, want in (("25C", "at 25 \u00b0C only"), ("full", "over the full temperature range"),
                            ("partial", "over part of the range: see conditions"), ("na", None)):
            self.row(scope=f'"{scope}"')
            c = dict(self.card()["lines"])
            self.assertEqual(c.get("Temperature"), want, scope)
            self.assertEqual(c["Conditions"], "none printed")
            self.assertNotIn("Used by", c)

    def test_plus_minus_value_and_unitless(self):
        self.assertEqual(self.value(min="-5", max="5"), "\u00b15 V")
        self.assertEqual(self.value(sym="true", max="7"), "\u00b17 V")
        self.assertEqual(self.value(min="-5", max="6"), "min -5, max 6 V")
        self.assertEqual(self.value(unit=None), "max 1 unitless")

    def test_note_open_rules(self):
        for note, extra, want in (("plain", {}, False), ("Read as a span", {}, True), ("it is applied AS shown", {}, True),
                                  ("Inferred from p.2", {}, True), ("plain", {"unchecked": '"why"'}, True)):
            self.row(note=f'"{note}"', **extra)
            c = self.card()
            self.assertEqual((c["note"], c["note_open"]), (note, want), note)

    def test_fix_first_and_pinout(self):
        self.row(max=None, pins=True)
        self.assertEqual(self.card()["fix"], "Fix first: the row has no min, typ or max")
        c = self.card("pinout")
        self.assertEqual(c["title"], "Pinout of Y")
        self.assertEqual(c["pins"], [("1", "IN", "input", "Input")])


class DocsQuoteNoCounts(unittest.TestCase):
    def test_no_review_counts_that_go_stale(self):
        for name in ("CONTRIBUTING.md", "tools/TRUST.md"):
            text = (ROOT / name).read_text()
            self.assertIsNone(re.search(r"\b\d+ of \d+ (?:used )?rows", text), name)
            self.assertIsNone(re.search(r"INA229AIDGS \d+ of \d+", text), name)


class Page(Stamped):
    def setUp(self):
        super().setUp()
        (self.d / "calc.py").write_text(CALC_ALL)

    def model(self, used=frozenset({"iq", "vos", "vos_bad", "nocite", "wrap", "absr", "capacitance"})):
        return RV.build_model(self.root, {self.d: set(used) if used is not None else None})

    def test_rows_tiers_and_tick_rules(self):
        (part,) = self.model()
        self.assertEqual(part["line"], "X: 1 of 6 rows that matter checked")
        tiers = {i["key"]: i["tier"] for i in part["items"]}
        self.assertEqual(tiers, {"vos": "tier 1", "wrap": "tier 2", "absr": "tier 3", "vos_bad": "fix", "nocite": "fix",
                                 "capacitance": "none"})
        self.assertEqual([i["key"] for i in part["items"]], ["vos", "wrap", "absr", "nocite", "vos_bad", "capacitance"])
        self.assertEqual(part["checked"], [("iq", "alice", "2026-11-20")])
        self.assertEqual(part["reference"], ["aol"])
        absr = part["items"][2]  # no auto crop: the full page of the cited page, boxes only when located, then the stamped image
        self.assertEqual((absr["images"], absr["locate"]["image"], absr["locate"]["boxes"]),
                         ([("evidence/table_p1_y67.png", "evidence the stamp records")], "evidence/locate_p1.png", []))
        vos = part["items"][0]
        self.assertIn("[param.vos]", vos["toml"])
        self.assertNotIn("verified", vos["toml"])
        self.assertEqual(vos["page"][1], "https://example.com/x.pdf#page=2")
        self.assertIn("status DISAGREE", next(i for i in part["items"] if i["key"] == "vos_bad")["why"])

    def hot(self):
        """A needs-check row with two IQ lines (table fallback) whose numbers print on one line: 1.4 and 2.5."""
        p = self.d / "component.toml"
        p.write_text(p.read_text() + prow("hot", "IQ", "mA", typ=1.4, max=2.5))
        (self.d / "calc.py").write_text(CALC_ALL.replace('"g": "absr.max"', '"g": "absr.max", "h": "hot"'))
        self.assertEqual(self.run_r()[0], 0)

    def test_non_auto_row_shows_its_full_page_with_boxes_over_it(self):
        self.hot()
        (part,) = self.model(used={"hot", "absr", "vos"})
        hot = next(i for i in part["items"] if i["key"] == "hot")
        import tomllib
        ev = tomllib.loads((self.d / "review" / "review.toml").read_text())["row"]["hot"]["image"]  # what stamp hashes
        self.assertNotEqual(ev, "evidence/locate_p2.png")
        self.assertEqual((hot["tier"], hot["images"], hot["locate"]["image"]),
                         ("tier 3", [(ev, "evidence the stamp records")], "evidence/locate_p2.png"))
        (b,) = hot["locate"]["boxes"]
        self.assertIn("Quiescent current, hot", b["text"])
        images = {}
        page = RV.render("t", [part], "TOK", self.root, images=images)
        item = page.split('id="row-X:hot"')[1].split('<div class="item"')[0]
        self.assertIn('class="loc"', item)
        x0, y0, x1, y1 = b["box"]
        self.assertIn(f'style="left:{x0}%;top:{y0}%;width:{round(x1 - x0, 2)}%;height:{round(y1 - y0, 2)}%"', item)
        self.assertEqual(item.count('class="box"'), 1)
        self.assertEqual(item.count("<img"), 2)  # the located page, then the evidence image the stamp hashes
        iid = next(k for k, v in images.items() if v == (self.cdir / "evidence/locate_p2.png").resolve())
        self.assertEqual(item.count(f"/img/{iid}?t=TOK"), 1)  # one URL for the page image
        eid = next(k for k, v in images.items() if v == (self.cdir / ev).resolve())
        self.assertEqual(item.count(f"/img/{eid}?t=TOK"), 1)
        self.assertIn("evidence the stamp records (click to enlarge)", item)
        self.assertLess(item.index('class="loc"'), item.index(f"/img/{eid}"))  # below the located page
        self.assertNotIn("row not located", item)
        self.assertIn('data-cx="', item)  # opened scrolled to the boxes
        self.assertIn("classList.toggle('full')", page)  # a click shows the whole page

    def test_located_page_that_is_the_ledger_image_is_shown_once(self):
        self.hot()
        ledger = {"row": {"hot": {"image": "evidence/locate_p2.png", "status": "AGREE_TEXT_CHECK"}}}  # a full-page fallback
        with mock.patch.object(RV, "locate_entry", return_value={"image": "evidence/locate_p2.png", "boxes": []}), \
                mock.patch.object(RV.S, "check_row", return_value=(self.d, "s", None)):
            _, _, imgs = RV.classify(self.root, self.d, "hot", ledger, {"hot": {"min": 1, "unit": "mA", "name": "n"}})
        self.assertEqual(imgs, [])

    def test_row_not_located_says_so_and_shows_the_page(self):
        (part,) = self.model()
        images = {}
        page = RV.render("t", [part], "TOK", self.root, images=images)
        item = page.split('id="row-X:absr"')[1].split('<div class="item"')[0]
        self.assertIn("row not located, find it on the page", item)
        self.assertNotIn('class="box"', item)
        self.assertIn("<img class=big ", item)
        self.assertIn((self.cdir / "evidence/locate_p1.png").resolve(), images.values())

    def test_image_of_another_sheet_never_falls_back_to_the_main_files_page(self):
        fill = [(40 + 30 * (n % 15), 200 + 10 * (n // 15), 8, "w%d" % n) for n in range(60)]
        (self.root / "docs/datasheets/y.pdf").write_bytes(fx.build_pdf([[(40, 100, 8, "Row X"), (300, 100, 8, "3.30"), fx.footer(1)] + fill]))
        p = self.d / "component.toml"
        p.write_text(p.read_text() + prow("sx", "SX", "V", cite="DS p.1 (y.pdf), Table, x", typ=3.3))
        (self.d / "calc.py").write_text(CALC_ALL.replace('"g": "absr.max"', '"g": "absr.max", "h": "sx"'))
        self.assertEqual(self.run_r()[0], 0)
        (self.cdir / "evidence/page_p1.png").write_bytes(b"main file page 1")  # same page number, the wrong sheet
        (part,) = self.model(used={"sx"})
        (sx,) = part["items"]
        self.assertTrue(sx["locate"]["image"].startswith("evidence/y_"), sx["locate"])
        self.assertIn("Row X 3.30", sx["locate"]["boxes"][0]["text"])
        (self.cdir / "locate.json").unlink()  # without locate data: the old images, still of the cited sheet
        (part,) = self.model(used={"sx"})
        (sx,) = part["items"]
        self.assertNotIn("evidence/page_p1.png", [p for p, _ in sx["images"]])
        self.assertTrue(all(p.startswith("evidence/y_") for p, _ in sx["images"]), sx["images"])

    def test_render_plain_words_one_button(self):
        page = RV.render("Rows to check: B", self.model(), "TOK", self.root, block="B")
        self.assertIn('<div id="summary"><p><b>1 of 6 rows that matter checked</b></p>\n<p><a href="#part-X">X: 1 of 6 rows that matter '
                      'checked</a></p></div>', page)
        self.assertLess(page.index('id="summary"'), page.index('class="item"'))  # the summary is the first screen
        self.assertIn('<h2 id="part-X">X: 1 of 6 rows that matter checked</h2>', page)
        self.assertIn("<p><b>VOS \u2014 n vos</b></p>", page)
        self.assertIn("<tr><th>Value</th><td>typ 10, max 35 \u00b5V</td></tr>", page)
        self.assertIn("<details><summary>Full TOML</summary><pre>[param.vos]", page)
        self.assertIn('rel="noreferrer noopener"', page)
        self.assertNotIn('rel="noopener"', page)
        self.assertIn("<img class=big ", page)  # table image: height capped
        self.assertNotIn("printed page n/a", page)
        self.assertIn('<button id="go" disabled>Stamp 0 rows and open PR</button>', page)
        self.assertIn("<details><summary>Already checked: 1 rows; other rows (reference): 1 rows</summary>", page)
        self.assertEqual(page.count('class="ok"'), 3)  # vos, wrap, absr; fix and catalog rows have no tick box
        self.assertIn('src="/img/', page)
        self.assertNotIn("base64", page)
        for word in ("HUMAN_VERIFIED", "MACHINE_CHECKED", "PDF_CHANGED", "NOT_COVERED", "UNVERIFIED", "STALE"):
            self.assertNotIn(word, page)
        self.assertNotIn("verified =", page)

    def test_parts_with_fewer_rows_first_and_released_line(self):
        import copy
        (x,) = self.model()
        a = copy.deepcopy(x)
        a.update(value="A", line="A: 0 of 1 rows that matter checked", k=0, n=1, items=[i for i in a["items"] if i["tier"] == "tier 3"])
        for i in a["items"]:
            i.update(part="A", ref="A:" + i["key"])
        r = copy.deepcopy(x)
        r.update(value="R", line="R: 2 of 2 rows that matter checked", released=True, items=[], k=2, n=2)
        page = RV.render("t", [a, x, r], "TOK", self.root, block="B")
        order = [page.index(f'id="row-{s}"') for s in ("A:absr", "X:vos", "X:wrap", "X:absr", "X:nocite", "X:capacitance")]
        self.assertEqual(order, sorted(order))
        self.assertIn('<a href="#part-R">R: 2 of 2 rows that matter checked. Released for B.</a>', page)
        self.assertIn("<b>3 of 9 rows that matter checked</b>", page)

    def test_parts_sorted_by_the_whole_parts_needs_check_count(self):
        import copy
        (x,) = self.model()
        a = copy.deepcopy(x)  # 5 rows shown, but only 1 needs a check (the page is narrowed to a block's rows)
        a.update(value="A", line="A: 4 of 5", k=4, n=5)
        b = copy.deepcopy(x)  # 1 row shown, 3 need a check
        b.update(value="B", line="B: 0 of 3", k=0, n=3, items=[x["items"][0]])
        for part in (a, b):
            for i in part["items"]:
                i.update(part=part["value"], ref=part["value"] + ":" + i["key"])
        self.assertGreater(len(a["items"]), len(b["items"]))
        page = RV.render("t", [b, a], "TOK", self.root, images={})
        self.assertLess(page.index('id="part-A"'), page.index('id="part-B"'))

    def test_image_outside_the_part_cache_is_not_registered_or_served(self):
        (part,) = self.model()
        (self.root / "secret.png").write_bytes(b"secret")
        (self.root / ".review-cache" / "Other.png").write_bytes(b"other")
        outside = [("../../../secret.png", "table or page"), (str(self.root / "secret.png"), "table or page"),
                   ("../../Other.png", "row"), ("../Y/evidence/x.png", "row")]
        item = part["items"][0]
        item["images"] = outside + item["images"][:1]
        part["items"] = [item]
        images = {}
        page = RV.render("t", [part], "TOK", self.root, images=images)
        self.assertEqual(len(images), 1)  # only the inside image
        self.assertTrue(all(p.resolve().is_relative_to((self.cdir).resolve()) for p in images.values()))
        self.assertEqual(page.count("outside the review cache"), 4)
        self.assertNotIn("secret", page)

    def test_images_are_served_with_nosniff(self):
        (part,) = self.model()
        images = {}
        page = RV.render("t", [part], "{TOKEN}", self.root, images=images)
        app = RV.App(page, [], lambda refs, emit: 0, images=images)
        threading.Thread(target=app.server.serve_forever, daemon=True).start()
        self.addCleanup(app.server.server_close)
        self.addCleanup(app.server.shutdown)
        iid = next(iter(images))
        got = urllib.request.urlopen(urllib.request.Request(f"{app.origin}/img/{iid}?t={app.token}"))
        self.assertEqual(got.headers["X-Content-Type-Options"], "nosniff")

    def test_fix_first_row_counts_in_n_and_has_no_tick_box(self):
        self.edit("typ = 3\nmax = 4", "")  # wrap: no min, typ or max
        self.run_r()
        (part,) = self.model()
        item = next(i for i in part["items"] if i["key"] == "wrap")
        self.assertEqual(item["tier"], "fix")
        self.assertIn("Fix first", item["why"])
        self.assertEqual(part["line"], "X: 1 of 6 rows that matter checked")  # still in n
        page = RV.render("t", [part], "TOK", self.root, images={})
        self.assertNotIn('value="X:wrap"', page)
        self.assertEqual(page.count('class="ok"'), 2)  # vos, absr

    def test_value_mode_lists_every_unchecked_row(self):
        (part,) = self.model(used=None)
        self.assertEqual(part["line"], "X: 1 of 6 rows that matter checked")
        self.assertEqual(part["reference"], ["aol"])
        self.assertEqual([i["key"] for i in part["items"]], ["vos", "wrap", "absr", "nocite", "vos_bad"])

    def test_block_narrows_the_page_never_the_status(self):
        (part,) = self.model(used={"vos"})
        self.assertEqual(part["line"], "X: 1 of 6 rows that matter checked")
        self.assertEqual([i["key"] for i in part["items"]], ["vos"])
        self.assertFalse(part["released"])

    def test_ensure_cache_runs_ds_review_only_when_missing(self):
        calls = []
        run = lambda cmd, **kw: calls.append(cmd) or mock.Mock(stdout="ok\n", stderr="")  # noqa: E731
        self.assertEqual(RV.ensure_cache(self.root, [self.d], run), [])
        shutil.rmtree(self.root / ".review-cache")
        out = RV.ensure_cache(self.root, [self.d], run)
        self.assertEqual(calls, [[sys.executable, "tools/ds_review.py", COMP]])
        self.assertEqual(out[-1], "ok")

    def test_ensure_cache_dry_run_spawns_nothing(self):
        shutil.rmtree(self.root / ".review-cache")
        calls = []
        out = RV.ensure_cache(self.root, [self.d], lambda *a, **k: calls.append(a), dry_run=True)
        self.assertEqual(calls, [])
        self.assertEqual(out, [f"would run (dry run): {sys.executable} tools/ds_review.py {COMP}"])


class Fake:
    """Scripted runner: answers by command prefix, records every command."""

    def __init__(self, **over):
        self.calls = []
        self.status = iter([(0, "?? scratch.txt\n"),
                            (0, " M components/Acme/X/component.toml\n M components/Acme/X/review/review.toml\n"
                                " M components/Acme/X/README.md\n")])
        self.over = over

    def __call__(self, cmd):
        self.calls.append(cmd)
        name = {("git", "status"): "status", ("git", "rev-parse"): "rev", ("gh", "api"): "login",
                ("git", "fetch"): "fetch", ("git", "for-each-ref"): "refs", ("git", "switch"): "switch",
                ("git", "branch"): "branch", ("git", "add"): "add", ("git", "commit"): "commit",
                ("git", "push"): "push", ("gh", "pr"): "pr"}.get(tuple(cmd[:2]))
        if name is None:
            name = "stamp" if cmd[1].endswith("stamp.py") else "verify"
        if name == "switch" and cmd[2] != "-c":
            name = "switch_back"
        if name in self.over:
            r = self.over[name]
            return r(cmd) if callable(r) else r
        if name == "status":
            return next(self.status)
        return {"rev": (0, "main\n"), "login": (0, "alice\n"),
                "refs": (0, "refs/heads/review/x-alice-20261120\nrefs/remotes/origin/review/other\n"),
                "stamp": (0, "X:iq: (no stamp) -> human:alice ...\nnext: ...\n"), "verify": (0, "PASS\n"),
                "pr": (0, "Creating pull request\nhttps://github.com/o/r/pull/7\n")}.get(name, (0, ""))


class Publish(unittest.TestCase):
    root = Path("/lib")
    dirs = [Path("/lib/components/Acme/X"), Path("/lib/components/Acme/Y")]

    def go(self, fake, refs=("X:iq", "X:vos")):
        lines = []
        rc = RV.publish(self.root, self.dirs, list(refs), fake, lambda *ln: lines.extend(ln),
                        today=datetime.date(2026, 11, 20), python="py")
        return rc, lines, [c[:3] for c in fake.calls]

    def test_success_sequence(self):
        f = Fake(refs=(0, "refs/heads/review/x-alice-20261120\nrefs/remotes/origin/review/x-alice-20261120-2\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 0, lines)
        b = "review/x-alice-20261120-3"
        want = [["git", "status", "--porcelain"], ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                ["gh", "api", "user", "--jq", ".login"], ["git", "fetch", "origin"],
                ["git", "for-each-ref", "--format=%(refname)", "refs/heads/review/", "refs/remotes/origin/review/"],
                ["git", "switch", "-c", b, "origin/main"]]
        self.assertEqual(f.calls[:6], want)
        self.assertEqual(f.calls[6][:5], ["py", "tools/stamp.py", "--who", "alice", "--from"])
        self.assertFalse(os.path.exists(f.calls[6][5]), "the ref list is removed")
        self.assertEqual(f.calls[7], ["py", "tools/verify.py", "--regen", "components/Acme/X"])  # only stamped parts
        self.assertEqual(f.calls[9], ["git", "add", "--", "components/Acme/X/README.md",
                                      "components/Acme/X/component.toml", "components/Acme/X/review/review.toml"])
        self.assertEqual(f.calls[10][:3], ["git", "commit", "-m"])
        self.assertEqual(f.calls[10][3], "X: human check of 2 rows\n\nRows checked on the datasheet page image "
                                         "(tools/review.py):\n- X:iq\n- X:vos")
        self.assertEqual(f.calls[11], ["git", "push", "-u", "origin", b])
        self.assertEqual(f.calls[12][:7], ["gh", "pr", "create", "--base", "main", "--head", b])
        self.assertIn("- X:iq\n- X:vos", f.calls[12][-1])
        self.assertEqual(lines[-1], "PR: https://github.com/o/r/pull/7")
        self.assertIn("$ git switch -c " + b + " origin/main", lines)  # each command is shown

    def test_dirty_tree_refused(self):
        f = Fake(status=(0, " M lib/x.py\n?? new.txt\n"))
        rc, lines, calls = self.go(f)
        self.assertEqual((rc, calls), (1, [["git", "status", "--porcelain"]]))
        self.assertIn("uncommitted changes (lib/x.py)", lines[-1])
        self.assertIn("Commit or stash them", lines[-1])

    def test_early_failures_change_nothing(self):
        for name, reply, want in (("status", (128, "fatal"), "git status failed"),
                                  ("login", (1, "not logged in"), "gh auth login"),
                                  ("login", (0, "bad name!\n"), "no GitHub login"),
                                  ("fetch", (1, "no network"), "git fetch origin failed"),
                                  ("switch", (128, "exists"), "could not create branch")):
            f = Fake(**{name: reply})
            rc, lines, calls = self.go(f)
            self.assertEqual(rc, 1, name)
            self.assertIn(want, lines[-1])
            self.assertNotIn(["py", "tools/stamp.py", "--who"], calls)

    def test_detached_head_returns_to_the_commit(self):
        f = Fake(rev=lambda c: (0, "HEAD\n") if "--abbrev-ref" in c else (0, "abc123\n"), stamp=(1, "refused X:iq: ...\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn(["git", "switch", "abc123"], f.calls)

    def test_stamp_refusal_switches_back_and_deletes_branch(self):
        f = Fake(stamp=(1, "refused X:iq: status DISAGREE\nnothing written\n"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertEqual(f.calls[-2:], [["git", "switch", "main"], ["git", "branch", "-D", "review/x-alice-20261120-2"]])
        self.assertIn("refused X:iq: status DISAGREE", lines)
        self.assertIn("Back on main, branch review/x-alice-20261120-2 deleted. Nothing was stamped.", lines[-1])

    def test_stamp_refusal_with_failed_cleanup_says_so(self):
        f = Fake(stamp=(1, "refused\n"), branch=(1, "error: cannot delete"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("cleanup failed", lines[-1])
        self.assertIn("delete branch review/x-alice-20261120-2 yourself", lines[-1])

    def test_verify_failure_leaves_branch_uncommitted(self):
        f = Fake(verify=(1, "FAIL components/Acme/X/component.toml:3 bad\nlog: /tmp/zl-verify-1\n"))
        rc, lines, calls = self.go(f)
        self.assertEqual(rc, 1)
        self.assertEqual(calls[-1][:2], ["py", "tools/verify.py"])  # no commit, no switch back
        self.assertIn("log: /tmp/zl-verify-1", lines)
        self.assertIn("not committed", lines[-1])

    def test_unexpected_changes_not_committed(self):
        f = Fake()
        f.status = iter([(0, ""), (0, " M components/Acme/X/component.toml\n M lib/readme.py\n")])
        rc, lines, calls = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("unexpected changes (lib/readme.py)", lines[-1])
        self.assertNotIn(["git", "add", "--"], calls)

    def test_root_readme_status_table_is_committed(self):
        f = Fake()
        f.status = iter([(0, ""), (0, " M components/Acme/X/component.toml\n M components/Acme/X/review/review.toml\n"
                                      " M components/Acme/X/README.md\n M README.md\n")])
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 0, lines)
        self.assertEqual(f.calls[9], ["git", "add", "--", "README.md", "components/Acme/X/README.md",
                                      "components/Acme/X/component.toml", "components/Acme/X/review/review.toml"])

    def test_other_root_files_still_unexpected(self):
        f = Fake()
        f.status = iter([(0, ""), (0, " M components/Acme/X/component.toml\n M CONTRIBUTING.md\n M docs/README.md\n")])
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("unexpected changes (CONTRIBUTING.md, docs/README.md)", lines[-1])

    def test_commit_push_pr_failures(self):
        for name, want in (("commit", "commit failed"), ("push", "push failed"), ("pr", "gh pr create failed")):
            f = Fake(**{name: (1, "boom")})
            rc, lines, _ = self.go(f)
            self.assertEqual(rc, 1, name)
            self.assertIn(want, lines[-1])

    def test_pr_create_failure_with_a_url_is_a_failure(self):
        f = Fake(pr=(1, "https://github.com/o/r/pull/7\nerror: something else failed"))
        rc, lines, _ = self.go(f)
        self.assertEqual(rc, 1)
        self.assertIn("gh pr create failed", lines[-1])
        self.assertNotIn("PR: https://github.com/o/r/pull/7", lines)

    def test_dry_runner_shows_every_step(self):
        lines = []
        run = RV.dry_runner()
        rc = RV.publish(self.root, self.dirs, ["X:iq"], run, lambda *ln: lines.extend(ln),
                        today=datetime.date(2026, 11, 20), python="py")
        self.assertEqual(rc, 0, lines)
        cmds = [ln for ln in lines if ln.startswith("$ ")]
        self.assertEqual(len(cmds), 13)
        self.assertEqual(lines[-1], "PR: https://github.com/OWNER/zener-library/pull/0")
        self.assertIn("$ git add -- components/Acme/X/README.md components/Acme/X/component.toml "
                      "components/Acme/X/review/review.toml", lines)  # only the stamped part


class Server(unittest.TestCase):
    def setUp(self):
        self.jobs = []

        def job(refs, emit):
            self.jobs.append(refs)
            emit("$ git fetch origin", "PR: https://github.com/o/r/pull/1")
            return 0
        self.app = RV.App("<p>{TOKEN}</p>", ["X:iq", "X:vos"], job)
        threading.Thread(target=self.app.server.serve_forever, daemon=True).start()
        self.addCleanup(self.app.server.server_close)
        self.addCleanup(self.app.server.shutdown)

    def req(self, path, data=None, headers=None, token=True):
        url = f"{self.app.origin}{path}" + (f"?t={self.app.token}" if token else "")
        r = urllib.request.Request(url, data=data, headers=headers or {}, method="POST" if data is not None else "GET")
        try:
            with urllib.request.urlopen(r, timeout=10) as resp:
                return resp.status, resp.read().decode()
        except urllib.error.HTTPError as e:
            with e:
                return e.code, e.read().decode()

    def post(self, refs, **headers):
        return self.req("/stamp", json.dumps({"refs": refs}).encode(), {"Content-Type": "application/json", **headers})

    def test_token_host_origin(self):
        self.assertEqual(self.req("/", token=False)[0], 403)
        self.assertEqual(self.req("/")[0:2], (200, f"<p>{self.app.token}</p>"))
        self.assertEqual(self.req("/", headers={"Host": "evil.example:80"})[0], 403)
        self.assertEqual(self.post(["X:iq"], Origin="https://evil.example")[0], 403)
        self.assertEqual(self.req("/stamp", b"{}", {"Content-Type": "application/json"}, token=False)[0], 403)
        self.assertEqual(self.jobs, [])

    def test_body_rules(self):
        self.assertEqual(self.req("/stamp", b'{"refs": ["X:iq"]}', {"Content-Type": "text/plain"})[0], 400)
        for refs in ([], ["X:other"], ["X:iq", "X:iq"], "X:iq", [1]):
            self.assertEqual(self.post(refs)[0], 400, refs)
        self.assertEqual(self.jobs, [])

    def test_one_job_streams_then_finishes(self):
        code, text = self.post(["X:iq"], Origin=self.app.origin)
        self.assertEqual((code, text), (200, "$ git fetch origin\nPR: https://github.com/o/r/pull/1\n"))
        self.assertTrue(self.app.finished.is_set())
        self.assertEqual((self.jobs, self.app.rc), ([["X:iq"]], 0))
        self.assertEqual(self.post(["X:vos"])[0], 409)

    def test_done(self):
        self.assertEqual(self.req("/done", b"")[0], 200)
        self.assertTrue(self.app.finished.is_set())

    def test_done_refused_once_a_job_started(self):
        gate, seen = threading.Event(), []

        def slow(refs, emit):
            emit("$ git fetch origin")
            gate.wait(10)
            return 0
        self.app.job = slow
        t = threading.Thread(target=lambda: seen.append(self.post(["X:iq"])))
        t.start()
        for _ in range(100):
            if self.app.started:
                break
            threading.Event().wait(0.05)
        self.assertEqual(self.req("/done", b"")[0], 409)  # mid-run: the server does not stop
        self.assertFalse(self.app.finished.is_set())
        gate.set()
        t.join(10)
        self.assertEqual(seen[0][0], 200)
        self.assertTrue(self.app.finished.is_set())

    def test_page_disables_done_when_the_run_starts(self):
        self.assertIn("go.disabled=true; done.disabled=true;", RV.JS)


class Main(unittest.TestCase):
    def test_refused_inside_claude_code_unless_dry_run(self):
        buf = io.StringIO()
        with mock.patch.dict(os.environ, {"CLAUDECODE": "1"}), contextlib.redirect_stdout(buf):
            self.assertEqual(RV.main(["X"]), 1)
        self.assertEqual(buf.getvalue().strip(), RV.AGENT)

    def test_block_or_values(self):
        with mock.patch.dict(os.environ, {"CLAUDECODE": ""}), contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                RV.main(["--block", "B", "X"])

    def test_no_arguments_means_every_part(self):
        self.assertEqual(RV.all_parts(ROOT), sorted(p.parent for p in (ROOT / "components").glob("*/*/component.toml")))

    def test_deny_rules_match_stamp(self):
        deny = json.loads((ROOT / ".claude/settings.json").read_text())["permissions"]["deny"]
        stamp = [d for d in deny if "stamp.py" in d]
        self.assertTrue(stamp)
        self.assertEqual(sorted(d.replace("stamp.py", "review.py") for d in stamp), sorted(d for d in deny if "review.py" in d))

    def test_default_blocks_repo(self):
        self.assertIn(RV.default_blocks_repo(ROOT).name, ("ina229", "circuit-blocks"))


if __name__ == "__main__":
    unittest.main()
