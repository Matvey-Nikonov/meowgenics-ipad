import Foundation

struct GPAKEntry: Identifiable, Hashable, Sendable {
    let path: String
    let offset: UInt64
    let size: Int
    var id: String { path }
    var fileExtension: String { (path as NSString).pathExtension.lowercased() }
}

/// Observed retail layout: LE u32 count, then (LE u16 UTF-8 length, path, LE u32 size),
/// followed by consecutive uncompressed payloads. No executable code is loaded.
struct GPAKArchive: Sendable {
    let url: URL
    let entries: [GPAKEntry]
    let byteCount: UInt64
    let indexByteCount: Int

    init(url: URL) throws {
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        let length = try handle.seekToEnd()
        try handle.seek(toOffset: 0)
        // Read at most 16 MiB even when the archive is several GiB.
        let index = try handle.read(upToCount: 16 * 1024 * 1024) ?? Data()
        var reader = BinaryReader(index)
        let count = try reader.u32()
        guard count > 0, count <= 250_000 else { throw PortError.invalid("Invalid GPAK entry count: \(count).") }
        var table: [(String, Int)] = []
        var names = Set<String>()
        var total: UInt64 = 0
        for _ in 0..<count {
            let nameLength = try reader.u16()
            guard nameLength > 0, nameLength <= 4096,
                  let name = String(data: try reader.data(nameLength), encoding: .utf8),
                  !name.contains("\0"), names.insert(name).inserted else {
                throw PortError.invalid("Invalid or duplicate GPAK path.")
            }
            let size = try reader.u32()
            table.append((name, size))
            total += UInt64(size)
        }
        let indexSize = reader.position
        guard UInt64(indexSize) + total == length else {
            throw PortError.invalid("GPAK sizes do not match the file. It may be incomplete or use a different format.")
        }
        var offset = UInt64(indexSize)
        entries = table.map { path, size in
            defer { offset += UInt64(size) }
            return GPAKEntry(path: path, offset: offset, size: size)
        }
        self.url = url
        byteCount = length
        indexByteCount = indexSize
    }

    func read(_ entry: GPAKEntry, limit: Int = 32 * 1024 * 1024) throws -> Data {
        guard entries.contains(entry), entry.size <= limit else {
            throw PortError.invalid("This asset exceeds the preview limit of \(limit / 1024 / 1024) MiB.")
        }
        return try prefix(entry, count: entry.size)
    }

    func prefix(_ entry: GPAKEntry, count: Int) throws -> Data {
        guard entries.contains(entry), count >= 0, count <= entry.size else {
            throw PortError.invalid("Invalid archive entry or read size.")
        }
        let handle = try FileHandle(forReadingFrom: url)
        defer { try? handle.close() }
        guard try handle.seekToEnd() == byteCount else { throw PortError.invalid("Archive changed. Open it again.") }
        try handle.seek(toOffset: entry.offset)
        let result = try handle.read(upToCount: count) ?? Data()
        guard result.count == count else { throw PortError.invalid("Incomplete asset read.") }
        return result
    }
}
