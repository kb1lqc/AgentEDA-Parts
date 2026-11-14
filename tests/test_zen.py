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

    def test_ground_names(self):
        from lib.zen import GROUND_NAMES
        self.assertIn("VSSA", GROUND_NAMES)  # analog ground (STM32 VSSA) is io(Ground), like VSS

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
    ("Panasonic/ERJ-6ENF", "nominal", [], "pass", ""),
    ("Panasonic/ERJ-6ENF", "r_decimal_value", ["value=49.9ohm", "va=1V"], "pass", ""),  # 49R9 code; rated sqrt(0.125 x 49.9) = 2.5 V
    ("Panasonic/ERJ-6ENF", "power_limited", ["value=1kohm", "va=12V"], "error", "rated_voltage"),  # > sqrt(0.125 x 1k) = 11.2 V
    ("Panasonic/ERJ-6ENF", "vlimit_limited", ["value=2.2Mohm", "va=155V"], "error", "rated_voltage"),  # > 150 V limit
    ("Panasonic/ERJ-6ENF", "value_not_allowed", ["value=1.01kohm"], "error", "value_allowed"),
    ("Panasonic/ERJ-6ENF", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERJ-6ENF", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERJ-8ENF", "nominal", [], "pass", ""),
    ("Panasonic/ERJ-8ENF", "power_limited", ["value=1kohm", "va=17V"], "error", "rated_voltage"),  # > sqrt(0.25 x 1k) = 15.8 V
    ("Panasonic/ERJ-8ENF", "vlimit_limited", ["value=2.2Mohm", "va=205V"], "error", "rated_voltage"),  # > 200 V limit
    ("Panasonic/ERJ-8ENF", "value_not_allowed", ["value=1.01kohm"], "error", "value_allowed"),
    ("Panasonic/ERJ-8ENF", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERJ-8ENF", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERA-2AEB", "nominal", [], "pass", ""),
    ("Panasonic/ERA-2AEB", "e24_low_value", ["value=47ohm", "va=1V"], "pass", ""),  # E24 at the range minimum
    ("Panasonic/ERA-2AEB", "e96_below_min", ["value=47.5ohm", "va=1V"], "error", "value_allowed"),  # E96 only from 100 ohm
    ("Panasonic/ERA-2AEB", "e96_allowed", ["value=1.05kohm", "va=1V"], "pass", ""),  # 1051 code
    ("Panasonic/ERA-2AEB", "power_limited", ["value=1kohm", "va=9V"], "error", "rated_voltage"),  # > sqrt(0.063 x 1k) = 7.9 V
    ("Panasonic/ERA-2AEB", "vlimit_limited", ["value=100kohm", "va=52V"], "error", "rated_voltage"),  # > 50 V limit
    ("Panasonic/ERA-2AEB", "out_of_range", ["value=150kohm"], "error", "value_allowed"),  # range 47 ohm to 100 kohm
    ("Panasonic/ERA-2AEB", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERA-2AEB", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERA-3AEB", "nominal", [], "pass", ""),
    ("Panasonic/ERA-3AEB", "e96_below_min", ["value=47.5ohm", "va=1V"], "error", "value_allowed"),  # E96 only from 100 ohm
    ("Panasonic/ERA-3AEB", "power_limited", ["value=1kohm", "va=11V"], "error", "rated_voltage"),  # > sqrt(0.1 x 1k) = 10 V
    ("Panasonic/ERA-3AEB", "vlimit_limited", ["value=330kohm", "va=77V"], "error", "rated_voltage"),  # > 75 V limit
    ("Panasonic/ERA-3AEB", "out_of_range", ["value=390kohm"], "error", "value_allowed"),  # range to 330 kohm
    ("Panasonic/ERA-3AEB", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERA-3AEB", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
    ("Panasonic/ERA-6AEB", "nominal", [], "pass", ""),
    ("Panasonic/ERA-6AEB", "e96_below_min", ["value=47.5ohm", "va=1V"], "error", "value_allowed"),
    ("Panasonic/ERA-6AEB", "power_limited", ["value=1kohm", "va=12V"], "error", "rated_voltage"),  # > sqrt(0.125 x 1k) = 11.2 V
    ("Panasonic/ERA-6AEB", "vlimit_limited", ["value=1Mohm", "va=102V"], "error", "rated_voltage"),  # > 100 V limit
    ("Panasonic/ERA-6AEB", "out_of_range", ["value=1.5Mohm"], "error", "value_allowed"),  # range to 1 Mohm (1.5 M is E24)
    ("Panasonic/ERA-6AEB", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Panasonic/ERA-6AEB", "ambient_out", ["ta=-40°C to 160°C"], "error", "category_temp_ambient"),
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
    ("STMicroelectronics/STM32H723ZET6", "nominal", [], "pass", ""),
    ("STMicroelectronics/STM32H723ZET6", "vdd_out", ["vdd=3.7V"], "error", "vdd_op_VDD"),
    ("STMicroelectronics/STM32H723ZET6", "vdda_low", ["vdda=1.5V", "vref=1.4V"], "error", "vdda_op_adc_VDDA"),  # VREF+ moved below VDDA too
    ("STMicroelectronics/STM32H723ZET6", "vref_above_vdda", ["vref=3.2V"], "warning", "adc16_vref_plus_ge2_VREF_P"),  # > VDDA(min) 3.135 V
    ("STMicroelectronics/STM32H723ZET6", "vref_tied_waived", ["vref=3.3V 5%", "waive_vref=VREF+ tied to VDDA, DS p.162 Table 80"], "pass", ""),
    ("STMicroelectronics/STM32H723ZET6", "vref_low", ["vref=1.5V"], "warning", "adc16_vref_plus_ge2_VREF_P"),
    ("STMicroelectronics/STM32H723ZET6", "vbat_low", ["vbat=1.0V"], "warning", "vbat_op_VBAT"),
    ("STMicroelectronics/STM32H723ZET6", "vbat_waived", ["vbat=1.0V", "waive=VBAT low with VDD present, DS p.91 footnote 2"], "pass", ""),
    ("STMicroelectronics/STM32H723ZET6", "vbat_abs_out", ["vbat=4.2V"], "error", "abs_vddx_vss_VBAT"),  # also the vbat_op warning
    ("STMicroelectronics/STM32H723ZET6", "vusb_out", ["vusb=3.8V"], "error", "vdd33usb_op_nousb_VDD33USB"),
    ("STMicroelectronics/STM32H723ZET6", "boot0_out", ["boot0=9.5V"], "error", "abs_vin_boot0_BOOT0"),
    ("STMicroelectronics/STM32H723ZET6", "nrst_out", ["nrst=4.2V"], "error", "abs_vin_other_NRST"),
    ("STMicroelectronics/STM32H723ZET6", "pdron_out", ["pdron=4.2V"], "error", "abs_vin_other_PDR_ON"),
    ("STMicroelectronics/STM32H723ZET6", "vdd_unset", ["vdd=unset"], "warning", "UNVERIFIED vdd_op_VDD"),
    ("STMicroelectronics/STM32H723ZET6", "ambient_out", ["ta=-40°C to 105°C"], "error", "ta_range6_max_power_ambient"),
    ("STMicroelectronics/STM32H723ZET6", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ta_range6_max_power_ambient"),
    ("Murata/GCM155", "nominal", [], "pass", ""),  # 0.1 uF 50 V X7R
    ("Murata/GCM155", "tolerance_ambiguous", ["tolerance="], "error", "part_orderable"),  # +/-10 % and +/-20 % both exist
    ("Murata/GCM155", "tolerance_not_listed", ["tolerance=+/-5%"], "error", "part_orderable"),
    ("Murata/GCM155", "other_value", ["value=1uF", "rated=4V", "va=3V"], "pass", ""),  # GCM155R70G105KE02, only +/-10 %
    ("Murata/GCM155", "rated_v_out", ["va=52V"], "error", "rated_voltage: up to 52.0 V"),  # > 50 V
    ("Murata/GCM155", "reversed_out", ["va=0V", "vb=52V"], "error", "rated_voltage"),  # non-polar: -52 V also fails
    ("Murata/GCM155", "derated_out", ["va=48V", "derate=0.9"], "error", "rated_voltage"),  # 48 V > 0.9 x 50 V
    ("Murata/GCM155", "both_nets_spread", ["va=48V 1%", "vb=0V"], "pass", ""),  # 48.48 V worst case, inside 50 V
    ("Murata/GCM155", "value_not_listed", ["value=0.11uF"], "error", "part_orderable"),  # not in the catalog
    ("Murata/GCM155", "voltage_not_listed", ["rated=40V"], "error", "part_orderable"),  # 0.1 uF has no 40 V part
    ("Murata/GCM155", "dielectric_not_listed", ["dielectric=X8R"], "error", "part_orderable"),  # X8R is not in the catalog
    ("Murata/GCM155", "c0g_nominal", ["dielectric=C0G", "value=100pF", "tolerance=+/-1%"], "pass", ""),  # GCM1555C1H101FA16, 100 pF 50 V +/-1 %
    ("Murata/GCM155", "c0g_ambient_out", ["dielectric=C0G", "value=100pF", "tolerance=+/-1%", "ta=-60°C to 85°C"], "error", "ambient_range"),  # C0G range -55 to 125 degC
    ("Murata/GCM155", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM155", "ambient_out", ["ta=-40°C to 130°C"], "error", "ambient_range"),
    ("Murata/GCM155", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ambient_range"),
    ("Murata/GCM188", "nominal", [], "pass", ""),  # 0.1 uF 50 V X7R
    ("Murata/GCM188", "tolerance_optional", ["tolerance="], "pass", ""),  # only one tolerance listed
    ("Murata/GCM188", "rated_v_out", ["va=52V"], "error", "rated_voltage: up to 52.0 V"),  # > 50 V
    ("Murata/GCM188", "reversed_out", ["va=0V", "vb=52V"], "error", "rated_voltage"),  # non-polar: -52 V also fails
    ("Murata/GCM188", "derated_out", ["va=48V", "derate=0.9"], "error", "rated_voltage"),  # 48 V > 0.9 x 50 V
    ("Murata/GCM188", "both_nets_spread", ["va=48V 1%", "vb=0V"], "pass", ""),  # 48.48 V worst case, inside 50 V
    ("Murata/GCM188", "value_not_listed", ["value=0.11uF"], "error", "part_orderable"),  # not in the catalog
    ("Murata/GCM188", "voltage_not_listed", ["rated=40V"], "error", "part_orderable"),  # 0.1 uF has no 40 V part
    ("Murata/GCM188", "dielectric_not_listed", ["dielectric=X8R"], "error", "part_orderable"),  # X8R is not in the catalog
    ("Murata/GCM188", "c0g_nominal", ["dielectric=C0G", "value=100pF", "tolerance=+/-2%"], "pass", ""),  # GCM1885C1H101GA16, 100 pF 50 V +/-2 %
    ("Murata/GCM188", "c0g_ambient_out", ["dielectric=C0G", "value=100pF", "tolerance=+/-2%", "ta=-60°C to 85°C"], "error", "ambient_range"),  # C0G range -55 to 125 degC
    ("Murata/GCM188", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM188", "ambient_out", ["ta=-40°C to 130°C"], "error", "ambient_range"),
    ("Murata/GCM188", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ambient_range"),
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
    ("Murata/GCM21A", "nominal", [], "pass", ""),  # GCM21A5C2E101FX01, 100 pF 250 V C0G +/-1 %
    ("Murata/GCM21A", "tolerance_ambiguous", ["tolerance="], "error", "part_orderable"),  # +/-1/2/5 % all listed
    ("Murata/GCM21A", "rated_v_out", ["va=252V"], "error", "rated_voltage"),  # > 250 V
    ("Murata/GCM21A", "reversed_out", ["va=0V", "vb=252V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM21A", "derated_out", ["va=240V", "derate=0.9"], "error", "rated_voltage"),  # 240 V > 0.9 x 250 V
    ("Murata/GCM21A", "x7r_nominal", ["dielectric=X7R", "value=1000pF", "tolerance=+/-10%"], "pass", ""),  # GCM21AR72E102KWB1, 250 V
    ("Murata/GCM21A", "value_not_listed", ["value=0.1uF", "rated=100V"], "error", "part_orderable"),  # no 0.1 uF in 1.0 mm
    ("Murata/GCM21A", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM21A", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # C0G range -55 to 125 degC
    ("Murata/GCM21A", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ambient_range"),
    ("Murata/GCM21B", "nominal", [], "pass", ""),  # GCM21BR72A104KA37, 0.1 uF 100 V X7R +/-10 %
    ("Murata/GCM21B", "tolerance_ambiguous", ["tolerance="], "error", "part_orderable"),  # +/-10/20 % both listed
    ("Murata/GCM21B", "rated_v_out", ["va=102V"], "error", "rated_voltage"),  # > 100 V
    ("Murata/GCM21B", "reversed_out", ["va=0V", "vb=102V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM21B", "derated_out", ["va=95V", "derate=0.9"], "error", "rated_voltage"),  # 95 V > 0.9 x 100 V
    ("Murata/GCM21B", "c0g_nominal", ["dielectric=C0G", "value=18000pF", "rated=50V", "tolerance=+/-1%", "va=12V 5%"], "pass", ""),  # GCM21B5C1H183FA16
    ("Murata/GCM21B", "value_not_listed", ["value=0.11uF"], "error", "part_orderable"),
    ("Murata/GCM21B", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM21B", "ambient_out", ["ta=-40°C to 130°C"], "error", "ambient_range"),
    ("Murata/GCM21B", "ambient_unset", ["ta=unset"], "warning", "UNVERIFIED ambient_range"),
    ("Murata/GCM216", "nominal", [], "pass", ""),  # GCM2165C2A222FA16
    ("Murata/GCM216", "rated_v_out", ["va=102V"], "error", "rated_voltage"),  # > 100 V
    ("Murata/GCM216", "reversed_out", ["va=0V", "vb=102V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM216", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM216", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM216", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM219", "nominal", [], "pass", ""),  # GCM2195C1K153FA16
    ("Murata/GCM219", "rated_v_out", ["va=81.6V"], "error", "rated_voltage"),  # > 80 V
    ("Murata/GCM219", "reversed_out", ["va=0V", "vb=81.6V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM219", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM219", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM219", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM319", "nominal", [], "pass", ""),  # GCM3195C2A432FA16
    ("Murata/GCM319", "rated_v_out", ["va=102V"], "error", "rated_voltage"),  # > 100 V
    ("Murata/GCM319", "reversed_out", ["va=0V", "vb=102V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM319", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM319", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM319", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM31A", "nominal", [], "pass", ""),  # GCM31A5C2J680GX01
    ("Murata/GCM31A", "rated_v_out", ["va=642.6V"], "error", "rated_voltage"),  # > 630 V
    ("Murata/GCM31A", "reversed_out", ["va=0V", "vb=642.6V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM31A", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM31A", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM31A", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM31B", "nominal", [], "pass", ""),  # GCM31B5C2J272GX01
    ("Murata/GCM31B", "rated_v_out", ["va=642.6V"], "error", "rated_voltage"),  # > 630 V
    ("Murata/GCM31B", "reversed_out", ["va=0V", "vb=642.6V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM31B", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM31B", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM31B", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM31C", "nominal", [], "pass", ""),  # GCM31C5C2J103FX03
    ("Murata/GCM31C", "rated_v_out", ["va=642.6V"], "error", "rated_voltage"),  # > 630 V
    ("Murata/GCM31C", "reversed_out", ["va=0V", "vb=642.6V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM31C", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM31C", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM31C", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM31M", "nominal", [], "pass", ""),  # GCM31M5C1H513JA16
    ("Murata/GCM31M", "rated_v_out", ["va=51V"], "error", "rated_voltage"),  # > 50 V
    ("Murata/GCM31M", "reversed_out", ["va=0V", "vb=51V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM31M", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM31M", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM31M", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM32D", "nominal", [], "pass", ""),  # GCM32D5C3A682GX01
    ("Murata/GCM32D", "rated_v_out", ["va=1020V"], "error", "rated_voltage"),  # > 1000 V
    ("Murata/GCM32D", "reversed_out", ["va=0V", "vb=1020V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM32D", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM32D", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM32D", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM32E", "nominal", [], "pass", ""),  # GCM32E5C3A153GX0A
    ("Murata/GCM32E", "rated_v_out", ["va=1020V"], "error", "rated_voltage"),  # > 1000 V
    ("Murata/GCM32E", "reversed_out", ["va=0V", "vb=1020V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM32E", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM32E", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM32E", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
    ("Murata/GCM32Q", "nominal", [], "pass", ""),  # GCM32QR72J103KWB1
    ("Murata/GCM32Q", "rated_v_out", ["va=642.6V"], "error", "rated_voltage"),  # > 630 V
    ("Murata/GCM32Q", "reversed_out", ["va=0V", "vb=642.6V"], "error", "rated_voltage"),  # non-polar
    ("Murata/GCM32Q", "value_not_listed", ["value=1.23nF"], "error", "part_orderable"),
    ("Murata/GCM32Q", "p1_unset", ["va=unset"], "warning", "UNVERIFIED rated_voltage"),
    ("Murata/GCM32Q", "ambient_out", ["ta=-60°C to 85°C"], "error", "ambient_range"),  # range -55 to 125 degC
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
