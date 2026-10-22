#!/usr/bin/env python3
"""把 2026-10-23 公告四查的结论写回登记表与规则库。

每一行都对应一条可核验的官方公告原文（URL 见 EVIDENCE）。本脚本只做
「把已核实的事实写进数据」，不做任何推断；查不到的一律不写。

本轮查出三处与仓库现有记录不一致的地方，均以公告原文为准：

  1. GB 50015-2019 实施日期：2019-10-01 → **2020-03-01**
  2. GB 55020-2021 实施日期：2021-10-01 → **2022-04-01**
  3. GB 50014-2021 第 4.1.6 条：**强条属性已于 2022-10-01 被 GB 55027-2022 废止**
     （GB 55027-2022 公告的废止清单第一项即含 4.1.6）

另有两处文档性错误，只影响 docs 不影响数据：
  - GB 51022-2015 的唯一强条是 14.2.5，表 11.1.11 **不是强条**
  - GB 50015-2019 的强条是 **30 条**（公告逐条列号），不是 31 条

用法：
    python scripts/apply_source_check.py            # 只报告
    python scripts/apply_source_check.py --apply    # 写入
"""
from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sources" / "standards.json"
DRAFTS = ROOT / "rules" / "building_rain"

CHECKED_AT = "2026-10-23"
CHECKED_BY = "沈澄 给排水工程师"

EVIDENCE = {
    "GB50015-2019": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2019/art_17339_242990.html",
    "GB55020-2021": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_762458.html",
    "GB55030-2022": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2022/art_17339_768499.html",
    "GB50014-2021": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2021/art_17339_250183.html",
    "GB50345-2012": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2012/art_17339_210744.html",
    "GB51022-2015": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2016/art_17339_226433.html",
    "GB55026-2022": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2024/art_17339_765626.html",
    "GB55027-2022": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2022/art_17339_765619.html",
    "CJT245-2021": "https://www.mohurd.gov.cn/gongkai/zc/wjk/art/2022/art_17339_765709.html",
}

# 公告原文核实到的字段。implemented 以公告「实施日期」字段为准。
VERIFIED = {
    "GB50015-2019": {"announcement_no": "2019 年第 171 号", "implemented": "2020-03-01",
                     "status": "current"},
    "GB55020-2021": {"announcement_no": "2021 年第 171 号", "implemented": "2022-04-01",
                     "status": "current"},
    "GB55030-2022": {"announcement_no": "2022 年第 147 号", "implemented": "2023-04-01",
                     "status": "current"},
    "GB50014-2021": {"announcement_no": "2021 年第 58 号", "implemented": "2021-10-01",
                     "status": "current"},
    "GB50345-2012": {"announcement_no": "2012 年第 1395 号", "implemented": "2012-10-01",
                     "status": "current"},
    "GB51022-2015": {"announcement_no": "2015 年第 991 号", "implemented": "2016-08-01",
                     "status": "current"},
    "GB55026-2022": {"announcement_no": "2022 年第 46 号", "implemented": "2022-10-01",
                     "status": "current"},
    "GB55027-2022": {"announcement_no": "2022 年第 45 号", "implemented": "2022-10-01",
                     "status": "current"},
    "CJT245-2021": {"name": "建筑屋面排水用雨水斗通用技术条件",
                    "name_verified": True, "announcement_no": "2021 年第 220 号",
                    "implemented": "2022-03-01", "status": "current",
                    "notes": "2021-12-23 发布，2022-03-01 实施，代替 CJ/T 245-2007《虹吸雨水斗》。"
                             "旧版名为「虹吸雨水斗」，新版扩为「建筑屋面排水用」，因此含重力流雨水斗要求——"
                             "这正是 6.6.3 能作为斗选型依据的原因。推荐性行业标准，非强条。"},
}

# 公告核实到的强条清单（仅登记与本子域相关的结论，不录条文数值）
MANDATORY_FINDINGS = {
    "GB50015-2019": "公告列强条 30 条，全部在第 3/4/6 章，**第 5 章（雨水）0 条**",
    "GB50014-2021": "公告列强条 14 条，含 4.1.6 与 5.15.3；两条的强条属性均已被 GB 55027-2022 废止",
    "GB50345-2012": "公告列强条 8 条（3.0.5/4.5.1/4.5.5/4.5.6/4.5.7/4.8.1/4.9.1/5.1.6），"
                    "2023-04-01 起被 GB 55030-2022 废止强条属性",
    "GB51022-2015": "公告列强条 **仅 14.2.5 一条**；表 11.1.11 不是强条",
    "GB55026-2022": "一句话含两种形态：「废止现行国家标准《城镇给水排水技术规范》GB 50788-2012」= 整部废止；"
                    "「和下列……相关强制性条文」= 部分废止",
    "GB55027-2022": "全部为「同时废止下列……相关强制性条文」，无整部废止",
}

# 新增的已废止条目（公告原文明确「同时废止」）
NEW_ABOLISHED = [
    {"id": "GB50345-2004", "standard": "GB 50345", "name": "屋面工程技术规范（2004 年版）",
     "group": "N", "role": "abolished", "in_scope": False, "status": "abolished",
     "name_verified": True, "implemented": None, "announcement_no": None,
     "sources": ["mohurd_notice"],
     "notes": "被 GB 50345-2012 替代（公告第 1395 号原文「原国家标准《屋面工程技术规范》GB 50345-2004 同时废止」）。"},
    {"id": "CJT245-2007", "standard": "CJ/T 245", "name": "虹吸雨水斗（2007 年版）",
     "group": "N", "role": "abolished", "in_scope": False, "status": "abolished",
     "name_verified": True, "implemented": None, "announcement_no": None,
     "sources": ["mohurd_notice"],
     "notes": "被 CJ/T 245-2021 替代。旧版只管虹吸斗，新版扩到建筑屋面排水用雨水斗（含重力流）。"},
]


def main() -> int:
    apply_mode = "--apply" in sys.argv
    data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    by_id = {s["id"]: s for s in data["standards"]}

    print("=" * 68)
    print("公告四查结论回写" + ("（已写入）" if apply_mode else "（仅报告）"))
    print("=" * 68)

    changed = []
    for sid, fields in VERIFIED.items():
        s = by_id.get(sid)
        if not s:
            print(f"  [跳过] {sid} 不在登记表中")
            continue
        for key, new in fields.items():
            old = s.get(key)
            if old != new:
                changed.append((sid, key, old, new))
                if apply_mode:
                    s[key] = new
        if apply_mode:
            s["last_checked"] = CHECKED_AT
            s["checked_by"] = CHECKED_BY
            s["evidence"] = EVIDENCE[sid]

    print(f"字段变更 {len(changed)} 处：")
    for sid, key, old, new in changed:
        print(f"  {sid:14s} {key:16s} {old!r} → {new!r}")

    # 新增已废止条目
    added = []
    for item in NEW_ABOLISHED:
        if item["id"] not in by_id:
            added.append(item["id"])
            if apply_mode:
                data["standards"].append(item)
    if added:
        print(f"新增已废止条目 {len(added)} 条：{', '.join(added)}")

    # 强条清单结论写入 notes（只写结论，不录数值）
    if apply_mode:
        for sid, finding in MANDATORY_FINDINGS.items():
            s = by_id.get(sid)
            if s:
                note = f"【公告核 2026-10-23】强条：{finding}。"
                if note not in (s.get("notes") or ""):
                    s["notes"] = (s.get("notes") or "") + ("\n" if s.get("notes") else "") + note

    # ---- 规则库数据修正：4.1.6 的强条属性已废止 ----
    print("-" * 68)
    draft_files = sorted(DRAFTS.glob("_draft_*.json"))
    fixed = []
    for path in draft_files:
        rules = json.loads(path.read_text(encoding="utf-8"))
        dirty = False
        for r in rules:
            if r.get("rule_id") != "GB50014-2021-4.1.6":
                continue
            if r.get("mandatory_level") != "strong_clause":
                continue
            old = r["mandatory_level"]
            r["mandatory_level"] = "recommended"
            r["mandatory_level_pending"] = {
                "_TEMPORARY": True,
                "intended_level": "clause",
                "normative_verb": "不得",
                "reason": "本条原为 GB 50014-2021 强条，但其强条属性已于 2022-10-01 被 "
                          "GB 55027-2022 废止（该公告废止清单第一项即含 4.1.6）。"
                          "标准本体现行、条文本条仍有效，但不得再作强条引用（CS 判据）。"
                          "同一要求现由 GB 55027-2022 以全文强制规范承载，校验时应引通规。",
                "blocks_production": True,
            }
            r["intended_level"] = "clause"
            r["normative_verb"] = "不得"
            r["blocks_production"] = True
            r["exceptions"] = (r.get("exceptions") or []) + [{
                "condition": "强条属性已废止：现行强制力来自 GB 55027-2022（全文强制），"
                             "本条只作为方法性条文引用，不得标 strong_clause",
                "clause_ref": "GB55027-2022-4.1.6",
            }]
            fixed.append(r["rule_id"])
            dirty = True
        if dirty and apply_mode:
            path.write_text(json.dumps(rules, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")

    if fixed:
        print(f"规则库修正 {len(fixed)} 条：{', '.join(fixed)}")
        print("  GB50014-2021-4.1.6  strong_clause → recommended(+pending, intended=clause)")
        print("  依据：GB 55027-2022 公告废止清单第一项含 4.1.6")
    else:
        print("规则库无需要修正的条目（可能已修正过）")

    print("-" * 68)
    print(f"核对人：{CHECKED_BY}    核对日期：{CHECKED_AT}")
    print("口径：按标准计。status=current 仅表示本轮查到官方公告且确认现行；"
          "未列入本脚本的标准一律保持原状态，不得视为已核。")

    if apply_mode:
        REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                            encoding="utf-8")
        print("\n已写入 sources/standards.json 与规则库。")
        print("请运行：python scripts/validate.py --drafts-only && python scripts/check_sources.py")
    else:
        print("\n以上为报告。加 --apply 写入。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
