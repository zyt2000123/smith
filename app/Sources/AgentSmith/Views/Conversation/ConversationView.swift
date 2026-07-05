import SwiftUI

struct ConversationItem: Identifiable {
    let id: String
    let employeeName: String
    let role: String
    let avatarImageName: String?
    let avatarColor: Color
    let preview: String
    let timestamp: String
}

struct SuggestionCard: Identifiable {
    let id = UUID()
    let text: String
}

enum CapabilityPanelTab: String, CaseIterable {
    case plan, mcp, skills, permissions, knowledge

    var label: String {
        switch self {
        case .plan: return "计划"
        case .mcp: return "MCP"
        case .skills: return "技能"
        case .permissions: return "权限"
        case .knowledge: return "知识库"
        }
    }

    var icon: String {
        switch self {
        case .plan: return "list.bullet.clipboard"
        case .mcp: return "puzzlepiece.extension"
        case .skills: return "sparkles"
        case .permissions: return "shield"
        case .knowledge: return "book"
        }
    }
}

struct ConversationView: View {
    var onBack: (() -> Void)?
    @State private var messageText = ""
    @State private var searchText = ""
    @State private var selectedConversation: String
    @State private var showCapabilityPanel = false
    @State private var selectedPanelTab: CapabilityPanelTab = .plan

    private let conversations: [ConversationItem] = [
        ConversationItem(
            id: "ivy",
            employeeName: "Ivy",
            role: "产品经理",
            avatarImageName: "product-manager",
            avatarColor: .purple,
            preview: "版本范围已经同步到路线图里。",
            timestamp: "刚刚"
        ),
        ConversationItem(
            id: "luna",
            employeeName: "Luna",
            role: "前端工程师",
            avatarImageName: "frontend-engineer",
            avatarColor: .green,
            preview: "好的，我来看看这个组件的实现…",
            timestamp: "5 分钟前"
        ),
        ConversationItem(
            id: "theo",
            employeeName: "Theo",
            role: "后端工程师",
            avatarImageName: "backend-engineer",
            avatarColor: .blue,
            preview: "API 接口已经部署完成。",
            timestamp: "1 小时前"
        ),
    ]

    private let suggestions: [SuggestionCard] = [
        SuggestionCard(text: "帮我把这个想法整理成可执行的 PRD 和验收标准"),
        SuggestionCard(text: "帮我分析这些用户反馈，归类问题并给出优先级建议"),
        SuggestionCard(text: "帮我调研竞品最近的变化，并总结对产品的启发"),
    ]

    init(initialConversationID: String = "ivy", onBack: (() -> Void)? = nil) {
        self.onBack = onBack
        _selectedConversation = State(initialValue: initialConversationID)
    }

    private var activeConversation: ConversationItem {
        conversations.first(where: { $0.id == selectedConversation }) ?? conversations[0]
    }

    private var filteredConversations: [ConversationItem] {
        guard !searchText.isEmpty else { return conversations }
        return conversations.filter {
            $0.employeeName.localizedCaseInsensitiveContains(searchText)
                || $0.role.localizedCaseInsensitiveContains(searchText)
                || $0.preview.localizedCaseInsensitiveContains(searchText)
        }
    }

    var body: some View {
        ZStack(alignment: .leading) {
            HStack(spacing: 0) {
                Color.clear
                    .frame(width: FloatingSidebarMetrics.width + FloatingSidebarMetrics.inset)

                conversationWorkspace

                if showCapabilityPanel {
                    Divider()
                    capabilityPanel
                        .transition(.move(edge: .trailing).combined(with: .opacity))
                }
            }

            conversationSidebar
                .frame(width: FloatingSidebarMetrics.width)
                .frame(maxHeight: .infinity)
                .floatingSidebarSurface()
                .padding(.leading, FloatingSidebarMetrics.inset)
                .padding(.vertical, FloatingSidebarMetrics.inset)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppPalette.canvas)
    }

    private var conversationSidebar: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Button { onBack?() } label: {
                    Image(systemName: "chevron.left")
                        .appFont(size: 11, weight: .semibold)
                        .foregroundStyle(.secondary)
                        .frame(width: 20, height: 20)
                }
                .buttonStyle(.plain)
                .help("返回员工总览")

                Text("对话")
                    .appFont(size: 16, weight: .bold)
                Spacer()
                Button {} label: {
                    Image(systemName: "square.and.pencil")
                        .appFont(size: 14, weight: .medium)
                }
                .buttonStyle(.plain)
                .help("新建对话")
            }
            .padding(.top, FloatingSidebarMetrics.topContentPadding)
            .padding(.horizontal, 14)
            .padding(.bottom, 12)

            HStack(spacing: 7) {
                Image(systemName: "magnifyingglass")
                    .appFont(size: 11)
                    .foregroundStyle(.tertiary)
                TextField("搜索对话…", text: $searchText)
                    .textFieldStyle(.plain)
                    .appFont(size: 12)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 7)
            .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 8))
            .padding(.horizontal, 12)
            .padding(.bottom, 16)

            Text("最近对话")
                .appFont(size: 11, weight: .semibold)
                .foregroundStyle(.tertiary)
                .padding(.horizontal, 14)
                .padding(.bottom, 6)

            ScrollView {
                LazyVStack(spacing: 3) {
                    ForEach(filteredConversations) { conversation in
                        conversationRow(conversation)
                    }
                }
                .padding(.horizontal, 8)
            }

            Divider()
                .padding(.horizontal, 12)

            Button {} label: {
                Label("新建群组对话", systemImage: "person.2.badge.plus")
                    .appFont(size: 12)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 14)
                    .padding(.vertical, 12)
            }
            .buttonStyle(.plain)
        }
    }

    private func conversationRow(_ conversation: ConversationItem) -> some View {
        let isSelected = selectedConversation == conversation.id

        return Button {
            selectedConversation = conversation.id
        } label: {
            HStack(spacing: 9) {
                EmployeePortraitView(
                    imageName: conversation.avatarImageName,
                    fallbackColor: conversation.avatarColor,
                    fallbackText: String(conversation.employeeName.prefix(1)),
                    width: 36,
                    height: 42,
                    cornerRadius: 8
                )

                VStack(alignment: .leading, spacing: 3) {
                    HStack(spacing: 4) {
                        Text(conversation.employeeName)
                            .appFont(size: 13, weight: .semibold)
                            .foregroundStyle(.primary)
                        Spacer(minLength: 2)
                        Text(conversation.timestamp)
                            .appFont(size: 9)
                            .foregroundStyle(.tertiary)
                    }
                    Text(conversation.preview)
                        .appFont(size: 11)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 8)
            .background(
                RoundedRectangle(cornerRadius: 9)
                    .fill(isSelected ? AppPalette.selectedSurface : Color.clear)
            )
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private var conversationWorkspace: some View {
        VStack(spacing: 0) {
            conversationHeader
            Divider()

            VStack(spacing: 0) {
                Spacer(minLength: 36)
                welcomeContent
                Spacer(minLength: 28)
                composer
            }
            .padding(.horizontal, 28)
            .padding(.bottom, 22)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppPalette.canvas)
    }

    private var conversationHeader: some View {
        HStack(spacing: 10) {
            EmployeePortraitView(
                imageName: activeConversation.avatarImageName,
                fallbackColor: activeConversation.avatarColor,
                fallbackText: String(activeConversation.employeeName.prefix(1)),
                width: 30,
                height: 34,
                cornerRadius: 8
            )

            VStack(alignment: .leading, spacing: 1) {
                Text(activeConversation.employeeName)
                    .appFont(size: 14, weight: .semibold)
                Text(activeConversation.role)
                    .appFont(size: 10)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            headerButton("对话任务", icon: "plus.bubble")
            headerButton("自动任务", icon: "clock.arrow.circlepath")

            Button {
                withAnimation(.easeInOut(duration: 0.2)) {
                    showCapabilityPanel.toggle()
                }
            } label: {
                Label("任务列表", systemImage: "sidebar.right")
                    .appFont(size: 12, weight: .medium)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(
                        RoundedRectangle(cornerRadius: 7)
                            .fill(showCapabilityPanel ? Color.blue.opacity(0.14) : AppPalette.mutedSurface)
                    )
                    .foregroundStyle(showCapabilityPanel ? .blue : .primary)
            }
            .buttonStyle(.plain)
        }
        .padding(.leading, 18)
        .padding(.trailing, 16)
        .padding(.top, FloatingSidebarMetrics.rightContentTopInset)
        .padding(.bottom, 10)
    }

    private func headerButton(_ title: String, icon: String) -> some View {
        Button {} label: {
            Label(title, systemImage: icon)
                .appFont(size: 12, weight: .medium)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 7))
        }
        .buttonStyle(.plain)
    }

    private var welcomeContent: some View {
        VStack(spacing: 14) {
            EmployeePortraitView(
                imageName: activeConversation.avatarImageName,
                fallbackColor: activeConversation.avatarColor,
                fallbackText: String(activeConversation.employeeName.prefix(1)),
                width: 78,
                height: 90,
                cornerRadius: 18
            )
            .shadow(color: activeConversation.avatarColor.opacity(0.16), radius: 18, y: 8)

            Text("你好，今天我能帮你什么？")
                .appFont(size: 24, weight: .bold)

            Text("我是 \(activeConversation.employeeName)，一名\(activeConversation.role)，可以完成你指派的各类任务。")
                .appFont(size: 13)
                .foregroundStyle(.secondary)

            VStack(spacing: 9) {
                ForEach(suggestions) { suggestion in
                    Button {
                        messageText = suggestion.text
                    } label: {
                        HStack(spacing: 11) {
                            Image(systemName: "sparkles")
                                .appFont(size: 13)
                                .foregroundStyle(.blue)
                                .frame(width: 18)
                            Text(suggestion.text)
                                .appFont(size: 13)
                                .foregroundStyle(.primary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .lineLimit(2)
                            Image(systemName: "arrow.up.left")
                                .appFont(size: 10)
                                .foregroundStyle(.tertiary)
                        }
                        .padding(.horizontal, 15)
                        .padding(.vertical, 12)
                        .background(AppPalette.card, in: RoundedRectangle(cornerRadius: 11))
                        .overlay(
                            RoundedRectangle(cornerRadius: 11)
                                .stroke(AppPalette.border.opacity(0.8), lineWidth: 0.5)
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .frame(maxWidth: 560)
            .padding(.top, 6)
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("输入消息，@ 选择当前工作区上下文…", text: $messageText, axis: .vertical)
                .textFieldStyle(.plain)
                .appFont(size: 13)
                .lineLimit(1...4)

            HStack(spacing: 12) {
                Button {} label: {
                    Label("选择工作目录", systemImage: "folder.badge.plus")
                        .appFont(size: 12)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)

                Button {} label: {
                    Image(systemName: "plus")
                        .appFont(size: 12, weight: .medium)
                        .foregroundStyle(.secondary)
                }
                .buttonStyle(.plain)

                Spacer()

                Menu("Auto") {
                    Button("自动") {}
                    Button("快速") {}
                    Button("深度思考") {}
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .appFont(size: 12)

                Button {
                    messageText = ""
                } label: {
                    Image(systemName: "arrow.up")
                        .appFont(size: 13, weight: .bold)
                        .foregroundStyle(.white)
                        .frame(width: 30, height: 30)
                        .background(
                            Circle().fill(messageText.isEmpty ? Color.secondary.opacity(0.45) : Color.blue)
                        )
                }
                .buttonStyle(.plain)
                .disabled(messageText.isEmpty)
                .keyboardShortcut(.return, modifiers: .command)
            }
        }
        .padding(14)
        .frame(maxWidth: 760, minHeight: 96, alignment: .topLeading)
        .background(AppPalette.card, in: RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(AppPalette.border, lineWidth: 0.7)
        )
        .shadow(color: .black.opacity(0.07), radius: 16, y: 7)
    }

    private var capabilityPanel: some View {
        VStack(spacing: 0) {
            HStack(spacing: 0) {
                ForEach(CapabilityPanelTab.allCases, id: \.self) { tab in
                    Button {
                        selectedPanelTab = tab
                    } label: {
                        VStack(spacing: 4) {
                            Image(systemName: tab.icon)
                                .appFont(size: 13)
                            Text(tab.label)
                                .appFont(size: 9)
                        }
                        .foregroundStyle(selectedPanelTab == tab ? .blue : .secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 9)
                        .background(
                            selectedPanelTab == tab
                                ? Color.blue.opacity(0.08)
                                : Color.clear
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.top, FloatingSidebarMetrics.rightContentTopInset)

            Divider()

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    switch selectedPanelTab {
                    case .plan:
                        panelSection(title: "执行计划", items: [
                            ("1. 理解需求", "checkmark.circle", Color.green),
                            ("2. 分析影响", "arrow.triangle.branch", Color.blue),
                            ("3. 执行任务", "sparkles", Color.orange),
                            ("4. 验证结果", "checkmark.seal", Color.purple),
                        ])
                    case .mcp:
                        panelSection(title: "可用工具", items: [
                            ("read_file", "doc.text", Color.blue),
                            ("write_file", "doc.badge.plus", Color.green),
                            ("shell", "terminal", Color.orange),
                            ("web_fetch", "globe", Color.cyan),
                        ])
                    case .skills:
                        panelSection(title: "已加载技能", items: [
                            ("planning", "list.bullet.clipboard", Color.blue),
                            ("code-review", "eye", Color.green),
                            ("testing-strategy", "flask", Color.orange),
                        ])
                    case .permissions:
                        panelSection(title: "权限边界", items: [
                            ("工作目录: ~/Projects", "folder.badge.gear", Color.blue),
                            ("Shell: 受限模式", "terminal", Color.orange),
                            ("网络: 允许", "network", Color.green),
                        ])
                    case .knowledge:
                        panelSection(title: "知识库连接", items: [
                            ("Hub API 已连接", "link", Color.green),
                            ("本地文档索引: 128 条", "doc.on.doc", Color.blue),
                        ])
                    }
                }
                .padding(14)
            }
        }
        .frame(width: 240)
        .background(.ultraThinMaterial)
    }

    private func panelSection(title: String, items: [(String, String, Color)]) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .appFont(size: 13, weight: .semibold)
                .foregroundStyle(.secondary)

            ForEach(items, id: \.0) { item in
                HStack(spacing: 8) {
                    Image(systemName: item.1)
                        .appFont(size: 12)
                        .foregroundStyle(item.2)
                        .frame(width: 18)
                    Text(item.0)
                        .appFont(size: 12)
                }
                .padding(.vertical, 5)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 7))
            }
        }
    }
}
