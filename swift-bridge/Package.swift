// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "AppleNotesBridge",
    platforms: [.macOS(.v13)],
    products: [
        .executable(name: "notes-bridge", targets: ["AppleNotesBridge"])
    ],
    dependencies: [
        .package(url: "https://github.com/apple/swift-argument-parser", from: "1.2.0")
    ],
    targets: [
        .executableTarget(
            name: "AppleNotesBridge",
            dependencies: [
                .product(name: "ArgumentParser", package: "swift-argument-parser")
            ]
        )
    ]
)
