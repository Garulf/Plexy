#!/usr/bin/env bash
# Build the Flow Launcher plugin archive and print its path.
# Usage: scripts/package.sh [out_dir]   (default: dist)
set -euo pipefail

root="$(cd "$(dirname "$0")/.." && pwd)"
out_dir="${1:-$root/dist}"
version="$(python3 -c 'import json, sys; print(json.load(open(sys.argv[1]))["Version"])' "$root/data/plugin.json")"
build_dir="$(mktemp -d)"
wheelhouse="$(mktemp -d)"
trap 'rm -rf "$build_dir" "$wheelhouse"' EXIT

cp -r "$root/src/." "$build_dir/"
cp "$root/data/icon.png" "$root/data/cast.png" "$root/data/plugin.json" "$root/data/SettingsTemplate.yaml" \
  "$root/LICENSE" "$build_dir/"
find "$build_dir" \( -name __pycache__ -o -name "*.log" \) -prune -exec rm -rf {} +

# zeroconf only publishes compiled wheels, so build its pure-Python fallback and tag it as such.
python3 -m pip install --quiet --disable-pip-version-check wheel
SKIP_CYTHON=1 python3 -m pip wheel --no-deps --no-binary zeroconf \
  "$(grep -i '^zeroconf==' "$root/requirements.txt")" -w "$wheelhouse" \
  --quiet --disable-pip-version-check
python3 -m wheel tags --remove --python-tag py3 --abi-tag none --platform-tag any "$wheelhouse"/zeroconf-*.whl >/dev/null

# Vendor pure-Python wheels resolved for the oldest supported Python (pychromecast
# needs 3.11), so the archive works with whichever newer Python Flow Launcher uses.
python3 -m pip install -r "$root/requirements.txt" \
  --target "$build_dir/plugin/site-packages" \
  --only-binary=:all: --platform any --python-version 3.11 --implementation py \
  --find-links "$wheelhouse" \
  --quiet --disable-pip-version-check

mkdir -p "$out_dir"
zip_path="$(cd "$out_dir" && pwd)/Plexy-${version}.zip"
rm -f "$zip_path"
(cd "$build_dir" && zip -qr "$zip_path" .)
echo "$zip_path"
