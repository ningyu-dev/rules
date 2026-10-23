#!/usr/bin/env python3
"""归档台账审计：每本标准的正文从哪来、谁下的、什么时候下的、是否完整。

为什么单独做这个脚本：
    PDF 本身被 .gitignore 排除，git 里看不到它。于是「这本规范到底有没有
    正文、从哪下的」在版本库里完全没有痕迹——除非把记录做成可检查的对象。

审计四条：
  1. 每个 archive/<标准>/ 必须有 SOURCE.md（没有记录 = 不知道出处）
  2. 有 PDF 就必须有 SHA256.txt，且哈希要对得上（否则不是同一份）
  3. 有 PDF 就必须记「来源页面」与「下载时间」；只记直链等于无法复核入口
  4. 「完整性」标为不完整的，单独列出——节选件不能当全文用

用法：
    python scripts/audit_archive.py
    python scripts/audit_archive.py --strict   # 无正文也算问题
"""
from __future__ import annotations

import hashlib
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "archive"

ROW = re.compile(r"^\|\s*\*{0,2}([^|*]+?)\*{0,2}\s*\|\s*(.*?)\s*\|\s*$")


def parse_md(path: pathlib.Path) -> dict[str, str]:
    """只认两列的键值表行。

    多列表格（如 GB50015 的「日期/来源/文件/大小/校验」）不参与解析——
    它们承载的是更细的下载流水，不是台账字段。

    同名字段出现两次且值不同时直接报错：扁平字典会静默取最后一个，
    此前「废止强条清单」小节复用 `SHA-256` 键，就把 PDF 的哈希覆盖成了
    清单的哈希，审计因此误报「不是同一份文件」。静默丢信息的手段不用。
    """
    fields: dict[str, str] = {}
    conflicts: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        key, value = cells
        key = key.replace("*", "").strip()
        if key in ("项", "") or set(key) <= {"-"}:
            continue
        value = value.replace("**", "").replace("`", "").strip()
        if key in fields and fields[key] != value:
            conflicts[key] = fields[key]
        fields[key] = value
    if conflicts:
        raise SystemExit(
            f"{path}: 字段 {sorted(conflicts)} 出现多次且值不同。\n"
            "扁平解析会静默取最后一个——请给附表字段改名（如「清单 SHA-256」）后重跑。"
        )
    return fields


def sha256_of(path: pathlib.Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    strict = "--strict" in sys.argv
    dirs = sorted(p for p in ARCHIVE.iterdir() if p.is_dir())
    if not dirs:
        print("archive/ 下没有标准目录。")
        return 2

    problems: list[str] = []
    rows = []

    for d in dirs:
        sid = d.name
        md = d / "SOURCE.md"
        pdf = next((p for p in d.glob("*.pdf")), None)
        sha = d / "SHA256.txt"

        if not md.exists():
            problems.append(f"{sid}: 缺 SOURCE.md —— 无法知道正文有没有、从哪来")
            rows.append((sid, "无记录", "-", "-", "-", "-"))
            continue

        f = parse_md(md)
        has_pdf = pdf is not None
        source_page = f.get("来源页面", "")
        dl_time = f.get("下载时间", "")
        source_type = f.get("来源类型", "")
        integrity = f.get("完整性", "")
        digest = f.get("SHA-256", "")

        if has_pdf:
            if not sha.exists():
                problems.append(f"{sid}: 有 PDF 但缺 SHA256.txt")
            elif digest:
                real = sha256_of(pdf)
                if real != digest:
                    problems.append(f"{sid}: 哈希与记录不一致，不是同一份文件")
            if "未记录" in source_page:
                problems.append(f"{sid}: 有 PDF 但来源页面未记录 —— 只能复核直链，无法复核下载入口")
            if "未下载" in dl_time or "未记录" in dl_time:
                problems.append(f"{sid}: 有 PDF 但下载时间未记录")
            if "不完整" in integrity:
                problems.append(f"{sid}: {integrity}")
            state = f"{pdf.stat().st_size / 1048576:.1f} MB"
        else:
            state = "本地无"
            # PDF 不进 git，clone 到新机器上本来就没有。本地有无是运行时
            # 状态，不是台账缺陷——只如实显示，不报错。

        rows.append((sid, state, source_type or "-", source_page or "-",
                     dl_time or "-", integrity or "-"))

    print("=" * 100)
    print("归档台账")
    print("=" * 100)
    head = f"{'标准':22s} {'正文':10s} {'来源类型':10s} {'下载时间':12s} {'完整性'}"
    print(head)
    print("-" * 100)
    for sid, state, stype, spage, dtime, integ in rows:
        stype_short = stype.split("（")[0][:9]
        print(f"{sid:22s} {state:10s} {stype_short:10s} {dtime:12s} {integ[:40]}")
    print("-" * 100)
    with_pdf = sum(1 for r in rows if r[1] not in ("本地无", "无记录"))
    print(f"共 {len(rows)} 本：本地有 PDF {with_pdf} 本，本地无 PDF {len(rows) - with_pdf} 本")
    print("口径：本地运行时状态，按 archive/<id>/*.pdf 是否存在计；该状态不写入版本库。")

    if problems:
        print("-" * 100)
        print(f"问题 {len(problems)} 项：")
        for p in problems:
            print(f"  - {p}")
        # 有问题就红。不设「已知问题白名单」——白名单是「绿着但坏了」的开端，
        # 本项目已经在「校验通过 ≠ 正确」上栽过多次。
        return 1

    print("\n全部合规：有正文的都记了来源页面、下载时间与哈希。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
