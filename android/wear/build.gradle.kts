import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.ktlint)
}

val localProps = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use(::load)
}

android {
    // Must match :app, or the Data Layer drops every message (ADR-001 §2.1).
    signingConfigs {
        create("shared") {
            storeFile = localProps.getProperty("echocare.keystore")?.let(::file)
            storePassword = localProps.getProperty("echocare.keystore.password")
            keyAlias = "key0" // Android Studio's default alias in the shared keystore
            keyPassword = localProps.getProperty("echocare.key.password")
        }
    }

    namespace = "ro.echocare.wear"
    compileSdk {
        version = release(37)
    }

    defaultConfig {
        applicationId = "ro.echocare"
        minSdk = 36
        targetSdk = 37
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        // 06 §3 timers in demo mode so the course jury doesn't wait 4 hours for inactivity
        debug {
            signingConfig = signingConfigs.getByName("shared")
            val demo = localProps.getProperty("echocare.demo") != "false"
            buildConfigField("boolean", "DEMO", "$demo")
        }
        release {
            signingConfig = signingConfigs.getByName("shared")
            buildConfigField("boolean", "DEMO", "false")
            optimization {
                enable = true
            }
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
    }
    useLibrary("wear-sdk")
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.wear.tooling.preview)
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling)
    implementation(libs.play.services.wearable)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
    debugImplementation(libs.androidx.compose.ui.tooling)
    implementation(project(":shared"))
}
