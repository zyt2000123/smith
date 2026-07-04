import SwiftUI

enum SidebarTab: String, CaseIterable {
    case management
    case contacts
    case conversations
    case board
    case settings

    var icon: String {
        switch self {
        case .management: return "square.grid.2x2"
        case .contacts: return "person.2"
        case .conversations: return "bubble.left.and.bubble.right"
        case .board: return "rectangle.stack"
        case .settings: return "gear"
        }
    }

    var label: String {
        switch self {
        case .management: return "Agent管理"
        case .contacts: return "通讯录"
        case .conversations: return "对话"
        case .board: return "看板"
        case .settings: return "设置"
        }
    }
}

struct ContentView: View {
    @State private var selectedTab: SidebarTab = .management
    @State private var selectedEmployee: Employee?
    @StateObject private var apiClient = APIClient()

    var body: some View {
        HStack(spacing: 0) {
            // Narrow icon sidebar
            VStack(spacing: 0) {
                // Logo
                VStack {
                    ZStack {
                        Circle()
                            .fill(Color.green)
                            .frame(width: 36, height: 36)
                        Text("AS")
                            .font(.system(size: 13, weight: .bold))
                            .foregroundColor(.white)
                    }
                }
                .frame(height: 60)

                Divider()
                    .padding(.horizontal, 12)

                // Top tabs
                VStack(spacing: 4) {
                    ForEach([SidebarTab.management, .contacts, .conversations, .board], id: \.self) { tab in
                        sidebarButton(tab)
                    }
                }
                .padding(.top, 12)

                Spacer()

                // Bottom settings
                sidebarButton(.settings)
                    .padding(.bottom, 12)
            }
            .frame(width: 56)
            .background(Color(nsColor: .controlBackgroundColor))

            Divider()

            // Main content
            Group {
                switch selectedTab {
                case .management:
                    ManagementView(selectedEmployee: $selectedEmployee)
                case .contacts:
                    placeholderView("通讯录", subtitle: "功能开发中...")
                case .conversations:
                    ConversationView()
                case .board:
                    placeholderView("看板", subtitle: "功能开发中...")
                case .settings:
                    SettingsView()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
        .environmentObject(apiClient)
    }

    private func sidebarButton(_ tab: SidebarTab) -> some View {
        Button {
            selectedTab = tab
        } label: {
            Image(systemName: tab.icon)
                .font(.system(size: 18))
                .foregroundColor(selectedTab == tab ? .accentColor : .secondary)
                .frame(width: 40, height: 40)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(selectedTab == tab ? Color.accentColor.opacity(0.12) : Color.clear)
                )
        }
        .buttonStyle(.plain)
        .help(tab.label)
    }

    private func placeholderView(_ title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Text(title)
                .font(.title)
                .fontWeight(.bold)
            Text(subtitle)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
