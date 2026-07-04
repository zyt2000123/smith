import SwiftUI

struct TaskItem: Identifiable {
    let id: String
    let name: String
    let source: String
    let status: String
    let createdAt: String
}

struct EmployeeTasksView: View {
    let employee: Employee

    private let tasks: [TaskItem] = [
        TaskItem(id: "TASK-001", name: "实现登录页面", source: "对话", status: "进行中", createdAt: "2024-01-15 10:30"),
        TaskItem(id: "TASK-002", name: "修复导航栏样式", source: "自动", status: "已完成", createdAt: "2024-01-14 14:20"),
        TaskItem(id: "TASK-003", name: "优化首页加载速度", source: "对话", status: "待处理", createdAt: "2024-01-13 09:15"),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("对话任务")
                        .font(.system(size: 24, weight: .bold))
                    Text("该员工执行的所有对话任务记录")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    // new task
                } label: {
                    Label("新建", systemImage: "plus")
                        .font(.system(size: 13, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
            }

            // Date range
            HStack(spacing: 8) {
                Image(systemName: "calendar")
                    .foregroundColor(.secondary)
                Text("2024-01-01 ~ 2024-01-31")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
            }

            // Table
            VStack(spacing: 0) {
                // Header
                HStack(spacing: 0) {
                    tableHeader("ID", width: 100)
                    tableHeader("名称", width: nil)
                    tableHeader("来源", width: 80)
                    tableHeader("状态", width: 80)
                    tableHeader("创建时间", width: 160)
                }
                .padding(.vertical, 10)
                .background(Color.secondary.opacity(0.06))

                Divider()

                // Rows
                ForEach(tasks) { task in
                    HStack(spacing: 0) {
                        Text(task.id)
                            .font(.system(size: 12, design: .monospaced))
                            .foregroundColor(.secondary)
                            .frame(width: 100, alignment: .leading)

                        Text(task.name)
                            .font(.system(size: 13))
                            .frame(maxWidth: .infinity, alignment: .leading)

                        Text(task.source)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .frame(width: 80, alignment: .leading)

                        statusBadge(task.status)
                            .frame(width: 80, alignment: .leading)

                        Text(task.createdAt)
                            .font(.system(size: 12))
                            .foregroundColor(.secondary)
                            .frame(width: 160, alignment: .leading)
                    }
                    .padding(.vertical, 10)

                    Divider()
                }
            }
            .padding(.horizontal, 14)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.secondary.opacity(0.1), lineWidth: 1)
            )
        }
    }

    private func tableHeader(_ title: String, width: CGFloat?) -> some View {
        Group {
            if let width = width {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(width: width, alignment: .leading)
            } else {
                Text(title)
                    .font(.system(size: 12, weight: .medium))
                    .foregroundColor(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func statusBadge(_ status: String) -> some View {
        let color: Color = {
            switch status {
            case "进行中": return .blue
            case "已完成": return .green
            case "待处理": return .orange
            default: return .gray
            }
        }()
        return Text(status)
            .font(.system(size: 11))
            .foregroundColor(color)
            .padding(.horizontal, 8)
            .padding(.vertical, 3)
            .background(
                Capsule().fill(color.opacity(0.12))
            )
    }
}
