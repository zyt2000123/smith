import AppKit
import SwiftUI

struct WindowChromeConfigurator: NSViewRepresentable {
    let sidebarInset: CGFloat
    let onToggleSidebar: () -> Void

    private let buttonSize: CGFloat = 16
    private let buttonSpacing: CGFloat = 10
    private let toggleButtonGap: CGFloat = 16
    private let toggleButtonSize = NSSize(width: 28, height: 24)

    func makeCoordinator() -> Coordinator {
        Coordinator(onToggleSidebar: onToggleSidebar)
    }

    func makeNSView(context: Context) -> NSView {
        let view = NSView()
        DispatchQueue.main.async {
            configureWindow(for: view, coordinator: context.coordinator)
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        context.coordinator.onToggleSidebar = onToggleSidebar
        DispatchQueue.main.async {
            configureWindow(for: nsView, coordinator: context.coordinator)
        }
    }

    private func configureWindow(for view: NSView, coordinator: Coordinator) {
        guard let window = view.window else { return }

        window.titleVisibility = .hidden
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.styleMask.insert(.fullSizeContentView)
        window.isOpaque = false
        window.backgroundColor = NSColor(calibratedRed: 0.20, green: 0.20, blue: 0.21, alpha: 1)

        guard
            let closeButton = window.standardWindowButton(.closeButton),
            let miniButton = window.standardWindowButton(.miniaturizeButton),
            let zoomButton = window.standardWindowButton(.zoomButton),
            let buttonContainer = closeButton.superview,
            let titlebarView = buttonContainer.superview
        else { return }

        let buttons = [closeButton, miniButton, zoomButton]
        for (index, button) in buttons.enumerated() {
            button.setFrameSize(NSSize(width: buttonSize, height: buttonSize))
            button.setFrameOrigin(
                NSPoint(
                    x: CGFloat(index) * (buttonSize + buttonSpacing),
                    y: 0
                )
            )
        }

        let titlebarHeight = titlebarView.frame.height
        let targetButtonY = max(0, floor((titlebarHeight - buttonSize) / 2) - 1)
        let targetOrigin = NSPoint(x: sidebarInset + 12, y: targetButtonY)
        if buttonContainer.frame.origin != targetOrigin {
            buttonContainer.setFrameOrigin(targetOrigin)
        }

        let targetWidth = buttonSize * 3 + buttonSpacing * 2
        if buttonContainer.frame.size.width != targetWidth || buttonContainer.frame.size.height != buttonSize {
            buttonContainer.setFrameSize(NSSize(width: targetWidth, height: buttonSize))
        }

        let toggleButton = coordinator.toggleButton ?? makeToggleButton(coordinator: coordinator)
        if toggleButton.superview == nil {
            titlebarView.addSubview(toggleButton)
        }

        let toggleOrigin = NSPoint(
            x: targetOrigin.x + targetWidth + toggleButtonGap,
            y: max(0, floor((titlebarHeight - toggleButtonSize.height) / 2) - 1)
        )
        toggleButton.setFrameOrigin(toggleOrigin)
    }

    private func makeToggleButton(coordinator: Coordinator) -> NSButton {
        let button = NSButton(frame: NSRect(origin: .zero, size: toggleButtonSize))
        button.identifier = NSUserInterfaceItemIdentifier("agent-smith-toggle-sidebar")
        button.image = NSImage(
            systemSymbolName: "sidebar.leading",
            accessibilityDescription: "切换边栏"
        )
        button.imageScaling = .scaleProportionallyDown
        button.imagePosition = .imageOnly
        button.isBordered = false
        button.bezelStyle = .texturedRounded
        button.contentTintColor = NSColor.white.withAlphaComponent(0.78)
        button.toolTip = "切换边栏"
        button.target = coordinator
        button.action = #selector(Coordinator.handleToggleSidebar)
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.layer?.backgroundColor = NSColor.white.withAlphaComponent(0.06).cgColor
        coordinator.toggleButton = button
        return button
    }

    final class Coordinator: NSObject {
        var onToggleSidebar: () -> Void
        weak var toggleButton: NSButton?

        init(onToggleSidebar: @escaping () -> Void) {
            self.onToggleSidebar = onToggleSidebar
        }

        @objc func handleToggleSidebar() {
            onToggleSidebar()
        }
    }
}
