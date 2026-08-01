#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

for d in core sources media content avito admin lifecycle messenger scheduler bot web tests; do
  : > "$d/__init__.py"
  echo "created $d/__init__.py"
done

: > data/.gitkeep
: > media_store/.gitkeep
echo done
