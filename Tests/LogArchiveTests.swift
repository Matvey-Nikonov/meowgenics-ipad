import Foundation

private final class FailingMoveManager: FileManager, @unchecked Sendable {
    override func moveItem(at source: URL, to destination: URL) throws {
        throw NSError(domain: "LogArchiveTests", code: 1)
    }
}

@main
struct LogArchiveTests {
    static func main() throws {
        let root = URL(fileURLWithPath: CommandLine.arguments[1], isDirectory: true)
        let fm = FileManager.default
        try fm.createDirectory(at: root, withIntermediateDirectories: true)
        var assertions = 0
        func check(_ condition: Bool, _ message: String) {
            guard condition else { fatalError(message) }
            assertions += 1
        }
        func content(_ url: URL) throws -> String {
            try String(contentsOf: url, encoding: .utf8)
        }
        let sessions = root.appendingPathComponent("sessions", isDirectory: true)
        try fm.createDirectory(at: sessions, withIntermediateDirectories: true)
        let current = sessions.appendingPathComponent("madeira-log.txt")
        try LogArchive.rotate(in: sessions)
        check(try fm.contentsOfDirectory(atPath: sessions.path).isEmpty,
              "First launch should not invent an archive")

        // Actual game failure, followed by the two short JIT handoff processes.
        for text in ["failed-game-session", "requesting-JIT", "JIT-handoff"] {
            try text.write(to: current, atomically: true, encoding: .utf8)
            try LogArchive.rotate(in: sessions)
        }
        check(try content(LogArchive.previousURL(in: sessions, generation: 3)) == "failed-game-session",
              "JIT roundtrip must preserve the failed game session")
        check(try content(LogArchive.previousURL(in: sessions, generation: 1)) == "JIT-handoff",
              "Existing prev.txt path should still mean the last process")

        for index in 1...6 {
            try "session-\(index)".write(to: current, atomically: true, encoding: .utf8)
            try LogArchive.rotate(in: sessions)
        }
        for generation in 1...LogArchive.previousCount {
            check(try content(LogArchive.previousURL(in: sessions, generation: generation)) ==
                  "session-\(7 - generation)", "Archives must retain chronological order")
        }
        check(try fm.contentsOfDirectory(atPath: sessions.path).count == LogArchive.previousCount,
              "Archive count must stay bounded")

        let failure = root.appendingPathComponent("failed-rotation", isDirectory: true)
        try fm.createDirectory(at: failure, withIntermediateDirectories: true)
        let important = failure.appendingPathComponent("madeira-log.txt")
        try "keep-this-crash-evidence".write(to: important, atomically: true, encoding: .utf8)
        do {
            try LogArchive.rotate(in: failure, fileManager: FailingMoveManager())
            fatalError("Injected move failure was swallowed")
        } catch {
            check(try content(important) == "keep-this-crash-evidence",
                  "Failed rotation must preserve the current log for appending")
        }
        print("PASS: \(assertions) log-archive assertions")
    }
}
