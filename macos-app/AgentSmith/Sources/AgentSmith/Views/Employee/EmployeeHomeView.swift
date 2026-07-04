import SwiftUI

struct EmployeeHomeView: View {
    let employee: Employee

    private var skillTags: [String] { employee.capabilities }
    private var workStyles: [String] { employee.workStyles }
    private let rawFiles = ["IDENTITY.md", "BIBLE.md", "MEMORY.md", "PERSONA.md"]

    var body: some View {
        VStack(alignment: .leading, spacing: 24) {
            identitySection
            WorkRecordView(employee: employee)
            MemoryTimelineView(employee: employee)
            aboutMeSection
            skillsAndToolsSection
            rawFilesSection
        }
    }

    // MARK: - Identity
    private var identitySection: some View {
        HStack(alignment: .top, spacing: 20) {
            // Tilted avatar
            ZStack {
                RoundedRectangle(cornerRadius: 20)
                    .fill(employee.avatarColor.gradient)
                    .frame(width: 80, height: 80)
                    .rotationEffect(.degrees(-6))
                    .shadow(color: employee.avatarColor.opacity(0.3), radius: 10, y: 4)

                Text(String(employee.name.prefix(1)))
                    .font(.system(size: 36, weight: .bold))
                    .foregroundColor(.white)
            }
            .padding(.trailing, 4)

            VStack(alignment: .leading, spacing: 8) {
                HStack(spacing: 10) {
                    Text(employee.name)
                        .font(.system(size: 24, weight: .bold))

                    Text(employee.role)
                        .font(.system(size: 12))
                        .foregroundColor(.secondary)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 4)
                        .background(Capsule().fill(Color.secondary.opacity(0.1)))

                    HStack(spacing: 4) {
                        Circle()
                            .fill(employee.isOnline ? Color.green : Color.gray)
                            .frame(width: 8, height: 8)
                        Text(employee.isOnline ? "在线" : "离线")
                            .font(.system(size: 12))
                            .foregroundColor(employee.isOnline ? .green : .secondary)
                    }
                }

                Text(employee.description)
                    .font(.system(size: 14))
                    .foregroundColor(.secondary)
                    .lineLimit(2)

                Button {
                    // edit action
                } label: {
                    Label("编辑资料", systemImage: "pencil")
                        .font(.system(size: 12))
                }
                .buttonStyle(.bordered)
                .controlSize(.small)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(nsColor: .controlBackgroundColor))
                .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
        )
    }

    // MARK: - About Me
    private var aboutMeSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("关于我")
                .font(.system(size: 18, weight: .semibold))

            HStack(alignment: .top, spacing: 16) {
                // Strengths
                VStack(alignment: .leading, spacing: 10) {
                    Text("我最擅长")
                        .font(.system(size: 14, weight: .medium))
                    VStack(alignment: .leading, spacing: 8) {
                        strengthRow(icon: "paintbrush", text: "精准的视觉还原与界面设计")
                        strengthRow(icon: "square.grid.3x3", text: "组件化架构与设计系统构建")
                        strengthRow(icon: "bolt", text: "交互细节与微动效打磨")
                        strengthRow(icon: "iphone", text: "跨端响应式体验适配")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Work style
                VStack(alignment: .leading, spacing: 10) {
                    Text("工作风格")
                        .font(.system(size: 14, weight: .medium))
                    FlowLayout(spacing: 6) {
                        ForEach(workStyles, id: \.self) { style in
                            Text(style)
                                .font(.system(size: 12))
                                .foregroundColor(.primary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .background(
                                    RoundedRectangle(cornerRadius: 6)
                                        .fill(Color.secondary.opacity(0.08))
                                )
                        }
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)

                // Work modes
                VStack(alignment: .leading, spacing: 10) {
                    Text("工作模式")
                        .font(.system(size: 14, weight: .medium))
                    VStack(alignment: .leading, spacing: 8) {
                        workModeRow(title: "构建新界面", desc: "从设计稿到可交互组件")
                        workModeRow(title: "修复交互问题", desc: "定位并修复用户交互缺陷")
                        workModeRow(title: "优化用户体验", desc: "提升性能与交互流畅度")
                        workModeRow(title: "重构组件", desc: "改善代码结构与可维护性")
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(nsColor: .controlBackgroundColor))
                .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
        )
    }

    private func strengthRow(icon: String, text: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: icon)
                .font(.system(size: 12))
                .foregroundColor(.accentColor)
                .frame(width: 18)
            Text(text)
                .font(.system(size: 13))
                .foregroundColor(.primary)
        }
    }

    private func workModeRow(title: String, desc: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.system(size: 13, weight: .medium))
            Text(desc)
                .font(.system(size: 11))
                .foregroundColor(.secondary)
        }
    }

    // MARK: - Skills & Tools
    private var skillsAndToolsSection: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("能力与工具")
                .font(.system(size: 18, weight: .semibold))

            VStack(alignment: .leading, spacing: 12) {
                HStack {
                    Text("我的能力 (\(skillTags.count)/\(skillTags.count))")
                        .font(.system(size: 14, weight: .medium))
                    Spacer()
                    Button("管理 >") {}
                        .buttonStyle(.plain)
                        .font(.system(size: 13))
                        .foregroundColor(.accentColor)
                }

                FlowLayout(spacing: 8) {
                    ForEach(skillTags, id: \.self) { skill in
                        HStack(spacing: 4) {
                            Circle()
                                .fill(Color.green)
                                .frame(width: 6, height: 6)
                            Text(skill)
                                .font(.system(size: 12))
                        }
                        .padding(.horizontal, 10)
                        .padding(.vertical, 5)
                        .background(
                            RoundedRectangle(cornerRadius: 6)
                                .fill(Color.secondary.opacity(0.08))
                        )
                    }
                }

                Divider()

                HStack {
                    Text("连接器")
                        .font(.system(size: 14, weight: .medium))
                    Spacer()
                    Button("+ 添加") {}
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                    Button("{ } 导入 JSON") {}
                        .buttonStyle(.bordered)
                        .controlSize(.small)
                }

                Text("暂无连接器")
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
            }
        }
        .padding(20)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(Color(nsColor: .controlBackgroundColor))
                .shadow(color: .black.opacity(0.04), radius: 6, y: 2)
        )
    }

    // MARK: - Raw Files
    private var rawFilesSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("原始档案")
                .font(.system(size: 18, weight: .semibold))

            LazyVGrid(columns: [GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible()), GridItem(.flexible())], spacing: 12) {
                ForEach(rawFiles, id: \.self) { file in
                    HStack(spacing: 8) {
                        Image(systemName: "doc.text")
                            .font(.system(size: 20))
                            .foregroundColor(.secondary)
                        Text(file)
                            .font(.system(size: 13, weight: .medium))
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(Color.secondary.opacity(0.06))
                    )
                    .overlay(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.secondary.opacity(0.1), lineWidth: 1)
                    )
                }
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

// MARK: - FlowLayout
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = arrangeSubviews(proposal: proposal, subviews: subviews)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = arrangeSubviews(proposal: ProposedViewSize(width: bounds.width, height: bounds.height), subviews: subviews)
        for (index, position) in result.positions.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + position.x, y: bounds.minY + position.y), proposal: .unspecified)
        }
    }

    private func arrangeSubviews(proposal: ProposedViewSize, subviews: Subviews) -> (size: CGSize, positions: [CGPoint]) {
        let maxWidth = proposal.width ?? .infinity
        var positions: [CGPoint] = []
        var x: CGFloat = 0
        var y: CGFloat = 0
        var rowHeight: CGFloat = 0
        var maxX: CGFloat = 0

        for subview in subviews {
            let size = subview.sizeThatFits(.unspecified)
            if x + size.width > maxWidth && x > 0 {
                x = 0
                y += rowHeight + spacing
                rowHeight = 0
            }
            positions.append(CGPoint(x: x, y: y))
            rowHeight = max(rowHeight, size.height)
            x += size.width + spacing
            maxX = max(maxX, x - spacing)
        }

        return (CGSize(width: maxX, height: y + rowHeight), positions)
    }
}
