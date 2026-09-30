#!/bin/bash
set -euo pipefail
repo_dir="$(cd "$(dirname "$0")/.." && pwd)"
if [[ -n "${MEWGENICS_CACHE_DIR:-}" ]]; then
  task_cache="$MEWGENICS_CACHE_DIR"
elif [[ -d /Volumes/Work ]]; then
  task_cache=/Volumes/Work/caches/meowgenics-ipad
else
  echo 'Work drive is unavailable. Set MEWGENICS_CACHE_DIR to an explicitly approved temporary location.' >&2
  exit 1
fi
mkdir -p "$task_cache/tmp" "$task_cache/modules" "$task_cache/diagnostics"
export TMPDIR="$task_cache/tmp"
export CLANG_MODULE_CACHE_PATH="$task_cache/modules"
export SWIFT_MODULECACHE_PATH="$task_cache/modules"
xcrun swiftc -swift-version 5 -O -module-cache-path "$task_cache/modules" \
  -import-objc-header "$repo_dir/MewgenicsIPad/Core/ZlibBridge.h" -lz \
  "$repo_dir"/MewgenicsIPad/Core/*.swift "$repo_dir/Tests/main.swift" \
  -o "$task_cache/core-tests"
"$task_cache/core-tests" "$@"
