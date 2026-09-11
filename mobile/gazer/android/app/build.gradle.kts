import org.jetbrains.kotlin.gradle.dsl.JvmTarget
import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("dev.flutter.flutter-gradle-plugin")
    id("org.jlleitschuh.gradle.ktlint")
    jacoco
}

// AGP 9.1.0's DEFAULT (newDsl-decorated) ApplicationExtension crashes
// dev.flutter.flutter-gradle-plugin: `ApplicationExtensionImpl$AgpDecorated_Decorated cannot be
// cast to AbstractAppExtension` at com.flutter.gradle.FlutterPlugin.addFlutterTasks -- a confirmed,
// still-open upstream bug (flutter/flutter#192111; Flutter team, 2026-09-01: "AGP 9.1.0 ... ahead of
// what 3.47.2 officially supports"). Worked around by forcing `android.newDsl=false` and
// `android.builtInKotlin=false` in android/gradle.properties, which restores AGP's classic
// (non-decorated) extension that Flutter's plugin expects -- but that means built-in Kotlin is OFF,
// so the classic `org.jetbrains.kotlin.android` plugin (above) is required again, not the
// AGP-9-built-in-Kotlin DSL. Do not remove either half of this workaround without re-verifying
// against flutter/flutter#192111's resolution -- do not downgrade AGP/Kotlin to dodge it.
//
// Separately, under this Kotlin/AGP combination `android.kotlinOptions { jvmTarget = ... }` is a
// hard compile ERROR (not just a deprecation warning): "'var jvmTarget: String' is deprecated.
// Please migrate to the compilerOptions DSL" (https://kotl.in/u1r8ln). Replaced with the top-level
// `kotlin { compilerOptions { jvmTarget = ... } }` block below, per that migration guide.

kotlin {
    compilerOptions {
        jvmTarget.set(JvmTarget.JVM_17)
    }
}

// Release signing. mobile/gazer/android/key.properties is never committed (see .gitignore) --
// it is either written by a developer for a local signed build (Task 25 Step 8c) or by CI from
// the ANDROID_UPLOAD_KEY_STORE_B64/ANDROID_UPLOAD_KEY_STORE_PASSWORD/ANDROID_UPLOAD_KEY_ALIAS/
// ANDROID_UPLOAD_KEY_ALIAS_PASSWORD secrets (see .github/workflows/gazer-mobile.yml `build` job)
// and deleted again in an `if: always()` step immediately after the build. storeFile is
// resolved with rootProject.file(...) because key.properties lives at android/key.properties
// (the Gradle root project for this module), not android/app/.
val keyPropsFile = rootProject.file("key.properties")
val keyProps = Properties()
if (keyPropsFile.exists()) {
    keyPropsFile.inputStream().use { keyProps.load(it) }
}

android {
    namespace = "io.waddlebot.gazer"
    compileSdk = 36
    ndkVersion = "28.2.13676358"

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    defaultConfig {
        applicationId = "io.waddlebot.gazer"
        minSdk = 29
        targetSdk = 36
        versionCode = flutter.versionCode
        versionName = flutter.versionName
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        // This is the Play App Signing *upload* key, not the app signing key -- Google Play
        // holds the real app signing key and re-signs the app for distribution; this key only
        // proves uploads to Play's ingestion come from PenguinTech. It is recoverable if lost
        // (Play Console upload-key-reset flow), unlike the app signing key.
        if (keyPropsFile.exists()) {
            create("upload") {
                storeFile = rootProject.file(keyProps.getProperty("storeFile"))
                storePassword = keyProps.getProperty("storePassword")
                keyAlias = keyProps.getProperty("keyAlias")
                keyPassword = keyProps.getProperty("keyPassword")
            }
        }
    }

    buildTypes {
        release {
            // Tag builds (gazer-v*) must never ship debug-signed -- fail closed before any
            // signingConfig decision below. See .github/workflows/gazer-mobile.yml `build` job,
            // which sets GAZER_REQUIRE_SIGNING=1 only when github.ref starts with refs/tags/gazer-v.
            if (System.getenv("GAZER_REQUIRE_SIGNING") == "1" && !keyPropsFile.exists()) {
                throw GradleException("GAZER_REQUIRE_SIGNING=1 but key.properties is missing")
            }
            if (keyPropsFile.exists()) {
                signingConfig = signingConfigs.getByName("upload")
            } else {
                signingConfig = signingConfigs.getByName("debug")
                // Single, unmistakable line -- asserted by Task 25 Step 8a to appear exactly
                // once per `flutter build`/Gradle invocation of this buildType.
                println("WARNING: release build is debug-signed (no key.properties)")
            }
        }
        debug {
            enableUnitTestCoverage = true
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            isReturnDefaultValues = true
        }
    }
}

flutter {
    source = "../.."
}

jacoco {
    toolVersion = libs.versions.jacoco.get()
}

// Pigeon-generated Kotlin (android/app/src/main/kotlin/io/waddlebot/gazer/pigeon/) is not
// hand-maintained: its toString() overrides come out of the Pigeon 28.0.0 Kotlin template as a
// single line per class and can exceed ktlint's max-line-length (140) rule, which ktlintFormat
// cannot auto-correct (wrapping a string-template expression across lines is a semantic choice
// the formatter won't make for you). Regenerating via `make mobile-codegen` is expected to
// reproduce this on every run, so linting this directory would fail on generated code no author
// ever hand-edits. Excluded from ktlint entirely -- mirrors the JaCoCo "**/pigeon/**" exclusion
// in the jacocoTestReport task below for the same reason (generated code, not authored code).
ktlint {
    filter {
        exclude { it.file.path.contains("/pigeon/") }
    }
}

dependencies {
    implementation(libs.rootencoder.library)
    implementation(libs.kotlinx.coroutines.core)
    implementation(libs.kotlinx.coroutines.android)

    testImplementation(libs.junit.jupiter)
    testRuntimeOnly(libs.junit.platform.launcher)
    testImplementation(libs.mockk)

    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.junit4)
}

// Flutter's own bundled :integration_test module (pulled in because pubspec.yaml's
// dev_dependencies declares `integration_test: sdk: flutter`, per spec) declares
// androidx.test:runner/rules and espresso-core as MAIN (non-test) dependencies, which drags
// androidx.test:runner 1.3.0 / androidx.test:rules 1.2.0 / junit:junit 4.12 into :app's own
// debugRuntimeClasspath. AGP's cross-variant "consistent resolution" then forces
// debugAndroidTestRuntimeClasspath to match those same old versions, conflicting with this
// module's own newer androidTestImplementation pins above (from gradle/libs.versions.toml) and
// failing with "Cannot find a version of ... that satisfies the version constraints". Forcing
// resolution to this module's pinned versions everywhere resolves the conflict; all three are
// backward-compatible newer releases of the same libraries integration_test itself requests a
// floor of (>=1.2+, >=1.2.0, junit 4.12), so forcing upward is safe.
configurations.all {
    resolutionStrategy {
        force(
            libs.androidx.test.runner
                .get(),
            libs.androidx.test.rules
                .get(),
            libs.junit4.get(),
        )
    }
}

// dev.flutter.flutter-gradle-plugin's own `copyFlutterAssetsDebug` task (which
// `packageDebugUnitTestForUnitTest` consumes -- unit tests package the merged debug assets) isn't
// wired with an explicit Gradle task dependency, which AGP 9.1.0's stricter implicit-dependency
// validation now treats as a build-breaking error rather than a warning: "Task
// ':app:packageDebugUnitTestForUnitTest' uses this output of task ':app:copyFlutterAssetsDebug'
// without declaring an explicit or implicit dependency." Declaring it here is Gradle's own
// suggested solution #2 (Task#dependsOn) for this exact validation problem -- applied from this
// build script since flutter-gradle-plugin's own task wiring isn't ours to edit.
tasks.matching { it.name == "packageDebugUnitTestForUnitTest" }.configureEach {
    dependsOn("copyFlutterAssetsDebug")
}

tasks.withType<Test> {
    useJUnitPlatform()
}

// NOTE: android/build.gradle.kts (Step 9 above) redirects the *root* buildDir to
// mobile/gazer/build, so this module's normal Gradle outputs (compiled classes, .exec/.ec
// coverage data) land under mobile/gazer/build/app, not android/app/build. The JaCoCo XML/HTML
// *report* output below is deliberately pinned to `layout.projectDirectory` (NOT
// `layout.buildDirectory`, which is the redirected one) so it lands at the fixed, predictable
// path `android/app/build/reports/jacoco/jacocoTestReport/...` that `make mobile-test-android`
// (repo-root Makefile), `scripts/coverage_gate.sh`'s jacoco-mode default, the CI `android-unit`
// job (Task 3), and Task 17 Step 7's existence check all read from -- every one of those must
// keep agreeing with this exact path if it is ever changed here.
tasks.register<JacocoReport>("jacocoTestReport") {
    dependsOn("testDebugUnitTest")
    reports {
        xml.required.set(true)
        xml.outputLocation.set(layout.projectDirectory.file("build/reports/jacoco/jacocoTestReport/jacocoTestReport.xml"))
        html.required.set(true)
        html.outputLocation.set(layout.projectDirectory.dir("build/reports/jacoco/jacocoTestReport/html"))
    }
    val fileFilter =
        listOf(
            "**/R.class",
            "**/R\$*.class",
            "**/BuildConfig.*",
            "**/Manifest*.*",
            "**/*Test*.*",
            "**/pigeon/**",
            // Why: MainActivity.kt's constructor/lifecycle methods are never invoked by a plain
            // JVM unit test (Activities need Robolectric/instrumentation, out of scope here), so
            // leaving it in this JaCoCo scan drags the LINE ratio down with a permanently-
            // uncoverable phantom miss. Constraint (controller ruling R11, satisfied by Task 20):
            // MainActivity.kt stays a <=3-line bridge -- configureFlutterEngine's body is exactly
            // `super.configureFlutterEngine(flutterEngine); GazerFlutterBindings.install(...)` --
            // and every real wiring decision (messenger, CameraManager, PigeonHostApiImpl
            // construction, GazerHostApi.setUp) lives in GazerFlutterBindings.install, covered by
            // GazerFlutterBindingsTest.kt on the JVM unit-test target. Do not let this exclusion's
            // scope grow beyond MainActivity itself if real logic is ever added back to it.
            "**/MainActivity.class",
            "**/MainActivity\$*.class",
            // RootEncoderEngine wraps RootEncoder's GenericStream (real Camera2/MediaCodec/
            // socket stack); it cannot run on the JVM unit-test target and is exercised by the
            // instrumented StreamServiceTest (Task 20) instead. Excluded here so the JaCoCo
            // >=90% gate does not count admittedly-uncovered forwarding calls against a class
            // that unit tests structurally cannot reach - narrow, single class, documented, not
            // a blanket exclusion. (Folded into this shared fileFilter -- rather than a separate
            // tasks.withType<JacocoReport>().configureEach{} block -- because classDirectories
            // below is already set to this filtered debugTree; a second post-hoc
            // classDirectories.files.map{fileTree(it){...}} would re-wrap already-resolved leaf
            // .class files instead of directories and silently produce an empty report.)
            "**/pipeline/RootEncoderEngine.class",
        )
    val debugTree =
        fileTree("${layout.buildDirectory.get()}/tmp/kotlin-classes/debug") {
            exclude(fileFilter)
        }
    val mainSrc = "${project.projectDir}/src/main/kotlin"
    sourceDirectories.setFrom(files(mainSrc))
    classDirectories.setFrom(files(debugTree))
    executionData.setFrom(
        fileTree(layout.buildDirectory.get()) {
            include("**/*.exec", "**/*.ec")
        },
    )
}
