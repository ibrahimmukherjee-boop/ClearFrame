#!/usr/bin/env bash
# Link your Mac Downloads copies into the Nexus sandbox workspace.
# Run this on your Mac after cloning the workspace repo.

set -euo pipefail

DOWNLOADS="${NEXUS_DOWNLOADS:-/Users/ibrahimmukherjee/Downloads}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COMPONENTS="${ROOT}/components"

link_repo() {
  local src_name="$1"
  local dest_name="$2"
  local src="${DOWNLOADS}/${src_name}"
  local dest="${COMPONENTS}/${dest_name}"

  if [ ! -d "$src" ]; then
    echo "SKIP  $src_name (not found at $src)"
    return
  fi

  if [ -L "$dest" ] || [ -d "$dest" ]; then
    rm -rf "$dest"
  fi
  ln -s "$src" "$dest"
  echo "LINK  $src → $dest"
}

mkdir -p "$COMPONENTS"

link_repo "TrustRegistry-main" "trust-registry"
link_repo "Aegis-main" "aegis"
link_repo "Sonar-main" "sonar"
link_repo "ClearFrame-main" "clearframe-upstream"

if [ -d "${DOWNLOADS}/Clearframe Stack" ]; then
  ln -sfn "${DOWNLOADS}/Clearframe Stack" "${ROOT}/clearframe-stack"
  echo "LINK  Clearframe Stack → ${ROOT}/clearframe-stack"
fi

echo ""
echo "Done. Re-install components:"
echo "  pip install -e ${COMPONENTS}/trust-registry"
echo "  pip install -e ${COMPONENTS}/aegis"
echo "  pip install -e ${COMPONENTS}/sonar"
echo "  bash ${ROOT}/scripts/start-all.sh"
