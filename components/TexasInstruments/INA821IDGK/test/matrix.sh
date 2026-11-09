#!/usr/bin/env bash
# Self-checking test matrix for INA821IDGK. Method: docs/TESTING.md. Case list: test/README.md.
# Usage: test/matrix.sh [pcb version, e.g. 0.4.95]   (from any directory; default = current toolchain)
# Each case builds harness.zen with --config overrides, then compares the outcome with the expectation:
#   pass    = build exits 0 under -Wstyle -Dwarnings
#   error   = build fails with an Error diagnostic
#   warning = build fails with Warning diagnostics only (-Dwarnings promotes them)
# and requires the given text in the output. Exit 1 if any case differs.
set -u
cd "$(dirname "$0")" || exit 2
PCB=(pcb)
[ $# -ge 1 ] && PCB=(pcb "+$1")
echo "toolchain: $("${PCB[@]}" --version)"
n=0
bad=0

classify() { # $1 = exit code, $2 = output
    if [ "$1" -eq 0 ]; then
        echo pass
    elif printf '%s\n' "$2" | grep -v 'Build failed' | grep -q '^Error'; then
        echo error
    elif printf '%s\n' "$2" | grep -q '^Warning'; then
        echo warning
    else
        echo unknown
    fi
}

verdict() { # name expect text got out
    n=$((n + 1))
    if [ "$4" = "$2" ] && { [ -z "$3" ] || printf '%s\n' "$5" | grep -qF -- "$3"; }; then
        printf 'ok    %-18s %s\n' "$1" "$2"
    else
        bad=$((bad + 1))
        printf 'FAIL  %-18s expected %s "%s", got %s\n' "$1" "$2" "$3" "$4"
        printf '%s\n' "$5" | grep -E '^(Error|Warning)' | sed 's/^/      /'
    fi
}

t() { # name expect text [KEY=VALUE ...]
    local name=$1 expect=$2 text=$3 out rc
    shift 3
    local args=()
    for c in "$@"; do args+=("--config=$c"); done
    out=$("${PCB[@]}" build -Wstyle -Dwarnings harness.zen ${args[@]+"${args[@]}"} 2>&1)
    rc=$?
    verdict "$name" "$expect" "$text" "$(classify $rc "$out")" "$out"
}

# Every case has a comment: the scenario, the worst-case arithmetic behind its numbers, and what it proves.
# Harness defaults (test/harness.zen) are the nominal passing design: V+ 15 V 5% (14.25 to 15.75 V), V- -15 V 5%
# (-15.75 to -14.25 V), +IN 1 V 1% (0.99 to 1.01 V), -IN 0 V, REF 0 V, ambient -40°C to 85°C, derate 1.0, no waivers.
# A case changes only the values it lists. "Worst case" pairs the min of one net with the max of the other.

# Package built alone: no nets attached, so UNVERIFIED drops to advice and the build stays green.
out=$("${PCB[@]}" build -Wstyle -Dwarnings .. 2>&1)
verdict package_root pass "" "$(classify $? "$out")" "$out"

# All defaults: span 28.5 to 31.5 V (inside 4.5-36 V and 0-40 V), inputs inside ±40 V and the vcm window
# -12.25 to 12.25 V, REF 0 V inside -14.25 to 14.25 V, ambient inside the grade. Proves the nominal design passes.
t nominal            pass    ""

# abs_span: V+ - V- <= 40 V x derate. derate 0.8 isolates it from op_span (36 V).
# span max = 16 - (-16) = 32.0 V = 0.8 x 40 V, exactly on the derated limit (op_span 36 V not reached): edge passes.
t span_derate_bound  pass    ""                                     "vp=15.5V to 16V" "vn=-16V to -15.5V" derate=0.8
# span max = 16.1 - (-16) = 32.1 V, 0.1 V over the derated 32 V and still under op_span's 36 V: abs_span alone fails.
t span_derate_out    error   "outside 0.0 to 32.0 V (derate 0.8)"   "vp=15.6V to 16.1V" "vn=-16V to -15.5V" derate=0.8
# span max = 20.1 - (-20) = 40.1 V, over the non-derated 40 V. op_span (36 V) also fires; the text pins abs_span.
t span_abs_out       error   "outside 0.0 to 40.0 V (derate 1.0)"   "vp=20V to 20.1V" "vn=-20V to -19.9V"
# Rails swapped: span min = -15.75 - 15.75 = -31.5 V, below the assumed 0 V minimum (reversed supply not rated).
# op_span (min 4.5 V) also fires; the text pins abs_span ("0.0 to 40.0"). Inputs and REF at 0 V; the inverted
# rails also trip the vcm and ref_range warnings, but an error decides the outcome.
t span_reversed      error   "outside 0.0 to 40.0 V"                "vp=-15V 5%" "vn=15V 5%" vinp=0V vref=0V
# op_span: 4.5 V to 36 V. Inputs and REF moved inside the single-supply common-mode window.
# Single supply, V- = GND: span min = 4.5 - 0 = 4.5 V, exactly the rec-op minimum. Inputs/REF 2.2 V 1%
# (2.178 to 2.222 V) sit inside the vcm window 0 + 2 = 2.0 V to 4.5 - 2 = 2.5 V, so only op_span is at its edge.
t op_lo_bound        pass    ""      "vp=4.5V to 4.6V" vn=GND "vinp=2.2V 1%" "vinn=2.2V 1%" "vref=2.2V 1%"
# span min = 4.4 V, 0.1 V under 4.5 V: op_span fails (vcm window 2.0 to 2.4 V still holds the inputs).
t op_lo_out          error   "4.4 to 4.6 V outside 4.5 to 36.0 V"   "vp=4.4V to 4.6V" vn=GND "vinp=2.2V 1%" "vinn=2.2V 1%" "vref=2.2V 1%"
# span max = 18 - (-18) = 36.0 V, exactly the rec-op maximum (abs_span 40 V not reached): edge passes.
t op_hi_bound        pass    ""                                     "vp=17.5V to 18V" "vn=-18V to -17.5V"
# span max = 18.1 - (-18) = 36.1 V, 0.1 V over 36 V and under abs_span's 40 V: op_span alone fails.
t op_hi_out          error   "35.0 to 36.1 V outside 4.5 to 36.0 V" "vp=17.5V to 18.1V" "vn=-18V to -17.5V"
# abs_IN_P / abs_IN_N: +-40 V to GND. vcm waived so only the abs-max check can fire.
# +IN max = 40 V, exactly the abs max (vcm, which this far exceeds, is waived to advice): edge passes.
t absin_hi_bound     pass    ""                                     "vinp=39V to 40V" waive_vcm=test
# +IN max = 40.1 V, 0.1 V over: abs_IN_P fails.
t absin_hi_out       error   "39.0 to 40.1 V outside -40.0 to 40.0 V" "vinp=39V to 40.1V" waive_vcm=test
# -IN min = -40 V, exactly the abs min: edge passes, and proves the -IN copy of the loop is registered.
t absin_lo_bound     pass    ""                                     "vinn=-40V to -39V" waive_vcm=test
# -IN min = -40.1 V, 0.1 V under: abs_IN_N fails.
t absin_lo_out       error   "-40.1 to -39.0 V outside -40.0 to 40.0 V" "vinn=-40.1V to -39V" waive_vcm=test
# derate 0.5: limit ±20 V, +IN max 21 V fails. abs_span (20 V at derate 0.5, span 31.5 V) also fires; the text
# "-20.0 to 20.0" pins abs_IN_P (abs_span prints "0.0 to 20.0"). Proves derate reaches the input check.
t absin_derate_out   error   "outside -20.0 to 20.0 V (derate 0.5)" "vinp=20V to 21V" derate=0.5 waive_vcm=test
# abs_REF: +-20 V to GND. ref_range waived so only the abs-max check can fire.
# REF max = 20 V, exactly the abs max (ref_range, exceeded, is waived): edge passes.
t absref_hi_bound    pass    ""                                     "vref=19V to 20V" waive_ref=test
# REF max = 20.1 V, 0.1 V over: abs_REF fails.
t absref_hi_out      error   "19.0 to 20.1 V outside -20.0 to 20.0 V" "vref=19V to 20.1V" waive_ref=test
# REF min = -20 V, exactly the abs min: edge passes.
t absref_lo_bound    pass    ""                                     "vref=-20V to -19V" waive_ref=test
# REF min = -20.1 V, 0.1 V under: abs_REF fails.
t absref_lo_out      error   "-20.1 to -19.0 V outside -20.0 to 20.0 V" "vref=-20.1V to -19V" waive_ref=test
# vcm_*: (V-)+2 V to (V+)-2 V, worst case. Default rails +-15 V 5% put the window at -12.25 V to 12.25 V.
# Window top = V+.min - 2 = 14.25 - 2 = 12.25 V; +IN max 12.25 V sits exactly on it: edge passes.
t vcm_hi_bound       pass    ""                                     "vinp=12V to 12.25V"
# +IN max 12.3 V, 0.05 V over the window top: vcm_IN_P warns (25°C-only limit, so warning, not error).
t vcm_hi_out         warning "12.0 to 12.3 V outside (V-)+2.0 to (V+)-2.0" "vinp=12V to 12.3V"
# Same input with a waiver rationale: the warning drops to advice and the build passes. Proves waive_vcm works.
t vcm_hi_waived      pass    ""                                     "vinp=12V to 12.3V" "waive_vcm=DS p.6 test"
# Window bottom = V-.max + 2 = -14.25 + 2 = -12.25 V; -IN min -12.25 V sits exactly on it: edge passes.
t vcm_lo_bound       pass    ""                                     "vinn=-12.25V to -12V"
# -IN min -12.3 V, 0.05 V under the window bottom: vcm_IN_N warns.
t vcm_lo_out         warning "-12.3 to -12.0 V outside (V-)+2.0 to (V+)-2.0" "vinn=-12.3V to -12V"
# ref_range: (V-) to (V+), worst case: -14.25 V to 14.25 V at the default rails.
# REF max 14.25 V = V+.min: edge passes.
t ref_hi_bound       pass    ""                                     "vref=14V to 14.25V"
# REF max 14.3 V, 0.05 V over V+.min: ref_range warns (25°C-only limit).
t ref_hi_out         warning "14.0 to 14.3 V outside (V-)+0.0 to (V+)-0.0" "vref=14V to 14.3V"
# Same REF with a waiver rationale: drops to advice, build passes. Proves waive_ref works.
t ref_hi_waived      pass    ""                                     "vref=14V to 14.3V" "waive_ref=DS p.7 test"
# REF min -14.25 V = V-.max: edge passes.
t ref_lo_bound       pass    ""                                     "vref=-14.25V to -14V"
# REF min -14.3 V, 0.05 V under V-.max: ref_range warns.
t ref_lo_out         warning "-14.3 to -14.0 V outside (V-)+0.0 to (V+)-0.0" "vref=-14.3V to -14V"
# temp_grade: ambient within -40 C to 125 C.
# Ambient exactly the grade range: edge passes.
t ta_bound           pass    ""                                     "ta=-40°C to 125°C"
# Ambient 1°C below the grade minimum: temp_grade fails.
t ta_lo_out          error   "outside -40–125°C"                    "ta=-41°C to 125°C"
# Ambient 1°C above the grade maximum: temp_grade fails.
t ta_hi_out          error   "outside -40–125°C"                    "ta=-40°C to 126°C"
# Tolerance: a net with min == max warns (worst case not assessed); exactly 0 V (GND) is exempt.
# V+ exactly 15 V: span checks pass on the single value, but vpos_tol warns that no worst case was assessed.
t tol_vp             warning "V+ has no tolerance"                  vp=15V
# V- exactly -15 V (not 0 V, so not exempt): vneg_tol warns.
t tol_vn             warning "V- has no tolerance"                  vn=-15V
# +IN exactly 1 V: tol_IN_P warns. (tol_IN_N shares the loop; the default -IN is 0 V, which is exempt.)
t tol_inp            warning "IN_P has no tolerance"                vinp=1V
# REF exactly 1 V: tol_REF warns.
t tol_ref            warning "REF has no tolerance"                 vref=1V
# V- = GND, exactly 0 V: exempt from vneg_tol. Inputs/REF 3 V 1% sit in the single-supply windows (vcm 2.0 to
# 12.25 V, REF 0 to 14.25 V). Proves a single-supply design passes with no tolerance warning on ground.
t gnd_rail_ok        pass    ""      vn=GND "vinp=3V 1%" "vinn=3V 1%" "vref=3V 1%"
# Unset inputs: every check fed by the missing value reports UNVERIFIED, never a silent pass.
# V+ with no voltage: vpos_tol, abs_span, op_span, vcm_* and ref_range all report UNVERIFIED; text pins one.
t unset_vp           warning "UNVERIFIED vpos_tol"                  vp=unset
# V- with no voltage: same set of checks via V-.
t unset_vn           warning "UNVERIFIED vneg_tol"                  vn=unset
# Both inputs with no voltage: tol_, abs_ and vcm_ for each report UNVERIFIED.
t unset_in           warning "UNVERIFIED abs_IN_P"                  vinp=unset vinn=unset
# REF with no voltage: tol_REF, abs_REF and ref_range report UNVERIFIED.
t unset_ref          warning "UNVERIFIED abs_REF"                   vref=unset
# No ambient given: temp_grade reports UNVERIFIED instead of passing.
t ta_unset           warning "UNVERIFIED temp_grade"                ta=unset
# derate must be in (0, 1].
# derate above 1 would loosen abs max: rejected by the top-level check.
t derate_gt1         error   "derate must be in (0, 1]"             derate=1.5
# derate 0 would zero every abs-max limit: rejected.
t derate_zero        error   "derate must be in (0, 1]"             derate=0

# Mutation: _limit() must refuse a waiver on an error-level check. Needs a code change, so patch a temp copy.
tmp=$(mktemp -d)
cp -R .. "$tmp/pkg"
sed -i.bak 's/{"v": ambient, "lim": TA_GRADE}, "error")/{"v": ambient, "lim": TA_GRADE}, "error", "x")/' "$tmp/pkg/INA821IDGK.zen"
if grep -q '"error", "x")' "$tmp/pkg/INA821IDGK.zen"; then
    out=$("${PCB[@]}" build -Wstyle -Dwarnings "$tmp/pkg/INA821IDGK.zen" 2>&1)
    verdict waiver_on_error error "only warning-level checks can be waived" "$(classify $? "$out")" "$out"
else
    verdict waiver_on_error error "mutation applied" unknown "sed pattern not found in INA821IDGK.zen"
fi
rm -rf "$tmp"

echo "$((n - bad))/$n cases as expected"
[ "$bad" -eq 0 ]
