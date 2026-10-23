#!/usr/bin/env python3
"""把规范正文 PDF 归档到 archive/<标准>/，由 .gitignore 排除。

为什么这么放：PDF 动辄几十 MB，全入库会让每次 clone 变重；但核对又必须
读原文。所以正文放工作区、公告与哈希进 git —— 文件可信由哈希保证，
不由二进制入库保证（D-006）。

**来源类型必须标清，这是本脚本存在的主要理由。**

    官方   住建部门户网站发布件，或正式出版文本
    转载   地方政府网站等转载的同一份文本

转载件可以读、可以定位、可以交叉比对，但**不得作为条文出处**——
直到拿到官方渠道件或正式出版文本为止。把转载件当官方件记，等于
把「来源未经真实性验证却声称已核对」重演一遍（第 4 轮失败）。

用法：
    # 下载并归档（会写 SHA256.txt 与 SOURCE.md）
    python scripts/archive_pdf.py GB50345-2012 <PDF_URL> --type 转载 --publisher "济南市住建局网站"

    # 只校验已有文件与 SHA256.txt 是否一致
    python scripts/archive_pdf.py GB50345-2012 --check

    # 已有人工下载的文件，只补哈希与 SOURCE.md
    python scripts/archive_pdf.py GB50345-2012 --from-local ~/Downloads/xxx.pdf --type 官方
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import date

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "standards.json"
ARCHIVE = ROOT / "archive"
UA = "Mozilla/5.0 (compatible; ningyu-rules-archiver/0.1)"
VALID_TYPES = ("官方", "转载")


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def registry_entry(sid: str) -> dict:
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    for s in data["standards"]:
        if s["id"] == sid:
            return s
    raise SystemExit(f"登记表里没有 {sid}，先登记再归档")


def page_count(path: pathlib.Path) -> int | None:
    """取 PDF 页数。macOS 用 mdls；其他平台返回 None（不猜）。

    页数不是装饰：本轮就靠它发现一份「转载件只有 32 页、而全文 81 页」，
    差点把节选当全文归档。
    """
    try:
        out = subprocess.run(
            ["mdls", "-name", "kMDItemNumberOfPages", str(path)],
            capture_output=True, text=True, timeout=10,
        ).stdout
        m = re.search(r"=\s*(\d+)", out)
        return int(m.group(1)) if m else None
    except (OSError, subprocess.SubprocessError):
        return None


def write_stub_md(folder: pathlib.Path, sid: str, entry: dict, *,
                  note: str = "", by: str | None = None,
                  at: str | None = None) -> pathlib.Path:
    """正文尚未归档时写「来源记录」。

    只记从哪取、怎么取、取到后怎么验，**不记本地有没有**。
    PDF 不进 git，本地有无是每台机器各自的运行时状态：写进版本库必然
    过期，还会让下一个人把「文档说没有」当成结论。本地状态由
    audit_archive.py 在运行时判断。
    """
    path = folder / "SOURCE.md"
    lines = [
        f"# {entry['standard']} {entry['name']} · 原文归档",
        "",
        "> 本目录的 PDF **不进 git**（见仓库根 `.gitignore`），只留在本地。",
        "> 本文件只记出处与获取方式，**不记本地是否已下载**——PDF 是否在手是每台机器",
        "> 各自的运行时状态，写进版本库必然过期。本地有没有，跑 `audit_archive.py` 看。",
        "",
        "## 来源",
        "",
        "| 项 | 内容 |",
        "|---|---|",
        f"| 标准号 | {entry['standard']} |",
        f"| 名称 | {entry['name']} |",
        f"| 公告号 | {entry.get('announcement_no') or '未取到'} |",
        f"| 实施日期 | {entry.get('implemented') or '未取到'} |",
        "| 来源类型 | 官方（住房和城乡建设部） |",
        f"| 公告页 | {entry.get('evidence') or '未记录'} |",
        "| 公告原文 | `announcement.html`（哈希见 `announcement.sha256`） |",
        "| 正文获取 | 公告页「附件下载」→ 规范全文（附件由 JS 动态加载，需浏览器打开） |",
        "",
        "## 获取方式",
        "",
        "```bash",
        f"python scripts/archive_pdf.py {sid} <PDF 直链> --type 官方 \\",
        f"    --source-page {entry.get('evidence') or '<公告页 URL>'}",
        "```",
        "",
        "已有人工下载的文件时用 `--from-local`。归档后脚本会写 `SHA256.txt`，",
        "并把哈希与大小补进本文件。",
        "",
        "## 用途边界",
        "",
        "公告原文可支撑：现行性、实施日期、废止措辞形态、强条清单。",
        "**不足以**支撑：逐条核对条文数值——那需要全文。",
    ]
    if note:
        lines += ["", "## 备注", "", note]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def write_source_md(folder: pathlib.Path, sid: str, entry: dict, *,
                    pdf_url: str | None, source_type: str, publisher: str,
                    size: int, digest: str, pages: int | None,
                    expected_pages: int | None,
                    source_page: str | None = None,
                    method: str = "脚本 archive_pdf.py",
                    downloaded_at: str | None = None,
                    downloaded_by: str | None = None,
                    note: str = "") -> pathlib.Path:
    path = folder / "SOURCE.md"
    if pages is None:
        integrity = "未核（无 PDF 工具，页数未知）"
    elif expected_pages and pages < expected_pages:
        integrity = f"**不完整：{pages} 页，全文应为 {expected_pages} 页**"
    elif expected_pages:
        integrity = f"页数与全文一致（{pages} 页）"
    else:
        integrity = f"{pages} 页（未与官方篇幅比对）"
    lines = [
        f"# {entry['standard']} {entry['name']} · 原文归档",
        "",
        "> 本目录的 PDF **不进 git**（见仓库根 `.gitignore`）。",
        "> 任何人按下列 URL 下载、用 `SHA256.txt` 比对，即可确认拿到的是同一份。",
        "> **下载来源必须记全**：只有直链而不知从哪个页面下的，等于无法复核。",
        "",
        "## 下载记录",
        "",
        "| 项 | 内容 |",
        "|---|---|",
        f"| 下载时间 | {downloaded_at or '未记录'} |",
        f"| 下载人 | {downloaded_by or '未记录'} |",
        f"| 下载方式 | {method} |",
        f"| **来源页面** | {source_page or '**未记录**（只知直链，无法复核下载入口）'} |",
        f"| PDF 直链 | {pdf_url or '未记录'} |",
        "",
        "## 文件",
        "",
        "| 项 | 内容 |",
        "|---|---|",
        f"| 标准号 | {entry['standard']} |",
        f"| 名称 | {entry['name']} |",
        f"| 公告号 | {entry.get('announcement_no') or '未取到'} |",
        f"| 实施日期 | {entry.get('implemented') or '未取到'} |",
        f"| 公告页 | {entry.get('evidence') or '未记录'} |",
        f"| **来源类型** | **{source_type}**{'（' + publisher + '）' if publisher else ''} |",
        f"| 文件 | `{sid}.pdf` |",
        f"| 大小 | {size:,} B |",
        f"| **完整性** | {integrity} |",
        f"| SHA-256 | `{digest}` |",
        "",
        "## 用途边界",
        "",
    ]
    # 页数未知时不写「完整性」行：那是本次运行的工具限制，不是文件属性，
    # 留在出处记录里会被误读成「这份文件有问题」。
    if pages is None:
        lines = [l for l in lines if not l.startswith("| **完整性** |")]
    if source_type == "官方":
        lines += [
            "官方发布件或正式出版文本。可作为条文出处。",
            "",
            "仍需注意：本文件只证明「拿到的是这一份」，**不证明条文数值已被核对**。",
            "录入规则库时 `provenance.page` 必须逐条填真实页码，`verified_by` 必须有值。",
        ]
    else:
        lines += [
            "**转载件，不得作为条文出处。**",
            "",
            "可用于：定位条文、交叉比对、判断某条是否存在。",
            "不可用于：作为 `provenance` 的最终依据、据此把条目判为已核对。",
            "",
            "要转为可用，需取得住建部门户网站发布件或正式出版文本，重新归档并把",
            "本字段改为「官方」。",
        ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    sid = sys.argv[1]

    check = "--check" in sys.argv
    stub = "--stub" in sys.argv
    from_local = None
    if "--from-local" in sys.argv:
        from_local = pathlib.Path(sys.argv[sys.argv.index("--from-local") + 1]).expanduser()

    def opt(name: str, default: str = "") -> str:
        return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default

    source_page = opt("--source-page", "")
    by = opt("--by", "沈澄 给排水工程师")
    note = opt("--note", "")
    downloaded_at = opt("--at", date.today().isoformat())

    pdf_url = None
    if not check and not from_local and not stub:
        # 第一个非选项参数即 URL（跳过各选项的取值）
        value_opts = ("--type", "--publisher", "--from-local", "--source-page",
                      "--by", "--note", "--at", "--expected-pages")
        for i, a in enumerate(sys.argv[2:], start=2):
            if a.startswith("--"):
                continue
            if sys.argv[i - 1] in value_opts:
                continue
            pdf_url = a
            break
        if not pdf_url:
            print("缺少 PDF URL。或用 --from-local / --stub / --check。")
            return 2

    source_type = "转载"
    if "--type" in sys.argv:
        source_type = sys.argv[sys.argv.index("--type") + 1]
    if source_type not in VALID_TYPES:
        print(f"--type 只能是 {VALID_TYPES}")
        return 2
    publisher = ""
    if "--publisher" in sys.argv:
        publisher = sys.argv[sys.argv.index("--publisher") + 1]

    entry = registry_entry(sid)
    folder = ARCHIVE / sid
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / f"{sid}.pdf"
    sha_path = folder / "SHA256.txt"

    print("=" * 64)
    print(f"{sid} · {entry['name']}")
    print("=" * 64)

    if stub:
        src = write_stub_md(folder, sid, entry, note=note, by=by, at=downloaded_at)
        print("  写入未取得记录：" + str(src.relative_to(ROOT)))
        print("  该标准正文尚未归档。补法见 SOURCE.md「怎么补」一节。")
        return 0

    if check:
        if not pdf_path.exists():
            print(f"  [缺] {pdf_path.name} 不在本地。按 SOURCE.md 的 URL 下载后再校验。")
            return 1
        digest = sha256_of(pdf_path)
        if not sha_path.exists():
            print(f"  [缺] 没有 SHA256.txt，无法校验。当前文件哈希：{digest}")
            return 1
        recorded = sha_path.read_text(encoding="utf-8").split()[0]
        ok = recorded == digest
        print(f"  文件：{pdf_path.name}  {pdf_path.stat().st_size:,} B")
        print(f"  记录：{recorded}")
        print(f"  实算：{digest}")
        print("  结论：" + ("一致" if ok else "**不一致** —— 不是同一份文件，不得采信"))
        return 0 if ok else 1

    if from_local:
        if not from_local.exists():
            print(f"  文件不存在：{from_local}")
            return 2
        shutil.copy2(from_local, pdf_path)
        print(f"  复制 {from_local.name} → {pdf_path.relative_to(ROOT)}")
    else:
        print(f"  下载 {pdf_url}")
        try:
            req = urllib.request.Request(pdf_url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = resp.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  失败：{type(e).__name__} {e}")
            print("  若是住建部门户网站：附件由 JS 动态加载，静态页面拿不到直链，")
            print("  需人工在浏览器下载后用 --from-local 归档。")
            return 1
        if not body.startswith(b"%PDF"):
            print("  失败：返回内容不是 PDF")
            return 1
        pdf_path.write_bytes(body)

    size = pdf_path.stat().st_size
    digest = sha256_of(pdf_path)
    sha_path.write_text(f"{digest}  {pdf_path.name}\n", encoding="utf-8")
    pages = page_count(pdf_path)
    expected = None
    if "--expected-pages" in sys.argv:
        try:
            expected = int(sys.argv[sys.argv.index("--expected-pages") + 1])
        except (IndexError, ValueError):
            print("--expected-pages 需要一个整数")
            return 2
    src = write_source_md(folder, sid, entry, pdf_url=pdf_url,
                          source_type=source_type, publisher=publisher,
                          size=size, digest=digest, pages=pages,
                          expected_pages=expected,
                          source_page=source_page,
                          method=("人工浏览器下载后 --from-local" if from_local
                                  else "脚本 archive_pdf.py 直链下载"),
                          downloaded_at=downloaded_at, downloaded_by=by,
                          note=note)

    print(f"  大小：{size:,} B")
    print(f"  页数：{pages if pages is not None else '未知'}"
          + (f"（全文应为 {expected} 页）" if expected else ""))
    if expected and pages and pages < expected:
        print("  [警告] 页数少于全文，这是节选件，不能当原文用。")
    print(f"  SHA-256：{digest}")
    print(f"  写入：{sha_path.relative_to(ROOT)}、{src.relative_to(ROOT)}")
    print(f"  来源类型：{source_type}" + ("  ← 不得作为条文出处" if source_type == "转载" else ""))
    print("-" * 64)
    print("提醒：PDF 已被 .gitignore 排除，不会进 git。")
    print("      校验请跑：python scripts/archive_pdf.py " + sid + " --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
