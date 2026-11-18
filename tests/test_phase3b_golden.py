"""Golden tests: the Phase 3b scripts against the committed, verified component files.

Datasheets and vendor KiCad files are git-ignored; a part whose inputs are missing is skipped with a reason.
A wrong OK / wrong AGREE fails the test. UNSURE is always allowed. Every DISAGREE must be in ADJUDICATED (empty:
none was found; add an entry only after settling it against the page image).
"""
import re
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import ds_index as D  # noqa: E402
import pins_from_sym as P  # noqa: E402
import table_xcheck as T  # noqa: E402

# (component dir, datasheet under docs/datasheets, vendor symbol dir under docs/vendor)
PARTS = [
    ("TexasInstruments/INA821IDGK", "ina821.pdf", "INA821IDGK"),
    ("AnalogDevices/LTC4364MS", "ltc4364.pdf", "LTC4364HMS-1"),
    ("Vishay/WSK2512R0250D", "wsk2512.pdf", "WSK2512R0250D"),
    ("TexasInstruments/INA229AIDGS", "ina229.pdf", "INA229AIDGS"),
    ("TexasInstruments/INA241DGK", "ina241a.pdf", "INA241DGK"),
    ("TexasInstruments/TPS48000QDGXQ1", "tps4800-q1.pdf", "TPS48000QDGXQ1"),
    ("STMicroelectronics/VNF1248F", "DS_vnf1248f.pdf", "VNF1248F"),
    ("Infineon/BSC040N10NS5", "infineon/infineon-bsc040n10ns5-datasheet-en.pdf", "BSC040N10NS5"),
    ("Infineon/ISC035N10NM5LF2", "infineon/infineon-isc035n10nm5lf2-datasheet-en.pdf", "ISC035N10NM5LF2"),
    ("Infineon/ISC750P10LM", "infineon/infineon-isc750p10lm-datasheet-en.pdf", "ISC750P10LM"),
]
_CACHE = {}
ADJUDICATED = {}  # (part, key) -> who is right; empty: no DISAGREE exists

KEYRX = {"abs_max": r"(absolute )?maximum ratings", "esd": r"ESD ratings", "rec_op": r"recommended operating conditions",
         "thermal": r"thermal (information|characteristics)", "electrical": r"electrical characteristics",
         "pin_functions": r"pin functions", "pin_config": r"pin configuration",
         "static_characteristics": r"static characteristics", "dynamic_characteristics": r"dynamic characteristics",
         "reverse_diode": r"reverse diode", "gate_charge": r"gate charge"}


def inputs(part, ds, vendor):
    toml = ROOT / "components" / part / "component.toml"
    pdf = ROOT / "docs" / "datasheets" / ds
    if not toml.is_file() or not pdf.is_file():
        return None
    return toml, pdf


def committed_cites(data):
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "cite" and isinstance(v, str):
                    out.append(v)
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(data)
    segs = []
    for c in out:
        for s in c.split(";"):
            m = re.match(r"\s*(?:DS )?p\.(\d+),\s*(.*)", s)
            if m:
                segs.append((int(m.group(1)), m.group(2)))
    return segs


def symbol_files(part, vendor):
    files = sorted((ROOT / "docs" / "vendor" / vendor).rglob("*.kicad_sym")) if (ROOT / "docs" / "vendor" / vendor).is_dir() else []
    committed = sorted((ROOT / "components" / part).glob("*.kicad_sym"))
    return files + committed


class TestGolden(unittest.TestCase):
    def test_ds_index_ok_items_match_committed_cites(self):
        ran = 0
        for part, ds, vendor in PARTS:
            got = inputs(part, ds, vendor)
            if not got:
                continue
            toml, pdf = got
            with self.subTest(part=part):
                doc, _ = D.build(str(pdf), tempfile.gettempdir(), True, False)
                self.assertEqual(doc["status"], "OK", part)
                segs = committed_cites(tomllib.loads(toml.read_text()))
                for it in doc["items"]:
                    if it["status"] != "OK":
                        continue
                    k, h = it["key"], it["hits"][0]
                    rx = KEYRX.get(k)
                    if k.split(":")[0] in ("table", "figure", "diagram"):
                        kind, lab = k.split(":")
                        rx = r"%s %s(?![\d.])" % (kind, re.escape(lab))
                    if not rx:
                        continue
                    pages = {p for p, t in segs if re.match(rx, re.sub(r"^[\d.]+\s+", "", t), re.I)}
                    if pages:
                        ran += 1
                        self.assertIn(h["printed_page"], pages, "%s %s" % (part, k))
        if not ran:
            self.skipTest("no datasheets present")

    def test_pins_ok_equal_committed(self):
        ran = 0
        for part, ds, vendor in PARTS:
            got = inputs(part, ds, vendor)
            if not got:
                continue
            toml, pdf = got
            data = tomllib.loads(toml.read_text())
            committed = {p["number"]: p["name"] for p in data.get("pin", [])}
            with tempfile.TemporaryDirectory() as td:
                doc, jobs = D.build(str(pdf), td, False, False)
                import json
                (Path(td) / "index.json").write_text(json.dumps(doc))
                for sym in symbol_files(part, vendor):
                    with self.subTest(part=part, sym=sym.name):
                        pins, head, fatal = P.run(str(sym), str(Path(td) / "index.json"))
                        if fatal:
                            continue  # e.g. multi-symbol library: FAIL is the correct, closed outcome
                        ran += 1
                        for p in pins:
                            if p["status"] == "OK":
                                self.assertEqual(committed.get(p["number"]), p["name"], (part, p))
        if not ran:
            self.skipTest("no vendor symbols present")

    def test_xcheck_agree_true_disagree_adjudicated(self):
        ran = 0
        for part, ds, vendor in PARTS:
            got = inputs(part, ds, vendor)
            if not got:
                continue
            toml, pdf = got
            rows, fatal = T.check_rows(str(pdf), str(toml))
            if fatal:
                continue
            data = tomllib.loads(toml.read_text())["param"]
            for key, st, why in rows:
                ran += 1
                if st == "DISAGREE":
                    self.assertIn((part, key), ADJUDICATED, "unadjudicated DISAGREE %s %s: %s" % (part, key, why))
                if st == "AGREE":
                    self.assertTrue(self.second_opinion(pdf, data[key]), "AGREE not confirmed %s %s" % (part, key))
        if not ran:
            self.skipTest("no datasheets present")

    @staticmethod
    def second_opinion(pdf, r):
        """Independent confirmation by pdftotext -layout: a line on the cited page holds the symbol and every
        committed number."""
        if pdf not in _CACHE:
            pages = D.parse_bbox(D.run(["pdftotext", "-bbox-layout", str(pdf), "-"])[1])
            printed, _ = D.printed_pages(pages)
            _CACHE[pdf] = {v: k for k, v in printed.items()}
        inv = _CACHE[pdf]
        pg = inv.get(T.cite_page(r["cite"]))
        if pg is None:
            return False
        txt = subprocess.run(["pdftotext", "-layout", "-f", str(pg), "-l", str(pg), str(pdf), "-"],
                             capture_output=True).stdout.decode("utf-8", "replace")
        sym = re.sub(r"\s", "", T.norm_minus(r["symbol"]))
        vals = [r[k] for k in ("min", "typ", "max") if k in r]
        for ln in txt.splitlines():
            line = T.norm_minus(ln)
            nums = [float(t) for t in line.split() if T.NUM.match(t)]
            if all(any(abs(n - v) < 1e-9 for n in nums) for v in vals) and sym[:3] in re.sub(r"\s", "", line):
                return True
        return False


if __name__ == "__main__":
    unittest.main()
