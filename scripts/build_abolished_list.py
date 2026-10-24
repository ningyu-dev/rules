#!/usr/bin/env python3
"""从已归档的官方公告附件生成 `sources/abolished_strong_clauses.json`。

**为什么不让 JSON 手工维护**
废止清单有 78 个条号。手工转录一定出错，且出错后无法复核——你没法
用眼睛比对 78 个「3.10.13」和「3.10.31」。所以 JSON 由脚本从官方附件
原文解析生成，条号一律不经人手。附件本身带 SHA-256，可追溯到具体文件。

**为什么必须取附件而不是公告正文**
GB 55020-2021 的公告正文只写「现行工程建设标准相关强制性条文同时废止」，
**不列条号**。条号全在附件 2。只看公告正文，会得出「全部废止了」这个
正确但无法执行（不知道哪几条）的结论；而库里的规则是按条号标记的，
判定必须落到条号一级。这就是「三查查不出修改单」之外的第二类盲区：
**公告查到了、措辞也读对了，但判据在附件里，附件没取。**

**为什么只有 GB 50015-2019 标 complete_strong_clause_set**
「该标准的强条全集是否等于本清单」是一个额外判断，不能默认成立。
GB 50015-2019 可以确认：公告 2019 年第 171 号逐条列了 30 条强条，
与本清单的 30 条逐项相同（见 verify 断言）。其余 8 项只知「这些条号被废止」，
不知「是否还有别的强条没被废止」，因此不标 complete。

用法：
    python scripts/build_abolished_list.py            # 只报告
    python scripts/build_abolished_list.py --apply    # 写入 JSON
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "sources" / "abolished_strong_clauses.json"

DOCX = ROOT / "archive/GB55020-2021/废止强条清单.docx"
TXT = ROOT / "archive/GB55020-2021/废止强条清单.txt"
ANNOUNCEMENT = ROOT / "archive/GB50015-2019/announcement.html"

DOCX_URL = ("https://www.mohurd.gov.cn/file/2021/20211012/"
            "cdd16de8eb9bf3a83a5d01f55acaa101.docx")

# 已知「强条全集 == 本清单」的标准，及其强条全集出处。
# 依据：GB 50015-2019 公告 2019 年第 171 号逐条列出 30 条强条，与本清单逐项相同。
COMPLETE_SET = {"GB 50015-2019"}

ITEM_RE = re.compile(
    r"(\d+)\.《(.+?)》\s*([A-Z][A-Za-z0-9/ ]*?)-(\d{4})第(.+)条$")
CLAUSE_RE = re.compile(r"\d+\.\d+\.\d+")


def sha256_of(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docx_lines(path: pathlib.Path) -> list[str]:
    """直接从 .docx 抽取段落文本。

    **不读派生的 .txt**：.txt 是副产物，一旦与 .docx 不同步，判据就悄悄变了，
    而且没有任何东西会发现。判据的唯一来源必须是带哈希的那个 .docx。
    .txt 只在 --apply 时由本函数顺手写出，供 grep 与 diff 用。
    """
    import html
    import re as _re
    import zipfile

    xml = zipfile.ZipFile(path).read("word/document.xml").decode("utf-8")
    xml = _re.sub(r"</w:p>", "\n", xml)
    txt = html.unescape(_re.sub(r"<[^>]+>", "", xml))
    return [l.strip() for l in txt.splitlines() if l.strip()]


def parse_items() -> list[dict]:
    if not DOCX.exists():
        raise SystemExit(f"缺少官方附件：{DOCX}\n"
                         "按 SOURCE.md 记录的直链下载后重跑。")
    items: list[dict] = []
    for line in docx_lines(DOCX):
        m = ITEM_RE.match(line.strip())
        if not m:
            continue
        seq, name, code, year, clause_part = m.groups()
        clauses = CLAUSE_RE.findall(clause_part)
        std = f"{code.strip()}-{year}"
        items.append({
            "standard": code.strip(),
            "year": int(year),
            "key": std,
            "name": name.strip(),
            "clauses": clauses,
            "count": len(clauses),
            "abolished_by": "GB 55020-2021",
            "announcement": "住房和城乡建设部公告 2021 年第 171 号",
            "effective": "2022-04-01",
            "scope": "strong_clause_status_only",
            "complete_strong_clause_set": std in COMPLETE_SET,
            "handling": "标准本体现行，条文照常引用；所列条号不得再作强制性条文引用。",
        })
    return items


def announcement_clauses() -> list[str]:
    """从 GB 50015-2019 公告正文抽出强条条号，用于交叉核对。"""
    import html

    raw = ANNOUNCEMENT.read_text(encoding="utf-8", errors="replace")
    body = re.sub(r"<script.*?</script>|<style.*?</style>", "", raw, flags=re.S)
    txt = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", body)))
    m = re.search(r"其中[^。]{0,400}?条为强制性条文", txt)
    return CLAUSE_RE.findall(m.group(0)) if m else []


def build() -> dict:
    items = parse_items()
    return {
        "_meta": {
            "title": "已废止强制性条文清单",
            "purpose": "给 validate / check_strong_clause 提供条号级判据："
                       "哪些条号已经不能再作强制性条文引用。",
            "rule": "只登记官方公告（正文或公告附件）明确列出条号的情形。"
                    "第三方标准平台标注的「部分作废」不作为依据——"
                    "平台字段与公告原文冲突已有实例（GB 50788-2012 被标「部分被替代」，"
                    "公告实为整部废止）。",
            "distinction": "scope=strong_clause_status_only 表示标准本体现行、"
                           "仅所列条号的强条属性废止。这与「整部废止」处置完全不同："
                           "前者照常引用标准，后者任何条文不得再引。",
            "complete_strong_clause_set": "为 true 时表示该标准的强条全集"
                                           "就是本清单所列条号（且已全部废止），"
                                           "故库内该标准不得出现任何 strong_clause。",
            "generated_by": "scripts/build_abolished_list.py",
            "do_not_edit": "本文件由脚本生成，请勿手工修改。要改请改脚本或补官方附件后重跑。",
            "announcements": [
                {
                    "announcement": "住房和城乡建设部公告 2021 年第 171 号",
                    "document": "GB 55020-2021 建筑给水排水与节水通用规范",
                    "effective": "2022-04-01",
                    "attachment_title": "废止的现行工程建设标准相关强制性条文",
                    "attachment_file": str(DOCX.relative_to(ROOT)),
                    "attachment_sha256": sha256_of(DOCX),
                    "attachment_url": DOCX_URL,
                    "retrieved": "2026-10-24",
                    "source_type": "官方",
                    "why_attachment": "公告正文只写「现行工程建设标准相关强制性条文同时废止」，"
                                      "不列条号；条号在附件 2。只看正文无法落到条号一级。",
                },
            ],
        },
        "abolished": items,
    }


def verify(data: dict) -> list[str]:
    """断言清单自身站得住，再写文件。"""
    problems: list[str] = []
    items = data["abolished"]
    if len(items) != 9:
        problems.append(f"项数应为 9，实际 {len(items)}")

    total = sum(i["count"] for i in items)
    if total != 78:
        problems.append(f"条号合计应为 78，实际 {total}")

    # 交叉核对：GB 50015-2019 的公告强条 == 本清单该标准条号
    gb = next((i for i in items if i["key"] == "GB 50015-2019"), None)
    if not gb:
        problems.append("清单缺 GB 50015-2019 项")
    else:
        anno = announcement_clauses()
        if not anno:
            problems.append("未能从公告 171 号抽出强条条号，交叉核对失效")
        elif anno != gb["clauses"]:
            problems.append(
                f"公告 171 号（{len(anno)} 条）与废止清单（{gb['count']} 条）不一致："
                f"仅在公告 {sorted(set(anno) - set(gb['clauses']))}，"
                f"仅在清单 {sorted(set(gb['clauses']) - set(anno))}")
        if gb["count"] != 30:
            problems.append(f"GB 50015-2019 应为 30 条，实际 {gb['count']}")

    # 每项条号必须唯一且非空
    for i in items:
        if not i["clauses"]:
            problems.append(f"{i['key']} 条号为空")
        if len(set(i["clauses"])) != len(i["clauses"]):
            problems.append(f"{i['key']} 条号有重复")

    return problems


def main() -> int:
    apply_mode = "--apply" in sys.argv
    data = build()
    problems = verify(data)

    print("=" * 66)
    print("已废止强制性条文清单 · 生成")
    print("=" * 66)
    print(f"{'标准':18s} {'条数':>4s} {'全集已知':>6s}  名称")
    print("-" * 66)
    for i in data["abolished"]:
        print(f"{i['key']:18s} {i['count']:>4d} "
              f"{'是' if i['complete_strong_clause_set'] else '否':>6s}  {i['name'][:24]}")
    print("-" * 66)
    print(f"合计 {len(data['abolished'])} 项 / "
          f"{sum(i['count'] for i in data['abolished'])} 条")
    print(f"附件 SHA-256：{data['_meta']['announcements'][0]['attachment_sha256']}")

    if problems:
        print("-" * 66)
        print("清单自身不自洽，拒绝写入：")
        for p in problems:
            print("  -", p)
        return 1

    print("-" * 66)
    print("自检通过：公告 171 号与附件 2 的 GB 50015-2019 条号逐项相同。")

    if not apply_mode:
        print("以上为报告。加 --apply 写入。")
        return 0

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    print(f"已写入 {OUT.relative_to(ROOT)}")

    # 顺手写出可 grep 的派生文本，仅供人读与 diff；判据始终以 .docx 为准。
    TXT.write_text("\n".join(docx_lines(DOCX)) + "\n", encoding="utf-8")
    print(f"已写入 {TXT.relative_to(ROOT)}（派生文本，判据以 .docx 为准）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
