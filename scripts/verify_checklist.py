#!/usr/bin/env python3
"""核对任务清单的完整性校验。

为什么需要这个脚本：清单本身由脚本生成，但生成逻辑与校验逻辑若都靠
人眼看，就会漏掉重复行。本脚本固化四条断言：

  1. 清单表格数据行数 == 草稿条目数（不做去重）
  2. 清单 rule_id 序列与草稿序列一一对应（多重集相等）
  3. 每个 rule_id 在清单中只出现一次
  4. 清单无 UTF-8 坏字符

第 1、2 条刻意不使用 set()。历史教训：同一失败模式已出现五次——
附录 G 数值错位、5.2.38 静默丢维度、强条清单 31/29/30、校验脚本回退
自证循环、以及清单 EP 条目重复 6 条。第五次是我用 set() 做覆盖率比对，
把重复吃掉了，同时骗过了我和复核两人。集合会去重，列表不会。

用法：
    python scripts/verify_checklist.py           # 校验，退出码非零表示有问题
"""
from __future__ import annotations

import collections
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CHECKLIST = ROOT / "docs" / "核对任务清单.md"
RULES_DIR = ROOT / "rules" / "building_rain"

# 清单表格数据行：以反引号包裹的 rule_id 开头
ROW_RE = re.compile(r"^\| `((?:GB|EP)[^`]+)` \|")
# 匹配 UTF-8 替换字符（解码失败或写入时截断的痕迹）
BAD_CHAR = "�"


def load_rule_ids() -> list[str]:
    """按文件名字典序读取草稿 rule_id，保留重复（正常应无）。"""
    ids: list[str] = []
    for path in sorted(RULES_DIR.glob("_draft_*.json")):
        for rule in json.loads(path.read_text(encoding="utf-8")):
            ids.append(rule["rule_id"])
    return ids


def main() -> int:
    errors: list[str] = []

    if not CHECKLIST.exists():
        print(f"找不到清单：{CHECKLIST}")
        return 1

    text = CHECKLIST.read_text(encoding="utf-8")
    rows = [m.group(1) for m in (ROW_RE.match(line) for line in text.split("\n")) if m]
    rules = load_rule_ids()

    print("=" * 60)
    print("核对任务清单 · 完整性校验")
    print("=" * 60)
    print(f"草稿条目：{len(rules)} 条")
    print(f"清单数据行：{len(rows)} 行")

    # 断言 1：行数相等（不做去重）
    if len(rows) != len(rules):
        errors.append(f"行数不等：清单 {len(rows)} 行 vs 草稿 {len(rules)} 条")

    # 断言 2、3：多重集相等且无重复
    rule_count = collections.Counter(rules)
    row_count = collections.Counter(rows)

    only_doc = row_count - rule_count
    only_rule = rule_count - row_count
    for rid, n in only_doc.items():
        errors.append(f"清单有而草稿无：{rid}（多 {n} 次）")
    for rid, n in only_rule.items():
        errors.append(f"草稿有而清单无：{rid}（缺 {n} 次）")

    for rid, n in row_count.items():
        if n > 1:
            errors.append(f"清单中重复出现：{rid} × {n}")

    # 断言 4：坏字符
    bad = [i + 1 for i, line in enumerate(text.split("\n")) if BAD_CHAR in line]
    for i in bad:
        errors.append(f"第 {i} 行含 UTF-8 坏字符")

    print(f"唯一 rule_id：{len(row_count)} 个（去重后）")
    if len(row_count) != len(rows):
        print(f"⚠️  有重复：{len(rows)} 行含 {len(row_count)} 个唯一 id")
    print("-" * 60)

    if errors:
        print(f"不通过：{len(errors)} 个问题")
        for e in errors:
            print(f"  ERROR {e}")
        return 1

    print("通过：行数一致、无重复、无缺漏、无坏字符")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())