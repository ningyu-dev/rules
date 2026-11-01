#!/usr/bin/env python3
"""扫描版 PDF 的 OCR 定位工具（macOS Vision，端侧，无第三方依赖）。

给「找条文在哪一页 / 页码回填 / 全文检索」用；**不是**核对工具：
OCR 会错且不报错，数值、表格、公式仍须对照页面图像逐条复核
（口径见 docs/OCR读页流程.md；D-010 同理——校验/识别手段本身必须被验证）。

用法:
    python3 scripts/ocr_pages.py <pdf> <输出目录> [页范围] [dpi]
    # 例：python3 scripts/ocr_pages.py archive/GB55020-2021/GB55020-2021.pdf tmp/ocr/text/GB55020-2021 1-28

产出:
    <输出目录>/pages.jsonl   每页一行 JSON（page/lines[{text,box}]）
    <输出目录>/page_NNN.txt 每页纯文本（自上而下顺序）

依赖: macOS 自带 swiftc / PDFKit / Vision；首次运行会把 scripts/ocr_vision.swift
编译到 tmp/bin/ocr_vision（tmp/ 已 gitignore）。
"""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / "scripts" / "ocr_vision.swift"
BIN = ROOT / "tmp" / "bin" / "ocr_vision"


def ensure_bin() -> pathlib.Path:
    if not BIN.exists() or BIN.stat().st_mtime < SRC.stat().st_mtime:
        BIN.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["swiftc", "-O", "-o", str(BIN), str(SRC)], check=True)
    return BIN


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    pdf = pathlib.Path(sys.argv[1])
    outdir = pathlib.Path(sys.argv[2])
    spec = sys.argv[3] if len(sys.argv) > 3 else "1-9999"
    dpi = sys.argv[4] if len(sys.argv) > 4 else "220"
    outdir.mkdir(parents=True, exist_ok=True)
    bin_path = ensure_bin()
    t0 = time.time()
    proc = subprocess.run([str(bin_path), str(pdf), spec, dpi], capture_output=True, text=True)
    elapsed = time.time() - t0
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    (outdir / "pages.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
    n = 0
    for line in lines:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if "error" in d:
            continue
        n += 1
        (outdir / f"page_{d['page']:03d}.txt").write_text(
            "\n".join(x["text"] for x in d["lines"]) + "\n", encoding="utf-8")
    print(f"OK {pdf} -> {outdir}: {n} 页, {elapsed:.1f}s, stderr={proc.stderr[:200]}")
    return 0 if n else 1


if __name__ == "__main__":
    raise SystemExit(main())
