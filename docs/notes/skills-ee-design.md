# Rationale and worked detail from the ee-design skill (humans only)

- Self-heating: x = theta x P(T_ambient + x), iterated to a stated residual, with P at the worst-case parameter for that temperature; evaluate the self-heating part's temperature-dependent parameters at its element or junction temperature, other parts at their own temperature (ambient or their own junction). Examples of such parts: shunt TCR, MOSFET Rds(on), regulator dropout, LED forward voltage.
- BOL example: on low-value parts the fixed term dominates (0.5 mohm is 5 % of a 10 mohm shunt). Learned on a shunt current-sense block.
- Calibration model: a gain calibration is a ratio, k = I_ref(1 + e_ref) / reading_cal, error = k x reading_op / I_true - 1. It removes fixed gain terms (tolerance, assembly shift, gain error, register rounding). What remains: temperature coefficients between operating and calibration temperature (including the element's self-heated temperature at the calibration point), drift relative to the calibration ambient, reference accuracy, offset away from the calibration point, quantisation. The calibration becomes a production requirement (operating point, ambient, reference accuracy).
- Narrowing the operating range example: capping a bus voltage so an abs-max is never exceeded rather than adding a TVS.
- Return-node example: gate-to-GND vs gate-to-source differ by the full bus voltage.
- R_out estimate example: (VS - VOH)/IOH is a bound, not a value; label it as not a datasheet equation. Logic example: VIO max = VS + 0.3 V.
- Capping the Zener-side check: Zener abs_max checks already fail on DC violations (library wrapper `check_pins`); the skill keeps only "call out transients".
- Open item: the earlier skill cited "TPS4800-Q1 8.2.2" as the design-example reference; the repo's part is TPS48000(-Q1). Likely a typo; verify against the datasheet.
- Conflict resolved: ee-design "stop and ask" applies to circuit design; library-part tasks use the library's defaults table.
