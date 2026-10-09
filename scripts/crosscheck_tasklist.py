#!/usr/bin/env python3
"""交叉校验：核对任务清单 vs 规则库草稿。

为什么需要：清单曾出现 91 行 vs 草稿 85 条的偏差（6 条 EP
整段重复粘贴），而当时两方各自都报"一致"——清单侧用 set()
比对、只看唯一数，差异被掩盖。集合能证明"没有遗漏"，
不能证明"没有重复"。

这类偏差的共同特征（同前三例）：
  数字看着有、但错了，且没有任何检查会报。
因此必须有独立的交叉校验，而不是靠成员自述。

用法：
    python scripts/crosscheck_tasklist.py
"""
from __future__ import annotations

import collections
import glob
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"
TASKLIST_GLOB = str(ROOT / "docs" / "*核对*.md")

RID_RE = re.compile(r"`((?:GB|CJJ|CJT|EP)[^`]{4,60})`")


def load_tasklist() -> tuple[pathlib.Path, list[str]]:
    matches = glob.glob(TASKLIST_GLOB)
    if not matches:
        raise SystemExit(f"未找到核对清单：{TASKLIST_GLOB}")
    p = pathlib.Path(matches[0])
    return p, RID_RE.findall(p.read_text(encoding="utf-8"))


def load_drafts() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for f in sorted(DRAFTS.glob("_draft_*.json")):
        for r in json.loads(f.read_text(encoding="utf-8")):
            rid = r.get("rule_id")
            if rid:
                out[rid] = r
    return out


def main() -> int:
    tl_path, tl_ids = load_tasklist()
    drafts = load_drafts()
    d_ids = set(drafts)
    t_counts = collections.Counter(tl_ids)
    t_set = set(tl_ids)

    print("=" * 60)
    print("核对清单 vs 规则库草稿 交叉校验")
    print("=" * 60)
    print(f"清单文件：{tl_path.name}")
    print(f"清单行数：{len(tl_ids)} 处引用 / {len(t_set)} 个唯一")
    print(f"草稿条目：{len(d_ids)} 条")

    problems = 0

    # 1. 清单内部重复（集合能掩盖，必须查计数）
    dups = {k: v for k, v in t_counts.items() if v > 1}
    if dups:
        problems += 1
        print(f"\n[E1] 清单内部重复 {len(dups)} 个（清单比草稿多的行就在这里）：")
        for k, v in sorted(dups.items()):
            print(f"     {k}  出现 {v} 次")

    # 2. 清单有而草稿无
    orphan = sorted(t_set - d_ids)
    if orphan:
        problems += 1
        print(f"\n[E2] 清单有而草稿无 {len(orphan)} 个（清单指向不存在的条目）：")
        for k in orphan:
            print(f"     {k}")

    # 3. 草稿有而清单无（核对覆盖率缺口）
    missing = sorted(d_ids - t_set)
    if missing:
        problems += 1
        print(f"\n[W1] 草稿有而清单无 {len(missing)} 个（未纳入核对范围）：")
        for k in missing[:15]:
            print(f"     {k}")
        if len(missing) > 15:
            print(f"     ... 共 {len(missing)} 个")

    if not problems and not missing:
        print("\n一致：清单覆盖全部草稿条目，无重复、无孤立引用。")
        if len(tl_ids) != len(t_set):
            print(f"注意：清单有 {len(tl_ids)} 处引用但仅 {len(t_set)} 个唯一条目")
        print(f"核对覆盖率：{len(t_set & d_ids)}/{len(d_ids)} = 100%")
        return 0

    print()
    print("处理：清单须与草稿逐条对应，重复行按整行去除，不要按 ID 去重")
    print("（同 ID 可能承载不同核对维度）。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
