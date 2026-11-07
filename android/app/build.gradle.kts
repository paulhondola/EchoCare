import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ktlint)
    alias(libs.plugins.hilt)
    alias(libs.plugins.ksp)
    alias(libs.plugins.google.services)
}

// Keystore paths and passwords, and the optional API override, stay out of Git (ADR-001 §2.1, §2.2).
val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}

android {
    // One key for debug and release, phone and watch (ADR-001 §2.1). Same block in wear/build.gradle.kts.
    signingConfigs {
        create("shared") {
            storeFile = localProps.getProperty("echocare.keystore")?.let(::file)
            storePassword = localProps.getProperty("echocare.keystore.password")
            keyAlias = "key0" // Android Studio's default alias in the shared keystore
            keyPassword = localProps.getProperty("echocare.key.password")
        }
    }

    namespace = "ro.echocare"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "ro.echocare"
        minSdk = 37
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        // debug → staging, release → production (ADR-001 §2.2). echocare.apiUrl in local.properties
        // points a debug build elsewhere, e.g. http://10.0.2.2:8000 for Compose from the emulator.
        debug {
            signingConfig = signingConfigs.getByName("shared")
            val apiUrl = localProps.getProperty("echocare.apiUrl")
                ?: "https://echocare-api-staging.up.railway.app"
            buildConfigField("String", "API_URL", "\"$apiUrl\"")
            // How often an open screen re-reads (06 §3). echocare.rereadSeconds=10 for a demo.
            val reread = localProps.getProperty("echocare.rereadSeconds") ?: "30"
            buildConfigField("int", "REREAD_SECONDS", reread)
            // echocare.realSms=true keeps Firebase's app verification on, for real numbers (auth-layer §9).
            val realSms = localProps.getProperty("echocare.realSms") == "true"
            buildConfigField("boolean", "REAL_SMS", "$realSms")
        }
        release {
            signingConfig = signingConfigs.getByName("shared")
            buildConfigField(
                "String",
                "API_URL",
                "\"https://echocare-api-prod.up.railway.app\""
            )
            buildConfigField("int", "REREAD_SECONDS", "30")
            buildConfigField("boolean", "REAL_SMS", "true")
            optimization {
                enable = true
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.retrofit)
    implementation(libs.retrofit.converter.kotlinx.serialization)
    implementation(libs.kotlinx.serialization.json)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.firebase.messaging)
    implementation(libs.kotlinx.coroutines.play.services)
    implementation(libs.play.services.wearable)
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.androidx.hilt.lifecycle.viewmodel.compose)
    implementation(libs.androidx.navigation.compose)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
    implementation(project(":shared"))
}
