# INA821IDGK check tests

Run `test/matrix.sh [pcb version]`. Method and case types: `docs/TESTING.md`.

Harness defaults (nominal): V+ = 15 V 5%, V- = -15 V 5%, IN_P = 1 V 1%, IN_N = 0 V, REF = 0 V, ambient -40 °C to
85 °C, derate 1.0, no waivers. Worst-case rails: V+ min 14.25 V, V- max -14.25 V, span 28.5 V to 31.5 V.

| Case | Overrides | Expect | Proves |
|---|---|---|---|
| package_root | `pcb build ..` | pass | Package alone is green; UNVERIFIED is advice with no nets attached |
| nominal | none | pass | Defaults are a clean passing design |
| span_derate_bound | V+ 15.5-16 V, V- -16 to -15.5 V, derate 0.8 | pass | abs_span passes at its derated 32 V limit |
| span_derate_out | V+ 15.6-16.1 V, same V-, derate 0.8 | error | abs_span fails at 32.1 V; derate is applied; op_span (36 V) stays quiet |
| span_abs_out | V+ 20-20.1 V, V- -20 to -19.9 V | error | abs_span fails above 40 V (op_span also fires) |
| span_reversed | V+ -15 V 5%, V- 15 V 5% | error | abs_span lower bound: V+ below V- fails |
| op_lo_bound | V+ 4.5-4.6 V, V- GND, IN/REF 2.2 V 1% | pass | op_span passes at 4.5 V; also a single-supply case |
| op_lo_out | V+ 4.4-4.6 V, as above | error | op_span fails below 4.5 V |
| op_hi_bound | V+ 17.5-18 V, V- -18 to -17.5 V | pass | op_span passes at 36 V |
| op_hi_out | V+ 17.5-18.1 V, same V- | error | op_span fails at 36.1 V |
| absin_hi_bound | IN_P 39-40 V, waive_vcm | pass | abs_IN_P passes at +40 V (vcm waived to isolate) |
| absin_hi_out | IN_P 39-40.1 V, waive_vcm | error | abs_IN_P fails above +40 V |
| absin_lo_bound | IN_N -40 to -39 V, waive_vcm | pass | abs_IN_N passes at -40 V |
| absin_lo_out | IN_N -40.1 to -39 V, waive_vcm | error | abs_IN_N fails below -40 V |
| absin_derate_out | IN_P 20-21 V, derate 0.5, waive_vcm | error | derate shrinks the ±40 V limit to ±20 V |
| absref_hi_bound | REF 19-20 V, waive_ref | pass | abs_REF passes at +20 V (ref_range waived to isolate) |
| absref_hi_out | REF 19-20.1 V, waive_ref | error | abs_REF fails above +20 V |
| absref_lo_bound | REF -20 to -19 V, waive_ref | pass | abs_REF passes at -20 V |
| absref_lo_out | REF -20.1 to -19 V, waive_ref | error | abs_REF fails below -20 V |
| vcm_hi_bound | IN_P 12-12.25 V | pass | vcm_IN_P passes at (V+)min - 2 V = 12.25 V |
| vcm_hi_out | IN_P 12-12.3 V | warning | vcm_IN_P fails above the window, at warning severity |
| vcm_hi_waived | IN_P 12-12.3 V, waive_vcm | pass | The waiver drops vcm to advice |
| vcm_lo_bound | IN_N -12.25 to -12 V | pass | vcm_IN_N passes at (V-)max + 2 V = -12.25 V |
| vcm_lo_out | IN_N -12.3 to -12 V | warning | vcm_IN_N fails below the window |
| ref_hi_bound | REF 14-14.25 V | pass | ref_range passes at (V+)min = 14.25 V |
| ref_hi_out | REF 14-14.3 V | warning | ref_range fails above V+, at warning severity |
| ref_hi_waived | REF 14-14.3 V, waive_ref | pass | The waiver drops ref_range to advice |
| ref_lo_bound | REF -14.25 to -14 V | pass | ref_range passes at (V-)max = -14.25 V |
| ref_lo_out | REF -14.3 to -14 V | warning | ref_range fails below V- |
| ta_bound | ambient -40 °C to 125 °C | pass | temp_grade passes at the full grade range |
| ta_lo_out | ambient -41 °C to 125 °C | error | temp_grade fails below -40 °C |
| ta_hi_out | ambient -40 °C to 126 °C | error | temp_grade fails above 125 °C |
| tol_vp | V+ 15 V exactly | warning | vpos_tol: a rail with no tolerance warns |
| tol_vn | V- -15 V exactly | warning | vneg_tol |
| tol_inp | IN_P 1 V exactly | warning | tol_IN_P (IN_N uses the same loop) |
| tol_ref | REF 1 V exactly | warning | tol_REF |
| gnd_rail_ok | V- GND, IN/REF 3 V 1% | pass | A 0 V Ground rail is exempt from the tolerance check; V- as Ground works through the cast |
| unset_vp | V+ unset | warning | UNVERIFIED on vpos_tol and every check that uses V+ |
| unset_vn | V- unset | warning | UNVERIFIED on vneg_tol and every check that uses V- |
| unset_in | IN_P, IN_N unset | warning | UNVERIFIED on tol, abs and vcm for both inputs |
| unset_ref | REF unset | warning | UNVERIFIED on tol_REF, abs_REF, ref_range |
| ta_unset | ambient unset | warning | UNVERIFIED temp_grade |
| derate_gt1 | derate 1.5 | error | derate > 1 is rejected (it would loosen abs max) |
| derate_zero | derate 0 | error | derate must be > 0 |
| waiver_on_error | temp copy, waiver added to temp_grade | error | `_limit()` refuses to waive an error-level check (mutation test) |

Not tested, by design: the implicit `io(Power(voltage=))` range (CLAUDE.md). Rows marked `UNCHECKED` in
`INA821IDGK.zen` have no check, so they have no case.
