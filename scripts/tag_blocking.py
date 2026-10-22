#!/usr/bin/env python3
"""为含「应/不应/严禁/不得」但被标为 recommended 的规则打阻断标记。

背景：plumbing-rainwater-site-drainage 曾声明已加 mandatory_level_pending
与 safety_critical 字段，但实测 88 条草稿中这两个字段一条都不存在，
且 34 条含强制模态词的条文仍标 recommended，其中包含溢流设施这类
安全关键项。本脚本作为可复现的补救措施，不依赖成员自述。

**2026-10-22 修正（D-011）**：旧版第 86 行执行
`r["mandatory_level"] = "mandatory_level_pending"`，把**字段名**当作
哨兵值写进了枚举字段。结果 36 条规则的强制等级变成一个 schema 不认识
的字符串（含 8 条 safety_critical），而 validate.py 当时不校验 enum，
一路绿灯。本次改为：mandatory_level 保留真实基线值，待定级信息只写入
mandatory_level_pending 对象及其顶层镜像。

用法：
    python scripts/tag_blocking.py            # 检查并报告
    python scripts/tag_blocking.py --apply    # 写入标记
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"

# 强制模态词。「宜」类推荐词单独处理，不在此列。
VERB_WORDS = ("应设置", "应按", "应采用", "应符合", "不应", "严禁", "不得", "必须")

# 安全关键主题：溢流、压力、荷载、井盖、间距、电气安全等。
# 这些一旦漏项，后果不是图纸返工，而是屋面超载或安全事故。
SAFETY_KEYWORDS = (
    "overflow", "overflow_facility", "溢流",
    "pressure", "荷载", "积水",
    "spacing", "间距", "净距",
    "grounding", "接地", "防雷",
    "sealed", "密闭", "防水",
)

# 推荐级用法词（不视为强制）
RECOMMEND_WORDS = ("宜为", "宜按", "宜取", "宜在", "不宜", "宜采用", "宜设置")

# 待定级的真实目标等级。schema 的 mandatory_level 枚举暂无 clause 档（S-4），
# 因此基线值仍落在 recommended，阻断靠 blocks_production 承担。
PENDING_TARGET = "clause"
BASELINE = "recommended"


def is_recommended_only(statement: str) -> bool:
    """判断是否为纯推荐级表述（含「宜」但不含强制词）。"""
    has_recommend = any(w in statement for w in RECOMMEND_WORDS)
    has_strong = any(w in statement for w in VERB_WORDS)
    return has_recommend and not has_strong


def is_safety_critical(rule: dict) -> bool:
    blob = " ".join([
        str(rule.get("subject", "")),
        str(rule.get("statement", "")),
        " ".join(rule.get("applies_to", {}).keys()) if isinstance(rule.get("applies_to"), dict) else "",
    ]).lower()
    return any(k.lower() in blob for k in SAFETY_KEYWORDS)


def build_pending(rule: dict) -> dict:
    verb = next((w for w in VERB_WORDS if w in (rule.get("statement") or "")), "unknown")
    pending = {
        "_TEMPORARY": True,
        "intended_level": PENDING_TARGET,
        "normative_verb": verb,
        "reason": (
            "条文使用强制性表述（应/不应/严禁/不得），非「宜/可」的推荐级。"
            "schema 的 mandatory_level 枚举缺 clause 档（见 docs/规范依据规划.md §6.4），"
            "S-4 完成前基线值落 recommended，由 blocks_production 阻断投产。"
        ),
        "blocks_production": True,
    }
    if is_safety_critical(rule):
        pending["safety_critical"] = True
        pending["safety_reason"] = (
            "涉及溢流/防水/荷载/人员安全，误判为可跳过将直接产生安全隐患。"
            "S-4 完成前本条禁止投产，且不得按 recommended 的「可确认跳过」处理。"
        )
    return pending


def main() -> int:
    apply_mode = "--apply" in sys.argv
    drafts = sorted(DRAFTS.glob("_draft_*.json"))
    if not drafts:
        print("未找到草稿文件")
        return 2

    tagged, reviewed, skipped = [], 0, 0

    for path in drafts:
        rules = json.loads(path.read_text(encoding="utf-8"))
        dirty = False

        for r in rules:
            level = r.get("mandatory_level")
            stmt = r.get("statement") or ""

            # 已有待定级对象 → 幂等跳过，不重复打标
            if isinstance(r.get("mandatory_level_pending"), dict):
                skipped += 1
                continue
            # 只处理基线值仍为 recommended 的条目
            if level != BASELINE:
                continue
            if not any(w in stmt for w in VERB_WORDS):
                continue
            if is_recommended_only(stmt):
                continue

            reviewed += 1
            pending = build_pending(r)
            r["mandatory_level_pending"] = pending
            # 顶层镜像，便于检索；validate.py 的 E015 会校验两者一致
            for key in ("intended_level", "normative_verb", "blocks_production",
                        "safety_critical", "safety_reason"):
                if key in pending:
                    r[key] = pending[key]
            tagged.append(r["rule_id"])
            dirty = True

        if dirty and apply_mode:
            path.write_text(
                json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    print("=" * 60)
    print(f"含强制模态词但基线值为 recommended 的规则：{reviewed} 条")
    print(f"已打待定级标记：{len(tagged)} 条")
    print(f"已有标记、本次跳过：{skipped} 条")
    print("-" * 60)
    print("口径：按 rule_id 计数；判据为「mandatory_level == recommended 且 statement 命中强制模态词"
          "且不属纯推荐表述」。已有 mandatory_level_pending 对象的条目一律跳过，故本脚本可重复运行。")

    if tagged:
        print("-" * 60)
        print("以下规则在 schema 改造完成前禁止投产：")
        for rid in tagged[:12]:
            print(f"  {rid}")
        if len(tagged) > 12:
            print(f"  ... 共 {len(tagged)} 条")
    print("-" * 60)

    if not apply_mode:
        print("以上为报告。加 --apply 写入标记。")
        return 0

    print("已写入。")
    return 0



if __name__ == "__main__":
    raise SystemExit(main())
