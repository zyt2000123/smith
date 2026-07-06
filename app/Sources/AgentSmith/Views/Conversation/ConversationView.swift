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

/// 对话转写项：普通消息 + Agent 过程事件（思考/工具/技能）
enum TranscriptItem: Identifiable {
    case message(Message)
    case thinking(id: String, done: Bool, text: String)
    case tool(id: String, name: String, running: Bool, error: Bool, summary: String)
    case skill(id: String, name: String, status: String)

    var id: String {
        switch self {
        case .message(let m): return "msg-\(m.id)"
        case .thinking(let id, _, _): return "think-\(id)"
        case .tool(let id, _, _, _, _): return "tool-\(id)"
        case .skill(let id, _, _): return "skill-\(id)"
        }
    }
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
    @EnvironmentObject private var apiClient: APIClient
    @State private var messageText = ""
    @State private var selectedConversation: String
    @State private var showCapabilityPanel = false
    @State private var selectedPanelTab: CapabilityPanelTab = .plan
    @State private var conversations: [ConversationItem] = []
    @State private var transcript: [TranscriptItem] = []
    @State private var streamingReply: String?
    @State private var currentSession: Session?
    @State private var isSending = false
    @State private var expandedThinking: Set<String> = []
    @State private var expandedToolGroups: Set<String> = []

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
        conversations.first(where: { $0.id == selectedConversation })
            ?? conversations.first
            ?? ConversationItem(
                id: "", employeeName: "加载中", role: "",
                avatarImageName: nil, avatarColor: .gray,
                preview: "", timestamp: ""
            )
    }

    // 主侧边栏由 ContentView 常驻提供，这里只渲染右侧内容区
    var body: some View {
        HStack(spacing: 0) {
            conversationWorkspace

            if showCapabilityPanel {
                Divider()
                capabilityPanel
                    .transition(.move(edge: .trailing).combined(with: .opacity))
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(AppPalette.canvas)
        .task { await loadConversations() }
    }

    // MARK: - Data Loading

    private func loadConversations() async {
        guard let employees = try? await apiClient.fetchEmployees() else { return }
        var items: [ConversationItem] = []
        for emp in employees {
            let sessions = (try? await apiClient.fetchSessions(employeeId: emp.id)) ?? []
            let latest = Self.latestSession(sessions)
            items.append(ConversationItem(
                id: emp.id,
                employeeName: emp.name,
                role: emp.localizedRole,
                avatarImageName: emp.avatarImageName,
                avatarColor: emp.avatarColor,
                preview: latest?.lastMessagePreview ?? emp.description,
                timestamp: Self.relativeTime(latest?.lastMessageAt ?? latest?.createdAt)
            ))
        }
        conversations = items

        // ContentView 传入的可能是遗留 id（如 "ivy"），按Agent名回退解析
        if !items.contains(where: { $0.id == selectedConversation }) {
            let key = selectedConversation.lowercased()
            selectedConversation = items.first(where: { $0.employeeName.lowercased() == key })?.id
                ?? items.first?.id ?? ""
        }
        await openConversation(selectedConversation)
    }

    private func openConversation(_ employeeId: String) async {
        selectedConversation = employeeId
        transcript = []
        streamingReply = nil
        currentSession = nil
        guard !employeeId.isEmpty else { return }
        let sessions = (try? await apiClient.fetchSessions(employeeId: employeeId)) ?? []
        guard let latest = Self.latestSession(sessions) else { return }
        currentSession = latest
        let messages = (try? await apiClient.fetchMessages(employeeId: employeeId, sessionId: latest.id)) ?? []
        transcript = messages.map { .message($0) }
    }

    /// 收尾未完成的"思考中"行：有内容则标记完成，无内容直接移除（避免空壳"思考完成"）
    private func finishThinking(fill text: String = "") {
        guard case .thinking(let id, false, let existing) = transcript.last else { return }
        let content = text.isEmpty ? existing : text
        if content.isEmpty {
            transcript.removeLast()
        } else {
            transcript[transcript.count - 1] = .thinking(id: id, done: true, text: content)
        }
    }

    private func send() {
        let text = messageText.trimmingCharacters(in: .whitespacesAndNewlines)
        let employeeId = activeConversation.id
        guard !text.isEmpty, !isSending, !employeeId.isEmpty else { return }
        messageText = ""
        isSending = true
        transcript.append(.message(Message(
            id: UUID().uuidString, sessionId: currentSession?.id ?? "",
            role: "user", content: text, createdAt: ""
        )))

        Task {
            if currentSession == nil {
                currentSession = try? await apiClient.createSession(
                    employeeId: employeeId, title: String(text.prefix(20))
                )
            }
            guard let session = currentSession else {
                transcript.append(.message(Message(
                    id: UUID().uuidString, sessionId: "",
                    role: "assistant", content: "⚠️ 无法创建会话，请确认后端已启动（端口 8140）。", createdAt: ""
                )))
                isSending = false
                return
            }

            transcript.append(.thinking(id: UUID().uuidString, done: false, text: ""))
            for await event in apiClient.streamMessage(
                employeeId: employeeId, sessionId: session.id, content: text
            ) {
                switch event {
                case .thinking(let thought, let done):
                    if done {
                        finishThinking(fill: thought)
                    } else {
                        finishThinking()
                        transcript.append(.thinking(id: UUID().uuidString, done: false, text: ""))
                    }
                case .toolCall(let id, let name):
                    finishThinking()
                    transcript.append(.tool(id: id, name: name, running: true, error: false, summary: ""))
                case .toolResult(let id, let error, let summary):
                    if let idx = transcript.lastIndex(where: { $0.id == "tool-\(id)" }),
                       case .tool(_, let name, _, _, _) = transcript[idx] {
                        transcript[idx] = .tool(id: id, name: name, running: false, error: error, summary: summary)
                    }
                case .skill(let name, let status):
                    finishThinking()
                    transcript.append(.skill(id: UUID().uuidString, name: name, status: status))
                case .text(let chunk):
                    finishThinking()
                    streamingReply = (streamingReply ?? "") + chunk
                case .done:
                    break
                }
            }
            finishThinking()
            let reply = streamingReply ?? ""
            streamingReply = nil
            transcript.append(.message(Message(
                id: UUID().uuidString, sessionId: session.id,
                role: "assistant",
                content: reply.isEmpty ? "⚠️ 未收到回复，请检查后端日志。" : reply,
                createdAt: ""
            )))
            isSending = false
        }
    }

    private static func latestSession(_ sessions: [Session]) -> Session? {
        sessions.max(by: {
            ($0.lastMessageAt ?? $0.createdAt) < ($1.lastMessageAt ?? $1.createdAt)
        })
    }

    private static func relativeTime(_ iso: String?) -> String {
        guard let iso else { return "" }
        let f = ISO8601DateFormatter()
        f.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        var date = f.date(from: iso)
        if date == nil {
            f.formatOptions = [.withInternetDateTime]
            date = f.date(from: iso)
        }
        guard let date else { return "" }
        let rel = RelativeDateTimeFormatter()
        rel.locale = Locale(identifier: "zh_CN")
        rel.unitsStyle = .short
        return rel.localizedString(for: date, relativeTo: Date())
    }

    private var conversationWorkspace: some View {
        VStack(spacing: 0) {
            conversationHeader
            Divider()

            VStack(spacing: 0) {
                if transcript.isEmpty && streamingReply == nil {
                    Spacer(minLength: 36)
                    welcomeContent
                    Spacer(minLength: 28)
                } else {
                    messageList
                }
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

    /// 渲染行：连续 ≥2 个已完成的工具卡片收拢成一个折叠组
    private enum DisplayRow: Identifiable {
        case item(TranscriptItem)
        case toolGroup(id: String, tools: [TranscriptItem])

        var id: String {
            switch self {
            case .item(let t): return t.id
            case .toolGroup(let id, _): return "group-\(id)"
            }
        }
    }

    private var displayRows: [DisplayRow] {
        var rows: [DisplayRow] = []
        var buffer: [TranscriptItem] = []
        func flush() {
            if buffer.count >= 2 {
                rows.append(.toolGroup(id: buffer[0].id, tools: buffer))
            } else {
                rows.append(contentsOf: buffer.map { .item($0) })
            }
            buffer = []
        }
        for item in transcript {
            if case .tool(_, _, false, _, _) = item {
                buffer.append(item)
            } else {
                flush()
                rows.append(.item(item))
            }
        }
        flush()
        return rows
    }

    private var messageList: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 12) {
                    ForEach(displayRows) { row in
                        displayRowView(row)
                            .id(row.id)
                    }
                    if let streaming = streamingReply {
                        messageBubble(role: "assistant", content: streaming)
                            .id("streaming")
                    }
                }
                .padding(.vertical, 20)
                .frame(maxWidth: 760)
                .frame(maxWidth: .infinity)
            }
            .onChange(of: transcript.count) {
                if let last = displayRows.last {
                    proxy.scrollTo(last.id, anchor: .bottom)
                }
            }
            .onChange(of: streamingReply) {
                if streamingReply != nil {
                    proxy.scrollTo("streaming", anchor: .bottom)
                }
            }
        }
    }

    @ViewBuilder
    private func displayRowView(_ row: DisplayRow) -> some View {
        switch row {
        case .item(let item):
            transcriptRow(item)
        case .toolGroup(let gid, let tools):
            VStack(alignment: .leading, spacing: 6) {
                Button {
                    if expandedToolGroups.contains(gid) {
                        expandedToolGroups.remove(gid)
                    } else {
                        expandedToolGroups.insert(gid)
                    }
                } label: {
                    HStack(spacing: 8) {
                        RoundedRectangle(cornerRadius: 1.5)
                            .fill(Color.blue.opacity(0.55))
                            .frame(width: 3, height: 14)
                        Text("\(tools.count) 个工具")
                            .appFont(size: 12, weight: .medium)
                            .foregroundStyle(.primary)
                        Spacer()
                        Image(systemName: expandedToolGroups.contains(gid) ? "chevron.down" : "chevron.right")
                            .appFont(size: 10)
                            .foregroundStyle(.tertiary)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 9)
                    .frame(maxWidth: 560)
                    .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 9))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)

                if expandedToolGroups.contains(gid) {
                    VStack(alignment: .leading, spacing: 6) {
                        ForEach(tools) { tool in
                            transcriptRow(tool)
                        }
                    }
                    .padding(.leading, 12)
                }
            }
        }
    }

    @ViewBuilder
    private func transcriptRow(_ item: TranscriptItem) -> some View {
        switch item {
        case .message(let m):
            messageBubble(role: m.role, content: m.content)
        case .thinking(let id, let done, let text):
            VStack(alignment: .leading, spacing: 6) {
                if done {
                    Button {
                        if expandedThinking.contains(id) {
                            expandedThinking.remove(id)
                        } else {
                            expandedThinking.insert(id)
                        }
                    } label: {
                        HStack(spacing: 4) {
                            Image(systemName: expandedThinking.contains(id) ? "chevron.down" : "chevron.right")
                                .appFont(size: 9)
                            Text("思考完成")
                        }
                        .appFont(size: 11)
                        .foregroundStyle(.secondary)
                        .italic()
                    }
                    .buttonStyle(.plain)

                    if expandedThinking.contains(id) {
                        Text(text)
                            .appFont(size: 12)
                            .foregroundStyle(.secondary)
                            .italic()
                            .textSelection(.enabled)
                            .padding(.leading, 10)
                            .overlay(alignment: .leading) {
                                RoundedRectangle(cornerRadius: 1)
                                    .fill(AppPalette.border)
                                    .frame(width: 2)
                            }
                    }
                } else {
                    HStack(spacing: 6) {
                        ProgressView().controlSize(.mini)
                        Text("思考中…")
                    }
                    .appFont(size: 11)
                    .foregroundStyle(.secondary)
                    .italic()
                }
            }
            .padding(.leading, 4)
        case .tool(_, let name, let running, let error, let summary):
            HStack(spacing: 8) {
                Image(systemName: "wrench.and.screwdriver")
                    .appFont(size: 11)
                    .foregroundStyle(.blue)
                Text(name)
                    .font(.system(size: 12, design: .monospaced))
                if running {
                    ProgressView().controlSize(.mini)
                } else {
                    Image(systemName: error ? "xmark.circle.fill" : "checkmark.circle.fill")
                        .appFont(size: 11)
                        .foregroundStyle(error ? .red : .green)
                }
                if !running && !summary.isEmpty {
                    Text(summary)
                        .appFont(size: 11)
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 12)
            .padding(.vertical, 8)
            .frame(maxWidth: 560, alignment: .leading)
            .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 9))
            .overlay(
                RoundedRectangle(cornerRadius: 9)
                    .stroke(AppPalette.border.opacity(0.6), lineWidth: 0.5)
            )
        case .skill(_, let name, let status):
            HStack(spacing: 6) {
                Image(systemName: status == "start" ? "sparkles" : "checkmark.seal")
                    .appFont(size: 11)
                    .foregroundStyle(.purple)
                Text(status == "start" ? "技能 · \(name)" : "已完成 \(name)")
                    .appFont(size: 11, weight: .medium)
                    .foregroundStyle(.secondary)
            }
            .padding(.leading, 4)
        }
    }

    private func messageBubble(role: String, content: String) -> some View {
        let isUser = role == "user"
        return HStack {
            if isUser { Spacer(minLength: 80) }
            Group {
                if isUser {
                    Text(content).appFont(size: 13)
                } else {
                    MarkdownText(content: content)
                }
            }
                .textSelection(.enabled)
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(
                    isUser ? Color.blue.opacity(0.13) : AppPalette.card,
                    in: RoundedRectangle(cornerRadius: 12)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(AppPalette.border.opacity(0.6), lineWidth: 0.5)
                )
            if !isUser { Spacer(minLength: 80) }
        }
    }

    private var composer: some View {
        VStack(alignment: .leading, spacing: 10) {
            TextField("输入消息，@ 选择当前工作区上下文…", text: $messageText, axis: .vertical)
                .textFieldStyle(.plain)
                .appFont(size: 13)
                .lineLimit(1...4)
                .onSubmit { send() }

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
                    send()
                } label: {
                    Image(systemName: isSending ? "hourglass" : "arrow.up")
                        .appFont(size: 13, weight: .bold)
                        .foregroundStyle(.white)
                        .frame(width: 30, height: 30)
                        .background(
                            Circle().fill(
                                messageText.isEmpty || isSending
                                    ? Color.secondary.opacity(0.45) : Color.blue
                            )
                        )
                }
                .buttonStyle(.plain)
                .disabled(messageText.isEmpty || isSending)
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
