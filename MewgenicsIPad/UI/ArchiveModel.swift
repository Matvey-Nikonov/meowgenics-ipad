import Foundation
import SwiftUI

@MainActor
final class ArchiveModel: ObservableObject {
    @Published private(set) var archive: GPAKArchive?
    @Published private(set) var isLoading = false
    @Published var error: String?
    private var scopedURL: URL?

    func open(_ url: URL) async {
        guard !isLoading else { return }
        isLoading = true
        let scoped = url.startAccessingSecurityScopedResource()
        do {
            let result = try await Task.detached(priority: .userInitiated) { try GPAKArchive(url: url) }.value
            scopedURL?.stopAccessingSecurityScopedResource()
            scopedURL = scoped ? url : nil
            archive = result
        } catch {
            if scoped { url.stopAccessingSecurityScopedResource() }
            self.error = error.localizedDescription
        }
        isLoading = false
    }

    /// A simulator launch argument allows a repeatable test without duplicating a 5 GB archive.
    func openLaunchArgument() async {
        #if targetEnvironment(simulator)
        let arguments = ProcessInfo.processInfo.arguments
        if let index = arguments.firstIndex(of: "--archive"), index + 1 < arguments.count {
            await open(URL(fileURLWithPath: arguments[index + 1]))
        }
        #endif
    }

    deinit { scopedURL?.stopAccessingSecurityScopedResource() }
}
