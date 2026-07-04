import SwiftUI

struct MemoryTimelineNode: Identifiable {
    let id = UUID()
    let color: Color
    let label: String
    let skill: String
}

struct MemoryTimelineView: View {
    let employee: Employee

    private let nodes: [MemoryTimelineNode] = [
        MemoryTimelineNode(color: .green, label: "学到新技能", skill: "组件架构"),
        MemoryTimelineNode(color: .blue, label: "学到新技能", skill: "状态管理"),
        MemoryTimelineNode(color: .purple, label: "学到新技能", skill: "性能优化"),
        MemoryTimelineNode(color: .orange, label: "学到新技能", skill: "测试策略"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("记忆时间线")
                .font(.system(size: 18, weight: .semibold))

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 0) {
                    ForEach(Array(nodes.enumerated()), id: \.element.id) { index, node in
                        HStack(spacing: 0) {
                            VStack(spacing: 6) {
                                Circle()
                                    .fill(node.color)
                                    .frame(width: 14, height: 14)
                                    .overlay(
                                        Circle()
                                            .stroke(node.color.opacity(0.3), lineWidth: 3)
                                    )

                                Text(node.label)
                                    .font(.system(size: 11))
                                    .foregroundColor(.secondary)
                                Text(node.skill)
                                    .font(.system(size: 12, weight: .medium))
                                    .foregroundColor(.primary)
                            }

                            if index < nodes.count - 1 {
                                Rectangle()
                                    .fill(Color.secondary.opacity(0.2))
                                    .frame(width: 60, height: 2)
                                    .offset(y: -18)
                            }
                        }
                    }
                }
                .padding(.vertical, 10)
                .padding(.horizontal, 8)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(nsColor: .controlBackgroundColor))
                .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
        )
    }
}
