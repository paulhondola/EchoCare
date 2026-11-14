// swift-tools-version: 6.0
import PackageDescription

// The watch's detectors and the watch-phone messages, ported from android/shared.
let package = Package(
    name: "Shared",
    platforms: [.macOS(.v15), .iOS("26.0"), .watchOS("26.0")],
    products: [.library(name: "Shared", targets: ["Shared"])],
    targets: [
        .target(name: "Shared"),
        .testTarget(name: "SharedTests", dependencies: ["Shared"]),
    ]
)
