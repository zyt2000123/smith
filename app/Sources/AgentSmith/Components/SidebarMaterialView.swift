import AppKit
import SwiftUI

enum FloatingSidebarMetrics {
    static let width: CGFloat = 192
    static let inset: CGFloat = 12
    static let cornerRadius: CGFloat = 20
    static let topContentPadding: CGFloat = 44
    static let rightContentTopInset: CGFloat = 48
}

struct SidebarMaterialView: NSViewRepresentable {
    func makeNSView(context: Context) -> NSVisualEffectView {
        let view = NSVisualEffectView()
        view.material = .sidebar
        view.blendingMode = .withinWindow
        view.state = .active
        return view
    }

    func updateNSView(_ nsView: NSVisualEffectView, context: Context) {
        nsView.material = .sidebar
        nsView.blendingMode = .withinWindow
        nsView.state = .active
    }
}

extension View {
    func floatingSidebarSurface() -> some View {
        background(SidebarMaterialView())
            .clipShape(
                RoundedRectangle(
                    cornerRadius: FloatingSidebarMetrics.cornerRadius,
                    style: .continuous
                )
            )
            .overlay(
                RoundedRectangle(
                    cornerRadius: FloatingSidebarMetrics.cornerRadius,
                    style: .continuous
                )
                .stroke(AppPalette.border.opacity(0.75), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.08), radius: 14, y: 4)
    }

    func appSelectionBackground(
        isSelected: Bool,
        isHovered: Bool = false,
        cornerRadius: CGFloat = 8
    ) -> some View {
        background(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(
                    isSelected
                        ? Color.blue.opacity(0.12)
                        : isHovered
                            ? AppPalette.mutedSurface
                            : Color.clear
                )
        )
        .animation(.easeInOut(duration: 0.15), value: isSelected)
        .animation(.easeInOut(duration: 0.15), value: isHovered)
    }

    func sidebarNavigationBackground(
        isSelected: Bool,
        isHovered: Bool = false
    ) -> some View {
        appSelectionBackground(isSelected: isSelected, isHovered: isHovered)
    }
}
