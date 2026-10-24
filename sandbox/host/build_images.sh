#!/usr/bin/env bash
# Builds the sandbox base images: one folder under sandbox/images per image, tagged talnex-sandbox-<folder>.
# Run it on the sandbox host after Docker is up:  bash sandbox/host/build_images.sh [node python ...]
set -euo pipefail
cd "$(dirname "$0")/../images"
names=("$@")
if [ ${#names[@]} -eq 0 ]; then names=(*/); fi
for dir in "${names[@]}"; do
  dir="${dir%/}"
  echo "== building talnex-sandbox-$dir"
  docker build -t "talnex-sandbox-$dir" "$dir"
done
