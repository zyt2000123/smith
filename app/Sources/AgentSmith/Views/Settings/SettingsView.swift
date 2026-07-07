import SwiftUI

enum SettingsSection: String, CaseIterable, Identifiable {
    case general, llm, permissions, about
    var id: String { rawValue }

    var label: String {
        switch self {
        case .general: return "常规"
        case .llm: return "模型"
        case .permissions: return "权限"
        case .about: return "关于"
        }
    }

    var icon: String {
        switch self {
        case .general: return "gearshape"
        case .llm: return "cpu"
        case .permissions: return "shield.lefthalf.filled"
        case .about: return "info.circle"
        }
    }
}

struct SettingsView: View {
    var onBack: (() -> Void)? = nil
    @State private var selected: SettingsSection = .general
    @State private var hoveredSection: SettingsSection?
    @AppStorage("isDarkMode") private var isDarkMode = true
    @AppStorage("fontSizeOption") private var fontSizeOption = AppFontSizeOption.standard.rawValue
    @State private var autoReview = true
    @State private var shellRestricted = true
    @State private var networkAllowed = true
    @State private var llmModel = "GLM-4.7"
    @State private var language = "中文"

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                Button { onBack?() } label: {
                    HStack(spacing: 6) {
                        Image(systemName: "chevron.left").appFont(size: 11, weight: .semibold)
                        Text("返回应用").appFont(size: 13)
                    }
                    .foregroundStyle(.secondary)
                    .padding(.horizontal, 8).padding(.vertical, 6)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 4)

                ForEach(SettingsSection.allCases) { sec in
                    let isSelected = selected == sec
                    let isHovered = hoveredSection == sec

                    Button { selected = sec } label: {
                        HStack(spacing: 8) {
                            Image(systemName: sec.icon).appFont(size: 13)
                                .foregroundStyle(isSelected ? .blue : .secondary).frame(width: 18)
                            Text(sec.label).appFont(size: 13)
                                .foregroundStyle(isSelected ? .blue : .secondary)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.vertical, 7).padding(.horizontal, 10)
                        .sidebarNavigationBackground(isSelected: isSelected, isHovered: isHovered)
                    }
                    .buttonStyle(.plain)
                    .onHover { hovering in
                        hoveredSection = hovering ? sec : nil
                    }
                }
                Spacer()
            }
            .padding(.horizontal, 12)
            .padding(.bottom, 12)
            .padding(.top, FloatingSidebarMetrics.topContentPadding)
            .frame(width: FloatingSidebarMetrics.width)
            .floatingSidebarSurface()
            .padding(FloatingSidebarMetrics.inset)

            ScrollView {
                VStack(alignment: .leading, spacing: 24) {
                    switch selected {
                    case .general: generalSection
                    case .llm: llmSection
                    case .permissions: permissionsSection
                    case .about: aboutSection
                    }
                }
                .padding(.horizontal, 32)
                .padding(.bottom, 32)
                .padding(.top, FloatingSidebarMetrics.rightContentTopInset)
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private var generalSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("常规").appFont(size: 22, weight: .bold)
            card {
                tog("深色模式", sub: "关闭后使用浅色主题", on: $isDarkMode)
                Divider()
                row("语言", sub: "应用 UI 语言") {
                    Picker("", selection: $language) { Text("中文").tag("中文"); Text("English").tag("English") }.frame(width: 120)
                }
                Divider()
                row("字体大小", sub: "调整应用文字显示大小") {
                    Picker("", selection: $fontSizeOption) {
                        ForEach(AppFontSizeOption.allCases) { option in
                            Text(option.label).tag(option.rawValue)
                        }
                    }
                    .frame(width: 120)
                }
                Divider()
                row("数据目录", sub: "~/.agent-smith/") { Button("打开") {}.buttonStyle(.bordered).controlSize(.small) }
            }
        }
    }

    private var llmSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("模型").appFont(size: 22, weight: .bold)
            card {
                row("默认模型", sub: "Agent 对话使用的 LLM") {
                    Picker("", selection: $llmModel) { Text("GLM-4.7").tag("GLM-4.7"); Text("GPT-4o").tag("GPT-4o"); Text("Claude Sonnet").tag("Claude Sonnet") }.frame(width: 150)
                }
                Divider()
                row("API 地址", sub: "LLM 服务端点") { Text("已配置").appFont(size: 12).foregroundStyle(.green) }
                Divider()
                row("API Key", sub: "访问凭证") { Text("••••••").appFont(size: 12, design: .monospaced).foregroundStyle(.secondary) }
            }
        }
    }

    private var permissionsSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("权限").appFont(size: 22, weight: .bold)
            card {
                tog("自动审核", sub: "自动审核额外访问权限请求", on: $autoReview)
                Divider()
                tog("Shell 受限模式", sub: "限制 Agent 执行系统命令", on: $shellRestricted)
                Divider()
                tog("网络访问", sub: "允许 Agent 发起网络请求", on: $networkAllowed)
            }
        }
    }

    private var aboutSection: some View {
        VStack(alignment: .leading, spacing: 20) {
            Text("关于").appFont(size: 22, weight: .bold)
            card {
                row("版本", sub: "Agent Smith") { Text("1.0.0").appFont(size: 13, design: .monospaced).foregroundStyle(.secondary) }
                Divider()
                row("引擎", sub: "自研 Agent 框架") { Text("DAG + ReAct").appFont(size: 12).foregroundStyle(.secondary) }
            }
        }
    }

    private func card<C: View>(@ViewBuilder content: () -> C) -> some View {
        VStack(spacing: 0) { content() }
            .padding(.horizontal, 16).padding(.vertical, 4)
            .background(RoundedRectangle(cornerRadius: 10).fill(AppPalette.card))
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(AppPalette.border, lineWidth: 0.5))
    }

    private func row<T: View>(_ title: String, sub: String, @ViewBuilder trailing: () -> T) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) { Text(title).appFont(size: 14, weight: .medium); Text(sub).appFont(size: 12).foregroundStyle(.secondary) }
            Spacer(); trailing()
        }.padding(.vertical, 10)
    }

    private func tog(_ title: String, sub: String, on: Binding<Bool>) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) { Text(title).appFont(size: 14, weight: .medium); Text(sub).appFont(size: 12).foregroundStyle(.secondary) }
            Spacer(); Toggle("", isOn: on).toggleStyle(.switch).tint(.blue)
        }.padding(.vertical, 10)
    }

}
