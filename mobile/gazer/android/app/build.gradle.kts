import org.jetbrains.kotlin.gradle.dsl.JvmTarget

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

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("debug")
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
            // Why: MainActivity.kt is stock flutter-create boilerplate (Task 2 leaves it
            // untouched) with no JVM-testable logic of its own -- its default constructor is
            // never invoked by a plain JVM unit test (Activities need Robolectric/instrumentation,
            // out of scope here), so leaving it in this JaCoCo scan drags the LINE ratio down with
            // a permanently-uncoverable phantom miss unrelated to anything Task 2 introduces.
            // Constraint (controller ruling R11): this exclusion may stay ONLY as long as
            // MainActivity stays a flutter-create-boilerplate Activity with no testable logic.
            // Task 20 MUST keep MainActivity.kt a <=3-line bridge that delegates all real logic to
            // a separately unit-tested factory/class, and MUST revisit (narrow or remove) this
            // exclusion when it touches MainActivity.kt -- do not let this scope grow to cover
            // real logic added later.
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
