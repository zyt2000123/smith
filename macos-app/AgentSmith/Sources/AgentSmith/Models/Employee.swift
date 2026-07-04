import SwiftUI

struct Employee: Identifiable, Hashable {
    let id: String
    var name: String
    var role: String
    var device: String
    var isOnline: Bool
    var description: String
    var knowledge: [String]
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
            id: "ding", name: "小丁", role: "前端开发工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "专注前端界面设计与实现，擅长组件架构、视觉语言打磨、响应式体验。",
            knowledge: ["前端规范", "设计系统", "React 工作区"],
            environment: "本地", avatarColor: .green,
            joinDate: Date()
        ),
        Employee(
            id: "t", name: "T", role: "后端工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "专注 API 开发、数据建模、服务集成、性能优化和本地运行时排障。",
            knowledge: ["Hub API", "AgentScope", "SQLite/文件存储"],
            environment: "本地", avatarColor: .blue,
            joinDate: Date()
        ),
        Employee(
            id: "mei", name: "小美", role: "产品经理",
            device: "MacBook-Pro.local", isOnline: false,
            description: "围绕用户目标澄清需求、拆解版本范围、沉淀验收口径和路线图。",
            knowledge: ["需求文档", "用户研究", "Figma"],
            environment: "云端", avatarColor: .purple,
            joinDate: Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()
        ),
        Employee(
            id: "kai", name: "小凯", role: "测试工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "面向 Web 产品和命令行工具做质量保障，覆盖冒烟、回归和验收。",
            knowledge: ["Playwright", "Jest", "CI/CD"],
            environment: "本地", avatarColor: .orange,
            joinDate: Calendar.current.date(byAdding: .day, value: -14, to: Date()) ?? Date()
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
    EmployeeTemplate(id: "frontend", title: "前端开发工程师",
                     description: "专注前端界面设计与实现，擅长组件架构、视觉语言打磨、响应式体验。",
                     icon: "chevron.left.forwardslash.chevron.right"),
    EmployeeTemplate(id: "backend", title: "后端工程师",
                     description: "专注 API 开发、数据建模、服务集成、性能优化和稳定性保障。",
                     icon: "server.rack"),
    EmployeeTemplate(id: "pm", title: "项目管理员",
                     description: "面向软件与运营项目的范围澄清、里程碑规划、任务拆解、进度跟踪。",
                     icon: "briefcase"),
    EmployeeTemplate(id: "qa", title: "测试工程师",
                     description: "面向 Web 产品和命令行工具做质量保障，覆盖冒烟、回归和验收。",
                     icon: "flask"),
    EmployeeTemplate(id: "product", title: "产品经理",
                     description: "围绕用户目标澄清需求、拆解版本范围、沉淀验收口径和路线图。",
                     icon: "list.clipboard"),
    EmployeeTemplate(id: "data", title: "数据分析师",
                     description: "面向指标口径、业务查询、数据复盘和可视化报告，形成可复核结论。",
                     icon: "chart.bar"),
    EmployeeTemplate(id: "devops", title: "DevOps 工程师",
                     description: "面向 CI/CD、部署流水线、环境配置、告警排障与稳定性治理。",
                     icon: "shield.checkered"),
    EmployeeTemplate(id: "ops", title: "内容运营专员",
                     description: "面向内容日历、热点洞察、用户反馈和活动复盘，维护稳定输出节奏。",
                     icon: "megaphone"),
]
