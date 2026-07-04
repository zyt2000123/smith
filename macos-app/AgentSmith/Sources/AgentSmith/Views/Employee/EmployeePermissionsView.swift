import SwiftUI

struct PermissionRule: Identifiable {
    let id = UUID()
    let pattern: String
    let action: PermissionAction
}

enum PermissionAction: String {
    case allow = "Allow"
    case ask = "Ask"
    case deny = "Deny"

    var color: Color {
        switch self {
        case .allow: return .blue
        case .ask: return .orange
        case .deny: return .red
        }
    }
}

struct EmployeePermissionsView: View {
    let employee: Employee

    private let toolRules: [PermissionRule] = [
        PermissionRule(pattern: "Bash(*)", action: .ask),
        PermissionRule(pattern: "Read(*)", action: .allow),
        PermissionRule(pattern: "Write(*)", action: .ask),
        PermissionRule(pattern: "Edit(*)", action: .ask),
        PermissionRule(pattern: "WebFetch(*)", action: .allow),
        PermissionRule(pattern: "WebSearch(*)", action: .deny),
    ]

    private let fileRules: [PermissionRule] = [
        PermissionRule(pattern: "~/.ssh/*", action: .deny),
        PermissionRule(pattern: "~/.env*", action: .deny),
        PermissionRule(pattern: "~/Projects/**", action: .allow),
        PermissionRule(pattern: "/tmp/**", action: .allow),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("权限")
                .font(.system(size: 24, weight: .bold))

            // Tool guard
            permissionSection(title: "工具守卫", icon: "hammer", rules: toolRules)

            // File guard
            permissionSection(title: "文件守卫", icon: "folder.badge.gearshape", rules: fileRules)
        }
    }

    private func permissionSection(title: String, icon: String, rules: [PermissionRule]) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 6) {
                Image(systemName: icon)
                    .font(.system(size: 14))
                    .foregroundStyle(.blue)
                Text(title)
                    .font(.system(size: 16, weight: .semibold))
            }

            VStack(spacing: 0) {
                ForEach(rules) { rule in
                    HStack {
                        Text(rule.pattern)
                            .font(.system(size: 13, design: .monospaced))
                            .foregroundStyle(.primary)

                        Spacer()

                        Text(rule.action.rawValue)
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(rule.action.color)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 4)
                            .background(
                                Capsule().fill(rule.action.color.opacity(0.12))
                            )
                    }
                    .padding(.vertical, 10)
                    .padding(.horizontal, 14)

                    if rule.id != rules.last?.id {
                        Divider().padding(.leading, 14)
                    }
                }
            }
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(.blue.opacity(0.1), lineWidth: 1)
            )
        }
    }
}
