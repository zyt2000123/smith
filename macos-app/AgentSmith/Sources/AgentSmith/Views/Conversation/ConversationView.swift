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

struct ConversationView: View {
    @State private var messageText = ""
    @State private var selectedConversation: UUID?

    private let conversations: [ConversationItem] = [
        ConversationItem(employeeName: "小丁", avatarColor: .green, preview: "好的，我来看看这个组件的实现...", timestamp: "刚刚"),
        ConversationItem(employeeName: "T", avatarColor: .blue, preview: "API 接口已经部署完成", timestamp: "5 分钟前"),
        ConversationItem(employeeName: "小凯", avatarColor: .orange, preview: "测试用例全部通过", timestamp: "1 小时前"),
    ]

    private let suggestions: [SuggestionCard] = [
        SuggestionCard(text: "帮我实现一个响应式的导航栏组件"),
        SuggestionCard(text: "分析一下当前项目的代码质量"),
        SuggestionCard(text: "帮我写一个数据库迁移脚本"),
    ]

    var body: some View {
        HStack(spacing: 0) {
            // Left: conversation list
            VStack(spacing: 0) {
                HStack {
                    Text("对话")
                        .font(.system(size: 16, weight: .semibold))
                    Spacer()
                    Button {
                        // new conversation
                    } label: {
                        Image(systemName: "square.and.pencil")
                            .font(.system(size: 14))
                    }
                    .buttonStyle(.plain)
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
                                            .foregroundColor(.white)
                                    }

                                    VStack(alignment: .leading, spacing: 3) {
                                        HStack {
                                            Text(conv.employeeName)
                                                .font(.system(size: 13, weight: .medium))
                                                .foregroundColor(.primary)
                                            Spacer()
                                            Text(conv.timestamp)
                                                .font(.system(size: 11))
                                                .foregroundColor(.secondary)
                                        }
                                        Text(conv.preview)
                                            .font(.system(size: 12))
                                            .foregroundColor(.secondary)
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
            .background(Color(nsColor: .controlBackgroundColor))

            Divider()

            // Center: chat area
            VStack(spacing: 0) {
                Spacer()

                // Greeting
                VStack(spacing: 16) {
                    ZStack {
                        Circle()
                            .fill(Color.green.gradient)
                            .frame(width: 56, height: 56)
                        Text("丁")
                            .font(.system(size: 24, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    Text("你好，今天我能帮你什么？")
                        .font(.system(size: 20, weight: .medium))

                    // Suggestion cards
                    HStack(spacing: 12) {
                        ForEach(suggestions) { suggestion in
                            Button {
                                messageText = suggestion.text
                            } label: {
                                HStack(spacing: 8) {
                                    Image(systemName: "sparkles")
                                        .font(.system(size: 12))
                                        .foregroundColor(.accentColor)
                                    Text(suggestion.text)
                                        .font(.system(size: 13))
                                        .foregroundColor(.primary)
                                        .lineLimit(2)
                                        .multilineTextAlignment(.leading)
                                }
                                .padding(12)
                                .frame(maxWidth: .infinity, alignment: .leading)
                                .background(
                                    RoundedRectangle(cornerRadius: 10)
                                        .fill(Color(nsColor: .controlBackgroundColor))
                                )
                                .overlay(
                                    RoundedRectangle(cornerRadius: 10)
                                        .stroke(Color.secondary.opacity(0.12), lineWidth: 1)
                                )
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(.horizontal, 40)
                }

                Spacer()

                // Input area
                VStack(spacing: 10) {
                    HStack(spacing: 8) {
                        Button {
                            // select directory
                        } label: {
                            Label("选择工作目录", systemImage: "folder")
                                .font(.system(size: 12))
                                .foregroundColor(.secondary)
                        }
                        .buttonStyle(.plain)

                        Spacer()

                        Text("Auto")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundColor(.accentColor)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(
                                Capsule().fill(Color.accentColor.opacity(0.1))
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
                                    .fill(Color(nsColor: .controlBackgroundColor))
                            )
                            .overlay(
                                RoundedRectangle(cornerRadius: 10)
                                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
                            )

                        Button {
                            // send
                        } label: {
                            Image(systemName: "arrow.up.circle.fill")
                                .font(.system(size: 28))
                                .foregroundColor(messageText.isEmpty ? .secondary : .accentColor)
                        }
                        .buttonStyle(.plain)
                        .disabled(messageText.isEmpty)
                    }
                }
                .padding(16)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))
        }
    }
}
