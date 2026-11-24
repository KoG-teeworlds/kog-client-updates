#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
playwright=mcr.microsoft.com/playwright@sha256:70e367e0cbf60340a5b5fd562f6247a34eb3196efab9f88a3dd56482d9fe09d2
python=python:3.13-slim

docker run --rm --network none -v "$PWD:/work:ro" -w /work "$python" python -B -m unittest discover -s tests -v
docker run --rm --network none -v "$PWD:/work:ro" -w /work "$playwright" node --test tests/manifest.test.js
scripts/browser.sh pages "${KOG_SHOTS:-/tmp/kog-client-site-shots}"
