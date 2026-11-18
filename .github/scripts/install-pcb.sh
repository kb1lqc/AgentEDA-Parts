#!/usr/bin/env bash
# Install the pinned pcb toolchain from diodeinc/pcb GitHub releases: the exact pcbc release binary (static musl) and
# its stdlib, both sha256-checked, laid out as the launcher does (<dir>/pcb, <dir>/lib/std/) and put on PATH as `pcb`.
# CI never uses the self-updating shim, so a run is reproducible.
set -euo pipefail
version="${PCB_VERSION:?set PCB_VERSION, e.g. v0.4.102}"
base="https://github.com/diodeinc/pcb/releases/download/${version}"
dir="${RUNNER_TEMP:-/tmp}/pcb-${version}"
mkdir -p "$dir/lib/std"
fetch() {  # fetch <asset> <output>: download and check against the published sha256
  curl -fsSL --retry 3 "$base/$1" -o "$2"
  echo "$(curl -fsSL --retry 3 "$base/$1.sha256" | awk '{print $1}')  $2" | sha256sum -c -
}
fetch pcbc-x86_64-unknown-linux-musl "$dir/pcb"
fetch stdlib.tar.zst "$dir/stdlib.tar.zst"
zstd -q -dc "$dir/stdlib.tar.zst" | tar -x -C "$dir/lib/std"
chmod +x "$dir/pcb"
echo "$dir" >> "${GITHUB_PATH:-/dev/null}"
"$dir/pcb" --version
