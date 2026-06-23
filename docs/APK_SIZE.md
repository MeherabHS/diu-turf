# Android APK size guide — DIU Turf

Current baseline: **~90 MB** universal/local release APK (before optimizations).

Target: **50–70 MB** per installable APK where safely achievable.

---

## Investigation summary

| Factor | Finding |
|--------|---------|
| **Dev client** | `expo-dev-client` is **not** installed — release builds are standalone, not dev-client bloat. |
| **R8 / ProGuard** | Was **disabled** (`android.enableMinifyInReleaseBuilds=false`). Now **enabled** for release. |
| **Resource shrinking** | Was **disabled**. Now **enabled** (requires minify). |
| **ABIs** | `reactNativeArchitectures=x86_64` in `gradle.properties` is for **Windows emulator debug only**. A release built without overriding this produces an **x86_64 APK that will not run on phones**. |
| **Universal vs split** | A fat APK with all 4 ABIs (arm64, armeabi, x86, x86_64) can exceed **120 MB**. Device builds should use **ARM only**. |
| **Dependencies** | Typical Expo SDK 54 stack: New Architecture, Hermes, Reanimated, Worklets, Google Sign-In, Notifications, WebView — baseline **~40–60 MB** per ABI after optimization. |
| **Assets** | App icons/splash referenced in `app.json`; no unusually large bundled image assets found. |

---

## Changes applied (safe)

1. **`android/gradle.properties`**
   - `android.enableMinifyInReleaseBuilds=true` — R8 bytecode shrinking (~5–15 MB)
   - `android.enableShrinkResourcesInReleaseBuilds=true` — removes unused resources (~1–5 MB)
   - `android.enableBundleCompression=true` — compresses JS bundle in APK (~0.5–2 MB)

2. **`android/app/proguard-rules.pro`**
   - Keep rules for React Native, Hermes, Expo, Reanimated/Worklets, Google Sign-In, notifications, WebView.

3. **`android/app/build.gradle`**
   - Optional **ABI splits** (off by default for debug): per-ABI APKs when `-Pandroid.enableAbiSplits=true`.

4. **`eas.json`**
   - `preview` and `production` profiles build **ARM APKs** with splits and production API URL.

5. **`package.json` scripts**
   - `android:release` — split ARM APKs for distribution
   - `android:release:arm64` — single smallest APK for modern phones

---

## Expected sizes (estimates)

| Build | Approx. size | Notes |
|-------|--------------|-------|
| Before (unoptimized, multi-ABI or x86_64) | ~90 MB | Measured baseline |
| After R8 + shrink, single `arm64-v8a` | **~48–58 MB** | Best for modern phones |
| After R8 + shrink, split `arm64-v8a` APK | **~48–58 MB** | Same, via ABI split output |
| After R8 + shrink, split `armeabi-v7a` APK | **~45–55 MB** | Older 32-bit devices |
| Universal ARM (arm64 + armeabi, no split) | **~65–75 MB** | Still within target |
| Universal all 4 ABIs | **~90–120 MB** | Avoid for sideload distribution |

**Honest ceiling:** A full-featured Expo SDK 54 app with New Architecture, Google Sign-In, push notifications, and navigation is unlikely to go below **~45 MB** per ABI without removing features or switching to AAB + Play App Signing (which serves one ABI per device).

The **50–70 MB target is achievable** for a **single arm64-v8a release APK** or **per-ABI split APKs**. A universal ARM APK may land around **65–75 MB**.

---

## Rebuild commands

### Local release (recommended for phones)

```powershell
cd frontend

# Split ARM APKs (arm64 + armeabi) — pick the right one for the device
yarn android:release

# Smallest single APK (arm64-v8a only, covers most phones since ~2019)
yarn android:release:arm64
```

Output paths (with ABI splits enabled):

```
frontend/android/app/build/outputs/apk/release/app-arm64-v8a-release.apk
frontend/android/app/build/outputs/apk/release/app-armeabi-v7a-release.apk
```

Single-ABI output (no splits):

```
frontend/android/app/build/outputs/apk/release/app-release.apk
```

### Emulator debug (unchanged)

```powershell
cd frontend
npx expo run:android
# Uses reactNativeArchitectures=x86_64 from gradle.properties
```

### EAS cloud build (distribution)

```powershell
cd frontend
$env:EAS_NO_VCS = "1"
npx eas build -p android --profile preview
npx eas build:download -p android
```

EAS `preview` profile sets production API URL, ARM architectures, and ABI splits via `eas.json`.

---

## What we did NOT change (intentionally)

- **Google Sign-In** — kept; required for auth
- **Push notifications** — kept
- **New Architecture** — kept (`newArchEnabled=true`); disabling would save some native size but risks compatibility issues
- **Hermes** — kept (smaller than JSC)
- **expo-dev-client** — not present; no action needed
- **Animated WebP** — already disabled (`expo.webp.animated=false`)

---

## Troubleshooting

### Release crash after enabling R8

If OAuth or notifications break at runtime, check logcat for `ClassNotFoundException` and add targeted `-keep` rules to `android/app/proguard-rules.pro`.

### APK won't install on phone

You likely built for **x86_64** (emulator default). Use `yarn android:release:arm64` or pass `-PreactNativeArchitectures=arm64-v8a`.

### Still ~90 MB

Confirm you are installing the **arm64 split APK**, not a universal multi-ABI build. Run:

```powershell
# List APK contents / size
Get-ChildItem frontend/android/app/build/outputs/apk/release/*.apk | Select-Object Name, @{N='MB';E={[math]::Round($_.Length/1MB,1)}}
```

---

## Files changed

- `frontend/android/gradle.properties`
- `frontend/android/app/build.gradle`
- `frontend/android/app/proguard-rules.pro`
- `frontend/eas.json` (new)
- `frontend/package.json` (release scripts)
- `docs/APK_SIZE.md` (this file)
