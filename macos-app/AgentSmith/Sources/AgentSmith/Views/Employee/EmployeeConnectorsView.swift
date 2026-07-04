import SwiftUI

struct EmployeeConnectorsView: View {
    let employee: Employee

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text("连接器")
                        .font(.system(size: 24, weight: .bold))
                    Text("管理该Agent可使用的外部服务连接")
                        .font(.system(size: 14))
                        .foregroundStyle(.secondary)
                }
                Spacer()
                Button {
                    // add
                } label: {
                    Label("添加", systemImage: "plus")
                        .font(.system(size: 13, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
                .tint(.blue)

                Button {
                    // import JSON
                } label: {
                    Label("导入 JSON", systemImage: "curlybraces")
                        .font(.system(size: 13, weight: .medium))
                }
                .buttonStyle(.bordered)
            }

            // Empty state
            VStack(spacing: 16) {
                Image(systemName: "link")
                    .font(.system(size: 48))
                    .foregroundStyle(.secondary.opacity(0.3))

                Text("暂无连接器")
                    .font(.system(size: 16, weight: .medium))
                    .foregroundStyle(.secondary)

                Text("添加连接器让Agent访问外部 API、数据库或第三方服务")
                    .font(.system(size: 13))
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
