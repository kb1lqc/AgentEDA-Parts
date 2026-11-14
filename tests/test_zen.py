"""Zener wrapper generator tests.

Generator tests always run. Build tests run only when `pcb` is installed: each copies tests/zen/<Value>_harness.zen
next to the generated wrapper, builds it with -Wstyle -Dwarnings and checks the outcome. Every check row is shown
passing (nominal), failing at its severity, and UNVERIFIED when its net has no voltage.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import copytree

from lib.component import ROOT
from lib.zen import generate, io_name, wrappers

FIX = Path(__file__).parent / "fixtures" / "Acme"
HARNESS = Path(__file__).parent / "zen"


class TestGenerator(unittest.TestCase):
    def test_io_names(self):
        self.assertEqual([io_name(n) for n in ("+IN", "-VS", "V+", "NC3", "RG1")], ["IN_P", "VS_N", "V_P", "NC3", "RG1"])

    def test_fixture_wrapper(self):
        text, problems = generate(FIX / "LDO1")
        self.assertEqual(problems, [])
        self.assertIn('symbol=Symbol(library="./LDO1.kicad_sym")', text)
        self.assertIn('"IN": Power(IN, voltage=IN.voltage)', text)  # power_in pin cast to Power
        self.assertIn("GND = io(Ground)", text)
        self.assertIn('"lo": -0.3 * derate', text)  # abs_max lower bound derated
        self.assertIn('"hi": 40.0 * derate', text)
        self.assertIn('"lo": 2.0, "lo_ref": GND.voltage, "hi": -2.0, "hi_ref": IN.voltage', text)  # rec_op: no derate
        self.assertIn("# UNCHECKED: io_cont: Output current rating", text)

    def test_bad_check_pins(self):
        with tempfile.TemporaryDirectory() as d:
            copy = Path(d) / "LDO1"
            copytree(FIX / "LDO1", copy)
            toml = copy / "component.toml"
            toml.write_text(toml.read_text().replace('check_pins = ["IN"]', 'check_pins = ["NOPE"]'))
            _, problems = generate(copy)
            self.assertTrue(any("unknown or NC pin 'NOPE'" in p for p in problems), problems)

    def test_real_wrappers_are_current(self):
        """The committed .zen equals the generator output (after pcb fmt, which only rewraps long lines)."""
        if not shutil.which("pcb"):
            self.skipTest("pcb not installed")
        for d, variant in wrappers([]):  # a family has one wrapper per variant
            value = variant or d.name
            with tempfile.TemporaryDirectory(dir=d.parent) as tmp:
                work = Path(tmp) / d.name
                copytree(d, work)
                text, problems = generate(work, variant)
                self.assertEqual(problems, [], value)
                (work / f"{value}.zen").write_text(text)
                subprocess.run(["pcb", "fmt", str(work)], check=True, capture_output=True)
                self.assertEqual((work / f"{value}.zen").read_text(), (d / f"{value}.zen").read_text(),
                                 f"{value}.zen is stale: run python3 -m lib.zen")


# (component dir, case name, config overrides, expected: "pass" | "error" | "warning", text that must appear)
CASES = [
    ("TexasInstruments/INA821IDGK", "nominal", [], "pass", ""),
    ("TexasInstruments/INA821IDGK", "vin_abs_out", ["vinp=41V"], "error", "vin_abs_IN_P: 41.0 to 41.0 V outside"),
    ("TexasInstruments/INA821IDGK", "vcm_25c_out", ["vinp=13.5V"], "warning", "vcm_range_25c_IN_P"),
    ("TexasInstruments/INA821IDGK", "vcm_waived", ["vinp=13.5V", "waive=test rationale DS p.6"], "pass", ""),
    ("TexasInstruments/INA821IDGK", "vin_unset", ["vinp=unset"], "warning", "UNVERIFIED vin_abs_IN_P"),
    ("TexasInstruments/INA821IDGK", "span_out", ["vp=22V"], "error", "vs_rec_single_VS_P"),
    ("TexasInstruments/INA821IDGK", "ref_25c_out", ["vref=16V"], "warning", "vref_range_25c_REF"),
    ("TexasInstruments/INA821IDGK", "vref_abs_out", ["vref=21V"], "error", "vref_abs_REF"),
    ("TexasInstruments/INA821IDGK", "ambient_out", ["ta=-40°C to 130°C"], "error", "ta_rec_ambient"),
    ("TexasInstruments/INA821IDGK", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ta_rec_ambient"),
    ("AnalogDevices/LTC4364MS", "nominal", [], "pass", ""),
    ("AnalogDevices/LTC4364MS", "vcc_op_out", ["vcc=85V", "vout=85V", "vsense=85V"], "error", "vcc_op_VCC"),
    ("AnalogDevices/LTC4364MS", "vcc_abs_out", ["vcc=101V", "vout=101V", "vsense=101V"], "error", "abs_vcc_VCC"),
    ("AnalogDevices/LTC4364MS", "sense_out_out", ["vsense=45V"], "error", "abs_sense_out_SENSE"),
    ("AnalogDevices/LTC4364MS", "out_vcc_ok", ["vout=0V", "vsense=0V"], "pass", ""),
    ("AnalogDevices/LTC4364MS", "fb_out", ["vfb=6V"], "error", "abs_fb_tmr_FB"),
    ("AnalogDevices/LTC4364MS", "uv_unset", ["vuv=unset"], "warning", "UNVERIFIED abs_source_ov_uv_shdn_UV"),
    ("AnalogDevices/LTC4364MS", "ambient_out", ["ta=-40°C to 130°C"], "error", "ta_h_ambient"),
    ("AnalogDevices/LTC4364MS", "c1_nominal", ["variant=LTC4364CMS-1", "ta=0°C to 70°C"], "pass", ""),
    ("AnalogDevices/LTC4364MS", "c1_industrial_ambient", ["variant=LTC4364CMS-1"], "error", "ta_c_ambient"),
    ("AnalogDevices/LTC4364MS", "i2_nominal", ["variant=LTC4364IMS-2"], "pass", ""),
    ("AnalogDevices/LTC4364MS", "i2_ambient_out", ["variant=LTC4364IMS-2", "ta=-40°C to 90°C"], "error", "ta_i_ambient"),
    ("AnalogDevices/LTC4364MS", "h2_vcc_abs_out", ["variant=LTC4364HMS-2", "vcc=101V", "vout=101V", "vsense=101V"],
     "error", "abs_vcc_VCC"),
    ("TexasInstruments/INA229AIDGS", "nominal", [], "pass", ""),
    ("TexasInstruments/INA229AIDGS", "vbus_abs_out", ["vbus=86V"], "error", "vbus_abs_VBUS"),
    ("TexasInstruments/INA229AIDGS", "vcm_out", ["vinp=86V", "vinn=86V"], "error", "vcm_rec_IN_P"),
    ("TexasInstruments/INA229AIDGS", "vin_diff_out", ["vinn=5V"], "error", "vin_diff_abs_IN_P"),  # 45.6 - 5 > 40 V
    ("TexasInstruments/INA229AIDGS", "vs_rec_out", ["vs=5.8V"], "error", "vs_rec_VS"),
    ("TexasInstruments/INA229AIDGS", "vio_out", ["vmosi=4V"], "error", "vio_abs_MOSI"),  # > VS(min) 3.135 + 0.3 V
    ("TexasInstruments/INA229AIDGS", "vin_unset", ["vinp=unset"], "warning", "UNVERIFIED vin_diff_abs_IN_P"),
    ("TexasInstruments/INA229AIDGS", "ambient_out", ["ta=-40°C to 130°C"], "error", "ta_rec_ambient"),
    ("TexasInstruments/INA229AIDGS", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ta_rec_ambient"),
    ("STMicroelectronics/VNF1248F", "nominal", [], "pass", ""),
    ("STMicroelectronics/VNF1248F", "vs_op_out", ["vs=61V"], "error", "vs_op_VS"),
    ("STMicroelectronics/VNF1248F", "vspi_op_out", ["vspi=6.2V"], "error", "vspi_op_VSPI"),
    ("STMicroelectronics/VNF1248F", "spi_in_out", ["vsck=7V"], "error", "abs_spi_in_SCK"),
    ("STMicroelectronics/VNF1248F", "diag_v3v3_out", ["vdiag=3.6V"], "error", "abs_diag_v3v3_DIAG"),  # > 3.201 + 0.3
    ("STMicroelectronics/VNF1248F", "diag_abs_out", ["vdiag=4.7V"], "error", "abs_diag_DIAG"),
    ("STMicroelectronics/VNF1248F", "isns_diff_out", ["visnsn=44V"], "error", "abs_dvisns_ISNS_P"),  # 48.48 - 44 > 3.3
    ("STMicroelectronics/VNF1248F", "isns_abs_out", ["visnsp=71V", "visnsn=71V"], "error", "abs_isns_ISNS_P"),
    ("STMicroelectronics/VNF1248F", "v3v3_unset", ["vv3v3=unset"], "warning", "UNVERIFIED abs_diag_v3v3_DIAG"),
    ("Panasonic/ERJ-2RKF", "nominal", [], "pass", ""),
    ("Panasonic/ERJ-2RKF", "r_decimal_value", ["value=49.9ohm", "va=1V"], "pass", ""),  # 49R9 code; rated sqrt(0.1 x 49.9) = 2.2 V
    ("Panasonic/ERJ-2RKF", "power_limited", ["value=1kohm", "va=12V"], "error", "rated_voltage"),  # > sqrt(0.1 x 1k) = 10 V
    ("Panasonic/ERJ-2RKF", "vlimit_limited", ["value=1Mohm", "va=55V"], "error", "rated_voltage"),  # > 50 V limit
    ("Panasonic/ERJ-2RKF", "value_not_allowed", ["value=1.01kohm"], "error", "value_allowed"),  # not E24/E96
    ("Panasonic/ERJ-2RKF", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERJ-2RKF", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERJ-2RKF", "reversed_polarity", ["value=1kohm", "va=0V", "vb=12V"], "error", "rated_voltage"),  # |V| > 10 V
    ("Panasonic/ERJ-2RKF", "both_nets_spread", ["va=5V 5%", "vb=5V 5%"], "pass", ""),  # worst |V| 0.5 V << 31.6 V
    ("Panasonic/ERJ-3EKF", "nominal", [], "pass", ""),
    ("Panasonic/ERJ-3EKF", "r_decimal_value", ["value=49.9ohm", "va=1V"], "pass", ""),  # 49R9 code; rated sqrt(0.1 x 49.9) = 2.2 V
    ("Panasonic/ERJ-3EKF", "power_limited", ["value=1kohm", "va=12V"], "error", "rated_voltage"),  # > sqrt(0.1 x 1k) = 10 V
    ("Panasonic/ERJ-3EKF", "vlimit_limited", ["value=1Mohm", "va=80V"], "error", "rated_voltage"),  # > 75 V limit
    ("Panasonic/ERJ-3EKF", "value_not_allowed", ["value=1.01kohm"], "error", "value_allowed"),  # not E24/E96
    ("Panasonic/ERJ-3EKF", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERJ-3EKF", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERJ-3EKF", "reversed_polarity", ["value=1kohm", "va=0V", "vb=12V"], "error", "rated_voltage"),  # |V| > 10 V
    ("Panasonic/ERJ-3EKF", "both_nets_spread", ["va=5V 5%", "vb=5V 5%"], "pass", ""),  # worst |V| 0.5 V << 31.6 V
    ("TexasInstruments/INA241DGK", "nominal", [], "pass", ""),
    ("TexasInstruments/INA241DGK", "b5_nominal", ["variant=INA241B5IDGK"], "pass", ""),
    ("TexasInstruments/INA241DGK", "vs_rec_out", ["vs=21V"], "error", "vs_rec_VS"),  # REF 0 V still inside GND - 0.3 V
    ("TexasInstruments/INA241DGK", "vcm_out", ["vinp=111V", "vinn=111V"], "error", "vcm_rec_IN_P"),  # both inputs moved
    ("TexasInstruments/INA241DGK", "vdiff_out", ["vinn=10V"], "error", "vdiff_abs_IN_P"),  # 47.52 - 10 > 30 V
    ("TexasInstruments/INA241DGK", "vref_above_vs", ["vref1=5.5V"], "error", "vref_abs_REF1"),  # > VS(min) 4.75 + 0.3 V
    ("TexasInstruments/INA241DGK", "vref_below_gnd", ["vref2=-0.5V"], "error", "vref_abs_REF2"),
    ("TexasInstruments/INA241DGK", "vref_range_out", ["vref2=-0.2V"], "warning", "vref_range_25c_REF2"),  # inside abs GND - 0.3 V
    ("TexasInstruments/INA241DGK", "vref_range_waived", ["vref2=-0.2V", "waive=test rationale DS p.5"], "pass", ""),
    ("TexasInstruments/INA241DGK", "vs_unset", ["vs=unset"], "warning", "UNVERIFIED vs_rec_VS"),
    ("TexasInstruments/INA241DGK", "ambient_out", ["ta=-40°C to 130°C"], "error", "ta_rec_ambient"),
    ("TexasInstruments/INA241DGK", "b3_ambient_out", ["variant=INA241B3IDGK", "ta=-40°C to 130°C"], "error", "ta_rec_ambient"),
    ("TexasInstruments/INA241DGK", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ta_rec_ambient"),
    ("Murata/GCM155", "nominal", [], "pass", ""),
    ("Murata/GCM155", "rated_v_out", ["va=52V"], "error", "rated_v_P1"),  # > DC 50 V
    ("Murata/GCM155", "reversed_out", ["va=0V", "vb=52V"], "error", "rated_v_P1"),  # non-polar: -52 V also fails
    ("Murata/GCM155", "both_nets_spread", ["va=48V 1%", "vb=0V"], "pass", ""),  # 48.48 V worst case, inside 50 V
    ("Murata/GCM155", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_v_P1"),
    ("Murata/GCM155", "ambient_out", ["ta=-40°C to 130°C"], "error", "op_temp_ambient"),
    ("Murata/GCM188", "nominal", [], "pass", ""),
    ("Murata/GCM188", "rated_v_out", ["va=52V"], "error", "rated_v_P1"),  # > DC 50 V
    ("Murata/GCM188", "reversed_out", ["va=0V", "vb=52V"], "error", "rated_v_P1"),  # non-polar: -52 V also fails
    ("Murata/GCM188", "both_nets_spread", ["va=48V 1%", "vb=0V"], "pass", ""),  # 48.48 V worst case, inside 50 V
    ("Murata/GCM188", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_v_P1"),
    ("Murata/GCM188", "ambient_out", ["ta=-40°C to 130°C"], "error", "op_temp_ambient"),
    ("TexasInstruments/TPS48000QDGXQ1", "nominal", [], "pass", ""),
    ("TexasInstruments/TPS48000QDGXQ1", "vs_abs_out", ["vs=101V"], "error", "abs_vs_cs_gnd_VS"),  # also fails rec_vs_VS
    ("TexasInstruments/TPS48000QDGXQ1", "vs_rec_out", ["vs=96V"], "error", "rec_vs_VS"),  # inside abs 100 V, outside rec-op 95 V
    ("TexasInstruments/TPS48000QDGXQ1", "vs_scp_min_out", ["vs=3.8V"], "warning", "rec_vs_scp_min_VS"),  # inside rec-op 3.5 V, below SCP 4 V
    ("TexasInstruments/TPS48000QDGXQ1", "vs_scp_min_waived", ["vs=3.8V", "waive=SCP not used, DS p.4"], "pass", ""),
    ("TexasInstruments/TPS48000QDGXQ1", "csp_abs_out", ["vcsp=101V", "vcsn=101V"], "error", "abs_vs_cs_gnd_CS_P"),  # both CS nets moved
    ("TexasInstruments/TPS48000QDGXQ1", "cs_pair_out", ["vcsn=50V"], "error", "abs_cs_pair_CS_P"),  # 47.52 V < 50 - 1 V
    ("TexasInstruments/TPS48000QDGXQ1", "en_rec_out", ["ven=66V"], "error", "rec_en_inp_cs_sel_EN_UVLO"),  # inside abs 70 V
    ("TexasInstruments/TPS48000QDGXQ1", "ov_abs_out", ["vov=71V"], "error", "abs_input_vs_pos_OV"),
    ("TexasInstruments/TPS48000QDGXQ1", "scp_test_out", ["vscp=6V"], "error", "abs_iscp_tmr_scp_test_SCP_TEST"),
    ("TexasInstruments/TPS48000QDGXQ1", "flt_rec_out", ["vflt=16V"], "error", "rec_flt_FLT"),  # inside abs 20 V
    ("TexasInstruments/TPS48000QDGXQ1", "flt_gd_abs_out", ["vfltgd=21V"], "error", "abs_flt_gnd_FLT_GD"),
    ("TexasInstruments/TPS48000QDGXQ1", "vs_unset", ["vs=unset"], "warning", "UNVERIFIED abs_vs_cs_gnd_VS"),
    ("TexasInstruments/TPS48000QDGXQ1", "ambient_out", ["ta=-40°C to 130°C"], "error", "ta_grade_1_ambient"),
    ("TexasInstruments/TPS48000QDGXQ1", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ta_grade_1_ambient"),
    ("Vishay/WSK2512R0250D", "nominal", [], "pass", ""),
    ("Vishay/WSK2512R0250D", "ambient_out", ["ta=-40°C to 180°C"], "error", "t_oper_ambient"),
    ("Vishay/WSK2512R0250D", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED t_oper_ambient"),
]


def outcome(rc, out):
    """pass / error / warning from a pcb build exit code and output (judge by exit code first)."""
    if rc == 0:
        return "pass"
    lines = [ln for ln in out.splitlines() if "Build failed" not in ln]
    if any(ln.startswith("Error") for ln in lines):
        return "error"
    if any(ln.startswith("Warning") for ln in lines):
        return "warning"
    return "unknown"


@unittest.skipUnless(shutil.which("pcb"), "pcb not installed")
class TestBuilds(unittest.TestCase):
    def test_packages_build_clean(self):
        for toml in sorted((ROOT / "components").glob("*/*/component.toml")):
            r = subprocess.run(["pcb", "build", "-Wstyle", "-Dwarnings", str(toml.parent)],
                               capture_output=True, text=True)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_harness_cases(self):
        for comp, name, overrides, expect, text in CASES:
            d = ROOT / "components" / comp
            harness = d / "_harness.zen"
            shutil.copy(HARNESS / f"{d.name}_harness.zen", harness)
            try:
                cmd = ["pcb", "build", "-Wstyle", "-Dwarnings", str(harness)] + [f"--config={c}" for c in overrides]
                r = subprocess.run(cmd, capture_output=True, text=True)
            finally:
                harness.unlink()
            out = r.stdout + r.stderr
            with self.subTest(component=d.name, case=name):
                self.assertEqual(outcome(r.returncode, out), expect, out)
                self.assertIn(text, out)


if __name__ == "__main__":
    unittest.main()
