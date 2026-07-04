import SwiftUI

struct ManagementView: View {
    @Binding var selectedEmployee: Employee?
    @State private var employees = Employee.samples
    @State private var showCreateSheet = false
    @State private var selectedSegment = 0
    @State private var statusFilter = "全部"
    @State private var envFilter = "全部"
    @State private var searchText = ""
    @State private var navigateToDetail = false
    @State private var detailEmployee: Employee?

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
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 20) {
                    header
                    filterBar
                    employeeGrid
                }
                .padding(24)
            }
            .background(Color(nsColor: .windowBackgroundColor))
            .navigationDestination(item: $detailEmployee) { emp in
                EmployeeDetailView(employee: emp)
            }
        }
        .sheet(isPresented: $showCreateSheet) {
            CreateEmployeeSheet(employees: $employees, isPresented: $showCreateSheet)
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("我的Agent")
                        .font(.system(size: 28, weight: .bold))
                    Text("跨云端与本地运行时，统一创建、管理和对话你的Agent。")
                        .font(.system(size: 14))
                        .foregroundColor(.secondary)
                }
                Spacer()
                Button {
                    showCreateSheet = true
                } label: {
                    Label("新建Agent", systemImage: "plus")
                        .font(.system(size: 13, weight: .medium))
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.large)
            }
        }
    }

    private var filterBar: some View {
        HStack(spacing: 12) {
            Picker("", selection: $selectedSegment) {
                Text("我的Agent").tag(0)
                Text("我的群组").tag(1)
            }
            .pickerStyle(.segmented)
            .frame(width: 200)

            Picker("状态", selection: $statusFilter) {
                Text("全部").tag("全部")
                Text("在线").tag("在线")
                Text("离线").tag("离线")
            }
            .frame(width: 100)

            Picker("环境", selection: $envFilter) {
                Text("全部").tag("全部")
                Text("本地").tag("本地")
                Text("云端").tag("云端")
            }
            .frame(width: 100)

            Spacer()

            HStack {
                Image(systemName: "magnifyingglass")
                    .foregroundColor(.secondary)
                TextField("搜索Agent...", text: $searchText)
                    .textFieldStyle(.plain)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .background(
                RoundedRectangle(cornerRadius: 8)
                    .fill(Color(nsColor: .controlBackgroundColor))
            )
            .frame(width: 220)
        }
    }

    private var employeeGrid: some View {
        LazyVGrid(columns: columns, spacing: 16) {
            ForEach(filteredEmployees) { emp in
                EmployeeCardView(employee: emp) {
                    detailEmployee = emp
                }
            }
        }
    }
}
