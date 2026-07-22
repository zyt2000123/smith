# Shell 组件采纳决策与人工开发评审

> 状态：已实施的 Shell 前端决策。本文约束开发过程中的人工评审，不向
> Agent 运行时引入新的人工审批步骤。

## 目标与非目标

目标是让 `shell/` 在保留 Ink/React、Zustand、HTTP/SSE 和现有键盘路由的
前提下，获得可复用的终端展示组件，并让 Markdown 表格、diff 和流式输出在
窄终端中不丢内容。

这不是把 CodeBuddy 或 Codex CLI 迁入 Smith：

- 不复制外部 CLI 的源代码、raw-mode 管理或 Rust 渲染器。
- 不更改 `engine/`、`server/`、SSE 事件、工具审批或 Agent 的运行时决策。
- “人工参与”仅指需求确认、设计取舍、视觉验收和代码评审；Agent 执行期间的
  安全审批仍由既有 `ToolGuard`/审批事件处理。

## 已定下的采纳边界

| 类别 | 决定 | 当前实现 | 边界与理由 |
| --- | --- | --- | --- |
| 终端框架 | 直接复用既有 Ink + React 19 | `shell/src/index.tsx` | Shell 已有完整渲染、焦点与输入生命周期；不引入第二套 TUI 框架。 |
| 普通 Markdown | 保留既有 `@assistant-ui/react-ink-markdown` | `transcript.tsx` | 它继续负责正文、列表与常规 Markdown。 |
| GFM 表格解析 | 直接复用 `marked` 的 AST | `markdown-table.tsx` | 解析语义，不用字符串按 `|` 切割；避免转义管道等误判。 |
| 显示宽度 | 直接复用 `string-width` | `text-layout.ts` | 宽度以终端显示宽度计算，覆盖 CJK/emoji。 |
| 文本换行 | Smith 自研 | `text-layout.ts`、`display-text.tsx` | 普通正文可保留 URL；表格和 diff 选择强制断长 token，绝不省略内容。 |
| 网格表格 | Smith 自研 | `markdown-table.tsx` | 固定为 Unicode 网格、按列分配宽度、逐单元格换行。极端物理宽度记录 `overflowed`，不改成卡片或静默丢字段。 |
| 流式 Markdown | Smith 自研 | `streaming-markdown.ts` | 未闭合表格/围栏保留在动态区，完整后才提交至 scrollback。 |
| 富文本 diff | Smith 自研 | `diff-block.tsx` | 行号、增删颜色、词级变化、续行缩进和宽度安全换行；只在完整 fenced diff 后显示。 |
| 面板边界 | Smith 自研、仅展示层 | `panel-container.tsx` | 统一标题、说明、内容、底部提示；不拥有状态、键盘或网络调用。 |
| Tab 展示 | Smith 自研、仅展示层 | `tabbed-panel.tsx` | `TokenStatsPanel` 传入当前 tab；左右键仍由 `input.ts` 解释。 |
| 多选列表 | Smith 自研、仅展示层 | `multi-select-list.tsx` | `SkillTogglePanel` 传入可视窗口和 enabled 状态；选择、过滤、保存仍留在 Store/Bridge。 |

## 明确不采纳

| 来源/做法 | 决定 | 原因 |
| --- | --- | --- |
| CodeBuddy 表格超过若干行后转为 `Header: value` 纵向字段 | 不采纳 | 产品要求是始终保留完整网格表格，不能在窄宽度自动变为另一种文档表示。 |
| CodeBuddy 的 bundled formatter 或组件源码 | 不复制 | 只借鉴“显示宽度、强制断词、内容不截断”的设计原则；保留清晰的许可证、版本和维护边界。 |
| Codex CLI 的 ratatui/pulldown-cmark 渲染器 | 不迁移 | 它属于 Rust TUI；Smith 的真实渲染生命周期是 Ink/React，迁移会重建输入、焦点、scrollback 和测试基础设施。 |
| 第二套 MultiSelect/Tab 输入与焦点系统 | 不采纳 | `input.ts` + `list-navigation.ts` 已经是唯一键盘路由/可视窗口边界。展示组件不得截获按键。 |
| 前端按文本推断 Agent 运行状态 | 不采纳 | 状态来自 Store 的显式 SSE 事件；渲染层不成为安全或执行决策中心。 |

## 组件责任图

```text
ShellContent / panel state
  ├─ PanelContainer       标题、说明、内容、提示的视觉边界
  ├─ TokenStatsPanel
  │    └─ TabbedPanel     当前 tab 的视觉状态
  ├─ SkillTogglePanel
  │    └─ MultiSelectList 当前可见窗口、勾选与焦点的视觉状态
  └─ TranscriptEntryView
       ├─ MarkdownText    常规正文
       ├─ MarkdownTableBlock
       ├─ DiffBlock
       └─ DisplayText

input.ts + list-navigation.ts  键盘、焦点、翻页、选择
store.ts + bridge.ts           状态、HTTP/SSE、保存技能开关
```

上图的下两层不能反向依赖展示组件；新增展示组件也不能直接调用 `api.ts`。

## 人工参与的开发关卡

每次继续扩展这条前端路线时，开发者与产品/架构评审者按下面的关卡协作：

1. **范围确认（人工）**：确认是“展示问题”还是需要增加真实运行时事件；若后者，
   另起 Engine/Server 设计，不把语义伪装成前端组件。
2. **采纳决策（人工）**：在本表新增一行，明确“直接复用依赖”“借鉴行为、自研代码”
   或“不采纳”，并记录为什么。
3. **红绿测试（开发）**：先写用户可见的 Ink 渲染或纯布局测试，再加入最小实现；
   不能仅以静态类型通过代替内容保留验证。
4. **宽度验收（人工）**：至少在 40、80、120 列检查 CJK、长无空格 ID/路径、URL、
   多列表格、流式未完成表格和 fenced diff。表格必须仍为网格，且所有字符可追溯。
5. **输入回归（人工 + 自动）**：验证 `↑/↓`、`Enter`、`Esc` 和 `←/→` 的含义没有被
   展示组件截获；打开/关闭面板后 Composer 焦点恢复正常。
6. **独立评审（开发）**：审查边界、重复抽象、未覆盖的异常路径和文档是否仍和真实
   源码一致；发现问题后修复并重新跑质量门禁。

## 发布前验收清单

- [ ] `shell/src/` 的展示组件不 import `bridge.ts`、`api.ts` 或 `store.ts`。
- [ ] 新表格/diff/流式逻辑都有内容完整性和窄宽度回归测试。
- [ ] `npm run check`、`npm run build`、`npm test`、`npm pack --dry-run` 均通过。
- [ ] `git diff --check` 通过，且混合工作区中只审查/提交 Shell 与文档的目标文件。
- [ ] 人工确认没有把 Agent 的运行时安全审批改成“开发过程的人工参与”。

## 后续扩展阈值

现有 `PanelContainer`、`TabbedPanel`、`MultiSelectList` 是小而明确的展示原语。只有在
第三个独立面板需要同一种视觉契约时才继续提炼；若需求是新的键盘/焦点模型，应先修改
`input.ts` 和 `list-navigation.ts` 的显式契约，再考虑组件 API。
