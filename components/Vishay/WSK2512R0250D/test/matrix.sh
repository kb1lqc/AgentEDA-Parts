#!/usr/bin/env bash
# Self-checking matrix for WSK2512R0250D. Method: docs/TESTING.md. Case list: test/README.md.
# Usage: test/matrix.sh [pcb version, e.g. 0.4.95]   (from any directory; default = current toolchain)
# Each case builds harness.zen with --config overrides, then compares the outcome with the expectation:
#   pass    = build exits 0 under -Wstyle -Dwarnings
#   error   = build fails with an Error diagnostic
#   warning = build fails with Warning diagnostics only (-Dwarnings promotes them)
# and requires the given text in the output. Exit 1 if any case differs.
VALUE=WSK2512R0250D
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

# Every case gets a comment line above it: the scenario, the worst-case arithmetic, and which checks fire.
# Harness defaults: ambient -40 °C to 85 °C (inside the -65 °C to 170 °C operating range), derate 1.0, the four
# terminals on named nets with no voltage. The only electrical check is temp_grade, so every failing case below can
# fire only temp_grade or the derate guard.

# Package built alone: no nets attached, so UNVERIFIED drops to advice and the build stays green.
out=$("${PCB[@]}" build -Wstyle -Dwarnings .. 2>&1)
verdict package_root pass "" "$(classify $? "$out")" "$out"

# Defaults: ambient -40 °C to 85 °C inside -65 °C to 170 °C, derate 1.0: nothing fires.
t nominal            pass    ""
# temp_grade: ambient within -65 °C to 170 °C (DS p.2 Operating temperature range), _within, error.
# ambient min = -65 °C, exactly on the lower limit: passes.
t ta_lo_bound        pass    ""                                     "ta=-65°C to 85°C"
# ambient max = 170 °C, exactly on the upper limit (rated power is 0 W there; that is the module's check): passes.
t ta_hi_bound        pass    ""                                     "ta=-40°C to 170°C"
# ambient min = -66 °C, 1 °C below -65 °C: only temp_grade fails.
t ta_lo_out          error   "-66–85°C (9.5°C nom.) outside -65–170°C" "ta=-66°C to 85°C"
# ambient max = 171 °C, 1 °C above 170 °C: only temp_grade fails.
t ta_hi_out          error   "-40–171°C (65.5°C nom.) outside -65–170°C" "ta=-40°C to 171°C"
# ambient not given: temp_grade reports UNVERIFIED (warning), never a silent pass. Nothing else fires.
t unset_ta           warning "UNVERIFIED temp_grade"                ta=unset
# derate guard: must be in (0, 1]. 0.5 is accepted (nothing here is derated; modules pass it down): passes.
t derate_ok          pass    ""                                     derate=0.5
# derate 1.5 > 1 would loosen limits: the guard check() errors at evaluation.
t derate_gt1         error   "derate must be in (0, 1]"             derate=1.5
# derate 1.01, just above the 1.0 limit (the nominal case covers 1.0 itself): the guard errors.
t derate_gt1_edge    error   "derate must be in (0, 1]"             derate=1.01
# derate 0 is outside (0, 1]: the guard errors.
t derate_zero        error   "derate must be in (0, 1]"             derate=0

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
