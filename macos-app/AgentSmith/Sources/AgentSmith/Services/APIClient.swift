import Foundation

class APIClient: ObservableObject {
    let baseURL: String

    init(baseURL: String = "http://127.0.0.1:8000") {
        self.baseURL = baseURL
    }

    func fetchEmployees() async throws -> [Employee] {
        return Employee.samples
    }
}
