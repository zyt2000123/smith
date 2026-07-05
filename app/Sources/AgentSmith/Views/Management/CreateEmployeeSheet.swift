import SwiftUI

struct CreateEmployeeSheet: View {
    @EnvironmentObject private var apiClient: APIClient
    @Binding var isPresented: Bool
    var onCreated: (Employee) -> Void
    @State private var selectedTemplate: String? = nil
    @State private var name = ""
    @State private var description = ""
    @State private var selectedColor: Color = .blue
    @State private var isCreating = false
    @State private var hoveredTemplate: String?

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
                    isCreating = true
                    let role = selectedTemplate ?? "backend-engineer"
                    let empName = name.isEmpty ? "新员工" : name
                    let empDesc = description.isEmpty
                        ? (employeeTemplates.first(where: { $0.id == selectedTemplate })?.description ?? "")
                        : description
                    Task {
                        do {
                            let newEmp = try await apiClient.createEmployee(
                                name: empName, role: role, description: empDesc
                            )
                            onCreated(newEmp)
                        } catch {
                            print("Create employee failed: \(error)")
                        }
                        isCreating = false
                        isPresented = false
                    }
                }
                .buttonStyle(.borderedProminent)
                .keyboardShortcut(.defaultAction)
                .disabled((name.isEmpty && selectedTemplate == nil) || isCreating)
            }
        }
        .padding(24)
        .frame(width: 640, height: 720)
    }

    private func templateCard(_ template: EmployeeTemplate) -> some View {
        let isSelected = selectedTemplate == template.id
        let isHovered = hoveredTemplate == template.id

        return Button {
            selectedTemplate = template.id
            if name.isEmpty {
                description = template.description
            }
        } label: {
            HStack(spacing: 10) {
                Image(systemName: template.icon)
                    .appFont(size: 20)
                    .foregroundStyle(isSelected ? .blue : .secondary)
                    .frame(width: 36)

                VStack(alignment: .leading, spacing: 2) {
                    Text(template.title)
                        .appFont(size: 13, weight: .medium)
                        .foregroundStyle(isSelected ? .blue : .primary)
                    Text(template.description)
                        .appFont(size: 11)
                        .foregroundColor(.secondary)
                        .lineLimit(1)
                }
                Spacer()
            }
            .padding(10)
            .appSelectionBackground(isSelected: isSelected, isHovered: isHovered)
        }
        .buttonStyle(.plain)
        .onHover { hovering in
            hoveredTemplate = hovering ? template.id : nil
        }
        .accessibilityValue(isSelected ? "已选择" : "")
    }
}
