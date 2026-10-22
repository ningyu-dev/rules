#!/usr/bin/env python3
"""把 lookup_table 的 _TEMPORARY_* 结构迁移到正式字段（S-3a / S-3b）。

背景：旧 schema 的 lookup_table 只有 rows/columns/values 三件套，且
columns 必须是数字数组。为把规范里三种不同的表塞进去，草稿里出现了两种
权宜做法，都留下了隐患：

  1. 伪造公共轴 —— 附录 G 的铸铁/塑料/钢管规格互不对齐（7/13/7 档），
     硬并成一根 columns 会丢档、错位，De110 查表得 18.30（真实 12.80），
     高估 43% → 立管选小 → 溢流。
  2. 位置约定 —— 表 5.2.34 的「第二行是斗前水深」，语义靠 rows[1] 的
     位置维持，换个人重排就错。

新 schema 给了三种形态：values（矩阵）、groups（分组，各组自带列轴）、
entries（行键 + 具名 metrics）。本脚本按形态逐条迁移，**只改结构不改数值**，
并用硬编码的期望值断言迁移前后的数字完全一致。

用法：
    python scripts/migrate_lookup_tables.py            # 只报告
    python scripts/migrate_lookup_tables.py --apply    # 写入
"""
from __future__ import annotations

import copy
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DRAFTS = ROOT / "rules" / "building_rain"

# 迁移后必须成立的硬事实。数字来自草稿既有值，迁移不允许改动它们。
EXPECT = {
    "GB50015-2019-appendix-G": {
        "group_sizes": {"cast_iron": 7, "plastic": 13, "steel": 7},
        "total": 27,
        "spot_group": [("plastic", "110x3.2", 12.8), ("cast_iron", 100, 9.5), ("steel", "88.9x4.0", 5.1)],
    },
    "GB50015-2019-5.2.34-1": {
        "entries": {"75": (7.1, 48), "100": (7.4, 50), "150": (13.7, 68)},
    },
    "GB50015-2019-5.2.38": {
        "spot_diameter": [("雨水排水立管", "塑料管", 110), ("建筑外墙雨落水管", "塑料管", 75)],
    },
    "GB50014-2021-5.2.10": {
        "spot_slope": [("雨水管", "塑料管", 0.002), ("雨水管", "其他管", 0.003)],
    },
    "GB51022-2015-11.1.11": {
        "spot_ratio": [("直立缝锁边连接板", 0.0333, "1/30")],
    },
}


def migrate_appendix_g(lt: dict) -> None:
    groups = []
    for g in lt["_TEMPORARY_groups"]:
        groups.append({
            "key": g["key"],
            "label": g.get("label", ""),
            "columns": g["columns"],
            "values": g["values"],
        })
    lt["groups"] = groups
    lt["x_axis_label"] = "管径规格（各组自定：DN 或 外径×壁厚，mm）"
    lt["y_axis_label"] = "最大泄流量 (L/s)"
    lt["unit"] = "L/s"
    for k in ("rows", "columns", "values", "_TEMPORARY_groups", "_TEMPORARY_note"):
        lt.pop(k, None)


def migrate_5_2_34(lt: dict) -> None:
    by_dia = lt["_TEMPORARY_metrics"]["by_diameter_mm"]
    lt["entries"] = [
        {"key": str(dia),
         "metrics": {"max_discharge_lps": v["max_discharge_lps"],
                     "head_depth_mm": v["head_depth_mm"]}}
        for dia, v in by_dia.items()
    ]
    lt["x_axis_label"] = "雨水斗规格 (mm)"
    lt["y_axis_label"] = "具名指标（见 metrics 键名）"
    lt["unit"] = "见 metrics 键名"
    for k in ("rows", "columns", "values", "_TEMPORARY_metrics"):
        lt.pop(k, None)


def migrate_5_2_38(lt: dict) -> None:
    entries = []
    for e in lt["_TEMPORARY_entries"]:
        metrics = {"min_diameter_mm": e["values"]}
        if "min_slope" in e:
            metrics["min_slope"] = e["min_slope"]
        entries.append({"key": e["key"], "metrics": metrics})
    lt["entries"] = entries
    lt["x_axis_label"] = "管别"
    lt["y_axis_label"] = "最小管径 (mm) / 最小设计坡度（按管材细分）"
    lt["unit"] = "见 metrics 键名"
    for k in ("rows", "columns", "values", "_TEMPORARY_entries", "_TEMPORARY_note"):
        lt.pop(k, None)


def migrate_5_2_10(lt: dict) -> None:
    entries = []
    for e in lt["_TEMPORARY_entries"]:
        entries.append({"key": e["key"],
                        "metrics": {k: v for k, v in e.items() if k != "key"}})
    lt["entries"] = entries
    lt["x_axis_label"] = "管道类别"
    lt["y_axis_label"] = "最小管径 (mm) / 相应最小设计坡度"
    lt["unit"] = "见 metrics 键名"
    for k in ("rows", "columns", "values", "_TEMPORARY_entries", "_TEMPORARY_note"):
        lt.pop(k, None)


def migrate_11_1_11(lt: dict) -> None:
    entries = []
    for e in lt["_TEMPORARY_entries"]:
        entries.append({"key": e["key"],
                        "metrics": {"max_slope_ratio": e["max_slope_ratio"],
                                    "expression": e["expression"]}})
    lt["entries"] = entries
    lt["x_axis_label"] = "屋面板连接方式"
    lt["y_axis_label"] = "屋面排水坡度上限（比值）"
    lt["unit"] = "ratio"
    for k in ("rows", "columns", "values", "_TEMPORARY_entries", "_TEMPORARY_note"):
        lt.pop(k, None)


MIGRATORS = {
    "GB50015-2019-appendix-G": migrate_appendix_g,
    "GB50015-2019-5.2.34-1": migrate_5_2_34,
    "GB50015-2019-5.2.38": migrate_5_2_38,
    "GB50014-2021-5.2.10": migrate_5_2_10,
    "GB51022-2015-11.1.11": migrate_11_1_11,
}


def verify(rule: dict) -> list[str]:
    """迁移后的硬断言。任何一条不成立即拒绝写入。"""
    rid = rule["rule_id"]
    lt = rule["lookup_table"]
    problems: list[str] = []
    exp = EXPECT[rid]

    if "group_sizes" in exp:
        groups = {g["key"]: g for g in lt.get("groups", [])}
        got = {k: len(g["columns"]) for k, g in groups.items()}
        if got != exp["group_sizes"]:
            problems.append(f"分组档位变化：期望 {exp['group_sizes']}，实际 {got}")
        total = sum(got.values())
        if total != exp["total"]:
            problems.append(f"总档位变化：期望 {exp['total']}，实际 {total}")
        for gkey, col, want in exp["spot_group"]:
            g = groups.get(gkey)
            if not g:
                problems.append(f"缺少分组 {gkey}")
                continue
            cols = g["columns"]
            if col not in cols:
                problems.append(f"分组 {gkey} 缺少规格 {col}")
                continue
            got_v = g["values"][0][cols.index(col)]
            if got_v != want:
                problems.append(f"{gkey}/{col} 泄流量变化：期望 {want}，实际 {got_v}")

    if "entries" in exp:
        got = {e["key"]: (e["metrics"]["max_discharge_lps"], e["metrics"]["head_depth_mm"])
               for e in lt.get("entries", [])}
        if got != exp["entries"]:
            problems.append(f"表 5.2.34 数值变化：期望 {exp['entries']}，实际 {got}")

    if "spot_diameter" in exp:
        entries = {e["key"]: e["metrics"] for e in lt.get("entries", [])}
        for key, material, want in exp["spot_diameter"]:
            m = entries.get(key)
            if not m:
                problems.append(f"缺少行键 {key}")
                continue
            got = m["min_diameter_mm"].get(material) if isinstance(m["min_diameter_mm"], dict) else None
            if got != want:
                problems.append(f"{key}/{material} 最小管径变化：期望 {want}，实际 {got}")

    if "spot_slope" in exp:
        entries = {e["key"]: e["metrics"] for e in lt.get("entries", [])}
        for key, material, want in exp["spot_slope"]:
            m = entries.get(key)
            if not m:
                problems.append(f"缺少行键 {key}")
                continue
            got = m["min_slope"].get(material) if isinstance(m["min_slope"], dict) else None
            if got != want:
                problems.append(f"{key}/{material} 坡度变化：期望 {want}，实际 {got}")

    if rid == "GB51022-2015-11.1.11":
        entries = {e["key"]: e["metrics"] for e in lt.get("entries", [])}
        for key, ratio, expr in exp["spot_ratio"]:
            m = entries.get(key)
            if not m:
                problems.append(f"缺少行键 {key}")
                continue
            if m["max_slope_ratio"] != ratio or m["expression"] != expr:
                problems.append(f"{key} 坡度表达变化：{m}")

    # 所有临时字段必须清干净
    leftovers = [k for k in lt if k.startswith("_TEMPORARY")]
    if leftovers:
        problems.append(f"残留临时字段：{leftovers}")
    return problems


def main() -> int:
    apply_mode = "--apply" in sys.argv
    drafts = sorted(DRAFTS.glob("_draft_*.json"))
    if not drafts:
        print("未找到草稿文件")
        return 2

    migrated, skipped, failed = [], [], []
    touched = 0

    for path in drafts:
        rules = json.loads(path.read_text(encoding="utf-8"))
        dirty = False

        for rule in rules:
            rid = rule.get("rule_id")
            lt = rule.get("lookup_table")
            if not isinstance(lt, dict):
                continue
            has_temp = any(k.startswith("_TEMPORARY") for k in lt)
            if not has_temp:
                if rid in MIGRATORS:
                    skipped.append(rid)
                continue
            migrator = MIGRATORS.get(rid)
            if not migrator:
                failed.append((rid, ["有临时结构但没有对应迁移规则"]))
                continue

            before = copy.deepcopy(lt)
            migrator(lt)
            problems = verify(rule)
            if problems:
                # 断言失败必须回滚，不能留下半迁移状态
                rule["lookup_table"] = before
                failed.append((rid, problems))
                continue

            migrated.append(rid)
            dirty = True

        if dirty:
            touched += 1
            if apply_mode:
                path.write_text(
                    json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )

    print("=" * 66)
    print("lookup_table 临时结构迁移" + ("（已写入）" if apply_mode else "（仅报告）"))
    print("=" * 66)
    print(f"迁移成功：{len(migrated)} 条")
    for rid in migrated:
        print(f"  {rid}")
    if skipped:
        print(f"已是正式结构、本次跳过：{len(skipped)} 条")
    if failed:
        print(f"失败（已回滚）：{len(failed)} 条")
        for rid, problems in failed:
            print(f"  {rid}")
            for p in problems:
                print(f"    - {p}")
    print(f"改动文件：{touched} 个")
    print("-" * 66)
    print("口径：按 rule_id 计数。断言逐条比对迁移前后的数值，"
          "任何一项不等即回滚该条，不写入。")

    if failed:
        return 1
    if not apply_mode:
        print("\n以上为报告。加 --apply 写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
