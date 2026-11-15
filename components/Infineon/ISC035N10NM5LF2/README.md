<!-- GENERATED - do not edit. Run: python3 -m lib.readme -->

# ISC035N10NM5LF2

## Part

- **mpn**: ISC035N10NM5LF2
- **manufacturer**: Infineon Technologies
- **description**: 100 V N-channel OptiMOS 5 Linear FET 2 (hot swap / e-fuse), 164 A, 3.5 mohm max, PG-TDSON-8-59
- **category**: mosfet
- **package**: PG-TDSON-8-59
- **datasheet_url**: https://www.infineon.com
- **datasheet_file**: docs/datasheets/infineon/infineon-isc035n10nm5lf2-datasheet-en.pdf
- **datasheet_rev**: Revision 2.3
- **datasheet_date**: 2025-11-07
- **temp_grade**: -55 to 175 degC
- **kicad_symbol**: ISC035N10NM5LF2.kicad_sym
- **kicad_footprint**: ISC035N10NM5LF2.kicad_mod
- **step**: ISC035N10NM5LF2.step

## Pins

| Pin | Name | Type | Function | Cite |
|---|---|---|---|---|
| 1 | S | passive | Source, discrete MOSFET terminal; pins 1 to 3 are one source node (DS p.1 pin diagram 'Source Pin 1-3') | DS p.1, pin diagram (PG-TDSON-8), Source Pin 1-3 |
| 2 | S | passive | Source, discrete MOSFET terminal; same source node as pin 1 | DS p.1, pin diagram (PG-TDSON-8), Source Pin 1-3 |
| 3 | S | passive | Source, discrete MOSFET terminal; same source node as pin 1 | DS p.1, pin diagram (PG-TDSON-8), Source Pin 1-3 |
| 4 | G | passive | Gate, discrete MOSFET terminal (DS p.1 pin diagram 'Gate Pin 4') | DS p.1, pin diagram (PG-TDSON-8), Gate Pin 4 |
| 5 | D | passive | Drain, discrete MOSFET terminal; pins 5 to 8 and the tab are one drain node (DS p.1 'Drain Pin 5-8, tab'). The drain tab (exposed pad) has no DS number and is not a separate pin: the footprint makes it pad 5 (a real pad on the drain net), overlapping the drain lead pads 5-8. | DS p.1, pin diagram (PG-TDSON-8), Drain Pin 5-8, tab |
| 6 | D | passive | Drain, discrete MOSFET terminal; same drain node as pin 5 | DS p.1, pin diagram (PG-TDSON-8), Drain Pin 5-8, tab |
| 7 | D | passive | Drain, discrete MOSFET terminal; same drain node as pin 5 | DS p.1, pin diagram (PG-TDSON-8), Drain Pin 5-8, tab |
| 8 | D | passive | Drain, discrete MOSFET terminal; same drain node as pin 5 | DS p.1, pin diagram (PG-TDSON-8), Drain Pin 5-8, tab |

## Parameters: abs_max

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Continuous drain current, TC = 25 degC | ID |  |  | 164 | A | VGS = 10 V, TC = 25 degC Note: Footnote 1: rating refers to the product only with absolute maximum values, case temperature as specified; derate for other case temperatures (Diagram 2). | DS p.3, Table 2 Maximum ratings, Continuous drain current ID (row 1) |
| Continuous drain current, TC = 100 degC | ID |  |  | 116 | A | VGS = 10 V, TC = 100 degC | DS p.3, Table 2 Maximum ratings, Continuous drain current ID (row 2) |
| Continuous drain current, PCB-limited | ID |  |  | 19 | A | VGS = 10 V, TA = 25 degC, RthJA = 50 degC/W Note: Footnote 2: 40 x 40 x 1.5 mm FR4 PCB with 6 cm2 drain copper, vertical in still air. Printed RthJA 50 degC/W is the PCB value. | DS p.3, Table 2 Maximum ratings, Continuous drain current ID (row 3), footnote 2 |
| Pulsed drain current | ID,pulse |  |  | 656 | A | TA = 25 degC Note: The SOA (Diagrams 3, 4) is not extracted (open item). | DS p.3, Table 2 Maximum ratings, Pulsed drain current ID,pulse (footnote 3: Diagrams 3 and 4) |
| Gate-source voltage | VGS | -20 (rel. S) |  | 20 (rel. S) | V | Note: No reference pin printed; applied as gate to source (pin-pair row, S is the reference). | DS p.3, Table 2 Maximum ratings, Gate source voltage VGS |
| Power dissipation, TC = 25 degC | Ptot |  |  | 217 | W | TC = 25 degC Note: Ptot = f(TC) is Diagram 1 (curve, not extracted). Stored at TC = 25 degC only. | DS p.3, Table 2 Maximum ratings, Power dissipation Ptot (row 1) |
| Power dissipation, PCB-limited | Ptot |  |  | 3 | W | TA = 25 degC, RthJA = 50 degC/W | DS p.3, Table 2 Maximum ratings, Power dissipation Ptot (row 2), footnote 2 |
| Operating and storage temperature Tj, Tstg | Tj,Tstg | -55 |  | 175 | degC | Note: Junction range (Tj); the storage part of the row is assembly-owned (see the unchecked reason). | DS p.3, Table 2 Maximum ratings, Operating and storage temperature Tj, Tstg |
| Avalanche energy, single pulse | EAS |  |  | 398 | mJ | ID = 50 A, RGS = 25 ohm | DS p.3, Table 2 Maximum ratings, Avalanche energy, single pulse EAS (footnote 4: Diagram 14) |

## Parameters: rec_op

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Drain-source voltage rating | VDS |  |  | 100 (rel. S) | V | Note: Not a row of the Maximum ratings table (DS p.3). The DS gives no temperature for it. The guaranteed minimum breakdown voltage is V(BR)DSS = 100 V at 25 degC (vbr_dss, DS p.5 Table 4). Printed with no MIN/TYP/MAX label: stored as max. Only the upper bound is checked. | DS p.1, Table 1 Key performance parameters, VDS |

## Parameters: electrical

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Drain-source breakdown voltage | V(BR)DSS | 100 |  |  | V | VGS = 0 V, ID = 1 mA | DS p.5, Table 4 Static characteristics, Drain-source breakdown voltage V(BR)DSS |
| Gate threshold voltage | VGS(th) | 2.8 | 3.15 | 3.5 | V | VDS = VGS, ID = 115 uA | DS p.5, Table 4 Static characteristics, Gate threshold voltage VGS(th) |
| Zero gate voltage drain current, Tj = 25 degC | IDSS |  | 0.1 | 1 | uA | VDS = 100 V, VGS = 0 V, Tj = 25 degC | DS p.5, Table 4 Static characteristics, Zero gate voltage drain current IDSS (row 1) |
| Zero gate voltage drain current, Tj = 125 degC | IDSS |  | 10 | 100 | uA | VDS = 100 V, VGS = 0 V, Tj = 125 degC Note: Single stated temperature (125 degC); not a full-range row. | DS p.5, Table 4 Static characteristics, Zero gate voltage drain current IDSS (row 2) |
| Gate-source leakage current | IGSS |  | 10 | 100 | nA | VGS = 20 V, VDS = 0 V | DS p.5, Table 4 Static characteristics, Gate-source leakage current IGSS |
| Drain-source on-state resistance, VGS = 10 V | RDS(on) |  | 3.0 | 3.5 | mohm | VGS = 10 V, ID = 50 A Note: Table 1 prints RDS(on),max 3.5 mohm (DS p.1), same value. Tj = 25 degC only: no RDS(on) row over temperature (open item, see calc.py). | DS p.5, Table 4 Static characteristics, Drain-source on-state resistance RDS(on) |
| Normalized drain-source on-state resistance at Tj = 100 degC (curve) | RDS(on)/RDS(on)25C |  | 1.55 |  |  | ID = 50 A, VGS = 10 V, normalized to 25 degC, Tj = 100 degC Note: Read by eye, +/-0.05 (re-read at 220 dpi against the 25 degC = 1.0 point). The figure has one unlabelled line: read as the typical curve (no typ or max line printed). Not a bound. | DS p.9, Diagram 10 figure Normalized drain-source on resistance, RDS(on)=f(Tj), ID = 50 A, VGS = 10 V, read at Tj = 100 degC (curve) |
| Normalized drain-source on-state resistance at Tj = 150 degC (curve) | RDS(on)/RDS(on)25C |  | 2.0 |  |  | ID = 50 A, VGS = 10 V, normalized to 25 degC, Tj = 150 degC Note: Read by eye, +/-0.05 (re-read at 220 dpi against the 25 degC = 1.0 point). Unlabelled single line: typical curve, not a bound. The curve runs to about 175 degC (factor about 2.3 there); 150 degC is the printed Tj max. | DS p.9, Diagram 10 figure Normalized drain-source on resistance, RDS(on)=f(Tj), ID = 50 A, VGS = 10 V, read at Tj = 150 degC (curve) |
| Gate resistance | RG |  | 1.5 | 2.3 | ohm |  | DS p.5, Table 4 Static characteristics, Gate resistance RG |
| Transconductance | gfs | 26 | 52 |  | A/V | \|VDS\| >= 2\|ID\| RDS(on)max, ID = 50 A Note: Printed unit S; S = A/V, stored as A/V (loader has no S unit). Footnote 6: defined by design, not subject to production test. | DS p.5, Table 4 Static characteristics, Transconductance gfs (footnote 6) |
| Input capacitance | Ciss |  | 5500 | 7200 | pF | VGS = 0 V, VDS = 50 V, f = 1 MHz Note: Defined by design. Not subject to production test (footnote 7). | DS p.5, Table 5 Dynamic characteristics, Input capacitance Ciss |
| Output capacitance | Coss |  | 780 | 1000 | pF | VGS = 0 V, VDS = 50 V, f = 1 MHz Note: Defined by design. Not subject to production test (footnote 7). | DS p.5, Table 5 Dynamic characteristics, Output capacitance Coss |
| Reverse transfer capacitance | Crss |  | 19 | 33 | pF | VGS = 0 V, VDS = 50 V, f = 1 MHz Note: Defined by design. Not subject to production test (footnote 7). | DS p.5, Table 5 Dynamic characteristics, Reverse transfer capacitance Crss |
| Turn-on delay time | td(on) |  | 16 |  | ns | VDD = 50 V, VGS = 10 V, ID = 50 A, RG,ext = 1.6 ohm Note: Typical only (no min or max printed). | DS p.5, Table 5 Dynamic characteristics, Turn-on delay time td(on) |
| Rise time | tr |  | 11 |  | ns | VDD = 50 V, VGS = 10 V, ID = 50 A, RG,ext = 1.6 ohm Note: Typical only. | DS p.5, Table 5 Dynamic characteristics, Rise time tr |
| Turn-off delay time | td(off) |  | 25 |  | ns | VDD = 50 V, VGS = 10 V, ID = 50 A, RG,ext = 1.6 ohm Note: Typical only. | DS p.5, Table 5 Dynamic characteristics, Turn-off delay time td(off) |
| Fall time | tf |  | 10 |  | ns | VDD = 50 V, VGS = 10 V, ID = 50 A, RG,ext = 1.6 ohm Note: Typical only. | DS p.5, Table 5 Dynamic characteristics, Fall time tf |
| Gate plateau voltage | Vplateau |  | 6.4 |  | V | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V Note: Typical only (value in the Typ column, Max '-'). | DS p.6, Table 6 Gate charge characteristics, Gate plateau voltage Vplateau |
| Diode continuous forward current | IS |  |  | 159 | A | TC = 25 degC Note: Single stated temperature (TC = 25 degC). | DS p.6, Table 7 Reverse diode, Diode continuous forward current IS |
| Diode pulse current | IS,pulse |  |  | 656 | A | TC = 25 degC Note: Condition cell is merged with IS on DS p.6 (render): TC = 25 degC applies to both rows. | DS p.6, Table 7 Reverse diode, Diode pulse current IS,pulse |
| Diode forward voltage | VSD |  | 0.84 | 1.2 | V | VGS = 0 V, IF = 50 A, Tj = 25 degC | DS p.6, Table 7 Reverse diode, Diode forward voltage VSD |
| Reverse recovery time | trr |  | 49 | 98 | ns | VR = 50 V, IF = 50 A, diF/dt = 100 A/us Note: Defined by design. Not subject to production test (footnote 10). | DS p.6, Table 7 Reverse diode, Reverse recovery time trr |
| Gate to source charge | Qgs |  | 35 |  | nC | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V | DS p.6, Table 6 Gate charge characteristics, Gate to source charge Qgs |
| Gate charge at threshold | Qg(th) |  | 17 |  | nC | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V | DS p.6, Table 6 Gate charge characteristics, Gate charge at threshold Qg(th) |
| Gate to drain charge | Qgd |  | 12 | 18 | nC | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V Note: Defined by design. Not subject to production test (footnote 9). | DS p.6, Table 6 Gate charge characteristics, Gate to drain charge Qgd (footnote 9) |
| Switching charge | Qsw |  | 30 |  | nC | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V | DS p.6, Table 6 Gate charge characteristics, Switching charge Qsw |
| Gate charge total | Qg |  | 70 | 88 | nC | VDD = 50 V, ID = 50 A, VGS = 0 to 10 V Note: Defined by design. Not subject to production test (footnote 9). | DS p.6, Table 6 Gate charge characteristics, Gate charge total Qg (footnote 9) |
| Output charge | Qoss |  | 90 | 115 | nC | VDS = 50 V, VGS = 0 V Note: Defined by design. Not subject to production test (footnote 9). | DS p.6, Table 6 Gate charge characteristics, Output charge Qoss (footnote 9) |
| Reverse recovery charge | Qrr |  | 72 | 144 | nC | VR = 50 V, IF = 50 A, diF/dt = 100 A/us Note: Defined by design. Not subject to production test (footnote 10). | DS p.6, Table 7 Reverse diode, Reverse recovery charge Qrr (footnote 10) |

## Parameters: thermal

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Thermal resistance, junction to case, bottom | RthJC |  |  | 0.7 | degC/W | Note: Only a max is printed; the Min/Typ columns are '-'. | DS p.4, Table 3 Thermal characteristics, Thermal resistance junction-case, bottom |
| Thermal resistance, junction to case, top | RthJC |  |  | 20 | degC/W | Note: Top side is not the drain-to-PCB path; calc.tj_from_case uses the bottom row. | DS p.4, Table 3 Thermal characteristics, Thermal resistance junction-case, top |
| Thermal resistance, junction to ambient, 6 cm2 cooling area | RthJA |  |  | 50 | degC/W | 6 cm2 cooling area Note: Valid only for the DS PCB (footnote 5). | DS p.4, Table 3 Thermal characteristics, Thermal resistance junction-ambient, 6 cm2 cooling area (RthJA), footnote 5 |

## Limits of this data

Rows by scope: 25C 24, na 18 (25C rows hold only at 25 degC). Curve (graph) rows: 2. Text rows: 0. Temperatures are junction (TJ): analyse with TJ = TA + P x RthJA; no ambient range is printed.

## Zener checks

Generated wrapper: `ISC035N10NM5LF2.zen` (`python3 -m lib.zen`). abs_max and rec_op rows are errors (abs_max x derate); 25C and partial rows are waivable warnings; a checked net with no voltage is UNVERIFIED.

| Param | Name | Checked against | Not checked / reason |
|---|---|---|---|
| vds_rating | Drain-source voltage rating | pins D |  |
| id_tc25 | Continuous drain current, TC = 25 degC | UNCHECKED | not a voltage; owner: module |
| id_tc100 | Continuous drain current, TC = 100 degC | UNCHECKED | not a voltage; owner: module |
| id_pcb | Continuous drain current, PCB-limited | UNCHECKED | not a voltage; owner: module |
| id_pulse | Pulsed drain current | UNCHECKED | not a voltage; owner: module |
| vgs | Gate-source voltage | pins G |  |
| ptot_tc25 | Power dissipation, TC = 25 degC | UNCHECKED | not a voltage; owner: module |
| ptot_pcb | Power dissipation, PCB-limited | UNCHECKED | not a voltage; owner: module |
| tj_tstg | Operating and storage temperature Tj, Tstg | UNCHECKED | TJ: needs dissipation x RthJA; owner: module (Tstg part: owner: assembly) |
| eas | Avalanche energy, single pulse | UNCHECKED | not a voltage; owner: module |

## Equations

### `conduction_loss`

```
Not a DS equation: conduction loss P = I^2 x RDS(on). Use the 25 degC max row (rds_on_10v.max) for a bound at
25 degC; above 25 degC use rds_on_at_tj_typ, a typical estimate.
i: drain current, A (either sign; squared). rds_on: ohm. Returns: W.
```

Inputs:

- `rds_on` -> `rds_on_10v.max` (typ 3.0 max 3.5 mohm)

### `rds_on_at_tj_typ`

```
Curve-based estimate, not a bound: RDS(on) at Tj = rds_on_25 x factor. factor = RDS(on)/RDS(on)@25 degC read off
DS p.9 Diagram 10 (normalized, ID = 50 A, VGS = 10 V). The curve is unlabelled, read as typical.
rds_on_25: ohm (the 25 degC max row). factor: fraction, 1.0 at 25 degC. Returns: ohm.
```

Inputs:

- `rds_on_25` -> `rds_on_10v.max` (typ 3.0 max 3.5 mohm)
- `factor` -> `norm_rds_150c.typ` (typ 2.0 )

### `tj_from_case`

```
Not a DS equation: TJ = TC + P x RthJC, the case-referenced junction temperature (DS p.4 Table 3 RthJC).
The bottom RthJC (drain tab to case) is used. tc: case temperature, degC. p: dissipation, W, >= 0.
rth_jc: degC/W, use the max row for a bound. Returns: degC.
```

Inputs:

- `rth_jc` -> `rth_jc_bottom.max` (max 0.7 degC/W)

### `tj_from_ambient`

```
Not a DS equation: TJ = TA + P x RthJA (DS p.4 Table 3, 6 cm2 cooling area, footnote 5).
Valid only for that PCB. ta: ambient temperature, degC. p: dissipation, W, >= 0. rth_ja: degC/W, use the max row.
Returns: degC.
```

Inputs:

- `rth_ja` -> `rth_ja.max` (max 50 degC/W)

### `gate_drive_time`

```
Not a DS equation: time to charge the gate, t = |Qg| / Ig, Qg from DS p.6 Table 6 (Qg, VGS = 0 to 10 V) and Ig
the gate drive current (design choice). abs() is applied so a printed negative charge gives a time.
qg: C. ig: A, > 0. Returns: s.
```

Inputs:

- `qg` -> `qg.max` (typ 70 max 88 nC)


## Examples

| Call | Computed | Expected | Rel. tol | Result | Cite |
|---|---|---|---|---|---|
| conduction_loss(i=50, rds_on=0.0035) | 8.75 | 8.75 | 1e-09 | pass | DS p.5 Table 4 and p.1 Table 1, RDS(on) max 3.5 mohm at ID = 50 A (arithmetic only) |
| rds_on_at_tj_typ(rds_on_25=0.0035, factor=1) | 0.0035 | 0.0035 | 1e-09 | pass | DS p.9 Diagram 10 is normalized to 25 degC: factor 1.0 at 25 degC by definition (arithmetic only) |
| tj_from_ambient(ta=25, p=3, rth_ja=50) | 175 | 175 | 1e-09 | pass | DS p.3 Table 2 Ptot = 3 W at TA = 25 degC with RthJA = 50 degC/W gives Tj = 175 degC, the printed Tj max |
| tj_from_case(tc=25, p=10, rth_jc=0.7) | 32 | 32 | 1e-09 | pass | DS p.4 Table 3 RthJC max 0.7 degC/W (arithmetic only) |
| gate_drive_time(qg=8.8e-08, ig=1) | 8.8e-08 | 8.8e-08 | 1e-09 | pass | DS p.6 Table 6 Qg max 88 nC with Ig = 1 A (arithmetic only) |
