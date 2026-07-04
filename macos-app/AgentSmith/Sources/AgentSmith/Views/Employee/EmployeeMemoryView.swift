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

    private let events: [MemoryEvent] = [
        MemoryEvent(color: .blue, title: "学习了组件架构", detail: "掌握了 React 组件设计模式", timestamp: "2 天前"),
        MemoryEvent(color: .cyan, title: "完成了性能优化", detail: "页面加载速度提升 40%", timestamp: "5 天前"),
        MemoryEvent(color: .indigo, title: "建立了设计系统", detail: "统一了颜色、字体和间距规范", timestamp: "1 周前"),
    ]

    private var memoryContent: String {
        """
        # Memory - \(employee.name)

        ## Learned Skills
        - Component architecture
        - Responsive layouts
        - Design system patterns

        ## Work Preferences
        - Design first, then code
        - Small iterations with fast validation
        """
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("记忆")
                        .font(.system(size: 24, weight: .bold))
                    Text("该Agent的长期记忆与学习记录")
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    // edit
                } label: {
                    Label("编辑", systemImage: "pencil")
                        .font(.system(size: 13))
                }
                .buttonStyle(.bordered)
                .tint(.blue)
            }

            // Code block preview
            VStack(alignment: .leading, spacing: 0) {
                HStack {
                    Text("MEMORY.md")
                        .font(.system(size: 12, weight: .medium, design: .monospaced))
                        .foregroundStyle(.secondary)
                    Spacer()
                    Button {
                        // copy
                    } label: {
                        Image(systemName: "doc.on.doc")
                            .font(.system(size: 12))
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                }
                .padding(.horizontal, 14)
                .padding(.vertical, 10)
                .background(.blue.opacity(0.06))

                Text(memoryContent)
                    .font(.system(size: 12, design: .monospaced))
                    .foregroundStyle(.primary)
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(.blue.opacity(0.12), lineWidth: 1)
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
                                    .foregroundStyle(.secondary)
                            }
                            Text(event.detail)
                                .font(.system(size: 13))
                                .foregroundStyle(.secondary)
                        }
                    }
                    if event.id != events.last?.id {
                        Divider().padding(.leading, 22)
                    }
                }
            }
            .padding(16)
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        }
    }
}
