#!/bin/bash
set -euo pipefail

APP_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_BIN="${PYTHON_BIN:-}"

if [[ -z "${PYTHON_BIN}" ]]; then
    if command -v python >/dev/null 2>&1; then
        PYTHON_BIN="python"
    elif command -v python3 >/dev/null 2>&1; then
        PYTHON_BIN="python3"
    else
        echo "No python interpreter found in PATH." >&2
        exit 1
    fi
fi

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" || $# -eq 0 ]]; then
    cat <<'EOF'
Usage:
  bash run_backend.sh <input.json|input.jsonl> [media_path] [run_backend.py options...]

Examples:
  bash run_backend.sh your_data.json --dry-run
  bash run_backend.sh your_data.json /path/to/media_dir --dry-run
  bash run_backend.sh your_data.json --stage infer --infer-model "Gemini-2.5-pro"
  bash run_backend.sh your_data.json /path/to/media_dir --stage infer --infer-model "Gemini-2.5-pro"
  bash run_backend.sh your_data.json --stage eval --judge-model "GPT 5.2"
  bash run_backend.sh your_data.json \
    /path/to/media_dir \
    --infer-model "Gemini-2.5-pro" \
    --judge-model "GPT 5.2" \
    --infer-workers 4 \
    --eval-workers 4 \
    --apply-history

Optional:
  PYTHON_BIN=/path/to/python bash run_backend.sh your_data.json ...

Note:
  API config is read from app_config.env by run_backend.py, or can be
  overridden with --api-key / --base-url / --claude-api-url.
EOF
    exit 0
fi

INPUT_PATH="$1"
shift
if [[ "${INPUT_PATH}" != /* ]]; then
    INPUT_DIR="$(cd -- "$(dirname -- "${INPUT_PATH}")" && pwd)"
    INPUT_PATH="${INPUT_DIR}/$(basename -- "${INPUT_PATH}")"
fi

FORWARDED_ARGS=("${INPUT_PATH}")
if [[ $# -gt 0 && "${1}" != -* ]]; then
    MEDIA_PATH="$1"
    shift
    if [[ "${MEDIA_PATH}" != /* ]]; then
        MEDIA_DIR="$(cd -- "$(dirname -- "${MEDIA_PATH}")" && pwd)"
        MEDIA_PATH="${MEDIA_DIR}/$(basename -- "${MEDIA_PATH}")"
    fi
    FORWARDED_ARGS+=("${MEDIA_PATH}")
fi
FORWARDED_ARGS+=("$@")

cd "${APP_DIR}"
exec "${PYTHON_BIN}" "${APP_DIR}/run_backend.py" "${FORWARDED_ARGS[@]}"
