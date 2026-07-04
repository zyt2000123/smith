import SwiftUI

@main
struct AgentSmithApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1200, minHeight: 760)
        }
        .windowStyle(.titleBar)
        .defaultSize(width: 1400, height: 860)
    }
}
