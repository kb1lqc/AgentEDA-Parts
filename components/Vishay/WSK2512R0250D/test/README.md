# WSK2512R0250D check tests

Run `test/matrix.sh [pcb version]`. Method and case types: `docs/TESTING.md`.

Harness defaults (nominal): ambient -40 °C to 85 °C, derate 1.0, I1/I2/E1/E2 on named nets with no voltage. The only
electrical check is `temp_grade` (ambient within -65 °C to 170 °C, DS p.2). No check reads a net voltage, so there are
no tolerance or unset-net cases; power, current and working voltage are the module's (UNCHECKED, `wsk2512_limits.zen`).

| Case | Overrides | Expect | Proves |
|---|---|---|---|
| package_root | `pcb build ..` | pass | Package alone is green; UNVERIFIED is advice with no nets attached |
| nominal | none | pass | Defaults are a clean passing design |
| ta_lo_bound | ambient -65 °C to 85 °C | pass | temp_grade passes at the -65 °C limit |
| ta_hi_bound | ambient -40 °C to 170 °C | pass | temp_grade passes at the 170 °C limit (0 W rated there: module's check) |
| ta_lo_out | ambient -66 °C to 85 °C | error | temp_grade fails 1 °C below -65 °C; only temp_grade fires |
| ta_hi_out | ambient -40 °C to 171 °C | error | temp_grade fails 1 °C above 170 °C; only temp_grade fires |
| unset_ta | ambient unset | warning | Missing ambient reports UNVERIFIED temp_grade, never a silent pass |
| derate_ok | derate 0.5 | pass | derate is accepted (modules pass it down); nothing here is derated |
| derate_gt1 | derate 1.5 | error | derate > 1 is rejected |
| derate_gt1_edge | derate 1.01 | error | derate just above 1 is rejected (1.0 itself is the nominal case) |
| derate_zero | derate 0 | error | derate 0 is rejected |
| waiver_on_error | mutation: waiver added to temp_grade | error | `_limit()` refuses to waive an error-level check |
