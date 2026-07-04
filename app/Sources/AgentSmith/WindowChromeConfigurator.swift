import AppKit
import SwiftUI

struct WindowChromeConfigurator: NSViewRepresentable {
    let sidebarInset: CGFloat
    let onToggleSidebar: () -> Void

    private let buttonSize: CGFloat = 16
    private let buttonSpacing: CGFloat = 10
    private let toggleButtonGap: CGFloat = 16
    private let toggleButtonSize = NSSize(width: 28, height: 24)
    private let verticalOffset: CGFloat = -4

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
        window.backgroundColor = .windowBackgroundColor

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
        let targetButtonY = max(0, floor((titlebarHeight - buttonSize) / 2) - 1 + verticalOffset)
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
            y: max(0, floor((titlebarHeight - toggleButtonSize.height) / 2) - 1 + verticalOffset)
        )
        toggleButton.setFrameOrigin(toggleOrigin)
    }

    private func makeToggleButton(coordinator: Coordinator) -> NSButton {
        let button = HoverChromeButton(frame: NSRect(origin: .zero, size: toggleButtonSize))
        button.identifier = NSUserInterfaceItemIdentifier("agent-smith-toggle-sidebar")
        button.image = NSImage(
            systemSymbolName: "sidebar.leading",
            accessibilityDescription: "切换边栏"
        )
        button.imageScaling = .scaleProportionallyDown
        button.imagePosition = .imageOnly
        button.isBordered = false
        button.bezelStyle = .texturedRounded
        button.toolTip = "切换边栏"
        button.target = coordinator
        button.action = #selector(Coordinator.handleToggleSidebar)
        button.wantsLayer = true
        button.layer?.cornerRadius = 8
        button.refreshAppearance()
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

private final class HoverChromeButton: NSButton {
    private var trackingAreaRef: NSTrackingArea?
    private var isHovered = false

    override var isHighlighted: Bool {
        didSet { refreshAppearance() }
    }

    override func updateTrackingAreas() {
        super.updateTrackingAreas()
        if let trackingAreaRef {
            removeTrackingArea(trackingAreaRef)
        }
        let trackingArea = NSTrackingArea(
            rect: bounds,
            options: [.activeAlways, .mouseEnteredAndExited, .inVisibleRect],
            owner: self
        )
        addTrackingArea(trackingArea)
        trackingAreaRef = trackingArea
    }

    override func mouseEntered(with event: NSEvent) {
        isHovered = true
        refreshAppearance()
    }

    override func mouseExited(with event: NSEvent) {
        isHovered = false
        refreshAppearance()
    }

    override func viewDidChangeEffectiveAppearance() {
        super.viewDidChangeEffectiveAppearance()
        refreshAppearance()
    }

    func refreshAppearance() {
        let isDark = effectiveAppearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua
        let chromeColor = isDark ? NSColor.white : NSColor.black
        contentTintColor = chromeColor.withAlphaComponent(0.72)
        layer?.backgroundColor = isHovered || isHighlighted
            ? chromeColor.withAlphaComponent(0.08).cgColor
            : NSColor.clear.cgColor
    }
}
