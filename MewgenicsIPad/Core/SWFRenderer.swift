import CoreGraphics
import Foundation

enum SWFRenderer {
    static func bounds(movie: SWFMovie, character: Int, frame: Int, visited: Set<Int> = []) -> CGRect {
        guard !visited.contains(character), visited.count < 32 else { return .null }
        if let shape = movie.shapes[character] { return shape.bounds }
        guard let sprite = movie.sprites[character], !sprite.frames.isEmpty else { return .null }
        var visited = visited; visited.insert(character)
        let index = max(0, frame) % sprite.frames.count
        var result = CGRect.null
        for (_, object) in sprite.frames[index].objects where object.clipDepth == 0 {
            let child = bounds(movie: movie, character: object.character, frame: max(0, frame - object.bornFrame), visited: visited)
            if !child.isNull { result = result.union(child.applying(object.matrix)) }
        }
        return result
    }

    static func draw(movie: SWFMovie, character: Int, frame: Int, in context: CGContext, viewport: CGRect, fixedBounds: CGRect? = nil) {
        let bounds = fixedBounds ?? self.bounds(movie: movie, character: character, frame: frame)
        guard !bounds.isNull, bounds.width > 0, bounds.height > 0 else { return }
        context.saveGState()
        defer { context.restoreGState() }
        let scale = min(viewport.width / bounds.width, viewport.height / bounds.height) * 0.86
        context.translateBy(x: viewport.midX, y: viewport.midY)
        context.scaleBy(x: scale, y: scale)
        context.translateBy(x: -bounds.midX, y: -bounds.midY)
        var budget = 20_000
        drawNode(movie, character, frame, context, SWFColorTransform(), [], &budget)
    }

    private static func drawNode(_ movie: SWFMovie, _ character: Int, _ frame: Int, _ context: CGContext,
                                 _ color: SWFColorTransform, _ visited: Set<Int>, _ budget: inout Int) {
        guard budget > 0, !visited.contains(character), visited.count < 32 else { return }
        budget -= 1
        if let shape = movie.shapes[character] {
            for item in shape.paths {
                context.saveGState()
                context.addPath(item.path)
                if let width = item.strokeWidth {
                    context.setLineWidth(max(width, 0.05))
                    context.setLineCap(.round); context.setLineJoin(.round)
                    context.replacePathWithStrokedPath()
                }
                switch item.fill {
                case .solid(let fill):
                    context.setFillColor(fill.cgColor(color))
                    context.drawPath(using: .eoFill)
                case .gradient(let matrix, let stops, let colors, let radial):
                    context.clip(using: .evenOdd)
                    context.concatenate(matrix)
                    if let gradient = CGGradient(colorsSpace: CGColorSpaceCreateDeviceRGB(),
                                                 colors: colors.map { $0.cgColor(color) } as CFArray, locations: stops) {
                        if radial {
                            context.drawRadialGradient(gradient, startCenter: .zero, startRadius: 0,
                                                       endCenter: .zero, endRadius: 819.2,
                                                       options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
                        } else {
                            context.drawLinearGradient(gradient, start: CGPoint(x: -819.2, y: 0), end: CGPoint(x: 819.2, y: 0),
                                                       options: [.drawsBeforeStartLocation, .drawsAfterEndLocation])
                        }
                    }
                case .bitmap(let id, let matrix, let repeating):
                    context.clip(using: .evenOdd)
                    if let image = movie.bitmaps[id] {
                        context.concatenate(CGAffineTransform(a: matrix.a / 20, b: matrix.b / 20,
                                                              c: matrix.c / 20, d: matrix.d / 20, tx: matrix.tx, ty: matrix.ty))
                        context.setAlpha(min(1, max(0, color.multiply[3] + color.add[3])))
                        context.translateBy(x: 0, y: CGFloat(image.height)); context.scaleBy(x: 1, y: -1)
                        let rect = CGRect(x: 0, y: 0, width: image.width, height: image.height)
                        context.draw(image, in: rect, byTiling: repeating)
                    }
                }
                context.restoreGState()
            }
        } else if let sprite = movie.sprites[character], !sprite.frames.isEmpty {
            var visited = visited; visited.insert(character)
            let index = max(0, frame) % sprite.frames.count
            var masks: [(until: Int, path: CGPath)] = []
            for (depth, object) in sprite.frames[index].objects {
                masks.removeAll { $0.until < depth }
                if object.clipDepth > 0 {
                    let path = CGMutablePath()
                    appendMask(movie, object.character, max(0, frame - object.bornFrame), object.matrix, visited, to: path)
                    masks.append((object.clipDepth, path.copy()!))
                    continue
                }
                context.saveGState()
                for mask in masks { context.addPath(mask.path); context.clip(using: .evenOdd) }
                context.concatenate(object.matrix)
                drawNode(movie, object.character, max(0, frame - object.bornFrame), context, object.color.then(color), visited, &budget)
                context.restoreGState()
            }
        }
    }

    private static func appendMask(_ movie: SWFMovie, _ character: Int, _ frame: Int,
                                   _ transform: CGAffineTransform, _ visited: Set<Int>, to path: CGMutablePath) {
        guard !visited.contains(character), visited.count < 32 else { return }
        if let shape = movie.shapes[character] {
            for item in shape.paths where item.strokeWidth == nil { path.addPath(item.path, transform: transform) }
        } else if let sprite = movie.sprites[character], !sprite.frames.isEmpty {
            var visited = visited; visited.insert(character)
            for (_, object) in sprite.frames[max(0, frame) % sprite.frames.count].objects where object.clipDepth == 0 {
                appendMask(movie, object.character, max(0, frame - object.bornFrame), object.matrix.concatenating(transform), visited, to: path)
            }
        }
    }
}
