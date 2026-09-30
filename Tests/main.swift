import Foundation
import CoreGraphics
import ImageIO

func check(_ condition: @autoclosure () -> Bool, _ message: String) throws {
    guard condition() else { throw PortError.invalid("TEST FAILED: \(message)") }
}
func rejects(_ name: String, _ action: () throws -> Void) throws {
    do { try action() } catch { print("PASS rejected \(name)"); return }
    throw PortError.invalid("TEST FAILED: accepted \(name)")
}
func little(_ number: Int, width: Int) -> Data {
    Data((0..<width).map { UInt8(truncatingIfNeeded: number >> ($0 * 8)) })
}
func archiveData(_ items: [(String, Data)]) -> Data {
    var result = little(items.count, width: 4)
    for (path, data) in items {
        result += little(path.utf8.count, width: 2); result += Data(path.utf8); result += little(data.count, width: 4)
    }
    for (_, data) in items { result += data }
    return result
}

do {
    let folder = FileManager.default.temporaryDirectory.appendingPathComponent("mewgenics-tests-" + UUID().uuidString)
    try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: folder) }
    let fixture = folder.appendingPathComponent("fixture.gpak")
    let data = archiveData([("a.gon", Data("cat { hp 10 }".utf8)), ("b.bin", Data([0, 1, 2, 255]))])
    try data.write(to: fixture)
    let archive = try GPAKArchive(url: fixture)
    try check(archive.entries.count == 2, "GPAK count")
    let second = try archive.read(archive.entries[1])
    try check(second == Data([0, 1, 2, 255]), "GPAK offset and payload")
    try rejects("oversized asset read") { _ = try archive.read(archive.entries[0], limit: 1) }
    try data.dropLast().write(to: fixture)
    try rejects("truncated GPAK") { _ = try GPAKArchive(url: fixture) }
    try archiveData([("same", Data()), ("same", Data())]).write(to: fixture)
    try rejects("duplicate paths") { _ = try GPAKArchive(url: fixture) }
    try Data([255, 255, 255, 255]).write(to: fixture)
    try rejects("unbounded entry count") { _ = try GPAKArchive(url: fixture) }
    try rejects("empty SWF") { _ = try SWFMovie(data: Data()) }
    try rejects("compressed/unimplemented SWF") { _ = try SWFMovie(data: Data("CWS".utf8)) }
    var bits = BinaryReader(Data([0b11100100]))
    let negative = try bits.signed(3), positive = try bits.bits(5)
    try check(negative == -1 && positive == 4, "SWF signed bit fields")
    var identity = BinaryReader(Data([0]))
    let matrix = try identity.matrix()
    try check(matrix == .identity, "SWF identity matrix")
    print("PASS binary/core fixtures")

    if CommandLine.arguments.count > 1 {
        let real = try GPAKArchive(url: URL(fileURLWithPath: CommandLine.arguments[1]))
        print("ARCHIVE \(real.entries.count) entries, index \(real.indexByteCount), bytes \(real.byteCount)")
        let files = CommandLine.arguments.count > 2 ? Array(CommandLine.arguments.dropFirst(2)) : ["swfs/ability_icons.swf", "swfs/catparts.swf", "swfs/tiles.swf"]
        for path in files {
            guard let entry = real.entries.first(where: { $0.path == path }) else { throw PortError.invalid("Missing \(path)") }
            let began = Date()
            let movie = try SWFMovie(data: real.read(entry, limit: 64 * 1024 * 1024))
            print("SWF \(path): \(movie.shapes.count) shapes, \(movie.sprites.count) timelines, \(movie.exports.count) symbols; \(Date().timeIntervalSince(began)) s")
            let name = movie.publicSymbols.contains("CatHead") ? "CatHead" : movie.publicSymbols.first!
            let character = movie.exports[name]!
            let context = CGContext(data: nil, width: 640, height: 640, bitsPerComponent: 8, bytesPerRow: 640 * 4,
                                    space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
            context.translateBy(x: 0, y: 640); context.scaleBy(x: 1, y: -1)
            SWFRenderer.draw(movie: movie, character: character, frame: 0, in: context, viewport: CGRect(x: 0, y: 0, width: 640, height: 640))
            guard let image = context.makeImage(), let bytes = context.data else { throw PortError.invalid("No rendered image") }
            let alpha = bytes.assumingMemoryBound(to: UInt8.self)
            let painted = (0..<(640 * 640)).filter { alpha[$0 * 4 + 3] != 0 }.count
            try check(painted > 100, "non-empty original vector render: \(name)")
            let cache = ProcessInfo.processInfo.environment["MEWGENICS_CACHE_DIR"] ?? "/Volumes/Work/caches/meowgenics-ipad"
            let output = URL(fileURLWithPath: cache).appendingPathComponent("diagnostics/" + (path as NSString).lastPathComponent + ".png")
            guard let destination = CGImageDestinationCreateWithURL(output as CFURL, "public.png" as CFString, 1, nil) else { throw PortError.invalid("Image destination failed") }
            CGImageDestinationAddImage(destination, image, nil)
            try check(CGImageDestinationFinalize(destination), "PNG output")
            print("RENDER \(name): \(painted) painted pixels; \(output.path)")
            print("LIMITS \(movie.warnings.sorted()); tags \(movie.unsupportedTags)")
        }
    }
    print("ALL CORE TESTS PASSED")
} catch {
    fputs("\(error.localizedDescription)\n", stderr)
    exit(1)
}
