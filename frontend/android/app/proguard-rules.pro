# DIU Turf — release ProGuard/R8 rules (React Native + Expo + native modules)

-keepattributes SourceFile,LineNumberTable
-keepattributes *Annotation*
-keepattributes Signature
-keepattributes InnerClasses
-keepattributes EnclosingMethod

# React Native / Hermes (libraries also ship consumer ProGuard rules)
-keep class com.facebook.react.** { *; }
-keep class com.facebook.hermes.** { *; }
-keep class com.facebook.jni.** { *; }
-keep class com.facebook.soloader.** { *; }
-keepclassmembers class * { native <methods>; }

# Expo modules
-keep class expo.modules.** { *; }
-keepnames class * implements expo.modules.core.interfaces.Package
-keepnames class * extends expo.modules.core.BasePackage
-keepclassmembers public class expo.modules.ExpoModulesPackageList { public *; }
-keepclassmembers public class expo.modules.ReactActivityDelegateWrapper {
  protected com.facebook.react.ReactDelegate getReactDelegate();
}

# react-native-reanimated + worklets
-keep class com.swmansion.reanimated.** { *; }
-keep class com.swmansion.worklets.** { *; }
-keep class com.facebook.react.turbomodule.** { *; }
-keep class com.facebook.react.fabric.** { *; }

# Google Sign-In / Play Services
-keep class com.reactnativegooglesignin.** { *; }
-keep class com.google.android.gms.** { *; }
-dontwarn com.google.android.gms.**

# Push notifications
-keep class expo.modules.notifications.** { *; }

# WebView
-keepclassmembers class * extends android.webkit.WebViewClient {
    public void *(android.webkit.WebView, java.lang.String, android.graphics.Bitmap);
    public boolean *(android.webkit.WebView, java.lang.String);
}
-keepclassmembers class * extends android.webkit.WebChromeClient {
    public void *(android.webkit.WebView, java.lang.String);
}

# OkHttp / networking (used by RN and Google SDKs)
-dontwarn okhttp3.**
-dontwarn okio.**
-dontwarn javax.annotation.**
