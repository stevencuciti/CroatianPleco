#!/usr/bin/env bash
# Cross-compile libhrspeak.so (eSpeak NG + JNI bridge) for each Android ABI.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SDK="$ROOT/toolchain/android-sdk"
NDK="$SDK/ndk/28.2.13676358"
CMAKE_BIN="$SDK/cmake/3.31.6/bin"
ESPEAK_SRC="$ROOT/third_party/espeak-src/espeak-ng-1.52.0"
OUT="$ROOT/build/native"
for ABI in ${ABIS:-arm64-v8a armeabi-v7a x86_64}; do
  B="$OUT/obj/$ABI"
  mkdir -p "$B" "$OUT/lib/$ABI"
  "$CMAKE_BIN/cmake.exe" -S "$ROOT/app/jni" -B "$B" -G Ninja \
    -DCMAKE_MAKE_PROGRAM="$CMAKE_BIN/ninja.exe" \
    -DCMAKE_TOOLCHAIN_FILE="$NDK/build/cmake/android.toolchain.cmake" \
    -DANDROID_ABI="$ABI" -DANDROID_PLATFORM=android-24 \
    -DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON \
    -DCMAKE_BUILD_TYPE=Release \
    -DESPEAK_SRC="$ESPEAK_SRC" > "$B/configure.log" 2>&1 || { tail -40 "$B/configure.log"; exit 1; }
  "$CMAKE_BIN/cmake.exe" --build "$B" --target hrspeak > "$B/build.log" 2>&1 || { tail -60 "$B/build.log"; exit 1; }
  cp "$B/libhrspeak.so" "$OUT/lib/$ABI/"
  echo "$ABI: $(stat -c %s "$OUT/lib/$ABI/libhrspeak.so") bytes"
done
