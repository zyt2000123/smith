import SwiftUI

struct WorkRecordView: View {
    let employee: Employee

    @State private var selectedRecordTab = "时间线视图"
    private let recordTabs = ["时间线视图", "对话任务", "自动任务"]

    private let weeks = 20
    private let daysPerWeek = 7

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                Text("工作记录")
                    .appFont(size: 18, weight: .semibold)

                Spacer()

                HStack(spacing: 0) {
                    ForEach(recordTabs, id: \.self) { tab in
                        Button {
                            selectedRecordTab = tab
                        } label: {
                            Text(tab)
                                .appFont(size: 12)
                                .foregroundStyle(selectedRecordTab == tab ? .primary : .secondary)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 5)
                                .background(
                                    selectedRecordTab == tab
                                        ? AnyShapeStyle(.regularMaterial)
                                        : AnyShapeStyle(.clear)
                                    , in: RoundedRectangle(cornerRadius: 6)
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .padding(2)
                .background(
                    RoundedRectangle(cornerRadius: 8)
                        .fill(Color.secondary.opacity(0.08))
                )
            }

            // Stat cards
            HStack(spacing: 12) {
                statCard(title: "入职天数", value: "\(daysSinceJoin)天", icon: "calendar")
                statCard(title: "自动任务", value: "0", icon: "clock.arrow.circlepath")
                statCard(title: "对话任务", value: "0", icon: "bubble.left")
                statCard(title: "已创建的项目", value: "0", icon: "folder")
            }

            // Heatmap
            VStack(alignment: .leading, spacing: 4) {
                HStack(alignment: .top, spacing: 2) {
                    ForEach(0..<weeks, id: \.self) { week in
                        VStack(spacing: 2) {
                            ForEach(0..<daysPerWeek, id: \.self) { day in
                                let intensity = heatmapIntensity(week: week, day: day)
                                RoundedRectangle(cornerRadius: 2)
                                    .fill(heatmapColor(intensity))
                                    .frame(width: 12, height: 12)
                            }
                        }
                    }
                }

                // Legend
                HStack(spacing: 4) {
                    Spacer()
                    Text("少")
                        .appFont(size: 10)
                        .foregroundStyle(.secondary)
                    ForEach(0..<5, id: \.self) { level in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(heatmapColor(Double(level) / 4.0))
                            .frame(width: 12, height: 12)
                    }
                    Text("多")
                        .appFont(size: 10)
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(20)
        .frame(maxWidth: .infinity, alignment: .leading)
        .appCardSurface()
    }

    private var daysSinceJoin: Int {
        Calendar.current.dateComponents([.day], from: employee.joinDate, to: Date()).day ?? 0
    }

    private func statCard(title: String, value: String, icon: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 4) {
                Image(systemName: icon)
                    .appFont(size: 12)
                    .foregroundStyle(.secondary)
                Text(title)
                    .appFont(size: 12)
                    .foregroundStyle(.secondary)
            }
            Text(value)
                .appFont(size: 22, weight: .bold)
                .foregroundStyle(.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(.blue.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
    }

    private func heatmapIntensity(week: Int, day: Int) -> Double {
        // Deterministic pseudo-random pattern for demo
        let seed = (week * 7 + day + employee.id.hashValue) % 100
        if seed < 60 { return 0 }
        if seed < 75 { return 0.25 }
        if seed < 85 { return 0.5 }
        if seed < 95 { return 0.75 }
        return 1.0
    }

    private func heatmapColor(_ intensity: Double) -> Color {
        if intensity <= 0 {
            return Color.secondary.opacity(0.08)
        }
        return Color.blue.opacity(0.15 + intensity * 0.65)
    }
}
