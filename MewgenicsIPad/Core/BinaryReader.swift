import Foundation

enum PortError: Error, LocalizedError {
    case invalid(String)
    var errorDescription: String? {
        switch self { case .invalid(let message): return message }
    }
}

struct BinaryReader {
    let bytes: [UInt8]
    var bit = 0
    init(_ data: Data) { bytes = Array(data) }
    var position: Int { (bit + 7) / 8 }
    var remaining: Int { bytes.count - position }
    mutating func align() { bit = position * 8 }
    mutating func bits(_ count: Int) throws -> Int {
        guard (0...32).contains(count), bit + count <= bytes.count * 8 else {
            throw PortError.invalid("Truncated binary data at byte \(position).")
        }
        var value = 0
        for _ in 0..<count {
            value = (value << 1) | Int((bytes[bit / 8] >> (7 - bit % 8)) & 1)
            bit += 1
        }
        return value
    }
    mutating func signed(_ count: Int) throws -> Int {
        let value = try bits(count)
        return count > 0 && value & (1 << (count - 1)) != 0 ? value - (1 << count) : value
    }
    mutating func u8() throws -> Int { align(); return try bits(8) }
    mutating func u16() throws -> Int { let a = try u8(); return try a | (u8() << 8) }
    mutating func u32() throws -> Int { let a = try u16(); return try a | (u16() << 16) }
    mutating func data(_ count: Int) throws -> Data {
        align()
        guard count >= 0, count <= remaining else { throw PortError.invalid("Truncated binary payload.") }
        let start = position
        bit += count * 8
        return Data(bytes[start..<(start + count)])
    }
    mutating func string() throws -> String {
        align()
        let start = position
        while try u8() != 0 {
            guard position - start <= 4096 else { throw PortError.invalid("Oversized SWF string.") }
        }
        guard let result = String(bytes: bytes[start..<(position - 1)], encoding: .utf8) else {
            throw PortError.invalid("Invalid UTF-8 string.")
        }
        return result
    }
}
