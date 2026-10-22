#!/usr/bin/env python3
"""按登记表把公告原文归档到 archive/<标准>/announcement.html。

为什么只归档公告、不归档 PDF 正文：
  - 公告是**判据的唯一来源**（整部废止 / 强条废止 / 实施日期 / 强条清单），
    而且体积小（十几 KB），可以进 git、可以机械比对。
  - 规范正文 PDF 动辄几十 MB，放工作区、由 .gitignore 忽略，靠 SHA256 保证可信。

本脚本只写 announcement.html 与 announcement.sha256；SOURCE.md 由
scripts/write_source_md.py 生成（需要人工补来源类型等判断）。

用法：
    python scripts/archive_announcements.py            # 只报告
    python scripts/archive_announcements.py --apply    # 下载并写入
    python scripts/archive_announcements.py --apply --only GB50015-2019
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "standards.json"
ARCHIVE = ROOT / "archive"

UA = "Mozilla/5.0 (compatible; ningyu-rules-archiver/0.1)"


def fetch(url: str, timeout: int = 30) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def main() -> int:
    apply_mode = "--apply" in sys.argv
    only = None
    if "--only" in sys.argv:
        try:
            only = sys.argv[sys.argv.index("--only") + 1]
        except IndexError:
            print("--only 需要一个标准 id")
            return 2

    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    targets = [s for s in data["standards"] if s.get("evidence")]
    if only:
        targets = [s for s in targets if s["id"] == only]

    if not targets:
        print("没有可归档的对象：登记表里没有带 evidence 的标准。")
        print("先跑 scripts/apply_source_check.py 写入 evidence，再归档。")
        return 2

    print("=" * 64)
    print("公告原文归档" + ("（已写入）" if apply_mode else "（仅报告）"))
    print("=" * 64)

    ok, skipped, failed = 0, 0, []
    for s in targets:
        sid, url = s["id"], s["evidence"]
        folder = ARCHIVE / sid
        html_path = folder / "announcement.html"
        sha_path = folder / "announcement.sha256"

        if html_path.exists():
            skipped += 1
            print(f"  跳过（已存在）{sid}")
            continue

        if not apply_mode:
            print(f"  待下载 {sid:16s} {url}")
            continue

        try:
            body = fetch(url)
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            failed.append((sid, type(e).__name__))
            print(f"  失败 {sid}: {type(e).__name__}")
            continue

        if b"<html" not in body[:2000].lower() and b"<!doctype" not in body[:2000].lower():
            failed.append((sid, "返回内容不是 HTML"))
            print(f"  失败 {sid}: 返回内容不是 HTML")
            continue

        folder.mkdir(parents=True, exist_ok=True)
        html_path.write_bytes(body)
        digest = hashlib.sha256(body).hexdigest()
        sha_path.write_text(f"{digest}  announcement.html\n", encoding="utf-8")
        ok += 1
        print(f"  归档 {sid:16s} {len(body):>7d} B  {digest[:16]}…")

    print("-" * 64)
    print(f"新归档 {ok} / 跳过 {skipped} / 失败 {len(failed)}")
    print("口径：按标准计；已存在的不覆盖——公告页若改版，重下会改变哈希，")
    print("      需要显式删除旧文件再跑，避免把「页面改版」误记成「公告变了」。")

    if failed:
        for sid, why in failed:
            print(f"  {sid}: {why}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
