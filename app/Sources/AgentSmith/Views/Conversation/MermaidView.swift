import SwiftUI
import WebKit

/// mermaid 代码块 → 矢量图渲染（WKWebView + 离线 mermaid.js）。
/// 语法不完整/渲染失败时回退为等宽源码显示（流式过程中就是这个状态）。
struct MermaidBlockView: View {
    let code: String
    @State private var height: CGFloat = 0
    @State private var failed = false

    var body: some View {
        if failed {
            Text(code)
                .font(.system(size: 12, design: .monospaced))
                .padding(10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 8))
        } else {
            MermaidWebView(code: code, height: $height, failed: $failed)
                .frame(height: max(height, 48))
                .background(Color.white, in: RoundedRectangle(cornerRadius: 8))
                .overlay(
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Color.primary.opacity(0.08), lineWidth: 0.5)
                )
        }
    }
}

private struct MermaidWebView: NSViewRepresentable {
    let code: String
    @Binding var height: CGFloat
    @Binding var failed: Bool

    // 只读一次，全部 MermaidWebView 共享（~2.8MB）
    private static let mermaidJS: String = {
        guard let url = Bundle.module.url(forResource: "mermaid.min", withExtension: "js"),
              let js = try? String(contentsOf: url, encoding: .utf8) else { return "" }
        return js
    }()

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.userContentController.add(context.coordinator, name: "bridge")
        let webView = WKWebView(frame: .zero, configuration: config)
        webView.setValue(false, forKey: "drawsBackground")
        context.coordinator.lastCode = code
        load(into: webView)
        return webView
    }

    func updateNSView(_ webView: WKWebView, context: Context) {
        context.coordinator.parent = self
        if context.coordinator.lastCode != code {
            context.coordinator.lastCode = code
            load(into: webView)
        }
    }

    private func load(into webView: WKWebView) {
        let escaped = code
            .replacingOccurrences(of: "&", with: "&amp;")
            .replacingOccurrences(of: "<", with: "&lt;")
        let html = """
        <!doctype html><html><head><meta charset="utf-8">
        <meta http-equiv="Content-Security-Policy"
              content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; font-src data:; img-src data:;">
        <style>
        body { margin: 0; padding: 8px; background: transparent;
               font-family: -apple-system, 'PingFang SC', sans-serif; }
        .mermaid { display: flex; justify-content: center; }
        </style>
        <script>\(Self.mermaidJS)</script>
        </head><body>
        <pre class="mermaid">\(escaped)</pre>
        <script>
        mermaid.initialize({ startOnLoad: false, theme: 'neutral', securityLevel: 'strict' });
        mermaid.run().then(() => {
            window.webkit.messageHandlers.bridge.postMessage({ h: document.body.scrollHeight });
        }).catch(e => {
            window.webkit.messageHandlers.bridge.postMessage({ err: String(e) });
        });
        </script></body></html>
        """
        webView.loadHTMLString(html, baseURL: nil)
    }

    final class Coordinator: NSObject, WKScriptMessageHandler {
        var parent: MermaidWebView
        var lastCode: String?
        init(_ parent: MermaidWebView) { self.parent = parent }

        func userContentController(
            _ userContentController: WKUserContentController,
            didReceive message: WKScriptMessage
        ) {
            guard let dict = message.body as? [String: Any] else { return }
            DispatchQueue.main.async {
                if let h = dict["h"] as? Double, h > 0 {
                    self.parent.height = CGFloat(h)
                } else if dict["err"] != nil {
                    self.parent.failed = true
                }
            }
        }
    }
}
