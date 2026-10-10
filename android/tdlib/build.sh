#!/usr/bin/env bash
#
# Build the TDLib pieces Vmore's direct mode needs, reproducibly:
#
#   • org/drinkless/tdlib/{Client.java,TdApi.java} → android/app/src/main/java/org/drinkless/tdlib/
#   • libtdjni.so                                  → android/app/src/main/jniLibs/<abi>/
#
# Everything is derived from github.com/tdlib/td at the commit pinned in
# TDLIB_COMMIT — the Java bindings the app compiles against and the native
# library it ships are guaranteed to speak the same TDLib.
#
# Adapted from TDLib's own example/android scripts (tdlib/td, Boost license),
# trimmed to the paths Vmore uses: host generate → 2 phone ABIs, no PHP pass
# (the generated TdApi.java then needs no androidx annotation stubs).
#
# Requirements on the host: bash, git, a C++ toolchain, cmake, gperf, perl,
# curl or wget — and an Android SDK with the NDK below plus cmake 3.22.1.
#
#   bash android/tdlib/build.sh "$ANDROID_SDK_ROOT"
#
# Env knobs: TDLIB_NDK_VERSION, TDLIB_ABIS, OPENSSL_VERSION, TDLIB_JOBS.

set -euo pipefail
cd "$(dirname "$0")"

#: Name the exact failing command. A "::error::" line becomes a job annotation,
#: so the reason is visible through the API even when the raw step log is not.
trap 'rc=$?; echo "::error::android/tdlib/build.sh failed (exit $rc) at line $LINENO: $BASH_COMMAND"' ERR

TDLIB_COMMIT="$(tr -d '[:space:]' < TDLIB_COMMIT)"
ANDROID_SDK_ROOT="${1:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-}}}"
TDLIB_NDK_VERSION="${TDLIB_NDK_VERSION:-23.2.8568313}"
TDLIB_ABIS="${TDLIB_ABIS:-arm64-v8a armeabi-v7a}"
OPENSSL_VERSION="${OPENSSL_VERSION:-OpenSSL_1_1_1w}"
TDLIB_JOBS="${TDLIB_JOBS:-$(nproc 2>/dev/null || echo 4)}"

#: Android API floors per ABI. OpenSSL is built against these, and its ARM
#: capability probe calls getauxval (only declared from API 18 on), so libtdjni
#: must link against the same floor. Linking it at a lower platform (it was
#: android-16) fails with "undefined symbol: getauxval" on armeabi-v7a.
ANDROID_API32=19     # armeabi-v7a floor (NDK 23+)
ANDROID_API64=21     # 64-bit minimum

if [ -z "$ANDROID_SDK_ROOT" ] || [ ! -d "$ANDROID_SDK_ROOT" ]; then
    echo "::error::pass the Android SDK root as the first argument (or set ANDROID_SDK_ROOT/ANDROID_HOME)"
    exit 1
fi
ANDROID_SDK_ROOT="$(cd "$ANDROID_SDK_ROOT" && pwd -P)"
ANDROID_NDK_ROOT="$ANDROID_SDK_ROOT/ndk/$TDLIB_NDK_VERSION"
if [ ! -d "$ANDROID_NDK_ROOT" ]; then
    echo "::error::NDK $TDLIB_NDK_VERSION not found at $ANDROID_NDK_ROOT"
    echo "  install it with: sdkmanager 'ndk;$TDLIB_NDK_VERSION'"
    exit 1
fi
command -v gperf >/dev/null 2>&1 || { echo "::error::gperf not found — install it (apt-get/brew install gperf)"; exit 1; }
command -v g++   >/dev/null 2>&1 || { echo "::error::g++ not found"; exit 1; }

REPO_ROOT="$(cd ../.. && pwd -P)"
APP_JAVA="$REPO_ROOT/android/app/src/main/java/org/drinkless/tdlib"
APP_JNILIBS="$REPO_ROOT/android/app/src/main/jniLibs"
WGET="$(command -v wget >/dev/null 2>&1 && echo 'wget -q' || echo 'curl -sfLO')"

# The SDK's own cmake is the version TDLib's Android build files are tested with.
SDK_CMAKE="$ANDROID_SDK_ROOT/cmake/3.22.1/bin"
if [ -d "$SDK_CMAKE" ]; then
    PATH="$SDK_CMAKE:$PATH"
fi

# ── 1. TDLib sources at the pinned commit ────────────────────────────────────
if [ ! -d td/.git ] || [ "$(git -C td rev-parse HEAD 2>/dev/null || true)" != "$TDLIB_COMMIT" ]; then
    rm -rf td
    echo ":: Cloning github.com/tdlib/td @ $TDLIB_COMMIT (blob-less, single commit)"
    git clone -q --filter=blob:none --no-checkout https://github.com/tdlib/td.git td
    git -C td checkout -q "$TDLIB_COMMIT"
fi

# ── 2. Java bindings (host build, generation only) ──────────────────────────
if [ ! -s td/example/android/org/drinkless/tdlib/TdApi.java ]; then
    echo ":: Generating the TDLib Java API (prepare_cross_compiling + tl_generate_java)"
    #: PHP_EXECUTABLE= is not optional. CMake's td/generate/CMakeLists.txt runs
    #: find_program(PHP_EXECUTABLE php), and the GitHub runner ships PHP, so
    #: without this the upstream Javadoc + AddIntDef passes run and inject
    #: "import androidx.annotation.{IntDef,Nullable}" into TdApi.java. The app
    #: deliberately has no androidx.annotation dependency, so javac fails there.
    #: An empty cache value makes CMake skip the PHP passes (verified: no
    #: androidx lines in the output). The guard below keeps this from regressing.
    cmake -S td/example/android -B td/example/android/build-native-Java \
        -DTD_GENERATE_SOURCE_FILES=ON -DPHP_EXECUTABLE=
    cmake --build td/example/android/build-native-Java -j "$TDLIB_JOBS"
    cmake --build td/example/android/build-native-Java --target tl_generate_java
fi
[ -s td/example/android/org/drinkless/tdlib/TdApi.java ] || {
    echo "::error::TdApi.java was not generated"; exit 1; }
mkdir -p "$APP_JAVA"
cp -f td/example/android/org/drinkless/tdlib/TdApi.java "$APP_JAVA/TdApi.java"
cp -f td/example/java/org/drinkless/tdlib/Client.java   "$APP_JAVA/Client.java"
if grep -q 'androidx' "$APP_JAVA/TdApi.java"; then
    echo "::error::TdApi.java references androidx.annotation (PHP passes ran?). The app has no androidx dependency."
    echo "::error::Delete android/tdlib/td (stale generated sources) and rebuild."
    exit 1
fi
echo ":: Java bindings ready ($(wc -l < "$APP_JAVA/TdApi.java") lines of TdApi.java)"

# ── 3. OpenSSL for Android (static, once) ────────────────────────────────────
export ANDROID_NDK_ROOT ANDROID_NDK_HOME="$ANDROID_NDK_ROOT"
TOOLCHAIN_BIN="$ANDROID_NDK_ROOT/toolchains/llvm/prebuilt/linux-x86_64/bin"
PATH="$TOOLCHAIN_BIN:$PATH"

if [ ! -f third-party/openssl/arm64-v8a/lib/libcrypto.a ]; then
    echo ":: Building OpenSSL $OPENSSL_VERSION for: $TDLIB_ABIS"
    rm -rf third-party/openssl "openssl-$OPENSSL_VERSION" "$OPENSSL_VERSION.tar.gz"
    mkdir -p third-party/openssl
    OPENSSL_INSTALL_DIR="$(cd third-party/openssl && pwd -P)"
    $WGET "https://github.com/openssl/openssl/archive/refs/tags/$OPENSSL_VERSION.tar.gz"
    tar xzf "$OPENSSL_VERSION.tar.gz"
    rm "$OPENSSL_VERSION.tar.gz"
    cd "openssl-$OPENSSL_VERSION"

    for ABI in $TDLIB_ABIS; do
        case "$ABI" in
            armeabi-v7a) CONFIG_ABI="android-arm";  API=$ANDROID_API32 ;;
            arm64-v8a)   CONFIG_ABI="android-arm64"; API=$ANDROID_API64 ;;
            x86)         CONFIG_ABI="android-x86";  API=$ANDROID_API32 ;;
            x86_64)      CONFIG_ABI="android-x86_64"; API=$ANDROID_API64 ;;
            *) echo "::error::unknown ABI $ABI"; exit 1 ;;
        esac
        ARCH_FLAG=""
        [ "$ABI" = "armeabi-v7a" ] && ARCH_FLAG="-D__ARM_MAX_ARCH__=8"
        LD_FLAG=""
        [ "$API" = "$ANDROID_API64" ] && LD_FLAG="-Wl,-z,max-page-size=16384"
        LDFLAGS=$LD_FLAG ./Configure "$CONFIG_ABI" no-shared \
            -U__ANDROID_API__ -D__ANDROID_API__=$API $ARCH_FLAG
        sed -i.bak 's/-O3/-O3 -ffunction-sections -fdata-sections/g' Makefile
        make depend -s
        make -j"$TDLIB_JOBS" -s
        mkdir -p "$OPENSSL_INSTALL_DIR/$ABI/lib"
        cp libcrypto.a libssl.a "$OPENSSL_INSTALL_DIR/$ABI/lib/"
        cp -r include "$OPENSSL_INSTALL_DIR/$ABI/"
        make distclean
    done
    cd ..
    rm -rf "./openssl-$OPENSSL_VERSION"
    echo ":: OpenSSL ready"
fi

# ── 4. libtdjni.so per ABI ───────────────────────────────────────────────────
for ABI in $TDLIB_ABIS; do
    BUILD_DIR="td/example/android/build-$ABI-Java"
    case "$ABI" in
        arm64-v8a|x86_64) PLATFORM_API=$ANDROID_API64 ;;
        *)                PLATFORM_API=$ANDROID_API32 ;;
    esac
    if [ ! -f td/tdlib/libs/$ABI/libtdjni.so ]; then
        echo ":: Building libtdjni.so for $ABI (android-$PLATFORM_API, same floor as its OpenSSL)"
        cmake -S td/example/android -B "$BUILD_DIR" \
            -DCMAKE_TOOLCHAIN_FILE="$ANDROID_NDK_ROOT/build/cmake/android.toolchain.cmake" \
            -DOPENSSL_ROOT_DIR="$(pwd -P)/third-party/openssl/$ABI" \
            -DANDROID_ABI="$ABI" -DANDROID_STL="c++_static" -DANDROID_PLATFORM="android-$PLATFORM_API" \
            -DCMAKE_BUILD_TYPE=RelWithDebInfo -GNinja
        cmake --build "$BUILD_DIR" --target tdjni -j "$TDLIB_JOBS"
        mkdir -p td/tdlib/libs/"$ABI"
        cp -p "$BUILD_DIR"/libtd*.so* td/tdlib/libs/"$ABI"/
    fi
    mkdir -p "$APP_JNILIBS/$ABI"
    cp -f td/tdlib/libs/"$ABI"/libtdjni.so "$APP_JNILIBS/$ABI/libtdjni.so"
    echo ":: packaged $APP_JNILIBS/$ABI/libtdjni.so ($(du -h "$APP_JNILIBS/$ABI/libtdjni.so" | cut -f1))"
done

echo ":: TDLib direct mode build complete."
