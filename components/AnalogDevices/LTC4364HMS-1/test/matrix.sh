#!/usr/bin/env bash
# Self-checking matrix for LTC4364HMS-1. Method: docs/TESTING.md. Case list: test/README.md.
# Usage: test/matrix.sh [pcb version, e.g. 0.4.95]   (from any directory; default = current toolchain)
# Each case builds harness.zen with --config overrides, then compares the outcome with the expectation:
#   pass    = build exits 0 under -Wstyle -Dwarnings
#   error   = build fails with an Error diagnostic
#   warning = build fails with Warning diagnostics only (-Dwarnings promotes them)
# and requires the given text in the output. Exit 1 if any case differs.
VALUE=LTC4364HMS-1
set -u
cd "$(dirname "$0")" || exit 2
PCB=(pcb)
[ $# -ge 1 ] && PCB=(pcb "+$1")
echo "toolchain: $("${PCB[@]}" --version)"
n=0
bad=0

classify() { # $1 = exit code, $2 = output. Exit code first: a build that cannot start has no check output.
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

# Package built alone: no nets attached, so UNVERIFIED drops to advice and the build stays green.
out=$("${PCB[@]}" build -Wstyle -Dwarnings .. 2>&1)
verdict package_root pass "" "$(classify $? "$out")" "$out"

t nominal                pass    ""

# tol_*: a net with min == max warns; exactly 0 V is exempt (FB/OV/FLT/ENOUT may be tied to GND, DS p.8-9).
t tol_VCC                warning "VCC has no tolerance"                 vcc=12V
t tol_OUT                warning "OUT has no tolerance"                 vout=12V
t tol_SENSE              warning "SENSE has no tolerance"               vsense=12V
t tol_OV                 warning "OV has no tolerance"                  vov=1V
t tol_UV                 warning "UV has no tolerance"                  vuv=2V
t tol_SHDN               warning "SHDN has no tolerance"                vshdn=12V
t tol_FB                 warning "FB has no tolerance"                  vfb=1V
t tol_ENOUT              warning "ENOUT has no tolerance"               venout=12V
t tol_FLT                warning "FLT has no tolerance"                 vflt=3V
t zero_ok_OV             pass    ""                                     vov=0V
t zero_ok_FB             pass    ""                                     vfb=0V
t zero_ok_ENOUT          pass    ""                                     venout=0V
t zero_ok_FLT            pass    ""                                     vflt=0V

# op_VCC: 4 V to 80 V (k fixed at 1.0).
t op_VCC_lo_bound        pass    ""                                     "vcc=4V to 5V"
t op_VCC_lo_out          error   "3.9 to 5.0 V outside 4.0 to 80.0 V (derate 1.0)" "vcc=3.9V to 5V"
t op_VCC_hi_bound        pass    ""                                     "vcc=79V to 80V"
t op_VCC_hi_out          error   "79.0 to 80.1 V outside 4.0 to 80.0 V (derate 1.0)" "vcc=79V to 80.1V"

# abs_VCC: -40 V to 100 V. At derate 1 it sits outside op_VCC (4-80 V), so no passing boundary exists and every
# outside case also fires op_VCC. Derate 0.5 pulls the upper limit to 50 V, inside op_VCC, which isolates it.
t abs_VCC_hi_out         error   "99.0 to 100.1 V outside -40.0 to 100.0 V (derate 1.0)" "vcc=99V to 100.1V"
t abs_VCC_lo_out         error   "-40.1 to -39.0 V outside -40.0 to 100.0 V (derate 1.0)" "vcc=-40.1V to -39V"
t abs_VCC_dr_bound       pass    ""                                     "vcc=49V to 50V" derate=0.5
t abs_VCC_dr_out         error   "49.0 to 50.1 V outside -20.0 to 50.0 V (derate 0.5)" "vcc=49V to 50.1V" derate=0.5

# abs_OV, abs_UV, abs_SHDN: -40 V to 100 V (no rec-op range, so every edge is isolated). Distinct numbers per pin.
t abs_OV_hi_bound        pass    ""                                     "vov=98V to 100V"
t abs_OV_hi_out          error   "98.0 to 100.1 V outside -40.0 to 100.0 V (derate 1.0)" "vov=98V to 100.1V"
t abs_OV_lo_bound        pass    ""                                     "vov=-40V to -38V"
t abs_OV_lo_out          error   "-40.1 to -38.0 V outside -40.0 to 100.0 V (derate 1.0)" "vov=-40.1V to -38V"
t abs_OV_dr_bound        pass    ""                                     "vov=49V to 50V" derate=0.5
t abs_OV_dr_out          error   "49.5 to 50.1 V outside -20.0 to 50.0 V (derate 0.5)" "vov=49.5V to 50.1V" derate=0.5
t abs_UV_hi_bound        pass    ""                                     "vuv=97V to 100V"
t abs_UV_hi_out          error   "97.0 to 100.2 V outside -40.0 to 100.0 V (derate 1.0)" "vuv=97V to 100.2V"
t abs_UV_lo_bound        pass    ""                                     "vuv=-40V to -37V"
t abs_UV_lo_out          error   "-40.2 to -37.0 V outside -40.0 to 100.0 V (derate 1.0)" "vuv=-40.2V to -37V"
t abs_SHDN_hi_bound      pass    ""                                     "vshdn=96V to 100V"
t abs_SHDN_hi_out        error   "96.0 to 100.3 V outside -40.0 to 100.0 V (derate 1.0)" "vshdn=96V to 100.3V"
t abs_SHDN_lo_bound      pass    ""                                     "vshdn=-40V to -36V"
t abs_SHDN_lo_out        error   "-40.3 to -36.0 V outside -40.0 to 100.0 V (derate 1.0)" "vshdn=-40.3V to -36V"
t abs_SHDN_dr_lo_bound   pass    ""                                     "vshdn=-20V to -18V" derate=0.5
t abs_SHDN_dr_lo_out     error   "-20.3 to -18.0 V outside -20.0 to 50.0 V (derate 0.5)" "vshdn=-20.3V to -18V" derate=0.5

# Derate 0.5 on the remaining control-pin edges: -40..100 V becomes -20..50 V.
t abs_OV_dr_lo_bound     pass    ""                                     "vov=-20V to -19V" derate=0.5
t abs_OV_dr_lo_out       error   "-20.4 to -19.0 V outside -20.0 to 50.0 V (derate 0.5)" "vov=-20.4V to -19V" derate=0.5
t abs_UV_dr_hi_bound     pass    ""                                     "vuv=47V to 50V" derate=0.5
t abs_UV_dr_hi_out       error   "47.0 to 50.3 V outside -20.0 to 50.0 V (derate 0.5)" "vuv=47V to 50.3V" derate=0.5
t abs_UV_dr_lo_bound     pass    ""                                     "vuv=-20V to -17V" derate=0.5
t abs_UV_dr_lo_out       error   "-20.5 to -17.0 V outside -20.0 to 50.0 V (derate 0.5)" "vuv=-20.5V to -17V" derate=0.5
t abs_SHDN_dr_hi_bound   pass    ""                                     "vshdn=48V to 50V" derate=0.5
t abs_SHDN_dr_hi_out     error   "48.0 to 50.2 V outside -20.0 to 50.0 V (derate 0.5)" "vshdn=48V to 50.2V" derate=0.5

# abs_OUT, abs_SENSE: -20 V to 100 V. SENSE is moved with OUT so abs_SENSE_OUT (+-30 V) and abs_OUT_VCC stay quiet.
t abs_OUT_hi_bound       pass    ""                                     "vout=99V to 100V" "vsense=99V to 100V"
t abs_OUT_hi_out         error   "99.0 to 100.1 V outside -20.0 to 100.0 V (derate 1.0)" "vout=99V to 100.1V" "vsense=99V to 100V"
t abs_OUT_lo_bound       pass    ""                                     "vout=-20V to -19V" "vsense=-20V to -19V"
t abs_OUT_lo_out         error   "-20.1 to -19.0 V outside -20.0 to 100.0 V (derate 1.0)" "vout=-20.1V to -19V" "vsense=-20V to -19V"
t abs_OUT_dr_hi_bound    pass    ""                                     "vout=49V to 50V" "vsense=49V to 50V" derate=0.5
t abs_OUT_dr_hi_out      error   "49.0 to 50.3 V outside -10.0 to 50.0 V (derate 0.5)" "vout=49V to 50.3V" "vsense=49V to 50V" derate=0.5
t abs_OUT_dr_lo_bound    pass    ""                                     "vout=-10V to -8V" "vsense=-10V to -8V" derate=0.5
t abs_OUT_dr_lo_out      error   "-10.4 to -8.0 V outside -10.0 to 50.0 V (derate 0.5)" "vout=-10.4V to -8V" "vsense=-10V to -8V" derate=0.5
t abs_SENSE_hi_bound     pass    ""                                     "vsense=98V to 100V" "vout=98V to 100V"
t abs_SENSE_hi_out       error   "98.0 to 100.2 V outside -20.0 to 100.0 V (derate 1.0)" "vsense=98V to 100.2V" "vout=98V to 100V"
t abs_SENSE_lo_bound     pass    ""                                     "vsense=-20V to -18V" "vout=-20V to -18V"
t abs_SENSE_lo_out       error   "-20.2 to -18.0 V outside -20.0 to 100.0 V (derate 1.0)" "vsense=-20.2V to -18V" "vout=-20V to -18V"
t abs_SENSE_dr_out       error   "48.0 to 50.4 V outside -10.0 to 50.0 V (derate 0.5)" "vsense=48V to 50.4V" "vout=48V to 50V" derate=0.5

# abs_FB: -0.3 V to 5.5 V.
t abs_FB_hi_bound        pass    ""                                     "vfb=5.4V to 5.5V"
t abs_FB_hi_out          error   "5.4 to 5.6 V outside -0.3 to 5.5 V (derate 1.0)" "vfb=5.4V to 5.6V"
t abs_FB_lo_bound        pass    ""                                     "vfb=-0.3V to -0.2V"
t abs_FB_lo_out          error   "-0.4 to -0.2 V outside -0.3 to 5.5 V (derate 1.0)" "vfb=-0.4V to -0.2V"
t abs_FB_dr_bound        pass    ""                                     "vfb=2.7V to 2.75V" derate=0.5
t abs_FB_dr_out          error   "2.7 to 2.8 V outside -0.15 to 2.75 V (derate 0.5)" "vfb=2.7V to 2.8V" derate=0.5

# abs_ENOUT, abs_FLT: -0.3 V to 80 V (the lower of DS p.2 100 V and DS p.9 80 V).
t abs_ENOUT_hi_bound     pass    ""                                     "venout=78V to 80V"
t abs_ENOUT_hi_out       error   "78.0 to 80.1 V outside -0.3 to 80.0 V (derate 1.0)" "venout=78V to 80.1V"
t abs_ENOUT_lo_bound     pass    ""                                     "venout=-0.3V to -0.1V"
t abs_ENOUT_lo_out       error   "-0.4 to -0.1 V outside -0.3 to 80.0 V (derate 1.0)" "venout=-0.4V to -0.1V"
t abs_FLT_hi_bound       pass    ""                                     "vflt=77V to 80V"
t abs_FLT_hi_out         error   "77.0 to 80.2 V outside -0.3 to 80.0 V (derate 1.0)" "vflt=77V to 80.2V"
t abs_FLT_lo_bound       pass    ""                                     "vflt=-0.3V to 0.1V"
t abs_FLT_lo_out         error   "-0.5 to 0.1 V outside -0.3 to 80.0 V (derate 1.0)" "vflt=-0.5V to 0.1V"

# Derate 0.5 on FB lower edge (-0.15 V) and ENOUT/FLT (-0.15 V to 40 V).
t abs_FB_dr_lo_bound     pass    ""                                     "vfb=-0.15V to -0.1V" derate=0.5
t abs_FB_dr_lo_out       error   "-0.25 to -0.1 V outside -0.15 to 2.75 V (derate 0.5)" "vfb=-0.25V to -0.1V" derate=0.5
t abs_ENOUT_dr_hi_bound  pass    ""                                     "venout=38V to 40V" derate=0.5
t abs_ENOUT_dr_hi_out    error   "38.0 to 40.1 V outside -0.15 to 40.0 V (derate 0.5)" "venout=38V to 40.1V" derate=0.5
t abs_ENOUT_dr_lo_bound  pass    ""                                     "venout=-0.15V to 0.1V" derate=0.5
t abs_ENOUT_dr_lo_out    error   "-0.2 to 0.1 V outside -0.15 to 40.0 V (derate 0.5)" "venout=-0.2V to 0.1V" derate=0.5
t abs_FLT_dr_hi_bound    pass    ""                                     "vflt=37V to 40V" derate=0.5
t abs_FLT_dr_hi_out      error   "37.0 to 40.2 V outside -0.15 to 40.0 V (derate 0.5)" "vflt=37V to 40.2V" derate=0.5
t abs_FLT_dr_lo_bound    pass    ""                                     "vflt=-0.15V to 0.2V" derate=0.5
t abs_FLT_dr_lo_out      error   "-0.3 to 0.2 V outside -0.15 to 40.0 V (derate 0.5)" "vflt=-0.3V to 0.2V" derate=0.5

# abs_SENSE_OUT: SENSE - OUT, +-30 V. Worst case lo = SENSE.min - OUT.max, hi = SENSE.max - OUT.min.
t pair_SO_hi_bound       pass    ""                                     "vsense=39V to 40V" "vout=10V to 11V"
t pair_SO_hi_out         error   "28.0 to 30.1 V outside -30.0 to 30.0 V (derate 1.0)" "vsense=39V to 40.1V" "vout=10V to 11V"
t pair_SO_lo_bound       pass    ""                                     "vsense=10V to 11V" "vout=39V to 40V"
t pair_SO_lo_out         error   "-30.1 to -28.0 V outside -30.0 to 30.0 V (derate 1.0)" "vsense=9.9V to 11V" "vout=39V to 40V"
t pair_SO_dr_hi_bound    pass    ""                                     "vsense=24V to 25V" "vout=10V to 11V" derate=0.5
t pair_SO_dr_hi_out      error   "13.0 to 15.2 V outside -15.0 to 15.0 V (derate 0.5)" "vsense=24V to 25.2V" "vout=10V to 11V" derate=0.5
t pair_SO_dr_lo_bound    pass    ""                                     "vsense=10V to 11V" "vout=24V to 25V" derate=0.5
t pair_SO_dr_lo_out      error   "-15.2 to -13.0 V outside -15.0 to 15.0 V (derate 0.5)" "vsense=9.8V to 11V" "vout=24V to 25V" derate=0.5

# abs_OUT_VCC: OUT - VCC, +-100 V. Upper edge (OUT.max - VCC.min) cannot be reached by a legal design: it needs
# VCC.min <= 0 (op_VCC fires) or OUT.max >= 104 V (abs_OUT fires), so its outside case also fires op_VCC and no pass
# boundary exists. Lower edge (OUT.min - VCC.max) is reachable exactly at OUT -20 V, VCC 80 V. Derate 0.5 isolates it.
t pair_OV_lo_bound       pass    ""                                     "vout=-20V to -19V" "vsense=-20V to -19V" "vcc=79V to 80V"
t pair_OV_lo_out         error   "-100.1 to -98.0 V outside -100.0 to 100.0 V (derate 1.0)" "vout=-20V to -19V" "vsense=-20V to -19V" "vcc=79V to 80.1V"
t pair_OV_hi_out         error   "98.0 to 100.1 V outside -100.0 to 100.0 V (derate 1.0)" "vout=99V to 100V" "vsense=99V to 100V" "vcc=-0.1V to 1V"
t pair_OV_dr_lo_bound    pass    ""                                     "vout=-10V to -9V" "vsense=-10V to -9V" "vcc=39V to 40V" derate=0.5
t pair_OV_dr_lo_out      error   "-50.1 to -48.0 V outside -50.0 to 50.0 V (derate 0.5)" "vout=-10V to -9V" "vsense=-10V to -9V" "vcc=39V to 40.1V" derate=0.5

# temp_grade: ambient within -40 C to 125 C (H grade).
t ta_bound               pass    ""                                     "ta=-40°C to 125°C"
t ta_lo_out              error   "-41–125°C"                            "ta=-41°C to 125°C"
t ta_hi_out              error   "-40–126°C"                            "ta=-40°C to 126°C"

# Unset inputs: every check on the input reports UNVERIFIED, never a silent pass.
t unset_vcc_tol          warning "UNVERIFIED tol_VCC"                   vcc=unset
t unset_vcc_abs          warning "UNVERIFIED abs_VCC"                   vcc=unset
t unset_vcc_op           warning "UNVERIFIED op_VCC"                    vcc=unset
t unset_vcc_pair         warning "UNVERIFIED abs_OUT_VCC"               vcc=unset
t unset_vout_tol         warning "UNVERIFIED tol_OUT"                   vout=unset
t unset_vout_abs         warning "UNVERIFIED abs_OUT"                   vout=unset
t unset_vout_pairSO      warning "UNVERIFIED abs_SENSE_OUT"             vout=unset
t unset_vout_pairOV      warning "UNVERIFIED abs_OUT_VCC"               vout=unset
t unset_vsense_tol       warning "UNVERIFIED tol_SENSE"                 vsense=unset
t unset_vsense_abs       warning "UNVERIFIED abs_SENSE"                 vsense=unset
t unset_vsense_pair      warning "UNVERIFIED abs_SENSE_OUT"             vsense=unset
t unset_vov_tol          warning "UNVERIFIED tol_OV"                    vov=unset
t unset_vov_abs          warning "UNVERIFIED abs_OV"                    vov=unset
t unset_vuv_tol          warning "UNVERIFIED tol_UV"                    vuv=unset
t unset_vuv_abs          warning "UNVERIFIED abs_UV"                    vuv=unset
t unset_vshdn_tol        warning "UNVERIFIED tol_SHDN"                  vshdn=unset
t unset_vshdn_abs        warning "UNVERIFIED abs_SHDN"                  vshdn=unset
t unset_vfb_tol          warning "UNVERIFIED tol_FB"                    vfb=unset
t unset_vfb_abs          warning "UNVERIFIED abs_FB"                    vfb=unset
t unset_venout_tol       warning "UNVERIFIED tol_ENOUT"                 venout=unset
t unset_venout_abs       warning "UNVERIFIED abs_ENOUT"                 venout=unset
t unset_vflt_tol         warning "UNVERIFIED tol_FLT"                   vflt=unset
t unset_vflt_abs         warning "UNVERIFIED abs_FLT"                   vflt=unset
t unset_ta               warning "UNVERIFIED temp_grade"                ta=unset

# derate must be in (0, 1].
t derate_gt1             error   "derate must be in (0, 1]"             derate=1.5
t derate_zero            error   "derate must be in (0, 1]"             derate=0

# Mutation: _limit() must refuse a waiver on an error-level check. Needs a code change, so patch a temp copy.
tmp=$(mktemp -d)
cp -R .. "$tmp/pkg"
sed -i.bak 's/{"v": ambient, "lim": TA_GRADE}, "error")/{"v": ambient, "lim": TA_GRADE}, "error", "x")/' "$tmp/pkg/$VALUE.zen"
if grep -q '"error", "x")' "$tmp/pkg/$VALUE.zen"; then
    out=$("${PCB[@]}" build -Wstyle -Dwarnings "$tmp/pkg/$VALUE.zen" 2>&1)
    verdict waiver_on_error error "only warning-level checks can be waived" "$(classify $? "$out")" "$out"
else
    verdict waiver_on_error error "mutation applied" unknown "sed pattern not found in $VALUE.zen"
fi
rm -rf "$tmp"

echo "$((n - bad))/$n cases as expected"
[ "$bad" -eq 0 ]
