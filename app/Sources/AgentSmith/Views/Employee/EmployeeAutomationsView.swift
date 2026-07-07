import SwiftUI

struct EmployeeAutomationsView: View {
    let employee: Employee

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("自动任务")
                        .appFont(size: 24, weight: .bold)
                    Text("配置定时或事件触发的自动化任务")
                        .appFont(size: 14)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    // new automation
                } label: {
                    Label("新建", systemImage: "plus")
                        .appFont(size: 13, weight: .medium)
                }
                .buttonStyle(.borderedProminent)
                .tint(.blue)
            }

            // Info banner
            HStack(spacing: 10) {
                Image(systemName: "info.circle")
                    .appFont(size: 16)
                    .foregroundStyle(.blue)
                Text("自动任务支持 Cron 定时调度和 Webhook 事件触发两种模式，Agent 将按照预设指令自动执行工作。")
                    .appFont(size: 13)
                    .foregroundStyle(.secondary)
            }
            .padding(14)
            .background(
                RoundedRectangle(cornerRadius: 10)
                    .fill(Color.blue.opacity(0.06))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(Color.blue.opacity(0.15), lineWidth: 1)
            )

            // Empty state
            VStack(spacing: 16) {
                Image(systemName: "clock.arrow.circlepath")
                    .appFont(size: 48)
                    .foregroundStyle(.secondary.opacity(0.3))

                Text("暂无自动任务")
                    .appFont(size: 16, weight: .medium)
                    .foregroundStyle(.secondary)

                Text("创建第一个自动任务，让 Agent 定时执行重复性工作")
                    .appFont(size: 13)
                    .foregroundStyle(.secondary.opacity(0.7))
            }
            .frame(maxWidth: .infinity)
            .padding(.vertical, 60)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(.regularMaterial)
                    .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(style: StrokeStyle(lineWidth: 1, dash: [6, 4]))
                    .foregroundStyle(.secondary.opacity(0.2))
            )
        }
    }
}
