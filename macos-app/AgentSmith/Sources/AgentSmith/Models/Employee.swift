import SwiftUI

struct Employee: Identifiable, Hashable {
    let id: String
    var name: String
    var role: String
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
            id: "ding", name: "小丁", role: "前端开发工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "专注前端界面设计与实现，擅长组件架构、视觉语言打磨、响应式体验。",
            knowledge: ["前端规范", "设计系统", "React 工作区"],
            capabilities: ["组件开发", "视觉还原", "响应式布局", "状态管理", "性能优化", "设计系统"],
            workStyles: ["设计优先", "小步迭代", "证据驱动验证", "代码整洁", "用户体验导向"],
            environment: "本地", avatarColor: .green,
            joinDate: Date()
        ),
        Employee(
            id: "t", name: "T", role: "后端工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "专注 API 开发、数据建模、服务集成、性能优化和本地运行时排障。",
            knowledge: ["Hub API", "AgentScope", "SQLite/文件存储"],
            capabilities: ["API 设计", "数据建模", "性能调优", "服务集成", "故障排查"],
            workStyles: ["契约优先", "防御式编程", "渐进式交付", "可观测性驱动"],
            environment: "本地", avatarColor: .blue,
            joinDate: Date()
        ),
        Employee(
            id: "mei", name: "小美", role: "产品经理",
            device: "MacBook-Pro.local", isOnline: false,
            description: "围绕用户目标澄清需求、拆解版本范围、沉淀验收口径和路线图。",
            knowledge: ["需求文档", "用户研究", "Figma"],
            capabilities: ["需求分析", "版本规划", "用户研究", "验收标准定义"],
            workStyles: ["用户导向", "数据驱动", "迭代验证", "结构化表达"],
            environment: "云端", avatarColor: .purple,
            joinDate: Calendar.current.date(byAdding: .day, value: -30, to: Date()) ?? Date()
        ),
        Employee(
            id: "kai", name: "小凯", role: "测试工程师",
            device: "MacBook-Pro.local", isOnline: true,
            description: "面向 Web 产品和命令行工具做质量保障，覆盖冒烟、回归和验收。",
            knowledge: ["Playwright", "Jest", "CI/CD"],
            capabilities: ["自动化测试", "回归测试", "性能测试", "CI/CD 集成"],
            workStyles: ["风险优先", "边界覆盖", "可重复验证", "缺陷溯源"],
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
    EmployeeTemplate(id: "designer", title: "UI 设计师",
                     description: "面向产品界面设计、交互原型、设计系统维护和视觉规范输出。",
                     icon: "paintpalette"),
    EmployeeTemplate(id: "devops", title: "DevOps 工程师",
                     description: "面向 CI/CD、部署流水线、环境配置、告警排障与稳定性治理。",
                     icon: "shield.checkered"),
    EmployeeTemplate(id: "ops", title: "内容运营专员",
                     description: "面向内容日历、热点洞察、用户反馈和活动复盘，维护稳定输出节奏。",
                     icon: "megaphone"),
]
