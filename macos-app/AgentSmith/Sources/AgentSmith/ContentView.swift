import SwiftUI

struct ContentView: View {
    @AppStorage("isDarkMode") private var isDarkMode = true
    @State private var selectedPage: String = "management"
    @State private var sidebarVisible = true
    @State private var conversationsExpanded = true
    @State private var channelsExpanded = true
    @StateObject private var apiClient = APIClient()

    private let employees = Employee.samples

    var body: some View {
        ZStack {
            Color(red: 0.20, green: 0.20, blue: 0.21)
                .ignoresSafeArea()

            if selectedPage == "settings" {
                SettingsView(onBack: { selectedPage = "management" })
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .ignoresSafeArea(.container, edges: .top)
            } else {
                shellSplitView
                    .ignoresSafeArea(.container, edges: .top)
            }
        }
        .preferredColorScheme(isDarkMode ? .dark : .light)
        .environmentObject(apiClient)
        .background(
            WindowChromeConfigurator(sidebarInset: 14) {
                withAnimation(.easeInOut(duration: 0.18)) {
                    sidebarVisible.toggle()
                }
            }
        )
    }

    private var sidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                sidebarAction("新对话", icon: "square.and.pencil", page: "new-conv")
                sidebarAction("员工总览", icon: "square.grid.2x2", page: "management")
                sidebarAction("自动化", icon: "clock.arrow.circlepath", page: "automation")
            }
            .padding(.horizontal, 12)
            .padding(.top, 48)
            .padding(.bottom, 8)

            Divider().padding(.horizontal, 12)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    sidebarSection("对话", expanded: $conversationsExpanded) {
                        sidebarRow("UI review", subtitle: "Luna · 刚刚", icon: "bubble.left", page: "conv-1")
                        sidebarRow("API deploy", subtitle: "Theo · 5 分钟前", icon: "bubble.left", page: "conv-2")
                        sidebarRow("Roadmap sync", subtitle: "Ivy · 1 小时前", icon: "bubble.left", page: "conv-3")
                    }

                    sidebarSection("频道", expanded: $channelsExpanded) {
                        channelRow("全体", isPublic: true, page: "ch-all")
                        channelRow("前端协作", isPublic: false, page: "ch-frontend")
                        channelRow("后端架构", isPublic: false, page: "ch-backend")
                        channelRow("产品评审", isPublic: true, page: "ch-product")
                        channelRow("测试验收", isPublic: false, page: "ch-qa")
                    }
                }
                .padding(.horizontal, 12)
                .padding(.top, 8)
            }

            Spacer()
            Divider().padding(.horizontal, 12)

            Button { selectedPage = "settings" } label: {
                HStack(spacing: 8) {
                    Image(systemName: "gearshape").font(.system(size: 14))
                    Text("设置").font(.system(size: 14))
                }
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
            }
            .buttonStyle(.plain)
        }
    }

    private var sidebarPanel: some View {
        sidebar
            .frame(width: 248)
            .frame(maxHeight: .infinity)
            .background(Color(red: 0.11, green: 0.11, blue: 0.12))
            .clipShape(
                UnevenRoundedRectangle(
                    cornerRadii: .init(
                        topLeading: 20,
                        bottomLeading: 20,
                        bottomTrailing: 0,
                        topTrailing: 0
                    ),
                    style: .continuous
                )
            )
    }

    private func sidebarAction(_ title: String, icon: String, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 14)).foregroundStyle(.secondary).frame(width: 18)
                Text(title).font(.system(size: 14)).foregroundStyle(selectedPage == page ? .primary : .secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 6).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(selectedPage == page ? Color.white.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
    }

    private func sidebarSection<Content: View>(_ title: String, expanded: Binding<Bool>, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Button {
                withAnimation(.easeInOut(duration: 0.15)) { expanded.wrappedValue.toggle() }
            } label: {
                HStack {
                    Text(title).font(.system(size: 11, weight: .medium)).foregroundStyle(.tertiary)
                    Image(systemName: expanded.wrappedValue ? "chevron.down" : "chevron.right")
                        .font(.system(size: 8, weight: .semibold)).foregroundStyle(.tertiary)
                }
                .padding(.top, 12).padding(.bottom, 4).padding(.horizontal, 8)
            }
            .buttonStyle(.plain)

            if expanded.wrappedValue { content() }
        }
    }

    private func sidebarEmployeeRow(_ emp: Employee) -> some View {
        Button { selectedPage = "employee-\(emp.id)" } label: {
            HStack(spacing: 8) {
                ZStack(alignment: .bottomTrailing) {
                    Circle().fill(emp.avatarColor.gradient).frame(width: 22, height: 22)
                        .overlay(Text(String(emp.name.prefix(1))).font(.system(size: 10, weight: .semibold)).foregroundStyle(.white))
                    if emp.isOnline {
                        Circle().fill(Color.green).frame(width: 7, height: 7)
                            .overlay(Circle().stroke(Color(nsColor: .windowBackgroundColor), lineWidth: 1.5))
                    }
                }
                Text(emp.name).font(.system(size: 14))
                    .foregroundStyle(selectedPage == "employee-\(emp.id)" ? .primary : .secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(selectedPage == "employee-\(emp.id)" ? Color.white.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
    }

    private func channelRow(_ name: String, isPublic: Bool, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Text(isPublic ? "#" : "🔒").font(.system(size: 12)).frame(width: 18)
                Text(name).font(.system(size: 14)).foregroundStyle(selectedPage == page ? .primary : .secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(selectedPage == page ? Color.white.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
    }

    private func sidebarRow(_ title: String, subtitle: String, icon: String, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Image(systemName: icon).font(.system(size: 12)).foregroundStyle(.tertiary).frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).font(.system(size: 14)).foregroundStyle(selectedPage == page ? .primary : .secondary).lineLimit(1)
                    Text(subtitle).font(.system(size: 10)).foregroundStyle(.tertiary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 6).fill(selectedPage == page ? Color.white.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
    }

    private var mainContent: some View {
        Group {
            if selectedPage == "management" || selectedPage == "create" || selectedPage == "search" {
                ManagementView { employee in
                    selectedPage = "employee-\(employee.id)"
                }
            } else if selectedPage.hasPrefix("conv-") || selectedPage == "new-conv" {
                ConversationView()
            } else if selectedPage.hasPrefix("employee-"),
                      let emp = employees.first(where: { $0.id == String(selectedPage.dropFirst("employee-".count)) }) {
                EmployeeDetailView(employee: emp, onBack: {
                    selectedPage = "management"
                })
            } else {
                VStack(spacing: 8) {
                    Text("功能开发中...").font(.title2).fontWeight(.bold)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
    }

    private var mainPanel: some View {
        mainContent
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(red: 0.16, green: 0.16, blue: 0.17))
    }

    private var shellSplitView: some View {
        HStack(spacing: 0) {
            if sidebarVisible {
                sidebarPanel

                Rectangle()
                    .fill(Color.white.opacity(0.07))
                    .frame(width: 1)
            }

            mainPanel
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
