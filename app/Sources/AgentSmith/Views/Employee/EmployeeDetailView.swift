import SwiftUI

enum EmployeeDetailTab: String, CaseIterable {
    case home, projects, automations, tasks, memory, skills, connectors, im, permissions

    var label: String {
        switch self {
        case .home: return "首页"
        case .projects: return "项目"
        case .automations: return "自动任务"
        case .tasks: return "任务"
        case .memory: return "记忆"
        case .skills: return "技能"
        case .connectors: return "连接器"
        case .im: return "IM"
        case .permissions: return "权限"
        }
    }

    var icon: String {
        switch self {
        case .home: return "house"
        case .projects: return "folder"
        case .automations: return "clock.arrow.circlepath"
        case .tasks: return "list.bullet.rectangle.portrait"
        case .memory: return "brain.head.profile"
        case .skills: return "puzzlepiece"
        case .connectors: return "link"
        case .im: return "message"
        case .permissions: return "shield"
        }
    }

    var selectedIcon: String {
        switch self {
        case .home: return "house.fill"
        case .projects: return "folder.fill"
        case .automations: return "clock.arrow.circlepath"
        case .tasks: return "list.bullet.rectangle.portrait.fill"
        case .memory: return "brain.head.profile.fill"
        case .skills: return "puzzlepiece.fill"
        case .connectors: return "link"
        case .im: return "message.fill"
        case .permissions: return "shield.fill"
        }
    }
}

struct EmployeeDetailView: View {
    let employee: Employee
    var onBack: (() -> Void)? = nil
    @State private var selectedTab: EmployeeDetailTab = .home
    @State private var hoveredTab: EmployeeDetailTab?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HStack(spacing: 12) {
            employeeSidebar

            ScrollView {
                Group {
                    switch selectedTab {
                    case .home:
                        EmployeeHomeView(employee: employee)
                    case .skills:
                        EmployeeSkillsView(employee: employee)
                    case .memory:
                        EmployeeMemoryView(employee: employee)
                    case .tasks:
                        EmployeeTasksView(employee: employee)
                    case .automations:
                        EmployeeAutomationsView(employee: employee)
                    case .connectors:
                        EmployeeConnectorsView(employee: employee)
                    case .permissions:
                        EmployeePermissionsView(employee: employee)
                    case .im:
                        emptyState(icon: "message", title: "暂无 IM 连接")
                    case .projects:
                        emptyState(icon: "folder", title: "暂无项目")
                    }
                }
                .padding(24)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(AppPalette.canvas)
        }
        .padding(12)
        .background(AppPalette.canvas)
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden)
    }

    private var employeeSidebar: some View {
        VStack(alignment: .leading, spacing: 2) {
            VStack(alignment: .leading, spacing: 0) {
                Button {
                    if let onBack {
                        onBack()
                    } else {
                        dismiss()
                    }
                } label: {
                    Label("我的Agent", systemImage: "chevron.left")
                        .appFont(size: 13)
                        .foregroundStyle(.blue)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 12)

                HStack(alignment: .center, spacing: 10) {
                    EmployeePortraitView(
                        imageName: employee.avatarImageName,
                        fallbackColor: employee.avatarColor,
                        fallbackText: String(employee.name.prefix(1)),
                        width: 48,
                        height: 58,
                        cornerRadius: 10
                    )
                    VStack(alignment: .leading, spacing: 1) {
                        Text(employee.name)
                            .appFont(size: 15, weight: .semibold)
                        HStack(spacing: 4) {
                            Circle()
                                .fill(employee.isOnline ? AppPalette.online : Color.gray)
                                .frame(width: 6, height: 6)
                            Text(employee.isOnline ? "在线" : "离线")
                                .appFont(size: 11)
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(.bottom, 14)
            }

            ForEach(EmployeeDetailTab.allCases, id: \.self) { tab in
                let isSelected = selectedTab == tab
                let isHovered = hoveredTab == tab

                Button {
                    selectedTab = tab
                } label: {
                    Label {
                        Text(tab.label)
                    } icon: {
                        Image(systemName: isSelected ? tab.selectedIcon : tab.icon)
                    }
                    .appFont(size: 13)
                    .foregroundStyle(isSelected ? .blue : .primary)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.vertical, 7)
                    .padding(.horizontal, 10)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .fill(
                                isSelected
                                    ? Color.blue.opacity(0.12)
                                    : isHovered
                                        ? AppPalette.mutedSurface
                                        : Color.clear
                            )
                    )
                }
                .buttonStyle(.plain)
                .onHover { hovering in
                    hoveredTab = hovering ? tab : nil
                }
                .animation(.easeInOut(duration: 0.15), value: isHovered)
            }

            Spacer()
        }
        .padding(.horizontal, 12)
        .padding(.bottom, 14)
        .padding(.top, 44)
        .frame(width: 180)
        .background(SidebarMaterialView())
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 20, style: .continuous)
                .stroke(AppPalette.border.opacity(0.75), lineWidth: 0.5)
        )
        .shadow(color: .black.opacity(0.08), radius: 14, y: 4)
    }

    private func emptyState(icon: String, title: String) -> some View {
        VStack(spacing: 8) {
            Image(systemName: icon)
                .appFont(size: 40)
                .foregroundStyle(.secondary.opacity(0.5))
            Text(title)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(.top, 120)
    }
}
