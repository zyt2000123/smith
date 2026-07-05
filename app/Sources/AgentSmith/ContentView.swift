import SwiftUI

struct ContentView: View {
    @AppStorage("isDarkMode") private var isDarkMode = true
    @AppStorage("fontSizeOption") private var fontSizeOption = AppFontSizeOption.standard.rawValue
    @State private var selectedPage: String = "management"
    @State private var sidebarVisible = true
    @State private var conversationsExpanded = true
    @State private var channelsExpanded = true
    @State private var hoveredSidebarSection: String?
    @StateObject private var apiClient = APIClient()

    @State private var employees: [Employee] = []

    var body: some View {
        ZStack {
            AppPalette.canvas
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
        .environment(
            \.appFontScale,
            AppFontSizeOption(rawValue: fontSizeOption)?.scale ?? AppFontSizeOption.standard.scale
        )
        .environmentObject(apiClient)
        .task {
            do { employees = try await apiClient.fetchEmployees() }
            catch { employees = Employee.samples }
        }
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
                sidebarAction("Agent总览", icon: "square.grid.2x2", page: "management")
                sidebarAction("定时任务", icon: "clock.arrow.circlepath", page: "automation")
            }
            .padding(.horizontal, 12)
            .padding(.top, 44)
            .padding(.bottom, 8)

            Divider().padding(.horizontal, 12)

            ScrollView {
                VStack(alignment: .leading, spacing: 4) {
                    sidebarSection("对话", expanded: $conversationsExpanded, onCreate: {
                        selectedPage = "new-conv"
                    }, createHelp: "新建对话") {
                        sidebarRow("UI review", subtitle: "Luna · 刚刚", icon: "bubble.left", page: "conv-1")
                        sidebarRow("API deploy", subtitle: "Theo · 5 分钟前", icon: "bubble.left", page: "conv-2")
                        sidebarRow("Roadmap sync", subtitle: "Ivy · 1 小时前", icon: "bubble.left", page: "conv-3")
                    }

                    sidebarSection("频道", expanded: $channelsExpanded, onCreate: {
                        selectedPage = "new-channel"
                    }, createHelp: "新建频道") {
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
                    Image(systemName: "gearshape")
                        .appFont(size: 14)
                        .frame(width: 18)
                    Text("设置").appFont(size: 14)
                }
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 20)
                .padding(.vertical, 10)
            }
            .buttonStyle(.plain)
        }
    }

    private var sidebarPanel: some View {
        sidebar
            .frame(width: 180)
            .frame(maxHeight: .infinity)
            .background(SidebarMaterialView())
            .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 20, style: .continuous)
                    .stroke(AppPalette.border.opacity(0.75), lineWidth: 0.5)
            )
            .shadow(color: .black.opacity(0.08), radius: 14, y: 4)
            .padding(12)
    }

    private func sidebarAction(_ title: String, icon: String, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Image(systemName: icon).appFont(size: 14).foregroundStyle(.secondary).frame(width: 18)
                Text(title).appFont(size: 14).foregroundStyle(selectedPage == page ? .primary : .secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 6).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 10).fill(selectedPage == page ? AppPalette.selectedSurface : .clear))
        }
        .buttonStyle(.plain)
    }

    private func sidebarSection<Content: View>(
        _ title: String,
        expanded: Binding<Bool>,
        onCreate: (() -> Void)? = nil,
        createHelp: String = "新建",
        @ViewBuilder content: () -> Content
    ) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Button {
                    withAnimation(.easeInOut(duration: 0.15)) { expanded.wrappedValue.toggle() }
                } label: {
                    HStack {
                        Text(title).appFont(size: 13, weight: .medium).foregroundStyle(.tertiary)
                        Image(systemName: expanded.wrappedValue ? "chevron.down" : "chevron.right")
                            .appFont(size: 10, weight: .semibold).foregroundStyle(.tertiary)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if let onCreate {
                    Button(action: onCreate) {
                        Image(systemName: "plus")
                            .appFont(size: 12, weight: .semibold)
                            .foregroundStyle(.secondary)
                            .frame(width: 24, height: 24)
                    }
                    .buttonStyle(.plain)
                    .help(createHelp)
                    .opacity(hoveredSidebarSection == title ? 1 : 0)
                    .allowsHitTesting(hoveredSidebarSection == title)
                    .animation(.easeOut(duration: 0.12), value: hoveredSidebarSection == title)
                }
            }
            .padding(.top, 12)
            .padding(.bottom, 4)
            .padding(.leading, 8)
            .contentShape(Rectangle())
            .onHover { hovering in
                hoveredSidebarSection = hovering ? title : nil
            }

            if expanded.wrappedValue { content() }
        }
    }

    private func sidebarEmployeeRow(_ emp: Employee) -> some View {
        Button { selectedPage = "employee-\(emp.id)" } label: {
            HStack(spacing: 8) {
                ZStack(alignment: .bottomTrailing) {
                    Circle().fill(emp.avatarColor.gradient).frame(width: 22, height: 22)
                        .overlay(Text(String(emp.name.prefix(1))).appFont(size: 10, weight: .semibold).foregroundStyle(.white))
                    if emp.isOnline {
                        Circle().fill(Color.green).frame(width: 7, height: 7)
                            .overlay(Circle().stroke(Color(nsColor: .windowBackgroundColor), lineWidth: 1.5))
                    }
                }
                Text(emp.name).appFont(size: 14)
                    .foregroundStyle(selectedPage == "employee-\(emp.id)" ? .primary : .secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 10).fill(selectedPage == "employee-\(emp.id)" ? AppPalette.selectedSurface : .clear))
        }
        .buttonStyle(.plain)
    }

    private func channelRow(_ name: String, isPublic: Bool, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Text(isPublic ? "#" : "🔒").appFont(size: 12).frame(width: 18)
                Text(name).appFont(size: 14).foregroundStyle(selectedPage == page ? .primary : .secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 10).fill(selectedPage == page ? AppPalette.selectedSurface : .clear))
        }
        .buttonStyle(.plain)
    }

    private func sidebarRow(_ title: String, subtitle: String, icon: String, page: String) -> some View {
        Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Image(systemName: icon).appFont(size: 12).foregroundStyle(.tertiary).frame(width: 18)
                VStack(alignment: .leading, spacing: 1) {
                    Text(title).appFont(size: 14).foregroundStyle(selectedPage == page ? .primary : .secondary).lineLimit(1)
                    Text(subtitle).appFont(size: 10).foregroundStyle(.tertiary)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .background(RoundedRectangle(cornerRadius: 10).fill(selectedPage == page ? AppPalette.selectedSurface : .clear))
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
            .background(AppPalette.canvas)
    }

    private var shellSplitView: some View {
        HStack(spacing: 0) {
            if sidebarVisible && !selectedPage.hasPrefix("employee-") {
                sidebarPanel
            }

            mainPanel
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}
