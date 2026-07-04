import SwiftUI

struct Employee: Identifiable, Hashable {
    let id: String
    var name: String
    var role: String
    var avatarImageName: String?
    var device: String
    var isOnline: Bool
    var description: String
    var knowledge: [String]
    var capabilities: [String]
    var workStyles: [String]
    var environment: String
    var avatarColor: Color
    var joinDate: Date

    func hash(into hasher: inout Hasher) {
        hasher.combine(id)
    }

    static func == (lhs: Employee, rhs: Employee) -> Bool {
        lhs.id == rhs.id
    }

    static let samples: [Employee] = [
        Employee(
            id: "ivy", name: "Ivy", role: "Product Manager", avatarImageName: "product-manager",
            device: "AA01030deMacBook-Pro.local", isOnline: true,
            description: "面向 AI 原生产品做需求澄清、版本规划和验收口径整理，保持用户价值与交付节奏对齐。",
            knowledge: ["Roadmap", "User Research", "Figma"],
            capabilities: ["Requirement Analysis", "Release Planning", "Stakeholder Sync", "Acceptance Criteria"],
            workStyles: ["User Driven", "Data Informed", "Structured Communication", "Iterative Validation"],
            environment: "Cloud", avatarColor: .purple,
            joinDate: Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()
        ),
        Employee(
            id: "luna", name: "Luna", role: "Frontend Engineer", avatarImageName: "frontend-engineer",
            device: "AA01030deMacBook-Pro.local", isOnline: true,
            description: "专注前端界面设计与实现，擅长组件架构、视觉语言打磨和响应式体验优化。",
            knowledge: ["Design System", "React Workspace", "Responsive UI"],
            capabilities: ["Component Architecture", "Visual Polish", "State Management", "Performance Tuning"],
            workStyles: ["Design First", "Small Iterations", "Clean Code", "Evidence Driven"],
            environment: "Local", avatarColor: .green,
            joinDate: Date()
        ),
        Employee(
            id: "theo", name: "Theo", role: "Backend Engineer", avatarImageName: "backend-engineer",
            device: "AA01030deMacBook-Pro.local", isOnline: true,
            description: "专注 API 开发、数据建模、服务集成、性能优化和本地运行时排障。",
            knowledge: ["Hub API", "AgentScope", "SQLite Storage"],
            capabilities: ["API Design", "Data Modeling", "Service Integration", "Runtime Debugging"],
            workStyles: ["Contract First", "Defensive Coding", "Progressive Delivery", "Observable Systems"],
            environment: "Local", avatarColor: .blue,
            joinDate: Calendar.current.date(byAdding: .day, value: -7, to: Date()) ?? Date()
        ),
    ]
}

struct EmployeeTemplate: Identifiable {
    let id: String
    let title: String
    let description: String
    let icon: String
}

let employeeTemplates: [EmployeeTemplate] = [
    EmployeeTemplate(id: "product", title: "Product Manager",
                     description: "负责需求澄清、版本规划、验收标准与跨角色协同。",
                     icon: "list.clipboard"),
    EmployeeTemplate(id: "frontend", title: "Frontend Engineer",
                     description: "专注前端界面设计与实现，擅长组件架构、视觉语言打磨、响应式体验。",
                     icon: "chevron.left.forwardslash.chevron.right"),
    EmployeeTemplate(id: "backend", title: "Backend Engineer",
                     description: "专注 API 开发、数据建模、服务集成、性能优化和稳定性保障。",
                     icon: "server.rack"),
]
