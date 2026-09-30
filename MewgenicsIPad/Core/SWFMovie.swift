import Foundation
import CoreGraphics

struct SWFColor {
    var components: [CGFloat]
    init(_ values: [CGFloat]) { components = values }
    func cgColor(_ transform: SWFColorTransform) -> CGColor {
        let c = (0..<4).map { min(1, max(0, components[$0] * transform.multiply[$0] + transform.add[$0])) }
        return CGColor(colorSpace: CGColorSpaceCreateDeviceRGB(), components: c)!
    }
}

struct SWFColorTransform {
    var multiply: [CGFloat] = [1, 1, 1, 1]
    var add: [CGFloat] = [0, 0, 0, 0]
    func then(_ parent: Self) -> Self {
        Self(multiply: (0..<4).map { multiply[$0] * parent.multiply[$0] },
             add: (0..<4).map { add[$0] * parent.multiply[$0] + parent.add[$0] })
    }
}

enum SWFFill {
    case solid(SWFColor)
    case gradient(CGAffineTransform, [CGFloat], [SWFColor], radial: Bool)
    case bitmap(Int, CGAffineTransform, repeating: Bool)
}

struct SWFDrawPath {
    let path: CGPath
    let fill: SWFFill
    let strokeWidth: CGFloat?
}

struct SWFShape {
    let bounds: CGRect
    let paths: [SWFDrawPath]
}

struct SWFPlacement {
    var character: Int
    var matrix: CGAffineTransform = .identity
    var color = SWFColorTransform()
    var name: String = ""
    var clipDepth: Int = 0
    var bornFrame: Int = 0
}

struct SWFFrame { let objects: [(depth: Int, placement: SWFPlacement)] }
struct SWFSprite {
    let frames: [SWFFrame]
    let labels: [String: Int]
}

/// A bounded, read-only subset of SWF's asset display list, not an ActionScript VM.
/// Native paths are decoded once. Immutable after init, including all CGPaths.
final class SWFMovie: @unchecked Sendable {
    private(set) var shapes: [Int: SWFShape] = [:]
    private(set) var sprites: [Int: SWFSprite] = [:]
    private(set) var bitmaps: [Int: CGImage] = [:]
    private(set) var exports: [String: Int] = [:]
    private(set) var unsupportedTags: [Int: Int] = [:]
    private(set) var warnings = Set<String>()
    private(set) var frameRate: Double = 60
    private(set) var stage: CGRect = .zero
    private var tagCount = 0
    private var edgeCount = 0
    private var frameCount = 0
    private var bitmapBytes = 0

    init(data: Data) throws {
        var reader = BinaryReader(data)
        guard try reader.data(3) == Data("FWS".utf8) else {
            throw PortError.invalid("Only uncompressed FWS assets are currently supported.")
        }
        _ = try reader.u8()
        guard try reader.u32() == data.count, data.count <= 64 * 1024 * 1024 else {
            throw PortError.invalid("Invalid or oversized SWF file.")
        }
        stage = try reader.rect()
        frameRate = Double(try reader.u16()) / 256
        let declaredFrames = try reader.u16()
        sprites[0] = try parseTimeline(&reader, expectedFrames: declaredFrames, nesting: 0)
        if exports.isEmpty { exports["Root timeline"] = 0 }
    }

    var publicSymbols: [String] {
        let result = exports.keys.filter { !$0.contains("_fla.") }.sorted()
        return result.isEmpty ? exports.keys.sorted() : result
    }

    private func parseTimeline(_ reader: inout BinaryReader, expectedFrames: Int, nesting: Int) throws -> SWFSprite {
        guard nesting < 32, expectedFrames <= 20_000 else { throw PortError.invalid("SWF timeline limit exceeded.") }
        var objects: [Int: SWFPlacement] = [:]
        var frames: [SWFFrame] = []
        var labels: [String: Int] = [:]
        while reader.remaining > 0 {
            tagCount += 1
            guard tagCount < 500_000 else { throw PortError.invalid("SWF tag limit exceeded.") }
            let header = try reader.u16()
            let tag = header >> 6
            let length = header & 63 == 63 ? try reader.u32() : header & 63
            var payload = BinaryReader(try reader.data(length))
            switch tag {
            case 0:
                guard frames.count == expectedFrames else {
                    throw PortError.invalid("SWF frame count mismatch: \(frames.count) / \(expectedFrames).")
                }
                return SWFSprite(frames: frames, labels: labels)
            case 1:
                frameCount += 1
                guard frameCount <= 100_000, objects.count <= 10_000 else { throw PortError.invalid("SWF display-list limit exceeded.") }
                frames.append(SWFFrame(objects: objects.sorted { $0.key < $1.key }.map { ($0.key, $0.value) }))
            case 2, 22, 32, 83:
                let id = try payload.u16()
                shapes[id] = try parseShape(&payload, version: [2: 1, 22: 2, 32: 3, 83: 4][tag]!)
            case 39:
                let id = try payload.u16()
                let count = try payload.u16()
                sprites[id] = try parseTimeline(&payload, expectedFrames: count, nesting: nesting + 1)
            case 36:
                try parseBitmap(&payload)
            case 26, 70:
                let flags = try payload.u8()
                let flags2 = tag == 70 ? try payload.u8() : 0
                let depth = try payload.u16()
                if flags2 & 8 != 0 || (flags2 & 16 != 0 && flags & 2 != 0) { _ = try payload.string() }
                let moved = flags & 1 != 0
                var object = moved ? (objects[depth] ?? SWFPlacement(character: 0)) : SWFPlacement(character: 0)
                if flags & 2 != 0 {
                    object.character = try payload.u16()
                    object.bornFrame = frames.count
                }
                if flags & 4 != 0 { object.matrix = try payload.matrix() }
                if flags & 8 != 0 { object.color = try payload.colorTransform() }
                if flags & 16 != 0 { _ = try payload.u16() }
                if flags & 32 != 0 { object.name = try payload.string() }
                if flags & 64 != 0 { object.clipDepth = try payload.u16() }
                if flags2 != 0 { warnings.insert("PlaceObject3 filters and blend modes are not rendered.") }
                if object.character != 0 { objects[depth] = object }
            case 28: objects.removeValue(forKey: try payload.u16())
            case 5:
                _ = try payload.u16()
                objects.removeValue(forKey: try payload.u16())
            case 43: labels[try payload.string()] = frames.count
            case 56, 76:
                let count = try payload.u16()
                for _ in 0..<count {
                    let id = try payload.u16()
                    exports[try payload.string()] = id
                }
            case 9, 69, 77, 86: break // Background and metadata are not game content.
            case 12, 59, 82:
                warnings.insert("ActionScript is not executed; game-side timeline controls are not reconstructed.")
            default: unsupportedTags[tag, default: 0] += 1
            }
        }
        throw PortError.invalid("SWF timeline has no End tag.")
    }

    private func parseFill(_ reader: inout BinaryReader, version: Int) throws -> SWFFill {
        let kind = try reader.u8()
        switch kind {
        case 0: return .solid(try reader.color(alpha: version >= 3))
        case 0x10, 0x12, 0x13:
            let matrix = try reader.matrix()
            let flags = try reader.u8()
            let count = flags & 15
            guard count > 0 else { throw PortError.invalid("Empty SWF gradient.") }
            var stops: [CGFloat] = []
            var colors: [SWFColor] = []
            for _ in 0..<count {
                stops.append(CGFloat(try reader.u8()) / 255)
                colors.append(try reader.color(alpha: version >= 3))
            }
            if kind == 0x13 { _ = try reader.u16(); warnings.insert("Focal gradients use a centered radial approximation.") }
            if flags & 0xF0 != 0 { warnings.insert("Gradient spread/interpolation uses Core Graphics defaults.") }
            return .gradient(matrix, stops, colors, radial: kind != 0x10)
        case 0x40...0x43:
            let id = try reader.u16()
            let matrix = try reader.matrix()
            return .bitmap(id, matrix, repeating: kind & 1 == 0)
        default: throw PortError.invalid("Unsupported SWF fill type \(kind).")
        }
    }

    private func parseBitmap(_ reader: inout BinaryReader) throws {
        let id = try reader.u16(), format = try reader.u8(), width = try reader.u16(), height = try reader.u16()
        guard format == 5 else { warnings.insert("Palette/16-bit bitmaps are not decoded."); return }
        let count = width * height * 4
        guard width > 0, height > 0, count <= 32 * 1024 * 1024,
              bitmapBytes + count <= 128 * 1024 * 1024 else { throw PortError.invalid("SWF bitmap memory limit exceeded.") }
        let compressed = try reader.data(reader.remaining)
        var output = [UInt8](repeating: 0, count: count)
        var size = uLongf(count)
        let status = compressed.withUnsafeBytes { source in
            output.withUnsafeMutableBufferPointer { destination in
                uncompress(destination.baseAddress, &size, source.bindMemory(to: Bytef.self).baseAddress, uLong(compressed.count))
            }
        }
        guard status == Z_OK, size == count else { throw PortError.invalid("Invalid SWF bitmap compression.") }
        // DefineBitsLossless2 format 5 stores premultiplied ARGB; Core Graphics receives RGBA.
        for pixel in stride(from: 0, to: count, by: 4) {
            let alpha = output[pixel]
            output[pixel] = output[pixel + 1]; output[pixel + 1] = output[pixel + 2]
            output[pixel + 2] = output[pixel + 3]; output[pixel + 3] = alpha
        }
        guard let provider = CGDataProvider(data: Data(output) as CFData),
              let image = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32, bytesPerRow: width * 4,
                                  space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.premultipliedLast.rawValue),
                                  provider: provider, decode: nil, shouldInterpolate: true, intent: .defaultIntent) else {
            throw PortError.invalid("Could not create SWF bitmap.")
        }
        bitmapBytes += count; bitmaps[id] = image
    }

    private func styles(_ reader: inout BinaryReader, version: Int) throws -> ([SWFFill], [(CGFloat, SWFFill)]) {
        let shortFills = try reader.u8()
        let fillCount = shortFills == 255 && version >= 2 ? try reader.u16() : shortFills
        var fills: [SWFFill] = []
        for _ in 0..<fillCount { fills.append(try parseFill(&reader, version: version)) }
        let shortLines = try reader.u8()
        let lineCount = shortLines == 255 && version >= 2 ? try reader.u16() : shortLines
        var lines: [(CGFloat, SWFFill)] = []
        for _ in 0..<lineCount {
            let width = CGFloat(try reader.u16()) / 20
            var hasFill = false
            if version == 4 {
                let cap = try reader.bits(2)
                let join = try reader.bits(2)
                hasFill = try reader.bits(1) != 0
                let scaling = try reader.bits(3)
                _ = try reader.bits(5)
                let noClose = try reader.bits(1)
                let endCap = try reader.bits(2)
                if join == 2 { _ = try reader.u16() }
                if cap != 0 || join != 0 || scaling != 0 || noClose != 0 || endCap != 0 {
                    warnings.insert("Advanced stroke styles are approximated with round joins/caps.")
                }
            }
            let fill = hasFill ? try parseFill(&reader, version: version) : .solid(try reader.color(alpha: version >= 3))
            lines.append((width, fill))
        }
        return (fills, lines)
    }

    private func parseShape(_ reader: inout BinaryReader, version: Int) throws -> SWFShape {
        let bounds = try reader.rect()
        if version == 4 { _ = try reader.rect(); _ = try reader.u8() }
        var (fills, lines) = try styles(&reader, version: version)
        var fillBits = try reader.bits(4)
        var lineBits = try reader.bits(4)
        var fillBase = 0, lineBase = 0
        var fill0 = 0, fill1 = 0, line = 0
        var current = SWFPoint(x: 0, y: 0)
        var fillEdges: [Int: [SWFEdge]] = [:]
        var lineEdges: [Int: [SWFEdge]] = [:]
        while true {
            if try reader.bits(1) == 0 {
                let flags = try reader.bits(5)
                if flags == 0 { break }
                if flags & 1 != 0 {
                    let count = try reader.bits(5)
                    current = try SWFPoint(x: reader.signed(count), y: reader.signed(count))
                }
                if flags & 2 != 0 { let value = try reader.bits(fillBits); fill0 = value == 0 ? 0 : fillBase + value }
                if flags & 4 != 0 { let value = try reader.bits(fillBits); fill1 = value == 0 ? 0 : fillBase + value }
                if flags & 8 != 0 { let value = try reader.bits(lineBits); line = value == 0 ? 0 : lineBase + value }
                if flags & 16 != 0 {
                    reader.align()
                    fillBase = fills.count; lineBase = lines.count
                    let added = try styles(&reader, version: version)
                    fills.append(contentsOf: added.0); lines.append(contentsOf: added.1)
                    fillBits = try reader.bits(4); lineBits = try reader.bits(4)
                }
                continue
            }
            edgeCount += 1
            guard edgeCount <= 2_000_000 else { throw PortError.invalid("SWF edge limit exceeded.") }
            let straight = try reader.bits(1) != 0
            let count = try reader.bits(4) + 2
            var control: SWFPoint?
            var end = current
            if straight {
                if try reader.bits(1) != 0 {
                    end.x += try reader.signed(count); end.y += try reader.signed(count)
                } else if try reader.bits(1) != 0 { end.y += try reader.signed(count) }
                else { end.x += try reader.signed(count) }
            } else {
                let c = try SWFPoint(x: current.x + reader.signed(count), y: current.y + reader.signed(count))
                control = c
                end = try SWFPoint(x: c.x + reader.signed(count), y: c.y + reader.signed(count))
            }
            let edge = SWFEdge(start: current, control: control, end: end)
            guard fill0 <= fills.count, fill1 <= fills.count, line <= lines.count else { throw PortError.invalid("Invalid SWF style index.") }
            if fill0 > 0 { fillEdges[fill0, default: []].append(edge.reversed) }
            if fill1 > 0 { fillEdges[fill1, default: []].append(edge) }
            if line > 0 { lineEdges[line, default: []].append(edge) }
            current = end
        }
        let paths = fillEdges.keys.sorted().map { index in
            SWFDrawPath(path: SWFEdge.path(fillEdges[index]!, close: true), fill: fills[index - 1], strokeWidth: nil)
        } + lineEdges.keys.sorted().map { index in
            SWFDrawPath(path: SWFEdge.path(lineEdges[index]!, close: false), fill: lines[index - 1].1, strokeWidth: lines[index - 1].0)
        }
        return SWFShape(bounds: bounds, paths: paths)
    }
}

private struct SWFPoint: Hashable {
    var x: Int
    var y: Int
    var cg: CGPoint { CGPoint(x: CGFloat(x) / 20, y: CGFloat(y) / 20) }
}

private struct SWFEdge {
    let start: SWFPoint
    let control: SWFPoint?
    let end: SWFPoint
    var reversed: Self { Self(start: end, control: control, end: start) }
    static func path(_ edges: [Self], close: Bool) -> CGPath {
        let path = CGMutablePath()
        var outgoing: [SWFPoint: [Int]] = [:]
        for (i, edge) in edges.enumerated() { outgoing[edge.start, default: []].append(i) }
        var used = Set<Int>()
        for seed in edges.indices where !used.contains(seed) {
            var i = seed
            let origin = edges[i].start
            path.move(to: origin.cg)
            while !used.contains(i) {
                used.insert(i)
                let edge = edges[i]
                if let control = edge.control { path.addQuadCurve(to: edge.end.cg, control: control.cg) }
                else { path.addLine(to: edge.end.cg) }
                if edge.end == origin { if close { path.closeSubpath() }; break }
                while let candidate = outgoing[edge.end]?.last, used.contains(candidate) { outgoing[edge.end]?.removeLast() }
                guard let next = outgoing[edge.end]?.popLast() else { break }
                i = next
            }
        }
        return path.copy()!
    }
}

extension BinaryReader {
    mutating func rect() throws -> CGRect {
        align()
        let n = try bits(5)
        let x0 = try signed(n), x1 = try signed(n), y0 = try signed(n), y1 = try signed(n)
        align()
        guard x1 >= x0, y1 >= y0 else { throw PortError.invalid("Invalid SWF bounds.") }
        return CGRect(x: CGFloat(x0) / 20, y: CGFloat(y0) / 20, width: CGFloat(x1 - x0) / 20, height: CGFloat(y1 - y0) / 20)
    }
    mutating func matrix() throws -> CGAffineTransform {
        align()
        var a: CGFloat = 1, d: CGFloat = 1, b: CGFloat = 0, c: CGFloat = 0
        if try bits(1) != 0 { let n = try bits(5); a = CGFloat(try signed(n)) / 65536; d = CGFloat(try signed(n)) / 65536 }
        if try bits(1) != 0 { let n = try bits(5); b = CGFloat(try signed(n)) / 65536; c = CGFloat(try signed(n)) / 65536 }
        let n = try bits(5)
        let x = try signed(n), y = try signed(n)
        align()
        return CGAffineTransform(a: a, b: b, c: c, d: d, tx: CGFloat(x) / 20, ty: CGFloat(y) / 20)
    }
    mutating func color(alpha: Bool) throws -> SWFColor {
        let r = try u8(), g = try u8(), b = try u8(), a = alpha ? try u8() : 255
        return SWFColor([r, g, b, a].map { CGFloat($0) / 255 })
    }
    mutating func colorTransform() throws -> SWFColorTransform {
        align()
        let hasAdd = try bits(1) != 0, hasMultiply = try bits(1) != 0, n = try bits(4)
        var result = SWFColorTransform()
        if hasMultiply { for i in 0..<4 { result.multiply[i] = CGFloat(try signed(n)) / 256 } }
        if hasAdd { for i in 0..<4 { result.add[i] = CGFloat(try signed(n)) / 255 } }
        align()
        return result
    }
}
