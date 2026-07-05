import SwiftUI

struct ManagementView: View {
    var onOpenEmployee: (Employee) -> Void
    @EnvironmentObject private var apiClient: APIClient
    @State private var employees: [Employee] = []
    @State private var showCreateSheet = false
    @State private var selectedSegment = 0
    @State private var statusFilter = "全部"
    @State private var envFilter = "全部"
    @State private var searchText = ""

    private let columns = [
        GridItem(.flexible(), spacing: 16),
        GridItem(.flexible(), spacing: 16),
    ]

    var filteredEmployees: [Employee] {
        employees.filter { emp in
            let matchesStatus: Bool = {
                switch statusFilter {
                case "在线": return emp.isOnline
                case "离线": return !emp.isOnline
                default: return true
                }
            }()
            let matchesEnv: Bool = {
                switch envFilter {
                case "本地": return emp.environment == "本地"
                case "云端": return emp.environment == "云端"
                default: return true
                }
            }()
            let matchesSearch = searchText.isEmpty
                || emp.name.localizedCaseInsensitiveContains(searchText)
                || emp.role.localizedCaseInsensitiveContains(searchText)
            return matchesStatus && matchesEnv && matchesSearch
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                header
                filterBar
                employeeGrid
            }
            .padding(.horizontal, 24)
            .padding(.bottom, 24)
            .padding(.top, FloatingSidebarMetrics.rightContentTopInset)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .task { await loadEmployees() }
        .sheet(isPresented: $showCreateSheet) {
            CreateEmployeeSheet(
                isPresented: $showCreateSheet,
                onCreated: { newEmp in employees.append(newEmp) }
            )
            .environmentObject(apiClient)
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text("我的Agent")
                    .appFont(size: 26, weight: .bold)
                Text("统一创建、管理和对话你的Agent")
                    .appFont(size: 13)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                showCreateSheet = true
            } label: {
                Label("新建Agent", systemImage: "plus")
                    .appFont(size: 13, weight: .medium)
            }
            .buttonStyle(.borderedProminent)
            .tint(.blue)
            .controlSize(.large)
        }
    }

    private var filterBar: some View {
        HStack(spacing: 12) {
            employeeSegmentedControl

            filterPill("状态", selection: $statusFilter, options: ["全部", "在线", "离线"])
            filterPill("环境", selection: $envFilter, options: ["全部", "本地", "云端"])

            Spacer()

            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.tertiary)
                    .appFont(size: 12)
                TextField("搜索Agent...", text: $searchText)
                    .textFieldStyle(.plain)
                    .appFont(size: 13)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 8))
            .frame(width: 200)
        }
    }

    private var employeeSegmentedControl: some View {
        HStack(spacing: 2) {
            segmentButton("我的Agent", value: 0)
            segmentButton("我的群组", value: 1)
        }
        .padding(2)
        .frame(width: 200)
        .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 8))
    }

    private func segmentButton(_ title: String, value: Int) -> some View {
        let isSelected = selectedSegment == value

        return Button {
            selectedSegment = value
        } label: {
            Text(title)
                .appFont(size: 13, weight: isSelected ? .semibold : .regular)
                .foregroundStyle(isSelected ? .white : .primary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 5)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(isSelected ? Color.blue : Color.clear)
                )
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func filterPill(_ label: String, selection: Binding<String>, options: [String]) -> some View {
        Menu {
            ForEach(options, id: \.self) { option in
                Button {
                    selection.wrappedValue = option
                } label: {
                    if selection.wrappedValue == option {
                        Label(option, systemImage: "checkmark")
                    } else {
                        Text(option)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(label).foregroundStyle(.secondary)
                Text(selection.wrappedValue)
                Image(systemName: "chevron.down")
                    .appFont(size: 9, weight: .semibold)
                    .foregroundStyle(.tertiary)
            }
            .appFont(size: 12)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(AppPalette.mutedSurface, in: Capsule())
        }
        .buttonStyle(.plain)
    }

    private var employeeGrid: some View {
        LazyVGrid(columns: columns, spacing: 16) {
            ForEach(filteredEmployees) { emp in
                EmployeeCardView(employee: emp) {
                    onOpenEmployee(emp)
                }
            }
        }
    }

    private func loadEmployees() async {
        do {
            employees = try await apiClient.fetchEmployees()
        } catch {
            employees = Employee.samples
        }
    }
}
