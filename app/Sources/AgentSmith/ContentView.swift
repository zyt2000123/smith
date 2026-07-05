import SwiftUI

struct ContentView: View {
    @AppStorage("isDarkMode") private var isDarkMode = true
    @AppStorage("fontSizeOption") private var fontSizeOption = AppFontSizeOption.standard.rawValue
    @State private var selectedPage: String = "management"
    @State private var sidebarVisible = true
    @State private var conversationsExpanded = true
    @State private var channelsExpanded = true
    @State private var hoveredSidebarSection: String?
    @State private var hoveredSidebarItem: String?
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
                sidebarAction("员工总览", icon: "square.grid.2x2", page: "management")
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
                        conversationSidebarRow(
                            name: "Ivy",
                            preview: "版本范围已经同步到路线图里。",
                            timestamp: "刚刚",
                            imageName: "product-manager",
                            color: .purple,
                            page: "conv-3"
                        )
                        conversationSidebarRow(
                            name: "Luna",
                            preview: "好的，我来看看这个组件的实现…",
                            timestamp: "5 分钟前",
                            imageName: "frontend-engineer",
                            color: .green,
                            page: "conv-1"
                        )
                        conversationSidebarRow(
                            name: "Theo",
                            preview: "API 接口已经部署完成。",
                            timestamp: "1 小时前",
                            imageName: "backend-engineer",
                            color: .blue,
                            page: "conv-2"
                        )
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
            .frame(width: FloatingSidebarMetrics.width)
            .frame(maxHeight: .infinity)
            .floatingSidebarSurface()
            .padding(.leading, FloatingSidebarMetrics.inset)
            .padding(.vertical, FloatingSidebarMetrics.inset)
    }

    private func sidebarAction(_ title: String, icon: String, page: String) -> some View {
        let isSelected = selectedPage == page
        let isHovered = hoveredSidebarItem == page

        return Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Image(systemName: icon)
                    .appFont(size: 14)
                    .foregroundStyle(isSelected ? .blue : .secondary)
                    .frame(width: 18)
                Text(title)
                    .appFont(size: 14)
                    .foregroundStyle(isSelected ? .blue : .secondary)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 6).padding(.horizontal, 8)
            .sidebarNavigationBackground(isSelected: isSelected, isHovered: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredSidebarItem = hovering ? page : nil
        }
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
        let page = "employee-\(emp.id)"
        let isSelected = selectedPage == page
        let isHovered = hoveredSidebarItem == page

        return Button { selectedPage = page } label: {
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
                    .foregroundStyle(isSelected ? .blue : .secondary).lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .sidebarNavigationBackground(isSelected: isSelected, isHovered: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredSidebarItem = hovering ? page : nil
        }
    }

    private func channelRow(_ name: String, isPublic: Bool, page: String) -> some View {
        let isSelected = selectedPage == page
        let isHovered = hoveredSidebarItem == page

        return Button { selectedPage = page } label: {
            HStack(spacing: 8) {
                Text(isPublic ? "#" : "🔒")
                    .appFont(size: 12)
                    .foregroundStyle(isSelected ? .blue : .secondary)
                    .frame(width: 18)
                Text(name)
                    .appFont(size: 14)
                    .foregroundStyle(isSelected ? .blue : .secondary)
                    .lineLimit(1)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 5).padding(.horizontal, 8)
            .sidebarNavigationBackground(isSelected: isSelected, isHovered: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredSidebarItem = hovering ? page : nil
        }
    }

    private func conversationSidebarRow(
        name: String,
        preview: String,
        timestamp: String,
        imageName: String,
        color: Color,
        page: String
    ) -> some View {
        let isSelected = selectedPage == page
        let isHovered = hoveredSidebarItem == page

        return Button { selectedPage = page } label: {
            HStack(spacing: 9) {
                EmployeePortraitView(
                    imageName: imageName,
                    fallbackColor: color,
                    fallbackText: String(name.prefix(1)),
                    width: 36,
                    height: 42,
                    cornerRadius: 8
                )

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 4) {
                        Text(name)
                            .appFont(size: 13, weight: .semibold)
                            .foregroundStyle(.primary)
                        Spacer(minLength: 2)
                        Text(timestamp)
                            .appFont(size: 9)
                            .foregroundStyle(.tertiary)
                    }
                    Text(preview)
                        .appFont(size: 11)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.vertical, 8)
            .padding(.horizontal, 8)
            .sidebarNavigationBackground(isSelected: isSelected, isHovered: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredSidebarItem = hovering ? page : nil
        }
    }

    private var mainContent: some View {
        Group {
            if selectedPage == "management" || selectedPage == "create" || selectedPage == "search" {
                ManagementView { employee in
                    selectedPage = "employee-\(employee.id)"
                }
            } else if selectedPage.hasPrefix("conv-") || selectedPage == "new-conv" {
                ConversationView(
                    initialConversationID: conversationID(for: selectedPage),
                    onBack: { selectedPage = "management" }
                )
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
        ZStack(alignment: .leading) {
            mainPanel
                .padding(
                    .leading,
                    showsPrimarySidebar
                        ? FloatingSidebarMetrics.width + FloatingSidebarMetrics.inset
                        : 0
                )

            if showsPrimarySidebar {
                sidebarPanel
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var showsPrimarySidebar: Bool {
        sidebarVisible
            && !selectedPage.hasPrefix("employee-")
            && !selectedPage.hasPrefix("conv-")
            && selectedPage != "new-conv"
    }

    private func conversationID(for page: String) -> String {
        switch page {
        case "conv-1": return "luna"
        case "conv-2": return "theo"
        case "conv-3": return "ivy"
        default: return "ivy"
        }
    }
}
