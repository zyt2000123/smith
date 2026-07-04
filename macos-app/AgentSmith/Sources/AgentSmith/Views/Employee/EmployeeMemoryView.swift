import SwiftUI

struct MemoryEvent: Identifiable {
    let id = UUID()
    let color: Color
    let title: String
    let detail: String
    let timestamp: String
}

struct EmployeeMemoryView: View {
    let employee: Employee

    private let memoryContent = """
    # Memory - \u{5C0F}\u{4E01}

    ## \u{5DF2}\u{5B66}\u{4E60}\u{7684}\u{6280}\u{80FD}
    - \u{7EC4}\u{4EF6}\u{67B6}\u{6784}\u{8BBE}\u{8BA1}
    - \u{54CD}\u{5E94}\u{5F0F}\u{5E03}\u{5C40}\u{5B9E}\u{73B0}
    - \u{8BBE}\u{8BA1}\u{7CFB}\u{7EDF}\u{6784}\u{5EFA}

    ## \u{5DE5}\u{4F5C}\u{504F}\u{597D}
    - \u{8BBE}\u{8BA1}\u{4F18}\u{5148}\u{FF0C}\u{518D}\u{5199}\u{4EE3}\u{7801}
    - \u{5C0F}\u{6B65}\u{8FED}\u{4EE3}\u{FF0C}\u{9891}\u{7E41}\u{9A8C}\u{8BC1}
    """

    private let events: [MemoryEvent] = [
        MemoryEvent(color: .green, title: "学习了组件架构", detail: "掌握了 React 组件设计模式", timestamp: "2 天前"),
        MemoryEvent(color: .blue, title: "完成了性能优化", detail: "页面加载速度提升 40%", timestamp: "5 天前"),
        MemoryEvent(color: .purple, title: "建立了设计系统", detail: "统一了颜色、字体和间距规范", timestamp: "1 周前"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("记忆")
                        .font(.system(size: 24, weight: .bold))
                    Text("该员工的长期记忆与学习记录")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    // edit
                } label: {
                    Label("编辑", systemImage: "pencil")
                        .font(.system(size: 13))
                }
                .buttonStyle(.bordered)
            }

            // Code block preview
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("MEMORY.md")
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundColor(.secondary)
                    Spacer()
                    Button {
                        // copy
                    } label: {
                        Image(systemName: "doc.on.doc")
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(Color.secondary.opacity(0.08))

                Text(memoryContent)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundColor(.primary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.secondary.opacity(0.15), lineWidth: 1)
            )

            // Event timeline
            VStack(alignment: .leading, spacing: 16) {
                Text("记忆事件")
                    .font(.system(size: 16, weight: .semibold))

                ForEach(events) { event in
                    HStack(alignment: .top, spacing: 12) {
                        Circle()
                            .fill(event.color)
                            .frame(width: 10, height: 10)
                            .padding(.top, 4)

                        VStack(alignment: .leading, spacing: 2) {
                            HStack {
                                Text(event.title)
                                    .font(.system(size: 14, weight: .medium))
                                Spacer()
                                Text(event.timestamp)
                                    .font(.system(size: 12))
                                    .foregroundColor(.secondary)
                            }
                            Text(event.detail)
                                .font(.system(size: 13))
                                .foregroundColor(.secondary)
                        }
                    }
                    if event.id != events.last?.id {
                        Divider().padding(.leading, 22)
                    }
                }
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
        }
    }
}
