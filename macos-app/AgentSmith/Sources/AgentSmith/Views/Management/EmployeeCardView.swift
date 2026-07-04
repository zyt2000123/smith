import SwiftUI

struct EmployeeCardView: View {
    let employee: Employee
    var onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 12) {
                // Top: avatar + info
                HStack(alignment: .top, spacing: 12) {
                    // Avatar
                    ZStack {
                        Circle()
                            .fill(employee.avatarColor.gradient)
                            .frame(width: 44, height: 44)
                        Text(String(employee.name.prefix(1)))
                            .font(.system(size: 20, weight: .semibold))
                            .foregroundColor(.white)
                    }

                    VStack(alignment: .leading, spacing: 6) {
                        // Name + role
                        HStack(spacing: 8) {
                            Text(employee.name)
                                .font(.system(size: 16, weight: .semibold))
                                .foregroundColor(.primary)

                            Text(employee.role)
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Capsule().fill(Color.secondary.opacity(0.1)))

                            Text(employee.environment)
                                .font(.system(size: 11))
                                .foregroundColor(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Capsule().fill(Color.secondary.opacity(0.1)))
                        }

                        // Device tag
                        HStack(spacing: 4) {
                            Label(employee.device, systemImage: "desktopcomputer")
                                .font(.system(size: 11))
                                .foregroundColor(.orange)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(
                                    Capsule().fill(Color.orange.opacity(0.1))
                                )
                        }

                        // Status
                        HStack(spacing: 4) {
                            Circle()
                                .fill(employee.isOnline ? Color.green : Color.gray)
                                .frame(width: 7, height: 7)
                            Text(employee.isOnline ? "在线" : "离线")
                                .font(.system(size: 12))
                                .foregroundColor(employee.isOnline ? .green : .secondary)
                        }
                    }
                }

                // Description
                Text(employee.description)
                    .font(.system(size: 13))
                    .foregroundColor(.secondary)
                    .lineLimit(1)

                Divider()

                // Knowledge tags
                HStack(spacing: 6) {
                    ForEach(employee.knowledge, id: \.self) { tag in
                        Text(tag)
                            .font(.system(size: 11))
                            .foregroundColor(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(
                                RoundedRectangle(cornerRadius: 6)
                                    .fill(Color.secondary.opacity(0.08))
                            )
                    }
                    Spacer()
                }

                // Action buttons
                HStack(spacing: 8) {
                    Button {
                        // create conversation task
                    } label: {
                        Text("创建对话任务")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button {
                        // create automation task
                    } label: {
                        Text("创建自动任务")
                            .font(.system(size: 12, weight: .medium))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Spacer()

                    Menu {
                        Button("编辑") {}
                        Button("复制") {}
                        Divider()
                        Button("删除", role: .destructive) {}
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 14))
                            .foregroundColor(.secondary)
                            .frame(width: 28, height: 28)
                    }
                    .menuStyle(.borderlessButton)
                    .frame(width: 28)
                }
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(Color(nsColor: .controlBackgroundColor))
                    .shadow(color: .black.opacity(0.06), radius: 8, y: 2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.primary.opacity(0.06), lineWidth: 1)
            )
        }
        .buttonStyle(.plain)
    }
}
