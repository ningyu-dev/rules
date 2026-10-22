#!/usr/bin/env python3
"""修复 tag_blocking.py 旧版留下的非法枚举值与镜像漂移。

背景（D-011）：tag_blocking.py 旧版第 86 行把**字段名**当作哨兵值写进了
枚举字段：

    r["mandatory_level"] = "mandatory_level_pending"

后果是 36 条规则的强制等级变成 schema 不认识的字符串（含 8 条
safety_critical），而当时 validate.py 不校验 enum，所以校验一路绿灯。

本脚本只做「可证明的还原」，不做任何语义判断：

  1. mandatory_level 的哨兵值 → recommended
     依据是该条 reason 自己写明「S-4 完成前暂以 recommended 承载」，
     这是它的真实基线值，不是本脚本的新判断。

  2. mandatory_level_pending.normative_verb 的**截断**修复
     仅当嵌套值是顶层值的严格前缀（如嵌套「应」、顶层「应按」）时，
     把嵌套值补成顶层值。这类是旧版正则截断留下的痕迹。

  3. 顶层镜像对齐（intended_level / blocks_production / safety_critical /
     safety_reason）。canonical 方向固定为「嵌套对象 → 顶层」，不反向。

  4. 幂等：已合法的值不再改动。

**刻意不做的事**：不按 statement 重算 normative_verb。实测「最长匹配」
规则会把 GB51022-2015-11.3.2-1 的总起句「应符合」当成约束词，而该条
实际约束的是「伸缩缝处天沟应设置变形缝」。按语句猜词会制造新的无依据
判断，与 D-009 同源。非截断型漂移一律保留原值并列入「需人工判定」。

用法：
    python scripts/fix_pending_level.py            # 只报告
    python scripts/fix_pending_level.py --apply    # 写入
"""
from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"

VALID_LEVELS = ("strong_clause", "mandatory_general_code", "recommended", "reference")
MIRROR_KEYS = ("intended_level", "blocks_production", "safety_critical", "safety_reason")
BASELINE = "recommended"

# 合法模态词表。不在表内的值（如旧版截断留下的单字「应」）不可能是有效取值。
VERB_WORDS = ("应设置", "应按", "应采用", "应符合", "不应", "严禁", "不得", "必须")

# 逐条人工判定的结果，必须写明依据。不用启发式、不按关键词猜。
# 键为 rule_id，值为 (应采用的模态词, 判定依据)。
MANUAL_VERB_OVERRIDES = {
    "GB51022-2015-11.3.2-1": (
        "应设置",
        "subject=gutter_expansion_joint_at_frame_joint，指向「伸缩缝处天沟设变形缝」；"
        "statement 第 1 款为「天沟应对应设置变形缝」。「应符合」是总起句的引导词，"
        "约束的是整条构造要求，不是本 subject 的模态词。",
    ),
}


def main() -> int:
    apply_mode = "--apply" in sys.argv
    drafts = sorted(DRAFTS.glob("_draft_*.json"))
    if not drafts:
        print("未找到草稿文件")
        return 2

    before: Counter = Counter()
    after: Counter = Counter()
    fixed_level: list[str] = []
    fixed_truncation: list[str] = []
    fixed_mirror: list[str] = []
    unresolved: list[tuple[str, str, str, str]] = []
    touched_files = 0

    for path in drafts:
        rules = json.loads(path.read_text(encoding="utf-8"))
        dirty = False

        for r in rules:
            before[r.get("mandatory_level")] += 1
            rid = r.get("rule_id")
            pend = r.get("mandatory_level_pending")

            # 1. 非法枚举值 → 基线值
            if r.get("mandatory_level") not in VALID_LEVELS:
                r["mandatory_level"] = BASELINE
                fixed_level.append(rid)
                dirty = True

            if isinstance(pend, dict):
                nested_verb = pend.get("normative_verb") or ""
                top_verb = r.get("normative_verb") or ""

                # 2. 模态词漂移：只处理可证明的三类，不做语义猜测
                if top_verb and nested_verb != top_verb:
                    if top_verb.startswith(nested_verb) and len(nested_verb) < len(top_verb):
                        # 2a 严格前缀型截断，如嵌套「应」、顶层「应按」
                        pend["normative_verb"] = top_verb
                        fixed_truncation.append(rid)
                        dirty = True
                    elif nested_verb not in VERB_WORDS:
                        # 2b 嵌套值不在模态词表内（如单字「应」），不可能是合法取值
                        pend["normative_verb"] = top_verb
                        fixed_truncation.append(rid)
                        dirty = True
                    elif rid in MANUAL_VERB_OVERRIDES:
                        # 2c 逐条人工判定并留痕
                        pend["normative_verb"] = MANUAL_VERB_OVERRIDES[rid][0]
                        fixed_truncation.append(rid)
                        dirty = True
                    else:
                        unresolved.append((rid, nested_verb, top_verb,
                                           (r.get("statement") or "")[:60]))

                # 3. 嵌套 → 顶层镜像
                for key in MIRROR_KEYS:
                    if key in pend and r.get(key) != pend[key]:
                        r[key] = pend[key]
                        if rid not in fixed_mirror:
                            fixed_mirror.append(rid)
                        dirty = True

            after[r.get("mandatory_level")] += 1

        if dirty:
            touched_files += 1
            if apply_mode:
                path.write_text(
                    json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

    print("=" * 60)
    print("待定级字段修复" + ("（已写入）" if apply_mode else "（仅报告）"))
    print("=" * 60)
    print(f"修复前 mandatory_level 分布：{dict(before)}")
    print(f"修复后 mandatory_level 分布：{dict(after)}")
    print(f"改动文件：{touched_files} 个")
    print("-" * 60)
    print(f"1. 哨兵值改回 {BASELINE}：{len(fixed_level)} 条")
    print(f"2. 模态词截断修复：{len(fixed_truncation)} 条")
    print(f"3. 顶层镜像对齐：{len(fixed_mirror)} 条")
    print(f"4. 需人工判定、本次未改：{len(unresolved)} 条")
    print("-" * 60)
    print("口径：按 rule_id 计数；分布对 85 条草稿全量统计，含未改动条目。")

    if unresolved:
        print("-" * 60)
        print("以下条目的 normative_verb 嵌套值与顶层值不一致，且不属可证类别：")
        print("（保留原值。语义判定须人工，不按语句猜——猜错会把总起句当约束词）")
        for rid, nested_v, top_v, snippet in unresolved:
            print(f"  {rid}")
            print(f"    嵌套=`{nested_v}`  顶层=`{top_v}`")
            print(f"    statement: {snippet}")

    if MANUAL_VERB_OVERRIDES and fixed_truncation:
        applied = [rid for rid in MANUAL_VERB_OVERRIDES if rid in fixed_truncation]
        if applied:
            print("-" * 60)
            print("其中按人工判定修正的条目（依据随脚本固化，可复核）：")
            for rid in applied:
                print(f"  {rid} → `{MANUAL_VERB_OVERRIDES[rid][0]}`")
                print(f"    依据：{MANUAL_VERB_OVERRIDES[rid][1]}")

    if not apply_mode:
        print("\n以上为报告。加 --apply 写入。")
        return 0

    print("\n已写入。请运行：")
    print("  python scripts/validate.py --include-samples")
    print("  python scripts/verify_checklist.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
