import SwiftUI
import Observation

/// 会话级聊天状态：独立于视图生命周期，按 Agent 缓存常驻进程。
/// ConversationView 随页面切换销毁重建，但流式生成的 Task 和转写都挂在这里，
/// 切走再切回不丢任何进行中的内容。
@MainActor
@Observable
final class ChatModel {
    private static var cache: [String: ChatModel] = [:]

    static func shared(for employeeId: String, api: APIClient) -> ChatModel {
        if let existing = cache[employeeId] { return existing }
        let model = ChatModel(employeeId: employeeId, api: api)
        cache[employeeId] = model
        return model
    }

    let employeeId: String
    private let api: APIClient

    var transcript: [TranscriptItem] = []
    var streamingReply: String?
    var currentSession: Session?
    var isSending = false
    var expandedThinking: Set<String> = []
    var expandedToolGroups: Set<String> = []
    var attachedFiles: [URL] = []
    var workDirectory: URL? {
        didSet { Self.storeWorkDir(workDirectory, for: employeeId) }
    }

    private var loaded = false

    private init(employeeId: String, api: APIClient) {
        self.employeeId = employeeId
        self.api = api
        self.workDirectory = Self.storedWorkDir(for: employeeId)
    }

    // MARK: - 加载

    /// 进入会话时调用。正在生成或已加载过时直接复用内存态（比库里多过程卡片/进行中流），
    /// 只有首次（含 app 重启后首次）才从库拉历史。
    func openIfNeeded() async {
        guard !employeeId.isEmpty, !isSending, !loaded else { return }
        let sessions = (try? await api.fetchSessions(employeeId: employeeId)) ?? []
        // 拿到会话才算加载成功；后端未启动导致的失败留给下次进入重试
        guard let latest = Self.latestSession(sessions), !isSending else { return }
        loaded = true
        currentSession = latest
        let messages = (try? await api.fetchMessages(employeeId: employeeId, sessionId: latest.id)) ?? []
        guard !isSending else { return }
        transcript = messages.map { .message($0) }
        // 最后一条是用户消息 = 生成可能被打断在服务端继续，轮询等回复落库
        if messages.last?.role == "user" {
            awaitPendingReply(sessionId: latest.id)
        }
    }

    /// ponytail: 2s 轮询兜底（只覆盖 app 重启前未完成的回复）；进程内切换已由本模型常驻解决
    private func awaitPendingReply(sessionId: String) {
        Task {
            for _ in 0..<60 {
                try? await Task.sleep(for: .seconds(2))
                guard currentSession?.id == sessionId, !isSending else { return }
                let messages = (try? await api.fetchMessages(
                    employeeId: employeeId, sessionId: sessionId
                )) ?? []
                if messages.last?.role == "assistant", !isSending {
                    transcript = messages.map { .message($0) }
                    return
                }
            }
        }
    }

    // MARK: - 发送

    func send(_ text: String) {
        guard !text.isEmpty, !isSending, !employeeId.isEmpty else { return }
        let context = contextBlock()
        isSending = true
        transcript.append(.message(Message(
            id: UUID().uuidString, sessionId: currentSession?.id ?? "",
            role: "user", content: text, createdAt: ""
        )))

        Task {
            if currentSession == nil {
                currentSession = try? await api.createSession(
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

            attachedFiles = []  // 会话就绪才清空，创建失败时保留已选附件
            transcript.append(.thinking(id: UUID().uuidString, done: false, text: ""))
            for await event in api.streamMessage(
                employeeId: employeeId, sessionId: session.id, content: text, context: context
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

    // MARK: - 工作目录 / 附件

    /// 拖入或选中的路径：目录设为工作目录，文件加入附件（去重）
    func addDropped(_ urls: [URL]) {
        for url in urls {
            if url.hasDirectoryPath {
                workDirectory = url
            } else if !attachedFiles.contains(url) {
                attachedFiles.append(url)
            }
        }
    }

    /// 隐式环境上下文：工作目录和附件路径只传给引擎，不进对话气泡（本地 agent 可直接读这些路径）
    private func contextBlock() -> String? {
        var parts: [String] = []
        if let dir = workDirectory {
            parts.append("工作目录: \(dir.path)")
        }
        if !attachedFiles.isEmpty {
            parts.append("附件文件:\n" + attachedFiles.map { "- \($0.path)" }.joined(separator: "\n"))
        }
        guard !parts.isEmpty else { return nil }
        return "[环境上下文]（用户在界面选择，路径在本机可直接读取）\n" + parts.joined(separator: "\n")
    }

    private static func storedWorkDir(for employeeId: String) -> URL? {
        guard let dict = UserDefaults.standard.dictionary(forKey: "workDirectories") as? [String: String],
              let path = dict[employeeId] else { return nil }
        return URL(fileURLWithPath: path, isDirectory: true)
    }

    private static func storeWorkDir(_ url: URL?, for employeeId: String) {
        guard !employeeId.isEmpty else { return }
        var dict = (UserDefaults.standard.dictionary(forKey: "workDirectories") as? [String: String]) ?? [:]
        dict[employeeId] = url?.path
        UserDefaults.standard.set(dict, forKey: "workDirectories")
    }

    static func latestSession(_ sessions: [Session]) -> Session? {
        sessions.max(by: {
            ($0.lastMessageAt ?? $0.createdAt) < ($1.lastMessageAt ?? $1.createdAt)
        })
    }
}
