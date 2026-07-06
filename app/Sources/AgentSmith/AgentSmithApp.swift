import SwiftUI

@main
struct AgentSmithApp: App {
    init() {
        // 裸二进制（swift build 直接运行）没有 app bundle，
        // 必须显式声明为常规应用并激活，否则窗口收不到键盘输入
        NSApplication.shared.setActivationPolicy(.regular)
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1200, minHeight: 760)
                .onAppear {
                    setAppIcon()
                    NSApp.activate(ignoringOtherApps: true)
                }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1400, height: 860)
    }

    private func setAppIcon() {
        if let url = Bundle.module.url(forResource: "AppIcon", withExtension: "icns"),
           let image = NSImage(contentsOf: url) {
            NSApplication.shared.applicationIconImage = image
        }
    }
}
