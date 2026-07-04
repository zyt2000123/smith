import SwiftUI

struct CreateEmployeeSheet: View {
    @Binding var employees: [Employee]
    @Binding var isPresented: Bool
    @State private var selectedTemplate: String? = nil
    @State private var name = ""
    @State private var description = ""
    @State private var selectedColor: Color = .blue

    private let colorOptions: [Color] = [.blue, .green, .orange, .purple, .red, .pink, .cyan, .mint]

    private let columns = [
        GridItem(.flexible(), spacing: 12),
        GridItem(.flexible(), spacing: 12),
    ]

    var body: some View {
        VStack(alignment: .leading, spacing: 20) {
            // Header
            HStack {
                Text("新建数字员工")
                    .appFont(size: 20, weight: .bold)
                Spacer()
                Button {
                    isPresented = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .appFont(size: 20)
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }

            // Template grid
            Text("选择模板")
                .appFont(size: 14, weight: .medium)
                .foregroundColor(.secondary)

            LazyVGrid(columns: columns, spacing: 10) {
                ForEach(employeeTemplates) { template in
                    templateCard(template)
                }
            }

            Divider()

            // Name
            VStack(alignment: .leading, spacing: 6) {
                Text("名称")
                    .appFont(size: 13, weight: .medium)
                TextField("输入员工名称", text: $name)
                    .textFieldStyle(.roundedBorder)
            }

            // Avatar color
            VStack(alignment: .leading, spacing: 6) {
                Text("头像颜色")
                    .appFont(size: 13, weight: .medium)
                HStack(spacing: 8) {
                    ForEach(colorOptions, id: \.self) { color in
                        Circle()
                            .fill(color.gradient)
                            .frame(width: 28, height: 28)
                            .overlay(
                                Circle()
                                    .stroke(Color.primary, lineWidth: selectedColor == color ? 2 : 0)
                                    .padding(-2)
                            )
                            .onTapGesture {
                                selectedColor = color
                            }
                    }
                }
            }

            // Description
            VStack(alignment: .leading, spacing: 6) {
                Text("描述")
                    .appFont(size: 13, weight: .medium)
                TextEditor(text: $description)
                    .appFont(size: 13)
                    .frame(height: 80)
                    .padding(4)
                    .background(
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Color.secondary.opacity(0.3), lineWidth: 1)
                    )
            }

            Spacer()

            // Footer buttons
            HStack {
                Spacer()
                Button("取消") {
                    isPresented = false
                }
                .keyboardShortcut(.cancelAction)

                Button("保存并启用") {
                    let newEmployee = Employee(
                        id: UUID().uuidString,
                        name: name.isEmpty ? "新员工" : name,
                        role: employeeTemplates.first(where: { $0.id == selectedTemplate })?.title ?? "通用员工",
                        device: "MacBook-Pro.local",
                        isOnline: true,
                        description: description.isEmpty
                            ? (employeeTemplates.first(where: { $0.id == selectedTemplate })?.description ?? "")
                            : description,
                        knowledge: [],
                        capabilities: [],
                        workStyles: [],
                        environment: "本地",
                        avatarColor: selectedColor,
                        joinDate: Date()
                    )
                    employees.append(newEmployee)
                    isPresented = false
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled(name.isEmpty && selectedTemplate == nil)
            }
        }
        .padding(24)
        .frame(width: 640, height: 720)
    }

    private func templateCard(_ template: EmployeeTemplate) -> some View {
        Button {
            selectedTemplate = template.id
            if name.isEmpty {
                description = template.description
            }
        } label: {
            HStack(spacing: 10) {
                Image(systemName: template.icon)
                    .appFont(size: 20)
                    .foregroundColor(selectedTemplate == template.id ? .accentColor : .secondary)
                    .frame(width: 36)

                VStack(alignment: .leading, spacing: 2) {
                    Text(template.title)
                        .appFont(size: 13, weight: .medium)
                        .foregroundColor(.primary)
                    Text(template.description)
                        .appFont(size: 11)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer()
            }
            .padding(10)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(
                        selectedTemplate == template.id ? Color.accentColor : Color.clear,
                        lineWidth: 2
                    )
            )
        }
        .buttonStyle(.plain)
    }
}
