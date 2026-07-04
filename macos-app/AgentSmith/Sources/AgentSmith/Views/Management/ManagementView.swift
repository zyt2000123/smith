import SwiftUI

struct ManagementView: View {
    var onOpenEmployee: (Employee) -> Void
    @State private var employees = Employee.samples
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
            .padding(.top, 40)
        }
        .background(Color(nsColor: .windowBackgroundColor))
        .sheet(isPresented: $showCreateSheet) {
            CreateEmployeeSheet(employees: $employees, isPresented: $showCreateSheet)
        }
    }

    private var header: some View {
        HStack(alignment: .center) {
            VStack(alignment: .leading, spacing: 4) {
                Text("我的数字员工")
                    .appFont(size: 26, weight: .bold)
                Text("统一创建、管理和对话你的数字员工")
                    .appFont(size: 13)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button {
                showCreateSheet = true
            } label: {
                Label("新建员工", systemImage: "plus")
                    .appFont(size: 13, weight: .medium)
            }
            .buttonStyle(.borderedProminent)
            .tint(.blue)
            .controlSize(.large)
        }
    }

    private var filterBar: some View {
        HStack(spacing: 12) {
            Picker("", selection: $selectedSegment) {
                Text("我的员工").tag(0)
                Text("我的群组").tag(1)
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

            filterPill("状态", selection: $statusFilter, options: ["全部", "在线", "离线"])
            filterPill("环境", selection: $envFilter, options: ["全部", "本地", "云端"])

            Spacer()

            HStack(spacing: 6) {
                Image(systemName: "magnifyingglass")
                    .foregroundStyle(.tertiary)
                    .appFont(size: 12)
                TextField("搜索员工...", text: $searchText)
                    .textFieldStyle(.plain)
                    .appFont(size: 13)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(AppPalette.mutedSurface, in: RoundedRectangle(cornerRadius: 8))
            .frame(width: 200)
        }
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
}
