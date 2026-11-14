<!-- GENERATED - do not edit. Run: python3 -m lib.readme -->

# GCM155

## Part

- **manufacturer**: Murata
- **description**: Chip multilayer ceramic capacitor, X7R (R7), 1005M (0402), AEC-Q200 reference sheet
- **category**: capacitor_mlcc
- **package**: 1005M (0402)
- **datasheet_url**: 
- **datasheet_rev**: 01A
- **datasheet_date**: 2026-04
- **kicad_symbol**: GCM155.kicad_sym
- **kicad_footprint**: GCM155.kicad_mod
- **step**: GCM155.step

## Variants

Shared data below applies to every variant unless a row names its variants.

| Value | mpn | alternates | temp_grade | datasheet_file | description |
|---|---|---|---|---|---|
| GCM155R71H104KE02 | GCM155R71H104KE02D | GCM155R71H104KE02W, GCM155R71H104KE02J, GCM155R71H104KE02V | -55 to 125 degC | docs/datasheets/GCM155R71H104KE02-01A-EN.pdf | Chip multilayer ceramic capacitor, X7R (R7), 1005M (0402), 0.1 uF, DC 50 V, +/-10 %, AEC-Q200 |

## Pins

| Pin | Name | Type | Function | Cite |
|---|---|---|---|---|
| 1 | 1 | passive | Capacitor terminal (non-polarized) | DS p.2, Type & Dimension, image:Dimension |
| 2 | 2 | passive | Capacitor terminal (non-polarized) | DS p.2, Type & Dimension, image:Dimension |

## Parameters: mechanical

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Land pattern dimension a (reflow) | a | 0.3 |  | 0.5 | mm | Reflow soldering, chip 1.0x0.5 (within +/-0.10), chip code 15 Note: Letter label only in the DS figure; neutral name. Inferred meaning: gap between lands (not printed). | DS p.28, 2. Land Dimensions, Table 2 Reflow Soldering Method, 1.0x0.5 (within +/-0.10), a |
| Land pattern dimension b (reflow) | b | 0.35 |  | 0.45 | mm | Reflow soldering, chip 1.0x0.5 (within +/-0.10), chip code 15 Note: Letter label only in the DS figure; neutral name. Inferred meaning: land length, outer side (not printed). | DS p.28, 2. Land Dimensions, Table 2 Reflow Soldering Method, 1.0x0.5 (within +/-0.10), b |
| Land pattern dimension c (reflow) | c | 0.4 |  | 0.6 | mm | Reflow soldering, chip 1.0x0.5 (within +/-0.10), chip code 15 Note: Letter label only in the DS figure; neutral name. Inferred meaning: land width across the chip (not printed). | DS p.28, 2. Land Dimensions, Table 2 Reflow Soldering Method, 1.0x0.5 (within +/-0.10), c |

## Variant-specific parameters: GCM155R71H104KE02

| Parameter | Symbol | Min | Typ | Max | Unit | Conditions | Cite |
|---|---|---|---|---|---|---|---|
| Rated voltage (DC) |  | -50 (rel. 2) |  | 50 (rel. 2) | V | Voltage between pin 1 and pin 2 (non-polarized; either polarity) Note: DS prints DC 50V with no MIN/MAX label. Stored symmetric (min -50, max 50) because the part is non-polarized: \|V(1)-V(2)\| <= 50 V. Checked by the Zener wrapper against pin 2. | DS p.2, Rated Value, Rated Voltage (DC 50V) |
| Operating temperature range |  | -55 |  | 125 | degC |  | DS p.2, Rated Value, Operating Temp. Range (-55 to 125 degC) |
| Self-heating of the capacitor body (AC or pulse load) |  |  |  | 20 | degC | Measured at 25 degC ambient; rated voltage below 100 VDC | DS p.14, Rating 4. Type of Applied Voltage and Self-heating Temperature |
| AC or pulse voltage: peak-to-peak (and zero-to-peak with DC) within the rated DC voltage |  |  | Vp-p <= rated DC voltage; AC superimposed on DC: zero-to-peak <= rated DC voltage |  |  | AC or pulse voltage applied | DS p.13, Rating 3. Applied Voltage, 1-1 (1) |
| Capacitance | C |  | 0.1 |  | uF | 25 degC, 1.0 +/-0.1 kHz, 1.0 +/-0.2 Vrms (DS p.6, No. 17) | DS p.2, Rated Value, Capacitance (0.1uF) |
| Capacitance tolerance |  | -10 |  | 10 | % | Note: Printed +/-10 % as a limit: min -10, max 10 (SPEC +/-X rule). | DS p.2, Rated Value, Capacitance Tolerance (+/-10 %) |
| Dissipation factor (DF), initial | DF |  |  | 0.1 |  | 25 degC, 1.0 +/-0.1 kHz, 1.0 +/-0.2 Vrms | DS p.6, Specifications and Test Methods, No. 18 Q or Dissipation Factor (DF) |
| Insulation resistance (IR), 25 degC | IR |  | More than 50 ohm*F (printed 'More than 50 Ohm.F'), IR x C |  |  | 25 degC, rated voltage, charging time 1 min, charge/discharge current 50 mA max | DS p.6, Specifications and Test Methods, No. 19 Insulation Resistance (IR), Room Temperature |
| Insulation resistance (IR), 125 degC | IR |  | More than 5 ohm*F (printed 'More than 5 Ohm.F'), IR x C |  |  | 125 degC, rated voltage, charging time 1 min, charge/discharge current 50 mA max | DS p.6, Specifications and Test Methods, No. 20 Insulation Resistance (IR), High Temperature |
| Capacitance change, board flex | dC | -10 |  | 10 | % | Board flex: flexure 2 mm, holding time 60 s, reflow solder on test substrate; after test | DS p.6, Specifications and Test Methods, No. 22 Board Flex, Capacitance Change |
| Capacitance change, high-temperature exposure (storage) | dC | -10 |  | 10 | % | 150 degC, 1000 h, no bias; after 24 h at room temperature | DS p.3, Specifications and Test Methods, No. 3 High Temperature Exposure (Storage), Capacitance Change |
| Dissipation factor, high-temperature exposure | DF |  |  | 0.2 |  | 150 degC, 1000 h, no bias; after 24 h at room temperature | DS p.3, Specifications and Test Methods, No. 3 High Temperature Exposure (Storage), Q or D.F. |
| Insulation resistance, high-temperature exposure | IR |  | More than 50 ohm*F (printed 'More than 50 Ohm.F'), IR x C |  |  | Room temperature, after 150 degC, 1000 h exposure | DS p.3, Specifications and Test Methods, No. 3 High Temperature Exposure (Storage), I.R. (Room Temp.) |
| Capacitance change, temperature cycling | dC | -7.5 |  | 7.5 | % | 1000 cycles, min operating temp to max operating temp (30 min dwell each); after room-temperature sit Note: DS prints Q/DF and IR as 'within the specified initial value' (no number), so only the capacitance limit is stored. | DS p.3, Specifications and Test Methods, No. 4 Temperature Cycling, Capacitance Change |
| Capacitance change, moisture resistance | dC | -10 |  | 10 | % | +25 degC to +65 degC, 80 to 98 %RH, 10 cycles of the 24 h profile | DS p.4, Specifications and Test Methods, No. 6 Moisture Resistance, Capacitance Change |
| Dissipation factor, moisture resistance | DF |  |  | 0.2 |  | +25 degC to +65 degC, 80 to 98 %RH, 10 cycles of the 24 h profile | DS p.4, Specifications and Test Methods, No. 6 Moisture Resistance, Q or D.F. |
| Insulation resistance, moisture resistance | IR |  | More than 25 ohm*F (printed 'More than 25 Ohm.F'), IR x C |  |  | Room temperature, after the moisture test | DS p.4, Specifications and Test Methods, No. 6 Moisture Resistance, I.R. (Room Temp.) |
| Capacitance change, humidity bias | dC | -12.5 |  | 12.5 | % | 85 degC, 80 to 85 %RH, 1000 h; test voltage: rated voltage and 1.3 +0.2/-0 V DC (6.8 kohm series, as printed) | DS p.4, Specifications and Test Methods, No. 7 Humidity Bias, Capacitance Change |
| Dissipation factor, humidity bias | DF |  |  | 0.2 |  | 85 degC, 80 to 85 %RH, 1000 h | DS p.4, Specifications and Test Methods, No. 7 Humidity Bias, Q or D.F. |
| Insulation resistance, humidity bias | IR |  | More than 12.5 ohm*F (printed 'More than 12.5 Ohm.F'), IR x C |  |  | Room temperature, after the humidity bias test | DS p.4, Specifications and Test Methods, No. 7 Humidity Bias, I.R. (Room Temp.) |
| Capacitance change, high-temperature operating life | dC | -12.5 |  | 12.5 | % | Max operating temp +/-3 degC (125 degC), 1000 h, 150 % of rated voltage | DS p.4, Specifications and Test Methods, No. 8 High Temperature Operating Life, Capacitance Change |
| Dissipation factor, high-temperature operating life | DF |  |  | 0.2 |  | Max operating temp +/-3 degC, 1000 h, 150 % of rated voltage | DS p.4, Specifications and Test Methods, No. 8 High Temperature Operating Life, Q or D.F. |
| Insulation resistance, high-temperature operating life | IR |  | More than 25 ohm*F (printed 'More than 25 Ohm.F'), IR x C |  |  | Room temperature, after the high-temperature operating life test | DS p.4, Specifications and Test Methods, No. 8 High Temperature Operating Life, I.R. (Room Temp.) |
| Temperature characteristic, R7 (X7R) | TC | -15 |  | 15 | % | Ref. temp 25 degC; temp range -55 to 125 degC; capacitance change over temperature Note: Public STD code X7R (EIA). Capacitance change over temperature, not a DC-bias or aging limit (see the open items above). | DS p.2, Rated Value, Temp. coeff. or Cap. Change (-15 to 15 %) |
| Capacitance change with DC bias |  |  | Not specified: the sheet shows only an example curve |  |  | DC voltage applied Note: X7R loses capacitance under DC bias; the DS example curve (sample R(R1), 0.1 uF, 50 VDC: a different temperature-characteristic code from this R7 part) shows a large loss approaching rated voltage; it is an example, not a rating for this part. capacitance_worst excludes it: do not use capacitance_worst as an in-circuit minimum. The DS also requires the AC/pulse zero-to-peak voltage to stay within the rated DC voltage; the Zener check is DC steady state only. | DS p.14, Rating 5. DC Voltage and AC Voltage Characteristic (example figure) |
| Thickness (T) | T | 0.45 | 0.5 | 0.55 | mm | Note: min and max are the printed nominal 0.5 -/+ 0.05 (arithmetic). | DS p.2, Type & Dimension, T (0.5+/-0.05) |
| Terminal width (e) | e | 0.15 |  | 0.35 | mm |  | DS p.2, Type & Dimension, e (0.15 to 0.35) |
| Gap between terminals (g) | g | 0.3 |  |  | mm | Note: Printed as a minimum only; no max stored. | DS p.2, Type & Dimension, g (0.3 min.) |
| Beam load test, destruction value |  |  | More than 8 N (destruction value) |  |  | Speed 0.5 mm/s; chip length 2.5 mm max. | DS p.6, Specifications and Test Methods, No. 24 Beam Load Test |
| Length (L) | L | 0.95 | 1.0 | 1.05 | mm | Note: min and max are the printed nominal 1.0 -/+ 0.05 (arithmetic); the DS prints 1.0+/-0.05. | DS p.2, Type & Dimension, L (1.0+/-0.05) |
| Width (W) | W | 0.45 | 0.5 | 0.55 | mm | Note: min and max are the printed nominal 0.5 -/+ 0.05 (arithmetic); the DS prints 0.5+/-0.05. | DS p.2, Type & Dimension, W (0.5+/-0.05) |
| Solderability: terminations soldered evenly and continuously |  | 95 |  |  | % | Specifications and Test Methods No.16 (a) test conditions Note: Assembly acceptance criterion, not a circuit limit. | DS p.5, Specifications and Test Methods, No.16 Solderability (a) |

## Limits of this data

Rows by scope: 25C 3, full 1, na 31 (25C rows hold only at 25 degC). Curve (graph) rows: 0. Text rows: 9.

## Zener checks

No Zener checks declared.

### Zener checks: variant GCM155R71H104KE02

Generated wrapper: `GCM155R71H104KE02.zen` (`python3 -m lib.zen`). abs_max and rec_op rows are errors (abs_max x derate); 25C and partial rows are waivable warnings; a checked net with no voltage is UNVERIFIED.

| Param | Name | Checked against | Not checked / reason |
|---|---|---|---|
| rated_v | Rated voltage (DC) | pins 1 |  |
| op_temp | Operating temperature range | board ambient |  |
| self_heating | Self-heating of the capacitor body (AC or pulse load) | UNCHECKED | depends on AC/pulse current, not a DC net voltage; owner: module |
| ac_peak | AC or pulse voltage: peak-to-peak (and zero-to-peak with DC) within the rated DC voltage | UNCHECKED | AC/pulse waveform is not modelled by the DC net-voltage check; owner: module |

## Equations

### `capacitance_worst`

```
Not a DS equation: C = C0 * (1 + tol) * (1 + tc). Combines capacitance tolerance (DS p.2, Rated Value,
Capacitance Tolerance +/-10 %) and the temperature characteristic capacitance change (DS p.2, Rated Value,
Temp. coeff. or Cap. Change -15 to 15 % over -55 to 125 degC, ref 25 degC). EXCLUDES DC-bias and aging capacitance
loss, which the reference sheet does not quantify (DS p.14 section 5 figure; DS p.15 section 6 figure). For X7R
these can dominate. This is a worst-case stack of two printed rows, not a guaranteed capacitance.
c0: nominal capacitance, F (DS p.2, 0.1 uF). tol: capacitance tolerance, fraction (DS p.2, +/-10 %).
tc: temperature characteristic capacitance change, fraction (DS p.2, -15 to 15 %). Returns: C, F.
```

Inputs:

- `c0` -> `capacitance.typ` (typ 0.1 uF)
- `tol` -> `tolerance` (min -10 max 10 %)
- `tc` -> `tc_r7` (min -15 max 15 %)


## Examples

| Call | Computed | Expected | Rel. tol | Result | Cite |
|---|---|---|---|---|---|
| capacitance_worst(c0=1e-07, tol=-0.1, tc=-0.15) | 7.65e-08 | 7.65e-08 | 1e-09 | pass | DS p.2, Rated Value |
