#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${REPO_ROOT}"

VERSION="${1:-}"

if [[ -x ".venv/bin/python" ]]; then
  PYTHON=".venv/bin/python"
else
  PYTHON="python3"
fi

if [[ -z "${VERSION}" ]]; then
  if git describe --tags --always >/dev/null 2>&1; then
    VERSION="$(git describe --tags --always)"
  else
    VERSION="dev"
  fi
fi

VERSION_SAFE="$(echo "${VERSION}" | sed 's/[^0-9A-Za-z._-]/_/g')"
HASH="$(git rev-parse --short HEAD 2>/dev/null || echo "local")"
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
  DIRTY="_dirty"
else
  DIRTY=""
fi

EXE_NAME="GameHub_${VERSION_SAFE}_${HASH}${DIRTY}_linux_x86_64"
export GAMEHUB_EXE_NAME="${EXE_NAME}"

echo "Building Linux artifact: ${EXE_NAME}"

"${PYTHON}" -m pip install --upgrade pip
if [[ -f "requirements-lock.txt" ]]; then
  "${PYTHON}" -m pip install -r requirements-lock.txt
else
  "${PYTHON}" -m pip install -r requirements-dev.txt
fi

"${PYTHON}" -m PyInstaller --noconfirm --clean GameHub_allmods.spec

DIST_DIR="${REPO_ROOT}/dist"
BIN_PATH="${DIST_DIR}/${EXE_NAME}"
if [[ ! -f "${BIN_PATH}" ]]; then
  echo "Build finished, but binary not found: ${BIN_PATH}" >&2
  exit 1
fi

TAR_PATH="${DIST_DIR}/${EXE_NAME}.tar.gz"
rm -f "${TAR_PATH}"
tar -C "${DIST_DIR}" -czf "${TAR_PATH}" "${EXE_NAME}"

SHA_FILE="${DIST_DIR}/SHA256SUMS_linux.txt"
sha256sum "${BIN_PATH}" | sed "s|${BIN_PATH}|${EXE_NAME}|g" > "${SHA_FILE}"
sha256sum "${TAR_PATH}" | sed "s|${TAR_PATH}|${EXE_NAME}.tar.gz|g" >> "${SHA_FILE}"

echo "Build OK: ${BIN_PATH}"
echo "TAR OK:   ${TAR_PATH}"
echo "SHA256:   ${SHA_FILE}"
