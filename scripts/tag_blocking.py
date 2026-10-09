#!/usr/bin/env python3
"""为含「应/不应/严禁/不得」但被标为 recommended 的规则打阻断标记。

背景：plumbing-rainwater-site-drainage 曾声明已加 mandatory_level_pending
与 safety_critical 字段，但实测 88 条草稿中这两个字段一条都不存在，
且 34 条含强制模态词的条文仍标 recommended，其中包含溢流设施这类
安全关键项。本脚本作为可复现的补救措施，不依赖成员自述。

用法：
    python scripts/tag_blocking.py            # 检查并报告
    python scripts/tag_blocking.py --apply    # 写入标记

写入的字段是 schema 未定义的扩展字段，validate.py 的 --strict 模式
会对它们报错，这是预期的：schema 改造完成前，这些规则本就不可投产。
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"

# 强制模态词。「宜」类推荐词单独处理，不在此列。
STRONG_VERB = re.compile(r"[应不严须禁][应不应严禁必须不得]?")
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


def main() -> int:
    apply_mode = "--apply" in sys.argv
    drafts = sorted(DRAFTS.glob("_draft_*.json"))
    if not drafts:
        print("未找到草稿文件")
        return 2

    tagged, reviewed = [], 0

    for path in drafts:
        rules = json.loads(path.read_text(encoding="utf-8"))
        dirty = False

        for r in rules:
            level = r.get("mandatory_level")
            stmt = r.get("statement") or ""

            # 只处理：标了 recommended，但含强制模态词，且不是纯推荐表述
            if level != "recommended":
                continue
            if not any(w in stmt for w in VERB_WORDS):
                continue
            if is_recommended_only(stmt):
                continue

            reviewed += 1
            r["mandatory_level"] = "mandatory_level_pending"
            r["intended_level"] = "clause"
            r["normative_verb"] = next(
                (w for w in VERB_WORDS if w in stmt), "unknown"
            )
            r["blocks_production"] = True
            if is_safety_critical(r):
                r["safety_critical"] = True
            tagged.append(r["rule_id"])
            dirty = True

        if dirty and apply_mode:
            path.write_text(
                json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

    print("=" * 60)
    print(f"含强制模态词但被标 recommended 的规则：{reviewed} 条")
    print(f"已标记 blocks_production / mandatory_level_pending：{len(tagged)} 条")

    safety = [r for r in tagged if "safety_critical" in str(r)]
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
