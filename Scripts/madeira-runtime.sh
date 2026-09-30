#!/bin/bash
# Standalone Mewgenics runtime. Private settings stay in ignored .local/.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[ ! -f "$ROOT/.local/config.sh" ] || source "$ROOT/.local/config.sh"
: "${MEWGENICS_CACHE:?Copy config.example.sh to .local/config.sh and set MEWGENICS_CACHE}"
CACHE="$MEWGENICS_CACHE"
case "$CACHE" in /*) ;; *) echo 'MEWGENICS_CACHE must be an absolute path' >&2; exit 2 ;; esac
python3 - "$ROOT" "$CACHE" <<'PY'
import os, pathlib, sys
root, cache = map(pathlib.Path, sys.argv[1:])
if cache.resolve().is_relative_to(root.resolve()):
    raise SystemExit('MEWGENICS_CACHE must be outside the source repository')
if cache.parts[:2] == ('/', 'Volumes') and len(cache.parts) > 2:
    volume = pathlib.Path('/Volumes') / cache.parts[2]
    if not os.path.ismount(volume):
        raise SystemExit(f'Cache volume is not mounted: {volume}')
PY
SOURCE="$CACHE/sources/Madeira"
export TMPDIR="$CACHE/tmp" XDG_CACHE_HOME="$CACHE/packages"
export CCACHE_DIR="$CACHE/ccache" CLANG_MODULE_CACHE_PATH="$CACHE/clang-modules"
export PATH="/opt/homebrew/opt/bison/bin:/opt/homebrew/opt/llvm/bin:$PATH"
export JOBS="${JOBS:-12}" CMAKE_BUILD_PARALLEL_LEVEL="${JOBS:-12}"
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME" "$CACHE/diagnostics/madeira"
CONFIGURATION="${MEWGENICS_CONFIGURATION:-Release}"
case "$CONFIGURATION" in
  Debug|Release) ;;
  *) echo "MEWGENICS_CONFIGURATION must be Debug or Release" >&2; exit 2 ;;
esac
APP="$CACHE/DerivedData-mewgenics-runtime/Build/Products/$CONFIGURATION-iphoneos/Mewgenics.app"
BUNDLE="${MEWGENICS_BUNDLE_ID:-org.example.mewgenics}"
GAME_DIR="${MEWGENICS_GAME_DIR:-$ROOT/Mewgenics-exe}"
device() { : "${DEVICE_UDID:?Set DEVICE_UDID to the connected physical iPad UDID}"; }
case "${1:-help}" in
  prepare)
    python3 "$ROOT/Scripts/prepare-madeira.py" "$CACHE"
    ;;
  mesa)
    python3 "$ROOT/Scripts/build-mesa-zink.py" "$CACHE"
    ;;
  native)
    cd "$SOURCE"
    bash build/ffmpeg/build.sh
    bash build/gnutls-ios/build.sh
    bash build/freetype-ios/build.sh
    mkdir -p wine/build-macos
    if [ ! -f wine/build-macos/config.status ]; then
      (cd wine/build-macos && PATH="$SOURCE/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin:$PATH" \
        ../configure --enable-archs=arm64ec --without-x --disable-tests --enable-winegstreamer)
    fi
    make -C wine/build-macos -j"$JOBS" include/all
    PATH="$SOURCE/toolchains/llvm-mingw-20260421-ucrt-macos-universal/bin:$PATH" \
      make -C wine/build-macos -j"$JOBS" \
      dlls/vulkan-1/arm64ec-windows/vulkan-1.dll \
      dlls/winevulkan/arm64ec-windows/winevulkan.dll
    cp wine/build-macos/dlls/vulkan-1/arm64ec-windows/vulkan-1.dll app/Madeira/arm64ec-windows/
    cp wine/build-macos/dlls/winevulkan/arm64ec-windows/winevulkan.dll app/Madeira/arm64ec-windows/
    bash build/ntdll-unix/build.sh
    bash build/wineserver/build.sh
    bash build/win32u-unix/build.sh
    bash build/fex-ios/build.sh
    cmake -S toolchains/llvm-project/llvm -B toolchains/llvm-host-build -G Ninja \
      -DCMAKE_BUILD_TYPE=Release -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS= \
      -DLLVM_INCLUDE_TESTS=OFF -DLLVM_ENABLE_ZLIB=OFF -DLLVM_ENABLE_ZSTD=OFF \
      -DLLVM_ENABLE_LIBXML2=OFF -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    cmake --build toolchains/llvm-host-build --target llvm-tblgen -j"$JOBS"
    cmake -S toolchains/llvm-project/llvm -B toolchains/llvm-ios-build -G Ninja \
      -DCMAKE_SYSTEM_NAME=iOS -DCMAKE_OSX_ARCHITECTURES=arm64 \
      -DCMAKE_OSX_SYSROOT=iphoneos -DCMAKE_OSX_DEPLOYMENT_TARGET=17.0 \
      -DCMAKE_BUILD_TYPE=Release -DLLVM_HOST_TRIPLE=arm64-apple-ios17.0 \
      -DLLVM_DEFAULT_TARGET_TRIPLE=arm64-apple-ios17.0 -DLLVM_TARGET_ARCH=host \
      -DLLVM_TARGETS_TO_BUILD= -DLLVM_ENABLE_PROJECTS= -DLLVM_BUILD_TOOLS=OFF \
      -DLLVM_INCLUDE_TOOLS=OFF -DLLVM_INCLUDE_TESTS=OFF -DLLVM_INCLUDE_BENCHMARKS=OFF \
      -DLLVM_INCLUDE_EXAMPLES=OFF -DLLVM_BUILD_UTILS=OFF -DLLVM_ENABLE_ZLIB=OFF \
      -DLLVM_ENABLE_ZSTD=OFF -DLLVM_ENABLE_LIBXML2=OFF \
      -DLLVM_TABLEGEN="$SOURCE/toolchains/llvm-host-build/bin/llvm-tblgen" \
      -DCMAKE_POLICY_VERSION_MINIMUM=3.5
    cmake --build toolchains/llvm-ios-build -j"$JOBS"
    bash build/dxmt-ios/build.sh
    bash build/stage-licenses.sh
    ;;
  build)
    : "${DEVELOPMENT_TEAM:?Set your Apple DEVELOPMENT_TEAM in .local/config.sh}"
    case "$DEVELOPMENT_TEAM:$BUNDLE" in *YOUR*|*yourname*|*:org.example.*) echo 'Set your own signing team and bundle ID' >&2; exit 2 ;; esac
    if [ -n "${MEWGENICS_APP_ICON:-}" ]; then
      python3 "$ROOT/Scripts/stage-app-icon.py" "$SOURCE/app/Madeira/Assets.xcassets" --icon "$MEWGENICS_APP_ICON"
    else
      python3 "$ROOT/Scripts/stage-app-icon.py" "$SOURCE/app/Madeira/Assets.xcassets"
    fi
    cd "$SOURCE"
    bash build/stage-licenses.sh
    DESTINATION=generic/platform=iOS
    if [ -n "${DEVICE_UDID:-}" ]; then DESTINATION="id=$DEVICE_UDID"; fi
    xcodebuild -project app/Madeira.xcodeproj -scheme Madeira -configuration "$CONFIGURATION" \
      -destination "$DESTINATION" \
      -derivedDataPath "$CACHE/DerivedData-mewgenics-runtime" \
      DEVELOPMENT_TEAM="$DEVELOPMENT_TEAM" PRODUCT_BUNDLE_IDENTIFIER="$BUNDLE" \
      -allowProvisioningUpdates -jobs "$JOBS" build
    codesign --verify --deep --strict "$APP"
    python3 - "$APP" <<'PY'
import plistlib, subprocess, sys
result = subprocess.run(['codesign', '-d', '--entitlements', ':-', sys.argv[1]],
                        check=True, capture_output=True)
entitlements = plistlib.loads(result.stdout)
for key in ('get-task-allow', 'com.apple.developer.kernel.increased-memory-limit'):
    if entitlements.get(key) is not True:
        raise SystemExit(f'Missing required signed entitlement: {key}')
print('Verified development JIT access and increased-memory entitlement.')
PY
    ;;
  install)
    device
    xcrun devicectl device install app --device "$DEVICE_UDID" "$APP"
    ;;
  diagnostics)
    device
    case "${2:-}" in
      off|stats|full) ;;
      *) echo "Usage: $0 diagnostics {off|stats|full}" >&2; exit 2 ;;
    esac
    # Stage from the current device config, preserving all graphics, input,
    # memory and save-path settings. Diagnostic switches apply next launch.
    STAMP="$(date +%Y%m%d-%H%M%S)-$$"
    BEFORE="$CACHE/diagnostics/madeira/diagnostics-$STAMP-before.cfg"
    AFTER="$CACHE/diagnostics/madeira/diagnostics-$STAMP-$2.cfg"
    xcrun devicectl device copy from --device "$DEVICE_UDID" \
      --source Documents/madeira.cfg --destination "$BEFORE" \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    python3 "$ROOT/Scripts/configure-runtime-diagnostics.py" "$BEFORE" "$AFTER" "$2"
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$AFTER" --destination Documents/madeira.cfg \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    echo "Diagnostics configured for the next launch: $2"
    ;;
  game)
    device
    python3 "$ROOT/Scripts/build-mesa-zink.py" "$CACHE" --check
    # Validate before uploading anything; the original installation is untouched.
    test -f "$GAME_DIR/resources.gpak" || { echo 'Missing resources.gpak in MEWGENICS_GAME_DIR' >&2; exit 2; }
    python3 "$ROOT/Scripts/patch-game-pools.py" "$GAME_DIR/Mewgenics.exe" "$CACHE/patched-game/Mewgenics.exe"
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$GAME_DIR" --destination Documents/wine/drive_c/Mewgenics \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$CACHE/patched-game/Mewgenics.exe" \
      --destination Documents/wine/drive_c/Mewgenics/Mewgenics.exe \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$CACHE/packages/mesa-zink-patched/x64/opengl32.dll" \
      --source "$CACHE/packages/mesa-zink-patched/x64/libgallium_wgl.dll" \
      --destination Documents/wine/drive_c/Mewgenics \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    ;;
  configure)
    device
    python3 "$ROOT/Scripts/configure-device.py" --device "$DEVICE_UDID" --bundle "$BUNDLE" --cache "$CACHE"
    ;;
  renderer)
    device
    case "${2:-}" in
      zink)
        python3 "$ROOT/Scripts/build-mesa-zink.py" "$CACHE" --check
        MESA_PACKAGE=mesa-zink-patched
        ;;
      llvmpipe) MESA_PACKAGE=mesa ;;
      *) echo "Usage: $0 renderer {zink|llvmpipe}" >&2; exit 2 ;;
    esac
    # Preserve all other runtime settings and game saves. Switching renderer
    # also switches the matching Mesa version; copying only a config is unsafe.
    xcrun devicectl device copy from --device "$DEVICE_UDID" \
      --source Documents/madeira.cfg --destination "$TMPDIR/renderer-before.cfg" \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    python3 - "$TMPDIR/renderer-before.cfg" "$TMPDIR/renderer-next.cfg" "$2" <<'PY'
import pathlib, sys
source, target, renderer = sys.argv[1:]
values = {"env.GALLIUM_DRIVER": renderer, "env.WINEDLLOVERRIDES": "opengl32=n"}
remove = {"env.MESA_GL_VERSION_OVERRIDE", "env.MESA_GLSL_VERSION_OVERRIDE",
          "env.MESA_DEBUG", "env.MESA_LOG_FILE", "env.ZINK_DEBUG"}
if renderer == "zink":
    values.update({"env.MESA_GL_VERSION_OVERRIDE": "4.4", "env.MESA_GLSL_VERSION_OVERRIDE": "440"})
else:
    values.update({"env.LP_NUM_THREADS": "4", "env.LP_NATIVE_VECTOR_WIDTH": "128"})
lines = [line for line in pathlib.Path(source).read_text().splitlines()
         if line.split("=", 1)[0].strip() not in remove | values.keys()]
lines.extend(f"{key} = {value}" for key, value in values.items())
pathlib.Path(target).write_text("\n".join(lines) + "\n")
PY
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$CACHE/packages/$MESA_PACKAGE/x64/opengl32.dll" \
      --source "$CACHE/packages/$MESA_PACKAGE/x64/libgallium_wgl.dll" \
      --destination Documents/wine/drive_c/Mewgenics \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    xcrun devicectl device copy to --device "$DEVICE_UDID" \
      --source "$TMPDIR/renderer-next.cfg" --destination Documents/madeira.cfg \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    echo "Renderer configured. Restart Mewgenics to apply."
    ;;
  launch)
    device
    xcrun devicectl device process launch --device "$DEVICE_UDID" "$BUNDLE"
    ;;
  log)
    device
    xcrun devicectl device copy from --device "$DEVICE_UDID" \
      --source Documents/madeira-log.txt \
      --destination "$CACHE/diagnostics/madeira/device-$(date +%Y%m%d-%H%M%S).log" \
      --domain-type appDataContainer --domain-identifier "$BUNDLE"
    ;;
  *)
    echo "Usage: $0 {prepare|mesa|native|build|install|game|configure|diagnostics off|diagnostics stats|diagnostics full|renderer zink|renderer llvmpipe|launch|log}"
    echo "Copy config.example.sh to .local/config.sh; set your own paths, signing and device."
    echo "Release builds are default; MEWGENICS_CONFIGURATION=Debug selects the diagnostic build."
    ;;
esac
