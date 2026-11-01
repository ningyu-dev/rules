// macOS 端侧 OCR 工具：PDF 页 -> 识别文本行（含坐标）。
//
// 用途：给扫描版规范做「定位层」——找条文所在页、页码、做全文检索。
// 不替代人工核对：OCR 会错，且不报错（本项目八次失败同型），
// 数值/表格/公式仍须对照页面图像逐条复核。
//
// 依赖：macOS 自带 PDFKit + Vision（无需安装第三方库）。
// 构建：swiftc -O -o tmp/bin/ocr_vision scripts/ocr_vision.swift
// 用法：ocr_vision <pdf> <起始页-结束页 | 单页> [dpi]  -> 每页一行 JSON
//
// 本文件与 scripts/ocr_pages.py 配套；口径见 docs/OCR读页流程.md。

import Foundation
import AppKit
import PDFKit
import Vision

struct Line: Codable { let text: String; let box: [Double] }

func renderPage(_ page: PDFPage, dpi: Double) -> CGImage? {
    let bounds = page.bounds(for: .mediaBox)
    let scale = dpi / 72.0
    let size = NSSize(width: bounds.width * scale, height: bounds.height * scale)
    let image = page.thumbnail(of: size, for: .mediaBox)
    var rect = NSRect(origin: .zero, size: image.size)
    return image.cgImage(forProposedRect: &rect, context: nil, hints: nil)
}

func ocr(_ cg: CGImage, languages: [String]) -> [Line] {
    let handler = VNImageRequestHandler(cgImage: cg, options: [:])
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = languages
    req.usesLanguageCorrection = true
    req.minimumTextHeight = 0.008
    do { try handler.perform([req]) } catch { return [] }
    guard let obs = req.results else { return [] }
    var lines: [Line] = []
    for o in obs {
        guard let c = o.topCandidates(1).first else { continue }
        let b = o.boundingBox
        lines.append(Line(text: c.string, box: [Double(b.origin.x), Double(b.origin.y), Double(b.width), Double(b.height)]))
    }
    lines.sort { a, b in
        if abs(a.box[1] - b.box[1]) > 0.02 { return a.box[1] > b.box[1] }
        return a.box[0] < b.box[0]
    }
    return lines
}

let args = CommandLine.arguments
guard args.count >= 3 else {
    FileHandle.standardError.write("usage: ocr_vision <pdf> <pages e.g. 100 or 95-100> [dpi]\n".data(using: .utf8)!)
    exit(2)
}
let path = args[1]
var pages: [Int] = []
let spec = args[2]
if spec.contains("-") {
    let p = spec.split(separator: "-").compactMap { Int($0) }
    if p.count == 2 { pages = Array(p[0]...p[1]) }
} else if let n = Int(spec) { pages = [n] }
let dpi = args.count > 3 ? (Double(args[3]) ?? 200) : 200
guard let doc = PDFDocument(url: URL(fileURLWithPath: path)) else {
    FileHandle.standardError.write("cannot open pdf\n".data(using: .utf8)!); exit(1)
}
let total = doc.pageCount
// 页范围上界夹到实际页数，避免 1-9999 这类调用为越界页输出大量 error 行
pages = pages.filter { $0 >= 1 && $0 <= total }
guard !pages.isEmpty else {
    FileHandle.standardError.write("page range out of bounds (total \(total))\n".data(using: .utf8)!); exit(1)
}
for p in pages {
    guard p >= 1 && p <= total, let page = doc.page(at: p - 1), let cg = renderPage(page, dpi: dpi) else {
        print("{\"page\": \(p), \"error\": \"bad page\"}"); continue
    }
    let lines = ocr(cg, languages: ["zh-Hans", "en-US"])
    let obj: [String: Any] = ["page": p, "width": cg.width, "height": cg.height,
                              "lines": lines.map { ["text": $0.text, "box": $0.box] }]
    let data = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
    print(String(data: data, encoding: .utf8)!)
}
