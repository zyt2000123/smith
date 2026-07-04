import SwiftUI

struct SkillItem: Identifiable {
    let id = UUID()
    let name: String
    let description: String
    let isActive: Bool
}

struct EmployeeSkillsView: View {
    let employee: Employee

    private let skills: [SkillItem] = [
        SkillItem(name: "planning", description: "需求分析、方案规划与任务拆解", isActive: true),
        SkillItem(name: "code-review", description: "代码审查、质量把关与改进建议", isActive: true),
        SkillItem(name: "testing-strategy", description: "测试策略设计与覆盖率分析", isActive: true),
        SkillItem(name: "sde-debug", description: "问题定位、根因分析与修复验证", isActive: true),
        SkillItem(name: "architecture", description: "系统架构设计与技术选型", isActive: true),
        SkillItem(name: "system-design", description: "模块设计、接口定义与数据建模", isActive: false),
    ]

    private let columns = [
        GridItem(.flexible(), spacing: 16),
        GridItem(.flexible(), spacing: 16),
        GridItem(.flexible(), spacing: 16),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("技能")
                        .appFont(size: 24, weight: .bold)
                    Text("管理该Agent可使用的技能模块")
                        .appFont(size: 14)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    // add skill
                } label: {
                    Label("添加技能", systemImage: "plus")
                        .appFont(size: 13, weight: .medium)
                }
                .buttonStyle(.borderedProminent)
                .tint(.blue)
            }

            LazyVGrid(columns: columns, spacing: 16) {
                ForEach(skills) { skill in
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text(skill.name)
                                .appFont(size: 14, weight: .semibold)
                            Spacer()
                            Circle()
                                .fill(skill.isActive ? Color.green : Color.gray.opacity(0.4))
                                .frame(width: 8, height: 8)
                        }
                        Text(skill.description)
                            .appFont(size: 12)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 10)
                            .fill(.regularMaterial)
                            .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 10)
                            .stroke(Color.secondary.opacity(0.1), lineWidth: 1)
                    )
                }
            }
        }
    }
}
