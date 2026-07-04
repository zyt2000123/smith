import SwiftUI

struct EmployeeCardView: View {
    let employee: Employee
    var onTap: () -> Void
    @State private var isHovered = false

    var body: some View {
        Button(action: onTap) {
            VStack(alignment: .leading, spacing: 14) {
                HStack(alignment: .top, spacing: 12) {
                    EmployeePortraitView(
                        imageName: employee.avatarImageName,
                        fallbackColor: employee.avatarColor,
                        fallbackText: String(employee.name.prefix(1)),
                        width: 108,
                        height: 132,
                        cornerRadius: 18
                    )

                    VStack(alignment: .leading, spacing: 5) {
                        HStack(spacing: 8) {
                            Text(employee.name)
                                .font(.system(size: 18, weight: .semibold))
                            Text(employee.role)
                                .font(.system(size: 11))
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 2)
                                .background(Color.blue.opacity(0.08), in: Capsule())
                        }

                        HStack(spacing: 8) {
                            Label(employee.device, systemImage: "laptopcomputer")
                                .font(.system(size: 11))
                                .foregroundStyle(.orange)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(Color.orange.opacity(0.10), in: RoundedRectangle(cornerRadius: 6))

                            Circle()
                                .fill(employee.isOnline ? Color.green : Color.gray.opacity(0.5))
                                .frame(width: 8, height: 8)

                            Text(employee.isOnline ? "Online" : "Offline")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(employee.isOnline ? .green : .secondary)
                        }
                    }

                    Spacer()

                    Menu {
                        Button("编辑") {}
                        Button("复制") {}
                        Divider()
                        Button("删除", role: .destructive) {}
                    } label: {
                        Image(systemName: "ellipsis")
                            .font(.system(size: 13))
                            .foregroundStyle(.tertiary)
                            .frame(width: 24, height: 24)
                    }
                    .menuStyle(.borderlessButton)
                    .frame(width: 24)
                }

                Text(employee.description)
                    .font(.system(size: 12))
                    .foregroundStyle(.secondary)
                    .lineLimit(2)
                    .lineSpacing(2)

                HStack(spacing: 5) {
                    ForEach(employee.knowledge, id: \.self) { tag in
                        Text(tag)
                            .font(.system(size: 11))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 5))
                    }
                    Spacer()
                }

                HStack(spacing: 8) {
                    Button {} label: {
                        Label("创建对话任务", systemImage: "arrow.up.right.square")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Button {} label: {
                        Label("创建自动任务", systemImage: "clock.arrow.circlepath")
                            .font(.system(size: 11, weight: .medium))
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)

                    Spacer()
                }
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(.regularMaterial)
                    .shadow(color: .black.opacity(isHovered ? 0.1 : 0.04), radius: isHovered ? 12 : 6, y: isHovered ? 4 : 2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(Color.primary.opacity(0.05), lineWidth: 0.5)
            )
            .scaleEffect(isHovered ? 1.01 : 1.0)
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
        .animation(.easeOut(duration: 0.15), value: isHovered)
    }
}
