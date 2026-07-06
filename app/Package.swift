// swift-tools-version: 6.1
import PackageDescription

let package = Package(
    name: "AgentSmith",
    platforms: [.macOS(.v15)],
    targets: [
        .executableTarget(
            name: "AgentSmith",
            path: "Sources/AgentSmith",
            resources: [
                .copy("Resources/AppIcon.icns"),
                .copy("Resources/Employees"),
                .copy("Resources/mermaid.min.js")
            ]
        )
    ]
)
