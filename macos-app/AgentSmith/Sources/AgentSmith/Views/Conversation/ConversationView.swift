import SwiftUI

struct ConversationItem: Identifiable {
    let id = UUID()
    let employeeName: String
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
    @State private var messageText = ""
    @State private var selectedConversation: UUID?
    @State private var showCapabilityPanel = false
    @State private var selectedPanelTab: CapabilityPanelTab = .plan

    private let conversations: [ConversationItem] = [
        ConversationItem(employeeName: "Luna", avatarColor: .green, preview: "好的，我来看看这个组件的实现...", timestamp: "刚刚"),
        ConversationItem(employeeName: "Theo", avatarColor: .blue, preview: "API 接口已经部署完成", timestamp: "5 分钟前"),
        ConversationItem(employeeName: "Ivy", avatarColor: .purple, preview: "版本范围已经同步到路线图里。", timestamp: "1 小时前"),
    ]

    private let suggestions: [SuggestionCard] = [
        SuggestionCard(text: "帮我实现一个响应式的导航栏组件"),
        SuggestionCard(text: "分析一下当前项目的代码质量"),
        SuggestionCard(text: "帮我写一个数据库迁移脚本"),
    ]

    var body: some View {
        HStack(spacing: 0) {
            VStack(spacing: 0) {
                HStack {
                    Text("对话")
                        .font(.system(size: 16, weight: .semibold))
                    Spacer()
                    Button {
                    } label: {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 14))
                    }
                    .buttonStyle(.plain)
                    .tint(.blue)
                }
                .padding(14)

                Divider()

                ScrollView {
                    VStack(spacing: 0) {
                        ForEach(conversations) { conv in
                            Button {
                                selectedConversation = conv.id
                            } label: {
                                HStack(spacing: 10) {
                                    ZStack {
                                        Circle()
                                            .fill(conv.avatarColor.gradient)
                                            .frame(width: 36, height: 36)
                                        Text(String(conv.employeeName.prefix(1)))
                                            .font(.system(size: 14, weight: .semibold))
                                            .foregroundStyle(.white)
                                    }

                                    VStack(alignment: .leading, spacing: 3) {
                                        HStack {
                                            Text(conv.employeeName)
                                                .font(.system(size: 13, weight: .medium))
                                                .foregroundStyle(.primary)
                                            Spacer()
                                            Text(conv.timestamp)
                                                .font(.system(size: 11))
                                                .foregroundStyle(.secondary)
                                        }
                                        Text(conv.preview)
                                            .font(.system(size: 12))
                                            .foregroundStyle(.secondary)
                                            .lineLimit(1)
                                    }
                                }
                                .padding(.horizontal, 14)
                                .padding(.vertical, 10)
                                .background(
                                    selectedConversation == conv.id
                                        ? Color.accentColor.opacity(0.08)
                                        : Color.clear
                                )
                            }
                            .buttonStyle(.plain)

                            Divider().padding(.leading, 60)
                        }
                    }
                }
            }
            .frame(width: 280)
            .background(.ultraThinMaterial)

            Divider()

            VStack(spacing: 0) {
                HStack(spacing: 10) {
                    Spacer()
                    Button {} label: {
                        Label("创建对话任务", systemImage: "plus.bubble")
                            .font(.system(size: 12))
                    }
                    .buttonStyle(.bordered)
                    .tint(.blue)
                    .controlSize(.small)

                    Button {} label: {
                        Label("创建自动任务", systemImage: "clock.arrow.circlepath")
                            .font(.system(size: 12))
                    }
                    .buttonStyle(.bordered)
                    .tint(.blue)
                    .controlSize(.small)

                    Button {
                        withAnimation(.easeInOut(duration: 0.2)) {
                            showCapabilityPanel.toggle()
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: "sidebar.right")
                            Text("任务列表")
                        }
                        .font(.system(size: 12))
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(showCapabilityPanel ? Color.blue : Color.clear)
                        )
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(.regularMaterial)
                                .opacity(showCapabilityPanel ? 0 : 1)
                        )
                        .foregroundStyle(showCapabilityPanel ? .white : .primary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 16)
                .padding(.vertical, 10)

                Divider()

                Spacer()

                VStack(spacing: 16) {
                    ZStack {
                        Circle()
                            .fill(Color.blue.gradient)
                            .frame(width: 56, height: 56)
                        Text("丁")
                            .font(.system(size: 24, weight: .semibold))
                            .foregroundStyle(.white)
                    }

                    Text("你好，今天我能帮你什么？")
                        .font(.system(size: 20, weight: .medium))

                    HStack(spacing: 12) {
                        ForEach(suggestions) { suggestion in
                            Button {
                                messageText = suggestion.text
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "sparkles")
                                        .font(.system(size: 12))
                                        .foregroundStyle(.blue)
                                    Text(suggestion.text)
                                        .font(.system(size: 13))
                                        .foregroundStyle(.primary)
                                        .lineLimit(2)
                                        .multilineTextAlignment(.leading)
                                }
                                .padding(12)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(.regularMaterial)
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 40)
                }

                Spacer()

                VStack(spacing: 10) {
                    HStack(spacing: 8) {
                        Button {
                        } label: {
                            Label("选择工作目录", systemImage: "folder")
                                .font(.system(size: 12))
                                .foregroundStyle(.secondary)
                        }
                        .buttonStyle(.plain)

                        Spacer()

                        Text("Auto")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.blue)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(
                                Capsule().fill(Color.blue.opacity(0.1))
                            )
                    }

                    HStack(spacing: 10) {
                        TextField("输入消息...", text: $messageText)
                            .textFieldStyle(.plain)
                            .font(.system(size: 14))
                            .padding(.horizontal, 14)
                            .padding(.vertical, 10)
                            .background(
                                RoundedRectangle(cornerRadius: 10)
                                    .fill(.regularMaterial)
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 10)
                                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
                            )

                        Button {
                        } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 28))
                                .foregroundStyle(messageText.isEmpty ? Color.secondary : Color.blue)
                        }
                        .buttonStyle(.plain)
                        .disabled(messageText.isEmpty)
                    }
                }
                .padding(16)
                .background(.regularMaterial)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))

            if showCapabilityPanel {
                Divider()
                capabilityPanel
            }
        }
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
                                .font(.system(size: 14))
                            Text(tab.label)
                                .font(.system(size: 10))
                        }
                        .foregroundStyle(selectedPanelTab == tab ? .blue : .secondary)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)
                        .background(
                            selectedPanelTab == tab
                                ? Color.blue.opacity(0.08)
                                : Color.clear
                        )
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding(.horizontal, 4)
            .padding(.top, 8)

            Divider()
                .padding(.top, 4)

            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    switch selectedPanelTab {
                    case .plan:
                        panelSection(title: "执行计划", items: [
                            ("1. 理解需求", "checkmark.circle", Color.green),
                            ("2. 分析影响", "arrow.triangle.branch", Color.blue),
                            ("3. 编写代码", "chevron.left.forwardslash.chevron.right", Color.orange),
                            ("4. 验证测试", "flask", Color.purple),
                        ])
                    case .mcp:
                        panelSection(title: "可用工具", items: [
                            ("read_file", "doc.text", Color.blue),
                            ("write_file", "doc.badge.plus", Color.green),
                            ("shell", "terminal", Color.orange),
                            ("search_knowledge", "magnifyingglass", Color.purple),
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
                .font(.system(size: 13, weight: .semibold))
                .foregroundStyle(.secondary)

            ForEach(items, id: \.0) { item in
                HStack(spacing: 8) {
                    Image(systemName: item.1)
                        .font(.system(size: 12))
                        .foregroundStyle(item.2)
                        .frame(width: 18)
                    Text(item.0)
                        .font(.system(size: 13))
                }
                .padding(.vertical, 4)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(.regularMaterial)
                )
            }
        }
    }
}
