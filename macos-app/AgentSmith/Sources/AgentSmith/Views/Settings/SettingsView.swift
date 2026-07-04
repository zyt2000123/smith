import SwiftUI

struct SettingsView: View {
    var body: some View {
        VStack(spacing: 12) {
            Image(systemName: "gear")
                .font(.system(size: 48))
                .foregroundColor(.secondary.opacity(0.4))
            Text("设置")
                .font(.system(size: 24, weight: .bold))
            Text("功能开发中...")
                .font(.system(size: 14))
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
