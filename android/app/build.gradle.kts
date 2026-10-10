import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
}

// Keystore paths and passwords, and the optional API override, stay out of Git (ADR-001 §2.1, §2.2).
val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}

android {
    // One key for debug and release, phone and watch (ADR-001 §2.1). Same block in wear/build.gradle.kts.
    signingConfigs {
        create("shared") {
            storeFile = localProps.getProperty("sentinela.keystore")?.let(::file)
            storePassword = localProps.getProperty("sentinela.keystore.password")
            keyAlias = "key0" // Android Studio's default alias in the shared keystore
            keyPassword = localProps.getProperty("sentinela.key.password")
        }
    }

    namespace = "bia.sentinela"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "bia.sentinela"
        minSdk = 37
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    buildTypes {
        // debug → staging, release → production (ADR-001 §2.2). sentinela.apiUrl in local.properties
        // points a debug build elsewhere, e.g. http://10.0.2.2:8000 for Compose from the emulator.
        debug {
            signingConfig = signingConfigs.getByName("shared")
            buildConfigField("String", "API_URL",
                "\"${localProps.getProperty("sentinela.apiUrl") ?: "https://STAGING-API-DOMAIN"}\"")
        }
        release {
            signingConfig = signingConfigs.getByName("shared")
            buildConfigField("String", "API_URL", "\"https://PRODUCTION-API-DOMAIN\"")
            optimization {
                enable = true
                packageScope = setOf("androidx.**", "kotlin.**", "kotlinx.**")
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
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.junit)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
    implementation(project(":shared"))
}
