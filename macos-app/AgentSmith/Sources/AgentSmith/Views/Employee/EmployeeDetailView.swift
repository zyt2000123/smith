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
}

struct EmployeeDetailView: View {
    let employee: Employee
    @State private var selectedTab: EmployeeDetailTab = .home
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        HStack(spacing: 0) {
            // Left sidebar
            VStack(alignment: .leading, spacing: 2) {
                Button {
                    dismiss()
                } label: {
                    Label("我的Agent", systemImage: "chevron.left")
                        .font(.system(size: 13))
                        .foregroundColor(.accentColor)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 16)

                // Employee avatar + name
                HStack(spacing: 10) {
                    ZStack {
                        Circle()
                            .fill(employee.avatarColor.gradient)
                            .frame(width: 32, height: 32)
                        Text(String(employee.name.prefix(1)))
                            .font(.system(size: 14, weight: .semibold))
                            .foregroundColor(.white)
                    }
                    VStack(alignment: .leading, spacing: 1) {
                        Text(employee.name)
                            .font(.system(size: 14, weight: .semibold))
                        HStack(spacing: 4) {
                            Circle()
                                .fill(employee.isOnline ? Color.green : Color.gray)
                                .frame(width: 6, height: 6)
                            Text(employee.isOnline ? "在线" : "离线")
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                        }
                    }
                }
                .padding(.bottom, 16)

                // Tab list
                ForEach(EmployeeDetailTab.allCases, id: \.self) { tab in
                    Button {
                        selectedTab = tab
                    } label: {
                        Label(tab.label, systemImage: tab.icon)
                            .font(.system(size: 13))
                            .foregroundColor(selectedTab == tab ? .accentColor : .primary)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding(.vertical, 6)
                            .padding(.horizontal, 10)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(selectedTab == tab ? Color.accentColor.opacity(0.1) : Color.clear)
                            )
                    }
                    .buttonStyle(.plain)
                }

                Spacer()
            }
            .padding(16)
            .frame(width: 200)
            .background(Color(nsColor: .controlBackgroundColor))

            Divider()

            // Content
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
                        VStack(spacing: 8) {
                            Image(systemName: "message")
                                .font(.system(size: 40))
                                .foregroundColor(.secondary.opacity(0.5))
                            Text("暂无 IM 连接")
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(.top, 120)
                    case .projects:
                        VStack(spacing: 8) {
                            Image(systemName: "folder")
                                .font(.system(size: 40))
                                .foregroundColor(.secondary.opacity(0.5))
                            Text("暂无项目")
                                .foregroundColor(.secondary)
                        }
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .padding(.top, 120)
                    }
                }
                .padding(24)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .windowBackgroundColor))
        }
        .navigationBarBackButtonHidden(true)
        .toolbar(.hidden)
    }
}
