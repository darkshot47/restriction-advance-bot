# TDLib — direct mode's engine

Vmore's direct mode runs a real Telegram client **on the phone** (TDLib), so
downloads ride *Telegram → phone* and uploads ride *phone → Telegram* — the
Render host moves zero media bytes in either direction.  Everything here is
derived from the upstream **tdlib/td** repository (Boost Software License) at
the single commit pinned in [`TDLIB_COMMIT`](TDLIB_COMMIT).

## What lives here (and what deliberately does not)

| Path | In git? | Why |
| --- | --- | --- |
| `TDLIB_COMMIT` | ✅ | The one commit everything is generated from — Java bindings and the native lib are always the same TDLib. |
| `build.sh` | ✅ | The whole pipeline, adapted from upstream's `example/android` scripts (2 phone ABIs, no PHP pass). |
| `td/` | ❌ | The cloned upstream checkout (re-cloned whenever the pinned commit changes). |
| `third-party/` | ❌ | Static OpenSSL for Android, built from the official sources. |
| `android/app/src/main/java/org/drinkless/` | ❌ | `TdApi.java` + `Client.java`, generated/copied here by `build.sh` right before Gradle runs. |
| `android/app/src/main/jniLibs/` | ❌ | `libtdjni.so` per ABI, copied here by `build.sh` right before Gradle runs. |

The CI job (`.github/workflows/android.yml`) runs `bash android/tdlib/build.sh
"$ANDROID_SDK_ROOT"` before the Gradle build, caches `td/` and `third-party/`
keyed by the pinned commit, and verifies the APK really contains
`libtdjni.so` for `arm64-v8a` and `armeabi-v7a`.

## Local rebuild

```bash
sudo apt-get install gperf ninja-build   # plus a JDK and a C++ toolchain
sdkmanager "ndk;23.2.8568313" "cmake;3.22.1"
bash android/tdlib/build.sh "$ANDROID_SDK_ROOT"
gradle --project-dir android assembleDebug
```

Notes:

* The host generate step (the TL → Java code generator) is Linux x86_64
  only — that is what CI uses, and what the build assumes.
* No PHP is needed: the upstream Javadoc/IntDef pass is skipped on purpose,
  so the generated `TdApi.java` needs no androidx annotation stubs and the
  app stays free of third-party Java dependencies. CMake would enable that
  pass automatically whenever `php` is on `PATH` (the GitHub runner has it),
  so `build.sh` passes `-DPHP_EXECUTABLE=` to turn it off, and it fails fast
  if `TdApi.java` still mentions `androidx`.
* Cache-size sanity: a full from-scratch build is heavy (OpenSSL + TDLib for
  two ABIs), the cache limits it to one such run per pinned commit.
