import Foundation
import SwiftUI

// MARK: - API Response Models

struct APIEmployeeResponse: Decodable {
    let id: String
    let name: String
    let role: String
    let device: String
    let online: Bool
    let description: String
    let knowledge: [String]
    let environment: String
    let accent: String
    let created_at: String

    func toEmployee() -> Employee {
        Employee(
            id: id,
            name: name,
            role: role,
            device: device,
            isOnline: online,
            description: description,
            knowledge: knowledge,
            capabilities: [],
            workStyles: [],
            environment: environment,
            avatarColor: Self.colorForRole(role),
            joinDate: Self.parseDate(created_at) ?? Date()
        )
    }

    private static func colorForRole(_ role: String) -> Color {
        switch role {
        case "Product Manager": return .purple
        case "Frontend Engineer": return .green
        case "Backend Engineer": return .blue
        default: return .cyan
        }
    }

    private static func parseDate(_ string: String) -> Date? {
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let date = formatter.date(from: string) { return date }
        formatter.formatOptions = [.withInternetDateTime]
        return formatter.date(from: string)
    }
}

struct Session: Identifiable, Codable {
    let id: String
    let employeeId: String
    let title: String
    let createdAt: String
    let lastMessagePreview: String?
    let lastMessageAt: String?
    let messageCount: Int

    enum CodingKeys: String, CodingKey {
        case id
        case employeeId = "employee_id"
        case title
        case createdAt = "created_at"
        case lastMessagePreview = "last_message_preview"
        case lastMessageAt = "last_message_at"
        case messageCount = "message_count"
    }
}

struct Message: Identifiable, Codable {
    let id: String
    let sessionId: String
    let role: String
    let content: String
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case sessionId = "session_id"
        case role
        case content
        case createdAt = "created_at"
    }
}

struct EmployeeStats: Codable {
    let employeeId: String
    let daysActive: Int
    let totalSessions: Int
    let totalMessages: Int
    let totalTasks: Int
    let completedTasks: Int
    let autoTasks: Int
    let recentActivity: [[String: String]]
    let activityHeatmap: [String: Int]
    let toolUsage: [String: Int]

    enum CodingKeys: String, CodingKey {
        case employeeId = "employee_id"
        case daysActive = "days_active"
        case totalSessions = "total_sessions"
        case totalMessages = "total_messages"
        case totalTasks = "total_tasks"
        case completedTasks = "completed_tasks"
        case autoTasks = "auto_tasks"
        case recentActivity = "recent_activity"
        case activityHeatmap = "activity_heatmap"
        case toolUsage = "tool_usage"
    }
}

struct APITemplateResponse: Decodable {
    let id: String
    let title: String
    let description: String
    let knowledge: [String]?

    func toTemplate() -> EmployeeTemplate {
        EmployeeTemplate(
            id: id,
            title: title,
            description: description,
            icon: Self.iconForId(id)
        )
    }

    private static func iconForId(_ id: String) -> String {
        switch id {
        case "product", "product-manager": return "list.clipboard"
        case "frontend", "frontend-engineer": return "chevron.left.forwardslash.chevron.right"
        case "backend", "backend-engineer": return "server.rack"
        default: return "person.fill"
        }
    }
}

// MARK: - API Errors

enum APIError: LocalizedError {
    case invalidURL
    case httpError(statusCode: Int, body: String)
    case decodingError(Error)

    var errorDescription: String? {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .httpError(let code, let body):
            return "HTTP \(code): \(body)"
        case .decodingError(let error):
            return "Decoding error: \(error.localizedDescription)"
        }
    }
}

// MARK: - APIClient

class APIClient: ObservableObject {
    let baseURL: String

    init(baseURL: String = "http://127.0.0.1:8140") {
        self.baseURL = baseURL
    }

    // MARK: - Generic Request Helper

    private func request<T: Decodable>(
        _ method: String,
        _ path: String,
        body: (any Encodable)? = nil
    ) async throws -> T {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method
        req.setValue("application/json", forHTTPHeaderField: "Accept")

        if let body {
            req.setValue("application/json", forHTTPHeaderField: "Content-Type")
            req.httpBody = try JSONEncoder().encode(AnyEncodable(body))
        }

        let (data, response) = try await URLSession.shared.data(for: req)

        if let httpResponse = response as? HTTPURLResponse,
           !(200...299).contains(httpResponse.statusCode) {
            let bodyText = String(data: data, encoding: .utf8) ?? ""
            throw APIError.httpError(statusCode: httpResponse.statusCode, body: bodyText)
        }

        do {
            return try JSONDecoder().decode(T.self, from: data)
        } catch {
            throw APIError.decodingError(error)
        }
    }

    /// Fire-and-forget variant for DELETE (no response body).
    private func requestVoid(
        _ method: String,
        _ path: String
    ) async throws {
        guard let url = URL(string: baseURL + path) else {
            throw APIError.invalidURL
        }

        var req = URLRequest(url: url)
        req.httpMethod = method

        let (data, response) = try await URLSession.shared.data(for: req)

        if let httpResponse = response as? HTTPURLResponse,
           !(200...299).contains(httpResponse.statusCode) {
            let bodyText = String(data: data, encoding: .utf8) ?? ""
            throw APIError.httpError(statusCode: httpResponse.statusCode, body: bodyText)
        }
    }

    // MARK: - Employees

    func fetchEmployees() async throws -> [Employee] {
        do {
            let responses: [APIEmployeeResponse] = try await request("GET", "/api/employees")
            return responses.map { $0.toEmployee() }
        } catch {
            print("[APIClient] fetchEmployees failed, falling back to samples: \(error)")
            return Employee.samples
        }
    }

    func createEmployee(name: String, role: String, description: String) async throws -> Employee {
        let body = ["name": name, "role": role, "description": description]
        let response: APIEmployeeResponse = try await request("POST", "/api/employees", body: body)
        return response.toEmployee()
    }

    func deleteEmployee(id: String) async throws {
        try await requestVoid("DELETE", "/api/employees/\(id)")
    }

    // MARK: - Templates

    func fetchTemplates() async throws -> [EmployeeTemplate] {
        let responses: [APITemplateResponse] = try await request("GET", "/api/templates")
        return responses.map { $0.toTemplate() }
    }

    // MARK: - Sessions

    func fetchSessions(employeeId: String) async throws -> [Session] {
        return try await request("GET", "/api/employees/\(employeeId)/sessions")
    }

    func createSession(employeeId: String, title: String) async throws -> Session {
        let body = ["title": title]
        return try await request("POST", "/api/employees/\(employeeId)/sessions", body: body)
    }

    // MARK: - Messages

    func sendMessage(employeeId: String, sessionId: String, content: String) async throws -> Message {
        let body = ["content": content]
        return try await request(
            "POST",
            "/api/employees/\(employeeId)/sessions/\(sessionId)/messages",
            body: body
        )
    }

    func streamMessage(employeeId: String, sessionId: String, content: String) -> AsyncStream<String> {
        AsyncStream { continuation in
            Task {
                do {
                    guard let url = URL(
                        string: "\(baseURL)/api/employees/\(employeeId)/sessions/\(sessionId)/messages/stream"
                    ) else {
                        continuation.finish()
                        return
                    }

                    var req = URLRequest(url: url)
                    req.httpMethod = "POST"
                    req.setValue("application/json", forHTTPHeaderField: "Content-Type")
                    req.httpBody = try JSONEncoder().encode(["content": content])

                    let (bytes, response) = try await URLSession.shared.bytes(for: req)

                    if let httpResponse = response as? HTTPURLResponse,
                       !(200...299).contains(httpResponse.statusCode) {
                        print("[APIClient] streamMessage HTTP \(httpResponse.statusCode)")
                        continuation.finish()
                        return
                    }

                    for try await line in bytes.lines {
                        guard line.hasPrefix("data: ") else { continue }
                        let json = String(line.dropFirst(6))
                        guard let data = json.data(using: .utf8),
                              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
                        else { continue }

                        if let text = obj["text"] as? String {
                            continuation.yield(text)
                        }
                        // event: done sends {"id": "msg_id"} -- we just finish
                        if obj["id"] != nil && obj["text"] == nil {
                            break
                        }
                    }
                    continuation.finish()
                } catch {
                    print("[APIClient] streamMessage error: \(error)")
                    continuation.finish()
                }
            }
        }
    }

    // MARK: - Stats

    func fetchStats(employeeId: String) async throws -> EmployeeStats {
        return try await request("GET", "/api/employees/\(employeeId)/stats")
    }
}

// MARK: - AnyEncodable (type-erased wrapper)

private struct AnyEncodable: Encodable {
    private let _encode: (Encoder) throws -> Void

    init(_ wrapped: any Encodable) {
        _encode = { encoder in
            try wrapped.encode(to: encoder)
        }
    }

    func encode(to encoder: Encoder) throws {
        try _encode(encoder)
    }
}
