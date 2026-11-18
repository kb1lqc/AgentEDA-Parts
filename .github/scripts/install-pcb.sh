#!/usr/bin/env bash
# Install the pinned pcb toolchain (pcbc) from diodeinc/pcb GitHub releases: exact version, sha256-checked, static
# musl binary, on PATH as `pcb`. CI never uses the self-updating shim, so a run is reproducible.
set -euo pipefail
version="${PCB_VERSION:?set PCB_VERSION, e.g. v0.4.102}"
asset="pcbc-x86_64-unknown-linux-musl"
url="https://github.com/diodeinc/pcb/releases/download/${version}/${asset}"
dir="${RUNNER_TEMP:-/tmp}/pcb-${version}"
mkdir -p "$dir"
curl -fsSL --retry 3 "$url" -o "$dir/pcb"
curl -fsSL --retry 3 "$url.sha256" -o "$dir/pcb.sha256"
echo "$(awk '{print $1}' "$dir/pcb.sha256")  $dir/pcb" | sha256sum -c -
chmod +x "$dir/pcb"
echo "$dir" >> "${GITHUB_PATH:-/dev/null}"
"$dir/pcb" --version
