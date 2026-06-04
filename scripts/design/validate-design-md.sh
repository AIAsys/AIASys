#!/bin/bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DESIGN_FILE="${1:-${PROJECT_ROOT}/DESIGN.md}"

if [[ ! -f "${DESIGN_FILE}" ]]; then
  echo "DESIGN.md not found: ${DESIGN_FILE}" >&2
  exit 1
fi

exec npx -y @google/design.md lint "${DESIGN_FILE}"
