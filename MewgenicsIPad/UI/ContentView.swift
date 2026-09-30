import SwiftUI
import UniformTypeIdentifiers
import ImageIO

struct ContentView: View {
    @StateObject private var model = ArchiveModel()
    @State private var importing = false
    @State private var query = ""
    @State private var category = "swf"
    @State private var selected: GPAKEntry?
    private let categories = [("swf", "Animation"), ("gon", "Data"), ("lvl", "Levels"), ("png", "Textures"), ("", "All")]

    private var entries: [GPAKEntry] {
        (model.archive?.entries ?? []).filter {
            (category.isEmpty || $0.fileExtension == category) && (query.isEmpty || $0.path.localizedCaseInsensitiveContains(query))
        }
    }

    var body: some View {
        NavigationSplitView {
            VStack(spacing: 0) {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Native port · Asset runtime").font(.headline)
                    Text("Original assets render natively. Gameplay reconstruction is in progress.")
                        .font(.caption).foregroundStyle(.secondary)
                    if let archive = model.archive {
                        Text("\(archive.entries.count.formatted()) assets · \(ByteCountFormatter.string(fromByteCount: Int64(archive.byteCount), countStyle: .file))")
                            .font(.caption.monospacedDigit())
                    }
                    Picker("Asset type", selection: $category) {
                        ForEach(categories, id: \.0) { value, title in Text(title).tag(value) }
                    }.pickerStyle(.menu)
                }.padding().frame(maxWidth: .infinity, alignment: .leading)
                List(entries, selection: $selected) { entry in
                    VStack(alignment: .leading, spacing: 4) {
                        Text((entry.path as NSString).lastPathComponent).font(.body)
                        Text(entry.path).font(.caption2).foregroundStyle(.secondary).lineLimit(1)
                    }.tag(entry)
                }
                .searchable(text: $query, prompt: "Search original assets")
            }
            .navigationTitle("Mewgenics")
            .toolbar {
                Button { importing = true } label: { Label("Open archive", systemImage: "folder") }
                    .accessibilityIdentifier("openArchive").disabled(model.isLoading)
            }
            .overlay { if model.isLoading { ProgressView("Reading archive index…").padding().background(.regularMaterial, in: RoundedRectangle(cornerRadius: 12)) } }
        } detail: {
            if let selected, let archive = model.archive {
                AssetDetail(archive: archive, entry: selected).id(selected.id + archive.url.absoluteString)
            } else {
                ContentUnavailableView {
                    Label("Mewgenics on iPad", systemImage: "pawprint")
                } description: {
                    Text("Open resources.gpak to render the original vector art and inspect game data. This build does not yet run combat, breeding, or saves.")
                } actions: {
                    Button("Open resources.gpak") { importing = true }.buttonStyle(.borderedProminent)
                }
            }
        }
        .fileImporter(isPresented: $importing, allowedContentTypes: [.data], allowsMultipleSelection: false) { result in
            switch result {
            case .success(let urls): if let url = urls.first { selected = nil; Task { await model.open(url) } }
            case .failure(let error): model.error = error.localizedDescription
            }
        }
        .alert("Couldn’t open archive", isPresented: Binding(get: { model.error != nil }, set: { if !$0 { model.error = nil } })) {
            Button("OK") { model.error = nil }
        } message: { Text(model.error ?? "") }
        .task {
            await model.openLaunchArgument()
            #if targetEnvironment(simulator)
            let arguments = ProcessInfo.processInfo.arguments
            if let index = arguments.firstIndex(of: "--asset"), index + 1 < arguments.count {
                selected = model.archive?.entries.first { $0.path == arguments[index + 1] }
            }
            #endif
        }
    }
}

private struct AssetDetail: View {
    let archive: GPAKArchive
    let entry: GPAKEntry
    @State private var movie: SWFMovie?
    @State private var text: String?
    @State private var image: UIImage?
    @State private var error: String?
    @State private var loaded = false

    var body: some View {
        Group {
            if let movie { MovieView(movie: movie) }
            else if let image { Image(uiImage: image).resizable().scaledToFit().padding() }
            else if let text {
                ScrollView([.vertical, .horizontal]) { Text(text).font(.system(.caption, design: .monospaced)).textSelection(.enabled).padding() }
            } else if let error { ContentUnavailableView("Asset not rendered", systemImage: "doc.questionmark", description: Text(error)) }
            else if !loaded { ProgressView("Decoding original asset…") }
            else { ContentUnavailableView("Decoder pending", systemImage: "hammer", description: Text("\(entry.fileExtension.uppercased()) runtime support has not been implemented yet.")) }
        }
        .navigationTitle((entry.path as NSString).lastPathComponent)
        .navigationBarTitleDisplayMode(.inline)
        .task {
            do {
                if entry.fileExtension == "swf" {
                    let result = try await Task.detached(priority: .userInitiated) { try SWFMovie(data: archive.read(entry)) }.value
                    guard !Task.isCancelled else { return }; movie = result
                } else if ["gon", "txt", "ini", "csv", "shader"].contains(entry.fileExtension) {
                    let data = try await Task.detached { try archive.prefix(entry, count: min(entry.size, 512 * 1024)) }.value
                    guard !Task.isCancelled else { return }
                    text = String(decoding: data, as: UTF8.self) + (entry.size > data.count ? "\n\n[Preview truncated at 512 KiB]" : "")
                } else if entry.fileExtension == "png" {
                    let data = try await Task.detached { try archive.read(entry) }.value
                    guard !Task.isCancelled else { return }
                    if let source = CGImageSourceCreateWithData(data as CFData, nil),
                       let thumbnail = CGImageSourceCreateThumbnailAtIndex(source, 0, [kCGImageSourceCreateThumbnailFromImageAlways: true, kCGImageSourceThumbnailMaxPixelSize: 2048] as CFDictionary) {
                        image = UIImage(cgImage: thumbnail)
                    } else { throw PortError.invalid("Invalid PNG texture.") }
                }
            } catch { if !Task.isCancelled { self.error = error.localizedDescription } }
            loaded = true
        }
    }
}

private struct MovieView: View {
    let movie: SWFMovie
    @State private var symbol = ""
    @State private var frame = 0.0
    @State private var playing = false
    @State private var start = Date()
    @State private var showLimitations = false
    private var character: Int { movie.exports[symbol] ?? 0 }
    private var count: Int { max(1, movie.sprites[character]?.frames.count ?? 1) }

    var body: some View {
        VStack(spacing: 12) {
            HStack {
                Picker("Symbol", selection: $symbol) {
                    ForEach(movie.publicSymbols, id: \.self) { Text($0).tag($0) }
                }.accessibilityIdentifier("symbolPicker")
                Spacer()
                Text("\(movie.shapes.count) vector shapes").font(.caption).foregroundStyle(.secondary)
            }.padding(.horizontal)
            TimelineView(.animation(minimumInterval: 1 / 30, paused: !playing)) { timeline in
                let elapsed = playing ? Int(timeline.date.timeIntervalSince(start) * movie.frameRate) : 0
                NativeVectorView(movie: movie, character: character, frame: Int(frame) + elapsed)
                    .background(Color(red: 0.88, green: 0.85, blue: 0.79))
            }.accessibilityIdentifier("nativeVectorPreview")
            HStack {
                Button {
                    if playing {
                        frame = Double((Int(frame) + Int(Date().timeIntervalSince(start) * movie.frameRate)) % count)
                        playing = false
                    } else { start = Date(); playing = true }
                } label: { Image(systemName: playing ? "pause.fill" : "play.fill") }
                    .accessibilityLabel(playing ? "Pause animation" : "Play animation")
                Slider(value: $frame, in: 0...Double(max(1, count - 1)), step: 1).disabled(playing || count <= 1)
                    .accessibilityIdentifier("animationFrame")
                Text("\(Int(frame) + 1) / \(count)").monospacedDigit().font(.caption)
            }.padding(.horizontal)
            HStack {
                Text("Native vector reconstruction").font(.caption).foregroundStyle(.secondary)
                Spacer()
                Button("Rendering limits") { showLimitations = true }.font(.caption)
            }.padding([.horizontal, .bottom])
        }
        .onAppear {
            symbol = movie.publicSymbols.contains("CatHead") ? "CatHead" : (movie.publicSymbols.first ?? "")
        }
        .onChange(of: symbol) { _, _ in frame = 0; playing = false }
        .sheet(isPresented: $showLimitations) {
            NavigationStack {
                List {
                    Text("This is an original-asset renderer. Game logic, Flash scripts, text/fonts, imported symbols, nested masks, morphing, and bitmap color tinting are not implemented. Some art will be incomplete.")
                    ForEach(movie.warnings.sorted(), id: \.self) { Text($0) }
                    if !movie.unsupportedTags.isEmpty {
                        Text("Unimplemented tag types: " + movie.unsupportedTags.keys.sorted().map(String.init).joined(separator: ", "))
                    }
                }.navigationTitle("Rendering limits").toolbar { Button("Done") { showLimitations = false } }
            }
        }
    }
}

private struct NativeVectorView: UIViewRepresentable {
    let movie: SWFMovie
    let character: Int
    let frame: Int
    func makeUIView(context: Context) -> VectorUIView { VectorUIView() }
    func updateUIView(_ uiView: VectorUIView, context: Context) {
        uiView.movie = movie; uiView.character = character; uiView.frameIndex = frame; uiView.setNeedsDisplay()
    }
}

private final class VectorUIView: UIView {
    var movie: SWFMovie?
    var character = 0
    var frameIndex = 0
    override init(frame: CGRect) { super.init(frame: frame); isOpaque = false; contentMode = .redraw }
    required init?(coder: NSCoder) { fatalError("init(coder:) is not used") }
    override func draw(_ rect: CGRect) {
        guard let movie, let context = UIGraphicsGetCurrentContext() else { return }
        SWFRenderer.draw(movie: movie, character: character, frame: frameIndex, in: context, viewport: bounds)
    }
}
