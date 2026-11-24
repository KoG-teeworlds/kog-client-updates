#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
image=mcr.microsoft.com/playwright@sha256:70e367e0cbf60340a5b5fd562f6247a34eb3196efab9f88a3dd56482d9fe09d2
mode=${1:?usage: browser.sh og|pages [outdir]}
out=${2:-/tmp/kog-client-site-shots}
visual=${3:-}
mkdir -p "$out"
case "$mode" in
  og) mount=(-v "$PWD:/work") ;;
  pages) mount=(-v "$PWD:/work:ro") ;;
  *) echo "unknown mode" >&2; exit 2 ;;
esac
docker run --rm --ipc=host "${mount[@]}" -v "$out:/out" -w /tmp "$image" \
  sh -c 'npm init -y >/dev/null && npm i --no-audit --no-fund --ignore-scripts playwright-core@1.49.1 >/dev/null 2>&1 && cp /work/scripts/shoot.mjs . && node shoot.mjs '"$mode $visual"
