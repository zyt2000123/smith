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
                        width: 140,
                        height: 172,
                        cornerRadius: 20
                    )

                    VStack(alignment: .leading, spacing: 12) {
                        HStack(spacing: 8) {
                            Text(employee.name)
                                .appFont(size: 20, weight: .semibold)
                            Text(employee.localizedRole)
                                .appFont(size: 11)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 7)
                                .padding(.vertical, 2)
                                .background(AppPalette.mutedSurface, in: Capsule())
                        }

                        HStack(spacing: 8) {
                            Label(employee.device, systemImage: "laptopcomputer")
                                .appFont(size: 11)
                                .foregroundStyle(.secondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 6))

                            Circle()
                                .fill(employee.isOnline ? AppPalette.online : Color.gray.opacity(0.5))
                                .frame(width: 8, height: 8)

                            Text(employee.isOnline ? "Online" : "Offline")
                                .appFont(size: 11, weight: .medium)
                                .foregroundStyle(employee.isOnline ? AppPalette.online : Color.secondary)
                        }

                        Text(employee.description)
                            .appFont(size: 12)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                            .lineSpacing(2)

                        HStack(spacing: 8) {
                            Button {} label: {
                                Label("创建对话任务", systemImage: "arrow.up.right.square")
                                    .appFont(size: 11, weight: .medium)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)

                            Button {} label: {
                                Label("创建自动任务", systemImage: "clock.arrow.circlepath")
                                    .appFont(size: 11, weight: .medium)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.small)
                        }
                    }
                    .padding(.top, 16)
                    .frame(maxWidth: .infinity, alignment: .leading)

                    Spacer()

                    Menu {
                        Button("编辑") {}
                        Divider()
                        Button("删除", role: .destructive) {}
                    } label: {
                        Image(systemName: "ellipsis")
                            .appFont(size: 13)
                            .foregroundStyle(.tertiary)
                            .frame(width: 24, height: 24)
                    }
                    .menuStyle(.borderlessButton)
                    .menuIndicator(.hidden)
                    .frame(width: 24)
                }

            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(AppPalette.card)
                    .shadow(color: .black.opacity(isHovered ? 0.09 : 0.025), radius: isHovered ? 12 : 5, y: isHovered ? 4 : 2)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(AppPalette.border, lineWidth: 0.5)
            )
            .scaleEffect(isHovered ? 1.01 : 1.0)
        }
        .buttonStyle(.plain)
        .onHover { isHovered = $0 }
        .animation(.easeOut(duration: 0.15), value: isHovered)
    }

}
