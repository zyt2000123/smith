import AppKit
import SwiftUI

enum AppPalette {
    static let canvas = adaptive(
        light: NSColor(srgbRed: 0.992, green: 0.994, blue: 0.996, alpha: 1),
        dark: NSColor(srgbRed: 0.105, green: 0.105, blue: 0.115, alpha: 1)
    )

    static let card = adaptive(
        light: NSColor(srgbRed: 0.985, green: 0.987, blue: 0.989, alpha: 1),
        dark: NSColor(srgbRed: 0.145, green: 0.145, blue: 0.155, alpha: 1)
    )

    static let mutedSurface = adaptive(
        light: NSColor(srgbRed: 0.935, green: 0.940, blue: 0.945, alpha: 1),
        dark: NSColor(srgbRed: 0.185, green: 0.185, blue: 0.200, alpha: 1)
    )

    static let selectedSurface = adaptive(
        light: NSColor(srgbRed: 0.890, green: 0.895, blue: 0.900, alpha: 1),
        dark: NSColor(srgbRed: 0.225, green: 0.225, blue: 0.240, alpha: 1)
    )

    static let border = adaptive(
        light: NSColor(srgbRed: 0.875, green: 0.882, blue: 0.890, alpha: 1),
        dark: NSColor(srgbRed: 0.275, green: 0.275, blue: 0.295, alpha: 1)
    )

    static let online = Color(red: 0.12, green: 0.68, blue: 0.34)

    private static func adaptive(light: NSColor, dark: NSColor) -> Color {
        Color(
            nsColor: NSColor(name: nil) { appearance in
                appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
            }
        )
    }
}

extension View {
    func appCardSurface(cornerRadius: CGFloat = 12) -> some View {
        background(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .fill(AppPalette.card)
                .shadow(color: .black.opacity(0.035), radius: 8, y: 2)
        )
        .overlay(
            RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)
                .stroke(AppPalette.border, lineWidth: 0.5)
        )
    }
}
