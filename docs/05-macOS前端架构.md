# macOS 前端架构

> Agent-Smith 原生桌面客户端架构文档。基于源码逐文件分析，覆盖技术栈、入口、布局、设计系统、数据模型、视图层级与状态管理。

---

## 1. 技术栈

| 维度 | 选型 |
|---|---|
| 语言 | Swift 6.1 |
| UI 框架 | SwiftUI |
| 最低系统 | macOS 15+ |
| 构建系统 | Swift Package Manager (`Package.swift`) |
| 第三方依赖 | **零** — 无任何外部 package |
| 资源打包 | `.copy("Resources/AppIcon.icns")`, `.copy("Resources/Employees")` |

`Package.swift` 只有一个 `.executableTarget`，名为 `AgentSmith`，无 test target。

---

## 2. 应用入口 (`AgentSmithApp.swift`)

```swift
@main
struct AgentSmithApp: App {
    var body: some Scene {
        WindowGroup {
            ContentView()
                .frame(minWidth: 1200, minHeight: 760)
                .onAppear { setAppIcon() }
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1400, height: 860)
    }
}
```

| 配置 | 值 |
|---|---|
| 窗口样式 | `.hiddenTitleBar` |
| 默认尺寸 | 1400 x 860 |
| 最小尺寸 | 1200 x 760 |
| 应用图标 | 运行时从 `Bundle.module` 加载 `AppIcon.icns`，赋值给 `NSApplication.shared.applicationIconImage` |

---

## 3. 主布局 (`ContentView.swift`)

### 3.1 状态声明

| 属性 | 类型 | 用途 |
|---|---|---|
| `isDarkMode` | `@AppStorage("isDarkMode")` | 持久化深色模式，默认 `true` |
| `fontSizeOption` | `@AppStorage("fontSizeOption")` | 持久化字号选项，默认 `standard` |
| `selectedPage` | `@State` `String` | 字符串路由，初始 `"management"` |
| `sidebarVisible` | `@State` `Bool` | 侧栏可见性 |
| `conversationsExpanded` | `@State` `Bool` | 对话分区折叠 |
| `channelsExpanded` | `@State` `Bool` | 频道分区折叠 |
| `hoveredSidebarSection` | `@State` `String?` | 侧栏 hover 状态 |
| `apiClient` | `@StateObject` `APIClient` | 通过 `.environmentObject()` 向下分发 |

数据源 `employees` 为 `private let`，直接引用 `Employee.samples`（硬编码）。

### 3.2 视图结构

```
ZStack
├── AppPalette.canvas (全屏背景)
├── [selectedPage == "settings"]
│   └── SettingsView (全屏，无侧栏)
└── [else]
    └── shellSplitView (HStack, spacing: 0)
        ├── sidebarPanel (条件显示：sidebarVisible && 非 employee- 前缀)
        └── mainPanel (弹性填充)
```

- `.preferredColorScheme` 跟随 `isDarkMode`
- `.environment(\.appFontScale, ...)` 注入字号倍率
- `.environmentObject(apiClient)` 注入 API 客户端
- `.background(WindowChromeConfigurator(...))` 配置窗口 chrome

### 3.3 侧栏

| 属性 | 值 |
|---|---|
| 宽度 | 180pt |
| 背景 | `SidebarMaterialView()` (NSVisualEffectView `.sidebar`) |
| 圆角 | 20pt (`RoundedRectangle(cornerRadius: 20, style: .continuous)`) |
| 描边 | `AppPalette.border.opacity(0.75)`, 0.5pt |
| 阴影 | `black.opacity(0.08)`, radius 14, y 4 |
| 外边距 | 12pt padding |

**分区布局**（从上到下）：

1. **功能入口**（paddingTop 44pt）— "Agent总览" / "定时任务"，选中态 `AppPalette.selectedSurface` 填充
2. **Divider**
3. **ScrollView**
   - **对话列表**（可折叠，hover 显示 "+" 按钮）— 3 条硬编码：
     - "UI review" (Luna, 刚刚)
     - "API deploy" (Theo, 5 分钟前)
     - "Roadmap sync" (Ivy, 1 小时前)
   - **频道列表**（可折叠）— 5 条硬编码：
     - `#全体`（公开）, `前端协作`, `后端架构`, `#产品评审`（公开）, `测试验收`
4. **Spacer**
5. **底部设置按钮**

### 3.4 导航路由（字符串匹配）

| `selectedPage` 值 | 目标视图 |
|---|---|
| `"management"` / `"create"` / `"search"` | `ManagementView` |
| `"conv-*"` / `"new-conv"` | `ConversationView` |
| `"employee-{id}"` | `EmployeeDetailView`（从 `Employee.samples` 查找匹配 id） |
| `"settings"` | `SettingsView`（替换整个 shell，不显示侧栏） |
| 其他 | "功能开发中..." 占位 |

当 `selectedPage` 以 `"employee-"` 开头时，侧栏自动隐藏。

### 3.5 `WindowChromeConfigurator`

`NSViewRepresentable`，负责定制窗口标题栏：

| 功能 | 实现 |
|---|---|
| 标题栏 | `titleVisibility = .hidden`, `titlebarAppearsTransparent = true` |
| 窗口行为 | `isMovableByWindowBackground = true`, `fullSizeContentView` |
| 交通灯位置 | 重新定位 close/minimize/zoom 按钮，`sidebarInset + 12` 水平偏移 |
| 侧栏切换按钮 | `HoverChromeButton`，使用 `sidebar.leading` SF Symbol，28x24 尺寸 |

**`HoverChromeButton`** 私有 `NSButton` 子类：
- 通过 `NSTrackingArea` 跟踪 hover
- 图标颜色：`chromeColor.withAlphaComponent(0.72)`，hover 背景 `chromeColor.withAlphaComponent(0.08)`
- 8px 圆角
- 响应 `viewDidChangeEffectiveAppearance()` 适配深色/浅色主题切换

**常量**：

| 名称 | 值 |
|---|---|
| `buttonSize` | 16 |
| `buttonSpacing` | 10 |
| `toggleButtonGap` | 16 |
| `toggleButtonSize` | 28 x 24 |
| `verticalOffset` | -4 |

---

## 4. 设计系统

### 4.1 `AppPalette`（语义色）

无实例枚举（namespace），所有颜色为 `static let`。通过 `NSColor(name:)` 动态 provider 实现自适应深色/浅色：

| Token | Light (sRGB) | Dark (sRGB) |
|---|---|---|
| `canvas` | (0.992, 0.994, 0.996) | (0.105, 0.105, 0.115) |
| `card` | (0.985, 0.987, 0.989) | (0.145, 0.145, 0.155) |
| `mutedSurface` | (0.935, 0.940, 0.945) | (0.185, 0.185, 0.200) |
| `selectedSurface` | (0.890, 0.895, 0.900) | (0.225, 0.225, 0.240) |
| `border` | (0.875, 0.882, 0.890) | (0.275, 0.275, 0.295) |
| `online` | 固定 (0.12, 0.68, 0.34) | 不随主题变化 |

```swift
private static func adaptive(light: NSColor, dark: NSColor) -> Color {
    Color(nsColor: NSColor(name: nil) { appearance in
        appearance.bestMatch(from: [.darkAqua, .aqua]) == .darkAqua ? dark : light
    })
}
```

### 4.2 `appCardSurface(cornerRadius:)` View 扩展

统一卡片样式，默认 `cornerRadius = 12`：

| 层 | 样式 |
|---|---|
| 填充 | `AppPalette.card` |
| 阴影 | `black.opacity(0.035)`, radius 8, y 2 |
| 描边 | `AppPalette.border`, 0.5pt |

### 4.3 `AppTypography`（字号系统）

**`AppFontSizeOption` 枚举**：

| Case | `rawValue` | `scale` | `label` |
|---|---|---|---|
| `.small` | `"small"` | 0.9 | "小" |
| `.standard` | `"standard"` | 1.0 | "标准" |
| `.large` | `"large"` | 1.12 | "大" |

**传递机制**：

1. `AppFontScaleKey: EnvironmentKey`（默认值 1.0）
2. `EnvironmentValues.appFontScale` 属性
3. `AppFontModifier: ViewModifier` — 读取 `@Environment(\.appFontScale)`，应用 `.system(size: size * scale, weight, design)`
4. `View.appFont(size:weight:design:)` — 便捷方法，全局统一字号 API

所有视图使用 `.appFont(size:)` 而非原生 `.font()`，确保字号偏好全局生效。

---

## 5. 数据模型 (`Models/Employee.swift`)

### 5.1 `Employee`

```swift
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
    var environment: String        // "Cloud" | "Local"
    var avatarColor: Color
    var joinDate: Date
}
```

- `localizedRole` 计算属性：`"Product Manager"` -> `"产品经理"`, `"Frontend Engineer"` -> `"前端工程师"`, `"Backend Engineer"` -> `"后端工程师"`
- `Hashable`/`Equatable` 仅基于 `id`

### 5.2 `Employee.samples`（3 条硬编码数据）

| id | name | role | color | environment | online | joinDate |
|---|---|---|---|---|---|---|
| `"ivy"` | Ivy | Product Manager | purple | Cloud | true | 30 天前 |
| `"luna"` | Luna | Frontend Engineer | green | Local | true | 今天 |
| `"theo"` | Theo | Backend Engineer | blue | Local | true | 7 天前 |

所有Agent的 `device` 均为 `"AA01030deMacBook-Pro.local"`。头像图片分别为 `product-manager.png`、`frontend-engineer.png`、`backend-engineer.png`，存放于 `Resources/Employees/` 目录。

### 5.3 `EmployeeTemplate`

```swift
struct EmployeeTemplate: Identifiable {
    let id: String
    let title: String
    let description: String
    let icon: String       // SF Symbol 名
}
```

全局常量 `employeeTemplates` 包含 3 个模板（product / frontend / backend），与 `Employee.samples` 一一对应。

---

## 6. API 集成 (`Services/APIClient.swift`)

```swift
class APIClient: ObservableObject {
    let baseURL: String   // 默认 "http://127.0.0.1:8000"

    func fetchEmployees() async throws -> [Employee] {
        return Employee.samples   // stub，无实际网络调用
    }
}
```

通过 `@StateObject` 创建于 `ContentView`，通过 `.environmentObject()` 注入整个视图树。当前为纯 stub。

---

## 7. 视图层级

### 7.1 管理视图 (`Views/Management/`)

#### `ManagementView`

| 状态 | 类型 | 用途 |
|---|---|---|
| `employees` | `@State [Employee]` | 初始 `Employee.samples` |
| `showCreateSheet` | `@State Bool` | 控制创建面板 |
| `selectedSegment` | `@State Int` | 顶部 tab（我的Agent/我的群组） |
| `statusFilter` | `@State String` | 在线/离线/全部 |
| `envFilter` | `@State String` | 本地/云端/全部 |
| `searchText` | `@State String` | 搜索关键字 |

- **回调**: `var onOpenEmployee: (Employee) -> Void`（非 Binding，由父视图传入）
- **计算属性** `filteredEmployees`：按状态、环境、搜索文本（name/role）组合过滤
- **布局**：ScrollView -> 标题（"我的Agent" + "新建Agent"按钮） -> 筛选栏（Segmented Picker + 状态/环境下拉菜单 + 搜索框） -> 2 列 `LazyVGrid` Agent卡片
- **Sheet**：`CreateEmployeeSheet`，模态弹出

#### `EmployeeCardView`

- **输入**：`employee: Employee`, `onTap: () -> Void`
- **布局**：Button 包裹 HStack，左侧 `EmployeePortraitView`（140x172, cornerRadius 20），右侧名称/角色 badge/设备/在线状态/描述/操作按钮
- **交互**：hover 放大 `scaleEffect(1.01)` + 增大阴影，`.easeOut(duration: 0.15)` 动画
- **上下文菜单**：`"..."` 按钮，选项 "编辑" / "删除"

#### `CreateEmployeeSheet`

- **Binding**：`employees: [Employee]`, `isPresented: Bool`
- **固定尺寸**：640 x 720
- **布局**：Header（关闭按钮） -> 模板选择（2 列 grid，`employeeTemplates`） -> 名称 TextField -> 头像颜色选择器（8 色圆形：blue/green/orange/purple/red/pink/cyan/mint，选中带蓝色圆环） -> 描述 TextEditor -> Footer（取消 + "保存并启用"）
- **保存逻辑**：创建新 `Employee`（UUID id），追加到 `employees` 数组

### 7.2 Agent详情 (`Views/Employee/`)

#### `EmployeeDetailView`

**标签页枚举 `EmployeeDetailTab`**（9 个 case）：

| Case | 标签 | 图标 | 选中图标 |
|---|---|---|---|
| `home` | 首页 | `house` | `house.fill` |
| `projects` | 项目 | `folder` | `folder.fill` |
| `automations` | 自动任务 | `clock.arrow.circlepath` | 同 |
| `tasks` | 任务 | `list.bullet.rectangle.portrait` | `.fill` |
| `memory` | 记忆 | `brain.head.profile` | `.fill` |
| `skills` | 技能 | `puzzlepiece` | `.fill` |
| `connectors` | 连接器 | `link` | 同 |
| `im` | IM | `message` | `message.fill` |
| `permissions` | 权限 | `shield` | `shield.fill` |

- **布局**：HStack（12pt spacing） -> 左侧 employeeSidebar（180pt） + 右侧 ScrollView 内容区
- **侧栏**：返回按钮（"我的Agent"） -> 头像（48x58） + 姓名 + 在线状态 -> 标签页列表（选中蓝色高亮 `blue.opacity(0.12)`，hover `mutedSurface`）
- **内容路由**：switch on `selectedTab`
  - `.home` -> `EmployeeHomeView`
  - `.skills` -> `EmployeeSkillsView`
  - `.memory` -> `EmployeeMemoryView`
  - `.tasks` -> `EmployeeTasksView`
  - `.automations` -> `EmployeeAutomationsView`
  - `.connectors` -> `EmployeeConnectorsView`
  - `.permissions` -> `EmployeePermissionsView`
  - `.im`, `.projects` -> 空状态占位（图标 + 标题）

#### `EmployeeHomeView`

首页视图，VStack（24pt spacing）包含 6 个区块：

1. **身份卡** (`identitySection`)：`EmployeePortraitView`（96x118, -4 度旋转, 阴影） + 姓名 + `localizedRole` badge + 在线状态 + 描述 + "编辑资料"按钮，包裹 `appCardSurface()`
2. **工作记录** (`WorkRecordView`)：组件
3. **记忆时间线** (`MemoryTimelineView`)：组件
4. **关于我** (`aboutMeSection`)：3 列 HStack
   - "我最擅长"：4 条硬编码优势（视觉还原/组件化/交互细节/跨端适配）
   - "工作风格"：`FlowLayout` 标签云，数据来自 `employee.workStyles`
   - "工作模式"：4 条硬编码模式（构建新界面/修复交互/优化体验/重构组件）
5. **能力与工具** (`skillsAndToolsSection`)：capabilities `FlowLayout` 标签（绿点 + 蓝底） + 连接器占位
6. **原始档案** (`rawFilesSection`)：4 列 `LazyVGrid`，文件卡片：IDENTITY.md / BIBLE.md / MEMORY.md / PERSONA.md

#### 其余标签页视图

| 视图 | 内容 |
|---|---|
| `EmployeeSkillsView` | 3 列 `LazyVGrid` 技能卡片（6 条硬编码：planning/code-review/testing-strategy/sde-debug/architecture/system-design），绿/灰 active 指示 |
| `EmployeeMemoryView` | `MEMORY.md` 代码预览块（hardcoded markdown）+ 事件时间线（3 条：学习组件架构/完成性能优化/建立设计系统） |
| `EmployeeTasksView` | 表格（ID/名称/来源/状态/创建时间），3 条硬编码任务，状态 badge 色彩编码（蓝=进行中, 绿=已完成, 橙=待处理） |
| `EmployeeAutomationsView` | Header + Cron/Webhook 信息提示 + 虚线边框空状态 |
| `EmployeeConnectorsView` | Header + "添加"/"导入 JSON" 按钮 + 虚线边框空状态 |
| `EmployeePermissionsView` | 工具权限规则（Bash:Ask, Read:Allow, Write:Ask, Edit:Ask, WebFetch:Allow, WebSearch:Deny）+ 文件权限规则（~/.ssh/*:Deny, ~/.env*:Deny, ~/Projects/**:Allow, /tmp/**:Allow），等宽字体 pattern + 色彩 badge |

### 7.3 对话视图 (`Views/Conversation/ConversationView`)

**辅助类型**：

| 类型 | 字段 |
|---|---|
| `ConversationItem` | `employeeName`, `avatarColor`, `preview`, `timestamp` |
| `SuggestionCard` | `text` |
| `CapabilityPanelTab` | `.plan`/`.mcp`/`.skills`/`.permissions`/`.knowledge` |

**状态**：`messageText`, `selectedConversation: UUID?`, `showCapabilityPanel: Bool`, `selectedPanelTab`

**三列布局**（HStack, spacing 0）：

| 列 | 宽度 | 背景 | 内容 |
|---|---|---|---|
| 会话列表 | 280pt | `.ultraThinMaterial` | 标题栏 + 对话列表（3 条 hardcoded：Luna/Theo/Ivy），圆形头像 + 名称 + 时间戳 + 预览 |
| 消息区 | 弹性 | `windowBackgroundColor` | 顶部工具栏（"创建对话任务"/"创建自动任务"按钮 + 能力面板切换） + 中央欢迎页（蓝色圆形 "丁" + "你好，今天我能帮你什么？"） + 3 张建议卡片 + 底部输入栏（工作目录按钮 + "Auto" badge + TextField + 发送按钮） |
| 能力面板 | 240pt | `.ultraThinMaterial` | 可切换显示/隐藏，5 个标签页 |

**能力面板标签页内容**：

| Tab | 标题 | 硬编码条目 |
|---|---|---|
| `plan` | 执行计划 | 4 步骤（理解需求/分析影响/编写代码/验证测试） |
| `mcp` | 可用工具 | 5 工具（read_file/write_file/shell/search_knowledge/web_fetch） |
| `skills` | 已加载技能 | 3 技能（planning/code-review/testing-strategy） |
| `permissions` | 权限边界 | 3 条（工作目录/Shell 受限/网络允许） |
| `knowledge` | 知识库连接 | 2 条（Hub API 已连接/本地文档索引 128 条） |

### 7.4 设置视图 (`Views/Settings/SettingsView`)

**`SettingsSection` 枚举**（4 个 case）：

| Case | 标签 | 图标 |
|---|---|---|
| `general` | 常规 | `gearshape` |
| `llm` | 模型 | `cpu` |
| `permissions` | 权限 | `shield.lefthalf.filled` |
| `about` | 关于 | `info.circle` |

**状态**：

| 属性 | 类型 | 持久化 |
|---|---|---|
| `isDarkMode` | `@AppStorage` | 是 |
| `fontSizeOption` | `@AppStorage` | 是 |
| `selected` | `@State` | 否 |
| `autoReview` | `@State` | 否 |
| `shellRestricted` | `@State` | 否 |
| `networkAllowed` | `@State` | 否 |
| `llmModel` | `@State` | 否 |
| `language` | `@State` | 否 |

> 注意：除 `isDarkMode` 和 `fontSizeOption` 外，其余设置项均为 `@State`，不会持久化。

**布局**：HStack -> 左侧栏（180pt, SidebarMaterialView, 同样式侧栏） + 右侧 ScrollView

**4 个设置面板**：

| Section | 内容 |
|---|---|
| 常规 | 深色模式 Toggle + 语言 Picker（中文/English） + 字号 Picker（小/标准/大） + 数据目录（`~/.agent-smith/`）|
| 模型 | 默认模型 Picker（GLM-4.7/GPT-4o/Claude Sonnet） + API 地址状态 + API Key（掩码显示） |
| 权限 | 自动审核 Toggle + Shell 受限模式 Toggle + 网络访问 Toggle |
| 关于 | 版本 `1.0.0` + 引擎 `DAG + ReAct` |

辅助方法 `card()` / `row()` / `tog()` 提供一致的设置行格式化。

---

## 8. 组件 (`Components/`)

### 8.1 `EmployeePortraitView`

头像组件，支持图片或渐变色 fallback。

| 参数 | 类型 | 说明 |
|---|---|---|
| `imageName` | `String?` | 图片名（从 `Bundle.module` `Employees/` 子目录加载 PNG） |
| `fallbackColor` | `Color` | 无图时的渐变底色 |
| `fallbackText` | `String` | 无图时居中显示的文字 |
| `width` / `height` | `CGFloat` | 尺寸 |
| `cornerRadius` | `CGFloat` | 圆角 |

Fallback 显示：`RoundedRectangle` + `fallbackColor.gradient` 填充 + 文字（字号 = `width * 0.28`）。

### 8.2 `WorkRecordView`

工作记录卡片，包含统计数据和 GitHub 风格热力图。

| 区域 | 细节 |
|---|---|
| 标签页 | 3 个 tab：时间线视图 / 对话任务 / 自动任务 |
| 统计卡 | 4 张：入职天数（`joinDate` 计算） / 自动任务 (0) / 对话任务 (0) / 已创建的项目 (0) |
| 热力图 | 20 列 x 7 行，12x12 圆角方块 |
| 热力图颜色 | 空=`secondary.opacity(0.08)`，有值=`blue.opacity(0.15 ~ 0.80)` |
| 热力图数据 | 确定性伪随机：`(week * 7 + day + employee.id.hashValue) % 100` |
| 图例 | "少" 到 "多"，5 级色阶 |

### 8.3 `MemoryTimelineView`

水平滚动的技能学习时间线。

- 4 个硬编码节点：blue(组件架构) / cyan(状态管理) / indigo(性能优化) / teal(测试策略)
- 每个节点：彩色圆形（14pt, 带 3pt 环） + "学到新技能" 标签 + 技能名
- 节点间连线：`Rectangle` 蓝色 20% 不透明度，60pt 宽，2pt 高
- 整体包裹 `appCardSurface()`

### 8.4 `SidebarMaterialView`

```swift
struct SidebarMaterialView: NSViewRepresentable {
    // NSVisualEffectView, material: .sidebar, blending: .behindWindow, state: .active
}
```

毛玻璃材质背景，用于所有侧栏面板（ContentView / EmployeeDetailView / SettingsView）。

### 8.5 `FlowLayout`

自定义 SwiftUI `Layout` 协议实现，水平换行标签云。

- 默认 `spacing: 8`
- 实现 `sizeThatFits` 和 `placeSubviews`
- 换行逻辑：当 `x + size.width > maxWidth` 且 `x > 0` 时换行
- 用于工作风格标签、能力标签等场景

---

## 9. 状态管理总结

| 机制 | 用途 | 实例 |
|---|---|---|
| `@State` | 视图内局部状态 | `selectedPage`, `sidebarVisible`, `isHovered`, `selectedTab`, ... |
| `@AppStorage` | UserDefaults 持久化偏好 | `isDarkMode`, `fontSizeOption` |
| `@StateObject` | 引用类型生命周期管理 | `APIClient`（创建于 ContentView） |
| `@EnvironmentObject` | 跨视图树共享对象 | `APIClient` |
| `@Environment` | 自定义环境值 | `appFontScale` |
| `@Binding` | 子视图 <-> 父视图双向通信 | `CreateEmployeeSheet` 的 `employees` 和 `isPresented` |
| 闭包回调 | 单向事件通知 | `ManagementView.onOpenEmployee`, `EmployeeDetailView.onBack` |

**不使用**：Combine Publishers, `@Observable` (Observation 框架), NavigationStack, NavigationSplitView。

---

## 10. 目录结构

```
app/AgentSmith/
├── Package.swift
└── Sources/AgentSmith/
    ├── AgentSmithApp.swift
    ├── ContentView.swift
    ├── WindowChromeConfigurator.swift
    ├── Models/
    │   └── Employee.swift
    ├── Services/
    │   └── APIClient.swift
    ├── Components/
    │   ├── AppPalette.swift
    │   ├── AppTypography.swift
    │   ├── SidebarMaterialView.swift
    │   ├── EmployeePortraitView.swift
    │   ├── MemoryTimelineView.swift
    │   └── WorkRecordView.swift
    ├── Views/
    │   ├── Settings/
    │   │   └── SettingsView.swift
    │   ├── Management/
    │   │   ├── ManagementView.swift
    │   │   ├── CreateEmployeeSheet.swift
    │   │   └── EmployeeCardView.swift
    │   ├── Employee/
    │   │   ├── EmployeeDetailView.swift
    │   │   ├── EmployeeHomeView.swift
    │   │   ├── EmployeeSkillsView.swift
    │   │   ├── EmployeeMemoryView.swift
    │   │   ├── EmployeeTasksView.swift
    │   │   ├── EmployeeAutomationsView.swift
    │   │   ├── EmployeeConnectorsView.swift
    │   │   └── EmployeePermissionsView.swift
    │   └── Conversation/
    │       └── ConversationView.swift
    └── Resources/
        ├── AppIcon.icns
        └── Employees/
            ├── frontend-engineer.png
            ├── product-manager.png
            └── backend-engineer.png
```

---

## 11. 当前限制

| 限制 | 说明 |
|---|---|
| 数据全部硬编码 | `Employee.samples` 为唯一数据源，`APIClient.fetchEmployees()` 直接返回 samples |
| 侧栏内容硬编码 | 对话列表（3 条）和频道列表（5 条）为常量 |
| 导航为字符串匹配 | 未使用 `NavigationStack` / `NavigationSplitView`，路由基于 `selectedPage` 字符串前缀匹配 |
| 设置不持久化 | 除深色模式和字号外，模型选择、语言、权限 Toggle 等均为 `@State`，重启丢失 |
| 详情标签页多为占位 | `EmployeeSkillsView` / `EmployeeMemoryView` / `EmployeeTasksView` 等使用硬编码数据；`EmployeeAutomationsView` / `EmployeeConnectorsView` 为空状态 |
| 无 `@Observable` | 未采用 Swift 5.9+ Observation 框架，仍使用 `ObservableObject` + `@StateObject` |
| `FlowLayout` 定义位置 | `FlowLayout` 定义在 `EmployeeHomeView.swift` 文件底部而非独立组件文件 |
| 侧栏样式重复 | 180pt 宽 + SidebarMaterialView + 20px 圆角 + border + shadow 的侧栏样式在 ContentView、EmployeeDetailView、SettingsView 中各自重复，未提取为公共组件 |
