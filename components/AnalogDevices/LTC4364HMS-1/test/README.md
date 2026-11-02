# LTC4364HMS-1 check tests

Run `test/matrix.sh [pcb version]`. Method and case types: `docs/TESTING.md`.
The matrix has 127 cases (package_root, 125 listed below, waiver_on_error); `matrix.sh` prints the count.

Harness defaults (nominal): VCC, OUT, SENSE, SHDN, ENOUT = 12 V 5%; UV = 2 V 5%; OV = 1 V 5%; FB = 1 V 5%; FLT =
3.3 V 5%; GND = Ground; ambient -40 °C to 85 °C; derate 1.0. DGATE, SOURCE, HGATE, TMR are named nets with no voltage
(UNCHECKED in the component). The waiver mechanism is not used by this component (no waivable checks), so there are no
waiver cases. Every voltage config accepts `unset`. Ranges are written `lo to hi` so tol_* stays quiet.

Messages come from `_rel`: `<v.min - ref.max> to <v.max - ref.min> V outside <lim.min*k if negative> to <lim.max*k if
positive> V (derate k)`, rounded to 3 decimals. Each pin uses different numbers so the expected text identifies the
check. Cases that are not isolated say so in the last column.

Limits that cannot be reached alone:
- abs_VCC (-40 to 100 V) lies outside op_VCC (4 to 80 V). At derate 1 no value passes abs_VCC and fails nothing
  else, so its two outside cases also fire op_VCC and there is no pass-at-boundary case. At derate 0.5 the upper limit
  is 50 V, inside op_VCC, so `abs_VCC_dr_*` isolate it. The lower limit (-40 V * k) is never inside op_VCC (4 V):
  only the non-isolated outside case exists.
- abs_OUT_VCC upper edge (OUT.max - VCC.min = 100 V) needs VCC.min <= 0 (op_VCC fires) or OUT.max >= 104 V (abs_OUT
  fires), so it cannot pass at the boundary; `pair_OV_hi_out` also fires op_VCC. The lower edge (OUT.min - VCC.max =
  -100 V) is reachable exactly at OUT -20 V and VCC 80 V (`pair_OV_lo_bound`); `pair_OV_lo_out` also fires op_VCC, and
  derate 0.5 (limit +-50 V) isolates it (`pair_OV_dr_lo_*`).
- The ENOUT/FLT limit is 80 V, the lower of DS p.2 (100 V) and DS p.9 (80 V).

| Case | Overrides | Expect | Proves |
|---|---|---|---|
| package_root | `pcb build ..` | pass | Package alone is green; UNVERIFIED is advice with no nets attached |
| nominal | none | pass | Defaults are a clean passing design |
| tol_VCC | `vcc=12V` | warning | tol_VCC warns on a point value |
| tol_OUT | `vout=12V` | warning | tol_OUT warns on a point value |
| tol_SENSE | `vsense=12V` | warning | tol_SENSE warns on a point value |
| tol_OV | `vov=1V` | warning | tol_OV warns on a point value |
| tol_UV | `vuv=2V` | warning | tol_UV warns on a point value |
| tol_SHDN | `vshdn=12V` | warning | tol_SHDN warns on a point value |
| tol_FB | `vfb=1V` | warning | tol_FB warns on a point value |
| tol_ENOUT | `venout=12V` | warning | tol_ENOUT warns on a point value |
| tol_FLT | `vflt=3V` | warning | tol_FLT warns on a point value |
| zero_ok_OV | `vov=0V` | pass | Exactly 0 V (tied to GND) is exempt from the tolerance check |
| zero_ok_FB | `vfb=0V` | pass | Exactly 0 V (tied to GND) is exempt from the tolerance check |
| zero_ok_ENOUT | `venout=0V` | pass | Exactly 0 V (tied to GND) is exempt from the tolerance check |
| zero_ok_FLT | `vflt=0V` | pass | Exactly 0 V (tied to GND) is exempt from the tolerance check |
| op_VCC_lo_bound | `vcc=4V to 5V` | pass | op_VCC passes at the edge |
| op_VCC_lo_out | `vcc=3.9V to 5V` | error | op_VCC fails past the edge: 3.9 to 5.0 V outside 4.0 to 80.0 V (derate 1.0); abs_VCC and abs_OUT_VCC stay quiet |
| op_VCC_hi_bound | `vcc=79V to 80V` | pass | op_VCC passes at the edge |
| op_VCC_hi_out | `vcc=79V to 80.1V` | error | op_VCC fails past the edge: 79.0 to 80.1 V outside 4.0 to 80.0 V (derate 1.0); abs_VCC and abs_OUT_VCC stay quiet |
| abs_VCC_hi_out | `vcc=99V to 100.1V` | error | abs_VCC fails just past the upper limit; op_VCC also fires (abs_VCC is outside op_VCC, no isolated case at derate 1) |
| abs_VCC_lo_out | `vcc=-40.1V to -39V` | error | abs_VCC fails just past the lower limit; op_VCC also fires (abs_VCC is outside op_VCC, no isolated case at derate 1) |
| abs_VCC_dr_bound | `vcc=49V to 50V, derate=0.5` | pass | abs_VCC passes exactly at the upper limit at derate 0.5 |
| abs_VCC_dr_out | `vcc=49V to 50.1V, derate=0.5` | error | abs_VCC fails just past the upper limit at derate 0.5 |
| abs_OV_hi_bound | `vov=98V to 100V` | pass | abs_OV passes exactly at the upper limit |
| abs_OV_hi_out | `vov=98V to 100.1V` | error | abs_OV fails just past the upper limit |
| abs_OV_lo_bound | `vov=-40V to -38V` | pass | abs_OV passes exactly at the lower limit |
| abs_OV_lo_out | `vov=-40.1V to -38V` | error | abs_OV fails just past the lower limit |
| abs_OV_dr_bound | `vov=49V to 50V, derate=0.5` | pass | abs_OV passes exactly at the upper limit at derate 0.5 |
| abs_OV_dr_out | `vov=49.5V to 50.1V, derate=0.5` | error | abs_OV fails just past the upper limit at derate 0.5 |
| abs_UV_hi_bound | `vuv=97V to 100V` | pass | abs_UV passes exactly at the upper limit |
| abs_UV_hi_out | `vuv=97V to 100.2V` | error | abs_UV fails just past the upper limit |
| abs_UV_lo_bound | `vuv=-40V to -37V` | pass | abs_UV passes exactly at the lower limit |
| abs_UV_lo_out | `vuv=-40.2V to -37V` | error | abs_UV fails just past the lower limit |
| abs_SHDN_hi_bound | `vshdn=96V to 100V` | pass | abs_SHDN passes exactly at the upper limit |
| abs_SHDN_hi_out | `vshdn=96V to 100.3V` | error | abs_SHDN fails just past the upper limit |
| abs_SHDN_lo_bound | `vshdn=-40V to -36V` | pass | abs_SHDN passes exactly at the lower limit |
| abs_SHDN_lo_out | `vshdn=-40.3V to -36V` | error | abs_SHDN fails just past the lower limit |
| abs_SHDN_dr_lo_bound | `vshdn=-20V to -18V, derate=0.5` | pass | abs_SHDN passes exactly at the lower limit at derate 0.5 |
| abs_SHDN_dr_lo_out | `vshdn=-20.3V to -18V, derate=0.5` | error | abs_SHDN fails just past the lower limit at derate 0.5 |
| abs_OV_dr_lo_bound | `vov=-20V to -19V, derate=0.5` | pass | abs_OV passes exactly at the lower limit at derate 0.5 |
| abs_OV_dr_lo_out | `vov=-20.4V to -19V, derate=0.5` | error | abs_OV fails just past the lower limit at derate 0.5 |
| abs_UV_dr_hi_bound | `vuv=47V to 50V, derate=0.5` | pass | abs_UV passes exactly at the upper limit at derate 0.5 |
| abs_UV_dr_hi_out | `vuv=47V to 50.3V, derate=0.5` | error | abs_UV fails just past the upper limit at derate 0.5 |
| abs_UV_dr_lo_bound | `vuv=-20V to -17V, derate=0.5` | pass | abs_UV passes exactly at the lower limit at derate 0.5 |
| abs_UV_dr_lo_out | `vuv=-20.5V to -17V, derate=0.5` | error | abs_UV fails just past the lower limit at derate 0.5 |
| abs_SHDN_dr_hi_bound | `vshdn=48V to 50V, derate=0.5` | pass | abs_SHDN passes exactly at the upper limit at derate 0.5 |
| abs_SHDN_dr_hi_out | `vshdn=48V to 50.2V, derate=0.5` | error | abs_SHDN fails just past the upper limit at derate 0.5 |
| abs_OUT_hi_bound | `vout=99V to 100V, vsense=99V to 100V` | pass | abs_OUT passes exactly at the upper limit |
| abs_OUT_hi_out | `vout=99V to 100.1V, vsense=99V to 100V` | error | abs_OUT fails just past the upper limit |
| abs_OUT_lo_bound | `vout=-20V to -19V, vsense=-20V to -19V` | pass | abs_OUT passes exactly at the lower limit |
| abs_OUT_lo_out | `vout=-20.1V to -19V, vsense=-20V to -19V` | error | abs_OUT fails just past the lower limit |
| abs_OUT_dr_hi_bound | `vout=49V to 50V, vsense=49V to 50V, derate=0.5` | pass | abs_OUT passes exactly at the upper limit at derate 0.5 |
| abs_OUT_dr_hi_out | `vout=49V to 50.3V, vsense=49V to 50V, derate=0.5` | error | abs_OUT fails just past the upper limit at derate 0.5 |
| abs_OUT_dr_lo_bound | `vout=-10V to -8V, vsense=-10V to -8V, derate=0.5` | pass | abs_OUT passes exactly at the lower limit at derate 0.5 |
| abs_OUT_dr_lo_out | `vout=-10.4V to -8V, vsense=-10V to -8V, derate=0.5` | error | abs_OUT fails just past the lower limit at derate 0.5 |
| abs_SENSE_hi_bound | `vsense=98V to 100V, vout=98V to 100V` | pass | abs_SENSE passes exactly at the upper limit |
| abs_SENSE_hi_out | `vsense=98V to 100.2V, vout=98V to 100V` | error | abs_SENSE fails just past the upper limit |
| abs_SENSE_lo_bound | `vsense=-20V to -18V, vout=-20V to -18V` | pass | abs_SENSE passes exactly at the lower limit |
| abs_SENSE_lo_out | `vsense=-20.2V to -18V, vout=-20V to -18V` | error | abs_SENSE fails just past the lower limit |
| abs_SENSE_dr_out | `vsense=48V to 50.4V, vout=48V to 50V, derate=0.5` | error | abs_SENSE fails just past the upper limit at derate 0.5 |
| abs_FB_hi_bound | `vfb=5.4V to 5.5V` | pass | abs_FB passes exactly at the upper limit |
| abs_FB_hi_out | `vfb=5.4V to 5.6V` | error | abs_FB fails just past the upper limit |
| abs_FB_lo_bound | `vfb=-0.3V to -0.2V` | pass | abs_FB passes exactly at the lower limit |
| abs_FB_lo_out | `vfb=-0.4V to -0.2V` | error | abs_FB fails just past the lower limit |
| abs_FB_dr_bound | `vfb=2.7V to 2.75V, derate=0.5` | pass | abs_FB passes exactly at the upper limit at derate 0.5 |
| abs_FB_dr_out | `vfb=2.7V to 2.8V, derate=0.5` | error | abs_FB fails just past the upper limit at derate 0.5 |
| abs_ENOUT_hi_bound | `venout=78V to 80V` | pass | abs_ENOUT passes exactly at the upper limit |
| abs_ENOUT_hi_out | `venout=78V to 80.1V` | error | abs_ENOUT fails just past the upper limit |
| abs_ENOUT_lo_bound | `venout=-0.3V to -0.1V` | pass | abs_ENOUT passes exactly at the lower limit |
| abs_ENOUT_lo_out | `venout=-0.4V to -0.1V` | error | abs_ENOUT fails just past the lower limit |
| abs_FLT_hi_bound | `vflt=77V to 80V` | pass | abs_FLT passes exactly at the upper limit |
| abs_FLT_hi_out | `vflt=77V to 80.2V` | error | abs_FLT fails just past the upper limit |
| abs_FLT_lo_bound | `vflt=-0.3V to 0.1V` | pass | abs_FLT passes exactly at the lower limit |
| abs_FLT_lo_out | `vflt=-0.5V to 0.1V` | error | abs_FLT fails just past the lower limit |
| abs_FB_dr_lo_bound | `vfb=-0.15V to -0.1V, derate=0.5` | pass | abs_FB passes exactly at the lower limit at derate 0.5 |
| abs_FB_dr_lo_out | `vfb=-0.25V to -0.1V, derate=0.5` | error | abs_FB fails just past the lower limit at derate 0.5 |
| abs_ENOUT_dr_hi_bound | `venout=38V to 40V, derate=0.5` | pass | abs_ENOUT passes exactly at the upper limit at derate 0.5 |
| abs_ENOUT_dr_hi_out | `venout=38V to 40.1V, derate=0.5` | error | abs_ENOUT fails just past the upper limit at derate 0.5 |
| abs_ENOUT_dr_lo_bound | `venout=-0.15V to 0.1V, derate=0.5` | pass | abs_ENOUT passes exactly at the lower limit at derate 0.5 |
| abs_ENOUT_dr_lo_out | `venout=-0.2V to 0.1V, derate=0.5` | error | abs_ENOUT fails just past the lower limit at derate 0.5 |
| abs_FLT_dr_hi_bound | `vflt=37V to 40V, derate=0.5` | pass | abs_FLT passes exactly at the upper limit at derate 0.5 |
| abs_FLT_dr_hi_out | `vflt=37V to 40.2V, derate=0.5` | error | abs_FLT fails just past the upper limit at derate 0.5 |
| abs_FLT_dr_lo_bound | `vflt=-0.15V to 0.2V, derate=0.5` | pass | abs_FLT passes exactly at the lower limit at derate 0.5 |
| abs_FLT_dr_lo_out | `vflt=-0.3V to 0.2V, derate=0.5` | error | abs_FLT fails just past the lower limit at derate 0.5 |
| pair_SO_hi_bound | `vsense=39V to 40V, vout=10V to 11V` | pass | abs_SENSE_OUT passes exactly at the upper limit |
| pair_SO_hi_out | `vsense=39V to 40.1V, vout=10V to 11V` | error | abs_SENSE_OUT fails just past the upper limit |
| pair_SO_lo_bound | `vsense=10V to 11V, vout=39V to 40V` | pass | abs_SENSE_OUT passes exactly at the lower limit |
| pair_SO_lo_out | `vsense=9.9V to 11V, vout=39V to 40V` | error | abs_SENSE_OUT fails just past the lower limit |
| pair_SO_dr_hi_bound | `vsense=24V to 25V, vout=10V to 11V, derate=0.5` | pass | abs_SENSE_OUT passes exactly at the upper limit at derate 0.5 |
| pair_SO_dr_hi_out | `vsense=24V to 25.2V, vout=10V to 11V, derate=0.5` | error | abs_SENSE_OUT fails just past the upper limit at derate 0.5 |
| pair_SO_dr_lo_bound | `vsense=10V to 11V, vout=24V to 25V, derate=0.5` | pass | abs_SENSE_OUT passes exactly at the lower limit at derate 0.5 |
| pair_SO_dr_lo_out | `vsense=9.8V to 11V, vout=24V to 25V, derate=0.5` | error | abs_SENSE_OUT fails just past the lower limit at derate 0.5 |
| pair_OV_lo_bound | `vout=-20V to -19V, vsense=-20V to -19V, vcc=79V to 80V` | pass | abs_OUT_VCC passes exactly at the lower limit |
| pair_OV_lo_out | `vout=-20V to -19V, vsense=-20V to -19V, vcc=79V to 80.1V` | error | abs_OUT_VCC fails just past the lower limit; op_VCC also fires |
| pair_OV_hi_out | `vout=99V to 100V, vsense=99V to 100V, vcc=-0.1V to 1V` | error | abs_OUT_VCC fails just past the upper limit; op_VCC also fires |
| pair_OV_dr_lo_bound | `vout=-10V to -9V, vsense=-10V to -9V, vcc=39V to 40V, derate=0.5` | pass | abs_OUT_VCC passes exactly at the lower limit at derate 0.5 |
| pair_OV_dr_lo_out | `vout=-10V to -9V, vsense=-10V to -9V, vcc=39V to 40.1V, derate=0.5` | error | abs_OUT_VCC fails just past the lower limit at derate 0.5 |
| ta_bound | `ta=-40°C to 125°C` | pass | temp_grade passes at the grade edges |
| ta_lo_out | `ta=-41°C to 125°C` | error | temp_grade fails outside -40 to 125 C |
| ta_hi_out | `ta=-40°C to 126°C` | error | temp_grade fails outside -40 to 125 C |
| unset_vcc_tol | `vcc=unset` | warning | UNVERIFIED tol_VCC (never a silent pass) |
| unset_vcc_abs | `vcc=unset` | warning | UNVERIFIED abs_VCC (never a silent pass) |
| unset_vcc_op | `vcc=unset` | warning | UNVERIFIED op_VCC (never a silent pass) |
| unset_vcc_pair | `vcc=unset` | warning | UNVERIFIED abs_OUT_VCC (never a silent pass) |
| unset_vout_tol | `vout=unset` | warning | UNVERIFIED tol_OUT (never a silent pass) |
| unset_vout_abs | `vout=unset` | warning | UNVERIFIED abs_OUT (never a silent pass) |
| unset_vout_pairSO | `vout=unset` | warning | UNVERIFIED abs_SENSE_OUT (never a silent pass) |
| unset_vout_pairOV | `vout=unset` | warning | UNVERIFIED abs_OUT_VCC (never a silent pass) |
| unset_vsense_tol | `vsense=unset` | warning | UNVERIFIED tol_SENSE (never a silent pass) |
| unset_vsense_abs | `vsense=unset` | warning | UNVERIFIED abs_SENSE (never a silent pass) |
| unset_vsense_pair | `vsense=unset` | warning | UNVERIFIED abs_SENSE_OUT (never a silent pass) |
| unset_vov_tol | `vov=unset` | warning | UNVERIFIED tol_OV (never a silent pass) |
| unset_vov_abs | `vov=unset` | warning | UNVERIFIED abs_OV (never a silent pass) |
| unset_vuv_tol | `vuv=unset` | warning | UNVERIFIED tol_UV (never a silent pass) |
| unset_vuv_abs | `vuv=unset` | warning | UNVERIFIED abs_UV (never a silent pass) |
| unset_vshdn_tol | `vshdn=unset` | warning | UNVERIFIED tol_SHDN (never a silent pass) |
| unset_vshdn_abs | `vshdn=unset` | warning | UNVERIFIED abs_SHDN (never a silent pass) |
| unset_vfb_tol | `vfb=unset` | warning | UNVERIFIED tol_FB (never a silent pass) |
| unset_vfb_abs | `vfb=unset` | warning | UNVERIFIED abs_FB (never a silent pass) |
| unset_venout_tol | `venout=unset` | warning | UNVERIFIED tol_ENOUT (never a silent pass) |
| unset_venout_abs | `venout=unset` | warning | UNVERIFIED abs_ENOUT (never a silent pass) |
| unset_vflt_tol | `vflt=unset` | warning | UNVERIFIED tol_FLT (never a silent pass) |
| unset_vflt_abs | `vflt=unset` | warning | UNVERIFIED abs_FLT (never a silent pass) |
| unset_ta | `ta=unset` | warning | UNVERIFIED temp_grade (never a silent pass) |
| derate_gt1 | `derate=1.5` | error | Config guard rejects derate outside (0, 1] |
| derate_zero | `derate=0` | error | Config guard rejects derate outside (0, 1] |
| waiver_on_error | temp_grade patched to pass a waiver | error | `_limit()` refuses a waiver on an error-level check (no config reaches this path) |
