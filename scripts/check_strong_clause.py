#!/usr/bin/env python3
"""检查库内是否有「引用已废止强制性条文」的条目。

**这是本项目的 C 类缺陷检测器。**
项目自己归纳的三类现行性缺陷：A 完全现行／B 引已整部废止的标准／
C 引已废止的强条。B 类容易发现（标准号一查就知），C 类最难——
标准号、名称、年版全都对，条文内容也一字不差，**唯一错的是它的强制等级**。
肉眼读不出来，只能靠条号比对。

判据来自 `sources/abolished_strong_clauses.json`，而那份 JSON 由
`scripts/build_abolished_list.py` 从官方公告附件生成，条号不经人手。

检查两件事：
  1. 标了 strong_clause，但该条号已在废止清单内 → 错误（引已废止的强条）
  2. 标了 pending(intended_level=strong_clause)，但该条号已在废止清单内
     → 错误（打算恢复成一个已废止的强条）

另外对 `complete_strong_clause_set: true` 的标准多做一条：
  该标准的强条全集就是清单所列、且已全部废止，因此库内**任何**条目都
  不得标 strong_clause。这能抓出「条号不在清单里、却标成强条」的误标。

用法：
    python scripts/check_strong_clause.py           # 报告，有问题返回 1
    python scripts/check_strong_clause.py --quiet    # 只在有问题时输出
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"
LIST = ROOT / "sources" / "abolished_strong_clauses.json"


def norm(standard: str, year) -> str:
    """把规则里的「GB 50015 + 2019」与清单里的「GB 50015-2019」对齐。

    两侧都要去掉空格：规则写「GB 50015」，清单键写「GB 50015-2019」。
    只归一化一侧会静默匹配不上——本检查第一版就是这么错的，
    结果报「库内落在清单覆盖范围内的标准：无」，看着是通过，实则一条没比。
    所以下面 main() 里断言 matched_standards 非空（清单覆盖的标准若在库内）。
    """
    return f"{str(standard).replace(' ', '').strip()}-{year}"


def norm_key(key: str) -> str:
    return key.replace(" ", "").strip()


def load_rules() -> list[tuple[str, dict]]:
    out = []
    for path in sorted(DRAFTS.glob("_draft_*.json")):
        for r in json.loads(path.read_text(encoding="utf-8")):
            out.append((path.name, r))
    return out


def main() -> int:
    quiet = "--quiet" in sys.argv
    if not LIST.exists():
        print(f"缺少 {LIST.relative_to(ROOT)}，先跑 scripts/build_abolished_list.py")
        return 2

    data = json.loads(LIST.read_text(encoding="utf-8"))
    by_key = {norm_key(i["key"]): i for i in data["abolished"]}
    rules = load_rules()

    errors: list[str] = []
    checked = 0
    matched_standards = sorted({k for k in by_key} & {norm(r.get("standard"), r.get("standard_year")) for _, r in rules})

    # 独立交叉核对：用「(标准号, 年份) 元组」另算一遍应比对的条数。
    # 与上面的字符串键是两条不同的匹配路径——若两者不一致，说明归一化有问题，
    # 而问题会表现为「比对 0 条、然后报通过」。这正是本检查第一版的错法。
    list_pairs = {(str(i["standard"]).replace(" ", ""), i["year"]) for i in data["abolished"]}
    should_check = sum(
        1 for _, r in rules
        if (str(r.get("standard", "")).replace(" ", ""), r.get("standard_year")) in list_pairs
    )

    for fname, r in rules:
        key = norm(r.get("standard"), r.get("standard_year"))
        item = by_key.get(key)
        if not item:
            continue
        checked += 1
        clause = str(r.get("clause", "")).strip()
        level = r.get("mandatory_level")
        pend = r.get("mandatory_level_pending") or {}
        intended = pend.get("intended_level") if isinstance(pend, dict) else None

        in_list = clause in item["clauses"]

        if level == "strong_clause" and in_list:
            errors.append(
                f"[E100] {r.get('rule_id')} 标为 strong_clause，但 {clause} 已由 "
                f"{item['announcement']}（{item['abolished_by']}，{item['effective']} 起）"
                f"废止强条属性")
        if intended == "strong_clause" and in_list:
            errors.append(
                f"[E101] {r.get('rule_id')} 的 pending.intended_level=strong_clause，"
                f"但 {clause} 的强条属性已废止")
        if (item.get("complete_strong_clause_set")
                and level == "strong_clause" and not in_list):
            errors.append(
                f"[E102] {r.get('rule_id')} 标为 strong_clause，但 {clause} 不在 "
                f"{key} 的强条全集内（该标准强条共 {item['count']} 条，"
                f"已全部废止，故本条不得标强条）")

    if not quiet:
        print("=" * 66)
        print("已废止强制性条文 · 库内引用检查")
        print("=" * 66)
        print(f"清单：{len(by_key)} 项 / "
              f"{sum(i['count'] for i in data['abolished'])} 条")
        print(f"库内落在清单覆盖范围内的标准：{matched_standards or '无'}")
        print(f"参与比对的库内条目：{checked} 条")
        print("-" * 66)

    if should_check != checked:
        print(f"归一化失效：按元组匹配应有 {should_check} 条参与比对，"
              f"实际只比对 {checked} 条。检查不成立，不得据此报「通过」。")
        return 2

    if errors:
        for e in errors:
            print("  " + e)
        print(f"\n不通过：{len(errors)} 条引用了已废止的强制性条文。")
        return 1

    if not quiet:
        print("通过：库内无「引用已废止强条」的条目。")
        print("注意：本检查只覆盖「公告已明确列号」的废止。"
              "标准是否整部废止、是否出修改单，仍须走公告四查。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
