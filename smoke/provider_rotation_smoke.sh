#!/usr/bin/env bash
set -Eeuo pipefail

cd "$(dirname "$0")/.."
uv run python smoke/provider_rotation_smoke.py "$@"
