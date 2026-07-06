import SwiftUI

/// 轻量 Markdown 渲染：标题/列表/代码块/表格/分隔线按块渲染，
/// 行内粗体、斜体、`code` 交给 AttributedString。
/// ponytail: 不做嵌套列表和图片，聊天气泡够用；需要完整渲染时换 swift-markdown-ui
struct MarkdownText: View {
    let content: String

    var body: some View {
        let blocks = Self.parse(content)
        VStack(alignment: .leading, spacing: 8) {
            ForEach(blocks.indices, id: \.self) { i in
                render(blocks[i])
            }
        }
    }

    private enum Block {
        case heading(level: Int, text: String)
        case bullet(text: String)
        case ordered(marker: String, text: String)
        case code(text: String)
        case mermaid(text: String)
        case table(header: [String]?, rows: [[String]])
        case rule
        case paragraph(text: String)
    }

    private static func parse(_ s: String) -> [Block] {
        var blocks: [Block] = []
        var codeBuffer: [String]?
        var codeLang = ""
        var tableBuffer: [String] = []

        func splitCells(_ line: String) -> [String] {
            var trimmed = line.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("|") { trimmed.removeFirst() }
            if trimmed.hasSuffix("|") { trimmed.removeLast() }
            return trimmed.split(separator: "|", omittingEmptySubsequences: false)
                .map { $0.trimmingCharacters(in: .whitespaces) }
        }

        func isSeparatorRow(_ cells: [String]) -> Bool {
            !cells.isEmpty && cells.allSatisfy { $0.wholeMatch(of: /:?-{2,}:?/) != nil }
        }

        func flushTable() {
            guard !tableBuffer.isEmpty else { return }
            var rows = tableBuffer.map(splitCells)
            tableBuffer = []
            var header: [String]? = nil
            if rows.count >= 2, isSeparatorRow(rows[1]) {
                header = rows[0]
                rows.removeFirst(2)
            }
            blocks.append(.table(header: header, rows: rows))
        }

        for rawLine in s.components(separatedBy: "\n") {
            if codeBuffer != nil {
                if rawLine.hasPrefix("```") {
                    let text = codeBuffer!.joined(separator: "\n")
                    blocks.append(codeLang == "mermaid" ? .mermaid(text: text) : .code(text: text))
                    codeBuffer = nil
                } else {
                    codeBuffer!.append(rawLine)
                }
                continue
            }
            let trimmed = rawLine.trimmingCharacters(in: .whitespaces)
            if trimmed.hasPrefix("```") {
                flushTable()
                codeBuffer = []
                codeLang = String(trimmed.dropFirst(3)).trimmingCharacters(in: .whitespaces).lowercased()
                continue
            }
            if trimmed.hasPrefix("|") { tableBuffer.append(trimmed); continue }
            flushTable()
            if trimmed.isEmpty { continue }

            if trimmed.wholeMatch(of: /[-*_]{3,}/) != nil {
                blocks.append(.rule)
            } else if let m = trimmed.firstMatch(of: /^(#{1,4})\s+(.+)$/) {
                blocks.append(.heading(level: m.1.count, text: String(m.2)))
            } else if let m = trimmed.firstMatch(of: /^[-*•]\s+(.+)$/) {
                blocks.append(.bullet(text: String(m.1)))
            } else if let m = trimmed.firstMatch(of: /^(\d+)[.、)]\s+(.+)$/) {
                blocks.append(.ordered(marker: String(m.1), text: String(m.2)))
            } else {
                blocks.append(.paragraph(text: trimmed))
            }
        }
        if let buf = codeBuffer { blocks.append(.code(text: buf.joined(separator: "\n"))) }
        flushTable()
        return blocks
    }

    @ViewBuilder
    private func render(_ block: Block) -> some View {
        switch block {
        case .heading(let level, let text):
            inline(text)
                .appFont(size: level <= 2 ? 15 : 13.5, weight: .bold)
                .padding(.top, 2)
        case .bullet(let text):
            HStack(alignment: .top, spacing: 6) {
                Text("•").appFont(size: 13)
                inline(text).appFont(size: 13)
            }
        case .ordered(let marker, let text):
            HStack(alignment: .top, spacing: 6) {
                Text("\(marker).").appFont(size: 13)
                inline(text).appFont(size: 13)
            }
        case .code(let text):
            Text(text)
                .font(.system(size: 12, design: .monospaced))
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        case .mermaid(let text):
            MermaidBlockView(code: text)
        case .table(let header, let rows):
            Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 7) {
                if let header {
                    GridRow {
                        ForEach(header.indices, id: \.self) { i in
                            inline(header[i]).appFont(size: 12, weight: .semibold)
                        }
                    }
                    Divider()
                }
                ForEach(rows.indices, id: \.self) { r in
                    GridRow {
                        ForEach(rows[r].indices, id: \.self) { c in
                            inline(rows[r][c]).appFont(size: 12)
                        }
                    }
                    if r < rows.count - 1 {
                        Divider().opacity(0.4)
                    }
                }
            }
            .padding(10)
            .background(Color.primary.opacity(0.03), in: RoundedRectangle(cornerRadius: 8))
            .overlay(
                RoundedRectangle(cornerRadius: 8)
                    .stroke(Color.primary.opacity(0.08), lineWidth: 0.5)
            )
        case .rule:
            Divider().padding(.vertical, 2)
        case .paragraph(let text):
            inline(text).appFont(size: 13)
        }
    }

    private func inline(_ text: String) -> Text {
        if let attr = try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        ) {
            return Text(attr)
        }
        return Text(text)
    }
}
