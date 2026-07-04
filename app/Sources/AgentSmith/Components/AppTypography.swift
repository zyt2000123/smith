import SwiftUI

enum AppFontSizeOption: String, CaseIterable, Identifiable {
    case small
    case standard
    case large

    var id: String { rawValue }

    var label: String {
        switch self {
        case .small: return "小"
        case .standard: return "标准"
        case .large: return "大"
        }
    }

    var scale: CGFloat {
        switch self {
        case .small: return 0.9
        case .standard: return 1
        case .large: return 1.12
        }
    }
}

private struct AppFontScaleKey: EnvironmentKey {
    static let defaultValue: CGFloat = 1
}

extension EnvironmentValues {
    var appFontScale: CGFloat {
        get { self[AppFontScaleKey.self] }
        set { self[AppFontScaleKey.self] = newValue }
    }
}

private struct AppFontModifier: ViewModifier {
    @Environment(\.appFontScale) private var scale

    let size: CGFloat
    let weight: Font.Weight
    let design: Font.Design

    func body(content: Content) -> some View {
        content.font(.system(size: size * scale, weight: weight, design: design))
    }
}

extension View {
    func appFont(
        size: CGFloat,
        weight: Font.Weight = .regular,
        design: Font.Design = .default
    ) -> some View {
        modifier(AppFontModifier(size: size, weight: weight, design: design))
    }
}
